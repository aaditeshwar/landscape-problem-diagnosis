#!/usr/bin/env python3
"""Set diagnostic_signals[].active=true on all raw evidence cards (archived one-off)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"


def main() -> int:
    if not RAW_DIR.is_dir():
        print(f"Missing directory: {RAW_DIR}", file=sys.stderr)
        return 1

    updated_files = 0
    updated_signals = 0
    for path in sorted(RAW_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for signal in data.get("diagnostic_signals") or []:
            if not isinstance(signal, dict):
                continue
            if signal.get("active") is not True:
                signal["active"] = True
                updated_signals += 1
                changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            updated_files += 1

    print(f"Updated {updated_signals} signals across {updated_files} files in {RAW_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
