#!/usr/bin/env python3
"""Tests for diagnosis snapshot identity helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.diagnosis_snapshot import (  # noqa: E402
    build_snapshot_id,
    parse_snapshot_id,
    turn_metrics_from_session,
)


def test_build_and_parse_snapshot_id():
    sid = build_snapshot_id("session_abc123", 0)
    assert sid == "session_abc123::fu_0"
    session, count = parse_snapshot_id(sid)
    assert session == "session_abc123"
    assert count == 0


def test_turn_metrics_initial():
    follow_up_count, turn_no = turn_metrics_from_session({"turns": []}, is_follow_up=False)
    assert follow_up_count == 0
    assert turn_no == 1


def test_turn_metrics_first_follow_up():
    session = {"turns": [{"turn": 1}]}
    follow_up_count, turn_no = turn_metrics_from_session(session, is_follow_up=True)
    assert follow_up_count == 1
    assert turn_no == 2


def main() -> int:
    test_build_and_parse_snapshot_id()
    test_turn_metrics_initial()
    test_turn_metrics_first_follow_up()
    print("All diagnosis snapshot tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
