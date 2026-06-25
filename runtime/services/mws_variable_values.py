"""Per-MWS variable values for the variable catalog browser."""

from __future__ import annotations

from typing import Any

from pymongo.database import Database

from services.assembler import location_context, resolve_variable
from services.expression_variable_access import format_access_value
from services.mws_export import TIME_SERIES_VARIABLES
from services.reasoner import DERIVED_VARIABLE_NAMES
from services.triage_card_map import load_mws_doc
from services.variable_registry import load_data_dictionary

_SEASONAL_FIELD_BY_VARIABLE = {
    "seasonal_precipitation_mm": "precipitation_mm",
    "seasonal_et_mm": "et_mm",
    "seasonal_runoff_mm": "runoff_mm",
    "seasonal_delta_g_mm": "delta_g_mm",
}

_CATEGORY_DICT_VARIABLES = frozenset(
    {
        "terrain_area_percent",
        "terrain_lulc_plain_percent",
        "terrain_lulc_slope_percent",
        "facility_distances_km",
        "aquifer_lithology_percent",
        "acwadam_class_percent",
    }
)

_LINE_ONLY_VARIABLES = frozenset(
    {
        "dry_spell_weeks",
        "delta_g_mm",
        "et_mm",
        "runoff_mm",
        "precipitation_mm",
        "cropping_intensity",
        "kharif_cropped_area_ha",
        "kharif_cropped_area_percent",
        "kharif_cropped_sqkm",
        "kharif_drought_total_weeks",
        "single_kharif_area_ha",
        "single_non_kharif_area_ha",
        "triple_crop_area_ha",
    }
)

_CATEGORY_BAR_VARIABLES = frozenset({"stream_order_area_percent"})

_CD_BREAKUP_VARIABLES = {
    "cd_degradation_ha": "cd_degradation_breakup",
    "cd_deforestation_ha": "cd_deforestation_breakup",
    "cd_crop_intensity_ha": "cd_crop_intensity_breakup",
}


def _is_year_keyed_dict(value: dict[Any, Any]) -> bool:
    if not value:
        return False
    sample = list(value.keys())[:5]
    return all(str(key).isdigit() for key in sample)


def classify_variable_value(name: str, value: Any) -> str:
    if value is None:
        return "missing"
    if name in DERIVED_VARIABLE_NAMES:
        return "derived"
    if name in TIME_SERIES_VARIABLES:
        return "time_series"
    if isinstance(value, dict):
        if _is_year_keyed_dict(value):
            return "time_series"
        return "static_dict"
    if isinstance(value, list):
        return "list"
    return "scalar"


def display_profile_for(name: str, kind: str, value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if name in _SEASONAL_FIELD_BY_VARIABLE:
        return {"type": "seasonal_lines", "field": _SEASONAL_FIELD_BY_VARIABLE[name]}
    if name in _LINE_ONLY_VARIABLES:
        return {"type": "line_only"}
    if name == "monsoon_onset_date":
        return {"type": "monsoon_offset"}
    if name == "drought_weeks":
        return {"type": "stacked_drought"}
    if name in {"crop_type_area_ha"}:
        return {"type": "stacked_cropping"}
    if name == "swb_area_ha":
        return {"type": "stacked_swb"}
    if name == "lulc_ha":
        return {"type": "stacked_lulc"}
    if name == "nrega_mws":
        return {"type": "nrega_years"}
    if name in _CD_BREAKUP_VARIABLES:
        return {"type": _CD_BREAKUP_VARIABLES[name]}
    if kind == "static_dict" and name in _CATEGORY_BAR_VARIABLES:
        return {"type": "category_bars"}
    if kind == "static_dict" and name in _CATEGORY_DICT_VARIABLES:
        return {"type": "category_dict"}
    if kind == "time_series" and isinstance(value, dict) and _is_year_keyed_dict(value):
        if value and all(isinstance(v, dict) for v in value.values()):
            if name == "drought_causality":
                return {"type": "nested_dict"}
        return {"type": "line_only"}
    return None


def _series_points(value: dict[Any, Any]) -> list[dict[str, Any]]:
    pairs: list[tuple[int, Any]] = []
    for key, raw in value.items():
        try:
            pairs.append((int(key), raw))
        except (TypeError, ValueError):
            continue
    pairs.sort(key=lambda item: item[0])
    return [{"year": year, "value": item} for year, item in pairs]


def _nested_series(value: dict[Any, Any]) -> list[dict[str, Any]]:
    """Year-keyed dict whose values are season/field sub-dicts."""
    series: list[dict[str, Any]] = []
    for year, row in sorted(value.items(), key=lambda item: str(item[0])):
        if not isinstance(row, dict):
            continue
        for key, raw in row.items():
            if isinstance(raw, (int, float, str, bool)) or raw is None:
                series.append({"year": str(year), "series": str(key), "value": raw})
    return series


def variable_value_entry(name: str, value: Any) -> dict[str, Any]:
    kind = classify_variable_value(name, value)
    profile = display_profile_for(name, kind, value)
    entry: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "formatted": format_access_value(value) if value is not None else "—",
    }
    if profile:
        entry["display_profile"] = profile
    if value is None:
        return entry
    if kind == "time_series" and isinstance(value, dict):
        if value and all(isinstance(v, dict) for v in value.values()):
            entry["nested_series"] = _nested_series(value)
        else:
            entry["series"] = _series_points(value)
        entry["raw"] = value
    elif kind in {"static_dict", "list"}:
        entry["raw"] = value
    else:
        entry["raw"] = value
    return entry


def mws_variable_values_payload(db: Database, mws_id: str) -> dict[str, Any] | None:
    mws_doc = load_mws_doc(db, mws_id)
    if not mws_doc:
        return None

    dd_vars = load_data_dictionary().get("variables") or {}
    variables: dict[str, dict[str, Any]] = {}
    for name in sorted(dd_vars.keys()):
        value = resolve_variable(mws_doc, name)
        variables[name] = variable_value_entry(name, value)

    loc = location_context(mws_doc)
    return {
        "mws_id": mws_id,
        "state": loc.get("state") or mws_doc.get("state"),
        "district": loc.get("district") or mws_doc.get("district"),
        "tehsil": loc.get("tehsil") or mws_doc.get("tehsil"),
        "variables": variables,
    }
