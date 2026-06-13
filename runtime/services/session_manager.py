from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo.database import Database


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_session_id() -> str:
    return f"session_{uuid4().hex[:12]}"


def create_session(db: Database, mws_doc: dict) -> dict:
    session_id = new_session_id()
    aquifer = mws_doc.get("aquifer") or {}
    doc = {
        "_id": session_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "mws_uid": mws_doc.get("uid"),
        "state": mws_doc.get("state"),
        "district": mws_doc.get("district"),
        "tehsil": mws_doc.get("tehsil"),
        "aquifer_class": aquifer.get("acwadam_class"),
        "turns": [],
        "injected_variables": {},
        "final_diagnosis": {},
    }
    db.sessions.insert_one(doc)
    return doc


def get_session(db: Database, session_id: str) -> dict | None:
    return db.sessions.find_one({"_id": session_id})


def append_turn(
    db: Database,
    session_id: str,
    *,
    user_input: str,
    retrieved_cards: list[str],
    llm_model: str,
    llm_response: dict,
    injected_variable: dict | None = None,
) -> None:
    session = get_session(db, session_id)
    if not session:
        raise KeyError(session_id)

    turn_no = len(session.get("turns", [])) + 1
    turn: dict[str, Any] = {
        "turn": turn_no,
        "user_input": user_input,
        "retrieved_cards": retrieved_cards,
        "llm_model": llm_model,
        "llm_response_json": llm_response,
        "panel_updates_triggered": llm_response.get("panel_updates", []),
    }
    if injected_variable:
        turn["injected_variable"] = injected_variable

    missing_asked = []
    for item in llm_response.get("uncertain_pathways", []):
        if not isinstance(item, dict):
            continue
        questions = item.get("missing_variable_questions") or []
        if not isinstance(questions, list):
            continue
        for q in questions:
            if not isinstance(q, dict):
                continue
            var = q.get("variable")
            if var:
                missing_asked.append(var)
    if missing_asked:
        turn["missing_vars_asked"] = missing_asked

    update: dict[str, Any] = {
        "$push": {"turns": turn},
        "$set": {
            "updated_at": _now_iso(),
            "final_diagnosis": {
                "confirmed_pathways": [
                    p.get("pathway_id")
                    for p in llm_response.get("confirmed_pathways", [])
                    if isinstance(p, dict) and p.get("pathway_id")
                ],
                "confidence": {
                    p.get("pathway_id"): p.get("confidence")
                    for p in llm_response.get("confirmed_pathways", [])
                    if isinstance(p, dict) and p.get("pathway_id")
                },
                "solutions": llm_response.get("solutions", []),
            },
        },
    }
    if injected_variable:
        for key, val in injected_variable.items():
            update.setdefault("$set", {})[f"injected_variables.{key}"] = val

    db.sessions.update_one({"_id": session_id}, update)
