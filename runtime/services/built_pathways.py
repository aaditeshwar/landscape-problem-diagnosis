"""Causal pathways with evidence cards in the diagnosis stack."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from config import ROOT

BUILT_PATHWAY_IDS: frozenset[str] = frozenset(
    {
        "drought",
        "groundwater_stress",
        "rainfed_risk",
        "irrigation_challenges",
        "forest_degradation",
        "encroachment",
        "multi_sector_vulnerability",
        "small_landholding",
    }
)

NONE_OF_THESE_PATHWAY = "__none_of_these__"
STRESS_ONLY_PATHWAY = "__stress_only__"

RAW_CARDS_DIR = ROOT / "data" / "evidence_cards" / "raw"


@lru_cache
def built_pathway_tuples() -> frozenset[tuple[str, str, str]]:
    """(production_system, observed_stress, causal_pathway) with at least one evidence card."""
    tuples: set[tuple[str, str, str]] = set()
    if not RAW_CARDS_DIR.is_dir():
        return frozenset()
    for path in RAW_CARDS_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(payload, dict):
            continue
        production = str(payload.get("production_system") or "").strip()
        stress = str(payload.get("observed_stress") or "").strip()
        pathway = str(payload.get("causal_pathway") or "").strip()
        if production and stress and pathway and pathway in BUILT_PATHWAY_IDS:
            tuples.add((production, stress, pathway))
    return frozenset(tuples)


def built_pathways_for_section(production_system: str, observed_stress: str) -> list[str]:
    """Built causal pathways that have evidence cards for this (production_system, observed_stress)."""
    return sorted(
        pathway
        for ps, stress, pathway in built_pathway_tuples()
        if ps == production_system and stress == observed_stress
    )


def section_has_built_pathways(production_system: str, observed_stress: str) -> bool:
    return bool(built_pathways_for_section(production_system, observed_stress))
