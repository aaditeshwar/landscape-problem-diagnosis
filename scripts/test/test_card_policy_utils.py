#!/usr/bin/env python3
"""Tests for card policy parsing helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from lib.card_policy_utils import derive_policy, primary_signals_from_note, confirm_signal_ids  # noqa: E402

GW010 = Path(__file__).resolve().parents[2] / "data" / "evidence_cards" / "raw" / "agriculture__water_scarcity__groundwater_stress__010.json"


def test_groundwater_010_primary_set_excludes_contextual_sig_03():
    with GW010.open(encoding="utf-8") as handle:
        card = json.load(handle)
    note = card["overall_reasoning_note"]
    confirm_ids = confirm_signal_ids(card)
    primary = primary_signals_from_note(note, confirm_ids)
    assert "sig_01" in primary
    assert "sig_02" in primary
    assert "sig_05" in primary
    assert "sig_03" not in primary

    policy = derive_policy(card)
    assert set(policy["primary_confirm_signals"]) == {"sig_01", "sig_02", "sig_05"}


def main() -> int:
    test_groundwater_010_primary_set_excludes_contextual_sig_03()
    print("All card policy utils tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
