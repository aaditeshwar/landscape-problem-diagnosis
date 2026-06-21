#!/usr/bin/env python3
"""Unit tests for production-system eligibility gating."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.derived_variables import tree_cover_percent_mws  # noqa: E402
from services.production_system_gate import (  # noqa: E402
    evaluate_production_system_gates,
    filter_cards_by_eligible_systems,
)


def _mws(tree_ha: float, area_ha: float = 1000.0) -> dict:
    return {
        "uid": "test_mws",
        "area_ha": area_ha,
        "lulc_ha": {
            "2023": {"tree_forest": tree_ha},
            "2024": {"tree_forest": tree_ha},
        },
    }


def test_tree_cover_percent_mws():
    assert tree_cover_percent_mws(_mws(50.0, 1000.0)) == 5.0
    assert tree_cover_percent_mws(_mws(120.0, 1000.0)) == 12.0
    assert tree_cover_percent_mws({"area_ha": 1000.0}) is None


def test_ntfp_skipped_below_ten_percent_tree_cover():
    gate = evaluate_production_system_gates(_mws(50.0))
    assert "NTFP_Forest_Biodiversity" not in gate["eligible_production_systems"]
    assert any(
        item["production_system"] == "NTFP_Forest_Biodiversity"
        for item in gate["skipped_production_systems"]
    )


def test_ntfp_eligible_at_ten_percent_tree_cover():
    gate = evaluate_production_system_gates(_mws(100.0))
    assert "NTFP_Forest_Biodiversity" in gate["eligible_production_systems"]
    assert not any(
        item["production_system"] == "NTFP_Forest_Biodiversity"
        for item in gate["skipped_production_systems"]
    )


def test_filter_cards_by_eligible_systems():
    cards = [
        {"card_id": "a", "production_system": "Agriculture"},
        {"card_id": "b", "production_system": "NTFP_Forest_Biodiversity"},
    ]
    filtered = filter_cards_by_eligible_systems(cards, {"Agriculture"})
    assert [card["card_id"] for card in filtered] == ["a"]


if __name__ == "__main__":
    test_tree_cover_percent_mws()
    test_ntfp_skipped_below_ten_percent_tree_cover()
    test_ntfp_eligible_at_ten_percent_tree_cover()
    test_filter_cards_by_eligible_systems()
    print("OK")
