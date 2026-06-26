#!/usr/bin/env python3
"""Refresh claude_review_user_card_edits.json patches from current raw evidence cards.

Keeps each patch's shape (only fields the reviewer originally edited) but pulls
current values from the raw card so apply_user_card_edits.py is a no-op and
applied_card_digest reflects the live card state.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap()

from review.apply_user_card_edits import (  # noqa: E402
    EDITS_PATH,
    RAW_DIR,
    apply_patch,
    card_digest,
    iter_user_edits,
    utc_now_iso,
)


def _index_signals(card: dict) -> dict[str, dict]:
    return {
        str(sig.get("signal_id")): sig
        for sig in card.get("diagnostic_signals") or []
        if isinstance(sig, dict) and sig.get("signal_id")
    }


def _index_questions(card: dict) -> dict[str, dict]:
    return {
        str(q.get("missing_variable")): q
        for q in card.get("missing_variable_questions") or []
        if isinstance(q, dict) and q.get("missing_variable")
    }


def pull_patch_from_raw(raw_card: dict, patch: dict) -> dict:
    """Return a patch with the same keys/shape as patch but values from raw_card."""
    refreshed: dict = {}

    if "overall_reasoning_note" in patch:
        refreshed["overall_reasoning_note"] = raw_card.get("overall_reasoning_note", patch["overall_reasoning_note"])

    if "confirmation_policy" in patch:
        refreshed["confirmation_policy"] = copy.deepcopy(
            raw_card.get("confirmation_policy", patch["confirmation_policy"])
        )

    partial_signals = patch.get("diagnostic_signals")
    if isinstance(partial_signals, list):
        raw_signals = _index_signals(raw_card)
        refreshed_signals: list[dict] = []
        for partial in partial_signals:
            if not isinstance(partial, dict):
                continue
            signal_id = str(partial.get("signal_id") or "")
            raw_sig = raw_signals.get(signal_id)
            if not isinstance(raw_sig, dict):
                refreshed_signals.append(copy.deepcopy(partial))
                continue
            new_partial: dict = {"signal_id": signal_id}
            for key, template_value in partial.items():
                if key == "signal_id":
                    continue
                if key == "condition" and isinstance(template_value, dict):
                    raw_cond = raw_sig.get("condition") or {}
                    new_cond: dict = {}
                    for cond_key in template_value:
                        if cond_key in raw_cond:
                            new_cond[cond_key] = copy.deepcopy(raw_cond[cond_key])
                        else:
                            new_cond[cond_key] = copy.deepcopy(template_value[cond_key])
                    new_partial["condition"] = new_cond
                elif key in raw_sig:
                    new_partial[key] = copy.deepcopy(raw_sig[key])
                else:
                    new_partial[key] = copy.deepcopy(template_value)
            refreshed_signals.append(new_partial)
        refreshed["diagnostic_signals"] = refreshed_signals

    partial_questions = patch.get("missing_variable_questions")
    if isinstance(partial_questions, list):
        raw_questions = _index_questions(raw_card)
        refreshed_questions: list[dict] = []
        for partial in partial_questions:
            if not isinstance(partial, dict):
                continue
            key = str(partial.get("missing_variable") or "")
            raw_q = raw_questions.get(key)
            if not isinstance(raw_q, dict):
                refreshed_questions.append(copy.deepcopy(partial))
                continue
            new_q: dict = {}
            for field in partial:
                if field in raw_q:
                    new_q[field] = copy.deepcopy(raw_q[field])
                else:
                    new_q[field] = copy.deepcopy(partial[field])
            refreshed_questions.append(new_q)
        refreshed["missing_variable_questions"] = refreshed_questions

    return refreshed


def sync_patches_from_raw(
    *,
    dry_run: bool = False,
    batch_id: str | None = None,
    card_ids: set[str] | None = None,
) -> dict:
    if not EDITS_PATH.exists():
        return {"updated": [], "skipped": [], "missing_raw": [], "dry_run": dry_run}

    doc = json.loads(EDITS_PATH.read_text(encoding="utf-8"))
    updated: list[str] = []
    skipped: list[str] = []
    missing_raw: list[str] = []
    details: dict[str, list[str]] = {}
    now = utc_now_iso()

    for source_batch, card_id, entry in iter_user_edits(doc, batch_id):
        if card_ids and card_id not in card_ids:
            continue
        if not isinstance(entry, dict):
            continue
        patch = entry.get("patch")
        if not isinstance(patch, dict) or not patch:
            skipped.append(card_id)
            continue

        raw_path = RAW_DIR / f"{card_id}.json"
        if not raw_path.exists():
            missing_raw.append(card_id)
            continue

        raw_card = json.loads(raw_path.read_text(encoding="utf-8"))
        refreshed_patch = pull_patch_from_raw(raw_card, patch)
        probe = copy.deepcopy(raw_card)
        apply_patch(probe, refreshed_patch)
        synced_digest = card_digest(probe)

        needs_patch_refresh = refreshed_patch != patch
        needs_digest_refresh = str(entry.get("applied_card_digest") or "") != synced_digest

        if not (needs_patch_refresh or needs_digest_refresh):
            skipped.append(card_id)
            continue

        if card_digest(probe) != card_digest(raw_card):
            details.setdefault(card_id, []).append(
                "WARN: refreshed patch would change raw card"
            )

        updated.append(card_id)
        entry_notes: list[str] = []
        if needs_patch_refresh:
            entry_notes.append("patch fields refreshed from raw")
        if needs_digest_refresh:
            entry_notes.append("applied_card_digest updated")
        details[card_id] = entry_notes

        if not dry_run:
            entry["patch"] = refreshed_patch
            entry["applied_card_digest"] = synced_digest
            if not entry.get("propagated_at"):
                entry["propagated_at"] = now

    if updated and not dry_run:
        EDITS_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "updated": updated,
        "updated_count": len(updated),
        "skipped": skipped,
        "missing_raw": missing_raw,
        "details": details,
        "dry_run": dry_run,
        "batch_id": batch_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-id", help="Limit to one revise-cards batch")
    parser.add_argument("--card-id", action="append", dest="card_ids")
    args = parser.parse_args()

    report = sync_patches_from_raw(
        dry_run=args.dry_run,
        batch_id=args.batch_id,
        card_ids=set(args.card_ids) if args.card_ids else None,
    )
    print("=== Sync user edit patches from raw cards ===")
    print(f"  Updated: {report['updated_count']}")
    print(f"  Skipped (already aligned): {len(report['skipped'])}")
    if report["missing_raw"]:
        print(f"  Missing raw cards: {len(report['missing_raw'])}")
    for card_id in report["updated"][:25]:
        print(f"    - {card_id}: {', '.join(report['details'].get(card_id, []))}")
    if report["updated_count"] > 25:
        print(f"    ... and {report['updated_count'] - 25} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
