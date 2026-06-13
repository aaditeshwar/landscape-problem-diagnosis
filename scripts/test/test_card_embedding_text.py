#!/usr/bin/env python3
"""Unit tests for alias-augmented card embedding text."""

from __future__ import annotations

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


def test_alias_map_loads_all_framework_pathways():
    aliases = load_semantic_aliases()
    assert "forest_degradation" in aliases
    assert "multi_sector_vulnerability" in aliases
    assert len(aliases) >= 20


def test_aliases_appended_at_end():
    card = {
        "production_system": "NTFP_Forest_Biodiversity",
        "observed_stress": "ntfp_decline",
        "causal_pathway": "forest_degradation",
        "overall_reasoning_note": "Core forest reasoning note.",
        "diagnostic_signals": [{"explanation": "Signal explanation text."}],
        "context": {
            "agro_climatic_zones": ["sub-humid"],
            "aquifer_types": ["alluvium"],
            "rainfall_regime": "sub-humid",
            "geographic_examples": ["Odisha coast"],
        },
    }
    text = build_card_embedding_text(card)
    aliases = format_alias_paragraph(aliases_for_pathway("forest_degradation"))
    assert text.endswith(aliases)
    assert "social ecological forest stress" in text
    assert len(text) > len(legacy_card_embed_text(card))


def test_raw_card_sample_has_alias_tail():
    sample_path = (
        ROOT
        / "data"
        / "evidence_cards"
        / "raw"
        / "ntfp_forest_biodiversity__ntfp_decline__forest_degradation__006.json"
    )
    if not sample_path.exists():
        return
    card = json.loads(sample_path.read_text(encoding="utf-8"))
    text = build_card_embedding_text(card)
    assert "Related themes:" in text
    assert text.index("Related themes:") > text.index(card["overall_reasoning_note"][:20])


def main() -> int:
    tests = [
        test_alias_map_loads_all_framework_pathways,
        test_aliases_appended_at_end,
        test_raw_card_sample_has_alias_tail,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n=== {len(tests) - failed}/{len(tests)} passed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
