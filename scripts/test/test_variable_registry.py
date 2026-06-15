#!/usr/bin/env python3
"""Unit tests for variable registry normalization helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.assembler import NOT_AVAILABLE, VARIABLE_RESOLVERS, resolve_variable  # noqa: E402
from services.variable_registry import (  # noqa: E402
    canonical_name,
    normalize_drought_causality,
    normalize_expression,
    not_available_variables,
    resolver_key_for,
    rewrite_self_comparison_tautologies,
)


def test_drought_causality_normalization():
    raw = {
        "2020": {
            "severe_moderate": {
                "moderate_drought_path3": 5.0,
                "moderate_drought_path12": 2.0,
            },
            "mild": {
                "mild_drought_spi_score": 21.0,
                "mild_drought_mai_score": 6.33,
                "mild_drought_dryspell_score": 4.0,
            },
        }
    }
    normalized = normalize_drought_causality(raw)
    mild = normalized["2020"]["mild"]
    assert mild["spi_score"] == 21.0
    assert mild["mai_score"] == 6.33
    assert mild["dryspell_score"] == 4.0
    assert normalized["2020"]["severe_moderate"]["drought_path3"] == 5.0
    assert normalized["2020"]["severe_moderate"]["drought_path12"] == 2.0
    assert "mild_drought_spi_score" not in mild


def test_alias_to_canonical():
    assert canonical_name("drought_causality_json") == "drought_causality"
    assert canonical_name("cd_total_urbanization_ha") == "cd_urbanization_ha"
    assert resolver_key_for("cd_urbanization_ha") == "cd_total_urbanization_ha"


def test_resolver_aliases():
    assert "drought_causality" in VARIABLE_RESOLVERS
    assert "cd_urbanization_ha" in VARIABLE_RESOLVERS
    assert "precipitation_mm" in VARIABLE_RESOLVERS


def test_static_cd_expression_rewrite():
    expr = (
        "cd_total_urbanization_ha[-1] > cd_total_urbanization_ha[0] "
        "and (cd_total_urbanization_ha[-1] - cd_total_urbanization_ha[0]) > 20"
    )
    patched, notes = normalize_expression(expr)
    assert patched == "cd_urbanization_ha > 20"
    assert notes


def test_tautology_rewrite_uses_card_thresholds():
    expr = "cd_forest_to_farm_ha > cd_forest_to_farm_ha"
    patched = rewrite_self_comparison_tautologies(expr, {"cd_forest_to_farm_ha": "50"})
    assert patched == "cd_forest_to_farm_ha > 50"


def test_landholding_alias_and_not_available():
    assert canonical_name("landholding_size_distribution") == "landholding_distribution"
    assert "landholding_size_distribution" in NOT_AVAILABLE
    assert "landholding_size_distribution" in not_available_variables()


def test_drought_expression_rewrite():
    raw = "drought_causality_json.get('spi_kharif', 0) <= -1.0"
    patched, notes = normalize_expression(raw)
    assert "drought_mild_spi_score_latest >= 26" in patched
    assert "drought_causality_json" not in patched
    assert notes


def test_resolve_variable_accepts_canonical_name():
    mws = {
        "change_detection": {"urbanization": {"total_ha": 29.01}},
    }
    assert resolve_variable(mws, "cd_urbanization_ha") == 29.01
    assert resolve_variable(mws, "cd_total_urbanization_ha") == 29.01


def test_monsoon_onset_date_keeps_string_values():
    mws = {
        "drought_kharif": {
            "2017": {"monsoon_onset": "2017-6-11", "severe_weeks": 2},
            "2018": {"monsoon_onset": "2018-6-12", "severe_weeks": 1},
        }
    }
    result = resolve_variable(mws, "monsoon_onset_date")
    assert result == {"2017": "2017-6-11", "2018": "2018-6-12"}
