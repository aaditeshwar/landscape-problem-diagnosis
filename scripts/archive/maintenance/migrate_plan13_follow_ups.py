#!/usr/bin/env python3
"""Plan 13 follow-up migration: question_mode, effects from MCQ templates (archived one-off)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"

sys.path.insert(0, str(ROOT / "runtime"))
from services.follow_up_mcq import MCQ_TEMPLATES  # noqa: E402

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
    "forest_fire_frequency": "presence_graded",
}


def _template_choice_map(variable: str) -> dict[str, dict]:
    template = MCQ_TEMPLATES.get(variable) or {}
    out: dict[str, dict] = {}
    for choice in template.get("choices") or []:
        if isinstance(choice, dict):
            cid = str(choice.get("id") or "").strip()
            if cid:
                out[cid] = choice
    return out


def _signal_ids_for_variable(card: dict, variable: str) -> list[str]:
    ids: list[str] = []
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        if signal.get("active") is False:
            continue
        vars_ = [str(v) for v in (signal.get("variables") or [])]
        if variable in vars_:
            sig_id = str(signal.get("signal_id") or "").strip()
            if sig_id:
                ids.append(sig_id)
    return ids


def _effects_for_choice(
    card: dict,
    variable: str,
    choice_id: str,
    template_choice: dict | None,
) -> dict | None:
    confirms_result = None
    if template_choice and "confirms_result" in template_choice:
        confirms_result = template_choice.get("confirms_result")
    if confirms_result is None:
        return None
    signal_ids = _signal_ids_for_variable(card, variable)
    if not signal_ids:
        return None
    return {
        "signals": [
            {"signal_id": sig_id, "result": bool(confirms_result)}
            for sig_id in signal_ids
        ]
    }


def _infer_question_mode(variable: str, question: dict) -> str:
    if question.get("question_mode"):
        return str(question["question_mode"])
    if variable in VARIABLE_QUESTION_MODE:
        return VARIABLE_QUESTION_MODE[variable]
    choices = question.get("choices") or []
    if not choices:
        return "magnitude"
    keys = set()
    for choice in choices:
        keys |= set((choice.get("normalized") or {}).keys())
    if "trend" in keys and "band" not in keys:
        return "trend"
    if keys <= {"present"} or keys == {"present"}:
        return "presence_binary"
    if "band" in keys:
        return "magnitude"
    return "presence_graded"


def migrate_card(card: dict) -> tuple[dict, int]:
    changes = 0
    template_vars = set(MCQ_TEMPLATES.keys())

    for question in card.get("missing_variable_questions") or []:
        if not isinstance(question, dict):
            continue
        if question.get("response_type") != "mcq":
            continue
        variable = str(question.get("missing_variable") or "").strip()
        mode = _infer_question_mode(variable, question)
        if variable in VARIABLE_QUESTION_MODE:
            mode = VARIABLE_QUESTION_MODE[variable]
        if question.get("question_mode") != mode:
            question["question_mode"] = mode
            changes += 1

        template_choices = _template_choice_map(variable)
        for choice in question.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            choice_id = str(choice.get("id") or "").strip()
            template_choice = template_choices.get(choice_id)
            if variable in template_vars or template_choice:
                effects = _effects_for_choice(card, variable, choice_id, template_choice)
                if effects and choice.get("effects") != effects:
                    choice["effects"] = effects
                    changes += 1

    return card, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-id", help="Migrate one card")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths = sorted(RAW_DIR.glob("*.json"))
    if args.card_id:
        paths = [RAW_DIR / f"{args.card_id}.json"]

    total_changes = 0
    for path in paths:
        if not path.exists():
            print(f"Missing: {path}")
            return 1
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        card, changes = migrate_card(card)
        if changes:
            print(f"{card.get('card_id')}: {changes} change(s)")
            total_changes += changes
            if not args.dry_run:
                with path.open("w", encoding="utf-8") as handle:
                    json.dump(card, handle, indent=2, ensure_ascii=False)
                    handle.write("\n")

    print(f"Done. {total_changes} total field updates across {len(paths)} card(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
