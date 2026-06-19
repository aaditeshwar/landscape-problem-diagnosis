from __future__ import annotations

from fastapi import APIRouter, HTTPException

from db import get_db
from services.evidence_card_api import get_evidence_card, list_cards_by_cluster

router = APIRouter(prefix="/api/evidence-cards", tags=["evidence-cards"])


@router.get("/by-cluster/{suffix}")
def evidence_cards_by_cluster(suffix: str):
    db = get_db()
    cards = list_cards_by_cluster(db, suffix)
    return {"suffix": suffix.zfill(3)[-3:], "cards": cards}


@router.get("/card/{card_id:path}")
def evidence_card_detail(card_id: str):
    db = get_db()
    doc = get_evidence_card(db, card_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Evidence card not found: {card_id}")
    return doc
