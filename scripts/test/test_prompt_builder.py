#!/usr/bin/env python3
"""Unit tests for diagnosis prompt profiles (no LLM required)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.reasoner import (  # noqa: E402
    _build_prompt,
    _format_bundle,
    _null_if_placeholder,
    _split_present_variables,
)


SAMPLE_BUNDLE = {
    "groundwater_stress": {
        "description": "Declining groundwater availability.",
        "solutions": ["Community pond repair", "Check dam construction"],
        "present_variables": {
            "soge_dev_percent": 56.86,
            "trend_annual_delta_g_mm": -15.06,
            "annual_delta_g_mm": {"2023": -4.16},
        },
        "missing_variables": ["annual_well_depth_m"],
        "evidence_card": {
            "overall_reasoning_note": "Confirm with at least two primary signals.",
            "diagnostic_signals": [
                {
                    "signal_id": "sig_01",
                    "direction": "confirms",
                    "condition": {"expression": "soge_dev_percent > 70"},
                    "explanation": "Elevated SOGE indicates stress.",
                    "interaction_with": ["sig_02"],
                    "sources_cited": ["CGWB"],
                }
            ],
            "confounders": [
                {
                    "confounder": "Meteorological drought",
                    "how_to_distinguish": "Check drought years only.",
                }
            ],
        },
    }
}

SAMPLE_LOCATION = {
    "uid": "18_31133",
    "tehsil": "Hungund",
    "district": "Bagalkot",
    "state": "Karnataka",
    "nbss_lup_aer_code": "AER-3",
    "nbss_lup_aer_name": "Deccan Plateau, hot arid ecoregion",
    "aquifer_class": "crystalline_basement",
    "aquifer_raw": "Hard Rock",
    "terrain_cluster": 1,
    "terrain_description": "Mostly Plains",
    "area_ha": 4545.8,
    "village_names": ["Hirehunakunti"],
}


def test_split_present_variables():
    raw, derived = _split_present_variables(SAMPLE_BUNDLE["groundwater_stress"]["present_variables"])
    assert "soge_dev_percent" in raw
    assert "trend_annual_delta_g_mm" in derived
    assert "annual_delta_g_mm" in raw


def test_null_if_placeholder():
    assert _null_if_placeholder("...") is None
    assert _null_if_placeholder("null") is None
    assert _null_if_placeholder("Ask about wells") == "Ask about wells"


def _assert_shared_prompt_blocks(prompt: str) -> None:
    assert "[SOLUTIONS AVAILABLE]" in prompt
    assert "groundwater_stress:" in prompt
    assert "Community pond repair" in prompt
    assert "[QUESTIONS ALREADY ASKED" in prompt
    assert "[DATA ALREADY PROVIDED BY USER" in prompt
    assert "(none)" in prompt
    assert "CRITICAL — do not re-ask" in prompt
    assert "Do not include a panel_updates field" in prompt
    assert '"panel_update_explanation": null' in prompt


def test_ollama_prompt_has_eval_block_and_json_fence():
    prompt = _build_prompt(
        location=SAMPLE_LOCATION,
        problem_description="Report stresses",
        bundle=SAMPLE_BUNDLE,
        profile="ollama",
    )
    assert "[SIGNAL EVALUATION" in prompt
    assert "NBSS-LUP AER: AER-3" in prompt
    assert "Derived/computed:" in prompt
    _assert_shared_prompt_blocks(prompt)
    assert "first character of your response must be '{'" in prompt
    assert "interaction_with" not in _format_bundle(SAMPLE_BUNDLE, "ollama")


def test_claude_prompt_has_shared_blocks_without_eval_fence():
    claude = _build_prompt(
        location=SAMPLE_LOCATION,
        problem_description="Report stresses",
        bundle=SAMPLE_BUNDLE,
        profile="claude",
    )
    assert "[SIGNAL EVALUATION" not in claude
    assert "expert agro-ecological diagnostician" in claude
    assert "Signals:" in claude
    assert "Confounders:" in claude
    _assert_shared_prompt_blocks(claude)
    assert "first character of your response must be '{'" not in claude


def test_prompt_includes_injected_data_and_prior_questions():
    prompt = _build_prompt(
        location=SAMPLE_LOCATION,
        problem_description="Report stresses",
        bundle=SAMPLE_BUNDLE,
        profile="claude",
        injected_variables={"groundwater_salinity": "high"},
        prior_asked_questions=["What is the borewell density in this village?"],
    )
    assert '"groundwater_salinity": "high"' in prompt
    assert "What is the borewell density" in prompt
    assert "(none)" not in prompt


def main() -> int:
    test_split_present_variables()
    test_null_if_placeholder()
    test_ollama_prompt_has_eval_block_and_json_fence()
    test_claude_prompt_has_shared_blocks_without_eval_fence()
    test_prompt_includes_injected_data_and_prior_questions()
    print("All prompt builder tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
