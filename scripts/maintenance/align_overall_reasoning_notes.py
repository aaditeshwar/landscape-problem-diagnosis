#!/usr/bin/env python3
"""Align overall_reasoning_note opening prose with confirmation_policy (policy authoritative)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap()

from lib.card_policy_utils import amplifier_signal_ids, signal_map  # noqa: E402
from lib.sig_note_labels import scrub_duplicate_signal_mentions, sig_note_label  # noqa: E402
from verify.audit_confirmation_policy import audit_card  # noqa: E402

RAW = ROOT / "data" / "evidence_cards" / "raw"

TAIL_MARKERS = (
    r"(?i)\bDistinguish from\b",
    r"(?i)\bPrioritise\b",
    r"(?i)\bThe pathway is most severe\b",
    r"(?i)\bAlways probe\b",
    r"(?i)\bAlways verify\b",
    r"(?i)\bAlways distinguish\b",
    r"(?i)\bIf drought is recent\b",
    r"(?i)\bThe multi-sector nature\b",
    r"(?i)\bprovide structural context\b",
    r"(?i)\bstructural context rather than\b",
    r"(?i)\bThe key distinction\b",
    r"(?i)\bWhen rainfall is near-normal\b",
    r"(?i)\bThe composite signal\b",
    r"(?i)\bDiagnosis should require\b",
    r"(?i)\bThese two signals together\b",
    r"(?i)\bThe qualitative\b",
    r"(?i)\bRecommended interventions\b",
)


def sig_label(card: dict, sig_id: str) -> str:
    return sig_note_label(card, sig_id)


def _pathway_phrase(card: dict) -> str:
    pathway = str(card.get("causal_pathway") or "this pathway").replace("_", " ")
    return pathway


def policy_opening_prose(card: dict) -> str:
    policy = card.get("confirmation_policy") or {}
    if not policy:
        return ""
    confirm_when = policy.get("confirm_when") or {}
    primary = [str(s) for s in (policy.get("primary_confirm_signals") or []) if str(s).strip()]
    min_confirms = int(confirm_when.get("min_confirms_true") or 1)
    min_from = confirm_when.get("min_from_set") or {}
    mfs_signals = [str(s) for s in (min_from.get("signals") or []) if str(s).strip()]
    mfs_min = int(min_from.get("min") or 0)
    required_all = [str(s) for s in (confirm_when.get("required_all") or []) if str(s).strip()]
    required_any = confirm_when.get("required_any") or []

    parts: list[str] = []
    pathway = _pathway_phrase(card)

    if mfs_signals and mfs_min >= 2:
        labels = [sig_label(card, sig_id) for sig_id in mfs_signals]
        parts.append(
            f"Confirm {pathway} when at least {mfs_min} of the primary signals — "
            + ", ".join(labels)
            + " — co-occur."
        )
    elif required_any:
        groups: list[str] = []
        for group in required_any:
            if not isinstance(group, list):
                continue
            ids = [str(s) for s in group if str(s).strip()]
            if not ids:
                continue
            labels = [sig_label(card, sig_id) for sig_id in ids]
            if len(labels) == 1:
                groups.append(f"{labels[0]} is TRUE")
            elif len(labels) == 2:
                groups.append(f"{labels[0]} and {labels[1]} are TRUE")
            else:
                groups.append(", ".join(labels[:-1]) + f", and {labels[-1]} are TRUE")
        if groups:
            parts.append(
                f"Confirm {pathway} when at least one of these signal groups is satisfied: "
                + "; OR ".join(groups)
                + "."
            )
    elif primary and min_confirms >= 2:
        labels = [sig_label(card, sig_id) for sig_id in primary]
        parts.append(
            f"Confirm {pathway} when at least {min_confirms} of the primary signals — "
            + ", ".join(labels)
            + " — co-occur."
        )
    elif primary and len(primary) == 1:
        parts.append(f"Confirm {pathway} when {sig_label(card, primary[0])} is TRUE.")
    elif primary:
        labels = [sig_label(card, sig_id) for sig_id in primary]
        parts.append(
            f"Confirm {pathway} when at least one of the primary signals is TRUE: "
            + ", ".join(labels)
            + "."
        )
    else:
        parts.append(f"Confirm {pathway} when at least {min_confirms} confirming signal(s) are TRUE.")

    if required_all:
        labels = [sig_label(card, sig_id) for sig_id in required_all]
        parts.append(f"Required: {', '.join(labels)} must all be TRUE.")

    if required_any and mfs_signals:
        groups: list[str] = []
        for group in required_any:
            if not isinstance(group, list):
                continue
            ids = [str(s) for s in group if str(s).strip()]
            if not ids:
                continue
            labels = [sig_label(card, sig_id) for sig_id in ids]
            if len(labels) == 1:
                groups.append(f"{labels[0]} is TRUE")
            else:
                groups.append(", ".join(labels[:-1]) + f", and {labels[-1]} are TRUE")
        if groups:
            parts.append(
                "Additionally, at least one of these signal groups is satisfied: "
                + "; OR ".join(groups)
                + "."
            )

    amplifiers = amplifier_signal_ids(card)
    if amplifiers:
        amp_labels = [sig_label(card, sig_id) for sig_id in amplifiers]
        parts.append(
            "Amplifying signals (do not alone confirm): " + ", ".join(amp_labels) + "."
        )

    return " ".join(parts)


def extract_context_tail(note: str) -> str:
    text = str(note or "").strip()
    if not text:
        return ""
    for pattern in TAIL_MARKERS:
        match = re.search(pattern, text)
        if match:
            return text[match.start() :].strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if sentences and re.match(r"(?i)^Confirm ", sentences[0].strip()):
        if len(sentences) > 1:
            return " ".join(sentences[1:]).strip()
    return ""


def dedupe_amplifier_tail(opening: str, tail: str) -> str:
    if not tail:
        return tail
    if "amplifying signals" in opening.lower():
        trimmed = re.sub(
            r"^sig_\d+\s*\([^)]*\)\s*(?:amplif[^.]*\.\s*)+",
            "",
            tail,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
        if trimmed:
            tail = trimmed
    # Drop stale primary-list fragments left from old openings.
    tail = re.sub(
        r"^(?:sig_\d+\s*\([^)]*\),?\s*)+",
        "",
        tail,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    return tail


def clean_tail(tail: str) -> str:
    text = tail.strip()
    # Drop duplicate policy clauses already present in the rebuilt opening.
    text = re.sub(
        r"(?i)(?:Required:\s*sig_\d+\s*\([^)]*\)\s*must all be TRUE\.\s*)+",
        "",
        text,
    ).strip()
    text = re.sub(
        r"(?i)(?:Amplifying signals\s*\(do not alone confirm\):[^.]*\.\s*)+",
        "",
        text,
    ).strip()
    text = re.sub(
        r"(?i)^Confirmation requires at least (?:one|1|two|2|three|3)[^.]*\.\s*",
        "",
        text,
    ).strip()
    text = re.sub(r"\)\s*\.\.\)[^.]*\.", "", text).strip()
    text = re.sub(
        r"(?i)^(?:and\s+)?sig_\d+\s*\([^)]*\)\s*(?:serve|provides|amplif)[^.]*\.\s*",
        "",
        text,
    ).strip()
    for _ in range(3):
        trimmed = re.sub(
            r"^(?:does not independently confirm[^.]*\.\s*|"
            r"A single signal may reflect[^.]*\.\s*|"
            r"sig_\d+\s*\([^)]*\)\s*is the gold-standard[^.]*\.\s*)",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
        if trimmed == text:
            break
        text = trimmed
    return text


def align_note_text(card: dict) -> tuple[str, str]:
    old = str(card.get("overall_reasoning_note") or "").strip()
    opening = policy_opening_prose(card)
    if not opening:
        return old, "no_policy"
    tail = clean_tail(dedupe_amplifier_tail(opening, extract_context_tail(old)))
    new = opening if not tail else f"{opening} {tail}"
    new = scrub_duplicate_signal_mentions(new, opening=opening)
    new = re.sub(r"\s+", " ", new).strip()
    if new == old:
        return old, "already_aligned"
    return new, "updated"


def cards_with_policy_note_drift(raw_dir: Path = RAW) -> list[str]:
    card_ids: list[str] = []
    for path in sorted(raw_dir.glob("*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        codes = {issue["code"] for issue in audit_card(card)}
        if codes & {"policy_extra_primary", "stored_derive_drift", "min_confirms_mismatch"}:
            card_ids.append(path.stem)
    return card_ids


def align_cards(
    *,
    dry_run: bool = False,
    card_ids: set[str] | None = None,
    all_drift: bool = True,
) -> dict:
    targets = cards_with_policy_note_drift() if all_drift else sorted(p.stem for p in RAW.glob("*.json"))
    if card_ids:
        targets = [cid for cid in targets if cid in card_ids]

    updated: list[dict] = []
    skipped: list[dict] = []

    for card_id in targets:
        path = RAW / f"{card_id}.json"
        card = json.loads(path.read_text(encoding="utf-8"))
        new_note, status = align_note_text(card)
        if status != "updated":
            skipped.append({"card_id": card_id, "status": status})
            continue
        updated.append(
            {
                "card_id": card_id,
                "before": str(card.get("overall_reasoning_note") or "")[:240],
                "after": new_note[:240],
            }
        )
        if not dry_run:
            card["overall_reasoning_note"] = new_note
            path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "updated": updated,
        "skipped": skipped,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--card-id", action="append", dest="card_ids")
    parser.add_argument("--all-cards", action="store_true", help="Process every card, not only drift flags")
    args = parser.parse_args()

    report = align_cards(
        dry_run=args.dry_run,
        card_ids=set(args.card_ids) if args.card_ids else None,
        all_drift=not args.all_cards,
    )
    print("=== Align overall_reasoning_note from confirmation_policy ===")
    print(f"  Updated: {report['updated_count']}")
    print(f"  Skipped: {report['skipped_count']}")
    for row in report["updated"][:12]:
        print(f"    - {row['card_id']}")
    if report["updated_count"] > 12:
        print(f"    ... and {report['updated_count'] - 12} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
