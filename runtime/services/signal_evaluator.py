"""Restricted evaluation of evidence-card signal expressions against present_variables."""

from __future__ import annotations

import ast
from datetime import date, datetime
from typing import Any

from services.aer_alignment import classify_aer_alignment, overlapping_retrieval_aer_tags
from services.derived_variables import DROUGHT_DERIVED_VARIABLE_NAMES
from services.variable_registry import list_type_variables, presence_categorical_variables

_NUMERIC_DERIVED_DEFAULTS = DROUGHT_DERIVED_VARIABLE_NAMES | {
    "mean_annual_precipitation_mm",
    "trend_annual_precipitation_mm",
    "mean_annual_et_mm",
    "trend_annual_et_mm",
    "mean_annual_runoff_mm",
    "trend_annual_runoff_mm",
    "mean_annual_delta_g_mm",
    "trend_annual_delta_g_mm",
    "mean_cropping_intensity",
    "trend_cropping_intensity",
    "mean_kharif_cropped_area_ha",
    "trend_kharif_cropped_area_ha",
    "mean_double_crop_area_ha",
    "trend_double_crop_area_ha",
    "drought_moderate_return_period",
    "drought_severe_return_period",
    "mean_swb_total_area_ha",
    "trend_swb_total_area_ha",
    "mean_swb_rabi_kharif_ratio",
    "trend_swb_rabi_kharif_ratio",
}

_TIME_SERIES_WHEN_NULL = frozenset(
    {
        "annual_delta_g_mm",
        "annual_precipitation_mm",
        "annual_et_mm",
        "annual_runoff_mm",
        "seasonal_precipitation_mm",
        "drought_weeks_severe",
        "drought_weeks_moderate",
        "dry_spell_weeks",
        "monsoon_onset_date",
        "kharif_cropped_area_percent",
        "drought_causality",
        "drought_causality_json",
        "cropping_intensity",
        "lulc_single_kharif_ha",
        "lulc_double_crop_ha",
        "lulc_cropland_ha",
        "lulc_shrub_scrub_ha",
        "lulc_barrenland_ha",
        "lulc_tree_forest_ha",
        "lulc_krz_water_ha",
        "swb_total_area_ha",
        "swb_kharif_area_ha",
        "swb_rabi_area_ha",
        "swb_zaid_area_ha",
    }
)

_SAFE_BUILTINS = {
    "abs": abs,
    "min": min,
    "max": max,
    "len": len,
    "sum": sum,
    "sorted": sorted,
    "round": round,
    "float": float,
    "int": int,
    "list": list,
    "dict": dict,
    "any": any,
    "all": all,
    "True": True,
    "False": False,
    "None": None,
}


class SeasonBlockMapping:
    """Season-keyed hydrological block; .get('kharif') returns kharif precipitation_mm scalar."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[Any, Any]):
        self._data = dict(data or {})

    def get(self, key: Any, default: Any = None) -> Any:
        block = self._data.get(key)
        if isinstance(block, dict) and "precipitation_mm" in block:
            return block["precipitation_mm"]
        if block is None:
            return default
        return block

    def __getitem__(self, key: Any) -> Any:
        return self.get(key)


def _season_block(data: dict[Any, Any]) -> bool:
    return any(k in data for k in ("kharif", "rabi", "zaid"))


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        parts = value.split("-")
        if len(parts) >= 3:
            try:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            except ValueError:
                pass
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


class DayDelta:
    __slots__ = ("days",)

    def __init__(self, days: int):
        self.days = days

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, (int, float)):
            return self.days > other
        return False

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, (int, float)):
            return self.days >= other
        return False


class DateValue:
    __slots__ = ("value",)

    def __init__(self, value: date):
        self.value = value

    def __sub__(self, other: Any) -> DayDelta:
        if isinstance(other, DateValue):
            return DayDelta((self.value - other.value).days)
        raise TypeError("unsupported date subtraction")

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, DateValue):
            return self.value > other.value
        if isinstance(other, (int, float)):
            return self.value.toordinal() > other
        return False

    def __add__(self, other: Any) -> DateValue:
        if isinstance(other, (int, float)):
            return DateValue(date.fromordinal(self.value.toordinal() + int(other)))
        raise TypeError("unsupported date addition")

    def __radd__(self, other: Any) -> DateValue:
        return self.__add__(other)


class YearIndexedMapping:
    """Dict keyed by agricultural year strings with integer index access ([-1] = latest)."""

    __slots__ = ("_data", "_years")

    def __init__(self, data: dict[Any, Any]):
        self._data = dict(data or {})
        self._years = sorted(str(y) for y in self._data.keys())

    def _resolve_key(self, key: Any) -> Any:
        if isinstance(key, int):
            if not self._years:
                raise KeyError(key)
            return self._years[key]
        return key

    def _year_value(self, year: str) -> Any:
        value = self._data[year]
        if isinstance(value, dict) and _season_block(value):
            return SeasonBlockMapping(value)
        parsed = _parse_date(value)
        if parsed is not None:
            return DateValue(parsed)
        return _wrap_eval_value(value)

    def __getitem__(self, key: Any) -> Any:
        resolved = self._resolve_key(key)
        return self._year_value(resolved)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def values(self):
        return (self._year_value(y) for y in self._years)

    def keys(self):
        return self._years

    def items(self):
        return ((y, _wrap_eval_value(self._data[y])) for y in self._years)

    def __len__(self) -> int:
        return len(self._years)

    def __iter__(self):
        return iter(self._years)

    def __sub__(self, other: Any):
        left = _parse_date(self[-1])
        if isinstance(other, YearIndexedMapping):
            right = _parse_date(other[-1])
        else:
            right = _parse_date(other) if not isinstance(other, (int, float)) else None
        if left and right:
            return DayDelta((left - right).days)
        if isinstance(other, YearIndexedMapping):
            return self[-1] - other[-1]
        return self[-1] - other

    def __rsub__(self, other: Any):
        left = _parse_date(self[-1])
        if left and isinstance(other, (int, float)):
            return DayDelta(int(other) - left.toordinal())
        return other - self[-1]

    def __gt__(self, other: Any) -> bool:
        left = _parse_date(self[-1])
        right = _parse_date(other) if not isinstance(other, (int, float)) else None
        if left and right:
            return left > right
        if isinstance(other, (int, float)) and left:
            return left.toordinal() > other
        return self[-1] > other

    def __add__(self, other: Any):
        left = _parse_date(self[-1])
        if left and isinstance(other, (int, float)):
            return date.fromordinal(left.toordinal() + int(other))
        raise TypeError("unsupported date addition")


class SafeYearIndexedMapping(YearIndexedMapping):
    def __getitem__(self, key: Any) -> Any:
        try:
            return super().__getitem__(key)
        except KeyError:
            if isinstance(key, int):
                return 0
            raise


_CATEGORICAL_WHEN_NULL = frozenset(
    {
        "river_name",
        "canal_name",
        "aquifer_class",
        "soge_class_name",
        "watershed_code",
        "basin_code",
        "downstream_uid",
        "flow_direction",
        "nbss_lup_aer_code",
    }
)


def _looks_like_year_series(data: dict[Any, Any]) -> bool:
    if not data:
        return False
    sample = list(data.keys())[:5]
    return all(str(key).isdigit() for key in sample)


def _wrap_eval_value(value: Any) -> Any:
    if isinstance(value, dict) and _looks_like_year_series(value):
        return YearIndexedMapping(value)
    return value


def merge_export_variables(export: dict[str, Any]) -> dict[str, Any]:
    """Combine present_variables and derived_variables from a case-study export."""
    merged = dict(export.get("present_variables") or {})
    merged.update(export.get("derived_variables") or {})
    for name in export.get("missing_variables") or []:
        merged.setdefault(name, None)
    return merged


def build_eval_context_from_export(export: dict[str, Any]) -> dict[str, Any]:
    return eval_context(merge_export_variables(export))


def classify_eval_error(error: str | None) -> str:
    if error is None:
        return "ok"
    if error == "missing expression":
        return "no_expression"
    if error.startswith("invalid syntax") or "SyntaxError" in error:
        return "syntax_error"
    if error.startswith("NameError"):
        return "name_error"
    if error.startswith("TypeError"):
        return "type_error"
    if error.startswith("AttributeError"):
        return "attribute_error"
    if error.startswith("KeyError"):
        return "key_error"
    return "other_error"


def eval_context(present_variables: dict[str, Any], injected: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a restricted namespace for signal expression evaluation."""
    ctx: dict[str, Any] = {}
    for key, value in (present_variables or {}).items():
        ctx[key] = _wrap_eval_value(value)
    if injected:
        for key, value in injected.items():
            ctx[key] = _wrap_eval_value(value)
    for name in DROUGHT_DERIVED_VARIABLE_NAMES:
        if ctx.get(name) is None:
            ctx[name] = 0
    for name in list_type_variables():
        ctx.setdefault(name, [])
    for name in presence_categorical_variables():
        ctx.setdefault(name, None)
    for name in _NUMERIC_DERIVED_DEFAULTS:
        if name in ctx:
            continue
        if name in {"drought_severe_return_period", "drought_moderate_return_period"}:
            ctx[name] = 999.0
        else:
            ctx[name] = 0
    for key, value in list(ctx.items()):
        if value is not None:
            continue
        if key in list_type_variables():
            ctx[key] = []
        elif key in presence_categorical_variables():
            ctx[key] = None
        elif key in _TIME_SERIES_WHEN_NULL:
            ctx[key] = SafeYearIndexedMapping({})
        elif key in _CATEGORICAL_WHEN_NULL:
            continue
        elif key in _NUMERIC_DERIVED_DEFAULTS or key.startswith(
            ("dist_", "cd_", "nrega_", "village_", "soge_", "mean_", "trend_", "drought_", "swb_", "slopy_")
        ):
            ctx[key] = 0
    return ctx


def validate_expression_syntax(expression: str) -> str | None:
    try:
        ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return str(exc)
    return None


def evaluate_expression(
    expression: str,
    present_variables: dict[str, Any],
    injected: dict[str, Any] | None = None,
) -> tuple[bool | None, str | None]:
    """Evaluate a card signal expression. Returns (result, error_message)."""
    syntax_error = validate_expression_syntax(expression)
    if syntax_error:
        return None, syntax_error
    ctx = eval_context(present_variables, injected)
    try:
        result = eval(  # noqa: S307 — restricted namespace for card expressions
            expression,
            {"__builtins__": _SAFE_BUILTINS},
            ctx,
        )
    except Exception as exc:  # noqa: BLE001 — surface eval errors to caller
        return None, f"{type(exc).__name__}: {exc}"
    if isinstance(result, bool):
        return result, None
    if result is None:
        return None, "expression did not return a boolean"
    return bool(result), None


def evaluate_signal_condition(
    condition: dict[str, Any] | None,
    present_variables: dict[str, Any],
    injected: dict[str, Any] | None = None,
) -> tuple[bool | None, str | None]:
    expression = (condition or {}).get("expression") or ""
    if not expression.strip():
        return None, "missing expression"
    return evaluate_expression(expression, present_variables, injected)


def _flatten_injected(injected: dict[str, Any] | None) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in (injected or {}).items():
        if isinstance(value, dict):
            flat[key] = value.get("raw", value)
        else:
            flat[key] = value
    return flat


def _signal_qualitative_hint(signal: dict[str, Any]) -> str:
    condition = signal.get("condition") or {}
    for key in ("qualitative_description", "expression"):
        text = str(condition.get(key) or "").strip()
        if text and key == "qualitative_description":
            return text[:200]
    explanation = str(signal.get("explanation") or "").strip()
    return explanation[:200] if explanation else ""


def _signal_variable_names(signal: dict[str, Any]) -> list[str]:
    return [str(name) for name in (signal.get("variables") or []) if name]


def _injected_payload(injected: dict[str, Any] | None, variable: str) -> dict[str, Any] | None:
    if not injected or variable not in injected:
        return None
    value = injected[variable]
    if isinstance(value, dict):
        return value
    return {"raw": str(value), "variable": variable}


def _apply_user_answer_overlay(
    *,
    signal: dict[str, Any],
    condition: dict[str, Any],
    injected: dict[str, Any] | None,
    card: dict[str, Any],
    initial_status: str,
) -> dict[str, Any] | None:
    """Merge follow-up answers into qualitative / missing-expression signals."""
    if not injected:
        return None

    matched_vars = [name for name in _signal_variable_names(signal) if name in injected]
    if not matched_vars:
        return None

    if initial_status == "ok":
        return None

    from services.diagnosis_revision import (
        card_update_rule_for_variable,
        infer_from_update_rule_threshold,
        infer_user_signal_result,
        match_update_rule_excerpt,
    )

    variable = matched_vars[0]
    normalized = _injected_payload(injected, variable)
    if not normalized:
        return None

    from services.diagnosis_revision import UNABLE_TO_EVALUATE_NOTE

    from services.follow_up_effects import effect_result_for_signal

    update_rule = card_update_rule_for_variable(card, variable)
    update_excerpt, excerpt_matched = match_update_rule_excerpt(update_rule, normalized)
    direction = str(signal.get("direction") or "")
    signal_id = str(signal.get("signal_id") or "")
    choice_id = str(normalized.get("choice_id") or "")
    user_result = effect_result_for_signal(
        card,
        variable=variable,
        choice_id=choice_id,
        signal_id=signal_id,
    )
    inference_source = update_excerpt if excerpt_matched else ""
    if user_result is None:
        user_result = infer_user_signal_result(
            direction=direction,
            normalized=normalized,
            update_excerpt=inference_source,
            update_rule=update_rule,
        )
    elif excerpt_matched:
        inference_source = update_excerpt

    overlay: dict[str, Any] = {
        "answered_variable": variable,
        "matched_variables": matched_vars,
        "user_answer": normalized.get("raw") or str(injected.get(variable)),
        "update_rule": update_rule,
        "update_interpretation": update_excerpt if excerpt_matched else "",
        "excerpt_matched": excerpt_matched,
    }

    if user_result is not None:
        overlay["status"] = "user_provided"
        overlay["result"] = user_result
        overlay["inference"] = "evaluated"
        if not excerpt_matched and update_rule:
            threshold = infer_from_update_rule_threshold(
                direction=direction,
                normalized=normalized,
                update_rule=update_rule,
            )
            if threshold is not None:
                overlay["update_interpretation"] = update_rule.strip()
                overlay["excerpt_matched"] = True
    else:
        overlay["status"] = "user_provided_unresolved"
        overlay["result"] = None
        overlay["inference"] = "unable_to_evaluate"
        overlay["inference_note"] = UNABLE_TO_EVALUATE_NOTE
    return overlay


def _count_signal_in_summary(summary: dict[str, int], direction: str, result: bool | None) -> None:
    if result is not True:
        return
    if direction == "confirms":
        summary["confirms_true"] += 1
    elif direction == "rules_out":
        summary["rules_out_true"] += 1
    elif direction == "amplifies":
        summary["amplifies_true"] += 1


def _variable_values_for_expression(expression: str, variables: dict[str, Any]) -> list[dict[str, str]]:
    from services.expression_variable_access import (
        expression_variable_accesses,
        format_access_value,
        resolve_access_value,
    )

    if not expression:
        return []
    rows: list[dict[str, str]] = []
    for access in expression_variable_accesses(expression):
        value = resolve_access_value(access, variables)
        rows.append({"access": access, "formatted": format_access_value(value)})
    return rows


def evaluate_pathway_signals(
    pathway_data: dict[str, Any],
    injected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate all diagnostic signals for one bundle pathway entry."""
    from services.variable_registry import normalize_expression

    present = dict(pathway_data.get("present_variables") or {})
    injected_flat = _flatten_injected(injected)
    card = pathway_data.get("evidence_card") or {}
    signals_out: list[dict[str, Any]] = []
    summary = {
        "confirms_true": 0,
        "rules_out_true": 0,
        "amplifies_true": 0,
        "ok": 0,
        "needs_llm": 0,
    }

    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        if signal.get("active") is False:
            continue
        condition = signal.get("condition") or {}
        raw_expr = str(condition.get("expression") or "").strip()
        expression = raw_expr
        if raw_expr:
            expression, _ = normalize_expression(raw_expr)

        eval_condition = dict(condition)
        if expression:
            eval_condition["expression"] = expression
        result, error = evaluate_signal_condition(eval_condition, present, injected_flat)
        status = classify_eval_error(error)
        missing_vars: list[str] = []
        if status == "name_error" and expression:
            missing_vars = sorted(missing_context_keys(expression, present))

        direction = str(signal.get("direction") or "")
        entry: dict[str, Any] = {
            "signal_id": signal.get("signal_id", "?"),
            "direction": direction,
            "expression": expression or raw_expr,
            "result": result,
            "status": status,
            "error": error,
            "missing_vars": missing_vars,
            "variable_values": _variable_values_for_expression(expression or raw_expr, present),
        }
        if status != "ok":
            entry["qualitative_hint"] = _signal_qualitative_hint(signal)
            summary["needs_llm"] += 1
        else:
            summary["ok"] += 1
            _count_signal_in_summary(summary, direction, result)

        overlay = _apply_user_answer_overlay(
            signal=signal,
            condition=condition,
            injected=injected,
            card=card,
            initial_status=status,
        )
        if overlay:
            entry.update(overlay)
            if overlay.get("result") is not None:
                if status != "ok":
                    summary["needs_llm"] = max(0, summary["needs_llm"] - 1)
                summary["ok"] += 1
                _count_signal_in_summary(summary, direction, entry.get("result"))

        signals_out.append(entry)

    return {
        "signals": signals_out,
        "summary": summary,
        "evidence_note": str(card.get("overall_reasoning_note") or ""),
    }


def evaluate_bundle_signals(
    bundle: dict[str, dict],
    injected: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Evaluate diagnostic signals for every pathway in the variable bundle."""
    return {
        str(pathway_id): evaluate_pathway_signals(data, injected=injected)
        for pathway_id, data in bundle.items()
    }


def collect_follow_up_signal_updates(
    eval_results: dict[str, dict[str, Any]],
    answered_variable: str | None,
) -> list[dict[str, Any]]:
    """Summarize card-driven follow-up signal overlays for API / frontend."""
    if not answered_variable:
        return []

    updates: list[dict[str, Any]] = []
    for pathway_id, data in eval_results.items():
        for signal in data.get("signals") or []:
            if not isinstance(signal, dict):
                continue
            if signal.get("status") not in {"user_provided", "user_provided_unresolved"}:
                continue
            if signal.get("answered_variable") != answered_variable:
                continue
            updates.append(
                {
                    "pathway_id": pathway_id,
                    "signal_id": signal.get("signal_id"),
                    "variable": answered_variable,
                    "direction": signal.get("direction"),
                    "result": signal.get("result"),
                    "inference": signal.get("inference"),
                    "inference_note": signal.get("inference_note"),
                    "user_answer": signal.get("user_answer"),
                    "update_interpretation": signal.get("update_interpretation"),
                    "update_rule": signal.get("update_rule"),
                }
            )
    return updates


def summarize_evaluation_for_log(eval_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compact pathway/signal summary for diagnosis JSONL logs."""
    pathways: list[dict[str, Any]] = []
    for pathway_id, data in eval_results.items():
        pathways.append(
            {
                "pathway_id": pathway_id,
                "summary": data.get("summary") or {},
                "evidence_note": data.get("evidence_note"),
                "signals": [
                    {
                        "signal_id": signal.get("signal_id"),
                        "direction": signal.get("direction"),
                        "result": signal.get("result"),
                        "status": signal.get("status"),
                        "expression": signal.get("expression") or "",
                        "qualitative_hint": signal.get("qualitative_hint") or "",
                        "user_answer": signal.get("user_answer") or "",
                        "update_interpretation": signal.get("update_interpretation") or "",
                        "update_rule": signal.get("update_rule") or "",
                        "answered_variable": signal.get("answered_variable") or "",
                        "inference": signal.get("inference") or "",
                        "inference_note": signal.get("inference_note") or "",
                    }
                    for signal in data.get("signals") or []
                    if isinstance(signal, dict)
                ],
            }
        )
    return {"pathways": pathways}


def summarize_pathway_evidence(
    bundle: dict[str, dict],
    *,
    mws_aer_code: str | None = None,
    retrieval_aer_tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Evidence card / AER context per retrieved pathway."""
    rows: list[dict[str, Any]] = []
    for pathway_id, data in bundle.items():
        card = data.get("evidence_card") or {}
        context = data.get("context") or {}
        aer_tags = data.get("aer_tags") or card.get("aer_tags") or []
        rows.append(
            {
                "pathway_id": pathway_id,
                "card_id": data.get("card_id") or card.get("card_id"),
                "aer_tags": aer_tags,
                "rainfall_regime": context.get("rainfall_regime"),
                "agro_climatic_zones": context.get("agro_climatic_zones") or [],
                "aer_alignment": classify_aer_alignment(aer_tags, mws_aer_code, retrieval_aer_tags),
                "retrieval_overlap_aer": overlapping_retrieval_aer_tags(aer_tags, retrieval_aer_tags),
            }
        )
    return rows


def expression_load_names(card_or_expression: Any) -> set[str]:
    """Return identifier names referenced in a card's signal expressions or a single expression."""
    names: set[str] = set()
    if isinstance(card_or_expression, str):
        expressions = [card_or_expression]
    else:
        expressions = [
            str((signal.get("condition") or {}).get("expression") or "").strip()
            for signal in (card_or_expression.get("diagnostic_signals") or [])
            if isinstance(signal, dict)
        ]
    for expression in expressions:
        if not expression:
            continue
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError:
            continue
        bound: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.comprehension):
                for sub in ast.walk(node.target):
                    if isinstance(sub, ast.Name):
                        bound.add(sub.id)
        names.update(
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id not in _SAFE_BUILTINS
            and node.id not in bound
        )
    return names


def missing_context_keys(expression: str, present_variables: dict[str, Any]) -> set[str]:
    """Return identifier names referenced in expression but absent from present_variables."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    bound.add(sub.id)
    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id not in _SAFE_BUILTINS
        and node.id not in bound
    }
    available = set(present_variables or {})
    available.update(DROUGHT_DERIVED_VARIABLE_NAMES)
    for key, value in (present_variables or {}).items():
        if value is None:
            available.add(key)
    return names - available
