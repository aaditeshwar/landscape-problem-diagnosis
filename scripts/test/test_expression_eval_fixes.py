#!/usr/bin/env python3
"""Tests for signal expression evaluation fixes (name_error, normalized eval)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.signal_evaluator import evaluate_expression, evaluate_pathway_signals  # noqa: E402


def test_organization_domains_without_present_variable():
    expression = (
        "'Agroforestry' not in organization_domains and "
        "'Watershed management' not in organization_domains"
    )
    result, error = evaluate_expression(expression, {})
    assert error is None
    assert result is True


def test_canal_name_without_present_variable():
    result, error = evaluate_expression("canal_name is None", {})
    assert error is None
    assert result is True


def test_river_name_without_present_variable():
    result, error = evaluate_expression("river_name is None", {})
    assert error is None
    assert result is True


def test_mean_cropping_intensity_from_present_series():
    present = {
        "cropping_intensity": {"2020": 1.05, "2021": 1.08, "2022": 1.1},
        "mean_cropping_intensity": 1.08,
    }
    result, error = evaluate_expression("mean_cropping_intensity <= 1.15", present)
    assert error is None
    assert result is True


def test_evaluate_pathway_resolves_expression_variables():
    card = {
        "missing_variable_questions": [],
        "diagnostic_signals": [
            {
                "signal_id": "sig_02",
                "direction": "confirms",
                "condition": {"expression": "mean_cropping_intensity <= 1.15"},
            }
        ],
    }
    results = evaluate_pathway_signals(
        {
            "present_variables": {
                "cropping_intensity": {"2020": 1.05, "2021": 1.08},
                "mean_cropping_intensity": 1.08,
            },
            "evidence_card": card,
        }
    )
    sig = results["signals"][0]
    assert sig["status"] == "ok"
    assert sig["result"] is True


if __name__ == "__main__":
    test_organization_domains_without_present_variable()
    test_canal_name_without_present_variable()
    test_river_name_without_present_variable()
    test_mean_cropping_intensity_from_present_series()
    test_evaluate_pathway_resolves_expression_variables()
    print("All expression eval fix tests passed.")
