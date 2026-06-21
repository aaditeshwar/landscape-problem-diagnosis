#!/usr/bin/env python3
"""Audit MCQ follow-up effects and variable/signal linkage."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "runtime"))
from lib.card_policy_utils import signal_map  # noqa: E402
from lib.policy_overrides import FOLLOW_UP_EFFECTS_AUDIT, POLICY_REVIEW_DIR  # noqa: E402
from services.follow_up_mcq import mcq_confirms_result  # noqa: E402


def signals_for_variable(card: dict, variable: str) -> list[str]:
    out: list[str] = []
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict) or signal.get("active") is False:
            continue
        vars_ = [str(v) for v in (signal.get("variables") or [])]
        if variable in vars_:
            sig_id = str(signal.get("signal_id") or "").strip()
            if sig_id:
                out.append(sig_id)
    return out


def audit_card(card: dict) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    card_id = str(card.get("card_id") or "")
    smap = signal_map(card)

    def add(code: str, detail: str, severity: str = "warn") -> None:
        issues.append({"card_id": card_id, "severity": severity, "code": code, "detail": detail})

    for question in card.get("missing_variable_questions") or []:
        if not isinstance(question, dict) or question.get("response_type") != "mcq":
            continue
        variable = str(question.get("missing_variable") or "").strip()
        if not variable:
            continue
        linked = signals_for_variable(card, variable)
        if not linked:
            add("no_signal_for_variable", f"{variable}: no active signal uses this variable", "error")

        for choice in question.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            choice_id = str(choice.get("id") or "?")
            effects = choice.get("effects") or {}
            signals = effects.get("signals") if isinstance(effects, dict) else None
            if not signals:
                add("missing_effects", f"{variable} choice {choice_id}: missing effects.signals", "error")
                continue

            for row in signals:
                if not isinstance(row, dict):
                    continue
                sig_id = str(row.get("signal_id") or "").strip()
                result = row.get("result")
                if result not in (True, False):
                    add("invalid_effect_result", f"{variable}/{choice_id}/{sig_id}: result must be boolean", "error")
                if sig_id not in smap:
                    add("unknown_effect_signal", f"{variable}/{choice_id}: unknown {sig_id}", "error")
                    continue
                if linked and sig_id not in linked:
                    add(
                        "effect_signal_variable_mismatch",
                        f"{variable}/{choice_id}: {sig_id} does not use {variable} (linked: {', '.join(linked)})",
                        "error",
                    )

            template_result = mcq_confirms_result(variable, choice_id)
            if template_result is not None and signals:
                for row in signals:
                    if not isinstance(row, dict):
                        continue
                    if row.get("result") != template_result and linked and row.get("signal_id") in linked:
                        add(
                            "template_effect_mismatch",
                            f"{variable}/{choice_id}: card effect {row.get('result')} != template {template_result}",
                        )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    all_issues: list[dict[str, str]] = []
    for path in sorted(RAW_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            all_issues.extend(audit_card(json.load(handle)))

    errors = [i for i in all_issues if i["severity"] == "error"]
    warns = [i for i in all_issues if i["severity"] != "error"]

    if args.write_report:
        POLICY_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with FOLLOW_UP_EFFECTS_AUDIT.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["card_id", "severity", "code", "detail"])
            writer.writeheader()
            writer.writerows(all_issues)

    for item in errors[:30]:
        print(f"ERROR {item['card_id']} [{item['code']}]: {item['detail']}", file=sys.stderr)
    if len(errors) > 30:
        print(f"... {len(errors) - 30} more errors", file=sys.stderr)

    print(f"follow-up effects audit: {len(errors)} error(s), {len(warns)} warning(s)")
    if errors:
        return 1
    if args.strict and warns:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
