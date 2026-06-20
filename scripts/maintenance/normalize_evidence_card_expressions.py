#!/usr/bin/env python3
"""Apply deterministic registry-based rewrites to evidence card signal expressions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.variable_registry import alias_to_canonical, card_variable_thresholds, normalize_expression  # noqa: E402

RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"


def _variables_from_expression(expression: str) -> list[str]:
    import ast

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return []
    allowed = {"True", "False", "None", "abs", "min", "max", "len", "sum", "sorted", "round", "float", "int", "list", "dict", "any", "all"}
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    bound.add(sub.id)
    names = [
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id not in allowed
        and node.id not in bound
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def patch_card(card: dict) -> tuple[dict, list[str]]:
    notes: list[str] = []
    thresholds = card_variable_thresholds(card)
    for sig in card.get("diagnostic_signals", []):
        condition = sig.get("condition") or {}
        expression = condition.get("expression") or sig.get("expression")
        if not expression:
            continue
        signal_id = sig.get("signal_id", "?")
        inferred = _variables_from_expression(expression)
        patched, expr_notes = normalize_expression(expression, card_thresholds=thresholds)
        if patched != expression:
            if "condition" in sig:
                sig["condition"]["expression"] = patched
            else:
                sig["expression"] = patched
            notes.append(f"{signal_id}: {', '.join(expr_notes)}")
            inferred = _variables_from_expression(patched)

        # Always sync variables from the effective expression, even if expression text is unchanged.
        if inferred:
            signal_vars = sig.get("variables")
            if not isinstance(signal_vars, list) or signal_vars != inferred:
                sig["variables"] = inferred
                notes.append(f"{signal_id}: synced signal variables list from expression")
            if isinstance(sig.get("condition"), dict):
                cond_vars = sig["condition"].get("variables")
                if not isinstance(cond_vars, list) or cond_vars != inferred:
                    sig["condition"]["variables"] = inferred
                    notes.append(f"{signal_id}: synced condition variables list from expression")

        for var_list, target in (
            (sig.get("variables"), "signal"),
            ((sig.get("condition") or {}).get("variables"), "condition"),
        ):
            if not isinstance(var_list, list):
                continue
            updated = [alias_to_canonical().get(var, var) for var in var_list]
            if updated == var_list:
                continue
            if target == "signal":
                sig["variables"] = updated
            else:
                sig["condition"]["variables"] = updated
            notes.append(f"{signal_id}: canonicalized {target} variables list")
    return card, notes


def normalize_cards(raw_dir: Path = RAW_DIR, *, dry_run: bool = False, prefix: str | None = None) -> dict:
    changed_cards: list[str] = []
    details: dict[str, list[str]] = {}

    paths = sorted(raw_dir.glob("*.json"))
    if prefix:
        paths = [p for p in paths if p.stem.startswith(prefix)]

    for path in paths:
        card = json.loads(path.read_text(encoding="utf-8"))
        patched, notes = patch_card(card)
        if not notes:
            continue
        changed_cards.append(path.stem)
        details[path.stem] = notes
        if not dry_run:
            path.write_text(json.dumps(patched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "raw_dir": str(raw_dir),
        "prefix": prefix,
        "cards_changed": changed_cards,
        "change_count": len(changed_cards),
        "details": details,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prefix", help="Only normalize cards whose card_id starts with this prefix")
    args = parser.parse_args()

    report = normalize_cards(dry_run=args.dry_run, prefix=args.prefix)
    print("=== Evidence card expression normalization ===")
    print(f"  Cards changed: {report['change_count']}")
    for card_id in report["cards_changed"][:20]:
        print(f"    - {card_id}")
    if report["change_count"] > 20:
        print(f"    ... and {report['change_count'] - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
