# -*- coding: utf-8 -*-
"""Convert blog markdown from cp1252 mojibake to UTF-8 punctuation."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def normalize_punctuation(text: str) -> str:
    """Fix literal ? placeholders left from earlier corruption."""
    text = text.replace("generation ? symbolic", "generation \u2192 symbolic")
    text = text.replace("artifact ? deterministic", "artifact \u2192 deterministic")
    text = text.replace(
        "case studies ? production systems ? pathways",
        "case studies \u2192 production systems \u2192 pathways",
    )
    text = text.replace(
        "Agriculture ? water_scarcity ? groundwater_stress",
        "Agriculture \u2192 water_scarcity \u2192 groundwater_stress",
    )
    text = text.replace("paper ? card ? normalize ? tune", "paper \u2192 card \u2192 normalize \u2192 tune")
    text = text.replace("roughly ?10 per", "roughly \u20b910 per")
    text = text.replace("confirm when ?2 of", "confirm when \u22652 of")
    text = text.replace("systems ? papers", "systems \u2192 papers")
    text = text.replace("? dictionary", "\u2192 dictionary")
    text = text.replace("? cards", "\u2192 cards")
    text = text.replace("? normalize", "\u2192 normalize")
    text = text.replace("? fine-tune", "\u2192 fine-tune")
    text = text.replace("system ? observed", "system \u2192 observed")
    text = text.replace("? causal", "\u2192 causal")
    # Double space before richer (typo from earlier edit)
    text = text.replace("collect ** richer", "collect **richer")
    return text


def convert_file(path: Path) -> None:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    text = normalize_punctuation(text)
    path.write_text(text, encoding="utf-8", newline="\n")
    verify = path.read_text(encoding="utf-8")
    bad = sum(1 for ch in verify if ord(ch) > 127 and ch in "\ufffd")
    print(f"{path.name}: utf-8 ok, em={verify.count(chr(0x2014))}, en={verify.count(chr(0x2013))}, arrow={verify.count(chr(0x2192))}")


def main() -> None:
    for name in ("diagnostics-engine-neurosymbolic-ai.md", "README.md"):
        convert_file(ROOT / "blogs" / name)


if __name__ == "__main__":
    main()
