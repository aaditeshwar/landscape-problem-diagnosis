#!/usr/bin/env python3
"""Precompute global variable CDF dashboards for triage sections."""

from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from db import get_db  # noqa: E402
from services.built_pathways import BUILT_PATHWAY_IDS, built_pathways_for_section, section_has_built_pathways  # noqa: E402
from services.expression_variable_access import (  # noqa: E402
    accesses_from_card,
    resolve_access_value,
)
from services.mws_export import ensure_mws_export, has_minimum_export_coverage  # noqa: E402
from services.signal_evaluator import merge_export_variables  # noqa: E402
from services.variable_categories import categorize_variable, category_sort_key  # noqa: E402
from services.variable_registry import variable_type_catalog  # noqa: E402
from services.triage_index import (  # noqa: E402
    framework_actual_pathways,
    group_instances_into_sections,
    load_case_study_rows_from_file,
    section_key,
)

OUTPUT_DIR = ROOT / "data" / "triage_dashboard"
RAW_CARDS_DIR = ROOT / "data" / "evidence_cards" / "raw"
DEFAULT_CATALOG = "case_study_locations_v2.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scalar_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def build_cdf(values: list[float], *, downsample_fraction: float = 0.5) -> list[list[float]]:
    if not values:
        return []
    ordered = sorted(values)
    n = len(ordered)
    points: list[list[float]] = []
    for idx, value in enumerate(ordered, start=1):
        percentile = round(idx / n, 6)
        if points and points[-1][0] == value:
            points[-1][1] = percentile
        else:
            points.append([value, percentile])
    return _downsample_cdf(points, fraction=downsample_fraction)


def _downsample_cdf(points: list[list[float]], *, fraction: float = 0.5) -> list[list[float]]:
    """Keep ~fraction of CDF points (min 2) for smaller dashboard payloads."""
    if len(points) <= 2:
        return points
    target = max(2, int(round(len(points) * fraction)))
    if target >= len(points):
        return points
    step = (len(points) - 1) / (target - 1)
    picked: list[list[float]] = []
    last_idx = -1
    for i in range(target):
        idx = int(round(i * step))
        if idx != last_idx:
            picked.append(points[idx])
            last_idx = idx
    if picked[-1][0] != points[-1][0]:
        picked.append(points[-1])
    return picked


def percentile_of(value: float, ordered: list[float]) -> float | None:
    if not ordered:
        return None
    idx = bisect_right(ordered, value)
    return round(idx / len(ordered), 6)


def cards_for_section(
    db,
    production_system: str,
    observed_stress: str,
    *,
    case_instances: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    pathways = built_pathways_for_section(production_system, observed_stress)
    cards: list[dict[str, Any]] = []
    seen_pathways: set[str] = set()
    for pid in pathways:
        doc = db.evidence_cards.find_one(
            {
                "causal_pathway": pid,
                "production_system": production_system,
                "observed_stress": observed_stress,
            },
            {"_id": 0},
        )
        if doc:
            cards.append(doc)
            seen_pathways.add(pid)

    if len(seen_pathways) < len(pathways) and case_instances:
        from services.triage_card_map import load_mws_doc, resolve_cards_for_mws

        seen_card_ids: set[str] = set()
        for card in cards:
            seen_card_ids.add(str(card.get("card_id") or ""))
        for instance in case_instances:
            mws_id = str(instance.get("mws_id") or "")
            if not mws_id:
                continue
            mws_doc = load_mws_doc(db, mws_id)
            if not mws_doc:
                continue
            resolved = resolve_cards_for_mws(db, mws_doc)
            for pid in pathways:
                if pid in seen_pathways:
                    continue
                card = resolved.get(pid)
                if not card:
                    continue
                if str(card.get("production_system") or "") not in ("", production_system):
                    continue
                if str(card.get("observed_stress") or "") not in ("", observed_stress):
                    continue
                card_id = str(card.get("card_id") or "")
                if card_id and card_id in seen_card_ids:
                    continue
                cards.append(card)
                seen_card_ids.add(card_id)
                seen_pathways.add(pid)

    if cards:
        return cards

    if RAW_CARDS_DIR.is_dir():
        for path in sorted(RAW_CARDS_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("production_system") != production_system:
                continue
            if payload.get("observed_stress") != observed_stress:
                continue
            pathway = str(payload.get("causal_pathway") or "")
            if pathway in pathways and pathway not in seen_pathways:
                cards.append(payload)
                seen_pathways.add(pathway)
    return cards


def collect_access_keys(
    production_system: str,
    observed_stress: str,
    cards: list[dict[str, Any]],
    extra_variables: list[str] | None,
) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for card in cards:
        for key in accesses_from_card(card):
            if key not in seen:
                seen.add(key)
                keys.append(key)
    for name in extra_variables or []:
        if name not in seen:
            seen.add(name)
            keys.append(name)
    return keys


def _is_categorical_access(access: str, type_catalog: dict[str, dict[str, Any]]) -> bool:
    base = access.split("[", 1)[0].split("(", 1)[0]
    info = type_catalog.get(base) or {}
    shape = str(info.get("shape") or "")
    unit = str(info.get("unit") or "").lower()
    return shape == "scalar_categorical" or "categorical" in unit


def _categorical_distribution(values: list[str]) -> list[dict[str, Any]]:
    if not values:
        return []
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        label = str(value).strip() if value is not None else "(missing)"
        if not label:
            label = "(missing)"
        counts[label] += 1
    total = len(values)
    rows = [{"label": label, "count": count, "percent": round(100 * count / total, 2)} for label, count in counts.items()]
    rows.sort(key=lambda item: (-item["percent"], item["label"]))
    return rows


def _is_scalar_dashboard_access(access: str, type_catalog: dict[str, dict[str, Any]]) -> bool:
    """Skip list/dict/seasonal-series variables; keep indexed yearly scalars and aggregates."""
    key = str(access or "").strip()
    base = key
    for func in ("mean", "min", "max", "sum", "len", "sorted"):
        prefix = f"{func}("
        if key.startswith(prefix) and key.endswith(")"):
            base = key[len(prefix) : -1]
            break
    if "[" in base:
        base = base.split("[", 1)[0]
    info = type_catalog.get(base) or {}
    shape = str(info.get("shape") or "")
    if shape in {"dict", "time_series_seasonal"}:
        return False
    if shape == "time_series_yearly" and "[" not in key and not key.startswith(("mean(", "min(", "max(", "sum(")):
        return False
    return True


def build_section_dashboard(
    db,
    *,
    production_system: str,
    observed_stress: str,
    exports: dict[str, dict[str, Any]],
    case_instances: list[dict[str, Any]],
    extra_variables: list[str] | None = None,
) -> dict[str, Any]:
    cards = cards_for_section(
        db,
        production_system,
        observed_stress,
        case_instances=case_instances,
    )
    access_keys = collect_access_keys(production_system, observed_stress, cards, extra_variables)
    type_catalog = variable_type_catalog()
    flat_variables: dict[str, Any] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for access in access_keys:
        if not _is_scalar_dashboard_access(access, type_catalog):
            continue
        base = access.split("[", 1)[0].split("(", 1)[0]
        type_info = type_catalog.get(base) or {}
        category = categorize_variable(base)

        if _is_categorical_access(access, type_catalog):
            raw_values: list[str] = []
            for export in exports.values():
                merged = merge_export_variables(export)
                value = resolve_access_value(access, merged)
                if value is None or isinstance(value, (dict, list)):
                    continue
                raw_values.append(str(value))
            entry = {
                "access": access,
                "chart_type": "categorical",
                "unit": type_info.get("unit"),
                "sample_count": len(raw_values),
                "distribution": _categorical_distribution(raw_values),
            }
        else:
            scalar_values: list[float] = []
            samples: list[dict[str, Any]] = []
            for uid, export in exports.items():
                merged = merge_export_variables(export)
                scalar = _scalar_or_none(resolve_access_value(access, merged))
                if scalar is not None:
                    scalar_values.append(scalar)
                    samples.append({"mws_id": uid, "value": scalar})
            ordered = sorted(scalar_values)
            x_max = ordered[-1] if ordered else None
            entry = {
                "access": access,
                "chart_type": "cdf",
                "unit": type_info.get("unit"),
                "sample_count": len(samples),
                "cdf": build_cdf(ordered),
                "x_max": x_max,
                "samples": samples,
            }

        if entry["chart_type"] == "cdf" and not entry.get("cdf"):
            continue
        if entry["chart_type"] == "categorical" and not entry.get("distribution"):
            continue

        flat_variables[access] = entry
        grouped[category].append(entry)

    variable_groups = [
        {"category": category, "variables": grouped[category]}
        for category in sorted(grouped.keys(), key=category_sort_key)
    ]

    return {
        "production_system": production_system,
        "observed_stress": observed_stress,
        "section_key": section_key(production_system, observed_stress),
        "generated_at": _utc_now(),
        "mws_count": len(exports),
        "case_study_instances": [
            {
                "case_study_id": item.get("case_study_id"),
                "mws_id": item.get("mws_id"),
                "expected_pathway": item.get("expected_pathway"),
                "stress_only": item.get("stress_only"),
            }
            for item in case_instances
        ],
        "variable_groups": variable_groups,
        "variables": flat_variables,
    }


def load_all_exports(db, *, limit: int | None = None) -> dict[str, dict[str, Any]]:
    exports: dict[str, dict[str, Any]] = {}
    cursor = db.mws_data.find({}, {"uid": 1})
    if limit:
        cursor = cursor.limit(limit)
    for doc in cursor:
        uid = str(doc.get("uid") or "").strip()
        if not uid:
            continue
        export = ensure_mws_export(db, uid)
        if export and has_minimum_export_coverage(export):
            exports[uid] = export
    return exports


def parse_section_arg(value: str) -> tuple[str, str]:
    if "/" not in value:
        raise ValueError(f"Expected production/stress, got {value!r}")
    production, stress = value.split("/", 1)
    return production.strip(), stress.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, help="Case study catalog filename")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--section", action="append", help="Only build Agriculture/water_scarcity (repeatable)")
    parser.add_argument("--add-variable", action="append", help="Extra variable access key for all built sections")
    parser.add_argument("--limit-mws", type=int, help="Limit MWS count (debug)")
    args = parser.parse_args()

    db = get_db()
    print("Loading global MWS exports…")
    exports = load_all_exports(db, limit=args.limit_mws)
    print(f"  {len(exports)} MWS with export coverage")

    instances = load_case_study_rows_from_file(args.catalog)
    sections = [
        section
        for section in group_instances_into_sections(instances)
        if section_has_built_pathways(section["production_system"], section["observed_stress"])
    ]
    if args.section:
        wanted = {parse_section_arg(item) for item in args.section}
        sections = [
            section
            for section in sections
            if (section["production_system"], section["observed_stress"]) in wanted
        ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_sections: list[dict[str, str]] = []

    for section in sections:
        production = section["production_system"]
        stress = section["observed_stress"]
        key = section["section_key"]
        payload = build_section_dashboard(
            db,
            production_system=production,
            observed_stress=stress,
            exports=exports,
            case_instances=section["instances"],
            extra_variables=args.add_variable,
        )
        out_path = args.output_dir / f"{key}.json"
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str, ensure_ascii=False)
            handle.write("\n")
        manifest_sections.append({"section_key": key, "filename": out_path.name})
        print(f"  wrote {out_path.name} ({payload['mws_count']} MWS, {len(payload['variables'])} variables)")

    manifest = {"generated_at": _utc_now(), "sections": manifest_sections}
    manifest_path = args.output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"\nWrote {len(manifest_sections)} section dashboards to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
