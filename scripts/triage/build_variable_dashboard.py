#!/usr/bin/env python3
"""Precompute global variable CDF dashboards per diagnosis section.

Sections = union of (1) case-study catalog (production_system, observed_stress) pairs
and (2) evidence-card sections with built pathways. Sections without built cards still
appear with empty variable charts. CDFs use every MWS in the database with export coverage.
"""

from __future__ import annotations

import argparse
import json
import math
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
from services.built_pathways import built_pathway_tuples, built_pathways_for_section  # noqa: E402
from services.expression_variable_access import (  # noqa: E402
    accesses_from_card,
    resolve_access_value,
)
from services.mws_export import ensure_mws_export, has_minimum_export_coverage  # noqa: E402
from services.signal_evaluator import merge_export_variables  # noqa: E402
from services.variable_categories import categorize_variable, category_sort_key  # noqa: E402
from services.variable_registry import variable_type_catalog  # noqa: E402
from services.dashboard_policy import excluded_dashboard_variables  # noqa: E402
from services.triage_index import group_instances_into_sections, load_case_study_rows_from_file, section_key  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "triage_dashboard"
RAW_CARDS_DIR = ROOT / "data" / "evidence_cards" / "raw"
DEFAULT_CATALOG = "case_study_locations_v3.json"


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


CDF_CENTILES = 100
TRIM_FRACTION = 0.001
MAX_REMOVED_MWS = 20


def build_cdf(values: list[float], *, centiles: int = CDF_CENTILES) -> list[list[float]]:
    """Empirical CDF as at most *centiles* [value, percentile] points (1% steps)."""
    if not values:
        return []
    ordered = sorted(values)
    n = len(ordered)
    points: list[list[float]] = []
    steps = max(1, min(centiles, n))
    for i in range(1, steps + 1):
        percentile = round(i / steps, 6)
        idx = min(n - 1, max(0, int(math.ceil(percentile * n)) - 1))
        value = ordered[idx]
        if points and points[-1][0] == value:
            points[-1][1] = percentile
        else:
            points.append([value, percentile])
    return points


def _cdf_variant_key(trim_top: bool, trim_bottom: bool, remove_zeros: bool, log_scale: bool) -> str:
    return f"{int(trim_top)}{int(trim_bottom)}{int(remove_zeros)}{int(log_scale)}"


def _removed_bucket(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(samples),
        "mws_ids": [str(item["mws_id"]) for item in samples[:MAX_REMOVED_MWS]],
    }


def _remove_zero_samples(samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    removed = [item for item in samples if item["value"] == 0]
    kept = [item for item in samples if item["value"] != 0]
    return kept, removed


def _trim_samples(
    samples: list[dict[str, Any]],
    *,
    trim_top: bool,
    trim_bottom: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(samples, key=lambda item: item["value"])
    n = len(ordered)
    top_cut = math.ceil(n * TRIM_FRACTION) if trim_top else 0
    bottom_cut = math.ceil(n * TRIM_FRACTION) if trim_bottom else 0
    kept = ordered[bottom_cut : max(bottom_cut, n - top_cut)]
    removed_top = ordered[n - top_cut :] if trim_top else []
    removed_bottom = ordered[:bottom_cut] if trim_bottom else []
    return kept, removed_top, removed_bottom


def build_cdf_variants(
    samples: list[dict[str, Any]],
    *,
    global_x_max: float | None,
) -> dict[str, dict[str, Any]]:
    """Precompute centile CDFs for all toggle combinations (2^4 = 16)."""
    variants: dict[str, dict[str, Any]] = {}
    for trim_top in (False, True):
        for trim_bottom in (False, True):
            for remove_zeros in (False, True):
                for log_scale in (False, True):
                    working = samples
                    removed_zeros: list[dict[str, Any]] = []
                    if remove_zeros:
                        working, removed_zeros = _remove_zero_samples(working)
                    kept, removed_top, removed_bottom = _trim_samples(
                        working,
                        trim_top=trim_top,
                        trim_bottom=trim_bottom,
                    )
                    values = [float(item["value"]) for item in kept]
                    cdf = build_cdf(values)
                    has_data_filters = trim_top or trim_bottom or remove_zeros
                    if has_data_filters:
                        x_max = values[-1] if values else None
                    else:
                        x_max = global_x_max
                    key = _cdf_variant_key(trim_top, trim_bottom, remove_zeros, log_scale)
                    variants[key] = {
                        "trim_top": trim_top,
                        "trim_bottom": trim_bottom,
                        "remove_zeros": remove_zeros,
                        "log_scale": log_scale,
                        "cdf": cdf,
                        "sample_count": len(kept),
                        "x_max": x_max,
                        "removed": {
                            "zeros": _removed_bucket(removed_zeros),
                            "top": _removed_bucket(removed_top),
                            "bottom": _removed_bucket(removed_bottom),
                        },
                    }
    return variants


def percentile_of(value: float, ordered: list[float]) -> float | None:
    if not ordered:
        return None
    idx = bisect_right(ordered, value)
    return round(idx / len(ordered), 6)


def built_dashboard_sections() -> list[dict[str, str]]:
    """Sections with built pathways, derived from evidence cards (not case-study catalog)."""
    seen: set[tuple[str, str]] = set()
    sections: list[dict[str, str]] = []
    for production, stress, _pathway in sorted(built_pathway_tuples()):
        key = (production, stress)
        if key in seen:
            continue
        seen.add(key)
        sections.append(
            {
                "production_system": production,
                "observed_stress": stress,
                "section_key": section_key(production, stress),
            }
        )
    return sections


def dashboard_sections(catalog_filename: str) -> list[dict[str, str]]:
    """Union of case-study catalog sections and evidence-card sections with built pathways."""
    by_key: dict[str, dict[str, str]] = {}

    for section in built_dashboard_sections():
        by_key[section["section_key"]] = section

    instances = load_case_study_rows_from_file(catalog_filename)
    for section in group_instances_into_sections(instances):
        key = section["section_key"]
        if key in by_key:
            continue
        by_key[key] = {
            "production_system": section["production_system"],
            "observed_stress": section["observed_stress"],
            "section_key": key,
        }

    return sorted(
        by_key.values(),
        key=lambda item: (item["production_system"], item["observed_stress"]),
    )


def cards_for_section(
    db,
    production_system: str,
    observed_stress: str,
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
    extra_variables: list[str] | None = None,
) -> dict[str, Any]:
    cards = cards_for_section(db, production_system, observed_stress)
    access_keys = collect_access_keys(production_system, observed_stress, cards, extra_variables)
    type_catalog = variable_type_catalog()
    flat_variables: dict[str, Any] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skip_variables = excluded_dashboard_variables()

    for access in access_keys:
        if access in skip_variables:
            continue
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
            samples: list[dict[str, Any]] = []
            for uid, export in exports.items():
                merged = merge_export_variables(export)
                scalar = _scalar_or_none(resolve_access_value(access, merged))
                if scalar is not None:
                    samples.append({"mws_id": uid, "value": scalar})
            ordered = sorted(item["value"] for item in samples)
            global_x_max = ordered[-1] if ordered else None
            cdf_variants = build_cdf_variants(samples, global_x_max=global_x_max)
            entry = {
                "access": access,
                "chart_type": "cdf",
                "unit": type_info.get("unit"),
                "sample_count": len(samples),
                "x_max": global_x_max,
                "cdf_variants": cdf_variants,
            }

        if entry["chart_type"] == "cdf":
            has_cdf = any(variant.get("cdf") for variant in (entry.get("cdf_variants") or {}).values())
            if not has_cdf:
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
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, help="Case study catalog for section list")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--section", action="append", help="Only build Agriculture/water_scarcity (repeatable)")
    parser.add_argument("--add-variable", action="append", help="Extra variable access key for all built sections")
    parser.add_argument("--limit-mws", type=int, help="Limit MWS count (debug)")
    args = parser.parse_args()

    db = get_db()
    print("Loading global MWS exports…")
    exports = load_all_exports(db, limit=args.limit_mws)
    print(f"  {len(exports)} MWS with export coverage")

    sections = dashboard_sections(args.catalog)
    if args.section:
        wanted = {parse_section_arg(item) for item in args.section}
        sections = [
            section
            for section in sections
            if (section["production_system"], section["observed_stress"]) in wanted
        ]

    if not sections:
        print("No dashboard sections found (check case study catalog and evidence cards).")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_sections: list[dict[str, str]] = []
    written_keys: set[str] = set()

    for section in sections:
        production = section["production_system"]
        stress = section["observed_stress"]
        key = section["section_key"]
        written_keys.add(key)
        payload = build_section_dashboard(
            db,
            production_system=production,
            observed_stress=stress,
            exports=exports,
            extra_variables=args.add_variable,
        )
        out_path = args.output_dir / f"{key}.json"
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str, ensure_ascii=False)
            handle.write("\n")
        manifest_sections.append({"section_key": key, "filename": out_path.name})
        print(f"  wrote {out_path.name} ({payload['mws_count']} MWS, {len(payload['variables'])} variables)")

    for path in args.output_dir.glob("*.json"):
        if path.name == "manifest.json" or path.stem in written_keys:
            continue
        path.unlink()
        print(f"  removed stale {path.name}")

    manifest = {"generated_at": _utc_now(), "sections": manifest_sections}
    manifest_path = args.output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"\nWrote {len(manifest_sections)} section dashboards to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
