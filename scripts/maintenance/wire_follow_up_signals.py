#!/usr/bin/env python3
"""Consolidate follow-up variable names and wire missing_variable_questions to diagnostic signals."""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT  # noqa: E402

RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
FRAMEWORK_PATH = ROOT / "metadata" / "diagnosis_framework.json"

# Canonical names for duplicate question variables across cards.
VARIABLE_RENAMES: dict[str, str] = {
    "ntfp_collection_trend_reported": "ntfp_collection_trend_qualitative",
    "ntfp_collection_trend_self_reported": "ntfp_collection_trend_qualitative",
    "ntfp_collection_volume_trend": "ntfp_collection_trend_qualitative",
    "ntfp_collection_volume_kg": "ntfp_collection_trend_qualitative",
    "ntfp_collection_quantity_kg": "ntfp_collection_trend_qualitative",
    "fire_frequency": "forest_fire_frequency",
    "jfm_cfr_status": "community_forest_governance_status",
    "community_forest_protection_status": "community_forest_governance_status",
}

NTFP_ALIASES = [
    "ntfp_collection_trend_qualitative",
    "ntfp_collection_trend_reported",
    "ntfp_collection_trend_self_reported",
    "ntfp_collection_volume_trend",
    "ntfp_collection_volume_kg",
    "ntfp_collection_quantity_kg",
]

GOVERNANCE_ALIASES = [
    "community_forest_governance_status",
    "community_forest_protection_status",
    "jfm_cfr_status",
]

FIRE_ALIASES = ["forest_fire_frequency", "fire_frequency"]

# (pathway, canonical variable) -> signal template (signal_id assigned per card).
SIGNAL_TEMPLATES: dict[tuple[str, str], dict] = {
    ("groundwater_stress", "annual_well_depth_m"): {
        "variables": ["annual_well_depth_m"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Farmers report borewell or dug-well deepening over recent years, or seasonal failure "
                "of shallow wells during rabi or zaid, indicating declining static water levels."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "Farmer-reported well deepening or seasonal well failure is a strong qualitative "
            "confirmation of groundwater stress, especially in low-storativity aquifers."
        ),
    },
    ("rainfed_risk", "irrigated_area_ha"): {
        "variables": ["irrigated_area_ha"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Irrigated share of cultivated land is negligible (under roughly 5–10%), confirming "
                "structural rainfed dependence; meaningful irrigated area (above roughly 20%) "
                "weakens the rainfed-risk diagnosis."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "User-reported irrigated area is the most direct confirmatory variable for rainfed risk "
            "when landscape proxies are ambiguous."
        ),
    },
    ("multi_sector_vulnerability", "migrant_household_percent"): {
        "variables": ["migrant_household_percent"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "More than roughly 30% of households report seasonal or permanent out-migration, "
                "confirming multi-sector economic hardship and labour shortage feedback loops."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "regional",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "Distress migration confirms insufficient local livelihoods across production systems."
        ),
    },
    ("multi_sector_vulnerability", "household_income_inr"): {
        "variables": ["household_income_inr"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Mean household income below approximately Rs 50,000/year confirms severe economic "
                "hardship; mid-band income partially confirms; higher income weakens the pathway."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "regional",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "Direct income evidence sharpens severity of multi-sector vulnerability beyond structural proxies."
        ),
    },
    ("small_landholding", "landholding_size_distribution"): {
        "variables": ["landholding_size_distribution"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "More than half of farming households own less than 1 hectare, directly confirming "
                "small-landholding-driven low income; lower marginal-holder shares weaken the pathway."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "Self-reported landholding distribution substitutes for per-capita cropland proxies when "
            "household-level evidence is available."
        ),
    },
    ("groundwater_stress", "borewell_density"): {
        "variables": ["borewell_density"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Farmers report moderate-to-high borewell/tubewell density (roughly 10–50 or more than 50 "
                "within 2–3 km) in hard rock terrain, indicating localised over-extraction not captured "
                "by block-level SOGE. Very low density or widespread borewell failure may indicate aquifer "
                "limits rather than density-driven stress."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "High local borewell density confirms extraction pressure at micro-watershed scale when paired "
            "with landscape depletion signals. Failed or unsuccessful borewells indicate hard-rock aquifer "
            "limits and may amplify stress severity without confirming high density per se."
        ),
    },
    ("groundwater_stress", "groundwater_salinity"): {
        "variables": ["groundwater_salinity"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Farmers report salty/brackish well water, white crust on soil or pipes, or water unsuitable "
                "for sensitive crops — indicating salinity from deep penetration or over-extraction."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "Reported salinity confirms groundwater stress as a quality-and-quantity problem; may also "
            "indicate a distinct salinity pathway requiring solution reassessment."
        ),
    },
    ("irrigation_challenges", "tank_siltation_status"): {
        "variables": ["tank_siltation_status"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Farmers confirm visible tank/check-dam siltation, reduced depth, or faster post-monsoon "
                "drying compared to roughly 10 years ago."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "User-confirmed siltation supports storage-loss mechanisms in sig_01/sig_02 and prioritises "
            "desilting interventions over new construction alone."
        ),
    },
    ("irrigation_challenges", "annual_well_depth_m"): {
        "variables": ["annual_well_depth_m"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Farmers report well or borewell deepening over 5–10 years, or seasonal failure of shallow "
                "wells, indicating co-occurring groundwater depletion alongside surface irrigation failure."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "moderate",
        "direction": "confirms",
        "explanation": (
            "Well deepening co-confirms groundwater_stress alongside irrigation_challenges when surface "
            "storage is inadequate; informs lift-cost assumptions for solar pump solutions."
        ),
    },
    ("small_landholding", "household_income_inr"): {
        "variables": ["household_income_inr"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Mean household or farm income below approximately Rs 50,000/year confirms severe income "
                "insufficiency on small holdings; Rs 50,000–1,00,000 partial; above weakens landholding "
                "as the primary driver."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "regional",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "Direct income evidence distinguishes volume-poverty (small area) from market or price failure "
            "(see market_price_crop amplifier)."
        ),
    },
    ("small_landholding", "market_price_crop"): {
        "variables": ["market_price_crop"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Farm-gate price consistently well below MSP (roughly 20–40% gap) for the main crop, "
                "amplifying income loss from small land area."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "moderate",
        "direction": "amplifies",
        "explanation": (
            "Market price failure amplifies small_landholding stress; near-MSP prices suggest low volume "
            "rather than exploitation is the dominant constraint."
        ),
    },
    ("encroachment", "fra_claims_filed_count"): {
        "variables": ["fra_claims_filed_count"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Many pending or rejected FRA claims with reported NTFP decline and forest conversion "
                "indicate tenure insecurity confirming encroachment vulnerability; high recognition "
                "weakens encroachment as primary driver."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "Unresolved forest rights alongside measurable conversion corroborates encroachment as a "
            "tenure and access driver of NTFP decline."
        ),
    },
    ("encroachment", "forest_boundary_demarcation_status"): {
        "variables": ["forest_boundary_demarcation_status"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Absent or disputed forest boundary demarcation (no pillars/signage, active boundary "
                "disputes) is a precondition for encroachment; clear demarcation with no disputes "
                "weakens the pathway."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "moderate",
        "direction": "confirms",
        "explanation": (
            "Boundary ambiguity enables encroachment and restricts communities' ability to defend "
            "forest access."
        ),
    },
    ("encroachment", "forest_patch_connectivity"): {
        "variables": ["forest_patch_connectivity"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Community reports forest fragmentation — patches separated by fields or roads that "
                "were contiguous 10–15 years ago — corroborating encroachment-driven access loss."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "moderate",
        "direction": "confirms",
        "explanation": (
            "Fragmentation confirms access loss beyond what area metrics alone capture and compounds "
            "NTFP collection decline."
        ),
    },
    ("encroachment", "ntfp_collection_trend_qualitative"): {
        "variables": ["ntfp_collection_trend_qualitative"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Collectors report NTFP decline attributed to shrinking forest area or blocked/restricted "
                "access (not merely lower density inside intact forest). Decline greater than 25–50% "
                "increases severity."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "Access- or area-attributed NTFP decline distinguishes encroachment from degradation or "
            "over-harvesting within intact forest."
        ),
    },
    ("forest_degradation", "forest_fire_frequency"): {
        "variables": ["forest_fire_frequency"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Frequent or intensifying forest fires (annual or every few years, worsening trend) "
                "damaging NTFP species and suppressing regeneration."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "regional",
        },
        "severity": "high",
        "direction": "confirms",
        "explanation": (
            "Fire-driven degradation is a major NTFP loss mechanism in dry deciduous and plateau forests."
        ),
    },
    ("forest_degradation", "community_forest_governance_status"): {
        "variables": ["community_forest_governance_status"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Absence of active VSS/JFM/CFR governance and forest patrols amplifies degradation risk; "
                "recognised CFR rights with enforcement weaken ongoing active degradation."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "local",
        },
        "severity": "moderate",
        "direction": "amplifies",
        "explanation": (
            "Institutional gap amplifies degradation severity; active community forest governance "
            "suggests legacy rather than ongoing degradation."
        ),
    },
    ("forest_degradation", "forest_patch_connectivity"): {
        "variables": ["forest_patch_connectivity"],
        "condition": {
            "type": "qualitative",
            "qualitative_description": (
                "Highly fragmented, isolated forest patches surrounded by agriculture increase edge "
                "effects and local species loss, amplifying degradation impacts."
            ),
            "threshold_confidence": "medium",
            "context_sensitivity": "regional",
        },
        "severity": "moderate",
        "direction": "amplifies",
        "explanation": (
            "Fragmentation amplifies degradation severity in sparse forest landscapes."
        ),
    },
}

FRAMEWORK_ADDITIONS: dict[str, list[dict]] = {
    "encroachment": [
        {
            "variable": "fra_claims_filed_count",
            "rationale": "Pending or rejected FRA claims indicate tenure insecurity amplifying encroachment impacts",
            "availability": "not_available",
        },
        {
            "variable": "forest_boundary_demarcation_status",
            "rationale": "Absent or disputed boundaries precondition encroachment and access loss",
            "availability": "not_available",
        },
        {
            "variable": "forest_patch_connectivity",
            "rationale": "Reported fragmentation corroborates encroachment-driven NTFP access loss",
            "availability": "not_available",
        },
        {
            "variable": "ntfp_collection_trend_qualitative",
            "rationale": "Community-reported NTFP decline attributed to area loss or blocked access",
            "availability": "not_available",
        },
    ],
    "forest_degradation": [
        {
            "variable": "forest_fire_frequency",
            "rationale": "Recurring or intensifying fires are a primary degradation driver for NTFP species",
            "availability": "not_available",
        },
        {
            "variable": "community_forest_governance_status",
            "rationale": "Active JFM/CFR/VSS governance reduces ongoing degradation risk",
            "availability": "not_available",
        },
        {
            "variable": "forest_patch_connectivity",
            "rationale": "Fragmentation amplifies edge effects and species loss in degraded patches",
            "availability": "not_available",
        },
    ],
    "irrigation_challenges": [
        {
            "variable": "tank_siltation_status",
            "rationale": "Visible siltation confirms storage loss driving surface irrigation failure",
            "availability": "not_available",
        },
    ],
}


def _max_signal_num(signals: list[dict]) -> int:
    best = 0
    for sig in signals:
        sid = str(sig.get("signal_id") or "")
        match = re.match(r"sig_(\d+)$", sid)
        if match:
            best = max(best, int(match.group(1)))
    return best


def _has_qualitative_user_signal(signals: list[dict], variables: list[str]) -> bool:
    var_set = set(variables)
    for sig in signals:
        sig_vars = set(sig.get("variables") or [])
        if not sig_vars.intersection(var_set):
            continue
        condition = sig.get("condition") or {}
        if condition.get("type") == "qualitative" and not condition.get("expression"):
            return True
    return False


def _dedupe_variables(variables: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in variables:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _dedupe_signal_variables(signals: list[dict]) -> None:
    for sig in signals:
        vars_list = sig.get("variables") or []
        sig["variables"] = _dedupe_variables([str(v) for v in vars_list if v])


def _rename_variable_in_signals(signals: list[dict], old: str, new: str) -> None:
    for sig in signals:
        vars_list = sig.get("variables") or []
        sig["variables"] = [new if v == old else v for v in vars_list]
        condition = sig.get("condition") or {}
        if condition.get("variables"):
            condition["variables"] = [new if v == old else v for v in condition["variables"]]


def _consolidate_questions(card: dict) -> list[str]:
    notes: list[str] = []
    questions = card.get("missing_variable_questions") or []
    if not questions:
        return notes

    renamed: list[dict] = []
    for q in questions:
        item = dict(q)
        var = item.get("missing_variable") or item.get("variable")
        if var in VARIABLE_RENAMES:
            new_var = VARIABLE_RENAMES[var]
            notes.append(f"renamed question variable {var} -> {new_var}")
            item["missing_variable"] = new_var
        renamed.append(item)

    by_var: dict[str, dict] = {}
    for q in renamed:
        var = q.get("missing_variable")
        if not var:
            continue
        if var not in by_var:
            by_var[var] = q
        else:
            notes.append(f"deduped duplicate question for {var}")

    card["missing_variable_questions"] = list(by_var.values())
    return notes


def _wire_signals(card: dict) -> list[str]:
    notes: list[str] = []
    pathway = str(card.get("causal_pathway") or "")
    questions = card.get("missing_variable_questions") or []
    question_vars = {q.get("missing_variable") for q in questions if q.get("missing_variable")}
    signals = card.setdefault("diagnostic_signals", [])

    for (tpl_pathway, canonical_var), template in SIGNAL_TEMPLATES.items():
        if tpl_pathway != pathway:
            continue
        tpl_vars = template["variables"]
        if not question_vars.intersection(set(tpl_vars)) and canonical_var not in question_vars:
            continue
        if _has_qualitative_user_signal(signals, tpl_vars):
            continue
        next_id = _max_signal_num(signals) + 1
        new_sig = deepcopy(template)
        new_sig["signal_id"] = f"sig_{next_id:02d}"
        new_sig["variables"] = _dedupe_variables(list(new_sig.get("variables") or []))
        signals.append(new_sig)
        notes.append(f"added {new_sig['signal_id']} for {canonical_var}")
    return notes


def patch_card(card: dict) -> list[str]:
    notes: list[str] = []
    signals = card.get("diagnostic_signals") or []
    for old, new in VARIABLE_RENAMES.items():
        if any(old in (sig.get("variables") or []) for sig in signals):
            _rename_variable_in_signals(signals, old, new)
            notes.append(f"renamed signal variable {old} -> {new}")
    notes.extend(_consolidate_questions(card))
    notes.extend(_wire_signals(card))
    before = json.dumps(card.get("diagnostic_signals", []), sort_keys=True)
    _dedupe_signal_variables(card.get("diagnostic_signals") or [])
    after = json.dumps(card.get("diagnostic_signals", []), sort_keys=True)
    if before != after:
        notes.append("deduped signal variable lists")
    return notes


def patch_framework(dry_run: bool) -> list[str]:
    notes: list[str] = []
    framework = json.loads(FRAMEWORK_PATH.read_text(encoding="utf-8"))
    root = framework.get("diagnosis_framework", framework).get("production_systems", {})
    ntfp = (
        root.get("NTFP_Forest_Biodiversity", {})
        .get("observed_stresses", {})
        .get("ntfp_decline", {})
        .get("causal_pathways", {})
    )
    ag = (
        root.get("Agriculture", {})
        .get("observed_stresses", {})
        .get("water_scarcity", {})
        .get("causal_pathways", {})
    )
    targets = {
        "encroachment": ntfp.get("encroachment", {}).setdefault("diagnostic_variables", []),
        "forest_degradation": ntfp.get("forest_degradation", {}).setdefault("diagnostic_variables", []),
        "irrigation_challenges": ag.get("irrigation_challenges", {}).setdefault("diagnostic_variables", []),
    }
    for pathway_id, additions in FRAMEWORK_ADDITIONS.items():
        existing = {v.get("variable") for v in targets[pathway_id] if isinstance(v, dict)}
        for item in additions:
            if item["variable"] in existing:
                continue
            targets[pathway_id].append(item)
            notes.append(f"framework: added {pathway_id}.{item['variable']}")
    if not dry_run:
        FRAMEWORK_PATH.write_text(json.dumps(framework, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    all_notes: list[str] = []
    for path in sorted(RAW_DIR.glob("*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        notes = patch_card(card)
        if notes:
            all_notes.append(f"{path.name}: {', '.join(notes)}")
            if not args.dry_run:
                path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    fw_notes = patch_framework(args.dry_run)
    all_notes.extend(fw_notes)

    for line in all_notes:
        print(line)
    print(f"\nPatched {len(all_notes)} items ({'dry-run' if args.dry_run else 'written'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
