"""Pathway-level confirmation objective using production signal_evaluator."""

from __future__ import annotations

import copy
from typing import Any

from services.confirmation_policy import pathway_is_confirmed
from services.signal_evaluator import (
    SafeYearIndexedMapping,
    YearIndexedMapping,
    evaluate_expression,
    evaluate_pathway_signals,
    merge_export_variables,
)

MAX_GRID_POINTS = 2500


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def extract_scalar_for_variable(export: dict[str, Any], variable_name: str) -> float | None:
    merged = merge_export_variables(export)
    direct = _as_float(merged.get(variable_name))
    if direct is not None:
        return direct

    if not variable_name.startswith("mean_"):
        derived = _as_float(merged.get(f"mean_{variable_name}"))
        if derived is not None:
            return derived

    value = merged.get(variable_name)
    if isinstance(value, dict):
        numeric_years: list[float] = []
        for key, item in value.items():
            if not str(key).isdigit():
                continue
            parsed = _as_float(item)
            if parsed is not None:
                numeric_years.append(parsed)
        if numeric_years:
            return numeric_years[-1]

    if isinstance(value, (YearIndexedMapping, SafeYearIndexedMapping)):
        try:
            latest = value[-1]
        except (IndexError, KeyError, TypeError):
            latest = None
        parsed = _as_float(latest)
        if parsed is not None:
            return parsed

    for probe in (f"{variable_name}[-1]", variable_name, f"mean({variable_name})"):
        result, error = evaluate_expression(probe, merged)
        if error is None:
            parsed = _as_float(result)
            if parsed is not None:
                return parsed
    return None


def evaluate_pathway_for_export(
    card: dict[str, Any],
    export: dict[str, Any],
    *,
    candidate_expressions: dict[str, str] | None = None,
) -> dict[str, Any]:
    card_copy = copy.deepcopy(card)
    if candidate_expressions:
        for signal in card_copy.get("diagnostic_signals") or []:
            if not isinstance(signal, dict):
                continue
            signal_id = str(signal.get("signal_id") or "")
            if signal_id in candidate_expressions:
                condition = dict(signal.get("condition") or {})
                condition["expression"] = candidate_expressions[signal_id]
                signal["condition"] = condition
    present = merge_export_variables(export)
    pathway_data = {"present_variables": present, "evidence_card": card_copy}
    return evaluate_pathway_signals(pathway_data)


def pathway_level_objective(
    card: dict[str, Any],
    mws_list: list[dict[str, Any]],
    ground_truth: dict[str, bool],
    candidate_expressions: dict[str, str] | None = None,
) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    per_mws_detail: list[dict[str, Any]] = []

    for export in mws_list:
        uid = str(export.get("uid") or "")
        pathway_eval = evaluate_pathway_for_export(
            card,
            export,
            candidate_expressions=candidate_expressions,
        )
        confirmed = pathway_is_confirmed(pathway_eval, card)
        truth = bool(ground_truth.get(uid, False))
        predicted = bool(confirmed)

        if truth and predicted:
            tp += 1
        elif truth and not predicted:
            fn += 1
        elif not truth and predicted:
            fp += 1
        else:
            tn += 1

        per_mws_detail.append(
            {
                "uid": uid,
                "truth": truth,
                "predicted": predicted,
                "signal_results": {
                    row.get("signal_id"): row.get("result")
                    for row in pathway_eval.get("signals") or []
                    if isinstance(row, dict)
                },
            }
        )

    n_pos = tp + fn
    n_neg = tn + fp
    return {
        "tpr": tp / n_pos if n_pos else None,
        "fpr": fp / n_neg if n_neg else None,
        "confusion_matrix": {"TP": tp, "FP": fp, "TN": tn, "FN": fn},
        "per_mws_detail": per_mws_detail,
    }
