#!/usr/bin/env python3
"""Audit alignment between overall_reasoning_note and confirmation_policy."""

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
from lib.card_policy_utils import (  # noqa: E402
    amplifier_signal_ids,
    confirm_signal_ids,
    derive_policy,
    draft_reasoning_note_from_policy,
    min_confirms_from_note,
    policy_primary_set,
    primary_signals_from_note,
    signal_map,
)

POLICY_AUDIT_FIELDS = [
    "card_id",
    "severity",
    "code",
    "detail",
    "note_min_derived",
    "policy_min_confirms_true",
    "note_derived_primary",
    "policy_primary_signals",
    "stored_primary_signals",
    "derived_primary_signals",
    "confirm_signal_ids",
    "note_excerpt",
    "draft_note_from_policy",
    "confirmation_policy_json",
]


def load_pilot_card_ids() -> set[str]:
    if not PILOT_POLICIES.exists():
        return set()
    with PILOT_POLICIES.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return set(data.keys()) if isinstance(data, dict) else set()


def card_policy_context(card: dict, pilot_ids: set[str] | None = None) -> dict[str, str]:
    card_id = str(card.get("card_id") or "")
    note = str(card.get("overall_reasoning_note") or "")
    policy = card.get("confirmation_policy") or {}
    confirm_ids = confirm_signal_ids(card)
    note_primary = primary_signals_from_note(note, confirm_ids)
    policy_primary = sorted(policy_primary_set(policy))
    note_min = min_confirms_from_note(note)
    policy_min = int((policy.get("confirm_when") or {}).get("min_confirms_true") or 0)
    derived = derive_policy(card)
    derived_primary = sorted(derived.get("primary_confirm_signals") or [])
    stored_primary = sorted(policy.get("primary_confirm_signals") or [])
    draft = draft_reasoning_note_from_policy(card, policy)
    return {
        "card_id": card_id,
        "note_min_derived": str(note_min),
        "policy_min_confirms_true": str(policy_min),
        "note_derived_primary": ",".join(note_primary),
        "policy_primary_signals": ",".join(policy_primary),
        "stored_primary_signals": ",".join(stored_primary),
        "derived_primary_signals": ",".join(derived_primary),
        "confirm_signal_ids": ",".join(confirm_ids),
        "note_excerpt": note[:600].replace("\n", " "),
        "draft_note_from_policy": draft[:600].replace("\n", " "),
        "confirmation_policy_json": json.dumps(policy, ensure_ascii=False, separators=(",", ":")),
        "_pilot_exempt": str(card_id in (pilot_ids or set())),
    }


def audit_card(card: dict, pilot_ids: set[str] | None = None) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    ctx = card_policy_context(card, pilot_ids)
    card_id = ctx["card_id"]
    note = str(card.get("overall_reasoning_note") or "")
    policy = card.get("confirmation_policy") or {}
    confirm_ids = confirm_signal_ids(card)
    note_primary = set(primary_signals_from_note(note, confirm_ids))
    policy_primary = policy_primary_set(policy)
    smap = signal_map(card)

    note_min = int(ctx["note_min_derived"])
    policy_min = int(ctx["policy_min_confirms_true"] or 0)

    def add(code: str, detail: str, severity: str = "warn") -> None:
        row = {
            "severity": severity,
            "code": code,
            "detail": detail,
        }
        row.update({k: v for k, v in ctx.items() if not k.startswith("_")})
        issues.append(row)

    if not policy:
        add("missing_policy", "confirmation_policy absent", "error")
        return issues

    if note_min != policy_min and note.strip():
        add(
            "min_confirms_mismatch",
            f"note implies min {note_min}, policy has min_confirms_true={policy_min}",
        )

    extra_in_policy = sorted(policy_primary - note_primary)
    missing_in_policy = sorted(note_primary - policy_primary)
    if extra_in_policy:
        add(
            "policy_extra_primary",
            f"policy primary set includes {', '.join(extra_in_policy)} not in note-derived primary {sorted(note_primary)}",
        )
    if missing_in_policy and policy_primary:
        add(
            "policy_missing_primary",
            f"note-derived primary {sorted(missing_in_policy)} missing from policy primary {sorted(policy_primary)}",
        )

    for sig_id in sorted(policy_primary):
        signal = smap.get(sig_id) or {}
        if str(signal.get("direction") or "") == "amplifies":
            add("amplifier_in_policy_primary", f"{sig_id} is direction=amplifies but in policy primary set", "error")

    derived = derive_policy(card)
    derived_primary = set(derived.get("primary_confirm_signals") or [])
    if derived_primary != note_primary and note.strip():
        add(
            "derive_note_drift",
            f"re-derived primary {sorted(derived_primary)} vs note-derived {sorted(note_primary)}",
        )

    stored_primary = set(policy.get("primary_confirm_signals") or [])
    if stored_primary != derived_primary and card_id not in (pilot_ids or set()):
        add(
            "stored_derive_drift",
            f"stored primary {sorted(stored_primary)} vs fresh derive {sorted(derived_primary)}",
        )

    for sig_id in sorted(note_primary & set(amplifier_signal_ids(card))):
        add("note_primary_is_amplifier", f"{sig_id} in note primary but direction=amplifies", "error")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--write-report", action="store_true", help="Write reports/policy_audit.csv")
    args = parser.parse_args()

    pilot_ids = load_pilot_card_ids()
    all_issues: list[dict[str, str]] = []
    all_card_rows: list[dict[str, str]] = []

    for path in sorted(RAW_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        ctx = card_policy_context(card, pilot_ids)
        card_issues = audit_card(card, pilot_ids)
        all_issues.extend(card_issues)
        summary_row = dict(ctx)
        summary_row.pop("_pilot_exempt", None)
        summary_row["issue_count"] = str(len(card_issues))
        summary_row["issue_codes"] = ",".join(sorted({i["code"] for i in card_issues}))
        all_card_rows.append(summary_row)

    errors = [i for i in all_issues if i["severity"] == "error"]
    warns = [i for i in all_issues if i["severity"] != "error"]

    if args.write_report:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        with (REPORT_DIR / "policy_audit.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=POLICY_AUDIT_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_issues)
        summary_fields = [
            "card_id",
            "issue_count",
            "issue_codes",
            "note_min_derived",
            "policy_min_confirms_true",
            "note_derived_primary",
            "policy_primary_signals",
            "stored_primary_signals",
            "derived_primary_signals",
            "confirm_signal_ids",
            "note_excerpt",
            "draft_note_from_policy",
            "confirmation_policy_json",
        ]
        with (REPORT_DIR / "policy_audit_summary.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=summary_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_card_rows)
        print(f"Wrote {REPORT_DIR / 'policy_audit.csv'} ({len(all_issues)} issue row(s))")
        print(f"Wrote {REPORT_DIR / 'policy_audit_summary.csv'} ({len(all_card_rows)} card row(s))")

    for item in warns[:20]:
        print(f"WARN {item['card_id']} [{item['code']}]: {item['detail']}")
    if len(warns) > 20:
        print(f"... {len(warns) - 20} more warnings")

    for item in errors:
        print(f"ERROR {item['card_id']} [{item['code']}]: {item['detail']}", file=sys.stderr)

    print(f"policy audit: {len(errors)} error(s), {len(warns)} warning(s) across {len(all_card_rows)} cards")
    if errors:
        return 1
    if args.strict and warns:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
