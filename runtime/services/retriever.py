"""Diversity-aware evidence card retrieval."""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from pymongo.database import Database

from services.diagnosis_trace import RetrievalMetrics, RetrievalResult
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

# When an MWS AER has few dedicated cards, retrieve from physiographically adjacent AERs
# instead of falling back to unrelated regions (e.g. AER-3 must not pull AER-9 Indo-Gangetic).
AER_RETRIEVAL_NEIGHBORS: dict[str, list[str]] = {
    "AER-1": ["AER-1", "AER-14", "AER-2", "AER-4"],
    "AER-2": ["AER-2", "AER-4", "AER-5"],
    "AER-3": ["AER-3", "AER-6", "AER-7", "AER-8"],
    "AER-4": ["AER-2", "AER-4", "AER-5", "AER-9"],
    "AER-5": ["AER-2", "AER-4", "AER-5", "AER-6"],
    "AER-6": ["AER-3", "AER-6", "AER-7", "AER-8"],
    "AER-7": ["AER-3", "AER-6", "AER-7", "AER-8"],
    "AER-8": ["AER-3", "AER-6", "AER-7", "AER-8"],
    "AER-9": ["AER-4", "AER-9", "AER-10", "AER-13"],
    "AER-10": ["AER-5", "AER-9", "AER-10", "AER-7", "AER-8"],
    # Eastern plateau / Chhota Nagpur — proxy to peninsular hard-rock cards until dedicated cluster exists.
    "AER-11": ["AER-11", "AER-12", "AER-10", "AER-7", "AER-8"],
    "AER-12": ["AER-12", "AER-11", "AER-10", "AER-7", "AER-8"],
    "AER-13": ["AER-9", "AER-13", "AER-15", "AER-10"],
    # Himalayan / NE / delta — weak proxies until dedicated cards exist.
    "AER-14": ["AER-14", "AER-1", "AER-16", "AER-10", "AER-9"],
    "AER-15": ["AER-13", "AER-15", "AER-9", "AER-18", "AER-19"],
    "AER-16": ["AER-16", "AER-14", "AER-17", "AER-10", "AER-15"],
    "AER-17": ["AER-17", "AER-16", "AER-11", "AER-10", "AER-7"],
    "AER-18": ["AER-15", "AER-18", "AER-19", "AER-8"],
    "AER-19": ["AER-15", "AER-18", "AER-19"],
    "AER-20": ["AER-20", "AER-19", "AER-18"],
}

CANDIDATE_POOL = 20
DEFAULT_LIMIT = 6
# Bonus added to similarity when selecting a card from a new production system or pathway.
SYSTEM_DIVERSITY_WEIGHT = 0.08
PATHWAY_DIVERSITY_WEIGHT = 0.08
# Prefer evidence cards whose aer_tags include the MWS AER over neighbor-proxy cards.
DIRECT_AER_MATCH_WEIGHT = 0.06


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


def _card_aer_tag(mws_doc: dict) -> str | None:
    code = mws_doc.get("nbss_lup_aer_code")
    if code and str(code).startswith("AER-"):
        return str(code)
    return None


def _aer_tags_for_retrieval(mws_doc: dict) -> list[str] | None:
    """Expand MWS AER to a retrieval set of related AER codes."""
    aer = _card_aer_tag(mws_doc)
    if not aer:
        return None
    neighbors = AER_RETRIEVAL_NEIGHBORS.get(aer, [aer])
    # Preserve order while deduplicating (MWS AER first).
    ordered: list[str] = []
    for tag in [aer, *neighbors]:
        if tag not in ordered:
            ordered.append(tag)
    return ordered


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


def _apply_direct_aer_bonus(
    scored: list[tuple[float, dict]],
    mws_aer: str | None,
) -> list[tuple[float, dict]]:
    """Boost cards that list the MWS AER in aer_tags (over neighbor-proxy cards)."""
    if not mws_aer:
        return scored
    boosted: list[tuple[float, dict]] = []
    for similarity, card in scored:
        tags = card.get("aer_tags") or []
        bonus = DIRECT_AER_MATCH_WEIGHT if mws_aer in tags else 0.0
        boosted.append((similarity + bonus, card))
    boosted.sort(key=lambda item: item[0], reverse=True)
    return boosted


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


def _card_query(aquifer_tag: str, aer_tags: list[str] | None) -> dict[str, Any]:
    query: dict[str, Any] = {"aquifer_tags": aquifer_tag}
    if aer_tags:
        query["aer_tags"] = {"$in": aer_tags} if len(aer_tags) > 1 else aer_tags[0]
    return query


def _fetch_candidates(
    db: Database,
    aquifer_tag: str,
    aer_tags: list[str] | None,
) -> list[dict]:
    """Load evidence cards matching aquifer and (optional) AER constraints."""
    query = _card_query(aquifer_tag, aer_tags)
    candidates = list(db.evidence_cards.find(query))
    if candidates or not aer_tags:
        return candidates

    # Last resort: same AER neighborhood without aquifer filter (never drop AER entirely).
    aer_only = {"aer_tags": {"$in": aer_tags} if len(aer_tags) > 1 else aer_tags[0]}
    candidates = list(db.evidence_cards.find(aer_only))
    if candidates:
        log.warning(
            "No cards for aquifer=%s in AER set %s; using AER-only pool (%s cards)",
            aquifer_tag,
            aer_tags,
            len(candidates),
        )
    else:
        log.warning(
            "No evidence cards for aquifer=%s AER set %s; retrieval may return fewer than %s cards",
            aquifer_tag,
            aer_tags,
            DEFAULT_LIMIT,
        )
    return candidates


def _score_candidates(
    db: Database,
    query_vector: list[float],
    aquifer_tag: str,
    aer_tags: list[str] | None = None,
    mws_aer: str | None = None,
) -> list[tuple[float, dict]]:
    candidates = _fetch_candidates(db, aquifer_tag, aer_tags)
    if len(candidates) < CANDIDATE_POOL and not aer_tags:
        candidates = list(db.evidence_cards.find({}))

    scored: list[tuple[float, dict]] = []
    for doc in candidates:
        emb = doc.get("embedding")
        if not emb:
            continue
        scored.append((_cosine(query_vector, emb), doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    scored = _apply_direct_aer_bonus(scored, mws_aer)
    return scored[: max(CANDIDATE_POOL, DEFAULT_LIMIT)]


def _vector_search_scored(
    db: Database,
    query_vector: list[float],
    aquifer_tag: str,
    pool: int,
    aer_tags: list[str] | None = None,
    mws_aer: str | None = None,
) -> list[tuple[float, dict]] | None:
    def _run(filter_query: dict[str, Any]) -> list[tuple[float, dict]] | None:
        pipeline: list[dict[str, Any]] = [
            {
                "$vectorSearch": {
                    "index": "evidence_card_vector_index",
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(50, pool * 10),
                    "limit": pool,
                    "filter": filter_query,
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
        return _apply_direct_aer_bonus(scored, mws_aer)

    scored = _run(_card_query(aquifer_tag, aer_tags))
    if aer_tags and not scored:
        aer_only = {"aer_tags": {"$in": aer_tags} if len(aer_tags) > 1 else aer_tags[0]}
        log.debug("Vector search found no hits for aquifer+AER; retrying AER-only filter")
        scored = _run(aer_only)
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
) -> RetrievalResult:
    t_total = time.perf_counter()

    t0 = time.perf_counter()
    query_vector = embed_text(problem_text)
    embed_ms = (time.perf_counter() - t0) * 1000

    aquifer_tag = _card_aquifer_tag(mws_doc)
    aer_tags = _aer_tags_for_retrieval(mws_doc)
    mws_aer = _card_aer_tag(mws_doc)

    t1 = time.perf_counter()
    scored = _vector_search_scored(db, query_vector, aquifer_tag, CANDIDATE_POOL, aer_tags, mws_aer)
    if not scored:
        scored = _score_candidates(db, query_vector, aquifer_tag, aer_tags, mws_aer)
    selected = _diverse_select(scored, limit)
    search_ms = (time.perf_counter() - t1) * 1000

    enriched = []
    t2 = time.perf_counter()
    for card in selected:
        pathway_tags = card.get("pathway_tags") or []
        citations = _fetch_paper_chunks(db, query_vector, pathway_tags, limit=3)
        item = _strip_embedding(card)
        item["citations"] = citations
        enriched.append(item)
    citations_ms = (time.perf_counter() - t2) * 1000

    metrics = RetrievalMetrics(
        embed_ms=embed_ms,
        search_ms=search_ms,
        citations_ms=citations_ms,
    )
    log.debug(
        "Retrieved %s evidence cards in %.1f ms (embed=%.1f search=%.1f citations=%.1f total=%.1f)",
        len(enriched),
        (time.perf_counter() - t_total) * 1000,
        embed_ms,
        search_ms,
        citations_ms,
        metrics.total_ms,
    )
    return RetrievalResult(cards=enriched, metrics=metrics)


def load_evidence_cards_by_ids(db: Database, card_ids: list[str]) -> list[dict]:
    """Reload evidence cards from Mongo in retrieval order (follow-up retrieval freeze)."""
    if not card_ids:
        return []
    docs = list(db.evidence_cards.find({"card_id": {"$in": card_ids}}))
    by_id = {str(doc.get("card_id")): doc for doc in docs if doc.get("card_id")}
    ordered: list[dict] = []
    for rank, card_id in enumerate(card_ids):
        doc = by_id.get(str(card_id))
        if not doc:
            continue
        item = _strip_embedding(dict(doc))
        item["retrieval_rank"] = rank
        item["citations"] = []
        ordered.append(item)
    return ordered


def frozen_retrieval_result(cards: list[dict]) -> RetrievalResult:
    return RetrievalResult(
        cards=cards,
        metrics=RetrievalMetrics(embed_ms=0.0, search_ms=0.0, citations_ms=0.0),
    )
