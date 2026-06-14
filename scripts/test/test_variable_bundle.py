#!/usr/bin/env python3
"""Tests for present/missing variable bucketing in assemble_variable_bundle."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

import json

from services.assembler import assemble_variable_bundle  # noqa: E402
from services.reasoner import sanitize_uncertain_pathways  # noqa: E402
from services.signal_evaluator import evaluate_expression, evaluate_pathway_signals  # noqa: E402


RAINFED_CARD = {
    "card_id": "agriculture__water_scarcity__rainfed_risk__002",
    "production_system": "Agriculture",
    "observed_stress": "water_scarcity",
    "causal_pathway": "rainfed_risk",
    "diagnostic_signals": [
        {
            "signal_id": "sig_03",
            "condition": {"expression": "canal_name is None and nrega_irrigation_count < 3"},
        }
    ],
    "missing_variable_questions": [],
}

MSV_CARD = {
    "card_id": "socio_economic__economic_hardship__multi_sector_vulnerability__003",
    "production_system": "Socio_Economic",
    "observed_stress": "economic_hardship",
    "causal_pathway": "multi_sector_vulnerability",
    "diagnostic_signals": [
        {
            "signal_id": "sig_org",
            "condition": {
                "expression": (
                    "'Watershed management' not in organization_domains and "
                    "'Agroforestry' not in organization_domains"
                )
            },
        }
    ],
    "missing_variable_questions": [],
}


def test_list_var_absent_goes_to_present_as_empty_list():
    mws = {"uid": "test_mws"}
    bundle = assemble_variable_bundle(mws, [MSV_CARD])
    entry = bundle["multi_sector_vulnerability"]
    assert "organization_domains" in entry["present_variables"]
    assert entry["present_variables"]["organization_domains"] == []
    assert "organization_domains" not in entry["missing_variables"]


def test_canal_absent_goes_to_present_as_none():
    mws = {"uid": "test_mws", "nrega_irrigation_count": 0}
    bundle = assemble_variable_bundle(mws, [RAINFED_CARD])
    entry = bundle["rainfed_risk"]
    assert "canal_name" in entry["present_variables"]
    assert entry["present_variables"]["canal_name"] is None
    assert "canal_name" not in entry["missing_variables"]


def test_canal_present_empty_name_stays_in_present():
    mws = {"uid": "test_mws", "canal": {"canal_name": "", "project_name": ""}}
    bundle = assemble_variable_bundle(mws, [RAINFED_CARD])
    entry = bundle["rainfed_risk"]
    assert entry["present_variables"]["canal_name"] == ""
    assert "canal_name" not in entry["missing_variables"]


def test_river_name_absent_goes_to_present_as_none():
    mws = {"uid": "test_mws"}
    bundle = assemble_variable_bundle(
        mws,
        [
            {
                **RAINFED_CARD,
                "causal_pathway": "irrigation_challenges",
                "card_id": "agriculture__water_scarcity__irrigation_challenges__001",
            }
        ],
    )
    entry = bundle["irrigation_challenges"]
    assert entry["present_variables"]["river_name"] is None
    assert "river_name" not in entry["missing_variables"]


def test_canal_name_is_none_evaluates_from_bundle_present():
    mws = {"uid": "test_mws"}
    bundle = assemble_variable_bundle(mws, [RAINFED_CARD])
    present = bundle["rainfed_risk"]["present_variables"]
    result, error = evaluate_expression("canal_name is None", present)
    assert error is None
    assert result is True


def test_canal_name_is_not_none_when_canal_key_exists():
    mws = {"uid": "test_mws", "canal": {"canal_name": ""}}
    bundle = assemble_variable_bundle(mws, [RAINFED_CARD])
    present = bundle["rainfed_risk"]["present_variables"]
    result, error = evaluate_expression("canal_name is None", present)
    assert error is None
    assert result is False


def test_msv_drought_return_period_present_when_no_severe_events():
    card = json.loads(
        Path("data/evidence_cards/raw/socio_economic__economic_hardship__multi_sector_vulnerability__001.json").read_text(
            encoding="utf-8"
        )
    )
    mws = {
        "uid": "4_122144",
        "drought_kharif": {str(y): {"severe_weeks": 0, "moderate_weeks": 0} for y in range(2017, 2025)},
    }
    bundle = assemble_variable_bundle(mws, [card])
    entry = bundle["multi_sector_vulnerability"]
    assert entry["present_variables"]["drought_severe_return_period"] == 8.0
    assert "drought_severe_return_period" not in entry["missing_variables"]
    assert "drought_severe_return_period" in entry["missing_signal_only_variables"] or (
        "drought_severe_return_period" not in entry["missing_variables"]
    )
    assert "migrant_household_percent" in entry["missing_variables"]
    assert "migrant_household_percent" not in entry["missing_signal_only_variables"]


def test_msv_sig_01_evaluates_without_name_error():
    card = json.loads(
        Path("data/evidence_cards/raw/socio_economic__economic_hardship__multi_sector_vulnerability__001.json").read_text(
            encoding="utf-8"
        )
    )
    mws = {
        "uid": "4_122144",
        "drought_kharif": {str(y): {"severe_weeks": 0} for y in range(2017, 2025)},
    }
    bundle = assemble_variable_bundle(mws, [card])
    entry = bundle["multi_sector_vulnerability"]
    results = evaluate_pathway_signals(entry)
    sig = next(s for s in results["signals"] if s["signal_id"] == "sig_01")
    assert sig["status"] == "ok"
    assert sig["result"] is False


def test_sanitize_uncertain_strips_invented_questions():
    card = json.loads(
        Path("data/evidence_cards/raw/socio_economic__economic_hardship__multi_sector_vulnerability__001.json").read_text(
            encoding="utf-8"
        )
    )
    mws = {"uid": "4_122144"}
    bundle = assemble_variable_bundle(mws, [card])
    parsed = {
        "confirmed_pathways": [],
        "uncertain_pathways": [
            {
                "pathway_id": "multi_sector_vulnerability",
                "confidence": "uncertain",
                "missing_variable_questions": [
                    {
                        "variable": "drought_severe_return_period",
                        "question": "How frequently do severe droughts occur?",
                    }
                ],
            }
        ],
        "follow_up_question": "How frequently do severe droughts occur?",
    }
    out = sanitize_uncertain_pathways(parsed, bundle=bundle)
    questions = out["uncertain_pathways"][0]["missing_variable_questions"]
    assert all(q["variable"] != "drought_severe_return_period" for q in questions)
    assert any(q["variable"] == "migrant_household_percent" for q in questions)


if __name__ == "__main__":
    test_list_var_absent_goes_to_present_as_empty_list()
    test_canal_absent_goes_to_present_as_none()
    test_canal_present_empty_name_stays_in_present()
    test_river_name_absent_goes_to_present_as_none()
    test_canal_name_is_none_evaluates_from_bundle_present()
    test_canal_name_is_not_none_when_canal_key_exists()
    test_msv_drought_return_period_present_when_no_severe_events()
    test_msv_sig_01_evaluates_without_name_error()
    test_sanitize_uncertain_strips_invented_questions()
    print("All variable bundle tests passed.")
