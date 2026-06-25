"""Shared evidence-card patch merge and diff helpers."""

from __future__ import annotations

import copy
import json
from typing import Any


def signal_expression(signal: dict[str, Any]) -> str:
    condition = signal.get("condition") or {}
    if isinstance(condition, dict):
        expr = condition.get("expression")
        if expr is not None:
            return str(expr)
    return str(signal.get("expression") or "")


def merge_signal_patches(card: dict[str, Any], partial_signals: list[dict[str, Any]]) -> None:
    signals = card.get("diagnostic_signals")
    if not isinstance(signals, list):
        return
    for partial in partial_signals:
        if not isinstance(partial, dict):
            continue
        signal_id = str(partial.get("signal_id") or "")
        if not signal_id:
            continue
        for index, raw in enumerate(signals):
            if not isinstance(raw, dict) or raw.get("signal_id") != signal_id:
                continue
            merged = copy.deepcopy(raw)
            for key, value in partial.items():
                if key == "condition" and isinstance(value, dict):
                    condition = dict(merged.get("condition") or {})
                    condition.update(value)
                    merged["condition"] = condition
                elif key != "signal_id":
                    merged[key] = copy.deepcopy(value)
            signals[index] = merged
            break


def apply_patch(card: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(card)
    if not patch:
        return out
    if "overall_reasoning_note" in patch:
        out["overall_reasoning_note"] = patch["overall_reasoning_note"]
    if "confirmation_policy" in patch:
        out["confirmation_policy"] = copy.deepcopy(patch["confirmation_policy"])
    partial_signals = patch.get("diagnostic_signals")
    if isinstance(partial_signals, list):
        merge_signal_patches(out, partial_signals)
    return out


def compute_triage_card_patch(
    raw_card: dict[str, Any],
    *,
    diagnostic_signals: list[dict[str, Any]],
    confirmation_policy: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a revise-cards-compatible patch and changed-field index."""
    patch: dict[str, Any] = {}
    changed: dict[str, Any] = {"signals": {}, "confirmation_policy": False}

    raw_signals: dict[str, dict[str, Any]] = {}
    for item in raw_card.get("diagnostic_signals") or []:
        if isinstance(item, dict) and item.get("signal_id"):
            raw_signals[str(item["signal_id"])] = item

    edited_by_id: dict[str, dict[str, Any]] = {}
    for item in diagnostic_signals:
        if isinstance(item, dict) and item.get("signal_id"):
            edited_by_id[str(item["signal_id"])] = item

    signal_patches: list[dict[str, Any]] = []
    for signal_id, edited in edited_by_id.items():
        original = raw_signals.get(signal_id)
        if not original:
            continue
        fields_changed: list[str] = []
        signal_patch: dict[str, Any] = {"signal_id": signal_id}

        if signal_expression(edited) != signal_expression(original):
            signal_patch["condition"] = {"expression": signal_expression(edited)}
            fields_changed.append("expression")

        edited_direction = str(edited.get("direction") or "")
        original_direction = str(original.get("direction") or "")
        if edited_direction != original_direction:
            signal_patch["direction"] = edited.get("direction")
            fields_changed.append("direction")

        edited_active = edited.get("active") is not False
        original_active = original.get("active") is not False
        if edited_active != original_active:
            signal_patch["active"] = edited_active
            fields_changed.append("active")

        if fields_changed:
            signal_patches.append(signal_patch)
            changed["signals"][signal_id] = fields_changed

    if signal_patches:
        patch["diagnostic_signals"] = signal_patches

    if confirmation_policy is not None:
        original_policy = raw_card.get("confirmation_policy") or {}
        if json.dumps(confirmation_policy, sort_keys=True) != json.dumps(original_policy, sort_keys=True):
            patch["confirmation_policy"] = copy.deepcopy(confirmation_policy)
            changed["confirmation_policy"] = True

    return patch, changed


def _signal_by_id(card: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in card.get("diagnostic_signals") or []:
        if isinstance(item, dict) and item.get("signal_id"):
            out[str(item["signal_id"])] = item
    return out


def _partial_signal_patch(signal_id: str, field: str, patch_signal: dict[str, Any]) -> dict[str, Any]:
    partial: dict[str, Any] = {"signal_id": signal_id}
    if field == "expression":
        condition = patch_signal.get("condition") if isinstance(patch_signal.get("condition"), dict) else {}
        expr = condition.get("expression")
        if expr is None:
            expr = patch_signal.get("expression")
        partial["condition"] = {"expression": expr}
    elif field in {"direction", "active"}:
        partial[field] = patch_signal.get(field)
    return {"diagnostic_signals": [partial]}


def build_triage_patch_findings(
    card_id: str,
    raw_card: dict[str, Any] | None,
    patch: dict[str, Any],
    changed_fields: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Convert triaging patch deltas into revise-cards finding rows."""
    if not raw_card or not patch or not changed_fields:
        return []

    raw_signals = _signal_by_id(raw_card)
    patch_signals = _signal_by_id(apply_patch(raw_card, patch))
    partial_by_id = {
        str(item.get("signal_id")): item
        for item in patch.get("diagnostic_signals") or []
        if isinstance(item, dict) and item.get("signal_id")
    }
    findings: list[dict[str, Any]] = []

    signal_changes = changed_fields.get("signals") or {}
    if isinstance(signal_changes, dict):
        for signal_id, fields in signal_changes.items():
            if isinstance(fields, list):
                field_list = [str(field) for field in fields]
            elif isinstance(fields, dict):
                field_list = [str(key) for key, enabled in fields.items() if enabled]
            else:
                continue

            original = raw_signals.get(signal_id, {})
            patched = patch_signals.get(signal_id, {})
            partial = partial_by_id.get(signal_id, {})

            for field in field_list:
                issue_id = f"triage-{signal_id}-{field}"
                if field == "expression":
                    current_value = signal_expression(original)
                    patched_value = signal_expression(patched)
                    field_path = f"diagnostic_signals[{signal_id}].condition.expression"
                    explanation = (
                        f"Triaging updated {signal_id} expression."
                        if current_value == patched_value
                        else f"Triaging changed {signal_id} expression from {current_value!r} to {patched_value!r}."
                    )
                elif field == "direction":
                    current_value = original.get("direction")
                    field_path = f"diagnostic_signals[{signal_id}].direction"
                    explanation = f"Triaging changed {signal_id} direction from {original.get('direction')!r} to {patched.get('direction')!r}."
                elif field == "active":
                    current_value = original.get("active", True)
                    field_path = f"diagnostic_signals[{signal_id}].active"
                    explanation = f"Triaging changed {signal_id} active from {original.get('active', True)!r} to {patched.get('active', True)!r}."
                else:
                    continue

                findings.append(
                    {
                        "issue_id": issue_id,
                        "dimension": "D1" if field != "confirmation_policy" else "D3",
                        "severity": "info",
                        "field_path": field_path,
                        "current_value": current_value,
                        "current_from_card": current_value,
                        "explanation": explanation,
                        "suggested_patch": _partial_signal_patch(signal_id, field, partial or patched),
                        "source": "triaging",
                    }
                )

    if changed_fields.get("confirmation_policy") and isinstance(patch.get("confirmation_policy"), dict):
        findings.append(
            {
                "issue_id": "triage-confirmation-policy",
                "dimension": "D3",
                "severity": "info",
                "field_path": "confirmation_policy",
                "current_value": raw_card.get("confirmation_policy"),
                "current_from_card": raw_card.get("confirmation_policy"),
                "explanation": "",
                "suggested_patch": {"confirmation_policy": patch.get("confirmation_policy")},
                "source": "triaging",
            }
        )

    return findings
