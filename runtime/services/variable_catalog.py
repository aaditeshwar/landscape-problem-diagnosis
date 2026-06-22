"""Variable catalog for the triage variable-list page."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from config import ROOT
from services.expression_variable_access import expression_variable_accesses
from services.variable_categories import categorize_variable, category_sort_key
from services.variable_registry import (
    load_data_dictionary,
    variable_type_catalog,
)

RAW_CARDS_DIR = ROOT / "data" / "evidence_cards" / "raw"


def _display_type(meta: dict[str, Any], type_info: dict[str, Any]) -> str:
    shape = str(type_info.get("shape") or "")
    if shape == "dict" or "keyed" in str(meta.get("description") or "").lower():
        return "dict"
    if shape in {"time_series_yearly", "time_series_seasonal"}:
        return "list"
    if shape == "scalar_categorical" or "categorical" in str(meta.get("unit") or "").lower():
        return "categorical"
    var_type = str(meta.get("type") or type_info.get("type") or "")
    if var_type == "derived":
        return "derived"
    if var_type == "time_series":
        return "list"
    return "scalar"


def _source_label(meta: dict[str, Any]) -> str:
    availability = str(meta.get("availability") or "")
    if availability == "not_available":
        return "not available"
    if availability == "derived" or meta.get("computation"):
        return str(meta.get("computation") or "derived")
    sheet = meta.get("source_sheet")
    column = meta.get("source_column")
    if sheet and column:
        return f"{sheet} · {column}"
    if sheet:
        return str(sheet)
    return availability or "—"

def _load_cards_from_disk() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    if not RAW_CARDS_DIR.is_dir():
        return cards
    for path in sorted(RAW_CARDS_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict):
            cards.append(payload)
    return cards


def _scan_signal_usages(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    usages: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: set[tuple[str, str, str, str]] = set()

    for card in cards:
        card_id = str(card.get("card_id") or "")
        for signal in card.get("diagnostic_signals") or []:
            if not isinstance(signal, dict):
                continue
            signal_id = str(signal.get("signal_id") or "")
            condition = signal.get("condition") or {}
            expression = str(condition.get("expression") or signal.get("expression") or "").strip()
            if not expression:
                continue
            for access in expression_variable_accesses(expression):
                base = access.split("[", 1)[0].split("(", 1)[0]
                key = (base, card_id, signal_id, access)
                if key in seen:
                    continue
                seen.add(key)
                usages[base].append(
                    {
                        "card_id": card_id,
                        "signal_id": signal_id,
                        "access": access,
                        "expression": expression,
                    }
                )
    return usages


def build_variable_catalog() -> dict[str, Any]:
    dd = load_data_dictionary()
    type_catalog = variable_type_catalog()
    variables_meta = dd.get("variables") or {}
    usages = _scan_signal_usages(_load_cards_from_disk())

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for name in sorted(variables_meta.keys()):
        meta = variables_meta.get(name) or {}
        if not isinstance(meta, dict):
            continue
        category = categorize_variable(name)
        type_info = type_catalog.get(name) or {}
        display_type = _display_type(meta, type_info)
        grouped[category].append(
            {
                "name": name,
                "display_type": display_type,
                "type": meta.get("type") or type_info.get("type"),
                "shape": type_info.get("shape"),
                "unit": meta.get("unit"),
                "availability": meta.get("availability"),
                "source": _source_label(meta),
                "description": meta.get("description"),
                "computation": meta.get("computation"),
                "source_sheet": meta.get("source_sheet"),
                "signal_usages": usages.get(name, []),
            }
        )

    sections = [
        {"category": category, "variables": grouped[category]}
        for category in sorted(grouped.keys(), key=category_sort_key)
    ]
    return {
        "schema_version": 1,
        "dictionary_version": dd.get("version"),
        "section_count": len(sections),
        "variable_count": sum(len(section["variables"]) for section in sections),
        "sections": sections,
    }
