"""Validate tuned expressions against variable_registry.json."""

from __future__ import annotations

import ast
from typing import Any


def validate_against_registry(expression: str, registry: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return {"valid": False, "violations": [f"syntax error: {exc}"]}

    variables = registry.get("variable_registry", {}).get("variables", {})
    invented: set[str] = set()
    for info in variables.values():
        invented.update(info.get("invented_expression_keys") or [])

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                key = node.args[0].value
                if key in invented:
                    violations.append(
                        f"Uses invented key '{key}' via .get() — not in variable_registry.json"
                    )
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            varname = node.value.id
            info = variables.get(varname)
            if info and info.get("type") == "static":
                violations.append(
                    f"Variable '{varname}' is type=static but is indexed with [...]"
                )

    return {"valid": len(violations) == 0, "violations": violations}
