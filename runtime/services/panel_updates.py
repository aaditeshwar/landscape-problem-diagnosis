"""Map confirmed diagnosis pathways to info-panel chart triggers from reference_standards.json."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from config import METADATA_DIR

PANEL_UPDATE_LABELS: dict[str, str] = {
    "cropping_intensity + annual_delta_g_mm dual_axis": "Cropping intensity vs groundwater recharge (ΔG)",
    "annual_well_depth_m trend": "Well depth trend",
    "annual_precipitation_mm + annual_delta_g_mm dual_axis": "Rainfall vs groundwater recharge (ΔG)",
    "drought_weeks stacked_bar": "Kharif drought-week breakdown",
    "annual_et_mm + annual_runoff_mm + annual_precipitation_mm stacked_area": "Water balance (ET, runoff, precipitation)",
    "lulc_stacked_area": "Land-use class trends",
    "cd_total_degradation_ha sparkline": "Cumulative cropping-area degradation",
    "nrega_land_restoration_count bar": "NREGA land-restoration works",
    "lulc_tree_forest_ha trend": "Tree/forest cover trend",
    "cd_total_deforestation_ha + cd_total_afforestation_ha paired_bar": "Deforestation vs afforestation",
    "drought_weeks_* stacked_bar": "Kharif drought-week breakdown",
    "dry_spell_weeks bar": "Dry-spell weeks",
    "monsoon_onset_date scatter": "Monsoon onset dates",
    "cropping_intensity trend": "Cropping intensity trend",
    "dist_*_km horizontal_bars": "Nearest facility distances",
    "nrega_*_count stacked_bar_cumulative": "MGNREGA works by category",
}

PANEL_UPDATE_RATIONALES: dict[str, str] = {
    "cropping_intensity + annual_delta_g_mm dual_axis": (
        "compare whether higher cropping intensity tracks with falling groundwater recharge"
    ),
    "annual_well_depth_m trend": "see if wells are deepening over time as a sign of falling water tables",
    "annual_precipitation_mm + annual_delta_g_mm dual_axis": (
        "check whether groundwater balance follows rainfall or diverges because of extraction"
    ),
    "drought_weeks stacked_bar": "review how often mild, moderate, and severe drought weeks occur during kharif",
    "annual_et_mm + annual_runoff_mm + annual_precipitation_mm stacked_area": (
        "inspect the annual water balance and how much precipitation is lost to ET and runoff"
    ),
    "lulc_stacked_area": "see how cropland, forest, scrub, and barren land have shifted over time",
    "cd_total_degradation_ha sparkline": "quantify cumulative loss of productive cropland to degradation",
    "nrega_land_restoration_count bar": (
        "check whether MGNREGA land-restoration investment matches the degradation observed"
    ),
    "lulc_tree_forest_ha trend": "track whether forest cover is stable, recovering, or declining",
    "cd_total_deforestation_ha + cd_total_afforestation_ha paired_bar": (
        "compare forest loss against new tree cover to judge net forest change"
    ),
    "drought_weeks_* stacked_bar": "review drought severity across recent kharif seasons",
    "dry_spell_weeks bar": "identify years with prolonged dry spells during the cropping season",
    "monsoon_onset_date scatter": "see whether monsoon timing has shifted",
    "cropping_intensity trend": "assess whether farmers are intensifying or reducing harvested area",
    "dist_*_km horizontal_bars": "judge how far households must travel for markets, banks, and services",
    "nrega_*_count stacked_bar_cumulative": "see which MGNREGA work types dominate local employment support",
}

PATHWAY_LABELS: dict[str, str] = {
    "groundwater_stress": "groundwater stress",
    "rainfed_risk": "rainfed risk",
    "irrigation_challenges": "irrigation challenges",
    "drought": "drought",
    "soil_degradation": "soil degradation",
    "forest_degradation": "forest degradation",
    "encroachment": "forest encroachment",
    "multi_sector_vulnerability": "multi-sector economic vulnerability",
    "small_landholding": "small landholding pressure",
    "deforestation": "deforestation",
}


@lru_cache
def load_panel_triggers() -> dict[str, list[str]]:
    path = METADATA_DIR / "reference_standards.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    block = (
        data.get("visualization_spec", {})
        .get("query_triggered_panel_updates", {})
        .get("triggers", {})
    )
    return {str(k): [str(v) for v in vals] for k, vals in block.items()}


def _pathway_suffix(pathway_id: str) -> str:
    return pathway_id.split("__")[-1] if "__" in pathway_id else pathway_id


def _humanize_pathway(pathway_id: str) -> str:
    suffix = _pathway_suffix(pathway_id)
    return PATHWAY_LABELS.get(suffix, suffix.replace("_", " "))


def _confirmed_pathway_ids(confirmed_pathways: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for entry in confirmed_pathways:
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("pathway_id") or "").strip()
        if pid:
            ids.append(pid)
    return ids


def _match_trigger_key(pathway_id: str, triggers: dict[str, list[str]]) -> str | None:
    if pathway_id in triggers:
        return pathway_id
    suffix = _pathway_suffix(pathway_id)
    if suffix in triggers:
        return suffix
    for key in triggers:
        if pathway_id == key or pathway_id.endswith(f"__{key}") or key in pathway_id:
            return key
    return None


def _match_composite_triggers(confirmed_ids: set[str], triggers: dict[str, list[str]]) -> list[str]:
    matched: list[str] = []
    confirmed_suffixes = {_pathway_suffix(pid) for pid in confirmed_ids} | confirmed_ids

    for key in triggers:
        if " + " not in key:
            continue
        parts = [part.strip() for part in key.split("+")]
        if parts and all(part in confirmed_suffixes or part in confirmed_ids for part in parts):
            matched.append(key)
    return matched


def panel_updates_for_confirmed(confirmed_pathways: list[dict[str, Any]]) -> list[str]:
    """Return deduplicated panel update keys for confirmed pathways."""
    triggers = load_panel_triggers()
    pathway_ids = _confirmed_pathway_ids(confirmed_pathways)
    if not pathway_ids:
        return []

    confirmed_set = set(pathway_ids)
    trigger_keys: list[str] = []

    for pid in pathway_ids:
        key = _match_trigger_key(pid, triggers)
        if key and key not in trigger_keys:
            trigger_keys.append(key)

    for key in _match_composite_triggers(confirmed_set, triggers):
        if key not in trigger_keys:
            trigger_keys.append(key)

    seen: set[str] = set()
    updates: list[str] = []
    for key in trigger_keys:
        for update in triggers.get(key, []):
            if update not in seen:
                seen.add(update)
                updates.append(update)
    return updates


def panel_update_action_labels(updates: list[str]) -> list[str]:
    return [
        PANEL_UPDATE_LABELS.get(key, key.replace("_", " "))
        for key in updates
    ]


def _looks_like_action_list(text: str) -> bool:
    lowered = text.lower()
    return lowered.count("highlighted") >= 2 or (
        lowered.startswith("highlighted ") and "info panel" in lowered
    )


def build_panel_update_explanation(
    confirmed_pathways: list[dict[str, Any]],
    updates: list[str],
    *,
    follow_up_context: str | None = None,
) -> str | None:
    """Fallback narrative when the LLM does not supply panel_update_explanation."""
    if not updates:
        return None

    pathway_names = []
    seen_names: set[str] = set()
    for entry in confirmed_pathways:
        if not isinstance(entry, dict):
            continue
        name = _humanize_pathway(str(entry.get("pathway_id") or ""))
        if name and name not in seen_names:
            seen_names.add(name)
            pathway_names.append(name)

    if len(pathway_names) == 1:
        pathway_phrase = f"the confirmed {pathway_names[0]} pathway"
    elif pathway_names:
        pathway_phrase = f"the confirmed pathways ({', '.join(pathway_names)})"
    else:
        pathway_phrase = "the updated diagnosis"

    rationales = [
        PANEL_UPDATE_RATIONALES.get(key, f"review {PANEL_UPDATE_LABELS.get(key, key.replace('_', ' ')).lower()}")
        for key in updates
    ]
    chart_phrase = "; ".join(rationales[:-1]) + ("; and " + rationales[-1] if len(rationales) > 1 else rationales[0])

    explanation = (
        f"Because {pathway_phrase} is supported by the available MWS data, "
        f"the info panel highlights charts that help you {chart_phrase}."
    )

    if follow_up_context:
        snippet = re.sub(r"\s+", " ", follow_up_context.strip())
        if len(snippet) > 160:
            snippet = snippet[:157] + "…"
        explanation += f" Your latest note ({snippet}) was folded into this reassessment."

    return explanation


def format_panel_update_explanation(updates: list[str]) -> str | None:
    """Legacy helper: short action list (used by tests and frontend fallback)."""
    if not updates:
        return None
    return "; ".join(panel_update_action_labels(updates))


def apply_panel_updates_from_standards(
    response: dict[str, Any],
    *,
    follow_up_context: str | None = None,
) -> dict[str, Any]:
    """Replace LLM panel_updates with reference_standards triggers for confirmed pathways."""
    out = dict(response)
    updates = panel_updates_for_confirmed(out.get("confirmed_pathways") or [])
    out["panel_updates"] = updates

    llm_explanation = str(out.get("panel_update_explanation") or "").strip()
    if llm_explanation.lower() in {"", "null", "none"}:
        llm_explanation = ""

    if llm_explanation and not _looks_like_action_list(llm_explanation):
        out["panel_update_explanation"] = llm_explanation
    elif updates:
        out["panel_update_explanation"] = build_panel_update_explanation(
            out.get("confirmed_pathways") or [],
            updates,
            follow_up_context=follow_up_context,
        )
    else:
        out["panel_update_explanation"] = None

    return out
