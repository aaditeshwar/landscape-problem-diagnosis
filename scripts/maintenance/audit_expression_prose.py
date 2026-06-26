#!/usr/bin/env python3
"""Flag important mismatches between signal expressions and qualitative prose."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from lib.expression_audit import extract_ast_names  # noqa: E402

RAW = ROOT / "data" / "evidence_cards" / "raw"

VAR_ALIASES: dict[str, list[str]] = {
    "soge_dev_percent": ["soge", "stage of groundwater extraction", "extraction percent"],
    "soge_class_name": ["cgwb", "semi-critical", "critical", "over-exploited"],
    "drought_weeks_severe": ["severe drought week", "severe week"],
    "drought_weeks_moderate": ["moderate drought week", "moderate week"],
    "drought_severe_return_period": ["severe drought return period", "return period"],
    "drought_moderate_return_period": ["moderate drought return period"],
    "dry_spell_weeks": ["dry spell"],
    "nrega_swc_count": ["mgnrega", "nrega", "soil and water conservation", "swc"],
    "nrega_irrigation_count": ["irrigation works", "mgnrega irrigation"],
    "mean_annual_delta_g_mm": ["delta_g", "delta g", "groundwater recharge", "water balance"],
    "trend_annual_delta_g_mm": ["delta_g trend", "recharge trend"],
    "annual_well_depth_m": ["well depth", "borewell depth"],
    "cropping_intensity": ["cropping intensity"],
    "mean_cropping_intensity": ["cropping intensity"],
    "trend_cropping_intensity": ["cropping intensity trend"],
    "double_crop_area_ha": ["double crop", "double-crop", "double cropping"],
    "cd_total_degradation_ha": ["deforestation", "forest degradation", "degradation"],
    "lulc_forest_ha": ["forest area", "forest cover"],
    "water_body_total_area_ha": ["water body", "surface water"],
    "mean_annual_precipitation_mm": ["annual precipitation", "annual rainfall", "rainfall"],
    "mean_kharif_precipitation": ["kharif rainfall", "kharif precipitation", "kharif seasonal rainfall"],
    "trend_annual_precipitation_mm": ["precipitation trend", "rainfall trend"],
    "drought_mild_spi_score_latest": ["spi", "standardized precipitation"],
    "drought_mild_mai_score_latest": ["mai", "moisture adequacy"],
    "drought_mild_vci_score_latest": ["vci", "vegetation condition"],
    "acwadam_class_percent": ["alluvium", "alluvial", "lithology", "acwadam"],
    "aquifer_class": ["aquifer", "hard rock", "basalt", "crystalline"],
    "fra_claims_pending": ["fra claim", "pending claim"],
    "fra_claims_rejected": ["rejected claim", "rejected fra"],
    "fra_claims_recognized": ["recognized claim", "fra recognition"],
    "canal_irrigation_present": ["canal irrigation"],
}

NUM_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "fifteen": 15,
    "twenty": 20,
    "fifty": 50,
}


def prose_numbers(text: str) -> list[float]:
    nums: list[float] = []
    if not text:
        return nums
    lowered = text.lower()
    for match in re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%?", lowered):
        nums.append(float(match.group(1)))
    for word, value in NUM_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            nums.append(float(value))
    return nums


def extract_thresholds(expr: str) -> list[float]:
    values: list[float] = []
    if not expr:
        return values
    for match in re.finditer(r"(?:[<>]=?|==|!=)\s*(-?\d+(?:\.\d+)?)", expr):
        values.append(float(match.group(1)))
    for match in re.finditer(r"(-?\d+(?:\.\d+)?)\s*(?:[<>]=?)", expr):
        values.append(float(match.group(1)))
    return values


def var_mentioned_in_prose(var: str, prose: str) -> bool:
    if not prose:
        return False
    lowered = prose.lower()
    if var.lower() in lowered:
        return True
    for alias in VAR_ALIASES.get(var, []):
        if alias.lower() in lowered:
            return True
    if var.replace("_", " ") in lowered:
        return True
    return False


def threshold_mismatch(expr: str, prose: str) -> list[str]:
    issues: list[str] = []
    expr_thresholds = extract_thresholds(expr)
    prose_thresholds = prose_numbers(prose)
    if not expr_thresholds or not prose_thresholds:
        return issues
    for prose_value in prose_thresholds:
        if prose_value in {0, 1}:
            continue
        close = any(
            abs(prose_value - expr_value) <= max(0.5, 0.05 * abs(expr_value))
            for expr_value in expr_thresholds
        )
        if close:
            continue
        if prose_value <= 1 and any(abs(prose_value * 100 - expr_value) <= 1 for expr_value in expr_thresholds):
            continue
        if prose_value > 1 and any(abs(prose_value / 100 - expr_value) <= 0.01 for expr_value in expr_thresholds):
            continue
        issues.append(
            f"prose threshold ~{prose_value:g} does not match expression thresholds {expr_thresholds}"
        )
    return issues


def variable_mismatch(expr_vars: set[str], qual: str, declared: list[str]) -> list[str]:
    issues: list[str] = []
    declared_set = set(declared)

    if declared_set and declared_set.isdisjoint(expr_vars):
        issues.append(
            f"variables list {sorted(declared_set)} is disjoint from expression vars {sorted(expr_vars)}"
        )

    for var in sorted(expr_vars):
        if var in {"True", "False", "None"}:
            continue
        if not var_mentioned_in_prose(var, qual):
            if declared_set and var not in declared_set:
                issues.append(f"expression uses {var} not listed in signal.variables")
            elif declared_set and declared_set != expr_vars:
                mentioned_declared = [v for v in declared if var_mentioned_in_prose(v, qual)]
                if mentioned_declared and var not in mentioned_declared:
                    issues.append(
                        f"prose describes {mentioned_declared} but expression uses {var}"
                    )

    for var in declared:
        if var not in expr_vars and var_mentioned_in_prose(var, qual):
            issues.append(f"prose references {var} but expression uses {sorted(expr_vars)}")

    return issues


def direction_mismatch(expr: str, qual: str) -> list[str]:
    issues: list[str] = []
    lowered = qual.lower()
    if re.search(r"\bbelow\b|\bless than\b|\bunder\b", lowered):
        if re.search(r">=|>", expr) and not re.search(r"<=|<", expr):
            issues.append("prose says below/less than but expression only uses > or >=")
    if re.search(r"\babove\b|\bmore than\b|\bexceed", lowered):
        if re.search(r"<=|<", expr) and not re.search(r">=|>", expr):
            issues.append("prose says above/more than but expression only uses < or <=")
    return issues


def audit_signal(sig: dict) -> list[str]:
    if sig.get("active") is False:
        return []
    cond = sig.get("condition") or {}
    expr = (cond.get("expression") or sig.get("expression") or "").strip()
    if not expr:
        return []
    qual = str(cond.get("qualitative_description") or "")
    declared = sig.get("variables") or cond.get("variables") or []
    expr_vars = extract_ast_names(expr)

    issues: list[str] = []
    issues.extend(variable_mismatch(expr_vars, qual, declared))
    issues.extend(threshold_mismatch(expr, qual))
    issues.extend(direction_mismatch(expr, qual))
    return list(dict.fromkeys(issues))


def audit_cards(raw_dir: Path = RAW) -> list[dict]:
    findings: list[dict] = []
    for path in sorted(raw_dir.glob("*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        card_id = str(card.get("card_id") or path.stem)
        for sig in card.get("diagnostic_signals") or []:
            issues = audit_signal(sig)
            if not issues:
                continue
            cond = sig.get("condition") or {}
            findings.append(
                {
                    "card_id": card_id,
                    "signal_id": sig.get("signal_id", "?"),
                    "expression": (cond.get("expression") or sig.get("expression") or "")[:200],
                    "qualitative_description": str(cond.get("qualitative_description") or "")[:240],
                    "issues": issues,
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    findings = audit_cards()
    if args.json:
        print(json.dumps({"count": len(findings), "findings": findings}, indent=2, ensure_ascii=False))
        return 0

    print(f"expression/prose mismatches: {len(findings)} signal(s)")
    for row in findings:
        print(f"\n{row['card_id']} :: {row['signal_id']}")
        print(f"  expr: {row['expression']}")
        print(f"  qual: {row['qualitative_description']}")
        for issue in row["issues"]:
            print(f"  - {issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
