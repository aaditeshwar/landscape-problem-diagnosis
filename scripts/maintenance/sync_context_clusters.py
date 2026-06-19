#!/usr/bin/env python3
"""Sync metadata/context_clusters.json from scripts/generate_evidence_cards.py."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "generate_evidence_cards.py"
TARGET = ROOT / "metadata" / "context_clusters.json"


def extract_context_clusters(source_text: str) -> list[dict]:
    module = ast.parse(source_text)
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CONTEXT_CLUSTERS":
                    value = ast.literal_eval(node.value)
                    if isinstance(value, list):
                        return value
    raise RuntimeError("CONTEXT_CLUSTERS assignment not found")


def main() -> int:
    if not SOURCE.is_file():
        print(f"Missing source: {SOURCE}", file=sys.stderr)
        return 1
    clusters = extract_context_clusters(SOURCE.read_text(encoding="utf-8"))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps({"clusters": clusters}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(clusters)} clusters -> {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
