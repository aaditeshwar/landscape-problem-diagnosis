#!/usr/bin/env python3
"""Validate MCQ normalized blocks and question_mode on evidence cards."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"

ALLOWED_NORMALIZED_KEYS = frozenset(
    {"band", "present", "trend", "percent_lower", "percent_upper", "variable", "raw", "choice_id"}
)
ALLOWED_BANDS = frozenset({"low", "moderate", "high"})
ALLOWED_TRENDS = frozenset({"stable", "worsening", "improving"})
QUESTION_MODES = frozenset({"magnitude", "presence_graded", "trend", "presence_binary"})

VARIABLE_QUESTION_MODE = {
    "annual_well_depth_m": "trend",
    "groundwater_salinity": "presence_graded",
    "tank_siltation_status": "presence_graded",
    "fra_claims_filed_count": "presence_graded",
    "forest_boundary_demarcation_status": "presence_graded",
    "forest_patch_connectivity": "presence_graded",
    "community_forest_governance_status": "presence_graded",
    "market_price_crop": "magnitude",
    "ntfp_collection_trend_qualitative": "magnitude",
    "irrigated_area_ha": "magnitude",
    "borewell_density": "magnitude",
    "household_income_inr": "magnitude",
    "migrant_household_percent": "magnitude",
    "landholding_size_distribution": "magnitude",
    "ntfp_species_presence": "magnitude",
    "groundwater_salinity": "presence_graded",
    "forest_fire_frequency": "presence_graded",
}


def _validate_normalized(normalized: dict, *, mode: str, choice_id: str, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(normalized, dict):
        return [f"{path} choice {choice_id}: normalized must be an object"]

    unknown = set(normalized.keys()) - ALLOWED_NORMALIZED_KEYS
    if unknown:
        errors.append(f"{path} choice {choice_id}: unknown normalized keys {sorted(unknown)}")

    band = normalized.get("band")
    if band is not None and str(band) not in ALLOWED_BANDS:
        errors.append(f"{path} choice {choice_id}: invalid band {band!r}")

    trend = normalized.get("trend")
    if trend is not None and str(trend) not in ALLOWED_TRENDS:
        errors.append(f"{path} choice {choice_id}: invalid trend {trend!r}")

    present = normalized.get("present")
    if present is not None and not isinstance(present, bool):
        errors.append(f"{path} choice {choice_id}: present must be boolean")

    if mode == "magnitude":
        if present is not True:
            errors.append(f"{path} choice {choice_id}: magnitude mode requires present=true")
        if band is None:
            errors.append(f"{path} choice {choice_id}: magnitude mode requires band")
    elif mode == "trend":
        if trend is None:
            errors.append(f"{path} choice {choice_id}: trend mode requires trend")
        if present is None:
            errors.append(f"{path} choice {choice_id}: trend mode requires present")
    elif mode == "presence_binary":
        if present is None:
            errors.append(f"{path} choice {choice_id}: presence_binary requires present")
        if band is not None or trend is not None:
            errors.append(f"{path} choice {choice_id}: presence_binary must not use band/trend")
    elif mode == "presence_graded":
        if present is None:
            errors.append(f"{path} choice {choice_id}: presence_graded requires present")
        if present is True and band is None:
            errors.append(f"{path} choice {choice_id}: presence_graded requires band when present=true")

    return errors


def audit_card(card: dict, *, path: str, require_effects: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for question in card.get("missing_variable_questions") or []:
        if not isinstance(question, dict):
            continue
        if question.get("response_type") != "mcq":
            continue
        variable = str(question.get("missing_variable") or "").strip()
        mode = str(question.get("question_mode") or VARIABLE_QUESTION_MODE.get(variable) or "").strip()
        if not mode:
            warnings.append(f"{path} {variable}: missing question_mode")
            continue
        if mode not in QUESTION_MODES:
            errors.append(f"{path} {variable}: invalid question_mode {mode!r}")

        choices = question.get("choices") or []
        if not choices:
            errors.append(f"{path} {variable}: MCQ has no choices")
            continue

        for choice in choices:
            if not isinstance(choice, dict):
                continue
            choice_id = str(choice.get("id") or "?")
            errors.extend(
                _validate_normalized(
                    choice.get("normalized") or {},
                    mode=mode,
                    choice_id=choice_id,
                    path=f"{path} {variable}",
                )
            )
            if require_effects and not (choice.get("effects") or {}).get("signals"):
                warnings.append(f"{path} {variable} choice {choice_id}: missing effects.signals")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-id", help="Audit a single card_id")
    parser.add_argument("--require-effects", action="store_true", help="Warn when MCQ choices lack effects")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    paths = sorted(RAW_DIR.glob("*.json"))
    if args.card_id:
        paths = [RAW_DIR / f"{args.card_id}.json"]

    total_errors: list[str] = []
    total_warnings: list[str] = []

    for path in paths:
        if not path.exists():
            print(f"Missing card file: {path}", file=sys.stderr)
            return 1
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        errors, warnings = audit_card(
            card,
            path=card.get("card_id") or path.name,
            require_effects=args.require_effects,
        )
        total_errors.extend(errors)
        total_warnings.extend(warnings)

    for line in total_warnings:
        print(f"WARN: {line}")
    for line in total_errors:
        print(f"ERROR: {line}", file=sys.stderr)

    if total_errors:
        return 1
    if args.strict and total_warnings:
        return 1

    print(f"audit_mcq_normalized: OK ({len(paths)} cards, {len(total_warnings)} warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
