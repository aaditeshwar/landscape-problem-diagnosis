"""Canonicalise signal expressions into templates with threshold placeholders."""

from __future__ import annotations

import ast
import re
from typing import Any


def extract_template_and_thresholds(expression: str) -> tuple[str, dict[str, float]]:
    """Replace numeric literals with ordered placeholders T0, T1, ... using AST."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return expression, {}

    thresholds: dict[str, float] = {}
    counter = [0]

    class Rewriter(ast.NodeTransformer):
        def visit_Constant(self, node: ast.Constant) -> ast.AST:
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                key = f"T{counter[0]}"
                thresholds[key] = float(node.value)
                counter[0] += 1
                return ast.copy_location(ast.Name(id=key, ctx=ast.Load()), node)
            return node

    rewritten = Rewriter().visit(tree)
    ast.fix_missing_locations(rewritten)
    template = ast.unparse(rewritten)
    return template, thresholds


def get_free_threshold_names(template: str, original_thresholds: dict[str, float]) -> list[str]:
    """Return tunable threshold placeholders (exclude convention-fixed T*=1)."""
    seen: list[str] = []
    for name in re.findall(r"T\d+", template):
        if name in seen:
            continue
        if original_thresholds.get(name) == 1:
            continue
        seen.append(name)
    return seen


def substitute_thresholds(template: str, threshold_map: dict[str, float]) -> str:
    expr = template
    for name in sorted(threshold_map, key=lambda key: int(key[1:]), reverse=True):
        value = threshold_map[name]
        replacement = str(int(value)) if value == int(value) else str(value)
        expr = expr.replace(name, replacement)
    return expr


def map_thresholds_to_variables(template: str, signal_variables: list[str]) -> dict[str, str]:
    """Map each T* placeholder to the variable name in its comparison."""
    tree = ast.parse(template, mode="eval")
    mapping: dict[str, str] = {}

    def innermost_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Subscript):
            return innermost_name(node.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "mean" and node.args:
                return innermost_name(node.args[0]) or node.func.id
            return node.func.id
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            return innermost_name(node.func.value)
        return None

    class Visitor(ast.NodeVisitor):
        def visit_Compare(self, node: ast.Compare) -> None:
            left_name = innermost_name(node.left)
            for comparator in node.comparators:
                right_name = innermost_name(comparator)
                if right_name and right_name.startswith("T") and left_name:
                    mapping[right_name] = left_name
                elif left_name and left_name.startswith("T") and right_name:
                    mapping[left_name] = right_name
            self.generic_visit(node)

    Visitor().visit(tree)
    for index in range(10):
        placeholder = f"T{index}"
        if placeholder in template and placeholder not in mapping and signal_variables:
            mapping[placeholder] = signal_variables[0]
    return mapping


def signals_eligible_for_tuning(card: dict[str, Any]) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        if signal.get("active") is False:
            continue
        if str(signal.get("direction") or "") != "confirms":
            continue
        expr = str((signal.get("condition") or {}).get("expression") or "").strip()
        if not expr:
            continue
        eligible.append(signal)
    return eligible
