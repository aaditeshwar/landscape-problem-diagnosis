#!/usr/bin/env python3
"""Unit tests for run_server_diagnosis (no LLM, no Mongo)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.reasoner import run_server_diagnosis  # noqa: E402

SAMPLE_BUNDLE = {
    "groundwater_stress": {
        "description": "Declining groundwater availability.",
        "solutions": ["Community pond repair", "Check dam construction"],
        "production_system": "agriculture",
        "observed_stress": "water_scarcity",
        "card_id": "agriculture__water_scarcity__groundwater_stress__013",
        "present_variables": {
            "soge_dev_percent": 56.86,
            "trend_annual_delta_g_mm": -15.06,
        },
        "missing_variables": ["annual_well_depth_m"],
        "missing_variable_questions": [
            {
                "missing_variable": "annual_well_depth_m",
                "question_to_user": "How deep are wells?",
            }
        ],
        "evidence_card": {
            "overall_reasoning_note": "Confirm with at least two primary signals.",
            "diagnostic_signals": [
                {
                    "signal_id": "sig_01",
                    "direction": "confirms",
                    "condition": {"expression": "soge_dev_percent > 50"},
                    "explanation": "Elevated SOGE indicates stress.",
                },
                {
                    "signal_id": "sig_02",
                    "direction": "confirms",
                    "condition": {"expression": "trend_annual_delta_g_mm < 0"},
                    "explanation": "Negative recharge trend.",
                },
            ],
        },
    }
}

SAMPLE_LOCATION = {
    "uid": "4_91594",
    "tehsil": "Test",
    "district": "Test",
    "state": "Test",
    "village_names": ["Village A"],
}


def test_run_server_diagnosis_returns_solutions_and_summary():
    run = run_server_diagnosis(
        location=SAMPLE_LOCATION,
        problem_description="",
        bundle=SAMPLE_BUNDLE,
    )
    assert run.model == "server"
    assert run.llm_ms == 0.0
    response = run.response
    assert isinstance(response.get("panel_update_explanation"), str)
    assert response["panel_update_explanation"]
    assert len(response.get("confirmed_pathways") or []) >= 1
    assert response.get("solutions")
    assert "Community pond repair" in response["solutions"]


def main() -> int:
    test_run_server_diagnosis_returns_solutions_and_summary()
    print("All server solutions tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
