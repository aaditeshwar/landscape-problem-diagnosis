#!/usr/bin/env python3
"""Tests for Tier-2 note label templates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from lib.note_label_templates import template_note_label  # noqa: E402
from lib.sig_note_labels import sig_note_label  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DROUGHT_001 = ROOT / "data" / "evidence_cards" / "raw" / "agriculture__water_scarcity__drought__001.json"
GW_015 = ROOT / "data" / "evidence_cards" / "raw" / "agriculture__water_scarcity__groundwater_stress__015.json"


def test_drought_001_template_labels():
    card = json.loads(DROUGHT_001.read_text(encoding="utf-8"))
    assert "≤ 4 years" in sig_note_label(card, "sig_01")
    assert "dry-spell" in sig_note_label(card, "sig_02").lower()
    assert "kharif" in sig_note_label(card, "sig_04").lower()
    assert "monsoon" in sig_note_label(card, "sig_05").lower()


def test_groundwater_015_template_labels():
    card = json.loads(GW_015.read_text(encoding="utf-8"))
    assert "SOGE" in sig_note_label(card, "sig_01")
    assert "Farmer-reported" in sig_note_label(card, "sig_05")
    assert template_note_label("groundwater_stress", "sig_07", "") == (
        "Farmer-reported saline or brackish well water"
    )


def main() -> int:
    test_drought_001_template_labels()
    test_groundwater_015_template_labels()
    print("All note label template tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
