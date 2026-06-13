"""
embed_utils.py (REFERENCE ONLY)
================================
Reference implementation for alias-augmented evidence card embedding.

Canonical implementation: runtime/services/card_embedding_text.py
Alias data: metadata/semantic_aliases.json

Do not run this script directly — use:
  python scripts/maintenance/preview_card_embedding_text.py
  python scripts/reembed_evidence_cards.py --apply
"""

import json
import re
from pathlib import Path
from typing import Optional

import ollama  # pip install ollama


# ── Load alias map once at module import ──────────────────────────────────────

_ALIAS_PATH = Path(__file__).parent.parent.parent / "metadata" / "semantic_aliases.json"
_alias_map: dict[str, list[str]] = {}

def _load_aliases() -> dict[str, list[str]]:
    global _alias_map
    if _alias_map:
        return _alias_map
    with open(_ALIAS_PATH) as f:
        data = json.load(f)
    _alias_map = {p["pathway_id"]: p["aliases"] for p in data["pathways"]}
    return _alias_map


# ── Text construction ─────────────────────────────────────────────────────────

def build_card_embedding_text(
    card: dict,
    include_signals: bool = True,
    include_aliases: bool = True,
) -> str:
    """
    Build the text to embed for an evidence card.

    Structure:
        [production system + observed stress + causal pathway header]
        [overall_reasoning_note — the primary semantic content]
        [signal explanations — domain vocabulary]
        [alias paragraph — broadens retrieval surface]

    Args:
        card:             Evidence card dict (conforming to evidence_card_schema.json).
        include_signals:  If True, append signal explanation texts.
        include_aliases:  If True, append alias paragraph from semantic_aliases.json.

    Returns:
        A single string to pass to nomic-embed-text.
    """
    aliases = _load_aliases()

    pathway_id = card.get("causal_pathway", "")
    production_system = card.get("production_system", "")
    observed_stress = card.get("observed_stress", "")

    parts = []

    # Header
    parts.append(
        f"Production system: {production_system}. "
        f"Observed stress: {observed_stress.replace('_', ' ')}. "
        f"Causal pathway: {pathway_id.replace('_', ' ')}."
    )

    # Core reasoning note
    reasoning = card.get("overall_reasoning_note", "")
    if reasoning:
        parts.append(reasoning)

    # Signal explanations (domain vocabulary)
    if include_signals:
        for sig in card.get("diagnostic_signals", []):
            explanation = sig.get("explanation", "")
            if explanation:
                parts.append(explanation)

    # Context description
    ctx = card.get("context", {})
    aer_tags = ctx.get("agro_climatic_zones", [])
    aquifer_tags = ctx.get("aquifer_types", [])
    rainfall = ctx.get("rainfall_regime", "")
    geo = ctx.get("geographic_examples", [])
    if any([aer_tags, aquifer_tags, rainfall, geo]):
        ctx_text = (
            f"Context: {', '.join(aer_tags)} agro-ecological zones. "
            f"Aquifer: {', '.join(aquifer_tags)}. "
            f"Rainfall: {rainfall}. "
            f"Examples: {', '.join(geo)}."
        )
        parts.append(ctx_text)

    # Alias paragraph — broadens the embedding surface toward colloquial queries
    if include_aliases and pathway_id in aliases:
        alias_paragraph = "Related themes: " + ". ".join(aliases[pathway_id]) + "."
        parts.append(alias_paragraph)

    return "\n\n".join(parts)


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_text(text: str, model: str = "nomic-embed-text") -> list[float]:
    """
    Embed a single text string using Ollama's nomic-embed-text model.
    Returns a 768-dimensional float list.
    """
    response = ollama.embeddings(model=model, prompt=text)
    return response["embedding"]


def embed_card(card: dict, model: str = "nomic-embed-text") -> list[float]:
    """
    Build alias-augmented embedding text for a card and return its embedding.
    Call this during evidence card generation (preprocessing Step 4) before
    storing the card in MongoDB.
    """
    text = build_card_embedding_text(card)
    return embed_text(text, model=model)


def embed_query(query: str, model: str = "nomic-embed-text") -> list[float]:
    """
    Embed a raw user query string.
    Do NOT augment query text with aliases — asymmetry is the point.
    """
    # Light normalisation only: strip extra whitespace
    query = re.sub(r"\s+", " ", query).strip()
    return embed_text(query, model=model)


# ── MongoDB retrieval helper ──────────────────────────────────────────────────

def retrieve_cards(
    query_embedding: list[float],
    db,
    aquifer_class: Optional[str] = None,
    aer_code: Optional[str] = None,
    top_k: int = 5,
    reviewed_weight_boost: float = 1.5,
) -> list[dict]:
    """
    Retrieve top-k evidence cards from MongoDB using Atlas Vector Search.

    Args:
        query_embedding:     768-dim embedding of the user query.
        db:                  pymongo Database object for diagnosis_db.
        aquifer_class:       ACWADAM class name to pre-filter cards (optional).
        aer_code:            NBSS-LUP AER code to pre-filter cards (optional).
        top_k:               Number of cards to return.
        reviewed_weight_boost: Score multiplier for expert-reviewed cards.

    Returns:
        List of evidence card dicts, re-ranked with review boost applied.
    """
    # Build Atlas Vector Search pre-filter
    pre_filter: dict = {}
    if aquifer_class:
        pre_filter["context.aquifer_types"] = {"$in": [aquifer_class, "any"]}
    if aer_code:
        pre_filter["context.agro_climatic_zones"] = {"$in": [aer_code, "any"]}

    pipeline = [
        {
            "$vectorSearch": {
                "index": "evidence_card_vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": top_k * 10,   # oversample for re-ranking
                "limit": top_k * 3,
                **({"filter": pre_filter} if pre_filter else {}),
            }
        },
        {
            "$addFields": {
                "vector_score": {"$meta": "vectorSearchScore"},
            }
        },
        {
            "$addFields": {
                # Boost expert-reviewed cards
                "adjusted_score": {
                    "$cond": {
                        "if": {"$eq": ["$metadata.reviewed_by_expert", True]},
                        "then": {"$multiply": ["$vector_score", reviewed_weight_boost]},
                        "else": "$vector_score",
                    }
                }
            }
        },
        {"$sort": {"adjusted_score": -1}},
        {"$limit": top_k},
    ]

    return list(db.evidence_cards.aggregate(pipeline))


# ── Batch re-embedding (for updating existing cards) ─────────────────────────

def reembed_all_cards(db, model: str = "nomic-embed-text", dry_run: bool = False):
    """
    Re-embed all evidence cards in MongoDB with the current alias set.
    Run this whenever semantic_aliases.json is updated.

    Args:
        db:       pymongo Database object.
        dry_run:  If True, print what would be updated without writing.
    """
    cards = list(db.evidence_cards.find({}))
    print(f"Re-embedding {len(cards)} evidence cards...")
    updated = 0
    for card in cards:
        text = build_card_embedding_text(card)
        if dry_run:
            preview = text[:120].replace("\n", " ")
            print(f"  [{card['card_id']}] text preview: {preview}...")
            continue
        embedding = embed_text(text, model=model)
        db.evidence_cards.update_one(
            {"_id": card["_id"]},
            {"$set": {"embedding": embedding, "embedding_model": model,
                       "embedding_includes_aliases": True}}
        )
        updated += 1
    if not dry_run:
        print(f"Done. {updated} cards re-embedded.")


# ── Diagnostic: show what a query retrieves ───────────────────────────────────

def debug_retrieval(query: str, db, top_k: int = 5, **retrieve_kwargs):
    """
    Print retrieval results for a query. Useful for diagnosing mismatch.

    Example:
        from embed_utils import debug_retrieval
        debug_retrieval("social ecological stress restoration", db, top_k=5)
    """
    emb = embed_query(query)
    cards = retrieve_cards(emb, db, top_k=top_k, **retrieve_kwargs)
    print(f"\nQuery: '{query}'")
    print(f"Top {len(cards)} retrieved cards:")
    for i, card in enumerate(cards):
        score = card.get("adjusted_score", card.get("vector_score", "?"))
        print(f"  {i+1}. [{card.get('causal_pathway','?')}]  "
              f"score={score:.4f}  reviewed={card.get('metadata',{}).get('reviewed_by_expert', False)}")
