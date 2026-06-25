#!/usr/bin/env python3
"""Unit tests for server-side evidence note and pathway status helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.evidence_note import (  # noqa: E402
    build_server_panel_summary,
    format_pathway_reasoning,
    pathway_status_from_evaluation,
    solutions_for_confirmed_pathways,
)

SAMPLE_BUNDLE = {
    "groundwater_stress": {
        "solutions": ["Community pond repair", "Check dam construction", "Shared solution"],
        "present_variables": {"soge_dev_percent": 56.86},
        "missing_variables": ["annual_well_depth_m"],
        "missing_variable_questions": [
            {
                "missing_variable": "annual_well_depth_m",
                "question_to_user": "How deep are wells in your area?",
            }
        ],
        "evidence_card": {
            "overall_reasoning_note": "Confirm with at least two primary signals.",
            "diagnostic_signals": [
                {"signal_id": "sig_1", "direction": "confirms", "active": True},
                {"signal_id": "sig_2", "direction": "confirms", "active": True},
                {"signal_id": "sig_3", "direction": "amplifies", "active": True},
            ],
        },
    },
    "drought": {
        "solutions": ["Drought contingency plan", "Shared solution"],
        "present_variables": {},
        "missing_variables": ["borewell_density"],
        "missing_variable_questions": [
            {
                "missing_variable": "borewell_density",
                "question_to_user": "How many borewells are nearby?",
            }
        ],
        "evidence_card": {"overall_reasoning_note": "At least two confirming signals required."},
    },
}

SAMPLE_LOCATION = {
    "uid": "4_91594",
    "village_names": ["Test Village"],
}


def _signal_eval(confirms_by_pathway: dict[str, int], *, rules_out: set[str] | None = None) -> dict:
    rules_out = rules_out or set()
    out = {}
    for pathway_id, confirms_true in confirms_by_pathway.items():
        signals = []
        for idx in range(confirms_true):
            signals.append(
                {
                    "signal_id": f"sig_{idx + 1}",
                    "direction": "confirms",
                    "result": True,
                    "status": "ok",
                }
            )
        if pathway_id in rules_out:
            signals.append(
                {
                    "signal_id": "sig_ro",
                    "direction": "rules_out",
                    "result": True,
                    "status": "ok",
                }
            )
        out[pathway_id] = {
            "summary": {
                "confirms_true": confirms_true,
                "rules_out_true": 1 if pathway_id in rules_out else 0,
                "needs_llm": 2 if confirms_true == 0 else 0,
            },
            "evidence_note": SAMPLE_BUNDLE[pathway_id]["evidence_card"]["overall_reasoning_note"],
            "signals": signals,
        }
    return out


def test_pathway_status_confirmed_and_uncertain():
    signal_eval = _signal_eval({"groundwater_stress": 1, "drought": 0})
    status = pathway_status_from_evaluation(
        signal_eval,
        SAMPLE_BUNDLE,
        location=SAMPLE_LOCATION,
    )
    confirmed_ids = [p["pathway_id"] for p in status["confirmed_pathways"]]
    uncertain_ids = [p["pathway_id"] for p in status["uncertain_pathways"]]
    assert confirmed_ids == ["groundwater_stress"]
    assert status["confirmed_pathways"][0]["confidence"] == "medium"
    assert uncertain_ids == ["drought"]
    assert status["uncertain_pathways"][0]["missing_variable_questions"][0]["variable"] == "borewell_density"


def test_pathway_status_rules_out_omitted():
    signal_eval = _signal_eval(
        {"groundwater_stress": 0, "drought": 0},
        rules_out={"groundwater_stress"},
    )
    status = pathway_status_from_evaluation(signal_eval, SAMPLE_BUNDLE)
    confirmed_ids = [p["pathway_id"] for p in status["confirmed_pathways"]]
    assert "groundwater_stress" not in confirmed_ids
    uncertain_ids = [p["pathway_id"] for p in status["uncertain_pathways"]]
    assert "groundwater_stress" not in uncertain_ids


def test_pathway_with_confirms_false_but_missing_vars_stays_uncertain():
    signal_eval = {
        "groundwater_stress": {
            "summary": {"confirms_true": 0, "rules_out_true": 0, "needs_llm": 1},
            "evidence_note": "Confirm with at least two primary signals.",
            "signals": [
                {
                    "signal_id": "sig_02",
                    "direction": "confirms",
                    "result": False,
                    "status": "ok",
                }
            ],
        }
    }
    status = pathway_status_from_evaluation(signal_eval, SAMPLE_BUNDLE)
    uncertain_ids = [p["pathway_id"] for p in status["uncertain_pathways"]]
    assert "groundwater_stress" in uncertain_ids


def test_pathway_fully_contradicted_without_gap_is_omitted():
    signal_eval = {
        "groundwater_stress": {
            "summary": {"confirms_true": 0, "rules_out_true": 0, "needs_llm": 0, "amplifies_true": 0},
            "evidence_note": "",
            "signals": [
                {
                    "signal_id": "sig_02",
                    "direction": "confirms",
                    "result": False,
                    "status": "ok",
                }
            ],
        }
    }
    bundle = {
        "groundwater_stress": {
            **SAMPLE_BUNDLE["groundwater_stress"],
            "missing_variables": [],
            "missing_variable_questions": [],
        }
    }
    status = pathway_status_from_evaluation(signal_eval, bundle)
    assert status["uncertain_pathways"] == []


def test_format_pathway_reasoning_includes_mws():
    reasoning = format_pathway_reasoning(
        "groundwater_stress",
        location=SAMPLE_LOCATION,
        pathway_eval=_signal_eval({"groundwater_stress": 1})["groundwater_stress"],
        bundle=SAMPLE_BUNDLE,
        status="confirmed",
    )
    assert "4_91594" in reasoning
    assert "1/2 confirming signals TRUE (sig_1)" in reasoning
    assert "0/1 amplifying signals TRUE (none)" in reasoning


def test_solutions_dedup_and_order():
    solutions = solutions_for_confirmed_pathways(
        ["groundwater_stress", "drought"],
        SAMPLE_BUNDLE,
    )
    assert solutions[0] == "Community pond repair"
    assert "Shared solution" in solutions
    assert solutions.count("Shared solution") == 1


def test_build_server_panel_summary():
    status = pathway_status_from_evaluation(
        _signal_eval({"groundwater_stress": 1}),
        SAMPLE_BUNDLE,
        location=SAMPLE_LOCATION,
    )
    summary = build_server_panel_summary(
        SAMPLE_LOCATION,
        status["confirmed_pathways"],
        status["uncertain_pathways"],
        _signal_eval({"groundwater_stress": 1, "drought": 0}),
        problem_description="Our wells are drying up",
    )
    assert "4_91594" in summary
    assert "groundwater stress" in summary.lower()
    assert "wells are drying" in summary


def main() -> int:
    test_pathway_status_confirmed_and_uncertain()
    test_pathway_status_rules_out_omitted()
    test_pathway_with_confirms_false_but_missing_vars_stays_uncertain()
    test_pathway_fully_contradicted_without_gap_is_omitted()
    test_format_pathway_reasoning_includes_mws()
    test_solutions_dedup_and_order()
    test_build_server_panel_summary()
    print("All evidence note tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
