"""Build alias-augmented text for evidence card embeddings.

Embed (card_text + semantic aliases) at index time; embed raw user queries at query time.
Alias lists live in metadata/semantic_aliases.json (see scripts/reference/embed_utils.py).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_ALIASES_PATH = ROOT / "metadata" / "semantic_aliases.json"


@lru_cache(maxsize=1)
def _load_alias_data() -> dict:
    with SEMANTIC_ALIASES_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_semantic_aliases() -> dict[str, list[str]]:
    """Return pathway_id -> alias phrase list."""
    data = _load_alias_data()
    return {p["pathway_id"]: list(p.get("aliases") or []) for p in data.get("pathways", [])}


def aliases_for_pathway(pathway_id: str) -> list[str]:
    return list(load_semantic_aliases().get(pathway_id, []))


def format_alias_paragraph(aliases: list[str]) -> str:
    if not aliases:
        return ""
    return "Related themes: " + ". ".join(aliases) + "."


def legacy_card_embed_text(card: dict) -> str:
    """Pre-alias embedding text (reasoning note + signal explanations only)."""
    parts = [card.get("overall_reasoning_note", "")]
    for sig in card.get("diagnostic_signals", []):
        parts.append(sig.get("explanation", ""))
    return " ".join(p for p in parts if p)


def build_card_embedding_text(
    card: dict,
    *,
    include_signals: bool = True,
    include_context: bool = True,
    include_aliases: bool = True,
) -> str:
    """Build the full string passed to nomic-embed-text for an evidence card."""
    pathway_id = str(card.get("causal_pathway") or "")
    production_system = str(card.get("production_system") or "")
    observed_stress = str(card.get("observed_stress") or "")

    parts: list[str] = []

    parts.append(
        f"Production system: {production_system}. "
        f"Observed stress: {observed_stress.replace('_', ' ')}. "
        f"Causal pathway: {pathway_id.replace('_', ' ')}."
    )

    reasoning = card.get("overall_reasoning_note", "")
    if reasoning:
        parts.append(str(reasoning))

    if include_signals:
        for sig in card.get("diagnostic_signals", []):
            explanation = sig.get("explanation", "")
            if explanation:
                parts.append(str(explanation))

    if include_context:
        ctx = card.get("context") or {}
        aer_tags = ctx.get("agro_climatic_zones") or []
        aquifer_tags = ctx.get("aquifer_types") or []
        rainfall = ctx.get("rainfall_regime") or ""
        geo = ctx.get("geographic_examples") or []
        if any([aer_tags, aquifer_tags, rainfall, geo]):
            parts.append(
                f"Context: {', '.join(aer_tags)} agro-ecological zones. "
                f"Aquifer: {', '.join(aquifer_tags)}. "
                f"Rainfall: {rainfall}. "
                f"Examples: {', '.join(geo)}."
            )

    if include_aliases:
        aliases = aliases_for_pathway(pathway_id)
        alias_paragraph = format_alias_paragraph(aliases)
        if alias_paragraph:
            parts.append(alias_paragraph)

    return "\n\n".join(parts)


def card_embed_text(card: dict) -> str:
    """Default embedding text builder used by ingest/reload scripts."""
    return build_card_embedding_text(card)


def stamp_embedding_metadata(card: dict) -> None:
    """Record alias provenance on the card metadata dict (in-place)."""
    meta = card.setdefault("metadata", {})
    pathway_id = str(card.get("causal_pathway") or "")
    aliases = aliases_for_pathway(pathway_id)
    meta["embedding_includes_aliases"] = bool(aliases)
    meta["semantic_alias_count"] = len(aliases)
    meta["semantic_aliases_source"] = "metadata/semantic_aliases.json"
