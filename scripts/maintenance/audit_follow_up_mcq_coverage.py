#!/usr/bin/env python3
"""Report evidence-card follow-up variables missing MCQ wiring."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"


def main() -> int:
    missing_mcq: Counter[str] = Counter()
    has_mcq: Counter[str] = Counter()
    for path in sorted(RAW_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as fh:
            card = json.load(fh)
        for entry in card.get("missing_variable_questions") or []:
            if not isinstance(entry, dict):
                continue
            var = str(entry.get("missing_variable") or entry.get("variable") or "").strip()
            if not var:
                continue
            if str(entry.get("response_type") or "").lower() == "mcq" and entry.get("choices"):
                has_mcq[var] += 1
            else:
                missing_mcq[var] += 1

    print("Variables with MCQ:", len(has_mcq))
    for var, count in has_mcq.most_common():
        print(f"  {var}: {count}")
    print("\nVariables without MCQ:", len(missing_mcq))
    for var, count in missing_mcq.most_common(20):
        print(f"  {var}: {count}")
    if len(missing_mcq) > 20:
        print(f"  … and {len(missing_mcq) - 20} more variable names")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
