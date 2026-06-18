"""MCQ follow-up payloads sourced from evidence card missing_variable_questions."""

from __future__ import annotations

from typing import Any

# Explicit confirms-direction inference for MCQ choices where generic band/trend
# matching is ambiguous or wrong. None = fall back to card excerpt logic.
def _choice(variable: str, choice_id: str, label: str, normalized: dict[str, Any], confirms_result: bool | None):
    return {
        "id": choice_id,
        "label": label,
        "normalized": normalized,
        "confirms_result": confirms_result,
    }


MCQ_TEMPLATES: dict[str, dict[str, Any]] = {
    "borewell_density": {
        "response_type": "mcq",
        "choices": [
            _choice("borewell_density", "few", "Very few (fewer than 10 within 2–3 km)", {"band": "low", "present": True}, False),
            _choice("borewell_density", "moderate", "Moderate (10–50 within 2–3 km)", {"band": "moderate", "present": True}, True),
            _choice("borewell_density", "many", "More than 50 within 2–3 km", {"band": "high", "present": True}, True),
        ],
    },
    "annual_well_depth_m": {
        "response_type": "mcq",
        "choices": [
            _choice("annual_well_depth_m", "stable", "Well depth has stayed roughly the same (within ~1 m)", {"trend": "stable", "present": False}, False),
            _choice("annual_well_depth_m", "deepening", "Wells have deepened by more than 2–3 m in the last 5–10 years", {"trend": "worsening", "present": True}, True),
            _choice("annual_well_depth_m", "failed", "Springs or shallow wells have dried up permanently or for much longer", {"trend": "worsening", "present": True, "band": "high"}, True),
        ],
    },
    "migrant_household_percent": {
        "response_type": "mcq",
        "choices": [
            _choice("migrant_household_percent", "low", "Very few households migrate seasonally (roughly under 10%)", {"band": "low", "present": True}, None),
            _choice("migrant_household_percent", "moderate", "A moderate share migrate (roughly 10–30%)", {"band": "moderate", "present": True}, None),
            _choice("migrant_household_percent", "high", "Many households migrate (roughly over 30%)", {"band": "high", "present": True}, True),
        ],
    },
    "household_income_inr": {
        "response_type": "mcq",
        "choices": [
            _choice("household_income_inr", "below_50k", "Below ₹50,000 per year from farming (or total household income)", {"band": "low", "present": True}, True),
            _choice("household_income_inr", "50k_to_100k", "Between ₹50,000 and ₹1,00,000 per year", {"band": "moderate", "present": True}, None),
            _choice("household_income_inr", "above_100k", "Above ₹1,00,000 per year", {"band": "high", "present": True}, False),
        ],
    },
    "groundwater_salinity": {
        "response_type": "mcq",
        "choices": [
            _choice("groundwater_salinity", "none", "No — water quality has not changed; no saltiness or deposits", {"present": False, "trend": "stable"}, False),
            _choice("groundwater_salinity", "mild", "Some salinity or white deposits; still usable for some crops", {"present": True, "band": "moderate", "trend": "worsening"}, True),
            _choice("groundwater_salinity", "severe", "Brackish or salty water; crop damage or unsuitable for irrigation", {"present": True, "band": "high", "trend": "worsening"}, True),
        ],
    },
    "irrigated_area_ha": {
        "response_type": "mcq",
        "choices": [
            _choice("irrigated_area_ha", "low", "Less than 10% of cultivated land is irrigated", {"band": "low", "present": True, "percent_upper": 10}, True),
            _choice("irrigated_area_ha", "moderate", "Between 10% and 30% of cultivated land is irrigated", {"band": "moderate", "present": True, "percent_lower": 10, "percent_upper": 30}, None),
            _choice("irrigated_area_ha", "high", "More than 30% of cultivated land is irrigated", {"band": "high", "present": True, "percent_lower": 30}, False),
        ],
    },
    "ntfp_species_presence": {
        "response_type": "mcq",
        "choices": [
            _choice("ntfp_species_presence", "abundant", "NTFP species are still common and easy to find", {"band": "high", "present": True, "trend": "stable"}, False),
            _choice("ntfp_species_presence", "reduced", "Some species are harder to find than 5–10 years ago", {"band": "moderate", "present": True, "trend": "worsening"}, None),
            _choice("ntfp_species_presence", "rare", "Several species that used to be common are now rare or absent", {"band": "low", "present": True, "trend": "worsening"}, True),
        ],
    },
    "landholding_size_distribution": {
        "response_type": "mcq",
        "choices": [
            _choice("landholding_size_distribution", "minority", "Less than one-quarter of farming households own under 1 ha", {"band": "low", "present": True}, False),
            _choice("landholding_size_distribution", "about_half", "About half of farming households own under 1 ha", {"band": "moderate", "present": True}, True),
            _choice("landholding_size_distribution", "majority", "More than half (or two-thirds) of households are marginal (<1 ha)", {"band": "high", "present": True}, True),
        ],
    },
    "market_price_crop": {
        "response_type": "mcq",
        "choices": [
            _choice("market_price_crop", "near_msp", "Prices close to government MSP (mandi or procurement)", {"band": "low", "present": True}, False),
            _choice("market_price_crop", "below_msp", "Prices significantly below MSP (e.g. farm-gate or trader)", {"band": "moderate", "present": True, "trend": "worsening"}, True),
            _choice("market_price_crop", "unable_to_sell", "Unable to sell at all or forced to accept very low prices", {"band": "high", "present": True, "trend": "worsening"}, True),
        ],
    },
    "fra_claims_filed_count": {
        "response_type": "mcq",
        "choices": [
            _choice("fra_claims_filed_count", "none", "No FRA claims filed by community members", {"present": False}, True),
            _choice("fra_claims_filed_count", "pending", "Claims filed but mostly pending or rejected", {"band": "moderate", "present": True}, True),
            _choice("fra_claims_filed_count", "recognized", "Several claims recognised (individual or community forest rights)", {"band": "high", "present": True}, False),
        ],
    },
    "ntfp_collection_trend_qualitative": {
        "response_type": "mcq",
        "choices": [
            _choice("ntfp_collection_trend_qualitative", "little_change", "Little change — decline under 25% or stable collection", {"band": "low", "present": True, "trend": "stable", "percent_upper": 25}, False),
            _choice("ntfp_collection_trend_qualitative", "moderate_decline", "Noticeable decline of about 25–50% in collection volume", {"band": "moderate", "present": True, "trend": "worsening", "percent_lower": 25, "percent_upper": 50}, True),
            _choice("ntfp_collection_trend_qualitative", "severe_decline", "Severe decline over 50% or access largely blocked", {"band": "high", "present": True, "trend": "worsening", "percent_lower": 50}, True),
        ],
    },
    "forest_fire_frequency": {
        "response_type": "mcq",
        "choices": [
            _choice("forest_fire_frequency", "rare", "Forest fires are rare; no increase in recent years", {"band": "low", "present": False, "trend": "stable"}, False),
            _choice("forest_fire_frequency", "occasional", "Occasional fires; frequency or severity increasing", {"band": "moderate", "present": True, "trend": "worsening"}, True),
            _choice("forest_fire_frequency", "frequent", "Frequent or repeated fires in the same forest patches", {"band": "high", "present": True, "trend": "worsening"}, True),
        ],
    },
    "forest_patch_connectivity": {
        "response_type": "mcq",
        "choices": [
            _choice("forest_patch_connectivity", "connected", "Forest areas remain connected; little new fragmentation", {"present": False, "trend": "stable"}, False),
            _choice("forest_patch_connectivity", "partial", "Some patches separated by fields, roads, or cleared land", {"band": "moderate", "present": True, "trend": "worsening"}, True),
            _choice("forest_patch_connectivity", "isolated", "Forest broken into small isolated patches", {"band": "high", "present": True, "trend": "worsening"}, True),
        ],
    },
    "forest_boundary_demarcation_status": {
        "response_type": "mcq",
        "choices": [
            _choice("forest_boundary_demarcation_status", "clear", "Boundaries clearly marked; no recent disputes", {"present": False, "trend": "stable"}, False),
            _choice("forest_boundary_demarcation_status", "partial", "Some marking exists but incomplete or poorly maintained", {"band": "moderate", "present": True}, True),
            _choice("forest_boundary_demarcation_status", "absent", "No clear demarcation or active boundary disputes", {"band": "high", "present": True, "trend": "worsening"}, True),
        ],
    },
    "community_forest_governance_status": {
        "response_type": "mcq",
        "choices": [
            _choice("community_forest_governance_status", "active", "Active JFM/Van Suraksha Samiti or recognised CFR with patrols or bylaws", {"band": "high", "present": True}, False),
            _choice("community_forest_governance_status", "inactive", "Committee exists on paper but little enforcement or activity", {"band": "moderate", "present": True}, None),
            _choice("community_forest_governance_status", "none", "No functioning forest governance institution in the village", {"present": False}, True),
        ],
    },
    "tank_siltation_status": {
        "response_type": "mcq",
        "choices": [
            _choice("tank_siltation_status", "none", "Tanks and ponds not visibly silted; depth and retention similar to before", {"present": False, "trend": "stable"}, False),
            _choice("tank_siltation_status", "moderate", "Visible siltation or shallower than before; dries somewhat faster", {"band": "moderate", "present": True, "trend": "worsening"}, True),
            _choice("tank_siltation_status", "severe", "Heavily silted, much shallower, or drying out quickly after monsoon", {"band": "high", "present": True, "trend": "worsening"}, True),
        ],
    },
}


def mcq_confirms_result(variable: str | None, choice_id: str | None) -> bool | None:
    """Return explicit confirms-direction result for an MCQ choice, or None to use card logic."""
    var = str(variable or "").strip()
    cid = str(choice_id or "").strip()
    if not var or not cid:
        return None
    template = MCQ_TEMPLATES.get(var)
    if not template:
        return None
    for choice in template.get("choices") or []:
        if str(choice.get("id") or "").strip() != cid:
            continue
        if "confirms_result" not in choice:
            return None
        value = choice.get("confirms_result")
        if value is None:
            return None
        return bool(value)
    return None


def mcq_choice_template(variable: str, choice_id: str) -> dict[str, Any] | None:
    var = str(variable or "").strip()
    cid = str(choice_id or "").strip()
    template = MCQ_TEMPLATES.get(var)
    if not template:
        return None
    for choice in template.get("choices") or []:
        if str(choice.get("id") or "").strip() == cid:
            return choice
    return None


def _iter_question_entries(bundle_or_cards: dict[str, dict] | list[dict]):
    if isinstance(bundle_or_cards, list):
        for card in bundle_or_cards:
            if not isinstance(card, dict):
                continue
            for q in card.get("missing_variable_questions") or []:
                if isinstance(q, dict):
                    yield q
        return
    for data in bundle_or_cards.values():
        for q in (data or {}).get("missing_variable_questions") or []:
            if isinstance(q, dict):
                yield q


def _question_entry_for_variable(
    bundle_or_cards: dict[str, dict] | list[dict],
    variable: str,
) -> dict[str, Any] | None:
    var = str(variable or "").strip()
    if not var:
        return None
    for q in _iter_question_entries(bundle_or_cards):
        q_var = str(q.get("missing_variable") or q.get("variable") or "").strip()
        if q_var == var:
            return q
    return None


def follow_up_mcq_from_bundle(
    bundle: dict[str, dict],
    *,
    variable: str | None,
    question: str | None,
) -> dict[str, Any] | None:
    """Build UI MCQ payload when the card entry has response_type=mcq."""
    if not variable or not question:
        return None
    entry = _question_entry_for_variable(bundle, variable)
    if not entry:
        return None
    if str(entry.get("response_type") or "").lower() != "mcq":
        return None
    choices = []
    for choice in entry.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        choice_id = str(choice.get("id") or "").strip()
        label = str(choice.get("label") or "").strip()
        if not choice_id or not label:
            continue
        choices.append({"id": choice_id, "label": label})
    if not choices:
        return None
    return {
        "variable": variable,
        "question": question,
        "choices": choices,
    }


def normalized_answer_from_mcq_choice(
    bundle_or_cards: dict[str, dict] | list[dict],
    variable: str,
    choice_id: str,
) -> dict[str, Any] | None:
    """Resolve MCQ choice_id to injected-variable payload via card normalized block."""
    choice_key = str(choice_id or "").strip()
    if not choice_key:
        return None

    template_choice = mcq_choice_template(variable, choice_key)
    entry = _question_entry_for_variable(bundle_or_cards, variable)
    card_choice = None
    if entry:
        for choice in entry.get("choices") or []:
            if isinstance(choice, dict) and str(choice.get("id") or "").strip() == choice_key:
                card_choice = choice
                break

    if not template_choice and not card_choice:
        return None

    label = str((template_choice or card_choice or {}).get("label") or choice_key)
    normalized = None
    if template_choice and isinstance(template_choice.get("normalized"), dict):
        normalized = dict(template_choice["normalized"])
    elif card_choice and isinstance(card_choice.get("normalized"), dict):
        normalized = dict(card_choice["normalized"])
    if normalized is None:
        return None

    out = dict(normalized)
    out["variable"] = variable
    out["raw"] = label
    out["choice_id"] = choice_key
    return out


def attach_follow_up_mcq(response: dict[str, Any], bundle: dict[str, dict]) -> dict[str, Any]:
    out = dict(response)
    out["follow_up_mcq"] = follow_up_mcq_from_bundle(
        bundle,
        variable=out.get("follow_up_variable"),
        question=out.get("follow_up_question"),
    )
    return out
