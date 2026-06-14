#!/usr/bin/env python3
"""Export assembler-resolved MWS variables for case-study locations.

For each MWS listed in metadata/case_study_locations_v2.json, writes a JSON file
under data/raw_jsons/ containing all variables supported by the assembler (as sent
to the reasoning LLM): raw present_variables plus derived/computed scalars.

Variable names and value shapes match the diagnosis pipeline (time series as
year-keyed dicts, static values as scalars/objects, derived as scalars).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from config import METADATA_DIR  # noqa: E402
from db import get_db  # noqa: E402
from services.assembler import (  # noqa: E402
    VARIABLE_RESOLVERS,
    location_context,
    resolve_variable,
)
from services.mws_enrich import enrich_mws_doc  # noqa: E402
from services.reasoner import DERIVED_VARIABLE_NAMES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CASE_STUDY_PATH = METADATA_DIR / "case_study_locations_v2.json"
OUTPUT_DIR = ROOT / "data" / "raw_jsons"

# Assembler resolver keys that return agricultural-year time series (or nested series).
TIME_SERIES_VARIABLES = frozenset(
    {
        "annual_delta_g_mm",
        "annual_precipitation_mm",
        "annual_et_mm",
        "annual_runoff_mm",
        "seasonal_precipitation_mm",
        "drought_weeks_severe",
        "drought_weeks_moderate",
        "dry_spell_weeks",
        "monsoon_onset_date",
        "kharif_cropped_area_percent",
        "drought_causality_json",
        "drought_causality",
        "cropping_intensity",
        "lulc_single_kharif_ha",
        "lulc_double_crop_ha",
        "lulc_cropland_ha",
        "lulc_shrub_scrub_ha",
        "lulc_barrenland_ha",
        "lulc_tree_forest_ha",
        "lulc_krz_water_ha",
        "swb_total_area_ha",
        "swb_kharif_area_ha",
        "swb_rabi_area_ha",
        "swb_zaid_area_ha",
    }
)

EXPORT_VARIABLES = sorted(VARIABLE_RESOLVERS.keys())


def load_case_study_mws() -> dict[str, list[dict[str, Any]]]:
    """Return {mws_id: [case_study_entry, ...]} from nested framework JSON."""
    with CASE_STUDY_PATH.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    by_mws: dict[str, list[dict[str, Any]]] = {}

    def walk(node: Any, production: str | None = None, stress: str | None = None, pathway: str | None = None) -> None:
        if isinstance(node, dict):
            if "case_studies" in node and isinstance(node["case_studies"], list):
                for entry in node["case_studies"]:
                    mws_id = entry.get("mws_id")
                    if not mws_id:
                        continue
                    ref = {
                        "case_study_id": entry.get("case_study_id"),
                        "lat": entry.get("lat"),
                        "lng": entry.get("lng"),
                        "production_system": production,
                        "observed_stress": stress,
                        "causal_pathway": None if pathway == "__stress_only__" else pathway,
                    }
                    by_mws.setdefault(str(mws_id), []).append(ref)
            for key, value in node.items():
                if key == "production_systems":
                    for prod, pdata in (value or {}).items():
                        for stress, sdata in (pdata.get("observed_stresses") or {}).items():
                            for pathway_id, pdata2 in (sdata.get("causal_pathways") or {}).items():
                                walk(pdata2, prod, stress, pathway_id)
                elif key not in ("meta", "diagnosis_framework", "normalisation_note", "note"):
                    walk(value, production, stress, pathway)
        elif isinstance(node, list):
            for item in node:
                walk(item, production, stress, pathway)

    walk(raw.get("diagnosis_framework") or raw)
    return by_mws


def variable_representation_type(name: str) -> str:
    if name in DERIVED_VARIABLE_NAMES:
        return "derived"
    if name in TIME_SERIES_VARIABLES:
        return "time_series"
    return "static"


def export_mws_variables(mws_doc: dict, case_study_refs: list[dict[str, Any]]) -> dict[str, Any]:
    present: dict[str, Any] = {}
    derived: dict[str, Any] = {}
    missing: list[str] = []

    for name in EXPORT_VARIABLES:
        value = resolve_variable(mws_doc, name)
        if value is None:
            missing.append(name)
            continue
        if name in DERIVED_VARIABLE_NAMES:
            derived[name] = value
        else:
            present[name] = value

    return {
        "uid": mws_doc.get("uid"),
        "case_study_refs": case_study_refs,
        "location_context": location_context(mws_doc),
        "present_variables": present,
        "derived_variables": derived,
        "missing_variables": missing,
        "variable_schema": {name: variable_representation_type(name) for name in EXPORT_VARIABLES},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uid", action="append", help="Export only these MWS uids (repeatable)")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Output directory")
    args = parser.parse_args()

    case_studies = load_case_study_mws()
    if args.uid:
        targets = {uid: case_studies.get(uid, []) for uid in args.uid}
    else:
        targets = case_studies

    if not targets:
        print("No case-study MWS ids found.")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    db = get_db()

    written = 0
    not_found: list[str] = []
    for mws_id, refs in sorted(targets.items()):
        raw = db.mws_data.find_one({"uid": mws_id})
        if not raw:
            not_found.append(mws_id)
            continue
        mws = enrich_mws_doc(db, raw)
        payload = export_mws_variables(mws, refs)
        out_path = args.output_dir / f"{mws_id.replace('/', '_')}.json"
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str, ensure_ascii=False)
            fh.write("\n")
        written += 1
        n_present = len(payload["present_variables"])
        n_derived = len(payload["derived_variables"])
        print(f"  {mws_id}: {n_present} raw + {n_derived} derived -> {out_path.name}")

    print(f"\nExported {written}/{len(targets)} MWS variable bundles to {args.output_dir}")
    if not_found:
        print(f"Not found in Mongo mws_data ({len(not_found)}): {', '.join(not_found)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
