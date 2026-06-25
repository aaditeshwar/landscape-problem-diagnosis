#!/usr/bin/env python3
"""Apply human-approved Claude review patches to raw evidence cards."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
BACKUP_DIR = RAW_DIR / ".backup_pre_claude_review"
PATCHES_PATH = ROOT / "reports" / "claude_review" / "suggested_patches.json"
DECISIONS_PATH = ROOT / "metadata" / "claude_review_decisions.json"
EDITED_PATCHES_PATH = ROOT / "metadata" / "claude_review_edited_patches.json"

COMPOSITE_SEP = "::"

sys.path.insert(0, str(ROOT / "scripts"))
from lib.expression_audit import validate_card_expressions  # noqa: E402


def composite_key(card_id: str, issue_id: str) -> str:
    return f"{card_id}{COMPOSITE_SEP}{issue_id}"


def set_by_path(obj: dict, field_path: str, value) -> None:
    """Apply value at a dotted path (supports list indices as integers)."""
    if not field_path or field_path == "(root)":
        raise ValueError("Cannot patch root without explicit merge logic")
    parts = field_path.split(".")
    cur = obj
    for part in parts[:-1]:
        if part.isdigit():
            cur = cur[int(part)]
        else:
            cur = cur.setdefault(part, {})
    last = parts[-1]
    if last.isdigit():
        cur[int(last)] = value
    else:
        cur[last] = value


def merge_patch(card: dict, patch: dict, field_path: str) -> None:
    if not patch:
        return
    if field_path and field_path in patch:
        set_by_path(card, field_path, patch[field_path])
        return
    for key, value in patch.items():
        if key in card and isinstance(card[key], dict) and isinstance(value, dict):
            card[key] = {**card[key], **value}
        else:
            card[key] = copy.deepcopy(value)


def load_decisions(path: Path, batch_id: str | None = None) -> tuple[dict[str, str], set[str]]:
    if not path.exists():
        return {}, set()
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}, set()

    out: dict[str, str] = {}
    finalized_cards: set[str] = set()

    if data.get("schema_version", 1) >= 2 and isinstance(data.get("batches"), dict):
        batches = data["batches"]
        selected = (
            {batch_id: batches[batch_id]}
            if batch_id and batch_id in batches
            else batches
        )
        for batch in selected.values():
            if not isinstance(batch, dict):
                continue
            card_status = batch.get("card_status") or {}
            if isinstance(card_status, dict):
                for card_id, entry in card_status.items():
                    if isinstance(entry, dict) and entry.get("status") == "finalized":
                        finalized_cards.add(str(card_id))
            decisions = batch.get("decisions") or {}
            if isinstance(decisions, dict):
                for key, decision in decisions.items():
                    if isinstance(decision, dict):
                        issue_decision = str(
                            decision.get("decision") or decision.get("status") or "reject"
                        )
                        card_id = str(decision.get("card_id") or "")
                        issue_id = str(decision.get("issue_id") or "")
                        if card_id and issue_id:
                            out[composite_key(card_id, issue_id)] = issue_decision
        return out, finalized_cards

    card_status = data.get("card_status") or {}
    if isinstance(card_status, dict):
        for card_id, entry in card_status.items():
            if isinstance(entry, dict) and entry.get("status") == "finalized":
                finalized_cards.add(str(card_id))

    decisions = data.get("decisions") or data
    if isinstance(decisions, dict):
        for key, decision in decisions.items():
            if key in {"schema_version", "card_status", "decisions", "review_batch_id"}:
                continue
            if isinstance(decision, str):
                out[str(key)] = decision
            elif isinstance(decision, dict):
                issue_decision = str(
                    decision.get("decision") or decision.get("status") or "reject"
                )
                card_id = str(decision.get("card_id") or "")
                issue_id = str(decision.get("issue_id") or "")
                if card_id and issue_id:
                    out[composite_key(card_id, issue_id)] = issue_decision
                else:
                    out[str(key)] = issue_decision
    return out, finalized_cards


def load_edited_patches(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}
    patches = data.get("patches") or {}
    if not isinstance(patches, dict):
        return {}
    return {str(key): value for key, value in patches.items() if isinstance(value, dict)}


def resolve_patch(
    card_id: str,
    issue_id: str,
    suggested_patch: dict | None,
    edited_patches: dict[str, dict],
) -> dict | None:
    key = composite_key(card_id, issue_id)
    edited = edited_patches.get(key)
    if isinstance(edited, dict) and edited.get("patch"):
        return edited["patch"]
    return suggested_patch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes only")
    parser.add_argument("--apply", action="store_true", help="Write patched cards to raw/")
    parser.add_argument("--patches", type=Path, default=PATCHES_PATH)
    parser.add_argument("--decisions", type=Path, default=DECISIONS_PATH)
    parser.add_argument("--edited-patches", type=Path, default=EDITED_PATCHES_PATH)
    parser.add_argument(
        "--include-unfinalized",
        action="store_true",
        help="Apply accept decisions even if the card was not finalized via /revise-cards",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        return 1

    if not args.patches.exists():
        print(f"Missing patches file: {args.patches}", file=sys.stderr)
        return 1

    with args.patches.open(encoding="utf-8") as handle:
        patches_by_card = json.load(handle)

    decisions, finalized_cards = load_decisions(args.decisions)
    edited_patches = load_edited_patches(args.edited_patches)

    planned = 0
    applied = 0
    skipped = 0

    for card_id, items in sorted(patches_by_card.items()):
        if not args.include_unfinalized and card_id not in finalized_cards:
            skipped += 1
            continue

        accepted = []
        for item in items:
            issue_id = str(item.get("issue_id") or "")
            key = composite_key(card_id, issue_id)
            legacy = decisions.get(issue_id)
            decision = decisions.get(key, legacy or "pending")
            if decision != "accept":
                continue
            patch = resolve_patch(
                card_id,
                issue_id,
                item.get("suggested_patch") or {},
                edited_patches,
            )
            accepted.append({**item, "resolved_patch": patch})

        if not accepted:
            skipped += 1
            continue

        card_path = RAW_DIR / f"{card_id}.json"
        if not card_path.exists():
            print(f"Missing card: {card_path}", file=sys.stderr)
            continue

        with card_path.open(encoding="utf-8") as handle:
            card = json.load(handle)

        for item in accepted:
            merge_patch(
                card,
                item.get("resolved_patch") or {},
                str(item.get("field_path") or ""),
            )
            planned += 1
            print(f"{'APPLY' if args.apply else 'PLAN'} {card_id} [{item.get('issue_id')}]")

        expr_errors = validate_card_expressions(card)
        if expr_errors:
            print(f"Expression validation failed for {card_id}:", file=sys.stderr)
            for err in expr_errors[:5]:
                print(f"  {err}", file=sys.stderr)
            return 1

        if args.apply:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_path = BACKUP_DIR / f"{card_id}.json"
            if not backup_path.exists():
                shutil.copy2(card_path, backup_path)
            card_path.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
            applied += 1

    print(
        f"Patches planned: {planned}  cards touched: {applied if args.apply else 'n/a (dry-run)'}  skipped cards: {skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
