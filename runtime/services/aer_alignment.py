"""Classify evidence-card AER tags vs MWS AER and retrieval neighbor set."""

from __future__ import annotations


def classify_aer_alignment(
    card_aer_tags: list[str] | None,
    mws_aer: str | None,
    retrieval_aer_tags: list[str] | None,
) -> str:
    """Return exact | neighbor | mismatch | unknown."""
    tags = [str(t) for t in (card_aer_tags or []) if t]
    if not mws_aer or not tags:
        return "unknown"
    if mws_aer in tags:
        return "exact"
    retrieval = {str(t) for t in (retrieval_aer_tags or []) if t}
    if retrieval & set(tags):
        return "neighbor"
    return "mismatch"


def overlapping_retrieval_aer_tags(
    card_aer_tags: list[str] | None,
    retrieval_aer_tags: list[str] | None,
) -> list[str]:
    retrieval = {str(t) for t in (retrieval_aer_tags or []) if t}
    tags = [str(t) for t in (card_aer_tags or []) if t]
    return [t for t in tags if t in retrieval]
