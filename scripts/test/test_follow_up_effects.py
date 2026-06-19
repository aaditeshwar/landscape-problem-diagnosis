#!/usr/bin/env python3
"""Unit tests for structured follow-up choice effects."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.follow_up_effects import effect_result_for_signal  # noqa: E402
from services.signal_evaluator import _apply_user_answer_overlay  # noqa: E402

CARD = {
    "missing_variable_questions": [
        {
            "missing_variable": "forest_boundary_demarcation_status",
            "response_type": "mcq",
            "choices": [
                {
                    "id": "clear",
                    "label": "Clear boundaries",
                    "normalized": {"present": False, "trend": "stable"},
                    "effects": {"signals": [{"signal_id": "sig_06", "result": False}]},
                },
                {
                    "id": "absent",
                    "label": "No demarcation",
                    "normalized": {"band": "high", "present": True, "trend": "worsening"},
                    "effects": {"signals": [{"signal_id": "sig_06", "result": True}]},
                },
            ],
        }
    ],
    "diagnostic_signals": [
        {
            "signal_id": "sig_06",
            "variables": ["forest_boundary_demarcation_status"],
            "direction": "confirms",
            "condition": {"type": "qualitative", "qualitative_description": "Boundary status"},
        }
    ],
}


def test_effect_result_for_signal():
    assert effect_result_for_signal(
        CARD,
        variable="forest_boundary_demarcation_status",
        choice_id="clear",
        signal_id="sig_06",
    ) is False
    assert effect_result_for_signal(
        CARD,
        variable="forest_boundary_demarcation_status",
        choice_id="absent",
        signal_id="sig_06",
    ) is True


def test_overlay_uses_effects_before_heuristics():
    signal = CARD["diagnostic_signals"][0]
    overlay = _apply_user_answer_overlay(
        signal=signal,
        condition=signal["condition"],
        injected={
            "forest_boundary_demarcation_status": {
                "variable": "forest_boundary_demarcation_status",
                "choice_id": "clear",
                "present": False,
                "trend": "stable",
                "raw": "Clear boundaries",
            }
        },
        card=CARD,
        initial_status="needs_llm",
    )
    assert overlay is not None
    assert overlay["status"] == "user_provided"
    assert overlay["result"] is False
    assert overlay["inference"] == "evaluated"


def main() -> int:
    test_effect_result_for_signal()
    test_overlay_uses_effects_before_heuristics()
    print("All follow-up effects tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
