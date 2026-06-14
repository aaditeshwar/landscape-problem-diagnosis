#!/usr/bin/env python3
"""Evaluate every evidence-card signal expression against every case-study MWS export."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.signal_evaluator import (  # noqa: E402
    build_eval_context_from_export,
    classify_eval_error,
    evaluate_expression,
    merge_export_variables,
    missing_context_keys,
)

RAW_JSONS = ROOT / "data" / "raw_jsons"
RAW_CARDS = ROOT / "data" / "evidence_cards" / "raw"
AUDIT_DIR = ROOT / "data" / "audits"


def load_exports(export_dir: Path = RAW_JSONS) -> dict[str, dict]:
    exports: dict[str, dict] = {}
    for path in sorted(export_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        uid = payload.get("uid") or path.stem
        exports[str(uid)] = payload
    return exports


def load_cards(card_dir: Path = RAW_CARDS) -> list[dict]:
    cards: list[dict] = []
    for path in sorted(card_dir.glob("*.json")):
        cards.append(json.loads(path.read_text(encoding="utf-8")))
    return cards


def iter_signal_expressions(card: dict):
    card_id = card.get("card_id", "?")
    for sig in card.get("diagnostic_signals", []):
        condition = sig.get("condition") or {}
        expression = (condition.get("expression") or sig.get("expression") or "").strip()
        yield card_id, sig.get("signal_id", "?"), expression


def evaluate_matrix(
    exports: dict[str, dict] | None = None,
    cards: list[dict] | None = None,
) -> dict:
    exports = exports or load_exports()
    cards = cards or load_cards()

    totals = Counter()
    by_category = Counter()
    hard_failures: list[dict] = []
    name_errors: list[dict] = []
    unique_hard = set()

    for uid, export in exports.items():
        merged = merge_export_variables(export)
        aer = (export.get("location_context") or {}).get("nbss_lup_aer_code")

        for card in cards:
            card_id = card.get("card_id", "?")
            for _, signal_id, expression in iter_signal_expressions(card):
                totals["signals"] += 1
                if not expression:
                    totals["no_expression"] += 1
                    by_category["no_expression"] += 1
                    continue

                missing = missing_context_keys(expression, merged)
                if missing:
                    totals["missing_context"] += 1
                    by_category["name_error"] += 1
                    name_errors.append(
                        {
                            "uid": uid,
                            "aer": aer,
                            "card_id": card_id,
                            "signal_id": signal_id,
                            "missing_variables": sorted(missing),
                            "expression": expression,
                        }
                    )
                    continue

                result, error = evaluate_expression(expression, merged)
                category = classify_eval_error(error)
                by_category[category] += 1

                if category == "ok":
                    totals["ok"] += 1
                    assert result is not None
                    continue

                totals["failed"] += 1
                if category in {"type_error", "attribute_error", "key_error", "syntax_error", "other_error"}:
                    totals["hard_failed"] += 1
                    key = (category, error.split(":", 1)[0])
                    if key not in unique_hard:
                        unique_hard.add(key)
                        hard_failures.append(
                            {
                                "uid": uid,
                                "aer": aer,
                                "card_id": card_id,
                                "signal_id": signal_id,
                                "category": category,
                                "error": error,
                                "expression": expression,
                            }
                        )

    return {
        "audited_at": date.today().isoformat(),
        "case_study_mws_count": len(exports),
        "card_count": len(cards),
        "matrix_size": totals["signals"],
        "totals": dict(totals),
        "by_category": dict(by_category),
        "hard_failure_count": totals["hard_failed"],
        "unique_hard_failure_patterns": len(unique_hard),
        "hard_failures_sample": hard_failures[:100],
        "name_error_count": by_category["name_error"],
        "name_errors_sample": name_errors[:50],
        "summary": {
            "evaluable_without_runtime_error": totals["ok"],
            "hard_runtime_errors": totals["hard_failed"],
            "missing_variable_context": by_category["name_error"],
            "exit_ok": totals["hard_failed"] == 0,
        },
    }


def print_report(report: dict) -> None:
    summary = report["summary"]
    print("=== Signal expression matrix (case-study MWS x all cards) ===")
    print(f"  Case-study MWS:     {report['case_study_mws_count']}")
    print(f"  Evidence cards:     {report['card_count']}")
    print(f"  Signal evaluations: {report['matrix_size']}")
    print(f"  OK (bool result):   {summary['evaluable_without_runtime_error']}")
    print(f"  Hard eval errors:   {summary['hard_runtime_errors']}")
    print(f"  Missing variables:  {summary['missing_variable_context']}")
    print(f"  No expression:      {report['totals'].get('no_expression', 0)}")
    print(f"  Unique hard patterns: {report['unique_hard_failure_patterns']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", type=Path, help="Write JSON report path")
    args = parser.parse_args()

    report = evaluate_matrix()
    print_report(report)

    out_path = args.write_report
    if out_path is None:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = AUDIT_DIR / f"signal_matrix_{date.today().isoformat()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written: {out_path}")

    return 0 if report["summary"]["exit_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
