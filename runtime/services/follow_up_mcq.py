"""MCQ follow-up payloads sourced from evidence card missing_variable_questions."""

from __future__ import annotations

from typing import Any

MCQ_TEMPLATES: dict[str, dict[str, Any]] = {
    "borewell_density": {
        "response_type": "mcq",
        "choices": [
            {
                "id": "few",
                "label": "Very few (fewer than 10 within 2–3 km)",
                "normalized": {"band": "low", "present": True},
            },
            {
                "id": "moderate",
                "label": "Moderate (10–50 within 2–3 km)",
                "normalized": {"band": "moderate", "present": True},
            },
            {
                "id": "many",
                "label": "More than 50 within 2–3 km",
                "normalized": {"band": "high", "present": True},
            },
        ],
    },
    "annual_well_depth_m": {
        "response_type": "mcq",
        "choices": [
            {
                "id": "stable",
                "label": "Well depth has stayed roughly the same (within ~1 m)",
                "normalized": {"trend": "stable", "present": True},
            },
            {
                "id": "deepening",
                "label": "Wells have deepened by more than 2–3 m in the last 5–10 years",
                "normalized": {"trend": "worsening", "present": True},
            },
            {
                "id": "failed",
                "label": "Springs or shallow wells have dried up permanently or for much longer",
                "normalized": {"trend": "worsening", "present": True, "band": "high"},
            },
        ],
    },
    "migrant_household_percent": {
        "response_type": "mcq",
        "choices": [
            {
                "id": "low",
                "label": "Very few households migrate seasonally (roughly under 10%)",
                "normalized": {"band": "low", "present": True},
            },
            {
                "id": "moderate",
                "label": "A moderate share migrate (roughly 10–30%)",
                "normalized": {"band": "moderate", "present": True},
            },
            {
                "id": "high",
                "label": "Many households migrate (roughly over 30%)",
                "normalized": {"band": "high", "present": True},
            },
        ],
    },
}


def _iter_question_entries(bundle_or_cards: dict[str, dict] | list[dict]):
    if isinstance(bundle_or_cards, list):
        for card in bundle_or_cards:
            if not isinstance(card, dict):
                continue
            for q in card.get("missing_variable_questions") or []:
                if isinstance(q, dict):
                    yield q
        return
    for data in bundle_or_cards.values():
        for q in (data or {}).get("missing_variable_questions") or []:
            if isinstance(q, dict):
                yield q


def _question_entry_for_variable(
    bundle_or_cards: dict[str, dict] | list[dict],
    variable: str,
) -> dict[str, Any] | None:
    var = str(variable or "").strip()
    if not var:
        return None
    for q in _iter_question_entries(bundle_or_cards):
        q_var = str(q.get("missing_variable") or q.get("variable") or "").strip()
        if q_var == var:
            return q
    return None


def follow_up_mcq_from_bundle(
    bundle: dict[str, dict],
    *,
    variable: str | None,
    question: str | None,
) -> dict[str, Any] | None:
    """Build UI MCQ payload when the card entry has response_type=mcq."""
    if not variable or not question:
        return None
    entry = _question_entry_for_variable(bundle, variable)
    if not entry:
        return None
    if str(entry.get("response_type") or "").lower() != "mcq":
        return None
    choices = []
    for choice in entry.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        choice_id = str(choice.get("id") or "").strip()
        label = str(choice.get("label") or "").strip()
        if not choice_id or not label:
            continue
        choices.append({"id": choice_id, "label": label})
    if not choices:
        return None
    return {
        "variable": variable,
        "question": question,
        "choices": choices,
    }


def normalized_answer_from_mcq_choice(
    bundle_or_cards: dict[str, dict] | list[dict],
    variable: str,
    choice_id: str,
) -> dict[str, Any] | None:
    """Resolve MCQ choice_id to injected-variable payload via card normalized block."""
    entry = _question_entry_for_variable(bundle_or_cards, variable)
    if not entry:
        return None
    choice_key = str(choice_id or "").strip()
    if not choice_key:
        return None
    for choice in entry.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        if str(choice.get("id") or "").strip() != choice_key:
            continue
        normalized = choice.get("normalized")
        if not isinstance(normalized, dict):
            return None
        out = dict(normalized)
        out["variable"] = variable
        out["raw"] = str(choice.get("label") or choice_key)
        out["choice_id"] = choice_key
        return out
    return None


def attach_follow_up_mcq(response: dict[str, Any], bundle: dict[str, dict]) -> dict[str, Any]:
    out = dict(response)
    out["follow_up_mcq"] = follow_up_mcq_from_bundle(
        bundle,
        variable=out.get("follow_up_variable"),
        question=out.get("follow_up_question"),
    )
    return out
