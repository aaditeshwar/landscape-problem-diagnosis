#!/usr/bin/env python3
"""Audit evidence-card prompts for expression-rules block and JSON staleness."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap()

RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
AUDIT_DIR = ROOT / "data" / "audits"
EXPRESSION_RULES_MARKER = "Signal expression rules (CRITICAL"


def audit_prompts(raw_dir: Path = RAW_DIR) -> dict:
    missing_block: list[str] = []
    stale_json: list[str] = []
    no_json: list[str] = []

    for prompt_path in sorted(raw_dir.glob("*.prompt.txt")):
        card_id = prompt_path.stem.replace(".prompt", "")
        text = prompt_path.read_text(encoding="utf-8")
        json_path = raw_dir / f"{card_id}.json"

        if EXPRESSION_RULES_MARKER not in text:
            missing_block.append(card_id)

        if not json_path.exists():
            no_json.append(card_id)
        elif json_path.stat().st_mtime < prompt_path.stat().st_mtime:
            stale_json.append(card_id)

    need_regen = sorted(set(missing_block) | set(stale_json))
    stale_only = sorted(set(stale_json) - set(missing_block))

    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "raw_dir": str(raw_dir),
        "total_prompts": len(list(raw_dir.glob("*.prompt.txt"))),
        "missing_expression_rules_block": missing_block,
        "json_older_than_prompt": stale_json,
        "json_older_than_prompt_only": stale_only,
        "missing_json": no_json,
        "need_regeneration": need_regen,
        "counts": {
            "missing_block": len(missing_block),
            "stale_json": len(stale_json),
            "stale_only": len(stale_only),
            "need_regen": len(need_regen),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-list",
        type=Path,
        help="Write need_regeneration card_ids one per line",
    )
    parser.add_argument(
        "--write-report",
        type=Path,
        help="Write full audit JSON report",
    )
    args = parser.parse_args()

    report = audit_prompts()
    counts = report["counts"]
    print("=== Evidence card prompt audit ===")
    print(f"  Prompts scanned:              {report['total_prompts']}")
    print(f"  Missing expression-rules block: {counts['missing_block']}")
    print(f"  JSON older than prompt:       {counts['stale_json']} ({counts['stale_only']} with up-to-date prompts)")
    print(f"  Need regeneration:            {counts['need_regen']}")

    if report["missing_expression_rules_block"]:
        print("\nMissing expression-rules block:")
        for card_id in report["missing_expression_rules_block"]:
            print(f"  {card_id}")

    if report["json_older_than_prompt_only"]:
        print("\nStale JSON (prompt already has expression-rules block):")
        for card_id in report["json_older_than_prompt_only"]:
            print(f"  {card_id}")

    if args.write_list:
        args.write_list.parent.mkdir(parents=True, exist_ok=True)
        args.write_list.write_text("\n".join(report["need_regeneration"]) + "\n", encoding="utf-8")
        print(f"\nWrote card list: {args.write_list}")

    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote report: {args.write_report}")
    else:
        default_report = AUDIT_DIR / f"evidence_card_prompts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        default_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport: {default_report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
