#!/usr/bin/env python3
"""Tests for lithology/AER-based ACWADAM and card aquifer tag inference."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.aquifer_classification import (  # noqa: E402
    card_aquifer_tags,
    dominant_lithology,
    infer_acwadam_class,
)


def test_dominant_lithology_excludes_none_bucket():
    lith = {"Granite": 62.0, "None": 38.0, "Basalt": 10.0}
    assert dominant_lithology(lith) == ("Granite", 62.0)


def test_basalt_maps_to_volcanic():
    result = infer_acwadam_class({"Basalt": 80.0, "None": 20.0})
    assert result["acwadam_class"] == "volcanic"
    assert result["acwadam_source"] == "lithology"


def test_laterite_deccan_uses_aer():
    result = infer_acwadam_class({"Laterite": 70.0, "None": 30.0}, "AER-6")
    assert result["acwadam_class"] == "volcanic"
    assert result["acwadam_source"] == "lithology+aer"


def test_laterite_peninsular_uses_aer():
    result = infer_acwadam_class({"Laterite": 70.0}, "AER-3")
    assert result["acwadam_class"] == "crystalline_basement"


def test_himalayan_sandstone_override():
    result = infer_acwadam_class({"Sandstone": 55.0, "Alluvium": 50.0}, "AER-14")
    assert result["acwadam_class"] == "himalayan_and_sub_himalayan"


def test_tie_within_5pp_uses_aer_fallback():
    result = infer_acwadam_class({"Granite": 40.0, "Gneiss": 36.0}, "AER-10")
    assert result["acwadam_class"] == "sedimentary_soft_rock"
    assert result["acwadam_source"] == "lithology+aer"


def test_aer18_alluvium_card_tags():
    assert card_aquifer_tags("alluvium", "AER-18") == ["coastal", "alluvium"]


def test_aer20_card_tags():
    assert card_aquifer_tags("alluvium", "AER-20") == ["coastal"]


def test_sedimentary_soft_rock_maps_semi_consolidated():
    assert card_aquifer_tags("sedimentary_soft_rock", "AER-10") == ["semi-consolidated"]


def main() -> int:
    test_dominant_lithology_excludes_none_bucket()
    test_basalt_maps_to_volcanic()
    test_laterite_deccan_uses_aer()
    test_laterite_peninsular_uses_aer()
    test_himalayan_sandstone_override()
    test_tie_within_5pp_uses_aer_fallback()
    test_aer18_alluvium_card_tags()
    test_aer20_card_tags()
    test_sedimentary_soft_rock_maps_semi_consolidated()
    print("All aquifer classification tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
