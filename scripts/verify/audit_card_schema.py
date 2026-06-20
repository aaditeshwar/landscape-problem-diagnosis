#!/usr/bin/env python3
"""JSON Schema validate all raw evidence cards."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
META = ROOT / "metadata"
REPORT_DIR = ROOT / "reports"

CSV_FIELDS = ["card_id", "severity", "code", "detail", "json_path"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true", help="Write reports/schema_audit.csv")
    args = parser.parse_args()

    schema_path = META / "evidence_card_schema.json"
    with schema_path.open(encoding="utf-8") as handle:
        schema = json.load(handle)

    rows: list[dict[str, str]] = []
    card_count = 0

    for path in sorted(RAW_DIR.glob("*.json")):
        card_count += 1
        card_id = path.stem
        try:
            with path.open(encoding="utf-8") as handle:
                card = json.load(handle)
            card_id = str(card.get("card_id") or card_id)
            jsonschema.validate(card, schema)
        except json.JSONDecodeError as exc:
            rows.append(
                {
                    "card_id": card_id,
                    "severity": "error",
                    "code": "invalid_json",
                    "detail": str(exc),
                    "json_path": "",
                }
            )
        except jsonschema.ValidationError as exc:
            json_path = ".".join(str(p) for p in exc.absolute_path) or "(root)"
            rows.append(
                {
                    "card_id": card_id,
                    "severity": "error",
                    "code": "schema_validation",
                    "detail": exc.message,
                    "json_path": json_path,
                }
            )

    errors = [r for r in rows if r["severity"] == "error"]

    if args.write_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = REPORT_DIR / "schema_audit.csv"
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {out_path} ({len(rows)} row(s))")

    for row in errors[:20]:
        print(f"ERROR {row['card_id']} [{row['code']}]: {row['detail']}", file=sys.stderr)
    if len(errors) > 20:
        print(f"... {len(errors) - 20} more error(s)", file=sys.stderr)

    print(f"schema audit: {len(errors)} error(s) across {card_count} cards")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
