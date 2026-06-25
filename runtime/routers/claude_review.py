from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import claude_review_store as store
from services import triage_patch_store as patch_store
from services.reviewer_access import ReviewerNotAllowedError, validate_reviewer_name

router = APIRouter(prefix="/api/claude-review", tags=["claude-review"])


class IssueDecisionBody(BaseModel):
    issue_id: str = Field(min_length=1)
    decision: str = Field(pattern="^(handled|not_handled)$")
    field_path: str = ""
    reviewer_note: str = ""
    edited_patch: dict[str, Any] | None = None


class FinalizeCardBody(BaseModel):
    batch_id: str = Field(min_length=1)
    reviewer: str | None = None
    issues: list[IssueDecisionBody] = Field(default_factory=list)
    user_card_edit: dict[str, Any] | None = None


@router.get("/batches")
def claude_review_batches():
    return {"batches": store.list_batches()}


@router.get("/batch/{batch_id}")
def claude_review_batch(batch_id: str):
    try:
        return store.batch_summary(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/batch/{batch_id}/card/{card_id:path}")
def claude_review_card(batch_id: str, card_id: str):
    try:
        return store.load_card_bundle(batch_id, card_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/card/{card_id:path}/finalize")
def claude_review_finalize_card(card_id: str, body: FinalizeCardBody):
    try:
        store.batch_summary(body.batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        if body.user_card_edit or patch_store.is_triage_batch(body.batch_id):
            reviewer = validate_reviewer_name(body.reviewer)
        else:
            reviewer = body.reviewer
        return store.finalize_card(
            card_id,
            [issue.model_dump() for issue in body.issues],
            reviewer=reviewer,
            user_card_edit=body.user_card_edit,
            batch_id=body.batch_id,
        )
    except ReviewerNotAllowedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/variable-registry")
def claude_review_variable_registry():
    return store.variable_registry_payload()


@router.get("/decisions")
def claude_review_decisions():
    return store.load_decisions_doc()


@router.get("/edited-patches")
def claude_review_edited_patches():
    return store.load_edited_patches_doc()
