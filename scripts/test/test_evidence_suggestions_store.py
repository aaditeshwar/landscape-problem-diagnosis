#!/usr/bin/env python3
"""Tests for evidence card suggestion persistence."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.evidence_suggestions_store import (  # noqa: E402
    get_suggestion,
    save_suggestion,
    suggestion_doc_id,
    validate_suggestions_payload,
)


def test_suggestion_doc_id_normalizes_email():
    assert suggestion_doc_id("card__001", "User@Example.com") == "card__001::user@example.com"


def test_validate_suggestions_payload():
    clean = validate_suggestions_payload(
        {
            "signals": [
                {
                    "signal_id": "sig_01",
                    "active": True,
                    "severity": "high",
                    "direction": "confirms",
                    "explanation": "Test",
                }
            ],
            "confirmation_policy": {"version": 1, "confirm_when": {"min_confirms_true": 2}},
            "overall_reasoning_note": "Note",
            "follow_up_questions": [
                {
                    "missing_variable": "borewell_density",
                    "question_mode": "magnitude",
                    "choices": [{"id": "few", "normalized": {"band": "low", "present": True}}],
                }
            ],
        }
    )
    assert clean["signals"][0]["signal_id"] == "sig_01"
    assert clean["confirmation_policy"]["version"] == 1


def test_save_and_get_round_trip():
    db = MagicMock()
    col = MagicMock()
    db.__getitem__.return_value = col
    base_card = {"card_id": "agriculture__water_scarcity__groundwater_stress__001", "causal_pathway": "groundwater_stress"}

    with patch("services.evidence_suggestions_store.get_evidence_card", return_value=base_card):
        stored = save_suggestion(
            db,
            card_id="agriculture__water_scarcity__groundwater_stress__001",
            reviewer_name="Expert",
            reviewer_email="expert@example.com",
            suggestions={"signals": [{"signal_id": "sig_01", "active": False}]},
        )
    assert stored["reviewer"]["email"] == "expert@example.com"
    assert stored["suggestions"]["signals"][0]["active"] is False
    assert col.replace_one.called

    doc_id = suggestion_doc_id("agriculture__water_scarcity__groundwater_stress__001", "expert@example.com")
    col.find_one.return_value = {"_id": doc_id, **stored}
    loaded = get_suggestion(db, card_id="agriculture__water_scarcity__groundwater_stress__001", email="expert@example.com")
    assert loaded is not None
    assert loaded["suggestions"]["signals"][0]["signal_id"] == "sig_01"


def main() -> int:
    test_suggestion_doc_id_normalizes_email()
    test_validate_suggestions_payload()
    test_save_and_get_round_trip()
    print("All evidence suggestions store tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
