#!/usr/bin/env python3
"""Unit tests for MCQ follow-up helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.follow_up_mcq import (  # noqa: E402
    attach_follow_up_mcq,
    follow_up_mcq_from_bundle,
    normalized_answer_from_mcq_choice,
)

BUNDLE = {
    "groundwater_stress": {
        "missing_variable_questions": [
            {
                "missing_variable": "borewell_density",
                "question_to_user": "How many borewells?",
                "response_type": "mcq",
                "choices": [
                    {
                        "id": "few",
                        "label": "Very few",
                        "normalized": {"band": "low", "present": True},
                    },
                    {
                        "id": "many",
                        "label": "Many",
                        "normalized": {"band": "high", "present": True},
                    },
                ],
            }
        ]
    }
}


def test_follow_up_mcq_from_bundle():
    mcq = follow_up_mcq_from_bundle(
        BUNDLE,
        variable="borewell_density",
        question="How many borewells?",
    )
    assert mcq is not None
    assert mcq["choices"][0]["id"] == "few"


def test_normalized_answer_from_mcq_choice():
    payload = normalized_answer_from_mcq_choice(BUNDLE, "borewell_density", "many")
    assert payload is not None
    assert payload["band"] == "high"
    assert payload["choice_id"] == "many"


def test_attach_follow_up_mcq():
    response = attach_follow_up_mcq(
        {
            "follow_up_variable": "borewell_density",
            "follow_up_question": "How many borewells?",
        },
        BUNDLE,
    )
    assert response["follow_up_mcq"]["choices"]


def main() -> int:
    test_follow_up_mcq_from_bundle()
    test_normalized_answer_from_mcq_choice()
    test_attach_follow_up_mcq()
    print("All follow-up MCQ tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
