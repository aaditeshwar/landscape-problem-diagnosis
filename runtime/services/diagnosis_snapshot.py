"""Diagnosis snapshot identity for per-stage feedback."""

from __future__ import annotations

import re
from typing import Any

SNAPSHOT_RE = re.compile(r"^(?P<session>.+)::fu_(?P<count>\d+)$")


def build_snapshot_id(session_id: str, follow_up_count: int) -> str:
    if follow_up_count < 0:
        raise ValueError("follow_up_count must be non-negative")
    return f"{session_id}::fu_{follow_up_count}"


def parse_snapshot_id(snapshot_id: str) -> tuple[str, int]:
    match = SNAPSHOT_RE.match(str(snapshot_id or "").strip())
    if not match:
        raise ValueError(
            f"Invalid snapshot_id {snapshot_id!r}; expected format session_xxx::fu_N"
        )
    return match.group("session"), int(match.group("count"))


def snapshot_fields(
    session_id: str,
    *,
    follow_up_count: int,
    turn_no: int,
    log_index: int | None = None,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "follow_up_count": follow_up_count,
        "turn_no": turn_no,
        "log_index": log_index,
        "diagnosis_snapshot_id": build_snapshot_id(session_id, follow_up_count),
    }


def turn_metrics_from_session(session: dict | None, *, is_follow_up: bool) -> tuple[int, int]:
    """Return (follow_up_count, turn_no) before append_turn for this request."""
    turns = session.get("turns") or [] if session else []
    turn_no = len(turns) + 1
    if is_follow_up:
        follow_up_count = len(turns)
    else:
        follow_up_count = 0
    return follow_up_count, turn_no
