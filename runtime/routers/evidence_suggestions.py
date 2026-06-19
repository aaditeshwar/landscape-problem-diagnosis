from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db import get_db
from services.evidence_suggestions_store import get_suggestion, save_suggestion

router = APIRouter(prefix="/api/evidence-suggestions", tags=["evidence-suggestions"])


class ReviewerBody(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)


class SuggestionSaveBody(BaseModel):
    reviewer: ReviewerBody
    suggestions: dict[str, Any] = Field(default_factory=dict)
    cluster_suffix: str | None = None
    pathway_id: str | None = None
    provenance: dict[str, Any] | None = None


@router.get("/{card_id:path}")
def suggestion_get(card_id: str, email: str = Query(..., min_length=3)):
    db = get_db()
    doc = get_suggestion(db, card_id=card_id, email=email)
    if not doc:
        raise HTTPException(status_code=404, detail="No saved suggestions for this card and email")
    return doc


@router.put("/{card_id:path}")
def suggestion_save(card_id: str, body: SuggestionSaveBody):
    db = get_db()
    try:
        return save_suggestion(
            db,
            card_id=card_id,
            reviewer_name=body.reviewer.name,
            reviewer_email=body.reviewer.email,
            suggestions=body.suggestions,
            cluster_suffix=body.cluster_suffix,
            pathway_id=body.pathway_id,
            provenance=body.provenance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
