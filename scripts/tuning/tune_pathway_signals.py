#!/usr/bin/env python3
"""Fine-tune evidence-card signal expressions against case-study corpora (Plan 14 Phase 3)."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from eval.case_study_index import load_case_study_rows  # noqa: E402
from services.built_pathways import BUILT_PATHWAY_IDS  # noqa: E402
from services.card_patch_utils import compute_triage_card_patch, signal_expression  # noqa: E402
from services.claude_review_store import card_digest  # noqa: E402
from tuning.corpus_builder import (  # noqa: E402
    assign_labels,
    feasibility_ok,
    load_pathway_cards,
    pathway_section,
)
from tuning.grid_search import grid_search_signal  # noqa: E402
from tuning.patch_writer import (  # noqa: E402
    DEFAULT_PATCH_CATALOG,
    append_summary_csv,
    build_patch_doc,
    write_json_report,
    write_markdown_report,
    write_patch_catalog,
)
from tuning.template_canonicalisation import (  # noqa: E402
    extract_template_and_thresholds,
    signals_eligible_for_tuning,
)


def load_metadata() -> tuple[dict[str, Any], dict[str, Any]]:
    registry = json.loads((ROOT / "metadata" / "variable_registry.json").read_text(encoding="utf-8"))
    data_dictionary = json.loads((ROOT / "metadata" / "data_dictionary_v2.json").read_text(encoding="utf-8"))
    return registry, data_dictionary


def tune_pathway(
    causal_pathway: str,
    *,
    case_study_rows: list[dict[str, Any]],
    registry: dict[str, Any],
    data_dictionary: dict[str, Any],
    aer_filter: str | None = None,
) -> dict[str, Any]:
    cards = load_pathway_cards(causal_pathway)
    if not cards:
        raise ValueError(f"No evidence cards found for pathway: {causal_pathway}")

    production_system, observed_stress, _ = pathway_section(cards)
    positives, negatives, missing = assign_labels(
        case_study_rows,
        production_system=production_system,
        observed_stress=observed_stress,
        causal_pathway=causal_pathway,
        aer_filter=aer_filter,
    )

    report: dict[str, Any] = {
        "pathway_id": causal_pathway,
        "production_system": production_system,
        "observed_stress": observed_stress,
        "scope": "aer_specific" if aer_filter else "all_aers",
        "aer_filter": aer_filter,
        "n_positives": len(positives),
        "n_negatives": len(negatives),
        "missing_exports": missing,
        "feasible": feasibility_ok(positives, negatives),
        "cards_considered": len(cards),
        "signal_results": [],
        "card_patches": {},
    }

    if not feasibility_ok(positives, negatives):
        report["status"] = "INSUFFICIENT_DATA"
        return report

    template_groups: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for card in cards:
        for signal in signals_eligible_for_tuning(card):
            expr = signal_expression(signal)
            template, _ = extract_template_and_thresholds(expr)
            key = (str(signal.get("signal_id") or ""), template)
            template_groups.setdefault(key, []).append((card, signal))

    card_signal_updates: dict[str, dict[str, str]] = {}

    for (signal_id, template), members in sorted(template_groups.items()):
        representative_card, representative_signal = members[0]
        try:
            trace = grid_search_signal(
                representative_card,
                representative_signal,
                positives=positives,
                negatives=negatives,
                registry=registry,
                data_dictionary=data_dictionary,
            )
        except (SyntaxError, ValueError) as exc:
            trace = {
                "signal_id": signal_id,
                "template": template,
                "original_expression": signal_expression(representative_signal),
                "proposed_expression": signal_expression(representative_signal),
                "recommendation": "SKIPPED_PARSE_ERROR",
                "error": str(exc),
            }
        trace["template"] = template
        trace["cards_sharing_template"] = sorted(
            {str(card.get("card_id") or "").split("__")[-1] for card, _ in members}
        )

        proposed = str(trace.get("proposed_expression") or "")
        recommendation = str(trace.get("recommendation") or "KEEP")

        for card, signal in members:
            card_id = str(card.get("card_id") or "")
            row = {
                **trace,
                "pathway_id": causal_pathway,
                "card_id": card_id,
                "signal_id": signal_id,
                "n_positives": len(positives),
                "n_negatives": len(negatives),
                "original_expression": signal_expression(signal),
            }
            if recommendation == "UPDATE" and proposed:
                row["proposed_expression"] = proposed
                card_signal_updates.setdefault(card_id, {})[signal_id] = proposed
            else:
                row["proposed_expression"] = signal_expression(signal)
            report["signal_results"].append(row)

    for card in cards:
        card_id = str(card.get("card_id") or "")
        updates = card_signal_updates.get(card_id) or {}
        if not updates:
            continue
        edited_signals = []
        for signal in card.get("diagnostic_signals") or []:
            if not isinstance(signal, dict):
                continue
            sid = str(signal.get("signal_id") or "")
            if sid not in updates:
                continue
            edited = copy.deepcopy(signal)
            condition = dict(edited.get("condition") or {})
            condition["expression"] = updates[sid]
            edited["condition"] = condition
            edited_signals.append(edited)
        patch, changed_fields = compute_triage_card_patch(
            card,
            diagnostic_signals=edited_signals,
            confirmation_policy=None,
        )
        if not patch:
            continue
        report["card_patches"][card_id] = {
            "card_id": card_id,
            "patch": patch,
            "changed_fields": changed_fields,
            "reviewer": "signal_tuning",
            "raw_card_digest": card_digest(card),
            "tuning_updates": updates,
        }

    report["status"] = "ok"
    report["updates_count"] = sum(len(v) for v in card_signal_updates.values())
    report["patched_cards"] = len(report["card_patches"])
    return report


def merge_patch_docs(existing: dict[str, Any], pathway_report: dict[str, Any]) -> dict[str, Any]:
    cards = dict(existing.get("cards") or {})
    for card_id, entry in (pathway_report.get("card_patches") or {}).items():
        cards[card_id] = entry
    existing["cards"] = cards
    return existing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pathway", action="append", dest="pathways", help="Causal pathway id (repeatable)")
    parser.add_argument("--all-built", action="store_true", help="Tune every built pathway with case studies")
    parser.add_argument("--case-study-catalog", default="case_study_locations_v3.json")
    parser.add_argument("--patch-catalog", default=DEFAULT_PATCH_CATALOG)
    parser.add_argument("--reviewer", default="signal_tuning")
    parser.add_argument("--aer", default="", help="Optional AER code filter (e.g. AER-6)")
    parser.add_argument("--write-patches", action="store_true", help="Write metadata/triage_patches/<catalog>")
    parser.add_argument("--append-summary", action="store_true", default=True)
    args = parser.parse_args()

    registry, data_dictionary = load_metadata()
    catalog_path = ROOT / "metadata" / args.case_study_catalog
    if not catalog_path.is_file():
        print(f"Case study catalog not found: {catalog_path}", file=sys.stderr)
        return 1

    from eval.case_study_index import enrich_case_study_rows  # noqa: E402

    case_study_rows = enrich_case_study_rows(load_case_study_rows(include_stress_only=False))

    pathways = list(args.pathways or [])
    if args.all_built:
        pathways = sorted(BUILT_PATHWAY_IDS)
    if not pathways:
        pathways = ["drought"]

    patch_doc = build_patch_doc(
        catalog_filename=args.patch_catalog,
        reviewer=args.reviewer,
        card_patches={},
    )
    patch_path = ROOT / "metadata" / "triage_patches" / args.patch_catalog
    if patch_path.is_file():
        patch_doc = json.loads(patch_path.read_text(encoding="utf-8"))

    summary_rows: list[dict[str, Any]] = []

    for pathway_id in pathways:
        print(f"Tuning pathway: {pathway_id}")
        try:
            report = tune_pathway(
                pathway_id,
                case_study_rows=case_study_rows,
                registry=registry,
                data_dictionary=data_dictionary,
                aer_filter=args.aer or None,
            )
        except ValueError as exc:
            print(f"  skip: {exc}", file=sys.stderr)
            continue

        json_path = write_json_report(pathway_id, report)
        md_path = write_markdown_report(pathway_id, report)
        print(
            f"  positives={report.get('n_positives')} negatives={report.get('n_negatives')} "
            f"updates={report.get('updates_count', 0)} status={report.get('status')}"
        )
        print(f"  report: {json_path}")
        print(f"  report: {md_path}")

        summary_rows.extend(report.get("signal_results") or [])
        if args.write_patches and report.get("card_patches"):
            from tuning.patch_writer import utc_now

            for entry in report["card_patches"].values():
                entry["updated_at"] = utc_now()
                entry["reviewer"] = args.reviewer
            patch_doc = merge_patch_docs(patch_doc, report)

    if args.write_patches:
        from tuning.patch_writer import utc_now

        patch_doc["updated_at"] = utc_now()
        patch_doc["reviewer"] = args.reviewer
        out = write_patch_catalog(args.patch_catalog, patch_doc)
        print(f"Wrote triage patches: {out} ({len(patch_doc.get('cards') or {})} cards)")

    if args.append_summary and summary_rows:
        summary_path = append_summary_csv(summary_rows)
        print(f"Summary: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
