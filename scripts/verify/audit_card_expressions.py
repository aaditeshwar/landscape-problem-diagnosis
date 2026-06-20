#!/usr/bin/env python3
"""Per-card expression audit CSV for evidence cards."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
REPORT_DIR = ROOT / "reports"

sys.path.insert(0, str(ROOT / "scripts"))
from lib.expression_audit import audit_card  # noqa: E402

CSV_FIELDS = ["card_id", "severity", "category", "signal_id", "detail", "expression"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true", help="Write reports/expression_audit.csv")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on BLOCKER/SHAPE/NESTED findings")
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    card_count = 0

    for path in sorted(RAW_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        card_count += 1
        for finding in audit_card(card):
            rows.append(
                {
                    "card_id": str(finding.get("card_id") or path.stem),
                    "severity": str(finding.get("severity") or ""),
                    "category": str(finding.get("category") or ""),
                    "signal_id": str(finding.get("signal_id") or ""),
                    "detail": str(finding.get("detail") or ""),
                    "expression": str(finding.get("expression") or "")[:240],
                }
            )

    blockers = [r for r in rows if r["severity"] in {"BLOCKER", "SHAPE", "NESTED"}]

    if args.write_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = REPORT_DIR / "expression_audit.csv"
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {out_path} ({len(rows)} row(s))")

    for row in blockers[:20]:
        print(
            f"{row['severity']} {row['card_id']} [{row['signal_id']}]: {row['detail']}",
            file=sys.stderr,
        )
    if len(blockers) > 20:
        print(f"... {len(blockers) - 20} more blocking finding(s)", file=sys.stderr)

    print(
        f"expression audit: {len(blockers)} blocking, {len(rows) - len(blockers)} other "
        f"across {card_count} cards"
    )
    if blockers and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
