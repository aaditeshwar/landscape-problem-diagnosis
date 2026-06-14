#!/usr/bin/env python3
"""Add pathway diagnostic_variables referenced in evidence-card signal expressions."""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_PATH = ROOT / "metadata" / "diagnosis_framework.json"
CARDS_DIR = ROOT / "data" / "evidence_cards" / "raw"

SAFE = {
    "True",
    "False",
    "None",
    "abs",
    "min",
    "max",
    "len",
    "sum",
    "sorted",
    "round",
    "float",
    "int",
    "list",
    "dict",
    "any",
    "all",
}


def expression_names(expression: str) -> set[str]:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    bound.add(sub.id)
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id not in SAFE
        and node.id not in bound
    }


def collect_needed_variables() -> dict[str, set[str]]:
    needed: dict[str, set[str]] = defaultdict(set)
    for fp in sorted(CARDS_DIR.glob("*.json")):
        card = json.loads(fp.read_text(encoding="utf-8"))
        pathway_id = card.get("causal_pathway")
        if not pathway_id:
            continue
        for signal in card.get("diagnostic_signals") or []:
            expression = (signal.get("condition") or {}).get("expression") or ""
            if expression.strip():
                needed[str(pathway_id)].update(expression_names(expression))
    return needed


def patch_framework(*, dry_run: bool = False) -> dict[str, list[str]]:
    framework = json.loads(FRAMEWORK_PATH.read_text(encoding="utf-8"))
    needed = collect_needed_variables()
    added: dict[str, list[str]] = defaultdict(list)

    for _prod, pdata in framework["diagnosis_framework"]["production_systems"].items():
        for _stress, sdata in pdata.get("observed_stresses", {}).items():
            for pathway_id, pcfg in sdata.get("causal_pathways", {}).items():
                if not isinstance(pcfg, dict) or "diagnostic_variables" not in pcfg:
                    continue
                existing = {v["variable"] for v in pcfg["diagnostic_variables"]}
                for var in sorted(needed.get(pathway_id, set()) - existing):
                    pcfg["diagnostic_variables"].append(
                        {
                            "variable": var,
                            "rationale": (
                                "Referenced in evidence-card signal expressions "
                                "(derived or supporting indicator)."
                            ),
                            "availability": "available",
                        }
                    )
                    added[pathway_id].append(var)

    if not dry_run and added:
        FRAMEWORK_PATH.write_text(
            json.dumps(framework, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return dict(added)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    added = patch_framework(dry_run=args.dry_run)
    for pathway_id, vars_added in sorted(added.items()):
        print(f"{pathway_id}: {vars_added}")
    print(f"Patched {len(added)} pathways" if not args.dry_run else f"Would patch {len(added)} pathways")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
