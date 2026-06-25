"""Export assembler-resolved MWS variables to data/raw_jsons (shared by CLI and triage API)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import ROOT
from pymongo.database import Database

from services.assembler import VARIABLE_RESOLVERS, location_context, resolve_variable
from services.mws_enrich import enrich_mws_doc
from services.reasoner import DERIVED_VARIABLE_NAMES

RAW_JSONS_DIR = ROOT / "data" / "raw_jsons"

TIME_SERIES_VARIABLES = frozenset(
    {
        "annual_delta_g_mm",
        "annual_precipitation_mm",
        "annual_et_mm",
        "annual_runoff_mm",
        "seasonal_precipitation_mm",
        "seasonal_et_mm",
        "seasonal_runoff_mm",
        "seasonal_delta_g_mm",
        "drought_weeks",
        "drought_weeks_severe",
        "drought_weeks_moderate",
        "dry_spell_weeks",
        "monsoon_onset_date",
        "kharif_cropped_area_percent",
        "drought_causality_json",
        "drought_causality",
        "cropping_intensity",
        "crop_type_area_ha",
        "lulc_single_kharif_ha",
        "lulc_double_crop_ha",
        "lulc_cropland_ha",
        "lulc_shrub_scrub_ha",
        "lulc_barrenland_ha",
        "lulc_tree_forest_ha",
        "lulc_krz_water_ha",
        "lulc_ha",
        "swb_area_ha",
        "swb_total_area_ha",
        "swb_kharif_area_ha",
        "swb_rabi_area_ha",
        "swb_zaid_area_ha",
        "nrega_mws",
    }
)

EXPORT_VARIABLES = sorted(VARIABLE_RESOLVERS.keys())


def export_path_for_uid(uid: str) -> Path:
    safe = str(uid or "").strip().replace("/", "_")
    return RAW_JSONS_DIR / f"{safe}.json"


def variable_representation_type(name: str) -> str:
    if name in DERIVED_VARIABLE_NAMES:
        return "derived"
    if name in TIME_SERIES_VARIABLES:
        return "time_series"
    return "static"


def export_mws_variables(
    mws_doc: dict,
    *,
    case_study_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
        "case_study_refs": case_study_refs or [],
        "location_context": location_context(mws_doc),
        "present_variables": present,
        "derived_variables": derived,
        "missing_variables": missing,
        "variable_schema": {name: variable_representation_type(name) for name in EXPORT_VARIABLES},
    }


def write_mws_export(payload: dict[str, Any], *, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or RAW_JSONS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    uid = str(payload.get("uid") or "").strip()
    out_path = out_dir / f"{uid.replace('/', '_')}.json"
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str, ensure_ascii=False)
        handle.write("\n")
    return out_path


def load_mws_export(uid: str) -> dict[str, Any] | None:
    path = export_path_for_uid(uid)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_mws_export(
    db: Database,
    uid: str,
    *,
    case_study_refs: list[dict[str, Any]] | None = None,
    write: bool = True,
) -> dict[str, Any] | None:
    """Load export JSON or create it from Mongo mws_data."""
    existing = load_mws_export(uid)
    if existing is not None:
        return existing

    raw = db.mws_data.find_one({"uid": uid})
    if not raw:
        return None
    mws_doc = enrich_mws_doc(db, raw)
    payload = export_mws_variables(mws_doc, case_study_refs=case_study_refs)
    if write:
        write_mws_export(payload)
    return payload


def has_minimum_export_coverage(export: dict[str, Any], *, min_present: int = 5) -> bool:
    present = export.get("present_variables") or {}
    derived = export.get("derived_variables") or {}
    return len(present) + len(derived) >= min_present
