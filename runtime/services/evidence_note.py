"""Server-side evidence formatting, pathway status, solutions, and panel summaries."""

from __future__ import annotations

import re
from typing import Any

from services.diagnosis_revision import (
    _humanize_pathway,
    _min_confirms_required_from_note,
    pathways_ruled_out_from_signal_evaluation,
)

DEFAULT_RETRIEVAL_PROBE = (
    "agriculture water scarcity groundwater drought landscape stress micro-watershed diagnosis"
)

SOLUTIONS_CAP = 12


def _pathway_evidence_note(bundle: dict[str, dict] | None, pathway_id: str) -> str:
    if not bundle:
        return ""
    data = bundle.get(pathway_id) or {}
    card = data.get("evidence_card") or {}
    return str(card.get("overall_reasoning_note") or data.get("overall_reasoning_note") or "")


def _location_context(location: dict[str, Any] | None) -> str:
    if not location:
        return ""
    uid = str(location.get("uid") or "").strip()
    villages = location.get("village_names") or []
    if isinstance(villages, list):
        village_text = ", ".join(str(v) for v in villages if v)
    else:
        village_text = ""
    parts: list[str] = []
    if uid:
        parts.append(f"MWS {uid}")
    if village_text:
        parts.append(f"villages {village_text}")
    return " · ".join(parts)


def _true_confirming_signals(pathway_eval: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for signal in pathway_eval.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        if signal.get("direction") != "confirms":
            continue
        if signal.get("result") is not True:
            continue
        sig_id = str(signal.get("signal_id") or "?")
        status = signal.get("status")
        if status == "user_provided":
            lines.append(f"{sig_id} TRUE (your answer)")
        else:
            lines.append(f"{sig_id} TRUE")
    return lines


def _has_evaluated_confirms_false(pathway_eval: dict[str, Any]) -> bool:
    for signal in pathway_eval.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        if signal.get("direction") != "confirms":
            continue
        if signal.get("status") not in {"ok", "user_provided"}:
            continue
        if signal.get("result") is False:
            return True
    return False


def _pathway_should_omit(
    pathway_eval: dict[str, Any],
    *,
    outstanding_missing: set[str],
    needs_llm: int,
    eligible_questions: list[dict[str, str]],
) -> bool:
    """Drop a pathway when landscape contradicts it and no follow-up can change the verdict."""
    summary = pathway_eval.get("summary") or {}
    confirms_true = int(summary.get("confirms_true") or 0)
    amplifies_true = int(summary.get("amplifies_true") or 0)
    has_gap = bool(outstanding_missing) or needs_llm > 0 or bool(eligible_questions)

    if has_gap or confirms_true > 0:
        return False

    if _has_evaluated_confirms_false(pathway_eval):
        return True

    if confirms_true == 0 and amplifies_true == 0:
        return True

    return False


def _confidence_from_confirms(pathway_id: str, confirms_true: int, bundle: dict[str, dict] | None) -> str:
    if confirms_true <= 0:
        return "low"
    note = _pathway_evidence_note(bundle, pathway_id)
    min_required = _min_confirms_required_from_note(note)
    if confirms_true == 1:
        return "medium"
    if confirms_true >= min_required:
        return "high"
    return "medium"


def _truncate_note(note: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(note or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def format_pathway_reasoning(
    pathway_id: str,
    *,
    location: dict[str, Any] | None,
    pathway_eval: dict[str, Any],
    bundle: dict[str, dict] | None,
    status: str,
) -> str:
    """Server-authored pathway reasoning from signal evaluation and card note."""
    label = _humanize_pathway(pathway_id)
    summary = pathway_eval.get("summary") or {}
    confirms_true = int(summary.get("confirms_true") or 0)
    loc = _location_context(location)
    parts: list[str] = []

    if loc:
        parts.append(f"For {loc},")
    if status == "confirmed":
        parts.append(f"{label} is supported by landscape data")
        true_signals = _true_confirming_signals(pathway_eval)
        if true_signals:
            parts.append(f"({', '.join(true_signals[:4])})")
        parts.append(f"with {confirms_true} confirming signal(s) TRUE.")
    else:
        parts.append(f"{label} remains uncertain:")
        missing = []
        if bundle:
            data = bundle.get(pathway_id) or {}
            missing = list(data.get("missing_variables") or [])[:4]
        if missing:
            parts.append(f"follow-up needed on {', '.join(missing)}.")
        else:
            parts.append("key diagnostic variables are not yet available.")

    note = pathway_eval.get("evidence_note") or _pathway_evidence_note(bundle, pathway_id)
    excerpt = _truncate_note(str(note))
    if excerpt:
        parts.append(f"Evidence note: {excerpt}")
    return " ".join(parts)


def _missing_questions_for_pathway(
    pathway_id: str,
    bundle: dict[str, dict],
    *,
    injected: dict[str, Any] | None,
) -> list[dict[str, str]]:
    data = bundle.get(pathway_id) or {}
    present = set((data.get("present_variables") or {}).keys())
    if injected:
        present |= set(injected.keys())
    missing = set(data.get("missing_variables") or [])
    out: list[dict[str, str]] = []
    for q in data.get("missing_variable_questions") or []:
        if not isinstance(q, dict):
            continue
        var = str(q.get("missing_variable") or q.get("variable") or "").strip()
        question = str(q.get("question_to_user") or q.get("question") or "").strip()
        if not var or not question or var not in missing or var in present:
            continue
        out.append({"variable": var, "question": question})
    return out


def pathway_status_from_evaluation(
    signal_eval: dict[str, dict[str, Any]],
    bundle: dict[str, dict],
    *,
    injected_variables: dict[str, Any] | None = None,
    ruled_out_ids: set[str] | None = None,
    location: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Derive confirmed and uncertain pathway lists from server signal evaluation."""
    ruled_out = ruled_out_ids if ruled_out_ids is not None else pathways_ruled_out_from_signal_evaluation(signal_eval)
    injected = injected_variables or {}
    confirmed: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []

    for pathway_id in bundle:
        if pathway_id in ruled_out:
            continue
        pathway_eval = signal_eval.get(pathway_id) or {}
        summary = pathway_eval.get("summary") or {}
        if int(summary.get("rules_out_true") or 0) > 0:
            continue

        confirms_true = int(summary.get("confirms_true") or 0)
        bundle_data = bundle.get(pathway_id) or {}
        missing = set(bundle_data.get("missing_variables") or [])
        present = set((bundle_data.get("present_variables") or {}).keys()) | set(injected.keys())
        outstanding_missing = missing - present

        if confirms_true >= 1:
            confidence = _confidence_from_confirms(pathway_id, confirms_true, bundle)
            confirmed.append(
                {
                    "pathway_id": pathway_id,
                    "confidence": confidence,
                    "reasoning": format_pathway_reasoning(
                        pathway_id,
                        location=location,
                        pathway_eval=pathway_eval,
                        bundle=bundle,
                        status="confirmed",
                    ),
                }
            )
            continue

        needs_llm = int(summary.get("needs_llm") or 0)
        questions = _missing_questions_for_pathway(pathway_id, bundle, injected=injected)
        if _pathway_should_omit(
            pathway_eval,
            outstanding_missing=outstanding_missing,
            needs_llm=needs_llm,
            eligible_questions=questions,
        ):
            continue

        uncertain.append(
            {
                "pathway_id": pathway_id,
                "confidence": "low",
                "reasoning": format_pathway_reasoning(
                    pathway_id,
                    location=location,
                    pathway_eval=pathway_eval,
                    bundle=bundle,
                    status="uncertain",
                ),
                "missing_variable_questions": questions,
            }
        )

    return {"confirmed_pathways": confirmed, "uncertain_pathways": uncertain}


def solutions_for_confirmed_pathways(
    confirmed_ids: list[str],
    bundle: dict[str, dict],
    *,
    cap: int = SOLUTIONS_CAP,
) -> list[str]:
    """Deduplicated union of framework solutions for confirmed pathways."""
    seen: set[str] = set()
    out: list[str] = []
    for pathway_id in confirmed_ids:
        data = bundle.get(pathway_id) or {}
        for item in data.get("solutions") or []:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
            if len(out) >= cap:
                return out
    return out


def build_server_panel_summary(
    location: dict[str, Any] | None,
    confirmed: list[dict[str, Any]],
    uncertain: list[dict[str, Any]],
    signal_eval: dict[str, dict[str, Any]],
    *,
    problem_description: str | None = None,
) -> str:
    """Deterministic panel explanation when LLM is off."""
    loc = _location_context(location)
    parts: list[str] = []

    if loc:
        parts.append(f"Landscape diagnosis for {loc}.")
    else:
        parts.append("Landscape diagnosis from server signal evaluation.")

    if confirmed:
        labels = []
        for pathway in confirmed:
            pid = str(pathway.get("pathway_id") or "")
            conf = str(pathway.get("confidence") or "medium")
            summary = (signal_eval.get(pid) or {}).get("summary") or {}
            ct = summary.get("confirms_true", 0)
            labels.append(f"{_humanize_pathway(pid)} ({conf}, {ct} confirming TRUE)")
        parts.append("Confirmed: " + "; ".join(labels) + ".")
    else:
        parts.append("No pathways confirmed from current landscape data.")

    if uncertain:
        unc = ", ".join(_humanize_pathway(str(p.get("pathway_id") or "")) for p in uncertain[:4])
        parts.append(f"Uncertain (follow-up may help): {unc}.")

    problem = str(problem_description or "").strip()
    if problem:
        parts.append(f"Regarding your question — {problem[:160]}{'…' if len(problem) > 160 else ''}")

    return " ".join(parts)


def build_follow_up_panel_summary(revision: dict[str, Any] | None) -> str | None:
    """Use server revision summary as panel explanation on follow-up turns."""
    if not revision:
        return None
    summary = revision.get("summary")
    if summary and str(summary).strip():
        return str(summary).strip()
    return None
