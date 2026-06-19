#!/usr/bin/env python3
"""Write reports/POLICY_FIXES_FOR_REVIEW.md from applied corrections."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib.card_policy_utils import draft_reasoning_note_from_policy, policy_fingerprint  # noqa: E402

EXAMPLES = {
    "758bb14fc8d6bbf1": "agriculture__water_scarcity__drought__005",
    "514cea203f3ea5b0": "agriculture__water_scarcity__drought__002",
    "6b4cc36f5057475d": "agriculture__water_scarcity__groundwater_stress__003",
    "e8dc01684602bd98": "ntfp_forest_biodiversity__ntfp_decline__forest_degradation__003",
    "539b4853797aafb1": "agriculture__water_scarcity__rainfed_risk__007",
    "891d2f836d063a2a": "agriculture__water_scarcity__rainfed_risk__002",
    "7203d24bf55d2cc9": "socio_economic__low_income__small_landholding__012",
    "5e7b2cca017d1bdb": "agriculture__water_scarcity__rainfed_risk__008",
    "6803055bd44bd95e": "agriculture__water_scarcity__rainfed_risk__011",
    "6078765eee9d5c67": "agriculture__water_scarcity__rainfed_risk__012",
    "cdd74db78c08c69f": "agriculture__water_scarcity__rainfed_risk__005",
    "f6ed3f98aa2dd75e": "agriculture__water_scarcity__irrigation_challenges__004",
    "045266b712bf5319": "agriculture__water_scarcity__irrigation_challenges__012",
    "9cae31a0b8d701ad": "agriculture__water_scarcity__irrigation_challenges__005",
    "7058dec595e400a6": "agriculture__water_scarcity__irrigation_challenges__014",
    "1893d4cba2de282a": "ntfp_forest_biodiversity__ntfp_decline__encroachment__004",
    "b3a16ce03ca2017f": "ntfp_forest_biodiversity__ntfp_decline__encroachment__001",
    "9f3ae20f0f54b7c8": "ntfp_forest_biodiversity__ntfp_decline__encroachment__003",
    "9b0276448d48e4a4": "ntfp_forest_biodiversity__ntfp_decline__encroachment__010",
    "1105430c8b5be6df": "ntfp_forest_biodiversity__ntfp_decline__encroachment__014",
    "f8775f4def3a75aa": "ntfp_forest_biodiversity__ntfp_decline__encroachment__015",
    "bcf9ecea2b9f1039": "socio_economic__economic_hardship__multi_sector_vulnerability__011",
    "2dbc650b1490ddc7": "socio_economic__economic_hardship__multi_sector_vulnerability__015",
    "165dde27b2d7007e": "socio_economic__low_income__small_landholding__007",
    "579f0295a41c238a": "socio_economic__low_income__small_landholding__015",
}

ISSUES = {
    "758bb14fc8d6bbf1": "Issue 1: added min_from_set (2-of-4 drought signals)",
    "514cea203f3ea5b0": "Issues 1+2: primary sig_01/02/03 (not lone sig_04); min_from_set added",
    "6b4cc36f5057475d": "Issue 3: expanded from lone sig_03 to sig_01+02+05",
    "e8dc01684602bd98": "Issue 1: RS primary sig_01/02/03 min 2 (was lone sig_05)",
    "539b4853797aafb1": "Issue 4: min confirms 3 to 2 on sig_01/02/04",
    "891d2f836d063a2a": "Issue 5: added primary sig_01/02/03 with min_from_set",
    "7203d24bf55d2cc9": "Issue 3: sig_01 required plus sig_05 (sig_02/03 are amplifiers on this card)",
    "9b0276448d48e4a4": "Issue 2: kept sig_01 OR sig_04 rule; added min_from_set for draft clarity",
    "b3a16ce03ca2017f": "Issue 1: sig_01 required plus one of sig_03/sig_04 (min 2)",
}


def main() -> int:
    raw = json.loads((ROOT / "metadata" / "policy_corrections.json").read_text(encoding="utf-8"))
    raw.pop("_comment", None)
    by_card = raw.pop("by_card_id", {})

    lines = [
        "# Policy fixes for your review",
        "",
        "Applied **46 card updates** via `metadata/policy_corrections.json`.",
        "Old fingerprints changed; search the updated `review_unique_policies.csv` by **example card**.",
        "",
        "## Summary by your issue list",
        "",
        "| Issue | Fix applied |",
        "|-------|-------------|",
        "| 1 (missing min_from_set) | All listed rows now have `min_from_set` when primary set has 2+ signals |",
        "| 2 (draft note incomplete) | `draft_reasoning_note_from_policy` now lists all signals in min_from_set |",
        "| 3 (6b4cc36f, 7203d24bf55d2cc9) | GW Indo-Gangetic: sig_01/02/05; NE small holding: sig_01 + sig_05 |",
        "| 4 (539b4853797aafb1) | rainfed_risk__007: min 3 changed to min 2 |",
        "| 5 (891d2f836d063a2a) | rainfed_risk__002: primary sig_01/02/03 (same as rainfed cluster default) |",
        "",
    ]

    for old_fp, card_id in EXAMPLES.items():
        body = by_card.get(card_id) or raw.get(old_fp)
        if not body:
            continue
        card = json.loads((ROOT / "data" / "evidence_cards" / "raw" / f"{card_id}.json").read_text(encoding="utf-8"))
        policy = card.get("confirmation_policy") or {"version": 1, **body}
        new_fp = policy_fingerprint(policy)
        issue = ISSUES.get(old_fp, "Issues 1+2: min_from_set plus full primary list")
        lines.extend(
            [
                f"## `{old_fp}` (new `{new_fp}`)",
                "",
                f"- **Example card:** `{card_id}`",
                f"- **Issue addressed:** {issue}",
                f"- **Primary:** {', '.join(policy.get('primary_confirm_signals') or [])}",
                f"- **min_from_set:** `{json.dumps((policy.get('confirm_when') or {}).get('min_from_set'), ensure_ascii=False)}`",
                "",
                "**Draft note:**",
                "",
                f"> {draft_reasoning_note_from_policy(card, policy)}",
                "",
                "---",
                "",
            ]
        )

    out = ROOT / "reports" / "POLICY_FIXES_FOR_REVIEW.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
