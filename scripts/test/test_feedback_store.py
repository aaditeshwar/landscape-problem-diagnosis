#!/usr/bin/env python3
"""Tests for feedback persistence helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.feedback_store import (  # noqa: E402
    feedback_doc_id,
    get_feedback,
    save_feedback,
    validate_reviewer,
)


def test_feedback_doc_id_normalizes_email():
    assert feedback_doc_id("sess-1::fu_0", "Reviewer@Example.COM") == "sess-1::fu_0::reviewer@example.com"


def test_validate_reviewer_requires_name_and_email():
    try:
        validate_reviewer("", "a@b.com")
        raise AssertionError("expected ValueError for empty name")
    except ValueError as exc:
        assert "name" in str(exc).lower()

    try:
        validate_reviewer("Ada", "not-an-email")
        raise AssertionError("expected ValueError for invalid email")
    except ValueError as exc:
        assert "email" in str(exc).lower()


def test_save_and_get_feedback_round_trip():
    db = MagicMock()
    col = MagicMock()
    db.__getitem__.return_value = col

    stored = save_feedback(
        db,
        diagnosis_snapshot_id="sess-abc::fu_1",
        session_id="sess-abc",
        follow_up_count=1,
        turn_no=2,
        log_index=7,
        mws_uid="MWS001",
        reviewer_name="Reviewer",
        reviewer_email="Reviewer@Example.COM",
        sections={"summary": {"free_text": "Looks good"}},
    )
    assert stored["reviewer"]["email"] == "reviewer@example.com"
    assert stored["sections"]["summary"]["free_text"] == "Looks good"
    assert col.replace_one.called

    doc_id = feedback_doc_id("sess-abc::fu_1", "reviewer@example.com")
    col.find_one.return_value = {"_id": doc_id, **stored}
    loaded = get_feedback(db, diagnosis_snapshot_id="sess-abc::fu_1", email="reviewer@example.com")
    assert loaded is not None
    assert loaded["reviewer"]["name"] == "Reviewer"
    assert "_id" not in loaded


def main() -> int:
    test_feedback_doc_id_normalizes_email()
    test_validate_reviewer_requires_name_and_email()
    test_save_and_get_feedback_round_trip()
    print("All feedback store tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
