#!/usr/bin/env python3
"""Unit tests for runtime signal expression evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.assembler import resolve_variable  # noqa: E402
from services.derived_variables import DROUGHT_DERIVED_VARIABLE_NAMES  # noqa: E402
from services.signal_evaluator import YearIndexedMapping, evaluate_expression  # noqa: E402
from services.variable_registry import normalize_expression  # noqa: E402

CASE_STUDY_DIR = ROOT / "data" / "raw_jsons"
CARD_DIR = ROOT / "data" / "evidence_cards" / "raw"


def _load_eval_context(export_path: Path) -> dict:
    export = json.loads(export_path.read_text(encoding="utf-8"))
    ctx = dict(export.get("present_variables") or {})
    ctx.update(export.get("derived_variables") or {})
    mws_stub = {
        "drought_causality": ctx.get("drought_causality") or ctx.get("drought_causality_json"),
        "drought_kharif": ctx.get("drought_weeks_severe") and {} or {},
    }
    for name in DROUGHT_DERIVED_VARIABLE_NAMES:
        if name not in ctx:
            value = resolve_variable(mws_stub, name)
            if value is not None:
                ctx[name] = value
    return ctx


def test_year_indexed_mapping_supports_negative_index():
    series = YearIndexedMapping({"2017": 1, "2018": 3, "2019": 5})
    assert series[-1] == 5
    assert series[0] == 1


def test_evaluate_normalized_drought_expression():
    mws = {
        "drought_causality": {
            "2024": {
                "mild": {"spi_score": 22.0, "mai_score": 6.0, "vci_score": 4.0},
                "severe_moderate": {},
            }
        }
    }
    ctx = {
        name: resolve_variable(mws, name)
        for name in (
            "drought_mild_spi_score_latest",
            "drought_mild_mai_score_latest",
            "drought_mild_vci_score_latest",
            "drought_severe_moderate_spi_score_latest",
            "drought_severe_moderate_path_score_latest",
        )
    }
    expr, _ = normalize_expression(
        "drought_causality.get('spi_kharif', 0) <= -1.0 and drought_causality.get('vci_kharif', 100) < 35"
    )
    result, error = evaluate_expression(expr, ctx)
    assert error is None
    assert isinstance(result, bool)


def test_drought_composite_signals_eval_on_case_study_export():
    sample_path = CASE_STUDY_DIR / "1_34623.json"
    if not sample_path.exists():
        return
    ctx = _load_eval_context(sample_path)
    errors: list[str] = []
    for card_path in sorted(CARD_DIR.glob("agriculture__water_scarcity__drought__*.json")):
        card = json.loads(card_path.read_text(encoding="utf-8"))
        for sig in card.get("diagnostic_signals", []):
            expr = (sig.get("condition") or {}).get("expression") or ""
            if "drought_mild_" not in expr and "drought_severe_moderate_" not in expr:
                continue
            patched, _ = normalize_expression(expr)
            result, err = evaluate_expression(patched, ctx)
            if err:
                errors.append(f"{card_path.stem} {sig.get('signal_id')}: {err}")
            else:
                assert isinstance(result, bool)
    assert errors == [], errors[:5]


def test_aquifer_class_percent_expression_with_missing_stored_percent():
    expr = (
        "(aquifer_class in ['volcanic', 'crystalline_basement', 'sedimentary_hard_rock']) "
        "and (acwadam_class_percent.get('alluvium', 0) < 20)"
    )
    result, error = evaluate_expression(
        expr,
        {"aquifer_class": "volcanic", "acwadam_class_percent": None},
    )
    assert error is None
    assert result is True


def test_drought_week_signals_use_year_indexing():
    sample_path = CASE_STUDY_DIR / "1_34623.json"
    if not sample_path.exists():
        return
    ctx = _load_eval_context(sample_path)
    expr = "drought_weeks_severe[-1] >= 2 or drought_weeks_moderate[-1] >= 4"
    result, error = evaluate_expression(expr, ctx)
    assert error is None
    assert isinstance(result, bool)
