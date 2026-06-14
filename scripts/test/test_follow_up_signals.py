"""Tests for follow-up answer integration into signal evaluation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.diagnosis_revision import (  # noqa: E402
    apply_ruled_out_guard,
    apply_scoped_follow_up,
    apply_user_rule_out,
    collect_pathway_interpretations,
    match_update_rule_excerpt,
    normalize_qualitative_answer,
    pathways_ruled_out_from_signal_evaluation,
)
from services.signal_evaluator import (  # noqa: E402
    collect_follow_up_signal_updates,
    evaluate_bundle_signals,
)


GW_CARD = {
    "overall_reasoning_note": "Confirm with at least two primary signals.",
    "missing_variable_questions": [
        {
            "missing_variable": "annual_well_depth_m",
            "how_answer_updates_diagnosis": (
                "A reported increase in well depth strongly confirms the groundwater stress pathway. "
                "Seasonal dug-well failure is a near-definitive confirmation."
            ),
        }
    ],
    "diagnostic_signals": [
        {
            "signal_id": "sig_05",
            "direction": "confirms",
            "variables": ["annual_well_depth_m"],
            "condition": {
                "type": "qualitative",
                "qualitative_description": "Farmers report well deepening or seasonal well failure.",
            },
        }
    ],
}

MS_CARD = {
    "missing_variable_questions": [
        {
            "missing_variable": "migrant_household_percent",
            "how_answer_updates_diagnosis": (
                "If more than 30% of households have out-migrants, this strongly confirms multi-sector vulnerability. "
                "If migration is below 10%, the hardship may be more acute (recent shock) than chronic structural vulnerability."
            ),
        }
    ],
    "diagnostic_signals": [
        {
            "signal_id": "sig_05",
            "direction": "confirms",
            "variables": ["migrant_household_percent"],
            "condition": {"type": "qualitative", "qualitative_description": "High out-migration confirms hardship."},
        }
    ],
}


def test_well_deepening_becomes_user_provided_true():
    injected = {
        "annual_well_depth_m": normalize_qualitative_answer(
            "annual_well_depth_m",
            "Yes more deepening has been required and shallow wells have gone dry",
        )
    }
    results = evaluate_bundle_signals({"groundwater_stress": {"evidence_card": GW_CARD}}, injected=injected)
    pathway = results["groundwater_stress"]
    sig = pathway["signals"][0]
    assert sig["status"] == "user_provided"
    assert sig["result"] is True
    assert pathway["summary"]["confirms_true"] == 1
    assert pathway["summary"]["needs_llm"] == 0
    assert "strongly confirms" in sig["update_interpretation"].lower()


def test_migration_low_band_uses_matching_card_sentence():
    normalized = normalize_qualitative_answer("migrant_household_percent", "Less than 10%")
    assert normalized.get("band") == "low"
    rule = MS_CARD["missing_variable_questions"][0]["how_answer_updates_diagnosis"]
    excerpt = match_update_rule_excerpt(rule, normalized)
    assert isinstance(excerpt, tuple)
    assert "below 10" in excerpt[0].lower()
    assert excerpt[1] is True

    injected = {"migrant_household_percent": normalized}
    results = evaluate_bundle_signals(
        {"multi_sector_vulnerability": {"evidence_card": MS_CARD}},
        injected=injected,
    )
    sig = results["multi_sector_vulnerability"]["signals"][0]
    assert sig["status"] == "user_provided"
    assert sig["result"] is True
    assert "acute" in sig["update_interpretation"].lower()


def test_collect_follow_up_signal_updates():
    injected = {
        "annual_well_depth_m": normalize_qualitative_answer(
            "annual_well_depth_m",
            "Yes, wells are deepening",
        )
    }
    results = evaluate_bundle_signals({"groundwater_stress": {"evidence_card": GW_CARD}}, injected=injected)
    updates = collect_follow_up_signal_updates(results, "annual_well_depth_m")
    assert len(updates) == 1
    assert updates[0]["pathway_id"] == "groundwater_stress"
    assert updates[0]["update_interpretation"]


def test_user_rule_out_removes_uncertain_groundwater():
    current = {
        "confirmed_pathways": [],
        "uncertain_pathways": [{"pathway_id": "groundwater_stress", "confidence": "low"}],
    }
    signal_eval = evaluate_bundle_signals(
        {"groundwater_stress": {"evidence_card": GW_CARD}},
        injected={
            "annual_well_depth_m": normalize_qualitative_answer(
                "annual_well_depth_m",
                "No, such reports have not been seen",
            )
        },
    )
    ruled = apply_user_rule_out(
        current,
        "annual_well_depth_m",
        signal_evaluation=signal_eval,
    )
    assert ruled["uncertain_pathways"] == []
    assert ruled["confirmed_pathways"] == []


def test_collect_pathway_interpretations_skips_unchanged_confirmed():
    prior = {
        "confirmed_pathways": [{"pathway_id": "irrigation_challenges", "confidence": "medium"}],
        "uncertain_pathways": [{"pathway_id": "groundwater_stress", "confidence": "low"}],
    }
    current = {
        "confirmed_pathways": [
            {
                "pathway_id": "irrigation_challenges",
                "confidence": "medium",
                "reasoning": "sig_01 TRUE — irrigation failure.",
            }
        ],
        "uncertain_pathways": [],
    }
    signal_eval = evaluate_bundle_signals(
        {"groundwater_stress": {"evidence_card": GW_CARD}},
        injected={
            "annual_well_depth_m": normalize_qualitative_answer(
                "annual_well_depth_m",
                "No, such reports have not been seen",
            )
        },
    )
    items = collect_pathway_interpretations(
        current,
        "annual_well_depth_m",
        prior=prior,
        signal_evaluation=signal_eval,
    )
    ids = {item["pathway_id"]: item["status"] for item in items}
    assert ids.get("groundwater_stress") == "ruled_out"
    assert "irrigation_challenges" not in ids


def test_user_rule_out_keeps_pathway_when_confirms_true_remain():
    prior = {
        "confirmed_pathways": [{"pathway_id": "groundwater_stress", "confidence": "medium"}],
        "uncertain_pathways": [],
    }
    current = {
        "confirmed_pathways": [],
        "uncertain_pathways": [{"pathway_id": "groundwater_stress", "confidence": "low"}],
    }
    signal_eval = evaluate_bundle_signals(
        {"groundwater_stress": {"evidence_card": GW_CARD}},
        injected={
            "annual_well_depth_m": normalize_qualitative_answer(
                "annual_well_depth_m",
                "Yes, wells are deepening",
            )
        },
    )
    scoped = apply_scoped_follow_up(
        current,
        prior,
        "annual_well_depth_m",
        signal_evaluation=signal_eval,
    )
    confirmed = {p["pathway_id"] for p in scoped["confirmed_pathways"]}
    assert "groundwater_stress" in confirmed


def test_negative_well_answer_becomes_user_provided_false():
    injected = {
        "annual_well_depth_m": normalize_qualitative_answer(
            "annual_well_depth_m",
            "No, such reports have not been seen",
        )
    }
    results = evaluate_bundle_signals({"groundwater_stress": {"evidence_card": GW_CARD}}, injected=injected)
    sig = results["groundwater_stress"]["signals"][0]
    assert sig["status"] == "user_provided"
    assert sig["result"] is False
    assert sig["update_rule"]
    assert sig["inference"] == "evaluated"


def test_migration_about_thirty_percent_resolves_false():
    normalized = normalize_qualitative_answer("migrant_household_percent", "About 30%")
    assert normalized.get("band") == "mid"
    rule = MS_CARD["missing_variable_questions"][0]["how_answer_updates_diagnosis"]
    injected = {"migrant_household_percent": normalized}
    results = evaluate_bundle_signals(
        {"multi_sector_vulnerability": {"evidence_card": MS_CARD}},
        injected=injected,
    )
    sig = results["multi_sector_vulnerability"]["signals"][0]
    assert sig["status"] == "user_provided"
    assert sig["result"] is False
    assert sig["inference"] == "evaluated"
    assert results["multi_sector_vulnerability"]["summary"]["confirms_true"] == 0


def test_unparseable_answer_stays_unresolved():
    injected = {
        "migrant_household_percent": normalize_qualitative_answer(
            "migrant_household_percent",
            "Most people stay here year-round; only a couple leave sometimes",
        )
    }
    results = evaluate_bundle_signals(
        {"multi_sector_vulnerability": {"evidence_card": MS_CARD}},
        injected=injected,
    )
    sig = results["multi_sector_vulnerability"]["signals"][0]
    assert sig["status"] == "user_provided_unresolved"
    assert sig["inference"] == "unable_to_evaluate"
    assert sig["result"] is None
    assert sig["user_answer"]
    assert sig["update_rule"]
    assert sig["inference_note"]
    assert results["multi_sector_vulnerability"]["summary"]["needs_llm"] == 1


def test_pathways_ruled_out_from_signal_evaluation():
    signal_eval = evaluate_bundle_signals(
        {"groundwater_stress": {"evidence_card": GW_CARD}},
        injected={
            "annual_well_depth_m": normalize_qualitative_answer(
                "annual_well_depth_m",
                "No, such reports have not been seen",
            )
        },
    )
    ruled_out = pathways_ruled_out_from_signal_evaluation(signal_eval)
    assert ruled_out == {"groundwater_stress"}


def test_apply_ruled_out_guard_blocks_llm_resurrection():
    prior = {
        "confirmed_pathways": [
            {"pathway_id": "irrigation_challenges", "confidence": "medium"},
            {"pathway_id": "multi_sector_vulnerability", "confidence": "medium"},
        ],
        "uncertain_pathways": [],
    }
    current = {
        "confirmed_pathways": prior["confirmed_pathways"],
        "uncertain_pathways": [
            {
                "pathway_id": "groundwater_stress",
                "confidence": "low",
                "reasoning": "LLM incorrectly re-opened GW after borewell answer.",
            }
        ],
    }
    signal_eval = evaluate_bundle_signals(
        {"groundwater_stress": {"evidence_card": GW_CARD}},
        injected={
            "annual_well_depth_m": normalize_qualitative_answer(
                "annual_well_depth_m",
                "No, such reports have not been seen",
            ),
            "borewell_density": normalize_qualitative_answer(
                "borewell_density",
                "No borewells exist in this area",
            ),
        },
    )
    scoped = apply_scoped_follow_up(
        current,
        prior,
        "borewell_density",
        signal_evaluation=signal_eval,
    )
    guarded = apply_ruled_out_guard(
        scoped,
        signal_evaluation=signal_eval,
        answered_variable="borewell_density",
    )
    uncertain_ids = {p["pathway_id"] for p in guarded["uncertain_pathways"]}
    assert "groundwater_stress" not in uncertain_ids


def test_apply_ruled_out_guard_allows_reconfirm_after_true_answer():
    prior = {
        "confirmed_pathways": [],
        "uncertain_pathways": [],
    }
    current = {
        "confirmed_pathways": [{"pathway_id": "groundwater_stress", "confidence": "medium"}],
        "uncertain_pathways": [],
    }
    signal_eval = evaluate_bundle_signals(
        {"groundwater_stress": {"evidence_card": GW_CARD}},
        injected={
            "annual_well_depth_m": normalize_qualitative_answer(
                "annual_well_depth_m",
                "Yes, wells are deepening",
            )
        },
    )
    scoped = apply_scoped_follow_up(
        current,
        prior,
        "annual_well_depth_m",
        signal_evaluation=signal_eval,
    )
    guarded = apply_ruled_out_guard(
        scoped,
        signal_evaluation=signal_eval,
        answered_variable="annual_well_depth_m",
    )
    confirmed_ids = {p["pathway_id"] for p in guarded["confirmed_pathways"]}
    assert "groundwater_stress" in confirmed_ids


def main() -> int:
    tests = [
        test_well_deepening_becomes_user_provided_true,
        test_migration_low_band_uses_matching_card_sentence,
        test_collect_follow_up_signal_updates,
        test_user_rule_out_removes_uncertain_groundwater,
        test_collect_pathway_interpretations_skips_unchanged_confirmed,
        test_user_rule_out_keeps_pathway_when_confirms_true_remain,
        test_negative_well_answer_becomes_user_provided_false,
        test_migration_about_thirty_percent_resolves_false,
        test_unparseable_answer_stays_unresolved,
        test_pathways_ruled_out_from_signal_evaluation,
        test_apply_ruled_out_guard_blocks_llm_resurrection,
        test_apply_ruled_out_guard_allows_reconfirm_after_true_answer,
    ]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
