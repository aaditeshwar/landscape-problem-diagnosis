from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db import get_db
from services.diagnosis_snapshot import parse_snapshot_id
from services.feedback_context import build_feedback_context
from services.feedback_store import get_feedback, save_feedback

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class ReviewerBody(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)


class FeedbackSaveBody(BaseModel):
    reviewer: ReviewerBody
    sections: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    follow_up_count: int | None = Field(default=None, ge=0)
    turn_no: int | None = Field(default=None, ge=1)
    log_index: int | None = Field(default=None, ge=0)
    mws_uid: str | None = None


@router.get("/context")
def feedback_context(
    snapshot_id: str | None = Query(None),
    session_id: str | None = Query(None),
    follow_up_count: int | None = Query(None, ge=0),
    log_index: int | None = Query(None, ge=0),
):
    db = get_db()
    try:
        return build_feedback_context(
            db,
            snapshot_id=snapshot_id,
            session_id=session_id,
            follow_up_count=follow_up_count,
            log_index=log_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/saved/{snapshot_id:path}")
def feedback_saved(snapshot_id: str, email: str = Query(..., min_length=3)):
    db = get_db()
    try:
        parse_snapshot_id(snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    doc = get_feedback(db, diagnosis_snapshot_id=snapshot_id, email=email)
    if not doc:
        raise HTTPException(status_code=404, detail="No saved feedback for this snapshot and email")
    return doc


@router.put("/saved/{snapshot_id:path}")
def feedback_save(snapshot_id: str, body: FeedbackSaveBody):
    db = get_db()
    try:
        session_id, follow_up_count = parse_snapshot_id(snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.session_id and body.session_id != session_id:
        raise HTTPException(status_code=400, detail="session_id does not match snapshot_id")
    if body.follow_up_count is not None and body.follow_up_count != follow_up_count:
        raise HTTPException(status_code=400, detail="follow_up_count does not match snapshot_id")

    context_meta: dict[str, Any] = {}
    try:
        context = build_feedback_context(db, snapshot_id=snapshot_id)
        context_meta = {
            "turn_no": context.get("turn_no"),
            "log_index": context.get("log_index"),
            "mws_uid": context.get("mws_uid"),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    mws_uid = body.mws_uid or context_meta.get("mws_uid") or ""
    if not mws_uid:
        raise HTTPException(status_code=400, detail="mws_uid could not be resolved")

    try:
        stored = save_feedback(
            db,
            diagnosis_snapshot_id=snapshot_id,
            session_id=session_id,
            follow_up_count=follow_up_count,
            turn_no=body.turn_no if body.turn_no is not None else context_meta.get("turn_no"),
            log_index=body.log_index if body.log_index is not None else context_meta.get("log_index"),
            mws_uid=str(mws_uid),
            reviewer_name=body.reviewer.name,
            reviewer_email=body.reviewer.email,
            sections=body.sections,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return stored
