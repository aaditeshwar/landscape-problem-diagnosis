"""Filter query_bank.json to queries runnable against built pathways."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.case_study_index import BUILT_PATHWAY_IDS, ROOT

QUERY_BANK_PATH = ROOT / "scripts" / "reference" / "query_bank.json"
RUBRIC_PATH = ROOT / "scripts" / "reference" / "evaluation_rubric.json"


def load_query_bank() -> dict[str, Any]:
    with QUERY_BANK_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_rubric() -> dict[str, Any]:
    with RUBRIC_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def query_pathways_eligible(query: dict[str, Any]) -> tuple[bool, str]:
    candidates = query.get("expected_pathway_candidates") or []
    if not candidates:
        return False, "no expected_pathway_candidates"
    unbuilt = [p for p in candidates if p not in BUILT_PATHWAY_IDS]
    if unbuilt:
        return False, f"unbuilt pathways: {', '.join(unbuilt)}"
    return True, ""


def eligible_queries() -> list[dict[str, Any]]:
    bank = load_query_bank()
    rows: list[dict[str, Any]] = []
    for query in bank.get("queries") or []:
        if not isinstance(query, dict):
            continue
        ok, reason = query_pathways_eligible(query)
        if ok:
            rows.append(query)
    return rows


def excluded_queries() -> list[dict[str, Any]]:
    bank = load_query_bank()
    rows: list[dict[str, Any]] = []
    for query in bank.get("queries") or []:
        if not isinstance(query, dict):
            continue
        ok, reason = query_pathways_eligible(query)
        if not ok:
            rows.append(
                {
                    "id": query.get("id"),
                    "expected_pathway_candidates": query.get("expected_pathway_candidates"),
                    "reason": reason,
                }
            )
    return rows


def _production_system_matches(query: dict[str, Any], case_study: dict[str, Any]) -> bool:
    q_prod = str(query.get("production_system") or "").strip().lower()
    cs_prod = str(case_study.get("production_system") or "").strip().lower()
    if not q_prod or not cs_prod:
        return True
    return q_prod == cs_prod


def built_systems_query() -> dict[str, Any]:
    """Synthetic Q000 — always run first for every case study."""
    try:
        runtime_dir = ROOT / "runtime"
        if str(runtime_dir) not in __import__("sys").path:
            __import__("sys").path.insert(0, str(runtime_dir))
        from services.built_pathways import built_pathway_tuples  # noqa: E402

        tuples = built_pathway_tuples()
    except ImportError:
        tuples = frozenset()

    by_prod: dict[str, dict[str, list[str]]] = {}
    for production, stress, pathway in sorted(tuples):
        by_prod.setdefault(production, {}).setdefault(stress, []).append(pathway.replace("_", " "))

    parts: list[str] = []
    for production in sorted(by_prod):
        stress_bits: list[str] = []
        for stress in sorted(by_prod[production]):
            pathways = ", ".join(sorted(by_prod[production][stress]))
            stress_bits.append(f"{stress.replace('_', ' ')} ({pathways})")
        parts.append(f"{production.replace('_', ' ')} ({'; '.join(stress_bits)})")

    systems_text = ", ".join(parts) if parts else "all built production systems"
    query_text = (
        "Diagnose various problems in this landscape related to production systems of "
        f"{systems_text}. "
        "Based on the diagnosis, recommend actionable solutions and interventions appropriate for this area."
    )
    return {
        "id": "Q000",
        "persona": "diagnostics_engine",
        "production_system": "Multi-system",
        "sub_theme": "built_pathways_overview",
        "query": query_text,
        "intent": "Broad landscape diagnosis across all built causal pathways.",
        "expected_pathway_candidates": sorted(BUILT_PATHWAY_IDS),
    }


def queries_for_case_study(case_study: dict[str, Any]) -> list[dict[str, Any]]:
    """Queries whose pathway candidates are built and relevant to this case study."""
    expected = str(case_study.get("expected_pathway") or "").strip()
    stress_only = bool(case_study.get("stress_only"))
    rows: list[dict[str, Any]] = [built_systems_query()]
    seen_ids = {"Q000"}
    for query in eligible_queries():
        qid = str(query.get("id") or "")
        if qid in seen_ids:
            continue
        if not _production_system_matches(query, case_study):
            continue
        candidates = [str(p) for p in (query.get("expected_pathway_candidates") or [])]
        if stress_only:
            rows.append(query)
            seen_ids.add(qid)
            continue
        if expected and expected in candidates:
            rows.append(query)
            seen_ids.add(qid)
            continue
        if not expected:
            rows.append(query)
            seen_ids.add(qid)
    return rows
