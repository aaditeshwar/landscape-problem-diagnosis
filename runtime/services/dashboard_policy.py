"""Variable dashboard chart defaults and exclusion policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import ROOT

CHART_DEFAULTS_PATH = ROOT / "metadata" / "dashboard_chart_defaults.json"


def load_dashboard_chart_policy() -> dict[str, Any]:
    if not CHART_DEFAULTS_PATH.is_file():
        return {"version": 1, "variables": {}, "excluded_variables": []}
    payload = json.loads(CHART_DEFAULTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"version": 1, "variables": {}, "excluded_variables": []}
    payload.setdefault("variables", {})
    payload.setdefault("excluded_variables", [])
    return payload


def excluded_dashboard_variables() -> set[str]:
    rows = load_dashboard_chart_policy().get("excluded_variables") or []
    return {str(name).strip() for name in rows if str(name).strip()}


def filter_dashboard_section(section: dict[str, Any]) -> dict[str, Any]:
    excluded = excluded_dashboard_variables()
    if not excluded:
        return section

    filtered = dict(section)
    variables = filtered.get("variables") or {}
    if isinstance(variables, dict):
        filtered["variables"] = {key: value for key, value in variables.items() if key not in excluded}

    groups = filtered.get("variable_groups")
    if isinstance(groups, list):
        next_groups: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            vars_in_group = group.get("variables") or []
            if not isinstance(vars_in_group, list):
                continue
            kept = [item for item in vars_in_group if str(item.get("access") or "") not in excluded]
            if kept:
                next_groups.append({**group, "variables": kept})
        filtered["variable_groups"] = next_groups

    return filtered
