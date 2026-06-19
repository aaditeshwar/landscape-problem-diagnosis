"""Read-only evidence card queries for the signal editor."""

from __future__ import annotations

import re
from typing import Any

from pymongo.database import Database

from services.geojson import sanitize_mongo_doc

CARD_SUFFIX_RE = re.compile(r"__(\d{3})$")

LIST_PROJECTION = {
    "_id": 0,
    "card_id": 1,
    "production_system": 1,
    "observed_stress": 1,
    "causal_pathway": 1,
    "pathway_tags": 1,
}


def cluster_suffix_from_card_id(card_id: str) -> str | None:
    match = CARD_SUFFIX_RE.search(str(card_id or ""))
    return match.group(1) if match else None


def list_cards_by_cluster(db: Database, suffix: str) -> list[dict[str, Any]]:
    clean_suffix = str(suffix or "").strip().zfill(3)[-3:]
    pattern = re.compile(rf"__{re.escape(clean_suffix)}$")
    docs = list(
        db.evidence_cards.find({"card_id": {"$regex": pattern}}, LIST_PROJECTION).sort("card_id", 1)
    )
    rows: list[dict[str, Any]] = []
    for doc in docs:
        row = sanitize_mongo_doc(doc) or {}
        row["cluster_suffix"] = clean_suffix
        row["pathway_id"] = str(row.get("causal_pathway") or "")
        rows.append(row)
    return rows


def get_evidence_card(db: Database, card_id: str) -> dict[str, Any] | None:
    doc = db.evidence_cards.find_one({"card_id": card_id})
    if not doc:
        return None
    row = sanitize_mongo_doc(doc) or {}
    row["cluster_suffix"] = cluster_suffix_from_card_id(card_id)
    row["pathway_id"] = str(row.get("causal_pathway") or "")
    return row
