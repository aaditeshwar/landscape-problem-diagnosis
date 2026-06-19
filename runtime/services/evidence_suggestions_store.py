"""Persist reviewer evidence-card suggestions in MongoDB (latest per card + email)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from services.evidence_card_api import cluster_suffix_from_card_id, get_evidence_card
from services.feedback_store import validate_reviewer

COLLECTION = "evidence_card_suggestions"
SIGNAL_DIRECTIONS = frozenset({"confirms", "amplifies", "rules_out"})
SIGNAL_SEVERITIES = frozenset({"low", "moderate", "high", "critical"})
QUESTION_MODES = frozenset({"magnitude", "presence_graded", "trend", "presence_binary"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def suggestion_doc_id(card_id: str, email: str) -> str:
    from services.feedback_store import _normalize_email

    clean_email = _normalize_email(email)
    if not clean_email:
        raise ValueError("a valid email is required")
    return f"{card_id}::{clean_email}"


def ensure_suggestion_indexes(db: Database) -> None:
    col = db[COLLECTION]
    col.create_index("card_id")
    col.create_index("updated_at")


def _validate_signal_suggestion(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("each signal suggestion must be an object")
    signal_id = str(item.get("signal_id") or "").strip()
    if not signal_id:
        raise ValueError("signal_id is required on signal suggestions")
    direction = str(item.get("direction") or "").strip()
    if direction and direction not in SIGNAL_DIRECTIONS:
        raise ValueError(f"invalid direction on {signal_id}: {direction}")
    severity = str(item.get("severity") or "").strip()
    if severity and severity not in SIGNAL_SEVERITIES:
        raise ValueError(f"invalid severity on {signal_id}: {severity}")
    return {
        "signal_id": signal_id,
        "active": bool(item.get("active", True)),
        "severity": severity or None,
        "direction": direction or None,
        "explanation": str(item.get("explanation") or "").strip() or None,
        "qualitative_description": str(item.get("qualitative_description") or "").strip() or None,
        "is_new": bool(item.get("is_new")),
        "expression": str(item.get("expression") or "").strip() or None,
        "variables": item.get("variables") if isinstance(item.get("variables"), list) else None,
        "condition_type": str(item.get("condition_type") or "").strip() or None,
    }


def _validate_follow_up_question(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("each follow-up question must be an object")
    variable = str(item.get("missing_variable") or "").strip()
    if not variable:
        raise ValueError("missing_variable is required on follow-up questions")
    mode = str(item.get("question_mode") or "").strip()
    if mode and mode not in QUESTION_MODES:
        raise ValueError(f"invalid question_mode on {variable}: {mode}")
    choices_out: list[dict[str, Any]] = []
    for choice in item.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        choice_id = str(choice.get("id") or "").strip()
        if not choice_id:
            raise ValueError(f"choice id required for {variable}")
        normalized = choice.get("normalized")
        if normalized is not None and not isinstance(normalized, dict):
            raise ValueError(f"normalized must be an object for {variable}/{choice_id}")
        effects = choice.get("effects")
        if effects is not None and not isinstance(effects, dict):
            raise ValueError(f"effects must be an object for {variable}/{choice_id}")
        choices_out.append(
            {
                "id": choice_id,
                "label": str(choice.get("label") or "").strip() or None,
                "normalized": normalized,
                "effects": effects,
            }
        )
    return {
        "missing_variable": variable,
        "question_mode": mode or None,
        "question_to_user": str(item.get("question_to_user") or "").strip() or None,
        "how_answer_updates_diagnosis": str(item.get("how_answer_updates_diagnosis") or "").strip() or None,
        "response_type": str(item.get("response_type") or "").strip() or None,
        "choices": choices_out,
    }


def validate_suggestions_payload(suggestions: dict[str, Any] | None) -> dict[str, Any]:
    raw = suggestions or {}
    if not isinstance(raw, dict):
        raise ValueError("suggestions must be an object")

    signals = [_validate_signal_suggestion(item) for item in raw.get("signals") or [] if isinstance(item, dict)]
    follow_up = [
        _validate_follow_up_question(item) for item in raw.get("follow_up_questions") or [] if isinstance(item, dict)
    ]
    confounders: list[dict[str, str]] = []
    for item in raw.get("confounders") or []:
        if not isinstance(item, dict):
            continue
        confounder = str(item.get("confounder") or "").strip()
        how = str(item.get("how_to_distinguish") or "").strip()
        if confounder:
            confounders.append({"confounder": confounder, "how_to_distinguish": how})

    policy = raw.get("confirmation_policy")
    if policy is not None and not isinstance(policy, dict):
        raise ValueError("confirmation_policy must be an object")

    note = raw.get("overall_reasoning_note")
    if note is not None and not isinstance(note, str):
        raise ValueError("overall_reasoning_note must be a string")

    return {
        "signals": signals,
        "follow_up_questions": follow_up,
        "confounders": confounders,
        "confirmation_policy": policy,
        "overall_reasoning_note": str(note).strip() if isinstance(note, str) else None,
    }


def get_suggestion(db: Database, *, card_id: str, email: str) -> dict[str, Any] | None:
    doc_id = suggestion_doc_id(card_id, email)
    doc = db[COLLECTION].find_one({"_id": doc_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


def save_suggestion(
    db: Database,
    *,
    card_id: str,
    reviewer_name: str,
    reviewer_email: str,
    suggestions: dict[str, Any],
    cluster_suffix: str | None = None,
    pathway_id: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name, email = validate_reviewer(reviewer_name, reviewer_email)
    base = get_evidence_card(db, card_id)
    if not base:
        raise ValueError(f"Evidence card not found: {card_id}")

    clean = validate_suggestions_payload(suggestions)
    suffix = cluster_suffix or cluster_suffix_from_card_id(card_id)
    pathway = pathway_id or str(base.get("causal_pathway") or "")

    ensure_suggestion_indexes(db)
    doc_id = suggestion_doc_id(card_id, email)
    payload: dict[str, Any] = {
        "_id": doc_id,
        "card_id": card_id,
        "cluster_suffix": suffix,
        "pathway_id": pathway,
        "reviewer": {"name": name, "email": email},
        "updated_at": _now_iso(),
        "base_card_snapshot": base,
        "suggestions": clean,
        "provenance": provenance or {},
    }
    db[COLLECTION].replace_one({"_id": doc_id}, payload, upsert=True)
    stored = dict(payload)
    stored.pop("_id", None)
    return stored
