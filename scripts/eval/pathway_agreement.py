"""Cohen's kappa for pathway confirmation agreement across diagnosis modes."""

from __future__ import annotations

from typing import Any

ConfirmationLevel = str  # high | medium | unconfirmed


def _norm_confidence(value: Any) -> str:
    text = str(value or "medium").strip().lower()
    if text in {"high", "medium", "low"}:
        return text
    return "medium"


def server_pathway_level(diagnosis: dict[str, Any], pathway_id: str) -> ConfirmationLevel:
    for item in diagnosis.get("confirmed_pathways") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("pathway_id") or "") != pathway_id:
            continue
        conf = _norm_confidence(item.get("confidence"))
        return "high" if conf == "high" else "medium"
    for item in diagnosis.get("uncertain_pathways") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("pathway_id") or "") == pathway_id:
            return "medium"
    return "unconfirmed"


def independent_pathway_level(diagnosis: dict[str, Any], pathway_id: str) -> ConfirmationLevel:
    for item in diagnosis.get("independent_pathway_review") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("pathway_id") or "") != pathway_id:
            continue
        present = str(item.get("pathway_present") or "uncertain").lower()
        if present == "no":
            return "unconfirmed"
        conf = _norm_confidence(item.get("confidence"))
        if present == "yes" and conf == "high":
            return "high"
        return "medium"
    return "unconfirmed"


def pathway_ids_union(*diagnoses: dict[str, Any]) -> list[str]:
    ids: set[str] = set()
    for diagnosis in diagnoses:
        for bucket in ("confirmed_pathways", "uncertain_pathways"):
            for item in diagnosis.get(bucket) or []:
                if isinstance(item, dict) and item.get("pathway_id"):
                    ids.add(str(item["pathway_id"]))
        for item in diagnosis.get("independent_pathway_review") or []:
            if isinstance(item, dict) and item.get("pathway_id"):
                ids.add(str(item["pathway_id"]))
    return sorted(ids)


def _category_distribution(labels: list[str]) -> dict[str, float]:
    if not labels:
        return {}
    n = len(labels)
    cats = sorted(set(labels))
    return {cat: round(labels.count(cat) / n, 4) for cat in cats}


def _cohens_kappa(labels_a: list[str], labels_b: list[str]) -> tuple[float | None, float, float]:
    """Return (kappa, observed_agreement, expected_agreement)."""
    if len(labels_a) != len(labels_b) or not labels_a:
        return None, 0.0, 0.0
    categories = sorted(set(labels_a) | set(labels_b))
    n = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n

    dist_a = {cat: labels_a.count(cat) / n for cat in categories}
    dist_b = {cat: labels_b.count(cat) / n for cat in categories}
    expected = sum(dist_a.get(cat, 0.0) * dist_b.get(cat, 0.0) for cat in categories)
    if expected >= 1.0:
        kappa = 1.0 if observed >= 1.0 else 0.0
    else:
        kappa = round((observed - expected) / (1.0 - expected), 4)
    return kappa, round(observed, 4), round(expected, 4)


def agreement_between(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    left_source: str,
    right_source: str,
) -> dict[str, Any]:
    left_fn = server_pathway_level if left_source == "server" else independent_pathway_level
    right_fn = server_pathway_level if right_source == "server" else independent_pathway_level
    pathway_ids = pathway_ids_union(left, right)
    left_labels = [left_fn(left, pid) for pid in pathway_ids]
    right_labels = [right_fn(right, pid) for pid in pathway_ids]
    kappa, observed, expected = _cohens_kappa(left_labels, right_labels)
    exact = sum(1 for a, b in zip(left_labels, right_labels) if a == b)
    return {
        "kappa": kappa,
        "observed_agreement": observed,
        "expected_agreement": expected,
        "pathway_count": len(pathway_ids),
        "exact_agreements": exact,
        "left_source": left_source,
        "right_source": right_source,
        "left_distribution": _category_distribution(left_labels),
        "right_distribution": _category_distribution(right_labels),
        "kappa_formula": "kappa = (observed_agreement - expected_agreement) / (1 - expected_agreement)",
        "level_scale": {
            "high": "confirmed at high confidence (server) or pathway_present=yes with high confidence (LLM)",
            "medium": "uncertain pathway or medium/low confidence confirmed (server) or yes/uncertain (LLM)",
            "unconfirmed": "pathway absent from server lists or pathway_present=no (LLM)",
        },
        "pathways": [
            {
                "pathway_id": pid,
                "left": left_labels[i],
                "right": right_labels[i],
                "agree": left_labels[i] == right_labels[i],
            }
            for i, pid in enumerate(pathway_ids)
        ],
    }


def query_run_agreement(
    *,
    server_diagnosis: dict[str, Any] | None,
    ollama_diagnosis: dict[str, Any] | None,
    claude_diagnosis: dict[str, Any] | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if server_diagnosis and ollama_diagnosis:
        out["server_vs_ollama_independent"] = agreement_between(
            server_diagnosis,
            ollama_diagnosis,
            left_source="server",
            right_source="independent",
        )
    if server_diagnosis and claude_diagnosis:
        out["server_vs_claude_independent"] = agreement_between(
            server_diagnosis,
            claude_diagnosis,
            left_source="server",
            right_source="independent",
        )
    if ollama_diagnosis and claude_diagnosis:
        out["ollama_vs_claude_independent"] = agreement_between(
            ollama_diagnosis,
            claude_diagnosis,
            left_source="independent",
            right_source="independent",
        )
    return out
