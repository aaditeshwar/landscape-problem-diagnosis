#!/usr/bin/env python3
"""Apply human-authored card edits from the revise-cards direct editor."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
BACKUP_DIR = RAW_DIR / ".backup_pre_user_card_edits"
EDITS_PATH = ROOT / "metadata" / "claude_review_user_card_edits.json"
DECISIONS_PATH = ROOT / "metadata" / "claude_review_decisions.json"

sys.path.insert(0, str(ROOT / "scripts"))
from lib.expression_audit import validate_card_expressions  # noqa: E402


def load_finalized_card_ids(batch_id: str | None = None) -> set[str]:
    if not DECISIONS_PATH.exists():
        return set()
    with DECISIONS_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)

    finalized: set[str] = set()
    if data.get("schema_version", 1) >= 2 and isinstance(data.get("batches"), dict):
        batches = data["batches"]
        selected = {batch_id: batches[batch_id]} if batch_id and batch_id in batches else batches
        for batch in selected.values():
            if not isinstance(batch, dict):
                continue
            card_status = batch.get("card_status") or {}
            for card_id, entry in card_status.items():
                if isinstance(entry, dict) and entry.get("status") == "finalized":
                    finalized.add(str(card_id))
        return finalized

    card_status = data.get("card_status") or {}
    return {
        str(card_id)
        for card_id, entry in card_status.items()
        if isinstance(entry, dict) and entry.get("status") == "finalized"
    }


def iter_user_edits(doc: dict, batch_id: str | None = None):
    if doc.get("schema_version", 1) >= 2 and isinstance(doc.get("batches"), dict):
        batches = doc["batches"]
        items = (
            [(batch_id, batches[batch_id])]
            if batch_id and batch_id in batches
            else list(batches.items())
        )
        for bid, batch in items:
            if not isinstance(batch, dict):
                continue
            edits = batch.get("edits") or {}
            if not isinstance(edits, dict):
                continue
            for card_id, entry in edits.items():
                yield str(bid), str(card_id), entry
        return

    edits = doc.get("edits") or {}
    if isinstance(edits, dict):
        for card_id, entry in edits.items():
            yield None, str(card_id), entry


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def card_digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def merge_signal_patches(card: dict, partial_signals: list[dict]) -> None:
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


def merge_follow_up_patches(card: dict, partial_questions: list[dict]) -> None:
    questions = card.get("missing_variable_questions")
    if not isinstance(questions, list):
        questions = []
        card["missing_variable_questions"] = questions
    for partial in partial_questions:
        if not isinstance(partial, dict):
            continue
        key = str(partial.get("missing_variable") or "")
        if not key:
            continue
        for index, raw in enumerate(questions):
            if not isinstance(raw, dict):
                continue
            if str(raw.get("missing_variable") or "") != key:
                continue
            merged = copy.deepcopy(raw)
            for field, value in partial.items():
                merged[field] = copy.deepcopy(value)
            questions[index] = merged
            break
        else:
            questions.append(copy.deepcopy(partial))


def apply_patch(card: dict, patch: dict) -> None:
    if not patch:
        return
    if "overall_reasoning_note" in patch:
        card["overall_reasoning_note"] = patch["overall_reasoning_note"]
    if "confirmation_policy" in patch:
        card["confirmation_policy"] = copy.deepcopy(patch["confirmation_policy"])
    partial_signals = patch.get("diagnostic_signals")
    if isinstance(partial_signals, list):
        merge_signal_patches(card, partial_signals)
    partial_questions = patch.get("missing_variable_questions")
    if isinstance(partial_questions, list):
        merge_follow_up_patches(card, partial_questions)


def sync_status(raw_card: dict, entry: dict, patch: dict) -> tuple[bool, str]:
    """Return whether raw card already reflects this edit (no file write needed)."""
    raw_digest = card_digest(raw_card)
    patched = copy.deepcopy(raw_card)
    apply_patch(patched, patch)
    if card_digest(patched) != raw_digest:
        return False, ""

    propagated_at = entry.get("propagated_at")
    applied_digest = str(entry.get("applied_card_digest") or "")
    if propagated_at and applied_digest and applied_digest == raw_digest:
        return True, f"already in sync (propagated {propagated_at})"
    return True, "raw card already matches edit"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--card-id", action="append", dest="card_ids")
    parser.add_argument("--batch-id", dest="batch_id", help="Apply edits from one revise-cards batch only")
    parser.add_argument("--include-unfinalized", action="store_true")
    args = parser.parse_args()

    if not EDITS_PATH.exists():
        print(f"No user card edits at {EDITS_PATH}")
        return 0

    with EDITS_PATH.open(encoding="utf-8") as handle:
        doc = json.load(handle)

    edit_rows = list(iter_user_edits(doc, args.batch_id))
    if not edit_rows:
        print("No user card edits to apply.")
        return 0

    finalized = load_finalized_card_ids(args.batch_id)
    selected = set(args.card_ids or [])
    applied = 0
    skipped = 0
    metadata_updated = False

    now = utc_now_iso()
    for source_batch, card_id, entry in edit_rows:
        if selected and card_id not in selected:
            continue
        if not args.include_unfinalized and card_id not in finalized:
            label = f"{source_batch}:" if source_batch else ""
            print(f"SKIP {label}{card_id} (not finalized in batch)")
            skipped += 1
            continue
        if not isinstance(entry, dict):
            continue
        patch = entry.get("patch")
        if not isinstance(patch, dict) or not patch:
            continue

        path = RAW_DIR / f"{card_id}.json"
        if not path.exists():
            print(f"MISSING {card_id}")
            skipped += 1
            continue

        with path.open(encoding="utf-8") as handle:
            raw_card = json.load(handle)

        in_sync, sync_reason = sync_status(raw_card, entry, patch)
        if in_sync:
            print(f"SKIP {card_id} ({sync_reason})")
            if not args.dry_run and not entry.get("propagated_at"):
                entry["propagated_at"] = now
                entry["applied_card_digest"] = card_digest(raw_card)
                metadata_updated = True
            skipped += 1
            continue

        card = copy.deepcopy(raw_card)
        apply_patch(card, patch)
        updated_digest = card_digest(card)

        notes = validate_card_expressions(card)
        if notes:
            print(f"WARN {card_id}: expression audit reported {len(notes)} note(s)")

        if args.dry_run:
            print(f"DRY-RUN would apply user edit to {card_id}")
        else:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / path.name
            if not backup.exists():
                shutil.copy2(path, backup)
            path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            entry["propagated_at"] = now
            entry["applied_card_digest"] = updated_digest
            metadata_updated = True
            print(f"APPLIED user edit to {card_id}")
        applied += 1

    if metadata_updated and not args.dry_run:
        doc["schema_version"] = doc.get("schema_version", 2)
        EDITS_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Done: applied={applied} skipped={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
