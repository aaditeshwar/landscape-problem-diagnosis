#!/usr/bin/env python3
"""Tests for monsoon onset derived variables and year-indexed access display."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap

bootstrap(runtime=True)

from services.derived_variables import (  # noqa: E402
    monsoon_onset_delay_first_year_days,
    monsoon_onset_delay_lag3_days,
    monsoon_onset_latest_doy,
    lulc_cropland_latest_ha,
)
from services.expression_variable_access import format_access_value, resolve_access_value  # noqa: E402
from services.signal_evaluator import evaluate_expression, merge_export_variables, present_variables_for_access_resolution  # noqa: E402


def test_monsoon_delay_within_season_not_calendar_span():
    mws = {
        "drought_kharif": {
            "2017": {"monsoon_onset": "2017-05-28"},
            "2024": {"monsoon_onset": "2024-05-29"},
        }
    }
    assert monsoon_onset_delay_first_year_days(mws) == 1


def test_monsoon_delay_expression_false_for_small_shift():
    export_path = Path("data/raw_jsons/7_1281.json")
    if not export_path.exists():
        return
    present = merge_export_variables(json.loads(export_path.read_text(encoding="utf-8")))
    result, error = evaluate_expression(
        "monsoon_onset_delay_first_year_days > 10 or monsoon_onset_delay_lag3_days > 7",
        present,
    )
    assert error is None
    assert result is False


def test_monsoon_onset_index_display_not_dash():
    export_path = Path("data/raw_jsons/7_1281.json")
    if not export_path.exists():
        return
    present = merge_export_variables(json.loads(export_path.read_text(encoding="utf-8")))
    lookup = present_variables_for_access_resolution(present)
    formatted = format_access_value(resolve_access_value("monsoon_onset_date[-1]", lookup))
    assert formatted != "—"
    assert "2024" in formatted


def test_lulc_cropland_latest_skips_trailing_zero():
    mws = {
        "lulc_ha": {
            "2022": {"single_kharif": 500, "single_non_kharif": 0, "double_crop": 50, "triple_crop": 0},
            "2023": {"single_kharif": 510, "single_non_kharif": 0, "double_crop": 55, "triple_crop": 0},
            "2024": {"single_kharif": 0, "single_non_kharif": 0, "double_crop": 0, "triple_crop": 0},
        }
    }
    assert lulc_cropland_latest_ha(mws) == 565.0


if __name__ == "__main__":
    test_monsoon_delay_within_season_not_calendar_span()
    test_monsoon_delay_expression_false_for_small_shift()
    test_monsoon_onset_index_display_not_dash()
    test_lulc_cropland_latest_skips_trailing_zero()
    print("ok")
