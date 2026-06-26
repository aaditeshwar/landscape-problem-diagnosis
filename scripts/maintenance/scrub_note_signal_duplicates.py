#!/usr/bin/env python3
"""Scrub duplicate or corrupted signal mentions in overall_reasoning_note (in-place)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap()

from lib.sig_note_labels import SIG_PAREN_RE, scrub_duplicate_signal_mentions  # noqa: E402

RAW = ROOT / "data" / "evidence_cards" / "raw"


def card_has_scrub_candidates(note: str) -> bool:
    text = str(note or "")
    if "). ..)" in text or "). …)" in text:
        return True
    if text.lower().count("amplifying signals") > 1:
        return True
    spans = [m.group(0).lower() for m in SIG_PAREN_RE.finditer(text)]
    return len(spans) != len(set(spans))


def scrub_cards(*, dry_run: bool = False, all_cards: bool = False) -> dict:
    updated: list[str] = []
    for path in sorted(RAW.glob("*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        old = str(card.get("overall_reasoning_note") or "")
        if not all_cards and not card_has_scrub_candidates(old):
            continue
        new = scrub_duplicate_signal_mentions(old)
        if new == old:
            continue
        updated.append(path.stem)
        if not dry_run:
            card["overall_reasoning_note"] = new
            path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"updated_count": len(updated), "updated": updated, "dry_run": dry_run}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all-cards", action="store_true")
    args = parser.parse_args()
    report = scrub_cards(dry_run=args.dry_run, all_cards=args.all_cards)
    print("=== Scrub duplicate signal mentions in notes ===")
    print(f"  Updated: {report['updated_count']}")
    for card_id in report["updated"][:20]:
        print(f"    - {card_id}")
    if report["updated_count"] > 20:
        print(f"    ... and {report['updated_count'] - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
