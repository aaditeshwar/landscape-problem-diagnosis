#!/usr/bin/env python3
"""Run Plan 15 deterministic preflight audits and index by card_id."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
BASELINE_DIR = ROOT / "reports" / "claude_review" / "baseline"
REPORTS_DIR = ROOT / "reports"
POLICY_REVIEW_DIR = REPORTS_DIR / "policy_review"
PYTHON = sys.executable

AUDIT_COMMANDS = [
    ["scripts/verify/audit_confirmation_policy.py", "--write-report"],
    ["scripts/verify/audit_follow_up_effects.py", "--write-report"],
    ["scripts/verify/audit_card_expressions.py", "--write-report"],
    ["scripts/verify/audit_card_schema.py", "--write-report"],
]

# (source path, baseline filename)
REPORT_SOURCES: list[tuple[Path, str]] = [
    (POLICY_REVIEW_DIR / "policy_audit.csv", "policy_audit.csv"),
    (POLICY_REVIEW_DIR / "policy_audit_summary.csv", "policy_audit_summary.csv"),
    (POLICY_REVIEW_DIR / "follow_up_effects_audit.csv", "follow_up_effects_audit.csv"),
    (REPORTS_DIR / "expression_audit.csv", "expression_audit.csv"),
    (REPORTS_DIR / "schema_audit.csv", "schema_audit.csv"),
]


def run_audit(relative_args: list[str]) -> int:
    cmd = [PYTHON, *[str(ROOT / relative_args[0]), *relative_args[1:]]]
    print(">", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def index_by_card(*file_pairs: tuple[str, Path]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for source, path in file_pairs:
        for row in load_csv_rows(path):
            card_id = str(row.get("card_id") or "").strip()
            if not card_id:
                continue
            entry = dict(row)
            entry["_source"] = source
            index[card_id].append(entry)
    return dict(index)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-audit-run",
        action="store_true",
        help="Only copy existing reports/ CSVs and rebuild index",
    )
    args = parser.parse_args()

    if not args.skip_audit_run:
        exit_code = 0
        for script_args in AUDIT_COMMANDS:
            code = run_audit(script_args)
            exit_code = max(exit_code, code)
        if exit_code:
            print("Warning: one or more audits reported issues (continuing to index)", file=sys.stderr)

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for src, filename in REPORT_SOURCES:
        if src.exists():
            dst = BASELINE_DIR / filename
            shutil.copy2(src, dst)
            copied.append(filename)

    file_pairs = [(name, BASELINE_DIR / name) for _, name in REPORT_SOURCES]
    preflight = index_by_card(*file_pairs)

    all_card_ids = sorted({p.stem for p in RAW_DIR.glob("*.json")})
    for card_id in all_card_ids:
        preflight.setdefault(card_id, [])

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "card_count": len(all_card_ids),
        "copied_reports": copied,
        "cards_with_issues": sum(1 for cid in all_card_ids if preflight.get(cid)),
    }
    (BASELINE_DIR / "preflight_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    (BASELINE_DIR / "preflight_by_card.json").write_text(
        json.dumps(preflight, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Baseline written to {BASELINE_DIR}")
    print(f"  cards: {len(all_card_ids)}  with preflight rows: {manifest['cards_with_issues']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
