"""Reconstruct diagnosis feedback context from logs + session."""

from __future__ import annotations

import re
from typing import Any

from pymongo.database import Database

from services.context_clusters import cluster_by_suffix
from services.diagnosis_snapshot import build_snapshot_id, parse_snapshot_id
from services.geojson import sanitize_mongo_doc
from services.log_reader import find_log_event
from services.mws_enrich import enrich_mws_doc
from services.session_manager import get_session

CARD_SUFFIX_RE = re.compile(r"__(\d{3})$")


def _pathway_id_from_card(card: dict[str, Any]) -> str:
    pathway = str(card.get("causal_pathway") or "").strip()
    if pathway:
        return pathway
    card_id = str(card.get("card_id") or "")
    if "__" in card_id:
        return card_id.rsplit("__", 1)[0].split("__")[-1]
    return card_id


def _cluster_suffix(card_id: str | None) -> str | None:
    match = CARD_SUFFIX_RE.search(str(card_id or ""))
    return match.group(1) if match else None


from services.feedback_history import build_follow_up_history


def _pathway_notes(llm_response: dict[str, Any], signal_evaluation: dict[str, Any] | None) -> dict[str, str]:
    """Full card overall_reasoning_note per pathway (feedback page shows after auto-generated reasoning)."""
    notes: dict[str, str] = {}
    eval_by_pathway = {
        str(item.get("pathway_id")): item
        for item in (signal_evaluation or {}).get("pathways") or []
        if isinstance(item, dict) and item.get("pathway_id")
    }
    for bucket in ("confirmed_pathways", "uncertain_pathways"):
        for pathway in llm_response.get(bucket) or []:
            if not isinstance(pathway, dict):
                continue
            pathway_id = str(pathway.get("pathway_id") or "")
            if not pathway_id:
                continue
            eval_note = (eval_by_pathway.get(pathway_id) or {}).get("evidence_note")
            if eval_note and str(eval_note).strip():
                notes[pathway_id] = str(eval_note).strip()
    return notes


def _card_diagnostic_signals(doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signal in doc.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        sig_id = str(signal.get("signal_id") or "").strip()
        if not sig_id:
            continue
        rows.append(
            {
                "signal_id": sig_id,
                "active": signal.get("active", True) is not False,
                "direction": signal.get("direction"),
            }
        )
    return rows


def _retrieved_cards(db: Database, card_ids: list[str]) -> list[dict[str, Any]]:
    if not card_ids:
        return []
    docs = list(db.evidence_cards.find({"card_id": {"$in": card_ids}}))
    by_id = {str(doc.get("card_id")): doc for doc in docs if doc.get("card_id")}
    rows: list[dict[str, Any]] = []
    for card_id in card_ids:
        doc = by_id.get(str(card_id))
        if not doc:
            continue
        suffix = _cluster_suffix(str(card_id))
        rows.append(
            {
                "card_id": str(card_id),
                "pathway_id": _pathway_id_from_card(doc),
                "cluster_suffix": suffix,
                "production_system": doc.get("production_system"),
                "observed_stress": doc.get("observed_stress"),
                "causal_pathway": doc.get("causal_pathway"),
                "diagnostic_signals": _card_diagnostic_signals(doc),
            }
        )
    return rows


def resolve_snapshot(
    *,
    snapshot_id: str | None = None,
    session_id: str | None = None,
    follow_up_count: int | None = None,
    log_index: int | None = None,
) -> tuple[str, int, int | None]:
    if snapshot_id:
        parsed_session, parsed_count = parse_snapshot_id(snapshot_id)
        return parsed_session, parsed_count, log_index
    if not session_id:
        raise ValueError("snapshot_id or session_id is required")
    if follow_up_count is None:
        raise ValueError("follow_up_count is required when snapshot_id is omitted")
    return session_id, int(follow_up_count), log_index


def build_feedback_context(
    db: Database,
    *,
    snapshot_id: str | None = None,
    session_id: str | None = None,
    follow_up_count: int | None = None,
    log_index: int | None = None,
) -> dict[str, Any]:
    resolved_session, resolved_count, resolved_log_index = resolve_snapshot(
        snapshot_id=snapshot_id,
        session_id=session_id,
        follow_up_count=follow_up_count,
        log_index=log_index,
    )
    diagnosis_snapshot_id = build_snapshot_id(resolved_session, resolved_count)

    session = get_session(db, resolved_session)
    if not session:
        raise KeyError(f"Session not found: {resolved_session}")

    event = find_log_event(
        session_id=resolved_session,
        follow_up_count=resolved_count,
        log_index=resolved_log_index,
    )
    if not event:
        raise KeyError(
            f"No log event for snapshot {diagnosis_snapshot_id}"
        )

    llm_response = event.get("llm_response") or {}
    if not isinstance(llm_response, dict):
        llm_response = {}

    mws_uid = str(session.get("mws_uid") or event.get("mws_uid") or "")
    mws_doc = db.mws_data.find_one({"uid": mws_uid})
    if not mws_doc:
        raise KeyError(f"MWS not found: {mws_uid}")
    mws_doc = sanitize_mongo_doc(enrich_mws_doc(db, mws_doc))

    signal_evaluation = event.get("signal_evaluation") or llm_response.get("signal_evaluation")
    follow_up_history = build_follow_up_history(session, resolved_count)
    pathway_notes = _pathway_notes(llm_response, signal_evaluation)
    card_ids = event.get("retrieved_card_ids") or []

    want_llm = bool(event.get("want_llm_opinion"))
    llm_skipped = bool(event.get("llm_skipped"))
    llm_diagnosis = None
    if want_llm and not llm_skipped:
        llm_diagnosis = {
            "reviewer_commentary": llm_response.get("reviewer_commentary"),
            "independent_pathway_review": llm_response.get("independent_pathway_review"),
            "change_review": llm_response.get("change_review"),
            "solutions_review_notes": llm_response.get("solutions_review_notes"),
        }

    summary = llm_response.get("panel_update_explanation")

    return {
        "session_id": resolved_session,
        "diagnosis_snapshot_id": diagnosis_snapshot_id,
        "follow_up_count": resolved_count,
        "turn_no": event.get("turn_no"),
        "log_index": event.get("index"),
        "mws_uid": mws_uid,
        "mws_doc": mws_doc,
        "want_llm_opinion": want_llm,
        "llm_skipped": llm_skipped,
        "follow_up_history": follow_up_history,
        "server_diagnosis": {
            "confirmed_pathways": llm_response.get("confirmed_pathways") or [],
            "uncertain_pathways": llm_response.get("uncertain_pathways") or [],
            "summary": summary,
            "solutions": llm_response.get("solutions") or [],
            "signal_evaluation": signal_evaluation,
            "pathway_notes": pathway_notes,
            "panel_updates": llm_response.get("panel_updates") or [],
            "panel_update_explanation": llm_response.get("panel_update_explanation"),
        },
        "llm_diagnosis": llm_diagnosis,
        "retrieved_cards": _retrieved_cards(db, card_ids),
        "context_clusters": cluster_by_suffix(),
        "skipped_production_systems": event.get("skipped_production_systems") or [],
    }
