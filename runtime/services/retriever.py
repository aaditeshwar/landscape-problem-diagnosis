"""Diversity-aware evidence card retrieval."""

from __future__ import annotations

import logging
import math
from typing import Any

from pymongo.database import Database

from services.ollama_client import embed_text

log = logging.getLogger(__name__)

ACWADAM_TO_CARD_AQUIFER = {
    "volcanic": "hard_rock",
    "crystalline_basement": "hard_rock",
    "sedimentary_hard_rock": "hard_rock",
    "himalayan_and_sub_himalayan": "hard_rock",
    "alluvium": "alluvium",
    "sedimentary_soft_rock": "semi-consolidated",
}

CANDIDATE_POOL = 20
DEFAULT_LIMIT = 5
# Bonus added to similarity when selecting a card from a new production system or pathway.
SYSTEM_DIVERSITY_WEIGHT = 0.08
PATHWAY_DIVERSITY_WEIGHT = 0.08


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _card_aquifer_tag(mws_doc: dict) -> str:
    acwadam = (mws_doc.get("aquifer") or {}).get("acwadam_class", "")
    return ACWADAM_TO_CARD_AQUIFER.get(acwadam, "hard_rock")


def _production_system(card: dict) -> str:
    return str(card.get("production_system") or "Unknown")


def _pathway_id(card: dict) -> str:
    return str(card.get("causal_pathway") or card.get("card_id") or "")


def _strip_embedding(doc: dict) -> dict:
    out = dict(doc)
    out.pop("embedding", None)
    return out


def pathway_retrieval_ranks(cards: list[dict]) -> dict[str, int]:
    """Best (lowest) retrieval rank per causal pathway."""
    ranks: dict[str, int] = {}
    for card in cards:
        pid = card.get("causal_pathway")
        if not pid:
            continue
        rank = int(card.get("retrieval_rank", 999))
        ranks[str(pid)] = min(ranks.get(str(pid), 999), rank)
    return ranks


def _diverse_select(scored: list[tuple[float, dict]], limit: int) -> list[dict]:
    """Greedy MMR-style selection favouring production-system and pathway diversity."""
    remaining = list(scored)
    picked: list[dict] = []

    while len(picked) < limit and remaining:
        picked_systems = {_production_system(c) for c in picked}
        picked_pathways = {_pathway_id(c) for c in picked}
        best_idx = 0
        best_score = -1e9

        for idx, (similarity, card) in enumerate(remaining):
            bonus = 0.0
            system = _production_system(card)
            pathway = _pathway_id(card)
            if system not in picked_systems:
                bonus += SYSTEM_DIVERSITY_WEIGHT
            if pathway not in picked_pathways:
                bonus += PATHWAY_DIVERSITY_WEIGHT
            combined = similarity + bonus
            if combined > best_score:
                best_score = combined
                best_idx = idx

        similarity, card = remaining.pop(best_idx)
        enriched = dict(card)
        enriched["retrieval_score"] = round(similarity, 6)
        enriched["retrieval_rank"] = len(picked)
        picked.append(enriched)

    return picked


def _score_candidates(
    db: Database,
    query_vector: list[float],
    aquifer_tag: str,
) -> list[tuple[float, dict]]:
    query = {"aquifer_tags": aquifer_tag}
    candidates = list(db.evidence_cards.find(query))
    if len(candidates) < CANDIDATE_POOL:
        candidates = list(db.evidence_cards.find({}))

    scored: list[tuple[float, dict]] = []
    for doc in candidates:
        emb = doc.get("embedding")
        if not emb:
            continue
        scored.append((_cosine(query_vector, emb), doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[: max(CANDIDATE_POOL, DEFAULT_LIMIT)]


def _vector_search_scored(
    db: Database,
    query_vector: list[float],
    aquifer_tag: str,
    pool: int,
) -> list[tuple[float, dict]] | None:
    pipeline: list[dict[str, Any]] = [
        {
            "$vectorSearch": {
                "index": "evidence_card_vector_index",
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": max(50, pool * 10),
                "limit": pool,
                "filter": {"aquifer_tags": aquifer_tag},
            }
        },
        {"$addFields": {"vectorSearchScore": {"$meta": "vectorSearchScore"}}},
    ]
    try:
        docs = list(db.evidence_cards.aggregate(pipeline))
    except Exception as exc:
        log.debug("Atlas vector search unavailable, using cosine fallback: %s", exc)
        return None

    if not docs:
        return None

    scored: list[tuple[float, dict]] = []
    for doc in docs:
        score = doc.pop("vectorSearchScore", None)
        if score is None:
            emb = doc.get("embedding")
            score = _cosine(query_vector, emb) if emb else 0.0
        scored.append((float(score), doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _fetch_paper_chunks(
    db: Database,
    query_vector: list[float],
    pathway_tags: list[str],
    limit: int = 3,
) -> list[dict]:
    filt: dict[str, Any] = {"embedding.0": {"$exists": True}}
    if pathway_tags:
        filt["pathway_tags"] = {"$in": pathway_tags}

    chunks = list(db.paper_chunks.find(filt, {"text": 1, "paper_id": 1, "embedding": 1, "page": 1}))
    scored: list[tuple[float, dict]] = []
    for chunk in chunks:
        emb = chunk.get("embedding")
        if not emb:
            continue
        scored.append((_cosine(query_vector, emb), chunk))
    scored.sort(key=lambda item: item[0], reverse=True)

    out = []
    for _, chunk in scored[:limit]:
        out.append(
            {
                "paper_id": chunk.get("paper_id"),
                "page": chunk.get("page"),
                "text": (chunk.get("text") or "")[:400],
            }
        )
    return out


def retrieve_evidence_cards(
    db: Database,
    problem_text: str,
    mws_doc: dict,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    query_vector = embed_text(problem_text)
    aquifer_tag = _card_aquifer_tag(mws_doc)

    scored = _vector_search_scored(db, query_vector, aquifer_tag, CANDIDATE_POOL)
    if not scored:
        scored = _score_candidates(db, query_vector, aquifer_tag)

    selected = _diverse_select(scored, limit)

    enriched = []
    for card in selected:
        pathway_tags = card.get("pathway_tags") or []
        citations = _fetch_paper_chunks(db, query_vector, pathway_tags, limit=3)
        item = _strip_embedding(card)
        item["citations"] = citations
        enriched.append(item)
    return enriched
