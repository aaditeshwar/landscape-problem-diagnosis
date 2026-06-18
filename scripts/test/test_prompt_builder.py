#!/usr/bin/env python3
"""Unit tests for diagnosis prompt profiles (no LLM required)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.reasoner import (  # noqa: E402
    _build_prompt,
    _build_reviewer_prompt,
    _format_bundle,
    _merge_reviewer_into_response,
    _normalize_reviewer_response,
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
    "tehsil_label": "Hungund, Bagalkot, Karnataka",
    "tehsils": [{"state": "Karnataka", "district": "Bagalkot", "tehsil": "Hungund"}],
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


def test_ollama_prompt_has_signal_results_and_json_fence():
    prompt = _build_prompt(
        location=SAMPLE_LOCATION,
        problem_description="Report stresses",
        bundle=SAMPLE_BUNDLE,
        profile="ollama",
    )
    assert "[SIGNAL EVALUATION RESULTS" in prompt
    assert "server-computed" in prompt
    assert "[ANSWER THE USER'S QUESTION" in prompt
    assert "primary deliverable" in prompt
    assert "For this question:" in prompt
    assert "name each confirmed pathway_id" in prompt
    assert "Answer [USER PROBLEM] first" in prompt
    assert "not merely classify pathways in isolation" in prompt
    assert "sig_01" in prompt
    assert "TRUE" in prompt or "FALSE" in prompt
    assert "Evaluate each signal expression against present_variables" not in prompt
    assert "NBSS-LUP AER: AER-3" in prompt
    assert "Derived/computed:" in prompt
    _assert_shared_prompt_blocks(prompt)
    assert "first character of your response must be '{'" in prompt
    assert "interaction_with" not in _format_bundle(SAMPLE_BUNDLE, "ollama")


def test_claude_prompt_reasons_signals_without_server_eval():
    claude = _build_prompt(
        location=SAMPLE_LOCATION,
        problem_description="Report stresses",
        bundle=SAMPLE_BUNDLE,
        profile="claude",
    )
    assert "[SIGNAL EVALUATION RESULTS — server-computed" not in claude
    assert "server-computed; authoritative" not in claude
    assert "Answer [USER PROBLEM] first" in claude or "ANSWER THE USER'S QUESTION" in claude
    assert "primary deliverable" in claude
    assert "For this question:" in claude
    assert "name each confirmed pathway_id" in claude
    assert "Do NOT assume server-side TRUE/FALSE" in claude
    assert "sig_01" in claude
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


SAMPLE_SERVER_RESPONSE = {
    "confirmed_pathways": [
        {
            "pathway_id": "agriculture/water_scarcity/groundwater_stress",
            "confidence": "high",
            "reasoning": "SOGE elevated.",
        }
    ],
    "uncertain_pathways": [],
    "solutions": ["Community pond repair", "Check dam construction"],
    "panel_updates": ["annual_well_depth_m trend"],
    "panel_update_explanation": "Groundwater stress is evident from SOGE.",
    "follow_up_question": "What is the borewell density?",
    "follow_up_variable": "borewell_density",
}

SAMPLE_SIGNAL_EVAL = {
    "groundwater_stress": {
        "summary": {"confirms_true": 1, "rules_out_true": 0, "needs_llm": 0},
        "signals": [
            {
                "signal_id": "sig_01",
                "direction": "confirms",
                "result": True,
                "status": "ok",
            }
        ],
    }
}


def test_reviewer_prompt_uses_reviewer_user_query_directive_not_legacy():
    prompt = _build_reviewer_prompt(
        location=SAMPLE_LOCATION,
        problem_description="Should we prioritise check dams or farm ponds?",
        bundle=SAMPLE_BUNDLE,
        server_response=SAMPLE_SERVER_RESPONSE,
        signal_eval=SAMPLE_SIGNAL_EVAL,
    )
    assert "[ANSWER THE USER'S QUESTION — REVIEWER]" in prompt
    assert "panel_update_explanation MUST open with a direct" in prompt
    assert "[SERVER DIAGNOSIS].panel_updates" in prompt
    assert "For this question:" in prompt
    assert "Every confirmed_pathways and uncertain_pathways reasoning string MUST" not in prompt


def test_reviewer_prompt_includes_server_diagnosis_and_signal_results():
    prompt = _build_reviewer_prompt(
        location=SAMPLE_LOCATION,
        problem_description="Why is groundwater declining?",
        bundle=SAMPLE_BUNDLE,
        server_response=SAMPLE_SERVER_RESPONSE,
        signal_eval=SAMPLE_SIGNAL_EVAL,
    )
    assert "[SERVER DIAGNOSIS — canonical" in prompt
    assert "[REVIEWER TASK]" in prompt
    assert "[SIGNAL EVALUATION RESULTS" in prompt
    assert "server-computed" in prompt
    assert "Do NOT output confirmed_pathways" in prompt
    assert "Community pond repair" in prompt
    assert "server owns confirmed_pathways" in prompt.lower() or "server owns" in prompt
    assert '"change_review": null' in prompt
    assert "sig_01" in prompt


def test_reviewer_prompt_revision_includes_change_review_task():
    server_with_revision = {
        **SAMPLE_SERVER_RESPONSE,
        "diagnosis_revision": {
            "pathway_changes": [
                {"pathway_id": "groundwater_stress", "from": "uncertain", "to": "confirmed"}
            ]
        },
    }
    prompt = _build_reviewer_prompt(
        location=SAMPLE_LOCATION,
        problem_description="Why is groundwater declining?",
        bundle=SAMPLE_BUNDLE,
        server_response=server_with_revision,
        signal_eval=SAMPLE_SIGNAL_EVAL,
        follow_up_context="borewell_density: many",
        is_revision=True,
    )
    assert "[SERVER REVISION — after follow-up answer]" in prompt
    assert "change_review" in prompt
    assert "agrees_with_revision" in prompt
    assert "[USER FOLLOW-UP ANSWER]" in prompt


def test_normalize_and_merge_reviewer_preserves_server_pathways():
    server = dict(SAMPLE_SERVER_RESPONSE)
    reviewer_raw = {
        "server_review": [
            {
                "pathway_id": "agriculture/water_scarcity/groundwater_stress",
                "agreement": "agree",
                "pathway_comment": "Matches the user's concern.",
            }
        ],
        "change_review": None,
        "panel_update_explanation": "Groundwater decline is the main issue here.",
        "solutions_review": {
            "notes": "Prioritise recharge structures.",
            "priority_order": ["Check dam construction", "Community pond repair"],
        },
    }
    reviewer = _normalize_reviewer_response(reviewer_raw)
    merged = _merge_reviewer_into_response(server, reviewer)

    assert merged["confirmed_pathways"] == server["confirmed_pathways"]
    assert merged["uncertain_pathways"] == server["uncertain_pathways"]
    assert len(merged["reviewer_commentary"]) == 1
    assert merged["reviewer_commentary"][0]["agreement"] == "agree"
    assert merged["panel_update_explanation"] == reviewer_raw["panel_update_explanation"]
    assert merged["solutions_review_notes"] == "Prioritise recharge structures."
    assert merged["solutions"][0] == "Check dam construction"
    assert merged["solutions"][1] == "Community pond repair"


def test_prompt_includes_reasoning_wording_rules():
    prompt = _build_prompt(
        location=SAMPLE_LOCATION,
        problem_description="Report stresses",
        bundle=SAMPLE_BUNDLE,
        profile="ollama",
    )
    assert "NEEDS_LLM means the variable is missing from landscape data" in prompt
    assert 'Do NOT write "farmer reports"' in prompt
    assert "data is NOT yet available" in prompt
    assert "not supported by current landscape data" in prompt


def main() -> int:
    test_split_present_variables()
    test_null_if_placeholder()
    test_ollama_prompt_has_signal_results_and_json_fence()
    test_claude_prompt_reasons_signals_without_server_eval()
    test_prompt_includes_injected_data_and_prior_questions()
    test_reviewer_prompt_uses_reviewer_user_query_directive_not_legacy()
    test_reviewer_prompt_includes_server_diagnosis_and_signal_results()
    test_reviewer_prompt_revision_includes_change_review_task()
    test_normalize_and_merge_reviewer_preserves_server_pathways()
    test_prompt_includes_reasoning_wording_rules()
    print("All prompt builder tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
