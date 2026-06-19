"""Resolve structured follow-up choice effects on evidence cards."""

from __future__ import annotations

from typing import Any


def question_entry_for_variable(card: dict[str, Any] | None, variable: str) -> dict[str, Any] | None:
    if not card or not variable:
        return None
    for question in card.get("missing_variable_questions") or []:
        if not isinstance(question, dict):
            continue
        var = str(question.get("missing_variable") or question.get("variable") or "").strip()
        if var == variable:
            return question
    return None


def choice_entry(question: dict[str, Any] | None, choice_id: str) -> dict[str, Any] | None:
    if not question or not choice_id:
        return None
    key = str(choice_id).strip()
    for choice in question.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        if str(choice.get("id") or "").strip() == key:
            return choice
    return None


def effect_result_for_signal(
    card: dict[str, Any] | None,
    *,
    variable: str,
    choice_id: str | None,
    signal_id: str,
) -> bool | None:
    """Return explicit TRUE/FALSE from choice effects when defined."""
    if not card or not variable or not choice_id or not signal_id:
        return None
    question = question_entry_for_variable(card, variable)
    selected = choice_entry(question, str(choice_id))
    if not selected:
        return None
    effects = selected.get("effects")
    if not isinstance(effects, dict):
        return None
    target = str(signal_id).strip()
    for row in effects.get("signals") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("signal_id") or "").strip() != target:
            continue
        result = row.get("result")
        if result is True:
            return True
        if result is False:
            return False
    return None
