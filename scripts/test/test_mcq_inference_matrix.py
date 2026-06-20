#!/usr/bin/env python3
"""Regression matrix: every MCQ choice must infer the declared confirms_result."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.diagnosis_revision import infer_user_signal_result, match_update_rule_excerpt  # noqa: E402
from services.follow_up_mcq import MCQ_TEMPLATES, mcq_confirms_result  # noqa: E402
from services.signal_evaluator import evaluate_bundle_signals  # noqa: E402

RAW = Path(__file__).resolve().parents[2] / "data" / "evidence_cards" / "raw"

# Representative card file per variable (first match in repo).
REPRESENTATIVE_CARDS: dict[str, str] = {
    "annual_well_depth_m": "agriculture__water_scarcity__groundwater_stress__001.json",
    "borewell_density": "agriculture__water_scarcity__groundwater_stress__001.json",
    "groundwater_salinity": "agriculture__water_scarcity__groundwater_stress__006.json",
    "irrigated_area_ha": "agriculture__water_scarcity__rainfed_risk__004.json",
    "tank_siltation_status": "agriculture__water_scarcity__irrigation_challenges__014.json",
    "migrant_household_percent": "socio_economic__economic_hardship__multi_sector_vulnerability__010.json",
    "household_income_inr": "socio_economic__low_income__small_landholding__003.json",
    "landholding_size_distribution": "socio_economic__low_income__small_landholding__003.json",
    "market_price_crop": "socio_economic__low_income__small_landholding__003.json",
    "ntfp_species_presence": "ntfp_forest_biodiversity__ntfp_decline__forest_degradation__017.json",
    "ntfp_collection_trend_qualitative": "ntfp_forest_biodiversity__ntfp_decline__encroachment__004.json",
    "fra_claims_filed_count": "ntfp_forest_biodiversity__ntfp_decline__encroachment__001.json",
    "forest_patch_connectivity": "ntfp_forest_biodiversity__ntfp_decline__encroachment__001.json",
    "forest_boundary_demarcation_status": "ntfp_forest_biodiversity__ntfp_decline__encroachment__010.json",
    "forest_fire_frequency": "ntfp_forest_biodiversity__ntfp_decline__forest_degradation__002.json",
    "community_forest_governance_status": "ntfp_forest_biodiversity__ntfp_decline__forest_degradation__008.json",
}


def _card_rule(variable: str) -> str:
    path = RAW / REPRESENTATIVE_CARDS[variable]
    card = json.loads(path.read_text(encoding="utf-8"))
    for question in card.get("missing_variable_questions") or []:
        if question.get("missing_variable") == variable:
            return str(question.get("how_answer_updates_diagnosis") or "")
    raise KeyError(f"No question for {variable} in {path.name}")


def _minimal_card(variable: str) -> dict:
    return {
        "missing_variable_questions": [
            {
                "missing_variable": variable,
                "how_answer_updates_diagnosis": _card_rule(variable),
            }
        ],
        "diagnostic_signals": [
            {
                "signal_id": "sig_mcq",
                "direction": "confirms",
                "variables": [variable],
                "condition": {"type": "qualitative", "qualitative_description": "User MCQ follow-up."},
            }
        ],
    }


def _payload(variable: str, choice: dict) -> dict:
    out = dict(choice["normalized"])
    out["variable"] = variable
    out["raw"] = choice["label"]
    out["choice_id"] = choice["id"]
    return out


def test_every_choice_has_confirms_result_declared():
    for variable, template in MCQ_TEMPLATES.items():
        for choice in template["choices"]:
            assert "confirms_result" in choice, f"{variable}/{choice['id']} missing confirms_result"


def test_mcq_confirms_result_lookup():
    assert mcq_confirms_result("annual_well_depth_m", "stable") is False
    assert mcq_confirms_result("annual_well_depth_m", "deepening") is True
    assert mcq_confirms_result("fra_claims_filed_count", "none") is True
    assert mcq_confirms_result("migrant_household_percent", "moderate") is False


def test_infer_matches_declared_result_on_representative_cards():
    failures: list[str] = []
    for variable, template in MCQ_TEMPLATES.items():
        if variable not in REPRESENTATIVE_CARDS:
            failures.append(f"{variable}: no representative card configured")
            continue
        rule = _card_rule(variable)
        for choice in template["choices"]:
            expected = choice["confirms_result"]
            payload = _payload(variable, choice)
            excerpt, matched = match_update_rule_excerpt(rule, payload)
            inferred = infer_user_signal_result(
                direction="confirms",
                normalized=payload,
                update_excerpt=excerpt,
                update_rule=rule,
            )
            if expected is None:
                continue
            if inferred != expected:
                failures.append(
                    f"{variable}/{choice['id']}: expected {expected}, got {inferred} "
                    f"(matched={matched}, excerpt={excerpt[:80]!r})"
                )
    if failures:
        raise AssertionError("MCQ inference mismatches:\n" + "\n".join(failures))


def test_signal_eval_overlay_matches_declared_result():
    failures: list[str] = []
    for variable, template in MCQ_TEMPLATES.items():
        if variable not in REPRESENTATIVE_CARDS:
            continue
        card = _minimal_card(variable)
        pathway_id = variable.split("_")[0] if False else "test_pathway"
        for choice in template["choices"]:
            expected = choice["confirms_result"]
            if expected is None:
                continue
            payload = _payload(variable, choice)
            results = evaluate_bundle_signals({pathway_id: {"evidence_card": card}}, injected={variable: payload})
            sig = results[pathway_id]["signals"][0]
            if sig.get("result") != expected:
                failures.append(
                    f"{variable}/{choice['id']}: signal result {sig.get('result')} != {expected} "
                    f"(status={sig.get('status')})"
                )
    if failures:
        raise AssertionError("Signal overlay mismatches:\n" + "\n".join(failures))


def test_moderate_band_matches_mid_excerpt():
    rule = "If between 10-30% is irrigated, the pathway is partially confirmed."
    payload = {
        "band": "moderate",
        "present": True,
        "percent_lower": 10,
        "percent_upper": 30,
        "variable": "irrigated_area_ha",
    }
    excerpt, matched = match_update_rule_excerpt(rule, payload)
    assert matched is True
    assert "partially" in excerpt.lower() or "10-30" in excerpt


def main() -> int:
    tests = [
        test_every_choice_has_confirms_result_declared,
        test_mcq_confirms_result_lookup,
        test_moderate_band_matches_mid_excerpt,
        test_infer_matches_declared_result_on_representative_cards,
        test_signal_eval_overlay_matches_declared_result,
    ]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
