#!/usr/bin/env python3
"""Update drought / small_landholding evidence cards to use new derived variables."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARD_DIR = ROOT / "data" / "evidence_cards" / "raw"

EXPRESSION_REPLACEMENTS = [
    (
        "(monsoon_onset_date[-1] - monsoon_onset_date[0]).days > 10 or (monsoon_onset_date[-1] - monsoon_onset_date[-3]).days > 7",
        "monsoon_onset_delay_first_year_days > 10 or monsoon_onset_delay_lag3_days > 7",
    ),
    (
        "monsoon_onset_date[-1] > monsoon_onset_date[0] and (monsoon_onset_date[-1] - monsoon_onset_date[0]).days > 10",
        "monsoon_onset_delay_first_year_days > 10",
    ),
    (
        "monsoon_onset_date[-1] > monsoon_onset_date[0] and (monsoon_onset_date[-1] - monsoon_onset_date[0]) > 7",
        "monsoon_onset_delay_first_year_days > 7",
    ),
    (
        "(monsoon_onset_date[-1] - monsoon_onset_date[0]).days > 10",
        "monsoon_onset_delay_first_year_days > 10",
    ),
    (
        "(monsoon_onset_date[-1] - monsoon_onset_date[0]) > 7 or monsoon_onset_date[-1] > 175",
        "monsoon_onset_delay_first_year_days > 7 or monsoon_onset_latest_doy > 175",
    ),
    (
        "(monsoon_onset_date[-1] - monsoon_onset_date[0]) > 7",
        "monsoon_onset_delay_first_year_days > 7",
    ),
    (
        "drought_severe_return_period < 5 or (monsoon_onset_date[-1] > monsoon_onset_date[0] and drought_weeks_severe[-1] >= 2)",
        "drought_severe_return_period < 5 or (monsoon_onset_delay_first_year_days > 0 and drought_weeks_severe[-1] >= 2)",
    ),
    (
        "monsoon_onset_date[-1] > monsoon_onset_date[0] and seasonal_precipitation_mm[-1].get('kharif', 9999) < 0.80 * mean_kharif_precipitation",
        "monsoon_onset_delay_first_year_days > 0 and seasonal_precipitation_mm[-1].get('kharif', 9999) < 0.80 * mean_kharif_precipitation",
    ),
    ("monsoon_onset_date[-1] > monsoon_onset_date[0] + 10", "monsoon_onset_delay_first_year_days > 10"),
    ("monsoon_onset_date[-1] > monsoon_onset_date[0] + 7", "monsoon_onset_delay_first_year_days > 7"),
    ("monsoon_onset_date[-1] > monsoon_onset_date[0]", "monsoon_onset_delay_first_year_days > 0"),
    ("monsoon_onset_date[-1] > 175", "monsoon_onset_latest_doy > 175"),
]

DERIVED_VARS = {
    "monsoon_onset_delay_first_year_days",
    "monsoon_onset_delay_lag3_days",
    "monsoon_onset_latest_doy",
    "lulc_cropland_latest_ha",
}


def _vars_for_expression(expression: str) -> list[str]:
    found = {name for name in DERIVED_VARS if name in expression}
    for legacy in ("monsoon_onset_date", "seasonal_precipitation_mm", "mean_kharif_precipitation", "drought_severe_return_period", "drought_weeks_severe", "village_total_population", "mean_cropping_intensity"):
        if legacy in expression:
            found.add(legacy)
    return sorted(found)


def _update_signal(signal: dict) -> bool:
    changed = False
    condition = signal.get("condition") or {}
    expr = str(condition.get("expression") or "")
    new_expr = expr
    for old, new in EXPRESSION_REPLACEMENTS:
        if old in new_expr:
            new_expr = new_expr.replace(old, new)
    if "lulc_cropland_ha[-1]" in new_expr:
        new_expr = new_expr.replace("lulc_cropland_ha[-1]", "lulc_cropland_latest_ha")
        changed = True
    if new_expr != expr:
        condition["expression"] = new_expr
        signal["condition"] = condition
        changed = True
    if new_expr:
        new_vars = _vars_for_expression(new_expr)
        if signal.get("variables") != new_vars:
            signal["variables"] = new_vars
            changed = True
    return changed


def main() -> None:
    updated = 0
    for path in sorted(CARD_DIR.glob("*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        card_changed = False
        for signal in card.get("diagnostic_signals") or []:
            if isinstance(signal, dict) and _update_signal(signal):
                card_changed = True
        if card_changed:
            path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            updated += 1
            print("updated", path.name)
    print(f"Done — {updated} cards updated")


if __name__ == "__main__":
    main()
