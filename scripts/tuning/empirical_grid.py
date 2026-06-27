"""Data-driven threshold candidate grids (expression_tuning_algorithm v4)."""

from __future__ import annotations

from typing import Any

from tuning.pathway_objective import MAX_GRID_POINTS, extract_scalar_for_variable


def infer_round_to(variable_name: str, registry: dict[str, Any], data_dictionary: dict[str, Any]) -> float | None:
    unit = str((data_dictionary.get(variable_name) or {}).get("unit") or "")
    var_type = str(
        (registry.get("variable_registry", {}).get("variables", {}).get(variable_name) or {}).get("type") or ""
    )

    if "week" in variable_name or "count" in variable_name or "return_period" in variable_name:
        return 1.0
    if unit in ("mm", "ha"):
        return 10.0
    if unit == "km":
        return 0.5
    if unit in ("percent", "ratio", "%") or "ratio" in variable_name:
        return 0.05
    if variable_name.endswith("_score_latest"):
        return 1.0
    if var_type == "static":
        return 1.0
    return None


def empirical_threshold_candidates(
    pos_values: list[float],
    neg_values: list[float],
    *,
    round_to: float | None = None,
) -> list[float]:
    all_vals = sorted(set(pos_values + neg_values))
    if not all_vals:
        return []

    candidates = [all_vals[0] - 1.0]
    for left, right in zip(all_vals[:-1], all_vals[1:]):
        candidates.append((left + right) / 2.0)
    candidates.append(all_vals[-1] + 1.0)

    if round_to is not None and round_to > 0:
        candidates = sorted(set(round(round(value / round_to) * round_to, 10) for value in candidates))
    return candidates


def build_candidate_lists_v4(
    free_thresholds: list[str],
    threshold_to_variable: dict[str, str],
    positives: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
    registry: dict[str, Any],
    data_dictionary: dict[str, Any],
) -> list[list[float]]:
    candidate_lists: list[list[float]] = []
    for threshold_name in free_thresholds:
        variable_name = threshold_to_variable.get(threshold_name, "")
        pos_vals = [
            value
            for value in (extract_scalar_for_variable(export, variable_name) for export in positives)
            if value is not None
        ]
        neg_vals = [
            value
            for value in (extract_scalar_for_variable(export, variable_name) for export in negatives)
            if value is not None
        ]
        round_to = infer_round_to(variable_name, registry, data_dictionary)
        candidates = empirical_threshold_candidates(pos_vals, neg_vals, round_to=round_to)
        candidate_lists.append(candidates)
    return candidate_lists
