"""Grid search over empirical threshold candidates with pathway-level objective."""

from __future__ import annotations

import itertools
from typing import Any

from tuning.empirical_grid import build_candidate_lists_v4
from tuning.pathway_objective import MAX_GRID_POINTS, pathway_level_objective
from tuning.registry_validation import validate_against_registry
from tuning.template_canonicalisation import (
    extract_template_and_thresholds,
    get_free_threshold_names,
    map_thresholds_to_variables,
    substitute_thresholds,
)


def pareto_front(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    front: list[dict[str, Any]] = []
    for candidate in results:
        dominated = False
        for other in results:
            if other is candidate:
                continue
            other_tpr = other.get("tpr") or 0.0
            candidate_tpr = candidate.get("tpr") or 0.0
            other_fpr = other.get("fpr")
            candidate_fpr = candidate.get("fpr")
            if other_tpr >= candidate_tpr and (other_fpr or 1.0) <= (candidate_fpr or 1.0):
                if other_tpr > candidate_tpr or (other_fpr or 1.0) < (candidate_fpr or 1.0):
                    dominated = True
                    break
        if not dominated:
            front.append(candidate)
    return front


def evaluate_expression_outcome(
    card: dict[str, Any],
    *,
    signal_id: str,
    expression: str,
    positives: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
) -> dict[str, Any]:
    ground_truth = {str(item.get("uid") or ""): True for item in positives}
    return pathway_level_objective(
        card,
        positives + negatives,
        ground_truth,
        candidate_expressions={signal_id: expression},
    )


def grid_search_signal(
    card: dict[str, Any],
    signal: dict[str, Any],
    *,
    positives: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
    registry: dict[str, Any],
    data_dictionary: dict[str, Any],
) -> dict[str, Any]:
    signal_id = str(signal.get("signal_id") or "")
    original_expression = str((signal.get("condition") or {}).get("expression") or "").strip()
    template, original_thresholds = extract_template_and_thresholds(original_expression)
    free = get_free_threshold_names(template, original_thresholds)
    threshold_to_variable = map_thresholds_to_variables(template, list(signal.get("variables") or []))

    baseline = evaluate_expression_outcome(
        card,
        signal_id=signal_id,
        expression=original_expression,
        positives=positives,
        negatives=negatives,
    )

    trace: dict[str, Any] = {
        "signal_id": signal_id,
        "template": template,
        "original_expression": original_expression,
        "original_thresholds": original_thresholds,
        "free_thresholds": free,
        "threshold_to_variable": threshold_to_variable,
        "baseline": baseline,
        "scope": "all_aers",
        "feasible": bool(free),
    }

    if not free:
        trace["recommendation"] = "NO_FREE_THRESHOLDS"
        trace["proposed_expression"] = original_expression
        return trace

    candidate_lists = build_candidate_lists_v4(
        free,
        threshold_to_variable,
        positives,
        negatives,
        registry,
        data_dictionary,
    )
    trace["grid_sizes"] = [len(values) for values in candidate_lists]
    trace["grid_total"] = 1
    for values in candidate_lists:
        trace["grid_total"] *= len(values)

    if trace["grid_total"] > MAX_GRID_POINTS:
        trace["recommendation"] = "GRID_TOO_LARGE"
        trace["proposed_expression"] = original_expression
        trace["grid_limit"] = MAX_GRID_POINTS
        return trace

    if not candidate_lists or any(not values for values in candidate_lists):
        trace["recommendation"] = "INSUFFICIENT_DATA"
        trace["proposed_expression"] = original_expression
        return trace

    results: list[dict[str, Any]] = []
    for combo in itertools.product(*candidate_lists):
        threshold_map = dict(zip(free, combo))
        candidate_expr = substitute_thresholds(template, threshold_map)
        outcome = evaluate_expression_outcome(
            card,
            signal_id=signal_id,
            expression=candidate_expr,
            positives=positives,
            negatives=negatives,
        )
        if outcome.get("tpr") is None:
            continue
        results.append(
            {
                "thresholds": threshold_map,
                "expression": candidate_expr,
                "tpr": outcome["tpr"],
                "fpr": outcome["fpr"],
                "confusion_matrix": outcome["confusion_matrix"],
            }
        )

    if not results:
        trace["recommendation"] = "INSUFFICIENT_DATA"
        trace["proposed_expression"] = original_expression
        return trace

    pareto = pareto_front(results)
    pareto.sort(key=lambda row: (-(row.get("tpr") or 0.0), row.get("fpr") if row.get("fpr") is not None else 1.0))
    best = pareto[0]
    trace["pareto_count"] = len(pareto)
    trace["best_candidate"] = best

    registry_check = validate_against_registry(best["expression"], registry)
    trace["registry_validation"] = registry_check

    baseline_tpr = baseline.get("tpr") or 0.0
    baseline_fpr = baseline.get("fpr")
    best_tpr = best.get("tpr") or 0.0
    best_fpr = best.get("fpr")

    if not registry_check.get("valid"):
        trace["recommendation"] = "REJECTED_REGISTRY_VIOLATION"
        trace["proposed_expression"] = original_expression
        return trace

    if best["expression"] == original_expression:
        trace["recommendation"] = "KEEP"
        trace["proposed_expression"] = original_expression
        return trace

    improved = (best_tpr > baseline_tpr) or (
        best_tpr == baseline_tpr
        and best_fpr is not None
        and (baseline_fpr is None or best_fpr < baseline_fpr)
    )
    if improved:
        trace["recommendation"] = "UPDATE"
        trace["proposed_expression"] = best["expression"]
        trace["proposed_thresholds"] = best.get("thresholds")
    else:
        trace["recommendation"] = "KEEP"
        trace["proposed_expression"] = original_expression

    return trace
