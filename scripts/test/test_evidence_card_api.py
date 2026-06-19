#!/usr/bin/env python3
"""Tests for evidence card listing helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.evidence_card_api import (  # noqa: E402
    cluster_suffix_from_card_id,
    get_evidence_card,
    list_cards_by_cluster,
)


def test_cluster_suffix_from_card_id():
    assert cluster_suffix_from_card_id("agriculture__water_scarcity__groundwater_stress__009") == "009"


def test_list_cards_by_cluster_filters_suffix():
    db = MagicMock()
    col = MagicMock()
    db.evidence_cards = col
    col.find.return_value.sort.return_value = [
        {
            "card_id": "agriculture__water_scarcity__groundwater_stress__009",
            "causal_pathway": "groundwater_stress",
            "production_system": "Agriculture",
        }
    ]
    rows = list_cards_by_cluster(db, "9")
    assert len(rows) == 1
    assert rows[0]["cluster_suffix"] == "009"
    assert rows[0]["pathway_id"] == "groundwater_stress"


def test_get_evidence_card():
    db = MagicMock()
    col = MagicMock()
    db.evidence_cards = col
    col.find_one.return_value = {
        "_id": "x",
        "card_id": "agriculture__water_scarcity__groundwater_stress__009",
        "causal_pathway": "groundwater_stress",
    }
    doc = get_evidence_card(db, "agriculture__water_scarcity__groundwater_stress__009")
    assert doc is not None
    assert doc["cluster_suffix"] == "009"
    assert "_id" not in doc


def main() -> int:
    test_cluster_suffix_from_card_id()
    test_list_cards_by_cluster_filters_suffix()
    test_get_evidence_card()
    print("All evidence card API tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
