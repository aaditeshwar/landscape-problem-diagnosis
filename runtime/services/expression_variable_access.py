"""Parse signal expressions into displayable variable access keys."""

from __future__ import annotations

import ast
import json
import statistics
from typing import Any

_AGG_FUNCS = frozenset({"mean", "min", "max", "sum", "len", "sorted"})
_SAFE_BUILTINS = frozenset(
    {
        "abs",
        "min",
        "max",
        "len",
        "sum",
        "sorted",
        "round",
        "float",
        "int",
        "str",
        "list",
        "dict",
        "any",
        "all",
        "True",
        "False",
        "None",
    }
)


def _bound_names(tree: ast.AST) -> set[str]:
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    bound.add(sub.id)
    return bound


def _index_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return repr(-node.operand.value)
    return None


def _subscript_key(base: str, slice_node: ast.AST) -> str | None:
    if isinstance(slice_node, ast.Constant):
        return f"{base}[{repr(slice_node.value)}]"
    if isinstance(slice_node, ast.UnaryOp) and isinstance(slice_node.op, ast.USub):
        lit = _index_literal(slice_node)
        if lit is not None:
            return f"{base}[{lit}]"
    if isinstance(slice_node, ast.Index):  # noqa: UP038 — py<3.9 compat in older envs
        return _subscript_key(base, slice_node.value)
    return None


def expression_variable_accesses(expression: str) -> list[str]:
    """Return ordered unique access keys referenced in a signal expression."""
    expression = str(expression or "").strip()
    if not expression:
        return []
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return []

    bound = _bound_names(tree)
    keys: list[str] = []
    seen: set[str] = set()
    agg_wrapped_bases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _AGG_FUNCS:
            if not node.args:
                continue
            arg0 = node.args[0]
            if isinstance(arg0, ast.Name):
                agg_wrapped_bases.add(arg0.id)
            elif isinstance(arg0, ast.Subscript) and isinstance(arg0.value, ast.Name):
                agg_wrapped_bases.add(arg0.value.id)

    def add(key: str) -> None:
        if key and key not in seen:
            seen.add(key)
            keys.append(key)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in _SAFE_BUILTINS:
            if node.id in bound:
                continue
            if node.id in _AGG_FUNCS:
                continue
            if node.id in agg_wrapped_bases:
                continue
            add(node.id)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id in bound:
                continue
            if node.value.id in agg_wrapped_bases:
                continue
            key = _subscript_key(node.value.id, node.slice)
            if key:
                add(key)
        elif isinstance(node, ast.Call):
            func_name: str | None = None
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "get" and isinstance(node.func.value, ast.Name):
                base = node.func.value.id
                if base in bound:
                    continue
                if node.args:
                    lit = _index_literal(node.args[0])
                    if lit is not None:
                        add(f"{base}[{lit}]")
                continue
            if func_name in _AGG_FUNCS and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Name) and arg0.id not in bound:
                    add(f"{func_name}({arg0.id})")
                elif isinstance(arg0, ast.Subscript) and isinstance(arg0.value, ast.Name) and arg0.value.id not in bound:
                    inner = _subscript_key(arg0.value.id, arg0.slice)
                    if inner:
                        add(f"{func_name}({inner})")

    return keys


def expression_dependency_names(expression: str) -> set[str]:
    """Base variable names required to evaluate a signal expression."""
    names: set[str] = set()
    for access in expression_variable_accesses(expression):
        for func in ("mean", "min", "max", "sum", "len", "sorted"):
            prefix = f"{func}("
            if access.startswith(prefix) and access.endswith(")"):
                inner = access[len(prefix) : -1]
                if "[" in inner:
                    inner = inner.split("[", 1)[0]
                names.add(inner)
                break
        else:
            if "[" in access:
                names.add(access.split("[", 1)[0])
            else:
                names.add(access)
    return names


def expression_dependencies_from_card(card: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        condition = signal.get("condition") or {}
        expression = str(condition.get("expression") or signal.get("expression") or "").strip()
        if expression:
            names.update(expression_dependency_names(expression))
    return names


def numeric_series_values(value: Any) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "_data"):
        value = getattr(value, "_data")
    return _numeric_series_values(value)


def accesses_from_card(card: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for signal in card.get("diagnostic_signals") or []:
        if not isinstance(signal, dict):
            continue
        condition = signal.get("condition") or {}
        expression = str(condition.get("expression") or signal.get("expression") or "").strip()
        for key in expression_variable_accesses(expression):
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def _numeric_series_values(value: Any) -> list[float]:
    if isinstance(value, dict):
        items: list[tuple[str, Any]] = []
        for key, item in value.items():
            try:
                sort_key = int(str(key))
            except ValueError:
                sort_key = str(key)
            items.append((sort_key, item))
        items.sort(key=lambda pair: pair[0])
        raw = [pair[1] for pair in items]
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        return []

    out: list[float] = []
    for item in raw:
        if item is None:
            continue
        if isinstance(item, (int, float)):
            out.append(float(item))
        elif isinstance(item, str):
            try:
                out.append(float(item))
            except ValueError:
                continue
    return out


def _is_year_keyed_dict(value: dict[Any, Any]) -> bool:
    if not value:
        return False
    sample = list(value.keys())[:5]
    return all(str(key).isdigit() for key in sample)


def _sorted_year_keys(value: dict[Any, Any]) -> list[str]:
    return sorted(value.keys(), key=lambda y: int(y))


def resolve_access_value(access_key: str, variables: dict[str, Any]) -> Any:
    """Resolve a display access key against merged export variables."""
    key = str(access_key or "").strip()
    if not key:
        return None

    for func in ("mean", "min", "max", "sum", "len", "sorted"):
        prefix = f"{func}("
        if key.startswith(prefix) and key.endswith(")"):
            base = key[len(prefix) : -1]
            value = variables.get(base)
            if func == "len":
                if isinstance(value, dict):
                    return len(value)
                if isinstance(value, (list, tuple)):
                    return len(value)
                return None
            nums = _numeric_series_values(value)
            if not nums:
                return None
            if func == "mean":
                return statistics.mean(nums)
            if func == "min":
                return min(nums)
            if func == "max":
                return max(nums)
            if func == "sum":
                return sum(nums)
            if func == "sorted":
                return sorted(nums)
            return None

    if "[" in key and key.endswith("]"):
        base, bracket = key.split("[", 1)
        index_text = bracket[:-1]
        value = variables.get(base)
        if value is None:
            return None
        try:
            index: Any = ast.literal_eval(index_text)
        except (SyntaxError, ValueError):
            index = index_text.strip("'\"")

        if isinstance(value, dict):
            if _is_year_keyed_dict(value) and isinstance(index, int):
                years = _sorted_year_keys(value)
                if not years:
                    return None
                try:
                    return value[years[index]]
                except IndexError:
                    return None
            if index in value:
                return value[index]
            str_index = str(index)
            if str_index in value:
                return value[str_index]
            nums = _numeric_series_values(value)
            if isinstance(index, int):
                if index < 0:
                    return nums[index] if nums and abs(index) <= len(nums) else None
                return nums[index] if index < len(nums) else None
            return None
        if isinstance(value, (list, tuple)):
            try:
                return value[int(index)]
            except (IndexError, TypeError, ValueError):
                return None
        return None

    return variables.get(key)


def format_access_value(value: Any, *, max_len: int = 80) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        text = f"{value:.4g}"
    elif isinstance(value, (int, bool)):
        text = str(value)
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, default=str, ensure_ascii=False)
        if len(text) > max_len:
            return text[: max_len - 1] + "…"
        return text
    else:
        text = str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text
