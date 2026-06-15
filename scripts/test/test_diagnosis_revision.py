"""Unit tests for follow-up diagnosis revision helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.diagnosis_revision import (  # noqa: E402
    apply_follow_up_revision,
    apply_scoped_follow_up,
    build_retrieval_query,
    collect_pathway_interpretations,
    compute_diagnosis_revision,
    match_update_rule_excerpt,
    normalize_qualitative_answer,
)


def test_normalize_yes_worsening():
    out = normalize_qualitative_answer("forest_degradation_observed", "Yes, it has been worsening")
    assert out["present"] is True
    assert out["trend"] == "worsening"
    assert out["raw"] == "Yes, it has been worsening"


def test_normalize_no():
    out = normalize_qualitative_answer("borewell_density", "No, we don't have many borewells")
    assert out["present"] is False
    assert out["trend"] is None


def test_retrieval_query_includes_injected():
    q = build_retrieval_query(
        "wells drying up",
        {"borewell_density": {"raw": "many new borewells", "present": True}},
    )
    assert "wells drying up" in q
    assert "borewell_density" in q
    assert "many new borewells" in q


def test_revision_promotion():
    prior = {
        "confirmed_pathways": [],
        "uncertain_pathways": [{"pathway_id": "forest_degradation", "confidence": "medium"}],
        "solutions": [],
        "panel_updates": [],
    }
    current = {
        "confirmed_pathways": [{"pathway_id": "forest_degradation", "confidence": "high"}],
        "uncertain_pathways": [],
        "solutions": ["contour bunding"],
        "panel_updates": ["drought_weeks stacked_bar"],
        "panel_update_explanation": "Show drought stress.",
    }
    revision = compute_diagnosis_revision(prior, current, answered_variable="forest_degradation_observed")
    assert revision["improved"] is True
    assert any(c["from"] == "uncertain" and c["to"] == "confirmed" for c in revision["pathway_changes"])

    gated = apply_follow_up_revision(current, prior, answered_variable="forest_degradation_observed")
    assert gated["panel_updates"] == current["panel_updates"]


def test_revision_no_change_gates_panel_updates():
    prior = {
        "confirmed_pathways": [{"pathway_id": "groundwater_stress", "confidence": "high"}],
        "uncertain_pathways": [],
        "solutions": ["recharge structures"],
        "panel_updates": ["cropping_intensity + annual_delta_g_mm dual_axis"],
    }
    current = {
        "confirmed_pathways": [{"pathway_id": "groundwater_stress", "confidence": "high"}],
        "uncertain_pathways": [],
        "solutions": ["recharge structures"],
        "panel_updates": ["drought_weeks stacked_bar"],
    }
    revision = compute_diagnosis_revision(prior, current)
    assert revision["improved"] is False

    gated = apply_follow_up_revision(current, prior)
    assert gated["panel_updates"] == []
    assert gated["diagnosis_revision"]["improved"] is False


def test_parse_about_thirty_percent_irrigated_band():
    normalized = normalize_qualitative_answer("irrigated_area_ha", "About 30% is irrigated")
    assert normalized.get("band") == "mid"

    rule = (
        "If irrigated area is less than 10% of total cultivated land, this strongly confirms the rainfed risk pathway. "
        "If 10–30% is irrigated, the pathway is partially confirmed but groundwater stress or canal irrigation failure may be co-occurring. "
        "If more than 30% is irrigated, the rainfed risk pathway is weakened."
    )
    excerpt, matched = match_update_rule_excerpt(rule, normalized)
    assert matched is True
    assert "10–30" in excerpt or "10-30" in excerpt


def test_confidence_change_pathway_interpretation():
    prior = {
        "confirmed_pathways": [{"pathway_id": "rainfed_risk", "confidence": "low", "reasoning": ""}],
        "uncertain_pathways": [],
    }
    current = {
        "confirmed_pathways": [
            {
                "pathway_id": "rainfed_risk",
                "confidence": "high",
                "reasoning": "sig_03 TRUE after irrigated_area_ha follow-up.",
            }
        ],
        "uncertain_pathways": [],
    }
    items = collect_pathway_interpretations(
        current,
        "irrigated_area_ha",
        prior=prior,
        follow_up_updates=[
            {
                "pathway_id": "rainfed_risk",
                "signal_id": "sig_03",
                "variable": "irrigated_area_ha",
                "direction": "confirms",
                "result": True,
                "update_interpretation": "If 10–30% is irrigated, the pathway is partially confirmed.",
            }
        ],
    )
    assert len(items) == 1
    assert items[0]["status"] == "confirmed"
    assert "sig_03" in items[0]["reasoning"] or "partially confirmed" in items[0]["reasoning"]


def test_pick_next_follow_up_replaces_stale_llm_question():
    from services.reasoner import pick_next_follow_up

    bundle = {
        "multi_sector_vulnerability": {
            "missing_variables": ["migrant_household_percent"],
            "missing_variable_questions": [
                {
                    "missing_variable": "migrant_household_percent",
                    "question_to_user": "Migration question?",
                },
            ],
            "present_variables": {},
        },
        "groundwater_stress": {
            "missing_variables": ["annual_well_depth_m"],
            "missing_variable_questions": [
                {
                    "missing_variable": "annual_well_depth_m",
                    "question_to_user": "Well depth question?",
                },
            ],
            "present_variables": {},
        },
    }
    ranks = {"groundwater_stress": 0, "multi_sector_vulnerability": 2}
    response = {
        "confirmed_pathways": [
            {"pathway_id": "groundwater_stress", "confidence": "low"},
        ],
        "uncertain_pathways": [
            {"pathway_id": "multi_sector_vulnerability", "confidence": "uncertain"},
        ],
        "follow_up_question": "Well depth question?",
    }
    out = pick_next_follow_up(
        response,
        {},
        bundle=bundle,
        pathway_retrieval_ranks=ranks,
    )
    assert out.get("follow_up_variable") == "migrant_household_percent"
    assert out.get("follow_up_question") == "Migration question?"


def test_signal_confidence_guard_demotes_single_confirm_pathways():
    from services.reasoner import apply_signal_confidence_guard

    response = {
        "confirmed_pathways": [
            {"pathway_id": "encroachment", "confidence": "high", "reasoning": "sig_01 only"},
            {"pathway_id": "small_landholding", "confidence": "high", "reasoning": "sig_01 and sig_02"},
        ],
        "uncertain_pathways": [],
    }
    signal_eval = {
        "encroachment": {"summary": {"confirms_true": 1}},
        "small_landholding": {"summary": {"confirms_true": 2}},
    }
    bundle = {
        "encroachment": {
            "evidence_card": {
                "overall_reasoning_note": "confirmed by at least sig_01 plus one of sig_03 or sig_04",
            }
        },
        "small_landholding": {"evidence_card": {"overall_reasoning_note": "confirmed when two signals co-occur"}},
    }
    out = apply_signal_confidence_guard(response, signal_eval=signal_eval, bundle=bundle)
    confirmed_ids = {p["pathway_id"] for p in out["confirmed_pathways"]}
    uncertain_ids = {p["pathway_id"] for p in out["uncertain_pathways"]}
    assert "encroachment" not in confirmed_ids
    assert "encroachment" in uncertain_ids
    assert "small_landholding" in confirmed_ids
    sl = next(p for p in out["confirmed_pathways"] if p["pathway_id"] == "small_landholding")
    assert sl["confidence"] == "high"


def test_scoped_follow_up_freezes_unrelated_pathways():
    prior = {
        "confirmed_pathways": [{"pathway_id": "groundwater_stress", "confidence": "medium"}],
        "uncertain_pathways": [
            {"pathway_id": "multi_sector_vulnerability", "confidence": "low"},
            {"pathway_id": "encroachment", "confidence": "low"},
        ],
        "solutions": [],
    }
    current = {
        "confirmed_pathways": [
            {"pathway_id": "multi_sector_vulnerability", "confidence": "medium"},
            {"pathway_id": "encroachment", "confidence": "low"},
            {"pathway_id": "rainfed_risk", "confidence": "medium"},
        ],
        "uncertain_pathways": [],
        "solutions": [],
    }
    scoped = apply_scoped_follow_up(current, prior, "migrant_household_percent")
    confirmed_ids = {p["pathway_id"] for p in scoped["confirmed_pathways"]}
    uncertain_ids = {p["pathway_id"] for p in scoped["uncertain_pathways"]}
    assert "groundwater_stress" in confirmed_ids
    assert "multi_sector_vulnerability" in confirmed_ids
    assert "encroachment" in uncertain_ids
    assert "rainfed_risk" not in confirmed_ids

    revision = compute_diagnosis_revision(prior, scoped, answered_variable="migrant_household_percent")
    changed_ids = {c["pathway_id"] for c in revision["pathway_changes"]}
    assert "encroachment" not in changed_ids
    assert "rainfed_risk" not in changed_ids
    ms_change = next(c for c in revision["pathway_changes"] if c["pathway_id"] == "multi_sector_vulnerability")
    assert "migrant_household_percent" in ms_change["reason"]


def test_server_pathway_interpretation_stays_uncertain_with_one_confirm():
    signal_evaluation = {
        "groundwater_stress": {
            "summary": {"confirms_true": 1, "amplifies_true": 1},
            "evidence_note": (
                "Groundwater stress should be confirmed by at least two of the three primary signals."
            ),
            "signals": [
                {"signal_id": "sig_01", "direction": "confirms", "result": False, "status": "ok"},
                {
                    "signal_id": "sig_05",
                    "direction": "confirms",
                    "result": True,
                    "status": "user_provided",
                    "user_answer": "Yes, wells have been deepened",
                },
                {"signal_id": "sig_03", "direction": "amplifies", "result": True, "status": "ok"},
            ],
        }
    }
    prior = {
        "confirmed_pathways": [],
        "uncertain_pathways": [{"pathway_id": "groundwater_stress", "confidence": "low"}],
    }
    current = {
        "confirmed_pathways": [],
        "uncertain_pathways": [{"pathway_id": "groundwater_stress", "confidence": "medium"}],
    }
    items = collect_pathway_interpretations(
        current,
        "annual_well_depth_m",
        prior=prior,
        signal_evaluation=signal_evaluation,
        follow_up_updates=[
            {
                "pathway_id": "groundwater_stress",
                "signal_id": "sig_05",
                "variable": "annual_well_depth_m",
                "direction": "confirms",
                "result": True,
                "update_interpretation": "Well deepening strongly confirms groundwater stress.",
            }
        ],
    )
    assert len(items) == 1
    assert items[0]["status"] == "uncertain"
    reasoning = items[0]["reasoning"]
    assert "remains uncertain" in reasoning
    assert "1 of 2" in reasoning
    assert "high confidence" not in reasoning.lower()


def test_borewell_not_successful_infers_false():
    from services.diagnosis_revision import infer_user_signal_result

    normalized = normalize_qualitative_answer(
        "borewell_density",
        "Borewells are not successful in this area",
    )
    result = infer_user_signal_result(
        direction="confirms",
        normalized=normalized,
        update_excerpt="High borewell density strongly confirms groundwater stress.",
        update_rule="High borewell density strongly confirms groundwater stress.",
    )
    assert result is False


def main() -> int:
    tests = [
        test_normalize_yes_worsening,
        test_normalize_no,
        test_retrieval_query_includes_injected,
        test_revision_promotion,
        test_revision_no_change_gates_panel_updates,
        test_parse_about_thirty_percent_irrigated_band,
        test_confidence_change_pathway_interpretation,
        test_pick_next_follow_up_replaces_stale_llm_question,
        test_signal_confidence_guard_demotes_single_confirm_pathways,
        test_scoped_follow_up_freezes_unrelated_pathways,
        test_server_pathway_interpretation_stays_uncertain_with_one_confirm,
        test_borewell_not_successful_infers_false,
    ]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
