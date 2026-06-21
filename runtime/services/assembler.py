from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from config import METADATA_DIR
from services.derived_variables import resolve_derived
from services.tehsil_refs import format_tehsil_list, normalize_tehsils, resolve_active_tehsil
from services.variable_registry import (
    canonical_name,
    extend_resolver_map,
    not_available_variables,
    resolver_key_for,
)

NOT_AVAILABLE = not_available_variables()


def _present_variables(bundle: dict[str, dict]) -> set[str]:
    present: set[str] = set()
    for data in bundle.values():
        present.update((data.get("present_variables") or {}).keys())
    return present


def _missing_variables(bundle: dict[str, dict]) -> set[str]:
    missing: set[str] = set()
    for data in bundle.values():
        missing.update(data.get("missing_variables") or [])
    return missing


def _nrega_category_total(mws: dict, category_key: str) -> int | float | None:
    total = 0
    found = False
    for year_data in (mws.get("nrega_mws") or {}).values():
        val = year_data.get(category_key)
        if val is not None:
            total += val
            found = True
    return total if found else None


def _nrega_swc_count(mws: dict) -> int | float | None:
    return _nrega_category_total(mws, "soil_and_water_conservation")


def _annual_series(mws: dict, field: str) -> dict | None:
    hydro = mws.get("hydrological_annual") or {}
    if not hydro:
        return None
    out = {str(y): row.get(field) for y, row in hydro.items() if row.get(field) is not None}
    return out or None


def _drought_series(mws: dict, field: str) -> dict | None:
    drought = mws.get("drought_kharif") or {}
    if not drought:
        return None
    out: dict[str, float] = {}
    for year, row in drought.items():
        if not isinstance(row, dict):
            continue
        if row.get(field) is not None:
            out[str(year)] = float(row[field])
        else:
            out[str(year)] = 0.0
    return out or None


def _monsoon_onset_series(mws: dict) -> dict | None:
    """Monsoon onset dates are ISO-like strings, not numeric drought metrics."""
    drought = mws.get("drought_kharif") or {}
    if not drought:
        return None
    out: dict[str, str] = {}
    for year, row in drought.items():
        if not isinstance(row, dict):
            continue
        value = row.get("monsoon_onset")
        if value is not None:
            out[str(year)] = str(value)
    return out or None


def _cropping_field_series(mws: dict, field: str) -> dict | None:
    ci = mws.get("cropping_intensity") or {}
    out: dict[str, float] = {}
    for year, row in ci.items():
        if isinstance(row, dict) and row.get(field) is not None:
            out[str(year)] = row[field]
    return out or None


def _lulc_field_series(mws: dict, field: str) -> dict | None:
    lulc = mws.get("lulc_ha") or {}
    out: dict[str, float] = {}
    for year, row in lulc.items():
        if isinstance(row, dict) and row.get(field) is not None:
            out[str(year)] = row[field]
    return out or None


_LULC_CROPLAND_COMPONENTS = (
    "single_kharif",
    "single_non_kharif",
    "double_crop",
    "triple_crop",
)


def _lulc_cropland_ha_series(mws: dict) -> dict | None:
    """Total cropped area per year from lulc_vector crop-class columns (not cropland_in_ha)."""
    lulc = mws.get("lulc_ha") or {}
    out: dict[str, float] = {}
    for year, row in lulc.items():
        if not isinstance(row, dict):
            continue
        parts = [row.get(key) for key in _LULC_CROPLAND_COMPONENTS]
        if not any(v is not None for v in parts):
            continue
        out[str(year)] = round(sum(v or 0 for v in parts), 4)
    return out or None


def _cropping_or_lulc_series(mws: dict, cropping_field: str, lulc_field: str) -> dict | None:
    return _cropping_field_series(mws, cropping_field) or _lulc_field_series(mws, lulc_field)


def _swb_field_series(mws: dict, field: str) -> dict | None:
    swb = mws.get("swb_annual") or {}
    out: dict[str, float] = {}
    for year, row in swb.items():
        if isinstance(row, dict) and row.get(field) is not None:
            out[str(year)] = row[field]
    return out or None


def _change_detection_value(mws: dict, sheet: str, field: str) -> Any:
    return ((mws.get("change_detection") or {}).get(sheet) or {}).get(field)


def _terrain_lulc_value(mws: dict, terrain_type: str, field: str) -> Any:
    return ((mws.get(f"terrain_lulc_{terrain_type}") or {}).get(field))


_CHANGE_DETECTION_RESOLVERS: dict[str, tuple[str, str]] = {
    # Degradation (2017-18 → 2024-25)
    "cd_farm_to_barren_ha": ("degradation", "farm_to_barren_ha"),
    "cd_farm_to_built_up_ha": ("degradation", "farm_to_built_up_ha"),
    "cd_farm_to_farm_ha": ("degradation", "farm_to_farm_ha"),
    "cd_farm_to_scrubland_ha": ("degradation", "farm_to_scrubland_ha"),
    "cd_total_degradation_ha": ("degradation", "total_ha"),
    # Deforestation
    "cd_forest_to_barren_ha": ("deforestation", "forest_to_barren_ha"),
    "cd_forest_to_built_up_ha": ("deforestation", "forest_to_built_up_ha"),
    "cd_forest_to_farm_ha": ("deforestation", "forest_to_farm_ha"),
    "cd_deforestation_forest_to_forest_ha": ("deforestation", "forest_to_forest_ha"),
    "cd_forest_to_scrubland_ha": ("deforestation", "forest_to_scrubland_ha"),
    "cd_total_deforestation_ha": ("deforestation", "total_ha"),
    # Urbanization
    "cd_barren_shrub_to_built_up_ha": ("urbanization", "barren_shrub_to_built_up_ha"),
    "cd_built_up_to_built_up_ha": ("urbanization", "built_up_to_built_up_ha"),
    "cd_tree_farm_to_built_up_ha": ("urbanization", "tree_farm_to_built_up_ha"),
    "cd_water_to_built_up_ha": ("urbanization", "water_to_built_up_ha"),
    "cd_urbanization_ha": ("urbanization", "total_ha"),
    "cd_total_urbanization_ha": ("urbanization", "total_ha"),
    # Afforestation
    "cd_barren_to_forest_ha": ("afforestation", "barren_to_forest_ha"),
    "cd_built_up_to_forest_ha": ("afforestation", "built_up_to_forest_ha"),
    "cd_farm_to_forest_ha": ("afforestation", "farm_to_forest_ha"),
    "cd_afforestation_forest_to_forest_ha": ("afforestation", "forest_to_forest_ha"),
    "cd_scrubland_to_forest_ha": ("afforestation", "scrubland_to_forest_ha"),
    "cd_afforestation_ha": ("afforestation", "total_ha"),
    "cd_total_afforestation_ha": ("afforestation", "total_ha"),
    # Crop intensity transitions
    "cd_single_to_single_ha": ("crop_intensity", "single_to_single_ha"),
    "cd_single_to_double_ha": ("crop_intensity", "single_to_double_ha"),
    "cd_single_to_triple_ha": ("crop_intensity", "single_to_triple_ha"),
    "cd_double_to_single_ha": ("crop_intensity", "double_to_single_ha"),
    "cd_double_to_double_ha": ("crop_intensity", "double_to_double_ha"),
    "cd_double_to_triple_ha": ("crop_intensity", "double_to_triple_ha"),
    "cd_triple_to_single_ha": ("crop_intensity", "triple_to_single_ha"),
    "cd_triple_to_double_ha": ("crop_intensity", "triple_to_double_ha"),
    "cd_triple_to_triple_ha": ("crop_intensity", "triple_to_triple_ha"),
    "cd_crop_intensity_total_change_ha": ("crop_intensity", "total_change_ha"),
}


def _change_detection_resolvers() -> dict[str, Any]:
    return {
        var: (lambda m, sheet=sheet, field=field: _change_detection_value(m, sheet, field))
        for var, (sheet, field) in _CHANGE_DETECTION_RESOLVERS.items()
    }


def _cropping_intensity_series(mws: dict) -> dict | None:
    return _cropping_field_series(mws, "cropping_intensity")


def _canal_name(mws: dict) -> str | None:
    if "canal" not in mws:
        return None
    canal = mws.get("canal") or {}
    return canal.get("canal_name") or canal.get("project_name") or ""


def _swb_count(mws: dict) -> int | None:
    if mws.get("swb_count") is not None:
        return mws["swb_count"]
    intersect = mws.get("swb_intersect")
    if isinstance(intersect, list):
        return len(intersect)
    return None


def _village_aggregate(mws: dict, field: str) -> Any:
    aggregates = mws.get("village_aggregates") or {}
    value = aggregates.get(field)
    return value if value is not None else None


def _facility_distance(mws: dict, field: str) -> Any:
    return (mws.get("facility_distances") or {}).get(field)


def _stream_order_n_percent(mws: dict) -> dict | None:
    data = mws.get("stream_order_area_percent")
    return data if data else None


_BASE_VARIABLE_RESOLVERS: dict[str, Any] = {
    "soge_dev_percent": lambda m: (m.get("soge") or {}).get("dev_percent"),
    "soge_class_name": lambda m: (m.get("soge") or {}).get("class_name"),
    "aquifer_class": lambda m: (m.get("aquifer") or {}).get("acwadam_class"),
    "aquifer_lithology_percent": lambda m: (m.get("aquifer") or {}).get("lithology_percent"),
    "acwadam_class_percent": lambda m: (m.get("aquifer") or {}).get("acwadam_class_percent"),
    "annual_delta_g_mm": lambda m: _annual_series(m, "delta_g_mm"),
    "delta_g_mm": lambda m: _annual_series(m, "delta_g_mm"),
    "annual_precipitation_mm": lambda m: _annual_series(m, "precipitation_mm"),
    "precipitation_mm": lambda m: _annual_series(m, "precipitation_mm"),
    "annual_et_mm": lambda m: _annual_series(m, "et_mm"),
    "et_mm": lambda m: _annual_series(m, "et_mm"),
    "annual_runoff_mm": lambda m: _annual_series(m, "runoff_mm"),
    "runoff_mm": lambda m: _annual_series(m, "runoff_mm"),
    "seasonal_precipitation_mm": lambda m: m.get("hydrological_seasonal"),
    "drought_weeks_severe": lambda m: _drought_series(m, "severe_weeks"),
    "drought_weeks_moderate": lambda m: _drought_series(m, "moderate_weeks"),
    "dry_spell_weeks": lambda m: _drought_series(m, "dry_spell_weeks"),
    "monsoon_onset_date": _monsoon_onset_series,
    "kharif_cropped_area_percent": lambda m: _drought_series(m, "kharif_cropped_percent"),
    "drought_causality_json": lambda m: m.get("drought_causality"),
    "drought_causality": lambda m: m.get("drought_causality"),
    "nrega_swc_count": _nrega_swc_count,
    "nrega_irrigation_count": lambda m: _nrega_category_total(m, "irrigation_on_farms"),
    "nrega_land_restoration_count": lambda m: _nrega_category_total(m, "land_restoration"),
    "nrega_plantation_count": lambda m: _nrega_category_total(m, "plantations"),
    "nrega_community_assets_count": lambda m: _nrega_category_total(m, "community_assets"),
    "cropping_intensity": _cropping_intensity_series,
    "lulc_single_kharif_ha": lambda m: _cropping_or_lulc_series(m, "single_kharif_ha", "single_kharif"),
    "lulc_double_crop_ha": lambda m: _cropping_or_lulc_series(m, "double_crop_ha", "double_crop"),
    "lulc_cropland_ha": _lulc_cropland_ha_series,
    "lulc_shrub_scrub_ha": lambda m: _lulc_field_series(m, "shrub_scrub"),
    "lulc_barrenland_ha": lambda m: _lulc_field_series(m, "barrenland"),
    "lulc_tree_forest_ha": lambda m: _lulc_field_series(m, "tree_forest"),
    "lulc_krz_water_ha": lambda m: _lulc_field_series(m, "krz_water"),
    "swb_total_area_ha": lambda m: _swb_field_series(m, "total_ha"),
    "swb_kharif_area_ha": lambda m: _swb_field_series(m, "kharif_ha"),
    "swb_rabi_area_ha": lambda m: _swb_field_series(m, "rabi_ha"),
    "swb_zaid_area_ha": lambda m: _swb_field_series(m, "zaid_ha"),
    "swb_count": _swb_count,
    "canal_name": _canal_name,
    "river_name": lambda m: m.get("river_name"),
    "sub_basin_code": lambda m: m.get("sub_basin_code"),
    "terrain_lulc_slope": lambda m: m.get("terrain_lulc_slope"),
    "terrain_lulc_plain": lambda m: m.get("terrain_lulc_plain"),
    "terrain_lulc_slope_forest_percent": lambda m: _terrain_lulc_value(m, "slope", "forest_percent"),
    "terrain_lulc_slope_barren_percent": lambda m: _terrain_lulc_value(m, "slope", "barren_percent"),
    "terrain_lulc_slope_shrub_scrub_percent": lambda m: _terrain_lulc_value(m, "slope", "shrub_scrub_percent"),
    "terrain_lulc_plain_forest_percent": lambda m: _terrain_lulc_value(m, "plain", "forest_percent"),
    "terrain_lulc_plain_barren_percent": lambda m: _terrain_lulc_value(m, "plain", "barren_percent"),
    "terrain_lulc_plain_shrub_scrub_percent": lambda m: _terrain_lulc_value(m, "plain", "shrub_scrub_percent"),
    "kharif_drought_total_weeks": lambda m: _drought_series(m, "total_weeks"),
    "kharif_cropped_sqkm": lambda m: _drought_series(m, "kharif_cropped_sqkm"),
    "kharif_cropped_area_ha": lambda m: _drought_series(m, "kharif_cropped_ha"),
    "single_kharif_area_ha": lambda m: _cropping_field_series(m, "single_kharif_ha"),
    "single_non_kharif_area_ha": lambda m: _cropping_field_series(m, "single_non_kharif_ha"),
    "double_crop_area_ha": lambda m: _cropping_field_series(m, "double_crop_ha"),
    "triple_crop_area_ha": lambda m: _cropping_field_series(m, "triple_crop_ha"),
    **_change_detection_resolvers(),
    "stream_order_N_area_percent": _stream_order_n_percent,
    "terrain_cluster_id": lambda m: (m.get("terrain") or {}).get("cluster_id"),
    "slopy_area_percent": lambda m: (m.get("terrain") or {}).get("slopy_percent"),
    "organization_domains": lambda m: m.get("organisation_domains") or m.get("organization_domains"),
    "mean_annual_precipitation_mm": lambda m: resolve_derived(m, "mean_annual_precipitation_mm"),
    "trend_annual_precipitation_mm": lambda m: resolve_derived(m, "trend_annual_precipitation_mm"),
    "mean_annual_et_mm": lambda m: resolve_derived(m, "mean_annual_et_mm"),
    "trend_annual_et_mm": lambda m: resolve_derived(m, "trend_annual_et_mm"),
    "mean_annual_runoff_mm": lambda m: resolve_derived(m, "mean_annual_runoff_mm"),
    "trend_annual_runoff_mm": lambda m: resolve_derived(m, "trend_annual_runoff_mm"),
    "mean_annual_delta_g_mm": lambda m: resolve_derived(m, "mean_annual_delta_g_mm"),
    "trend_annual_delta_g_mm": lambda m: resolve_derived(m, "trend_annual_delta_g_mm"),
    "mean_cropping_intensity": lambda m: resolve_derived(m, "mean_cropping_intensity"),
    "trend_cropping_intensity": lambda m: resolve_derived(m, "trend_cropping_intensity"),
    "mean_kharif_cropped_area_ha": lambda m: resolve_derived(m, "mean_kharif_cropped_area_ha"),
    "trend_kharif_cropped_area_ha": lambda m: resolve_derived(m, "trend_kharif_cropped_area_ha"),
    "mean_double_crop_area_ha": lambda m: resolve_derived(m, "mean_double_crop_area_ha"),
    "trend_double_crop_area_ha": lambda m: resolve_derived(m, "trend_double_crop_area_ha"),
    "drought_moderate_return_period": lambda m: resolve_derived(m, "drought_moderate_return_period"),
    "drought_severe_return_period": lambda m: resolve_derived(m, "drought_severe_return_period"),
    "mean_swb_total_area_ha": lambda m: resolve_derived(m, "mean_swb_total_area_ha"),
    "trend_swb_total_area_ha": lambda m: resolve_derived(m, "trend_swb_total_area_ha"),
    "mean_swb_rabi_kharif_ratio": lambda m: resolve_derived(m, "mean_swb_rabi_kharif_ratio"),
    "trend_swb_rabi_kharif_ratio": lambda m: resolve_derived(m, "trend_swb_rabi_kharif_ratio"),
    "tree_cover_percent_mws": lambda m: resolve_derived(m, "tree_cover_percent_mws"),
    "drought_mild_spi_score_latest": lambda m: resolve_derived(m, "drought_mild_spi_score_latest"),
    "drought_mild_mai_score_latest": lambda m: resolve_derived(m, "drought_mild_mai_score_latest"),
    "drought_mild_vci_score_latest": lambda m: resolve_derived(m, "drought_mild_vci_score_latest"),
    "drought_severe_moderate_spi_score_latest": lambda m: resolve_derived(m, "drought_severe_moderate_spi_score_latest"),
    "drought_severe_moderate_mai_score_latest": lambda m: resolve_derived(m, "drought_severe_moderate_mai_score_latest"),
    "drought_severe_moderate_vci_score_latest": lambda m: resolve_derived(m, "drought_severe_moderate_vci_score_latest"),
    "drought_severe_moderate_path_score_latest": lambda m: resolve_derived(m, "drought_severe_moderate_path_score_latest"),
    "village_sc_percent": lambda m: _village_aggregate(m, "village_sc_percent"),
    "village_st_percent": lambda m: _village_aggregate(m, "village_st_percent"),
    "village_literacy_rate": lambda m: _village_aggregate(m, "village_literacy_rate"),
    "village_total_population": lambda m: _village_aggregate(m, "village_total_population"),
    "dist_apmc_km": lambda m: _facility_distance(m, "dist_apmc_km"),
    "dist_bank_km": lambda m: _facility_distance(m, "dist_bank_km"),
    "dist_dairy_km": lambda m: _facility_distance(m, "dist_dairy_km"),
    "dist_cooperative_km": lambda m: _facility_distance(m, "dist_cooperative_km"),
    "dist_agri_market_km": lambda m: _facility_distance(m, "dist_markets_trading_km"),
    "dist_markets_trading_km": lambda m: _facility_distance(m, "dist_markets_trading_km"),
    "dist_cold_storage_km": lambda m: _facility_distance(m, "dist_storage_warehousing_km"),
    "dist_storage_warehousing_km": lambda m: _facility_distance(m, "dist_storage_warehousing_km"),
    "dist_agri_processing_km": lambda m: _facility_distance(m, "dist_agri_processing_km"),
    "dist_phc_km": lambda m: _facility_distance(m, "dist_phc_km"),
    "dist_chc_km": lambda m: _facility_distance(m, "dist_chc_km"),
    "dist_sub_centre_km": lambda m: _facility_distance(m, "dist_sub_centre_km"),
    "dist_district_hospital_km": lambda m: _facility_distance(m, "dist_district_hospital_km"),
    "dist_school_primary_km": lambda m: _facility_distance(m, "dist_school_primary_km"),
    "dist_school_upper_primary_km": lambda m: _facility_distance(m, "dist_school_upper_primary_km"),
    "dist_school_secondary_km": lambda m: _facility_distance(m, "dist_school_secondary_km"),
    "dist_school_higher_secondary_km": lambda m: _facility_distance(m, "dist_school_higher_secondary_km"),
    "dist_college_km": lambda m: _facility_distance(m, "dist_college_km"),
    "dist_university_km": lambda m: _facility_distance(m, "dist_university_km"),
    "dist_csc_km": lambda m: _facility_distance(m, "dist_csc_km"),
    "dist_pds_km": lambda m: _facility_distance(m, "dist_pds_km"),
    "dist_agri_support_km": lambda m: _facility_distance(m, "dist_agri_support_km"),
}

VARIABLE_RESOLVERS = extend_resolver_map(_BASE_VARIABLE_RESOLVERS)


@lru_cache
def load_framework() -> dict:
    path = METADATA_DIR / "diagnosis_framework.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def find_pathway(pathway_id: str) -> tuple[dict, str, str] | None:
    root = load_framework()["diagnosis_framework"]["production_systems"]
    for production, pdata in root.items():
        for stress, sdata in pdata.get("observed_stresses", {}).items():
            pathways = sdata.get("causal_pathways", {})
            if pathway_id in pathways:
                return pathways[pathway_id], production, stress
    return None


def pathway_diagnostic_variables(pathway_id: str) -> set[str]:
    found = find_pathway(pathway_id)
    if not found:
        return set()
    pathway_cfg, _, _ = found
    return {
        str(var_def.get("variable"))
        for var_def in pathway_cfg.get("diagnostic_variables", [])
        if var_def.get("variable")
    }


def pathway_uses_variable(pathway_id: str, variable: str) -> bool:
    if not variable:
        return False
    return variable in pathway_diagnostic_variables(pathway_id)


def _assign_present_variable(present: dict[str, Any], name: str, value: Any) -> None:
    present[name] = value
    canonical = canonical_name(name)
    if canonical != name and canonical not in present:
        present[canonical] = value


def _resolved_bundle_value(name: str, value: Any) -> Any | object:
    """Map resolver None to present-bucket defaults for list and presence-categorical vars."""
    from services.variable_registry import list_type_variables, presence_categorical_variables

    if value is not None:
        return value
    if name in list_type_variables():
        return []
    if name in presence_categorical_variables():
        return None
    return _UNRESOLVED_VARIABLE


_UNRESOLVED_VARIABLE = object()


def resolve_variable(mws_doc: dict, variable: str, injected: dict | None = None) -> Any:
    if injected and variable in injected:
        return injected[variable]
    lookup = resolver_key_for(variable)
    if lookup in NOT_AVAILABLE:
        return None
    derived = resolve_derived(mws_doc, lookup)
    if derived is not None:
        return derived
    resolver = VARIABLE_RESOLVERS.get(lookup)
    if resolver is None:
        return None
    return resolver(mws_doc)


CONFIDENCE_SORT_ORDER = {"low": 0, "medium": 1, "high": 2}


def _confidence_sort_key(confidence: str | None) -> int:
    return CONFIDENCE_SORT_ORDER.get(str(confidence or "medium").lower(), 1)


def authorized_follow_up_questions(
    bundle: dict[str, dict],
    injected: dict | None = None,
    *,
    uncertain_pathway_ids: set[str] | None = None,
    confirmed_pathway_ids: set[str] | None = None,
    confirmed_pathway_confidence: dict[str, str] | None = None,
    ruled_out_pathway_ids: set[str] | None = None,
    pathway_retrieval_ranks: dict[str, int] | None = None,
) -> list[tuple[str, str]]:
    """Return (variable, question) pairs allowed for user follow-up.

    A question is authorized only when the variable is still missing for this MWS
    (not in present_variables or injected) and the evidence card supplies the question text.
    Results are ordered: uncertain pathways first (tier 0), then bundle pathways
    that are neither uncertain nor confirmed (tier 1, high-recall), then confirmed
    pathways (tier 2). Within tier 2 only, questions are ordered by lowest
    confidence first (low, medium, high), then retrieval rank.
    When any uncertain pathway has eligible questions, only tier 0 is returned.
    When tier 0 has no eligible questions (whether or not uncertain pathways remain
    on the diagnosis), tier 1 and tier 2 are returned in that order.
    Pathways previously ruled out via user_provided confirms+FALSE are never asked again.
    """
    injected = injected or {}
    present = _present_variables(bundle)
    uncertain = uncertain_pathway_ids or set()
    confirmed = confirmed_pathway_ids or set()
    confirmed_confidence = confirmed_pathway_confidence or {}
    ruled_out = ruled_out_pathway_ids or set()
    ranks = pathway_retrieval_ranks or {}

    candidates: list[tuple[int, int, int, str, int, str, str]] = []
    seen_vars: set[str] = set()

    for pathway_id, data in bundle.items():
        if pathway_id in ruled_out:
            continue
        missing = set(data.get("missing_variables") or [])
        for q_idx, q in enumerate(data.get("missing_variable_questions") or []):
            var = q.get("missing_variable") or q.get("variable")
            question = (q.get("question_to_user") or q.get("question") or "").strip()
            if not var or not question or var in injected or var in present or var in seen_vars:
                continue
            if var not in missing:
                continue
            seen_vars.add(str(var))
            tier = 0 if pathway_id in uncertain else (2 if pathway_id in confirmed else 1)
            rank = ranks.get(pathway_id, 999)
            confidence_sort = (
                _confidence_sort_key(confirmed_confidence.get(pathway_id))
                if pathway_id in confirmed
                else 999
            )
            candidates.append((tier, confidence_sort, rank, pathway_id, q_idx, str(var), question))

    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))

    uncertain_candidates = [item for item in candidates if item[0] == 0]
    if uncertain_candidates:
        candidates = uncertain_candidates

    return [(var, question) for _, _, _, _, _, var, question in candidates]


def _resolve_signal_expression_variables(
    mws_doc: dict,
    card: dict,
    present: dict[str, Any],
    injected: dict | None,
) -> dict[str, Any]:
    """Resolve derived/list variables referenced in signal expressions but absent from present_variables."""
    from services.signal_evaluator import expression_load_names

    out = dict(present)
    for name in sorted(expression_load_names(card)):
        if name in out:
            continue
        slot = _resolved_bundle_value(name, resolve_variable(mws_doc, name, injected))
        if slot is _UNRESOLVED_VARIABLE:
            continue
        _assign_present_variable(out, name, slot)
    return out


def assemble_variable_bundle(
    mws_doc: dict,
    retrieved_cards: list[dict],
    injected: dict | None = None,
) -> dict[str, dict]:
    bundle: dict[str, dict] = {}

    for card in retrieved_cards:
        pathway_id = card.get("causal_pathway")
        if not pathway_id:
            continue
        found = find_pathway(pathway_id)
        if not found:
            continue
        pathway_cfg, _production, _stress = found

        present: dict[str, Any] = {}
        missing: list[str] = []
        for var_def in pathway_cfg.get("diagnostic_variables", []):
            name = var_def["variable"]
            if var_def.get("availability") == "not_available" and not (injected and name in injected):
                missing.append(name)
                continue
            value = resolve_variable(mws_doc, name, injected)
            slot = _resolved_bundle_value(name, value)
            if slot is _UNRESOLVED_VARIABLE:
                missing.append(name)
            else:
                _assign_present_variable(present, name, slot)

        card_questions = {
            q["missing_variable"]: q
            for q in card.get("missing_variable_questions", [])
            if q.get("missing_variable")
        }
        missing_questions = [card_questions[v] for v in missing if v in card_questions]

        present = _resolve_signal_expression_variables(mws_doc, card, present, injected)
        missing = [name for name in missing if name not in present]

        card_question_vars = set(card_questions)
        missing_signal_only = sorted(name for name in missing if name not in card_question_vars)

        bundle[pathway_id] = {
            "pathway_id": pathway_id,
            "card_id": card.get("card_id"),
            "production_system": card.get("production_system"),
            "observed_stress": card.get("observed_stress"),
            "context": card.get("context") or {},
            "aer_tags": card.get("aer_tags") or [],
            "description": pathway_cfg.get("description"),
            "solutions": pathway_cfg.get("solutions", []),
            "present_variables": present,
            "missing_variables": missing,
            "missing_signal_only_variables": missing_signal_only,
            "missing_variable_questions": missing_questions,
            "evidence_card": {
                "card_id": card.get("card_id"),
                "aer_tags": card.get("aer_tags", []),
                "overall_reasoning_note": card.get("overall_reasoning_note"),
                "diagnostic_signals": card.get("diagnostic_signals", []),
                "missing_variable_questions": card.get("missing_variable_questions", []),
                "confounders": card.get("confounders", []),
                "citations": card.get("citations", []),
            },
        }
    return bundle


def location_context(mws_doc: dict, tehsil_ref: dict | None = None) -> dict[str, Any]:
    terrain = mws_doc.get("terrain") or {}
    aquifer = mws_doc.get("aquifer") or {}
    villages = mws_doc.get("intersect_village_names") or []
    village_names = [v.get("name") for v in villages if v.get("name")]
    active = resolve_active_tehsil(mws_doc, tehsil_ref)
    tehsils = normalize_tehsils(mws_doc)
    return {
        "uid": mws_doc.get("uid"),
        "state": active["state"] if active else mws_doc.get("state"),
        "district": active["district"] if active else mws_doc.get("district"),
        "tehsil": active["tehsil"] if active else mws_doc.get("tehsil"),
        "tehsils": tehsils,
        "tehsil_label": format_tehsil_list(mws_doc, active),
        "area_ha": mws_doc.get("area_ha"),
        "nbss_lup_aer_code": mws_doc.get("nbss_lup_aer_code"),
        "nbss_lup_aer_name": mws_doc.get("nbss_lup_aer_name"),
        "aquifer_class": aquifer.get("acwadam_class"),
        "aquifer_raw": aquifer.get("raw_class"),
        "terrain_cluster": terrain.get("cluster_id"),
        "terrain_description": terrain.get("description"),
        "village_names": village_names,
        "villages": villages,
    }
