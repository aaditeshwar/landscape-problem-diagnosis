#!/usr/bin/env python3
"""Unit tests for retrieval diversity ranking and follow-up ordering."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.assembler import authorized_follow_up_questions  # noqa: E402
from services.retriever import _diverse_select, pathway_retrieval_ranks  # noqa: E402


def test_diverse_select_spreads_production_systems():
    scored = [
        (0.95, {"card_id": "a", "production_system": "Agriculture", "causal_pathway": "rainfed_risk"}),
        (0.94, {"card_id": "b", "production_system": "Agriculture", "causal_pathway": "groundwater_stress"}),
        (0.90, {"card_id": "c", "production_system": "NTFP_Forest_Biodiversity", "causal_pathway": "forest_degradation"}),
        (0.89, {"card_id": "d", "production_system": "Socio_Economic", "causal_pathway": "multi_sector_vulnerability"}),
        (0.88, {"card_id": "e", "production_system": "Agriculture", "causal_pathway": "irrigation_challenges"}),
    ]
    picked = _diverse_select(scored, limit=3)
    systems = {c["production_system"] for c in picked}
    pathways = {c["causal_pathway"] for c in picked}
    assert "NTFP_Forest_Biodiversity" in systems
    assert len(pathways) == 3
    assert picked[0]["retrieval_rank"] == 0
    assert pathway_retrieval_ranks(picked)["forest_degradation"] == picked[1]["retrieval_rank"] if any(
        c["causal_pathway"] == "forest_degradation" for c in picked
    ) else True


def test_follow_up_prefers_uncertain_by_rank():
    bundle = {
        "multi_sector_vulnerability": {
            "missing_variables": ["migrant_household_percent", "household_income_inr"],
            "missing_variable_questions": [
                {
                    "missing_variable": "migrant_household_percent",
                    "question_to_user": "Migration question?",
                },
                {
                    "missing_variable": "household_income_inr",
                    "question_to_user": "Income question?",
                },
            ],
            "present_variables": {},
        },
        "groundwater_stress": {
            "missing_variables": ["annual_well_depth_m"],
            "missing_variable_questions": [
                {
                    "missing_variable": "annual_well_depth_m",
                    "question_to_user": "Well depth question?",
                },
            ],
            "present_variables": {},
        },
    }
    ranks = {"multi_sector_vulnerability": 0, "groundwater_stress": 1}
    uncertain = {"multi_sector_vulnerability"}
    confirmed = {"groundwater_stress"}

    ordered = authorized_follow_up_questions(
        bundle,
        uncertain_pathway_ids=uncertain,
        confirmed_pathway_ids=confirmed,
        pathway_retrieval_ranks=ranks,
    )
    assert ordered[0] == ("migrant_household_percent", "Migration question?")

    uncertain_only_gw = {"groundwater_stress"}
    confirmed_ms = {"multi_sector_vulnerability"}
    ordered_gw = authorized_follow_up_questions(
        bundle,
        uncertain_pathway_ids=uncertain_only_gw,
        confirmed_pathway_ids=confirmed_ms,
        pathway_retrieval_ranks=ranks,
    )
    assert ordered_gw[0][0] == "annual_well_depth_m"


def test_ruled_out_pathways_excluded_from_follow_up():
    bundle = {
        "groundwater_stress": {
            "missing_variables": ["borewell_density", "groundwater_salinity"],
            "missing_variable_questions": [
                {
                    "missing_variable": "borewell_density",
                    "question_to_user": "Borewell density question?",
                },
                {
                    "missing_variable": "groundwater_salinity",
                    "question_to_user": "Salinity question?",
                },
            ],
            "present_variables": {},
        },
        "multi_sector_vulnerability": {
            "missing_variables": ["migrant_household_percent"],
            "missing_variable_questions": [
                {
                    "missing_variable": "migrant_household_percent",
                    "question_to_user": "Migration question?",
                },
            ],
            "present_variables": {},
        },
        "forest_degradation": {
            "missing_variables": ["community_forest_protection_status"],
            "missing_variable_questions": [
                {
                    "missing_variable": "community_forest_protection_status",
                    "question_to_user": "Forest protection question?",
                },
            ],
            "present_variables": {},
        },
    }
    ranks = {
        "groundwater_stress": 0,
        "multi_sector_vulnerability": 1,
        "forest_degradation": 2,
    }
    ordered = authorized_follow_up_questions(
        bundle,
        injected={"annual_well_depth_m": {"raw": "No"}},
        uncertain_pathway_ids=set(),
        confirmed_pathway_ids={"multi_sector_vulnerability"},
        ruled_out_pathway_ids={"groundwater_stress", "forest_degradation"},
        pathway_retrieval_ranks=ranks,
    )
    assert ordered[0] == ("migrant_household_percent", "Migration question?")
    assert all(var != "borewell_density" for var, _ in ordered)


def test_confirmed_follow_up_prefers_lowest_confidence():
    bundle = {
        "multi_sector_vulnerability": {
            "missing_variables": ["household_income_inr"],
            "missing_variable_questions": [
                {
                    "missing_variable": "household_income_inr",
                    "question_to_user": "Income question?",
                },
            ],
            "present_variables": {},
        },
        "small_landholding": {
            "missing_variables": ["landholding_size_distribution", "market_price_crop"],
            "missing_variable_questions": [
                {
                    "missing_variable": "landholding_size_distribution",
                    "question_to_user": "Landholding question?",
                },
                {
                    "missing_variable": "market_price_crop",
                    "question_to_user": "MSP question?",
                },
            ],
            "present_variables": {},
        },
        "irrigation_challenges": {
            "missing_variables": ["tank_siltation_status"],
            "missing_variable_questions": [
                {
                    "missing_variable": "tank_siltation_status",
                    "question_to_user": "Tank siltation question?",
                },
            ],
            "present_variables": {},
        },
    }
    ranks = {
        "multi_sector_vulnerability": 1,
        "small_landholding": 3,
        "irrigation_challenges": 4,
    }
    ordered = authorized_follow_up_questions(
        bundle,
        uncertain_pathway_ids=set(),
        confirmed_pathway_ids={
            "multi_sector_vulnerability",
            "small_landholding",
            "irrigation_challenges",
        },
        confirmed_pathway_confidence={
            "multi_sector_vulnerability": "high",
            "small_landholding": "high",
            "irrigation_challenges": "medium",
        },
        pathway_retrieval_ranks=ranks,
    )
    assert ordered[0] == ("tank_siltation_status", "Tank siltation question?")
    assert ordered[1][0] == "household_income_inr"


def test_tier_one_still_precedes_tier_two_despite_confidence_order():
    bundle = {
        "groundwater_stress": {
            "missing_variables": ["borewell_density"],
            "missing_variable_questions": [
                {
                    "missing_variable": "borewell_density",
                    "question_to_user": "Borewell question?",
                },
            ],
            "present_variables": {},
        },
        "irrigation_challenges": {
            "missing_variables": ["tank_siltation_status"],
            "missing_variable_questions": [
                {
                    "missing_variable": "tank_siltation_status",
                    "question_to_user": "Tank siltation question?",
                },
            ],
            "present_variables": {},
        },
        "multi_sector_vulnerability": {
            "missing_variables": ["household_income_inr"],
            "missing_variable_questions": [
                {
                    "missing_variable": "household_income_inr",
                    "question_to_user": "Income question?",
                },
            ],
            "present_variables": {},
        },
    }
    ranks = {"groundwater_stress": 0, "multi_sector_vulnerability": 1, "irrigation_challenges": 4}
    ordered = authorized_follow_up_questions(
        bundle,
        uncertain_pathway_ids=set(),
        confirmed_pathway_ids={"multi_sector_vulnerability", "irrigation_challenges"},
        confirmed_pathway_confidence={
            "multi_sector_vulnerability": "high",
            "irrigation_challenges": "medium",
        },
        ruled_out_pathway_ids=set(),
        pathway_retrieval_ranks=ranks,
    )
    assert ordered[0] == ("borewell_density", "Borewell question?")
    assert ordered[1] == ("tank_siltation_status", "Tank siltation question?")


def test_uncertain_without_questions_falls_through_with_tier_order():
    """When uncertain pathways have no askable vars, tier 1 precedes tier 2 (same as empty uncertain)."""
    bundle = {
        "drought": {
            "missing_variables": [],
            "missing_variable_questions": [],
            "present_variables": {"drought_weeks_severe": 2},
        },
        "irrigation_challenges": {
            "missing_variables": [],
            "missing_variable_questions": [
                {
                    "missing_variable": "annual_well_depth_m",
                    "question_to_user": "Well depth question?",
                },
            ],
            "present_variables": {},
        },
        "groundwater_stress": {
            "missing_variables": ["borewell_density"],
            "missing_variable_questions": [
                {
                    "missing_variable": "borewell_density",
                    "question_to_user": "Borewell density question?",
                },
            ],
            "present_variables": {},
        },
        "encroachment": {
            "missing_variables": ["fra_claims_filed_count"],
            "missing_variable_questions": [
                {
                    "missing_variable": "fra_claims_filed_count",
                    "question_to_user": "FRA claims question?",
                },
            ],
            "present_variables": {},
        },
        "rainfed_risk": {
            "missing_variables": ["irrigated_area_ha"],
            "missing_variable_questions": [
                {
                    "missing_variable": "irrigated_area_ha",
                    "question_to_user": "Irrigated area question?",
                },
            ],
            "present_variables": {},
        },
        "multi_sector_vulnerability": {
            "missing_variables": ["household_income_inr"],
            "missing_variable_questions": [
                {
                    "missing_variable": "household_income_inr",
                    "question_to_user": "Income question?",
                },
            ],
            "present_variables": {"migrant_household_percent": ">30%"},
        },
    }
    ranks = {
        "drought": 5,
        "irrigation_challenges": 4,
        "groundwater_stress": 0,
        "encroachment": 2,
        "rainfed_risk": 3,
        "multi_sector_vulnerability": 1,
    }
    ordered = authorized_follow_up_questions(
        bundle,
        injected={"migrant_household_percent": {"raw": ">30%"}, "annual_well_depth_m": {"raw": "yes"}},
        uncertain_pathway_ids={"drought", "irrigation_challenges"},
        confirmed_pathway_ids={"encroachment", "rainfed_risk", "multi_sector_vulnerability"},
        confirmed_pathway_confidence={
            "encroachment": "medium",
            "rainfed_risk": "medium",
            "multi_sector_vulnerability": "medium",
        },
        pathway_retrieval_ranks=ranks,
    )
    assert ordered[0] == ("borewell_density", "Borewell density question?")
    assert ordered[1] == ("fra_claims_filed_count", "FRA claims question?")
    assert ("irrigated_area_ha", "Irrigated area question?") in ordered
    assert ("household_income_inr", "Income question?") in ordered
    assert all(var != "annual_well_depth_m" for var, _ in ordered)


def main() -> int:
    tests = [
        test_diverse_select_spreads_production_systems,
        test_follow_up_prefers_uncertain_by_rank,
        test_ruled_out_pathways_excluded_from_follow_up,
        test_confirmed_follow_up_prefers_lowest_confidence,
        test_tier_one_still_precedes_tier_two_despite_confidence_order,
        test_uncertain_without_questions_falls_through_with_tier_order,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n=== {len(tests) - failed}/{len(tests)} passed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
