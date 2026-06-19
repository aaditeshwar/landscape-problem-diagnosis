#!/usr/bin/env python3
"""Unit tests for confirmation_policy helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.confirmation_policy import (  # noqa: E402
    pathway_confidence_level,
    pathway_is_confirmed,
)
from services.evidence_note import pathway_status_from_evaluation  # noqa: E402

CARD_005_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "evidence_cards"
    / "raw"
    / "socio_economic__economic_hardship__multi_sector_vulnerability__005.json"
)


def _load_card_005() -> dict:
    with CARD_005_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _eval_with_true_signals(card: dict, true_ids: list[str]) -> dict:
    signals = []
    for sig_id in true_ids:
        signals.append(
            {
                "signal_id": sig_id,
                "direction": "confirms",
                "result": True,
                "status": "ok",
            }
        )
    return {
        "summary": {"confirms_true": len(true_ids), "rules_out_true": 0},
        "signals": signals,
    }


def test_card_005_policy_requires_two_primaries():
    card = _load_card_005()
    assert card.get("confirmation_policy"), "Run derive_confirmation_policy.py --apply --pilot-only first"

    one = _eval_with_true_signals(card, ["sig_03"])
    assert not pathway_is_confirmed(one, card)

    two = _eval_with_true_signals(card, ["sig_01", "sig_03"])
    assert pathway_is_confirmed(two, card)
    assert pathway_confidence_level(two, card) == "high"


def test_card_005_single_confirm_uncertain_in_status():
    card = _load_card_005()
    bundle = {
        "socio_economic/economic_hardship/multi_sector_vulnerability": {
            "present_variables": {},
            "missing_variables": [],
            "missing_variable_questions": [],
            "evidence_card": card,
        }
    }
    pathway_eval = {
        "socio_economic/economic_hardship/multi_sector_vulnerability": _eval_with_true_signals(card, ["sig_03"])
    }
    status = pathway_status_from_evaluation(pathway_eval, bundle)
    assert status["confirmed_pathways"] == []
    assert len(status["uncertain_pathways"]) == 1


def test_legacy_card_without_policy_still_confirms_one():
    pathway_eval = {
        "summary": {"confirms_true": 1},
        "signals": [{"signal_id": "sig_01", "direction": "confirms", "result": True, "status": "ok"}],
    }
    assert pathway_is_confirmed(pathway_eval, {}, evidence_note="At least two signals required for high confidence.")


def test_amplifiers_only_not_confirmed_with_policy():
    card = {
        "confirmation_policy": {
            "confirm_when": {"min_confirms_true": 1},
            "confidence_when": [{"level": "low", "default": True}],
        },
        "diagnostic_signals": [
            {"signal_id": "sig_02", "direction": "amplifies", "severity": "moderate"},
        ],
    }
    pathway_eval = {
        "summary": {"confirms_true": 0, "amplifies_true": 1},
        "signals": [{"signal_id": "sig_02", "direction": "amplifies", "result": True, "status": "ok"}],
    }
    assert not pathway_is_confirmed(pathway_eval, card)


def main() -> int:
    test_card_005_policy_requires_two_primaries()
    test_card_005_single_confirm_uncertain_in_status()
    test_legacy_card_without_policy_still_confirms_one()
    test_amplifiers_only_not_confirmed_with_policy()
    print("All confirmation policy tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
