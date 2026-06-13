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


def main() -> int:
    tests = [test_diverse_select_spreads_production_systems, test_follow_up_prefers_uncertain_by_rank]
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
