#!/usr/bin/env python3
"""Tests for feedback context reconstruction helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.feedback_history import build_follow_up_history  # noqa: E402


def test_follow_up_history_empty_for_initial_snapshot():
    session = {
        "turns": [
            {"turn": 1, "user_input": "problem", "llm_response_json": {"follow_up_question": "Q1"}},
        ]
    }
    assert build_follow_up_history(session, 0) == []


def test_follow_up_history_one_exchange():
    session = {
        "turns": [
            {
                "turn": 1,
                "user_input": "problem",
                "llm_response_json": {
                    "follow_up_question": "Is irrigation available?",
                    "follow_up_variable": "irrigation_available",
                },
            },
            {
                "turn": 2,
                "user_input": "Mostly rainfed",
                "llm_response_json": {"panel_updates": ["cropping_intensity"]},
            },
        ]
    }
    history = build_follow_up_history(session, 1)
    assert len(history) == 1
    assert history[0]["question"] == "Is irrigation available?"
    assert history[0]["answer"] == "Mostly rainfed"
    assert history[0]["variable"] == "irrigation_available"


def test_follow_up_history_includes_mcq():
    session = {
        "turns": [
            {
                "turn": 1,
                "user_input": "problem",
                "llm_response_json": {
                    "follow_up_question": "Is irrigation available?",
                    "follow_up_mcq": {
                        "variable": "irrigation_available",
                        "question": "Is irrigation available?",
                        "choices": [
                            {"id": "yes", "label": "Yes, mostly irrigated"},
                            {"id": "no", "label": "No, mostly rainfed"},
                        ],
                    },
                },
            },
            {"turn": 2, "user_input": "No, mostly rainfed", "llm_response_json": {}},
        ]
    }
    history = build_follow_up_history(session, 1)
    assert history[0]["mcq"]["choices"][1]["label"] == "No, mostly rainfed"


def main() -> int:
    test_follow_up_history_empty_for_initial_snapshot()
    test_follow_up_history_one_exchange()
    test_follow_up_history_includes_mcq()
    print("All feedback context helper tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
