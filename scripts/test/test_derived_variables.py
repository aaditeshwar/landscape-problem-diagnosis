#!/usr/bin/env python3
"""Unit tests for runtime derived variable computations."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.derived_variables import (  # noqa: E402
    delta_g_series,
    drought_return_period,
    mean,
    resolve_derived,
    swb_rabi_kharif_ratio_series,
    trend,
)


def test_mean_and_trend():
    series = {"2017": 10.0, "2018": 12.0, "2019": 14.0, "2020": 16.0}
    assert mean(series) == 13.0
    assert trend(series) == 2.0


def test_delta_g_recompute():
    mws = {
        "hydrological_annual": {
            "2017": {"precipitation_mm": 100, "et_mm": 60, "runoff_mm": 20},
            "2018": {"precipitation_mm": 80, "et_mm": 70, "runoff_mm": 30},
        }
    }
    dg = delta_g_series(mws)
    assert dg == {"2017": 20.0, "2018": -20.0}
    assert mean(dg) == 0.0
    assert trend(dg) == -40.0


def test_drought_return_period():
    weeks = {"2017": 0, "2018": 2, "2019": 0, "2020": 4, "2021": 0, "2022": 1}
    assert drought_return_period(weeks) == 2.0
    assert drought_return_period({"2017": 0, "2018": 0}) == 2.0
    assert drought_return_period({}) is None


def test_drought_severe_return_period_with_no_events():
    mws = {
        "drought_kharif": {
            str(y): {"severe_weeks": 0, "moderate_weeks": 0}
            for y in range(2017, 2025)
        }
    }
    assert resolve_derived(mws, "drought_severe_return_period") == 8.0


def test_swb_ratio():
    mws = {
        "swb_annual": {
            "2017": {"kharif_ha": 100, "rabi_ha": 50},
            "2018": {"kharif_ha": 80, "rabi_ha": 40},
        }
    }
    ratios = swb_rabi_kharif_ratio_series(mws)
    assert ratios == {"2017": 0.5, "2018": 0.5}
    assert resolve_derived(mws, "mean_swb_rabi_kharif_ratio") == 0.5


def test_tree_cover_percent_mws_derived():
    mws = {
        "area_ha": 200.0,
        "lulc_ha": {
            "2022": {"tree_forest": 10.0},
            "2024": {"tree_forest": 25.0},
        },
    }
    assert resolve_derived(mws, "tree_cover_percent_mws") == 12.5


def test_swb_ratio_zero_kharif_across_years():
    mws = {
        "swb_annual": {
            "2017": {"kharif_ha": 0, "rabi_ha": 0},
            "2018": {"kharif_ha": 0, "rabi_ha": 12},
            "2019": {"kharif_ha": 0},
        }
    }
    ratios = swb_rabi_kharif_ratio_series(mws)
    assert ratios == {"2017": 0.0, "2018": 0.0, "2019": 0.0}
    assert resolve_derived(mws, "mean_swb_rabi_kharif_ratio") == 0.0
    assert resolve_derived(mws, "trend_swb_rabi_kharif_ratio") == 0.0


def test_seasonal_precipitation_means():
    mws = {
        "hydrological_seasonal": {
            "2017": {
                "kharif": {"precipitation_mm": 800.0},
                "rabi": {"precipitation_mm": 100.0},
                "zaid": {"precipitation_mm": 50.0},
            },
            "2018": {
                "kharif": {"precipitation_mm": 900.0},
                "rabi": {"precipitation_mm": 120.0},
                "zaid": {"precipitation_mm": 30.0},
            },
        }
    }
    assert resolve_derived(mws, "mean_kharif_precipitation") == 850.0
    assert resolve_derived(mws, "mean_rabi_precipitation") == 110.0
    assert resolve_derived(mws, "mean_zaid_precipitation") == 40.0


def test_resolve_derived_names():
    mws = {
        "hydrological_annual": {
            str(y): {"precipitation_mm": 100 + y, "et_mm": 50, "runoff_mm": 10, "delta_g_mm": 40 + y}
            for y in range(2017, 2021)
        },
        "cropping_intensity": {
            str(y): {"cropping_intensity": 1.0 + (y - 2017) * 0.1, "double_crop_ha": 10 * y}
            for y in range(2017, 2021)
        },
        "drought_kharif": {
            str(y): {"moderate_weeks": 1 if y % 2 == 0 else 0, "severe_weeks": 0, "kharif_cropped_ha": 100 + y}
            for y in range(2017, 2021)
        },
        "swb_annual": {
            str(y): {"total_ha": 50 + y, "kharif_ha": 40, "rabi_ha": 20}
            for y in range(2017, 2021)
        },
    }
    assert resolve_derived(mws, "trend_annual_delta_g_mm") == 1.0
    assert resolve_derived(mws, "trend_cropping_intensity") == 0.1
    assert resolve_derived(mws, "drought_moderate_return_period") == 2.0


def main() -> int:
    tests = [
        test_mean_and_trend,
        test_delta_g_recompute,
        test_drought_return_period,
        test_drought_severe_return_period_with_no_events,
        test_swb_ratio,
        test_tree_cover_percent_mws_derived,
        test_swb_ratio_zero_kharif_across_years,
        test_seasonal_precipitation_means,
        test_resolve_derived_names,
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
