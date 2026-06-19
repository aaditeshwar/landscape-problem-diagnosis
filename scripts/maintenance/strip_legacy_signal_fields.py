#!/usr/bin/env python3
"""Remove deprecated signal fields from evidence card JSON (not used by runtime)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"


def strip_card(card: dict) -> int:
    changes = 0
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        if "interaction_with" in signal:
            signal.pop("interaction_with", None)
            changes += 1
        condition = signal.get("condition")
        if isinstance(condition, dict):
            for key in ("threshold_confidence", "context_sensitivity"):
                if key in condition:
                    condition.pop(key, None)
                    changes += 1
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--card-id", help="Strip one card only")
    args = parser.parse_args()

    paths = sorted(RAW_DIR.glob("*.json"))
    if args.card_id:
        paths = [RAW_DIR / f"{args.card_id}.json"]

    total = 0
    for path in paths:
        if not path.exists():
            print(f"Missing: {path}")
            return 1
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        changes = strip_card(card)
        if changes:
            print(f"{card.get('card_id') or path.stem}: removed {changes} field(s)")
            total += changes
            if not args.dry_run:
                with path.open("w", encoding="utf-8") as handle:
                    json.dump(card, handle, indent=2, ensure_ascii=False)
                    handle.write("\n")

    print(f"Done. {total} deprecated field occurrence(s) {'would be ' if args.dry_run else ''}removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
