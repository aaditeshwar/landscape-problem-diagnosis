"""Build follow-up exchange history from session turns (no DB imports)."""

from __future__ import annotations

from typing import Any


def build_follow_up_history(session: dict[str, Any], follow_up_count: int) -> list[dict[str, Any]]:
    turns = session.get("turns") or []
    if follow_up_count <= 0 or len(turns) < 2:
        return []

    history: list[dict[str, Any]] = []
    for turn_idx in range(1, min(follow_up_count + 1, len(turns))):
        prior = turns[turn_idx - 1]
        current = turns[turn_idx]
        prior_resp = prior.get("llm_response_json") or {}
        if not isinstance(prior_resp, dict):
            prior_resp = {}
        current_resp = current.get("llm_response_json") or {}
        if not isinstance(current_resp, dict):
            current_resp = {}

        entry: dict[str, Any] = {
            "question": str(prior_resp.get("follow_up_question") or ""),
            "answer": str(current.get("user_input") or ""),
            "variable": prior_resp.get("follow_up_variable"),
            "mcq": prior_resp.get("follow_up_mcq"),
        }
        history.append(entry)
    return history
