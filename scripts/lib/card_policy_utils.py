"""Shared helpers for confirmation policy derivation, audit, and review catalogs."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SIG_REF_RE = re.compile(r"sig_(\d+)", re.IGNORECASE)
AT_LEAST_OF_RE = re.compile(
    r"at least (?:two|2|three|3) of[^:]*:\s*([^.;]+)",
    re.IGNORECASE,
)
TWO_OF_RE = re.compile(
    r"(?:two of|co-occur(?:ence)? of)\s+(?:the\s+)?(?:three|two|primary)?[^:]*:\s*([^.;]+)",
    re.IGNORECASE,
)
NON_PRIMARY_CONTEXT = re.compile(
    r"amplif|contextual|does not independently|do not independently|"
    r"not independently confirm|does not confirm|do not confirm|"
    r"secondary|supporting signal|intervention lever|intervention opportunit",
    re.IGNORECASE,
)


def canonical_sig_id(raw: str) -> str | None:
    match = SIG_REF_RE.search(str(raw or ""))
    if not match:
        return None
    return f"sig_{int(match.group(1)):02d}"


def signal_map(card: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        sig_id = str(signal.get("signal_id") or "").strip()
        if sig_id:
            out[sig_id] = signal
    return out


def confirm_signal_ids(card: dict) -> list[str]:
    out: list[str] = []
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict) or signal.get("active") is False:
            continue
        if str(signal.get("direction") or "") != "confirms":
            continue
        sig_id = str(signal.get("signal_id") or "").strip()
        if sig_id:
            out.append(sig_id)
    return out


def amplifier_signal_ids(card: dict) -> list[str]:
    out: list[str] = []
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict) or signal.get("active") is False:
            continue
        if str(signal.get("direction") or "") == "amplifies":
            sig_id = str(signal.get("signal_id") or "").strip()
            if sig_id:
                out.append(sig_id)
    return out


def _sig_ids_in_text(text: str, confirm_set: set[str]) -> list[str]:
    found: list[str] = []
    for match in SIG_REF_RE.finditer(text):
        sig_id = f"sig_{int(match.group(1)):02d}"
        if sig_id in confirm_set and sig_id not in found:
            found.append(sig_id)
    return found


def primary_signals_from_note(note: str, confirm_ids: list[str]) -> list[str]:
    """Extract primary confirm signal ids from note prose (best-effort)."""
    confirm_set = set(confirm_ids)
    note_text = str(note or "")
    note_l = note_text.lower()

    for pattern in (AT_LEAST_OF_RE, TWO_OF_RE):
        match = pattern.search(note_text)
        if match:
            clause = match.group(1)
            picked = _sig_ids_in_text(clause, confirm_set)
            if len(picked) >= 2:
                return picked

    excluded: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", note_text):
        if not sentence.strip():
            continue
        sigs = _sig_ids_in_text(sentence, confirm_set)
        if not sigs:
            continue
        if NON_PRIMARY_CONTEXT.search(sentence):
            excluded.update(sigs)

    mentioned: list[str] = []
    for match in SIG_REF_RE.finditer(note_text):
        sig_id = f"sig_{int(match.group(1)):02d}"
        if sig_id not in confirm_set or sig_id in excluded:
            continue
        if sig_id not in mentioned:
            mentioned.append(sig_id)

    if mentioned:
        return mentioned

    if "at least two" in note_l or "no single signal" in note_l:
        return list(confirm_ids)

    return list(confirm_ids)


def min_confirms_from_note(note: str) -> int:
    note_l = str(note or "").lower()
    if "at least three" in note_l or "at least 3" in note_l:
        return 3
    if (
        "at least two" in note_l
        or "at least 2" in note_l
        or "no single signal" in note_l
        or "two of" in note_l
        or "co-occur" in note_l
    ):
        return 2
    return 1


def policy_referenced_signal_ids(policy: dict | None) -> set[str]:
    """All signal ids explicitly named in confirmation_policy rules."""
    if not policy:
        return set()
    refs = set(policy_primary_set(policy))
    confirm_when = policy.get("confirm_when") or {}
    for signal_id in confirm_when.get("required_all") or []:
        if isinstance(signal_id, str) and signal_id.strip():
            refs.add(signal_id.strip())
    for groups in confirm_when.get("required_any") or []:
        if isinstance(groups, list):
            refs |= {str(s) for s in groups if str(s).strip()}
    for rule in policy.get("confidence_when") or []:
        if not isinstance(rule, dict):
            continue
        min_from = rule.get("min_from_set") or {}
        refs |= {str(s) for s in (min_from.get("signals") or []) if str(s).strip()}
    return refs


def unused_confirm_signals(card: dict) -> list[str]:
    """Active confirms-direction signals not explicitly referenced in confirmation_policy."""
    policy = card.get("confirmation_policy") or {}
    referenced = policy_referenced_signal_ids(policy)
    return [sig_id for sig_id in confirm_signal_ids(card) if sig_id not in referenced]


def policy_primary_set(policy: dict | None) -> set[str]:
    if not policy:
        return set()
    primary = set(policy.get("primary_confirm_signals") or [])
    confirm_when = policy.get("confirm_when") or {}
    min_from = confirm_when.get("min_from_set") or {}
    primary |= {str(s) for s in (min_from.get("signals") or []) if str(s).strip()}
    for group in confirm_when.get("required_all") or []:
        if isinstance(group, str):
            primary.add(group)
    for groups in confirm_when.get("required_any") or []:
        if isinstance(groups, list):
            primary |= {str(s) for s in groups if str(s).strip()}
    return primary


def derive_policy(card: dict) -> dict:
    note = str(card.get("overall_reasoning_note") or "")
    confirm_ids = confirm_signal_ids(card)
    primary = primary_signals_from_note(note, confirm_ids)
    min_confirms = min_confirms_from_note(note)

    effective_min = min_confirms
    if len(primary) >= 2 and effective_min < 2:
        effective_min = 2

    confirm_when: dict[str, Any] = {
        "min_confirms_true": effective_min,
        "amplifiers_do_not_confirm": True,
    }
    if len(primary) >= 2:
        confirm_when["min_from_set"] = {"signals": primary, "min": effective_min}
    elif len(primary) == 1 and min_confirms == 1:
        confirm_when["required_any"] = [[primary[0]]]
    elif effective_min >= 2 and confirm_ids:
        confirm_when["min_confirms_true"] = effective_min

    confidence_when: list[dict[str, Any]] = []
    if len(primary) >= 2:
        confidence_when.append(
            {
                "level": "high",
                "min_from_set": {"signals": primary, "min": min(effective_min, len(primary))},
                "min_high_severity_confirms": min(2, effective_min),
            }
        )
    else:
        confidence_when.append({"level": "high", "min_confirms_true": max(effective_min, 2)})
    confidence_when.extend(
        [
            {"level": "medium", "min_confirms_true": 1},
            {"level": "low", "default": True},
        ]
    )

    return {
        "version": 1,
        "primary_confirm_signals": primary,
        "confirm_when": confirm_when,
        "confidence_when": confidence_when,
    }


def draft_reasoning_note_from_policy(card: dict, policy: dict | None = None) -> str:
    """Generate concise prose from policy + signal metadata (for comparison with LLM note)."""
    policy = policy or card.get("confirmation_policy") or derive_policy(card)
    smap = signal_map(card)
    confirm_when = policy.get("confirm_when") or {}
    primary = list(policy.get("primary_confirm_signals") or [])
    min_confirms = int(confirm_when.get("min_confirms_true") or 1)
    min_from = confirm_when.get("min_from_set") or {}
    mfs_signals = list(min_from.get("signals") or [])
    mfs_min = int(min_from.get("min") or 0)
    required_all = [str(s) for s in (confirm_when.get("required_all") or []) if str(s).strip()]
    required_any = confirm_when.get("required_any") or []
    amplifiers = amplifier_signal_ids(card)

    def sig_label(sig_id: str) -> str:
        signal = smap.get(sig_id) or {}
        variables = ", ".join(signal.get("variables") or []) or sig_id
        return f"{sig_id} ({variables})"

    parts: list[str] = []
    pathway = card.get("causal_pathway") or card.get("card_id") or "this pathway"
    parts.append(f"Pathway {pathway} confirmation policy (auto-generated summary).")

    if mfs_signals and mfs_min >= 2:
        parts.append(
            f"Confirm when at least {mfs_min} of the primary signals co-occur: "
            + ", ".join(sig_label(s) for s in mfs_signals)
            + "."
        )
    elif mfs_signals and mfs_min == 1 and required_any:
        parts.append(
            "Confirm when any one of these primary signals is TRUE: "
            + ", ".join(sig_label(s) for s in mfs_signals)
            + "."
        )
    elif primary and min_confirms >= 2:
        parts.append(
            f"Confirm when at least {min_confirms} of the primary signals co-occur: "
            + ", ".join(sig_label(s) for s in primary)
            + "."
        )
    elif primary and len(primary) == 1:
        parts.append(f"Confirm when {sig_label(primary[0])} is TRUE.")
    elif primary:
        parts.append(
            f"Confirm when at least one of the primary signals is TRUE: "
            + ", ".join(sig_label(s) for s in primary)
            + "."
        )
    else:
        parts.append(f"Confirm when at least {min_confirms} confirming signal(s) are TRUE.")

    if required_all:
        parts.append(f"Required: {', '.join(sig_label(s) for s in required_all)} must be TRUE.")
    if required_any:
        any_labels: list[str] = []
        for group in required_any:
            if not isinstance(group, list):
                continue
            ids = [str(s) for s in group if str(s).strip()]
            if ids:
                any_labels.append(" + ".join(sig_label(s) for s in ids))
        if any_labels:
            parts.append("Additionally require at least one group: " + "; OR ".join(any_labels) + ".")

    if amplifiers:
        parts.append(
            "Amplifying signals (do not alone confirm): "
            + ", ".join(sig_label(s) for s in amplifiers)
            + "."
        )

    follow_ups = card.get("missing_variable_questions") or []
    if follow_ups:
        vars_ = [str(q.get("missing_variable") or "") for q in follow_ups[:3] if q.get("missing_variable")]
        if vars_:
            parts.append(f"Follow-up variables for field evidence: {', '.join(vars_)}.")

    return " ".join(parts)


def policy_fingerprint(policy: dict | None) -> str:
    blob = json.dumps(policy or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def expression_fingerprint(signal: dict) -> str:
    condition = signal.get("condition") or {}
    payload = {
        "type": condition.get("type"),
        "expression": condition.get("expression"),
        "qualitative_description": condition.get("qualitative_description"),
        "variables": signal.get("variables"),
        "direction": signal.get("direction"),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
