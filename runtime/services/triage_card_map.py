"""Resolve evidence cards for an MWS using the server-only diagnosis path."""

from __future__ import annotations

from typing import Any

from pymongo.database import Database

from services.evidence_card_api import get_evidence_card
from services.mws_enrich import enrich_mws_doc
from services.retriever import load_mws_scoped_evidence_cards


def load_mws_doc(db: Database, mws_id: str) -> dict[str, Any] | None:
    raw = db.mws_data.find_one({"uid": mws_id})
    if not raw:
        return None
    return enrich_mws_doc(db, raw)


def resolve_cards_for_mws(db: Database, mws_doc: dict) -> dict[str, dict[str, Any]]:
    """pathway_id -> full evidence card (same pool as want_llm_opinion=false)."""
    result = load_mws_scoped_evidence_cards(db, mws_doc)
    out: dict[str, dict[str, Any]] = {}
    for card in result.cards:
        pathway = str(card.get("causal_pathway") or "").strip()
        if pathway:
            out[pathway] = card
    return out


def card_map_payload(db: Database, mws_id: str) -> dict[str, Any]:
    mws_doc = load_mws_doc(db, mws_id)
    if not mws_doc:
        return {"mws_id": mws_id, "found": False, "cards_by_pathway": {}}

    cards = resolve_cards_for_mws(db, mws_doc)
    slim = {
        pathway: {
            "card_id": card.get("card_id"),
            "causal_pathway": card.get("causal_pathway"),
            "production_system": card.get("production_system"),
            "observed_stress": card.get("observed_stress"),
            "aer_tags": card.get("aer_tags") or [],
            "cluster_suffix": card.get("cluster_suffix"),
        }
        for pathway, card in cards.items()
    }
    return {
        "mws_id": mws_id,
        "found": True,
        "nbss_lup_aer_code": mws_doc.get("nbss_lup_aer_code"),
        "cards_by_pathway": slim,
        "cards": cards,
    }


def load_card_with_fallback(db: Database, card_id: str) -> dict[str, Any] | None:
    return get_evidence_card(db, card_id)
