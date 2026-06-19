"""Persist reviewer feedback in MongoDB (latest per snapshot + email)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from services.diagnosis_snapshot import build_snapshot_id, parse_snapshot_id

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COLLECTION = "diagnosis_feedback"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def feedback_doc_id(diagnosis_snapshot_id: str, email: str) -> str:
    return f"{diagnosis_snapshot_id}::{_normalize_email(email)}"


def validate_reviewer(name: str, email: str) -> tuple[str, str]:
    clean_name = str(name or "").strip()
    clean_email = _normalize_email(email)
    if not clean_name:
        raise ValueError("name is required")
    if not clean_email or not EMAIL_RE.match(clean_email):
        raise ValueError("a valid email is required")
    return clean_name, clean_email


def ensure_feedback_indexes(db: Database) -> None:
    col = db[COLLECTION]
    col.create_index("session_id")
    col.create_index("follow_up_count")
    col.create_index("mws_uid")
    col.create_index("updated_at")


def get_feedback(
    db: Database,
    *,
    diagnosis_snapshot_id: str,
    email: str,
) -> dict[str, Any] | None:
    doc_id = feedback_doc_id(diagnosis_snapshot_id, email)
    doc = db[COLLECTION].find_one({"_id": doc_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


def save_feedback(
    db: Database,
    *,
    diagnosis_snapshot_id: str,
    session_id: str,
    follow_up_count: int,
    turn_no: int | None,
    log_index: int | None,
    mws_uid: str,
    reviewer_name: str,
    reviewer_email: str,
    sections: dict[str, Any],
) -> dict[str, Any]:
    name, email = validate_reviewer(reviewer_name, reviewer_email)
    expected = build_snapshot_id(session_id, follow_up_count)
    if diagnosis_snapshot_id != expected:
        parsed_session, parsed_count = parse_snapshot_id(diagnosis_snapshot_id)
        if parsed_session != session_id or parsed_count != follow_up_count:
            raise ValueError("diagnosis_snapshot_id does not match session metadata")

    ensure_feedback_indexes(db)
    doc_id = feedback_doc_id(diagnosis_snapshot_id, email)
    payload: dict[str, Any] = {
        "_id": doc_id,
        "diagnosis_snapshot_id": diagnosis_snapshot_id,
        "session_id": session_id,
        "follow_up_count": follow_up_count,
        "turn_no": turn_no,
        "log_index": log_index,
        "reviewer": {"name": name, "email": email},
        "mws_uid": mws_uid,
        "updated_at": _now_iso(),
        "sections": sections or {},
    }
    db[COLLECTION].replace_one({"_id": doc_id}, payload, upsert=True)
    stored = dict(payload)
    stored.pop("_id", None)
    return stored
