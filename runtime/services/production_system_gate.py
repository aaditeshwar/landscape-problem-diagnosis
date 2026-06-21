"""Evaluate production-system eligibility rules from diagnosis_framework.json."""

from __future__ import annotations

from typing import Any

from services.assembler import load_framework, resolve_variable
from services.signal_evaluator import evaluate_expression, expression_load_names


def _gate_rules() -> list[tuple[str, dict[str, Any]]]:
    root = load_framework()["diagnosis_framework"]["production_systems"]
    rules: list[tuple[str, dict[str, Any]]] = []
    for production_system, cfg in root.items():
        eligibility = cfg.get("eligibility") or {}
        for rule in eligibility.get("skip_when") or []:
            if isinstance(rule, dict):
                rules.append((str(production_system), rule))
    return rules


def _collect_gate_variable_names() -> set[str]:
    names: set[str] = set()
    for _, rule in _gate_rules():
        expression = str(rule.get("expression") or "").strip()
        if expression:
            names.update(expression_load_names(expression))
    return names


def build_gate_eval_context(
    mws_doc: dict,
    injected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve variables referenced by all framework gate expressions."""
    present: dict[str, Any] = {}
    for name in sorted(_collect_gate_variable_names()):
        value = resolve_variable(mws_doc, name, injected)
        if value is not None:
            present[name] = value
    return present


def evaluate_production_system_gates(
    mws_doc: dict,
    injected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return eligible production systems and skip records for rules that fired."""
    root = load_framework()["diagnosis_framework"]["production_systems"]
    eligible = set(root.keys())
    skipped: list[dict[str, Any]] = []
    present = build_gate_eval_context(mws_doc, injected)

    for production_system, rule in _gate_rules():
        if production_system not in eligible:
            continue
        expression = str(rule.get("expression") or "").strip()
        if not expression:
            continue
        result, _error = evaluate_expression(expression, present, injected)
        if result is not True:
            continue
        eligible.discard(production_system)
        entry: dict[str, Any] = {
            "production_system": production_system,
            "rule_id": str(rule.get("id") or ""),
            "message": str(rule.get("message") or ""),
            "expression": expression,
        }
        for name in sorted(expression_load_names(expression)):
            if name in present:
                entry[name] = present[name]
        skipped.append(entry)

    return {
        "eligible_production_systems": sorted(eligible),
        "skipped_production_systems": skipped,
    }


def filter_cards_by_eligible_systems(
    cards: list[dict],
    eligible_production_systems: set[str] | list[str],
) -> list[dict]:
    eligible = set(eligible_production_systems)
    if not eligible:
        return []
    return [
        card
        for card in cards
        if str(card.get("production_system") or "") in eligible or not card.get("production_system")
    ]


def filter_bundle_by_eligible_systems(
    bundle: dict[str, dict],
    eligible_production_systems: set[str] | list[str],
) -> dict[str, dict]:
    eligible = set(eligible_production_systems)
    if not eligible:
        return {}
    return {
        pathway_id: data
        for pathway_id, data in bundle.items()
        if str(data.get("production_system") or "") in eligible or not data.get("production_system")
    }


def filter_pathways_in_response(
    response: dict[str, Any],
    eligible_production_systems: set[str] | list[str],
) -> dict[str, Any]:
    """Remove confirmed/uncertain pathways for ineligible production systems."""
    eligible = set(eligible_production_systems)
    if not eligible:
        out = dict(response)
        out["confirmed_pathways"] = []
        out["uncertain_pathways"] = []
        return out

    def _keep(pathway: Any) -> bool:
        if not isinstance(pathway, dict):
            return False
        production = str(pathway.get("production_system") or "")
        return production in eligible or not production

    out = dict(response)
    out["confirmed_pathways"] = [p for p in out.get("confirmed_pathways") or [] if _keep(p)]
    out["uncertain_pathways"] = [p for p in out.get("uncertain_pathways") or [] if _keep(p)]
    return out
