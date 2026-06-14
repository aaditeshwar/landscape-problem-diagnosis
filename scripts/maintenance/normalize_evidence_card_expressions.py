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

from services.variable_registry import alias_to_canonical, normalize_expression  # noqa: E402

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
    for sig in card.get("diagnostic_signals", []):
        condition = sig.get("condition") or {}
        expression = condition.get("expression") or sig.get("expression")
        if not expression:
            continue
        patched, expr_notes = normalize_expression(expression)
        if patched != expression:
            if "condition" in sig:
                sig["condition"]["expression"] = patched
            else:
                sig["expression"] = patched
            notes.append(f"{sig.get('signal_id', '?')}: {', '.join(expr_notes)}")
            inferred = _variables_from_expression(patched)
            if inferred:
                if "condition" in sig:
                    sig["condition"]["variables"] = inferred
                else:
                    sig["variables"] = inferred
                notes.append(f"{sig.get('signal_id', '?')}: synced variables list from expression")
        variables = condition.get("variables") or sig.get("variables")
        if isinstance(variables, list):
            updated = []
            changed = False
            for var in variables:
                canonical = alias_to_canonical().get(var, var)
                updated.append(canonical)
                if canonical != var:
                    changed = True
            if changed:
                if "condition" in sig:
                    sig["condition"]["variables"] = updated
                else:
                    sig["variables"] = updated
                notes.append(f"{sig.get('signal_id', '?')}: canonicalized variables list")
    return card, notes


def normalize_cards(raw_dir: Path = RAW_DIR, *, dry_run: bool = False) -> dict:
    changed_cards: list[str] = []
    details: dict[str, list[str]] = {}

    for path in sorted(raw_dir.glob("*.json")):
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
        "cards_changed": changed_cards,
        "change_count": len(changed_cards),
        "details": details,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = normalize_cards(dry_run=args.dry_run)
    print("=== Evidence card expression normalization ===")
    print(f"  Cards changed: {report['change_count']}")
    for card_id in report["cards_changed"][:20]:
        print(f"    - {card_id}")
    if report["change_count"] > 20:
        print(f"    ... and {report['change_count'] - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
