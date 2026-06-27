"""Build labelled MWS corpora from case-study catalog and raw_jsons exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RAW_JSONS_DIR = ROOT / "data" / "raw_jsons"
RAW_CARDS_DIR = ROOT / "data" / "evidence_cards" / "raw"


def load_mws_export(mws_id: str) -> dict[str, Any] | None:
    path = RAW_JSONS_DIR / f"{mws_id}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def load_pathway_cards(causal_pathway: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    pattern = f"*__{causal_pathway}__*.json"
    for path in sorted(RAW_CARDS_DIR.glob(pattern)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict):
            cards.append(payload)
    return cards


def pathway_section(cards: list[dict[str, Any]]) -> tuple[str, str, str]:
    if not cards:
        raise ValueError("No cards for pathway")
    first = cards[0]
    return (
        str(first.get("production_system") or ""),
        str(first.get("observed_stress") or ""),
        str(first.get("causal_pathway") or ""),
    )


def positive_mws_ids(
    case_study_rows: list[dict[str, Any]],
    *,
    production_system: str,
    observed_stress: str,
    causal_pathway: str,
) -> set[str]:
    return {
        str(row.get("mws_id") or "").strip()
        for row in case_study_rows
        if row.get("production_system") == production_system
        and row.get("observed_stress") == observed_stress
        and row.get("expected_pathway") == causal_pathway
        and not row.get("stress_only")
        and str(row.get("mws_id") or "").strip()
    }


def corpus_mws_ids(
    case_study_rows: list[dict[str, Any]],
    *,
    production_system: str,
) -> set[str]:
    return {
        str(row.get("mws_id") or "").strip()
        for row in case_study_rows
        if row.get("production_system") == production_system
        and not row.get("stress_only")
        and str(row.get("mws_id") or "").strip()
    }


def assign_labels(
    case_study_rows: list[dict[str, Any]],
    *,
    production_system: str,
    observed_stress: str,
    causal_pathway: str,
    aer_filter: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Return (positives, negatives, missing_uids)."""
    pos_ids = positive_mws_ids(
        case_study_rows,
        production_system=production_system,
        observed_stress=observed_stress,
        causal_pathway=causal_pathway,
    )
    corpus_ids = corpus_mws_ids(case_study_rows, production_system=production_system)
    positives: list[dict[str, Any]] = []
    negatives: list[dict[str, Any]] = []
    missing: list[str] = []

    for mws_id in sorted(corpus_ids):
        export = load_mws_export(mws_id)
        if export is None:
            missing.append(mws_id)
            continue
        aer = str((export.get("location_context") or {}).get("nbss_lup_aer_code") or "")
        if aer_filter and aer != aer_filter:
            continue
        if mws_id in pos_ids:
            positives.append(export)
        else:
            negatives.append(export)

    return positives, negatives, missing


def feasibility_ok(positives: list[Any], negatives: list[Any], *, min_pos: int = 2, min_neg: int = 3) -> bool:
    return len(positives) >= min_pos and len(negatives) >= min_neg
