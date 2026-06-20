"""Follow-up MCQ template helpers for propagation and review."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def choice_fingerprint(choices: list) -> str:
    rows = []
    for choice in choices or []:
        if not isinstance(choice, dict):
            continue
        normalized = choice.get("normalized") or {}
        effects = choice.get("effects") or {}
        effect_rows = effects.get("signals") if isinstance(effects, dict) else None
        rows.append(
            {
                "id": choice.get("id"),
                "normalized": normalized,
                "effects": effect_rows or [],
            }
        )
    return json.dumps(rows, sort_keys=True, ensure_ascii=False)


def follow_up_fingerprint(question: dict) -> str:
    variable = str(question.get("missing_variable") or "")
    mode = str(question.get("question_mode") or "")
    return f"{variable}::{mode}::{choice_fingerprint(question.get('choices') or [])}"


def fingerprint_short(full_fingerprint: str) -> str:
    return hashlib.sha256(full_fingerprint.encode("utf-8")).hexdigest()[:12]


def choice_summary(question: dict) -> str:
    parts: list[str] = []
    for choice in question.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        signals = (choice.get("effects") or {}).get("signals") if isinstance(choice.get("effects"), dict) else None
        result = signals[0].get("result") if signals else None
        parts.append(f"{choice.get('id')}->{result}")
    return "; ".join(parts)


def choice_summary_from_map(summary_map: dict[str, bool | None]) -> str:
    return "; ".join(f"{choice_id}->{value}" for choice_id, value in summary_map.items())


def none_choice_ids_from_summary(summary_map: dict[str, bool | None]) -> list[str]:
    return [choice_id for choice_id, value in summary_map.items() if value is None]


def merge_choice_summary(
    base_map: dict[str, bool | None],
    overrides: dict[str, bool | None],
) -> dict[str, bool | None]:
    out = dict(base_map)
    for choice_id, value in overrides.items():
        if choice_id in out:
            out[choice_id] = value
    return out


def parse_choice_summary(text: str) -> dict[str, bool | None]:
    out: dict[str, bool | None] = {}
    for part in str(text or "").split(";"):
        part = part.strip()
        if not part or "->" not in part:
            continue
        choice_id, raw = part.split("->", 1)
        choice_id = choice_id.strip()
        raw = raw.strip()
        if raw == "None":
            out[choice_id] = None
        elif raw == "True":
            out[choice_id] = True
        elif raw == "False":
            out[choice_id] = False
    return out


def signal_ids_for_variable(card: dict, variable: str) -> list[str]:
    out: list[str] = []
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict) or signal.get("active") is False:
            continue
        vars_ = [str(v) for v in (signal.get("variables") or [])]
        if variable not in vars_:
            continue
        sig_id = str(signal.get("signal_id") or "").strip()
        if sig_id:
            out.append(sig_id)
    return out


def effects_for_result(card: dict, variable: str, result: bool) -> dict[str, Any]:
    signal_ids = signal_ids_for_variable(card, variable)
    if not signal_ids:
        return {}
    return {
        "signals": [{"signal_id": sig_id, "result": result} for sig_id in signal_ids],
    }


def apply_choice_summary_to_question(
    card: dict,
    question: dict,
    summary_map: dict[str, bool | None],
) -> int:
    """Apply parsed choice_summary effects to a question. Returns number of choices changed."""
    variable = str(question.get("missing_variable") or "")
    changes = 0
    for choice in question.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        choice_id = str(choice.get("id") or "")
        if choice_id not in summary_map:
            continue
        result = summary_map[choice_id]
        if result is None:
            if "effects" in choice:
                choice.pop("effects", None)
                changes += 1
            continue
        new_effects = effects_for_result(card, variable, result)
        if new_effects and choice.get("effects") != new_effects:
            choice["effects"] = new_effects
            changes += 1
        elif not new_effects and "effects" in choice:
            choice.pop("effects", None)
            changes += 1
    return changes


def sync_choices_from_template(
    *,
    target_card: dict,
    target_question: dict,
    template_question: dict,
    summary_map: dict[str, bool | None] | None = None,
) -> int:
    """Sync question_mode, normalized blocks, and effects from template onto target."""
    variable = str(target_question.get("missing_variable") or "")
    changes = 0
    if template_question.get("question_mode") and target_question.get("question_mode") != template_question.get(
        "question_mode"
    ):
        target_question["question_mode"] = template_question["question_mode"]
        changes += 1

    template_by_id = {
        str(c.get("id") or ""): c
        for c in (template_question.get("choices") or [])
        if isinstance(c, dict) and c.get("id")
    }
    summary_map = summary_map or parse_choice_summary(choice_summary(template_question))

    for choice in target_question.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        choice_id = str(choice.get("id") or "")
        template_choice = template_by_id.get(choice_id)
        if not template_choice:
            continue

        normalized = template_choice.get("normalized") or {}
        if choice.get("normalized") != normalized:
            choice["normalized"] = dict(normalized)
            changes += 1

    changes += apply_choice_summary_to_question(target_card, target_question, summary_map)
    return changes
