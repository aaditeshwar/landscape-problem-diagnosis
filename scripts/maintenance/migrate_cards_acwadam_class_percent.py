#!/usr/bin/env python3
"""Replace aquifer_lithology_percent with acwadam_class_percent in evidence cards."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"

CARD_012_EXPRESSION = (
    "aquifer_class == 'himalayan_and_sub_himalayan' and "
    "acwadam_class_percent.get('crystalline_basement', 0) + "
    "acwadam_class_percent.get('sedimentary_hard_rock', 0) > 40"
)


def migrate_card(path: Path, *, dry_run: bool) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        card = json.load(handle)
    notes: list[str] = []
    card_id = str(card.get("card_id") or path.stem)
    text = json.dumps(card, ensure_ascii=False)
    if "aquifer_lithology_percent" not in text:
        return notes

    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        variables = signal.get("variables")
        if isinstance(variables, list):
            signal["variables"] = [
                "acwadam_class_percent" if v == "aquifer_lithology_percent" else v
                for v in variables
            ]
        condition = signal.get("condition")
        if isinstance(condition, dict) and isinstance(condition.get("expression"), str):
            expr = condition["expression"]
            if card_id.endswith("__012") and signal.get("signal_id") == "sig_01":
                if expr != CARD_012_EXPRESSION:
                    notes.append(f"{card_id}: rewrote sig_01 expression for ACWADAM keys")
                    condition["expression"] = CARD_012_EXPRESSION
            else:
                new_expr = expr.replace("aquifer_lithology_percent", "acwadam_class_percent")
                if new_expr != expr:
                    notes.append(f"{card_id}: {signal.get('signal_id')} expression variable rename")
                    condition["expression"] = new_expr

    if not dry_run:
        path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    notes.insert(0, f"{'Would update' if dry_run else 'Updated'} {path.name}")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pathway", default="", help="Limit to card_id prefix")
    args = parser.parse_args()

    paths = sorted(RAW_DIR.glob("*.json"))
    if args.pathway:
        paths = [p for p in paths if p.stem.startswith(args.pathway)]

    changed = 0
    for path in paths:
        notes = migrate_card(path, dry_run=args.dry_run)
        if len(notes) > 1 or (notes and "Would update" in notes[0]):
            changed += 1
            for note in notes:
                print(note)

    print(f"{'Would change' if args.dry_run else 'Changed'} {changed} card(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
