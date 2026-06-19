#!/usr/bin/env python3
"""Derive draft confirmation_policy objects from evidence cards (report or apply)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
REPORT_DIR = ROOT / "reports"
PILOT_POLICIES = ROOT / "metadata" / "pilot_confirmation_policies.json"

sys.path.insert(0, str(ROOT / "scripts"))
from lib.card_policy_utils import derive_policy  # noqa: E402
from lib.policy_overrides import load_pilot_overrides, resolve_policy_for_card  # noqa: E402


def load_pilot_overrides_legacy() -> dict[str, dict]:
    return load_pilot_overrides()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write policies into raw card JSON files")
    parser.add_argument("--pilot-only", action="store_true", help="Only apply metadata/pilot_confirmation_policies.json")
    parser.add_argument("--force", action="store_true", help="Replace existing confirmation_policy when deriving")
    parser.add_argument("--card-id", action="append", help="Limit to specific card_id(s)")
    args = parser.parse_args()

    overrides = load_pilot_overrides_legacy()
    paths = sorted(RAW_DIR.glob("*.json"))
    if args.card_id:
        paths = [RAW_DIR / f"{cid}.json" for cid in args.card_id]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "confirmation_policy_review.csv"
    rows: list[dict[str, str]] = []
    updated = 0

    for path in paths:
        if not path.exists():
            print(f"Skip missing: {path}")
            continue
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        card_id = str(card.get("card_id") or path.stem)

        if args.pilot_only and card_id not in overrides:
            continue

        if card_id in overrides:
            policy = overrides[card_id]
            source = "pilot"
        elif reviewed := resolve_policy_for_card(card, card_id=card_id, pilot=overrides):
            policy = reviewed
            source = "reviewed"
        elif card.get("confirmation_policy") and not args.force:
            policy = card["confirmation_policy"]
            source = "existing"
        else:
            policy = derive_policy(card)
            source = "derived"

        rows.append(
            {
                "card_id": card_id,
                "source": source,
                "min_confirms_true": str((policy.get("confirm_when") or {}).get("min_confirms_true", "")),
                "primary_signals": ",".join(policy.get("primary_confirm_signals") or []),
                "policy_json": json.dumps(policy, ensure_ascii=False),
            }
        )

        if args.apply:
            should_write = (
                card_id in overrides
                or source == "reviewed"
                or not card.get("confirmation_policy")
                or args.force
            )
            if should_write:
                card["confirmation_policy"] = policy
                with path.open("w", encoding="utf-8") as handle:
                    json.dump(card, handle, indent=2, ensure_ascii=False)
                    handle.write("\n")
                updated += 1

    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["card_id", "source", "min_confirms_true", "primary_signals", "policy_json"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {report_path} ({len(rows)} rows)")
    if args.apply:
        print(f"Updated {updated} card(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
