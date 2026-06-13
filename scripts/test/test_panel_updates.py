#!/usr/bin/env python3
"""Unit tests for panel_updates mapping (no LLM required)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.panel_updates import (  # noqa: E402
    build_panel_update_explanation,
    panel_updates_for_confirmed,
)


def assert_eq(label: str, got, expected) -> None:
    if got != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {got!r}")


def main() -> int:
    cases = [
        (
            "forest_degradation short id",
            [{"pathway_id": "forest_degradation", "confidence": "high"}],
            [
                "lulc_tree_forest_ha trend",
                "cd_total_deforestation_ha + cd_total_afforestation_ha paired_bar",
            ],
        ),
        (
            "encroachment pipeline key",
            [{"pathway_id": "ntfp_forest_biodiversity__ntfp_decline__encroachment", "confidence": "high"}],
            [
                "lulc_tree_forest_ha trend",
                "cd_total_deforestation_ha + cd_total_afforestation_ha paired_bar",
            ],
        ),
        (
            "multi_sector_vulnerability",
            [{"pathway_id": "multi_sector_vulnerability", "confidence": "medium"}],
            ["drought_weeks stacked_bar", "nrega_*_count stacked_bar_cumulative"],
        ),
        (
            "small_landholding",
            [{"pathway_id": "small_landholding", "confidence": "high"}],
            ["cropping_intensity trend", "dist_*_km horizontal_bars"],
        ),
    ]

    print("=== panel_updates unit tests ===")
    for label, confirmed, expected in cases:
        got = panel_updates_for_confirmed(confirmed)
        assert_eq(label, got, expected)
        explanation = build_panel_update_explanation(confirmed, got)
        assert explanation and "info panel" in explanation.lower(), f"{label}: missing explanation"
        assert "highlighted" not in explanation.lower() or explanation.lower().count("highlighted") < 2, (
            f"{label}: explanation looks like a duplicate action list"
        )
        print(f"  OK  {label}")

    print("=== ALL PASS ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
