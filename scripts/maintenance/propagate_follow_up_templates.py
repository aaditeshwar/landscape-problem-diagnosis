#!/usr/bin/env python3
"""Propagate reviewed MCQ follow-up templates from review_unique_follow_ups.csv."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data/evidence_cards/raw"
CSV_PATH = ROOT / "reports/review_unique_follow_ups.csv"
REVIEWED_BY_FP = ROOT / "metadata/reviewed_follow_up_by_fingerprint.json"
REPORT = ROOT / "reports/follow_up_propagation_review.md"

sys.path.insert(0, str(ROOT / "scripts"))
from lib.follow_up_utils import (  # noqa: E402
    choice_summary,
    choice_summary_from_map,
    fingerprint_short,
    follow_up_fingerprint,
    parse_choice_summary,
    sync_choices_from_template,
)


def build_groups() -> dict[str, list[tuple[str, dict]]]:
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for path in sorted(RAW_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        card_id = str(card.get("card_id") or path.stem)
        for question in card.get("missing_variable_questions") or []:
            if not isinstance(question, dict) or question.get("response_type") != "mcq":
                continue
            fp = follow_up_fingerprint(question)
            groups[fp].append((card_id, question))
    return groups


def find_group(groups: dict[str, list[tuple[str, dict]]], row: dict) -> tuple[str, list[tuple[str, dict]]] | None:
    fp_short = str(row.get("fingerprint") or "").strip()
    example = str(row.get("example_card_id") or "").strip()
    variable = str(row.get("variable") or "").strip()

    for fp, items in groups.items():
        if fingerprint_short(fp) == fp_short:
            return fp, items

    for fp, items in groups.items():
        if not fp.startswith(f"{variable}::"):
            continue
        if any(cid == example for cid, _ in items):
            return fp, items
    return None


def load_card(card_id: str) -> tuple[Path, dict]:
    path = RAW_DIR / f"{card_id}.json"
    with path.open(encoding="utf-8") as handle:
        return path, json.load(handle)


def question_for_variable(card: dict, variable: str) -> dict | None:
    for question in card.get("missing_variable_questions") or []:
        if not isinstance(question, dict):
            continue
        if str(question.get("missing_variable") or "") == variable and question.get("response_type") == "mcq":
            return question
    return None


def export_reviewed_templates(groups: dict[str, list[tuple[str, dict]]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fp, items in groups.items():
        if not items:
            continue
        _, question = items[0]
        out[fingerprint_short(fp)] = {
            "variable": question.get("missing_variable"),
            "question_mode": question.get("question_mode"),
            "choice_summary": choice_summary(question),
            "choices": question.get("choices") or [],
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--csv",
        type=Path,
        default=CSV_PATH,
        help="Reviewed follow-up catalog (default: reports/review_unique_follow_ups.csv)",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Missing {args.csv}")
        return 1

    groups = build_groups()
    rows = list(csv.DictReader(args.csv.open(encoding="utf-8")))

    updated_cards: set[str] = set()
    report_lines = [
        "# Follow-up propagation review",
        "",
        f"Source catalog: `{args.csv}`",
        "",
    ]

    for row in rows:
        decision = str(row.get("review_decision") or "").strip().lower()
        if decision in {"", "needs_review", "ok"}:
            continue

        found = find_group(groups, row)
        if not found:
            print(f"WARN: no group for {row.get('fingerprint')} {row.get('example_card_id')}")
            continue

        fp, items = found
        example_id = str(row.get("example_card_id") or items[0][0])
        variable = str(row.get("variable") or "")

        _, example_card = load_card(example_id)
        template_q = question_for_variable(example_card, variable)
        if not template_q:
            print(f"WARN: example {example_id} missing MCQ for {variable}")
            continue

        summary_map = parse_choice_summary(str(row.get("choice_summary") or ""))
        if decision == "apply_suggested":
            summary_map = parse_choice_summary(str(row.get("suggested_choice_summary") or ""))
        elif decision == "keep_none":
            summary_map = parse_choice_summary(str(row.get("choice_summary") or ""))
        elif decision == "propagate":
            summary_map = parse_choice_summary(str(row.get("choice_summary") or ""))
        if not summary_map:
            summary_map = parse_choice_summary(choice_summary(template_q))

        group_changes = 0
        for card_id, _ in items:
            path, card = load_card(card_id)
            target_q = question_for_variable(card, variable)
            if not target_q:
                continue
            changes = sync_choices_from_template(
                target_card=card,
                target_question=target_q,
                template_question=template_q,
                summary_map=summary_map,
            )
            if changes:
                group_changes += changes
                if not args.dry_run:
                    with path.open("w", encoding="utf-8") as handle:
                        json.dump(card, handle, indent=2, ensure_ascii=False)
                        handle.write("\n")
                updated_cards.add(card_id)

        report_lines.extend(
            [
                f"## `{row.get('fingerprint')}` — `{variable}`",
                "",
                f"- **Example card:** `{example_id}`",
                f"- **Cards in group:** {len(items)}",
                f"- **Review decision:** `{row.get('review_decision')}`",
                f"- **Choice summary:** `{row.get('choice_summary')}`",
                f"- **Applied summary:** `{choice_summary_from_map(summary_map) if summary_map else row.get('choice_summary')}`",
                f"- **Updates applied:** {group_changes} field change(s) across group",
                "",
            ]
        )

    if not args.dry_run:
        refreshed_groups = build_groups()
        templates = export_reviewed_templates(refreshed_groups)
        REVIEWED_BY_FP.parent.mkdir(parents=True, exist_ok=True)
        with REVIEWED_BY_FP.open("w", encoding="utf-8") as handle:
            json.dump(templates, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"Exported {len(templates)} template(s) to {REVIEWED_BY_FP}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"{'Would update' if args.dry_run else 'Updated'} {len(updated_cards)} card(s) from {len(rows)} template row(s)")
    print(f"Wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
