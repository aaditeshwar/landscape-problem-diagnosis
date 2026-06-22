"""Section-level signal evaluation and confusion-matrix assembly for triage."""

from __future__ import annotations

import copy
from typing import Any

from pymongo.database import Database

from services.assembler import assemble_variable_bundle, location_context
from services.built_pathways import (
    BUILT_PATHWAY_IDS,
    NONE_OF_THESE_PATHWAY,
    STRESS_ONLY_PATHWAY,
    built_pathways_for_section,
)
from services.evidence_note import pathway_status_from_evaluation
from services.expression_variable_access import (
    accesses_from_card,
    format_access_value,
    resolve_access_value,
)
from services.mws_export import ensure_mws_export
from services.production_system_gate import evaluate_production_system_gates
from services.reasoner import pathways_ruled_out_from_signal_evaluation
from services.signal_evaluator import evaluate_bundle_signals, merge_export_variables
from services.triage_card_map import load_mws_doc, resolve_cards_for_mws


def apply_card_edits(
    card: dict[str, Any],
    *,
    diagnostic_signals: list[dict[str, Any]] | None = None,
    confirmation_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = copy.deepcopy(card)
    if diagnostic_signals is not None:
        out["diagnostic_signals"] = diagnostic_signals
    if confirmation_policy is not None:
        out["confirmation_policy"] = confirmation_policy
    return out


def _confirmed_built_pathways(
    status: dict[str, list[dict[str, Any]]],
    *,
    allowed_pathways: set[str] | None = None,
) -> list[str]:
    confirmed = [
        str(item.get("pathway_id") or "")
        for item in status.get("confirmed_pathways") or []
        if isinstance(item, dict)
    ]
    built = [pid for pid in confirmed if pid in BUILT_PATHWAY_IDS]
    if allowed_pathways is not None:
        built = [pid for pid in built if pid in allowed_pathways]
    return built


def _pick_predicted_pathway(
    signal_eval: dict[str, dict[str, Any]],
    status: dict[str, list[dict[str, Any]]],
    *,
    allowed_pathways: set[str] | None = None,
) -> tuple[str, str]:
    def pathway_allowed(pathway_id: str) -> bool:
        return allowed_pathways is None or pathway_id in allowed_pathways

    uncertain = [
        str(item.get("pathway_id") or "")
        for item in status.get("uncertain_pathways") or []
        if isinstance(item, dict)
    ]
    built_confirmed = [
        pid for pid in _confirmed_built_pathways(status, allowed_pathways=allowed_pathways) if pathway_allowed(pid)
    ]
    if len(built_confirmed) == 1:
        return built_confirmed[0], "confirmed"
    if len(built_confirmed) > 1:
        built_confirmed.sort(
            key=lambda pid: int((signal_eval.get(pid) or {}).get("summary", {}).get("confirms_true") or 0),
            reverse=True,
        )
        return built_confirmed[0], "confirmed"

    return NONE_OF_THESE_PATHWAY, "not_confirmed"


def _pick_predicted_pathway_for_instance(
    prediction: dict[str, Any],
    instance: dict[str, Any],
    *,
    allowed_pathways: set[str] | None = None,
) -> tuple[str, str]:
    """Prefer catalog actual pathway when it is among confirmed pathways (triage tie-break)."""
    signal_eval = prediction.get("signal_eval") or {}
    status = prediction.get("status") or {}
    predicted, predicted_status = _pick_predicted_pathway(
        signal_eval,
        status,
        allowed_pathways=allowed_pathways,
    )
    if predicted_status != "confirmed":
        return predicted, predicted_status

    actual = _actual_pathway_for_instance(instance)
    if actual == STRESS_ONLY_PATHWAY:
        return predicted, predicted_status

    confirmed = _confirmed_built_pathways(status, allowed_pathways=allowed_pathways)
    if actual in confirmed:
        return actual, "confirmed"
    return predicted, predicted_status


def _actual_pathway_for_instance(instance: dict[str, Any]) -> str:
    if instance.get("stress_only"):
        return STRESS_ONLY_PATHWAY
    return str(instance.get("expected_pathway") or "")


def _matrix_match(instance: dict[str, Any], predicted_pathway: str, predicted_status: str) -> bool:
    actual = _actual_pathway_for_instance(instance)
    if actual == STRESS_ONLY_PATHWAY:
        return predicted_pathway == NONE_OF_THESE_PATHWAY
    if predicted_status != "confirmed":
        return False
    return actual == predicted_pathway


def evaluate_mws_prediction(
    db: Database,
    mws_doc: dict,
    *,
    card_edits: dict[str, dict[str, Any]],
    production_system: str,
    section_pathways: list[str] | None = None,
    for_triage: bool = False,
) -> dict[str, Any]:
    gate = evaluate_production_system_gates(mws_doc)
    eligible = set(gate.get("eligible_production_systems") or [])
    production_gated = production_system not in eligible
    if production_gated and not for_triage:
        return {
            "skipped": True,
            "skip_reason": "production_system_gated",
            "production_gated": True,
            "gate": gate,
            "predicted_pathway": NONE_OF_THESE_PATHWAY,
            "predicted_status": "not_confirmed",
            "signal_eval": {},
            "status": {"confirmed_pathways": [], "uncertain_pathways": []},
        }

    cards = resolve_cards_for_mws(db, mws_doc)
    edited_cards: list[dict[str, Any]] = []
    section_pathway_set = set(section_pathways or [])
    for pathway, card in cards.items():
        if section_pathway_set and pathway not in section_pathway_set:
            continue
        if str(card.get("production_system") or "") not in ("", production_system):
            continue
        card_id = str(card.get("card_id") or "")
        edits = card_edits.get(card_id) or {}
        edited_cards.append(
            apply_card_edits(
                card,
                diagnostic_signals=edits.get("diagnostic_signals"),
                confirmation_policy=edits.get("confirmation_policy"),
            )
        )

    bundle = assemble_variable_bundle(mws_doc, edited_cards)
    if section_pathway_set:
        bundle = {pid: data for pid, data in bundle.items() if pid in section_pathway_set}
    signal_eval = evaluate_bundle_signals(bundle)
    ruled_out = pathways_ruled_out_from_signal_evaluation(signal_eval)
    status = pathway_status_from_evaluation(
        signal_eval,
        bundle,
        location=location_context(mws_doc),
        ruled_out_ids=ruled_out,
    )
    predicted_pathway, predicted_status = _pick_predicted_pathway(
        signal_eval,
        status,
        allowed_pathways=section_pathway_set or None,
    )
    return {
        "skipped": False,
        "production_gated": production_gated,
        "gate": gate,
        "predicted_pathway": predicted_pathway,
        "predicted_status": predicted_status,
        "signal_eval": signal_eval,
        "status": status,
        "bundle": bundle,
        "cards": cards,
    }


def _instance_column_card(
    cards: dict[str, dict[str, Any]],
    instance: dict[str, Any],
    card_edits: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if instance.get("stress_only"):
        return None
    expected = str(instance.get("expected_pathway") or "")
    card = cards.get(expected)
    if not card:
        return None
    card_id = str(card.get("card_id") or "")
    edits = card_edits.get(card_id) or {}
    return apply_card_edits(
        card,
        diagnostic_signals=edits.get("diagnostic_signals"),
        confirmation_policy=edits.get("confirmation_policy"),
    )


def _signal_results_for_instance(
    prediction: dict[str, Any],
    instance: dict[str, Any],
    cards: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    expected = str(instance.get("expected_pathway") or "")
    if not expected:
        return []
    pathway_eval = (prediction.get("signal_eval") or {}).get(expected) or {}
    return list(pathway_eval.get("signals") or [])


def _instance_accesses_and_card(
    cards: dict[str, dict[str, Any]],
    instance: dict[str, Any],
    card_edits: dict[str, dict[str, Any]],
    *,
    section_pathways: list[str] | None = None,
) -> tuple[list[str], str | None]:
    """Return union of scalar access keys and a display card id for the instance column."""
    if instance.get("stress_only"):
        accesses: list[str] = []
        seen: set[str] = set()
        card_ids: list[str] = []
        for pathway in section_pathways or sorted(cards.keys()):
            card = cards.get(pathway)
            if not card:
                continue
            card_id = str(card.get("card_id") or "")
            edits = card_edits.get(card_id) or {}
            edited = apply_card_edits(
                card,
                diagnostic_signals=edits.get("diagnostic_signals"),
                confirmation_policy=edits.get("confirmation_policy"),
            )
            if card_id:
                card_ids.append(card_id)
            for key in accesses_from_card(edited):
                if key not in seen:
                    seen.add(key)
                    accesses.append(key)
        display_card = card_ids[0] if len(card_ids) == 1 else None
        return accesses, display_card

    card = _instance_column_card(cards, instance, card_edits)
    if not card:
        return [], None
    return accesses_from_card(card), str(card.get("card_id") or "") or None


def variable_table_for_instances(
    instances: list[dict[str, Any]],
    *,
    cards_by_mws: dict[str, dict[str, dict[str, Any]]],
    card_edits: dict[str, dict[str, Any]],
    exports_by_mws: dict[str, dict[str, Any]],
    section_pathways: list[str] | None = None,
) -> dict[str, Any]:
    columns: list[dict[str, Any]] = []
    access_keys: list[str] = []
    seen_access: set[str] = set()

    for instance in instances:
        mws_id = str(instance.get("mws_id") or "")
        cards = cards_by_mws.get(mws_id) or {}
        accesses, card_id = _instance_accesses_and_card(
            cards,
            instance,
            card_edits,
            section_pathways=section_pathways,
        )

        for key in accesses:
            if key not in seen_access:
                seen_access.add(key)
                access_keys.append(key)

        columns.append(
            {
                "case_study_id": instance.get("case_study_id"),
                "mws_id": mws_id,
                "state": instance.get("state"),
                "district": instance.get("district"),
                "tehsil": instance.get("tehsil"),
                "card_id": card_id,
                "accesses": accesses,
            }
        )

    rows: list[dict[str, Any]] = []
    for key in access_keys:
        row = {"access": key, "values": []}
        skip_row = False
        for instance, column in zip(instances, columns, strict=False):
            mws_id = str(instance.get("mws_id") or "")
            export = exports_by_mws.get(mws_id) or {}
            merged = merge_export_variables(export) if export else {}
            value = resolve_access_value(key, merged)
            if isinstance(value, (dict, list)):
                skip_row = True
                break
            row["values"].append(
                {
                    "case_study_id": instance.get("case_study_id"),
                    "mws_id": mws_id,
                    "formatted": format_access_value(value),
                    "raw": value,
                }
            )
        if skip_row:
            continue
        rows.append(row)

    return {"access_keys": access_keys, "columns": columns, "rows": rows}


def _actual_mws_ids_by_pathway(instances: list[dict[str, Any]]) -> dict[str, set[str]]:
    by_pathway: dict[str, set[str]] = {}
    for instance in instances:
        mws_id = str(instance.get("mws_id") or "").strip()
        if not mws_id:
            continue
        if instance.get("stress_only"):
            by_pathway.setdefault(STRESS_ONLY_PATHWAY, set()).add(mws_id)
            continue
        pathway = str(instance.get("expected_pathway") or "").strip()
        if pathway:
            by_pathway.setdefault(pathway, set()).add(mws_id)
    return by_pathway


def _pathway_confirmed_for_mws(
    prediction: dict[str, Any],
    pathway_id: str,
    *,
    allowed_pathways: set[str],
) -> bool:
    confirmed = _confirmed_built_pathways(
        prediction.get("status") or {},
        allowed_pathways=allowed_pathways,
    )
    return pathway_id in confirmed


def _binary_classification(*, is_actual: bool, predicted_positive: bool) -> str:
    if predicted_positive and is_actual:
        return "tp"
    if predicted_positive and not is_actual:
        return "fp"
    if not predicted_positive and is_actual:
        return "fn"
    return "tn"


def _instance_meta_by_mws(instances: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for instance in instances:
        mws_id = str(instance.get("mws_id") or "").strip()
        if mws_id and mws_id not in meta:
            meta[mws_id] = instance
    return meta


def _matrix_cells_binary_per_pathway(
    instances: list[dict[str, Any]],
    *,
    predictions_by_mws: dict[str, dict[str, Any]],
    section_pathways: list[str],
) -> list[dict[str, Any]]:
    """Per-pathway binary evaluation: all section MWS vs catalog actuals for that pathway."""
    by_pathway = _actual_mws_ids_by_pathway(instances)
    all_mws = sorted({str(item.get("mws_id") or "").strip() for item in instances if item.get("mws_id")})
    mws_meta = _instance_meta_by_mws(instances)
    section_pathway_set = set(section_pathways)
    cells: list[dict[str, Any]] = []

    for pathway_id in section_pathways:
        actual_mws = by_pathway.get(pathway_id, set())
        for mws_id in all_mws:
            instance = mws_meta[mws_id]
            prediction = predictions_by_mws.get(mws_id) or {}
            is_actual = mws_id in actual_mws
            predicted_positive = _pathway_confirmed_for_mws(
                prediction,
                pathway_id,
                allowed_pathways=section_pathway_set,
            )
            classification = _binary_classification(
                is_actual=is_actual,
                predicted_positive=predicted_positive,
            )
            predicted_col = pathway_id if predicted_positive else NONE_OF_THESE_PATHWAY
            cells.append(
                {
                    "matrix_row_pathway": pathway_id,
                    "actual_pathway": pathway_id,
                    "predicted_pathway": predicted_col,
                    "classification": classification,
                    "instance": {
                        "case_study_id": instance.get("case_study_id"),
                        "mws_id": mws_id,
                        "tehsil": instance.get("tehsil"),
                        "state": instance.get("state"),
                        "district": instance.get("district"),
                        "catalog_pathway": _actual_pathway_for_instance(instance),
                        "match": classification == "tp",
                        "predicted_status": "confirmed" if predicted_positive else "not_confirmed",
                    },
                }
            )

    return cells


def _unique_instances_by_mws(instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for instance in instances:
        mws_id = str(instance.get("mws_id") or "").strip()
        if mws_id and mws_id not in seen:
            seen[mws_id] = instance
    return list(seen.values())


def signal_grid_for_section(
    section_pathways: list[str],
    instances: list[dict[str, Any]],
    *,
    cards_by_mws: dict[str, dict[str, dict[str, Any]]],
    predictions_by_mws: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Per-pathway card columns with MWS eval cells for the unified signal table."""
    pathways_out: list[dict[str, Any]] = []
    all_mws = sorted({str(item.get("mws_id") or "").strip() for item in instances if item.get("mws_id")})
    mws_meta = _instance_meta_by_mws(instances)
    by_pathway = _actual_mws_ids_by_pathway(instances)
    section_pathway_set = set(section_pathways)

    for pathway in section_pathways:
        card_blocks: dict[str, dict[str, Any]] = {}
        actual_mws = by_pathway.get(pathway, set())

        for mws_id in all_mws:
            instance = mws_meta[mws_id]
            cards = cards_by_mws.get(mws_id) or {}
            card = cards.get(pathway)
            if not card:
                continue

            prediction = predictions_by_mws.get(mws_id) or {}
            pathway_eval = (prediction.get("signal_eval") or {}).get(pathway) or {}
            signals = list(pathway_eval.get("signals") or [])
            is_actual = mws_id in actual_mws
            pathway_confirmed = _pathway_confirmed_for_mws(
                prediction,
                pathway,
                allowed_pathways=section_pathway_set,
            )
            classification = _binary_classification(
                is_actual=is_actual,
                predicted_positive=pathway_confirmed,
            )
            actual_pathway = _actual_pathway_for_instance(instance)

            card_id = str(card.get("card_id") or "")
            block = card_blocks.setdefault(
                card_id,
                {"card_id": card_id, "mws_columns": [], "_mws_seen": set()},
            )
            if mws_id in block["_mws_seen"]:
                continue
            block["_mws_seen"].add(mws_id)
            block["mws_columns"].append(
                {
                    "mws_id": mws_id,
                    "case_study_id": instance.get("case_study_id"),
                    "state": instance.get("state"),
                    "district": instance.get("district"),
                    "tehsil": instance.get("tehsil"),
                    "actual_pathway": actual_pathway,
                    "actual_matches_pathway": is_actual,
                    "pathway_confirmed": pathway_confirmed,
                    "classification": classification,
                    "production_gated": bool(prediction.get("production_gated")),
                    "signals": {
                        str(item.get("signal_id") or ""): {
                            "result": item.get("result"),
                            "status": item.get("status"),
                            "variable_values": item.get("variable_values") or [],
                        }
                        for item in signals
                        if item.get("signal_id")
                    },
                }
            )

        cards_list: list[dict[str, Any]] = []
        for card_id in sorted(card_blocks.keys()):
            block = card_blocks[card_id]
            block["mws_columns"].sort(
                key=lambda item: (item.get("case_study_id") or 0, item.get("mws_id") or "")
            )
            block.pop("_mws_seen", None)
            if block["mws_columns"]:
                cards_list.append(block)

        if cards_list:
            pathways_out.append({"pathway_id": pathway, "cards": cards_list})

    return {"pathways": pathways_out}


def evaluate_section(
    db: Database,
    *,
    production_system: str,
    observed_stress: str,
    instances: list[dict[str, Any]],
    card_edits: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    section_pathways = built_pathways_for_section(production_system, observed_stress)
    card_edits = card_edits or {}
    predictions_by_mws: dict[str, dict[str, Any]] = {}
    cards_by_mws: dict[str, dict[str, dict[str, Any]]] = {}
    exports_by_mws: dict[str, dict[str, Any]] = {}

    unique_mws = sorted({str(item.get("mws_id") or "") for item in instances if item.get("mws_id")})
    for mws_id in unique_mws:
        export = ensure_mws_export(db, mws_id)
        if export:
            exports_by_mws[mws_id] = export
        mws_doc = load_mws_doc(db, mws_id)
        if not mws_doc:
            continue
        prediction = evaluate_mws_prediction(
            db,
            mws_doc,
            card_edits=card_edits,
            production_system=production_system,
            section_pathways=section_pathways,
            for_triage=True,
        )
        predictions_by_mws[mws_id] = prediction
        cards_by_mws[mws_id] = prediction.get("cards") or resolve_cards_for_mws(db, mws_doc)

    instance_results: list[dict[str, Any]] = []

    for instance in instances:
        mws_id = str(instance.get("mws_id") or "")
        prediction = predictions_by_mws.get(mws_id) or {}
        section_pathway_set = set(section_pathways)
        confirmed_pathways = _confirmed_built_pathways(
            prediction.get("status") or {},
            allowed_pathways=section_pathway_set,
        )
        actual_pathway = _actual_pathway_for_instance(instance)
        cards = cards_by_mws.get(mws_id) or {}
        column_card = _instance_column_card(cards, instance, card_edits)

        if len(confirmed_pathways) == 1:
            predicted_pathway = confirmed_pathways[0]
            predicted_status = "confirmed"
        elif len(confirmed_pathways) > 1:
            predicted_pathway = (
                actual_pathway
                if actual_pathway in confirmed_pathways and actual_pathway != STRESS_ONLY_PATHWAY
                else confirmed_pathways[0]
            )
            predicted_status = "confirmed"
        else:
            predicted_pathway = NONE_OF_THESE_PATHWAY
            predicted_status = "not_confirmed"

        match = _matrix_match(
            instance,
            predicted_pathway if predicted_status == "confirmed" else NONE_OF_THESE_PATHWAY,
            predicted_status,
        )

        result = {
            "case_study_id": instance.get("case_study_id"),
            "mws_id": mws_id,
            "expected_pathway": instance.get("expected_pathway"),
            "stress_only": bool(instance.get("stress_only")),
            "actual_pathway": actual_pathway,
            "predicted_pathway": predicted_pathway,
            "predicted_status": predicted_status,
            "confirmed_pathways": confirmed_pathways,
            "match": match,
            "skipped": bool(prediction.get("skipped")),
            "card_id": (column_card or {}).get("card_id"),
            "signals": _signal_results_for_instance(prediction, instance, cards),
        }
        instance_results.append(result)

    matrix_cells = _matrix_cells_binary_per_pathway(
        instances,
        predictions_by_mws=predictions_by_mws,
        section_pathways=section_pathways,
    )

    variable_table = variable_table_for_instances(
        instances,
        cards_by_mws=cards_by_mws,
        card_edits=card_edits,
        exports_by_mws=exports_by_mws,
        section_pathways=section_pathways,
    )

    signal_grid = signal_grid_for_section(
        section_pathways,
        instances,
        cards_by_mws=cards_by_mws,
        predictions_by_mws=predictions_by_mws,
    )

    return {
        "production_system": production_system,
        "observed_stress": observed_stress,
        "instances": instance_results,
        "matrix": {
            "cells": matrix_cells,
            "row_pathways": section_pathways,
        },
        "variable_table": variable_table,
        "signal_grid": signal_grid,
    }
