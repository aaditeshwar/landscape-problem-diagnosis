#!/usr/bin/env python3
"""Export reviewed policies by fingerprint and propagate to all matching raw cards."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
REVIEWED_BY_FP = ROOT / "metadata" / "reviewed_policy_by_fingerprint.json"

sys.path.insert(0, str(ROOT / "scripts"))
from lib.card_policy_utils import policy_fingerprint  # noqa: E402
from lib.policy_overrides import export_reviewed_by_fingerprint  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Only write metadata/reviewed_policy_by_fingerprint.json from raw cards",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write canonical policy onto every raw card sharing each fingerprint",
    )
    args = parser.parse_args()

    templates = export_reviewed_by_fingerprint(RAW_DIR)
    REVIEWED_BY_FP.parent.mkdir(parents=True, exist_ok=True)
    with REVIEWED_BY_FP.open("w", encoding="utf-8") as handle:
        json.dump(templates, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"Exported {len(templates)} reviewed policy template(s) to {REVIEWED_BY_FP}")

    if args.export_only or not args.apply:
        return 0

    updated = 0
    for path in sorted(RAW_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        fp = policy_fingerprint(card.get("confirmation_policy"))
        template = templates.get(fp or "")
        if not template:
            continue
        if card.get("confirmation_policy") == template:
            continue
        card["confirmation_policy"] = template
        with path.open("w", encoding="utf-8") as handle:
            json.dump(card, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        updated += 1

    print(f"Propagated templates to {updated} card(s) with drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
