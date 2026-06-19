"""Structured pathway confirmation and confidence rules from evidence cards."""

from __future__ import annotations

from typing import Any

_HIGH_SEVERITIES = frozenset({"high", "critical"})
_MODERATE_OR_HIGH = frozenset({"moderate", "high", "critical"})


def card_from_bundle(bundle: dict[str, dict] | None, pathway_id: str) -> dict[str, Any]:
    if not bundle:
        return {}
    data = bundle.get(pathway_id) or {}
    return data.get("evidence_card") or {}


def policy_from_card(card: dict[str, Any] | None) -> dict[str, Any] | None:
    if not card:
        return None
    policy = card.get("confirmation_policy")
    return policy if isinstance(policy, dict) else None


def _signal_severity_map(card: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        sig_id = str(signal.get("signal_id") or "").strip()
        if sig_id:
            out[sig_id] = str(signal.get("severity") or "moderate").strip().lower()
    return out


def _true_confirm_ids(pathway_eval: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for signal in pathway_eval.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        if signal.get("direction") != "confirms":
            continue
        if signal.get("result") is not True:
            continue
        sig_id = str(signal.get("signal_id") or "").strip()
        if sig_id:
            ids.add(sig_id)
    return ids


def _count_severity_confirms(true_ids: set[str], severity_map: dict[str, str], *, severities: frozenset[str]) -> int:
    return sum(1 for sig_id in true_ids if severity_map.get(sig_id, "moderate") in severities)


def _min_from_set(true_ids: set[str], rule: dict[str, Any] | None) -> bool:
    if not rule:
        return True
    signals = [str(s) for s in (rule.get("signals") or []) if str(s).strip()]
    if not signals:
        return True
    minimum = int(rule.get("min") or 1)
    return len(true_ids & set(signals)) >= minimum


def _required_all(true_ids: set[str], required: list[Any] | None) -> bool:
    if not required:
        return True
    needed = {str(s).strip() for s in required if str(s).strip()}
    return needed.issubset(true_ids)


def _required_any(true_ids: set[str], groups: list[Any] | None) -> bool:
    """At least one group must be fully satisfied (all signals in group are TRUE)."""
    if not groups:
        return True
    for group in groups:
        if not isinstance(group, list):
            continue
        needed = {str(s).strip() for s in group if str(s).strip()}
        if needed and needed.issubset(true_ids):
            return True
    return False


def _evaluate_confirm_when(
    confirm_when: dict[str, Any],
    *,
    confirms_true: int,
    true_ids: set[str],
    severity_map: dict[str, str],
) -> bool:
    if confirms_true <= 0:
        return False

    min_confirms = confirm_when.get("min_confirms_true")
    if min_confirms is not None and confirms_true < int(min_confirms):
        return False

    if not _min_from_set(true_ids, confirm_when.get("min_from_set")):
        return False

    if not _required_all(true_ids, confirm_when.get("required_all")):
        return False

    if not _required_any(true_ids, confirm_when.get("required_any")):
        return False

    min_high = confirm_when.get("min_high_severity_confirms")
    if min_high is not None:
        if _count_severity_confirms(true_ids, severity_map, severities=_HIGH_SEVERITIES) < int(min_high):
            return False

    min_moderate = confirm_when.get("min_moderate_severity_confirms")
    if min_moderate is not None:
        if _count_severity_confirms(true_ids, severity_map, severities=_MODERATE_OR_HIGH) < int(min_moderate):
            return False

    return True


def _rule_matches(
    rule: dict[str, Any],
    *,
    confirms_true: int,
    true_ids: set[str],
    severity_map: dict[str, str],
) -> bool:
    if rule.get("default"):
        return True

    min_confirms = rule.get("min_confirms_true")
    if min_confirms is not None and confirms_true < int(min_confirms):
        return False

    if not _min_from_set(true_ids, rule.get("min_from_set")):
        return False

    min_high = rule.get("min_high_severity_confirms")
    if min_high is not None:
        if _count_severity_confirms(true_ids, severity_map, severities=_HIGH_SEVERITIES) < int(min_high):
            return False

    min_moderate = rule.get("min_moderate_severity_confirms")
    if min_moderate is not None:
        if _count_severity_confirms(true_ids, severity_map, severities=_MODERATE_OR_HIGH) < int(min_moderate):
            return False

    one_high_one_moderate = rule.get("min_one_high_one_moderate")
    if one_high_one_moderate:
        high = _count_severity_confirms(true_ids, severity_map, severities=_HIGH_SEVERITIES)
        moderate_only = _count_severity_confirms(true_ids, severity_map, severities=frozenset({"moderate"}))
        if high < 1 or moderate_only < 1:
            return False

    return True


def fallback_min_confirms_from_note(note: str) -> int:
    """Legacy keyword parse of overall_reasoning_note."""
    note_l = str(note or "").lower()
    if "no single signal is sufficient" in note_l:
        return 2
    if "at least three" in note_l or "at least 3" in note_l:
        return 3
    if "at least two" in note_l or "at least 2" in note_l:
        return 2
    if "plus one of" in note_l or "and one of" in note_l:
        return 2
    return 1


def pathway_is_confirmed(
    pathway_eval: dict[str, Any],
    card: dict[str, Any] | None,
    *,
    evidence_note: str = "",
) -> bool:
    """Return whether evaluation satisfies card confirmation rules."""
    summary = pathway_eval.get("summary") or {}
    confirms_true = int(summary.get("confirms_true") or 0)
    policy = policy_from_card(card)

    if not policy:
        return confirms_true >= 1

    confirm_when = policy.get("confirm_when") or {}
    true_ids = _true_confirm_ids(pathway_eval)
    severity_map = _signal_severity_map(card or {})
    return _evaluate_confirm_when(
        confirm_when,
        confirms_true=confirms_true,
        true_ids=true_ids,
        severity_map=severity_map,
    )


def pathway_confidence_level(
    pathway_eval: dict[str, Any],
    card: dict[str, Any] | None,
    *,
    evidence_note: str = "",
) -> str:
    """Return low | medium | high from policy or legacy note heuristics."""
    summary = pathway_eval.get("summary") or {}
    confirms_true = int(summary.get("confirms_true") or 0)
    if confirms_true <= 0:
        return "low"

    policy = policy_from_card(card)
    true_ids = _true_confirm_ids(pathway_eval)
    severity_map = _signal_severity_map(card or {})

    if policy:
        for rule in policy.get("confidence_when") or []:
            if not isinstance(rule, dict):
                continue
            if _rule_matches(
                rule,
                confirms_true=confirms_true,
                true_ids=true_ids,
                severity_map=severity_map,
            ):
                level = str(rule.get("level") or "medium").strip().lower()
                if level in {"low", "medium", "high"}:
                    return level
        return "medium"

    min_required = fallback_min_confirms_from_note(evidence_note)
    if confirms_true == 1:
        return "medium"
    if confirms_true >= min_required:
        return "high"
    return "medium"
