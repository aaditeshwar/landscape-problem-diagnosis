"""Shared expression audit helpers for cards and generation pipeline."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.assembler import NOT_AVAILABLE, VARIABLE_RESOLVERS  # noqa: E402
from services.derived_variables import DROUGHT_DERIVED_VARIABLE_NAMES  # noqa: E402
from services.variable_registry import (  # noqa: E402
    alias_to_canonical,
    canonical_name,
    drought_invented_expression_keys,
    is_static_variable,
    known_variable_names,
)

GET_CALL_RE = re.compile(
    r"\b(drought_causality(?:_json)?)\.get\s*\(\s*['\"]([^'\"]+)['\"]"
)
STATIC_INDEX_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[[^\]]+\]")

_DERIVED_NAMES = {
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


def all_known_names() -> set[str]:
    names = known_variable_names()
    names.update(VARIABLE_RESOLVERS)
    names.update(NOT_AVAILABLE)
    names.update(_DERIVED_NAMES)
    names.update(DROUGHT_DERIVED_VARIABLE_NAMES)
    names.update({"True", "False", "None"})
    return names


def extract_ast_names(expression: str) -> set[str]:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()
    allowed_builtins = {
        "abs", "min", "max", "len", "sum", "sorted", "round", "float", "int", "str",
        "list", "dict", "any", "all", "set", "tuple", "range", "enumerate", "zip",
    }
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    bound.add(sub.id)
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id not in allowed_builtins
        and node.id not in bound
    }


def audit_expression(
    expression: str,
    *,
    card_id: str = "",
    signal_id: str = "",
    known: set[str] | None = None,
) -> list[dict]:
    known = known or all_known_names()
    invented = drought_invented_expression_keys()
    findings: list[dict] = []
    if not expression.strip():
        return findings

    for match in GET_CALL_RE.finditer(expression):
        key = match.group(2)
        if key in invented:
            findings.append(
                {
                    "severity": "NESTED",
                    "category": "invented_drought_key",
                    "card_id": card_id,
                    "signal_id": signal_id,
                    "detail": f".get('{key}') on drought causality is not in nested schema",
                    "expression": expression,
                }
            )

    for match in STATIC_INDEX_RE.finditer(expression):
        var = match.group(1)
        if is_static_variable(var):
            findings.append(
                {
                    "severity": "SHAPE",
                    "category": "static_indexed_as_series",
                    "card_id": card_id,
                    "signal_id": signal_id,
                    "detail": f"{var} is static but indexed as {match.group(0)}",
                    "expression": expression,
                }
            )

    for name in extract_ast_names(expression):
        if name in known:
            canonical = canonical_name(name)
            if name != canonical and name in alias_to_canonical():
                findings.append(
                    {
                        "severity": "ALIAS",
                        "category": "legacy_name_in_expression",
                        "card_id": card_id,
                        "signal_id": signal_id,
                        "detail": f"{name} should migrate to {canonical}",
                        "expression": expression,
                    }
                )
            continue
        findings.append(
            {
                "severity": "BLOCKER",
                "category": "unknown_identifier",
                "card_id": card_id,
                "signal_id": signal_id,
                "detail": f"unknown identifier '{name}'",
                "expression": expression,
            }
        )

    try:
        ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        findings.append(
            {
                "severity": "BLOCKER",
                "category": "invalid_python",
                "card_id": card_id,
                "signal_id": signal_id,
                "detail": str(exc),
                "expression": expression,
            }
        )
    return findings


def audit_card_framework_variables(
    card: dict,
    pathway_diagnostic_variables: set[str] | None = None,
) -> list[dict]:
    """Flag expression identifiers absent from the pathway diagnostic_variables list."""
    if not pathway_diagnostic_variables:
        return []
    card_id = card.get("card_id", "?")
    allowed = set(pathway_diagnostic_variables) | _DERIVED_NAMES | set(DROUGHT_DERIVED_VARIABLE_NAMES)
    findings: list[dict] = []
    for sig in card.get("diagnostic_signals", []):
        sig_id = sig.get("signal_id", "?")
        condition = sig.get("condition") or {}
        expression = condition.get("expression") or sig.get("expression") or ""
        for name in extract_ast_names(expression):
            canonical = canonical_name(name)
            if name in allowed or canonical in allowed:
                continue
            findings.append(
                {
                    "severity": "BLOCKER",
                    "category": "missing_framework_variable",
                    "card_id": card_id,
                    "signal_id": sig_id,
                    "detail": (
                        f"'{name}' used in expression but not listed in pathway "
                        f"diagnostic_variables — add it to diagnosis_framework.json"
                    ),
                    "expression": expression,
                }
            )
    return findings


def audit_card(card: dict, known: set[str] | None = None) -> list[dict]:
    card_id = card.get("card_id", "?")
    findings: list[dict] = []
    for sig in card.get("diagnostic_signals", []):
        sig_id = sig.get("signal_id", "?")
        condition = sig.get("condition") or {}
        expression = condition.get("expression") or sig.get("expression") or ""
        findings.extend(
            audit_expression(expression, card_id=card_id, signal_id=sig_id, known=known)
        )
    return findings


def blocking_findings(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f["severity"] in {"BLOCKER", "SHAPE", "NESTED"}]


def validate_card_expressions(
    card: dict,
    *,
    pathway_diagnostic_variables: set[str] | None = None,
) -> list[str]:
    """Return human-readable blocking errors for a card (empty if OK)."""
    findings = blocking_findings(audit_card(card))
    findings.extend(
        blocking_findings(
            audit_card_framework_variables(
                card,
                pathway_diagnostic_variables=pathway_diagnostic_variables,
            )
        )
    )
    return [f"{f['card_id']} {f['signal_id']}: {f['detail']}" for f in findings]
