#!/usr/bin/env python3
"""Apply hand-reviewed confirmation_policy corrections by policy fingerprint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
CORRECTIONS = ROOT / "metadata" / "policy_corrections.json"
REVIEWED_BY_FP = ROOT / "metadata" / "reviewed_policy_by_fingerprint.json"
REPORT = ROOT / "reports" / "policy_corrections_review.md"

sys.path.insert(0, str(ROOT / "scripts"))
from lib.card_policy_utils import draft_reasoning_note_from_policy, policy_fingerprint  # noqa: E402
from lib.policy_overrides import export_reviewed_by_fingerprint  # noqa: E402


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def wrap_policy(body: dict) -> dict:
    return {"version": 1, **body}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Skip rebuilding metadata/reviewed_policy_by_fingerprint.json",
    )
    args = parser.parse_args()

    corrections = load_json(CORRECTIONS)
    corrections.pop("_comment", None)
    by_card_id = corrections.pop("by_card_id", {}) or {}

    updated = 0
    review_rows: list[dict[str, str]] = []

    for path in sorted(RAW_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        card_id = str(card.get("card_id") or path.stem)
        old_fp = policy_fingerprint(card.get("confirmation_policy"))

        body = by_card_id.get(card_id)
        source = f"card:{card_id}"
        if not body and old_fp in corrections:
            body = corrections[old_fp]
            source = old_fp
        if not body:
            continue
        new_policy = wrap_policy(body)
        card["confirmation_policy"] = new_policy

        review_rows.append(
            {
                "fingerprint": source,
                "card_id": card_id,
                "primary": ", ".join(new_policy.get("primary_confirm_signals") or []),
                "min_confirms": str((new_policy.get("confirm_when") or {}).get("min_confirms_true", "")),
                "min_from_set": json.dumps((new_policy.get("confirm_when") or {}).get("min_from_set"), ensure_ascii=False),
                "draft_note": draft_reasoning_note_from_policy(card, new_policy),
            }
        )

        if not args.dry_run:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(card, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
        updated += 1

    if not args.dry_run and not args.no_export:
        templates = export_reviewed_by_fingerprint(RAW_DIR)
        REVIEWED_BY_FP.parent.mkdir(parents=True, exist_ok=True)
        with REVIEWED_BY_FP.open("w", encoding="utf-8") as handle:
            json.dump(templates, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"Exported {len(templates)} template(s) to {REVIEWED_BY_FP}")

    lines = [
        "# Policy corrections review",
        "",
        f"Applied corrections to **{updated}** card(s) across **{len({r['fingerprint'] for r in review_rows})}** fingerprint(s).",
        "",
    ]
    current_fp = None
    for row in sorted(review_rows, key=lambda r: (r["fingerprint"], r["card_id"])):
        if row["fingerprint"] != current_fp:
            current_fp = row["fingerprint"]
            lines.extend(
                [
                    f"## `{current_fp}`",
                    "",
                    f"- **Primary signals:** {row['primary']}",
                    f"- **min_confirms_true:** {row['min_confirms']}",
                    f"- **min_from_set:** `{row['min_from_set']}`",
                    "",
                    "**Draft note:**",
                    "",
                    f"> {row['draft_note']}",
                    "",
                    "**Cards updated:**",
                    "",
                ]
            )
            fp_cards = [r["card_id"] for r in review_rows if r["fingerprint"] == current_fp]
            for cid in sorted(fp_cards):
                lines.append(f"- `{cid}`")
            lines.append("")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"{'Would update' if args.dry_run else 'Updated'} {updated} card(s)")
    print(f"Wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
