"""Search variables for the signal expression builder."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "metadata" / "variable_registry.json"
DICTIONARY_PATH = ROOT / "metadata" / "data_dictionary_v2.json"


@lru_cache(maxsize=1)
def _load_registry_variables() -> dict[str, dict[str, Any]]:
    if not REGISTRY_PATH.is_file():
        return {}
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    variables = data.get("variables") or {}
    return {str(k): v for k, v in variables.items() if isinstance(v, dict)}


@lru_cache(maxsize=1)
def _load_dictionary_labels() -> dict[str, str]:
    if not DICTIONARY_PATH.is_file():
        return {}
    data = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    variables = data.get("variables") or {}
    labels: dict[str, str] = {}
    for name, spec in variables.items():
        if not isinstance(spec, dict):
            continue
        label = spec.get("label") or spec.get("description") or name
        labels[str(name)] = str(label)
    return labels


def search_variables(query: str = "", *, limit: int = 50) -> list[dict[str, Any]]:
    q = str(query or "").strip().lower()
    registry = _load_registry_variables()
    labels = _load_dictionary_labels()
    results: list[dict[str, Any]] = []

    for name, spec in sorted(registry.items()):
        label = labels.get(name, name)
        haystack = f"{name} {label} {spec.get('type', '')}".lower()
        if q and q not in haystack and not any(token in haystack for token in q.split()):
            continue
        results.append(
            {
                "name": name,
                "label": label,
                "type": spec.get("type"),
                "mongo_field": spec.get("mongo_field"),
            }
        )
        if len(results) >= limit:
            break
    return results
