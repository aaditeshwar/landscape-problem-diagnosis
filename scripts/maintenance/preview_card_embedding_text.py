#!/usr/bin/env python3
"""Dry-run preview of alias-augmented evidence card embedding text.

Does not call Ollama or write to MongoDB. Use before:
  python scripts/reembed_evidence_cards.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap()

from lib.card_embedding_text import (  # noqa: E402
    aliases_for_pathway,
    build_card_embedding_text,
    format_alias_paragraph,
    legacy_card_embed_text,
    load_semantic_aliases,
)

RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"


def iter_card_paths(prefix: str | None) -> list[Path]:
    paths = sorted(RAW_DIR.glob("*.json"))
    if prefix:
        paths = [p for p in paths if p.stem.startswith(prefix)]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", help="Only preview cards whose card_id starts with this prefix")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write full preview .txt files (requires --output-dir)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for --write output (created if missing)",
    )
    parser.add_argument(
        "--show-legacy",
        action="store_true",
        help="Also print legacy (pre-alias) embedding text length for comparison",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    if args.write and output_dir is None:
        print("--write requires --output-dir", file=sys.stderr)
        return 1

    alias_map = load_semantic_aliases()
    paths = iter_card_paths(args.prefix)
    if not paths:
        print("No raw card JSON files matched", file=sys.stderr)
        return 1

    missing_aliases: set[str] = set()
    if args.write and output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Embedding text preview ({len(paths)} card(s)) ===")
    print(f"Alias pathways loaded: {len(alias_map)}")

    for path in paths:
        card = json.loads(path.read_text(encoding="utf-8"))
        card_id = card.get("card_id") or path.stem
        pathway_id = str(card.get("causal_pathway") or "")
        aliases = aliases_for_pathway(pathway_id)
        if not aliases:
            missing_aliases.add(pathway_id)

        new_text = build_card_embedding_text(card)
        legacy_text = legacy_card_embed_text(card)
        alias_paragraph = format_alias_paragraph(aliases)

        print(f"\n--- {card_id} ---")
        print(f"pathway: {pathway_id}  aliases: {len(aliases)}")
        if args.show_legacy:
            print(f"legacy chars: {len(legacy_text)}  new chars: {len(new_text)}  (+{len(new_text) - len(legacy_text)})")
        if alias_paragraph:
            preview = alias_paragraph[:160] + ("..." if len(alias_paragraph) > 160 else "")
            print(f"alias tail: {preview}")
        print(f"text tail: {new_text[-220:].replace(chr(10), ' ')}")

        if args.write and output_dir is not None:
            out = output_dir / f"{card_id}.embedding.txt"
            out.write_text(new_text, encoding="utf-8")

    if missing_aliases:
        print(f"\nWARNING: no aliases for pathway(s): {', '.join(sorted(missing_aliases))}")

    if args.write and output_dir is not None:
        print(f"\nWrote preview files to {output_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
