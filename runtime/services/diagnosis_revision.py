"""Compare diagnosis turns and normalize qualitative follow-up answers."""

from __future__ import annotations

import json
from typing import Any


def normalize_qualitative_answer(variable: str, raw_answer: str) -> dict[str, Any]:
    """Parse free-text follow-up answers into structured evidence."""
    text = str(raw_answer or "").strip()
    lower = text.lower()

    negative = any(
        phrase in lower
        for phrase in (
            "no ",
            "not ",
            "never",
            "none",
            "don't",
            "doesn't",
            "didn't",
            "no sign",
            "not observed",
            "not happening",
        )
    )
    affirmative = any(
        phrase in lower
        for phrase in (
            "yes",
            "yeah",
            "yep",
            "confirmed",
            "observed",
            "happening",
            "worsened",
            "worsening",
            "increasing",
            "declining",
            "we have seen",
            "has been",
        )
    )
    worsening = any(w in lower for w in ("worsen", "worse", "increas", "growing", "more frequent", "declin"))
    improving = any(w in lower for w in ("improv", "better", "decreas", "less frequent", "stable", "recover"))

    if affirmative and not negative:
        present: bool | None = True
    elif negative and not affirmative:
        present = False
    else:
        present = None

    trend: str | None = None
    if worsening and not improving:
        trend = "worsening"
    elif improving and not worsening:
        trend = "improving"

    return {
        "variable": variable,
        "raw": text,
        "present": present,
        "trend": trend,
    }


def build_retrieval_query(problem_description: str, injected_variables: dict[str, Any] | None) -> str:
    """Augment the retrieval query with user-supplied field evidence."""
    parts = [problem_description.strip()]
    for variable, value in (injected_variables or {}).items():
        if isinstance(value, dict):
            snippet = value.get("raw") or json.dumps(value, default=str)
        else:
            snippet = str(value)
        parts.append(f"{variable}: {snippet}")
    return " | ".join(p for p in parts if p)


def _pathway_maps(response: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict]]:
    confirmed = {
        str(p["pathway_id"]): p
        for p in response.get("confirmed_pathways") or []
        if isinstance(p, dict) and p.get("pathway_id")
    }
    uncertain = {
        str(p["pathway_id"]): p
        for p in response.get("uncertain_pathways") or []
        if isinstance(p, dict) and p.get("pathway_id")
    }
    return confirmed, uncertain


def _status(pathway_id: str, confirmed: dict[str, dict], uncertain: dict[str, dict]) -> str:
    if pathway_id in confirmed:
        return "confirmed"
    if pathway_id in uncertain:
        return "uncertain"
    return "absent"


def _humanize_pathway(pathway_id: str) -> str:
    return pathway_id.split("__")[-1].replace("_", " ")


def compute_diagnosis_revision(
    prior: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    answered_variable: str | None = None,
) -> dict[str, Any]:
    """Diff two diagnosis payloads and summarize whether the ranking materially changed."""
    if not prior:
        return {"improved": False, "summary": None, "pathway_changes": []}

    prior_conf, prior_unc = _pathway_maps(prior)
    curr_conf, curr_unc = _pathway_maps(current)
    all_ids = set(prior_conf) | set(prior_unc) | set(curr_conf) | set(curr_unc)

    changes: list[dict[str, str]] = []
    for pathway_id in sorted(all_ids, key=_humanize_pathway):
        before = _status(pathway_id, prior_conf, prior_unc)
        after = _status(pathway_id, curr_conf, curr_unc)
        label = _humanize_pathway(pathway_id)

        if before == after:
            if before == "confirmed":
                prev_conf = prior_conf[pathway_id].get("confidence")
                next_conf = curr_conf[pathway_id].get("confidence")
                if prev_conf and next_conf and prev_conf != next_conf:
                    changes.append(
                        {
                            "pathway_id": pathway_id,
                            "from": f"confirmed ({prev_conf})",
                            "to": f"confirmed ({next_conf})",
                            "reason": f"Confidence for {label} changed after incorporating new evidence.",
                        }
                    )
            continue

        if before == "uncertain" and after == "confirmed":
            reason = f"New user evidence strengthened support for {label}."
        elif before == "confirmed" and after == "uncertain":
            reason = f"Support for {label} weakened after reassessment."
        elif before == "confirmed" and after == "absent":
            reason = f"{label.title()} was removed from the confirmed set."
        elif before == "uncertain" and after == "absent":
            reason = f"{label.title()} is no longer listed as uncertain."
        elif before == "absent" and after == "confirmed":
            reason = f"{label.title()} is newly confirmed."
        elif before == "absent" and after == "uncertain":
            reason = f"{label.title()} is now listed as uncertain."
        else:
            reason = f"Status for {label} changed from {before} to {after}."

        if answered_variable:
            reason += f" Follow-up variable: {answered_variable}."

        changes.append(
            {
                "pathway_id": pathway_id,
                "from": before,
                "to": after,
                "reason": reason,
            }
        )

    solutions_changed = set(prior.get("solutions") or []) != set(current.get("solutions") or [])
    improved = bool(changes) or solutions_changed

    if not improved:
        summary = (
            "Your answer was recorded and added to the evidence bundle, "
            "but the pathway ranking did not change materially."
        )
    elif len(changes) == 1:
        change = changes[0]
        summary = (
            f"{_humanize_pathway(change['pathway_id']).title()} moved from "
            f"{change['from']} to {change['to']}."
        )
    else:
        promoted = [
            _humanize_pathway(c["pathway_id"])
            for c in changes
            if c["from"] == "uncertain" and c["to"] == "confirmed"
        ]
        if promoted:
            summary = f"Diagnosis updated: {', '.join(promoted)} confirmed after your follow-up answer."
        else:
            summary = f"Diagnosis updated after your follow-up answer ({len(changes)} pathway changes)."

    return {
        "improved": improved,
        "summary": summary,
        "pathway_changes": changes,
    }


def prior_diagnosis_from_session(session: dict[str, Any] | None) -> dict[str, Any] | None:
    if not session:
        return None
    turns = session.get("turns") or []
    if not turns:
        return None
    response = turns[-1].get("llm_response_json")
    return response if isinstance(response, dict) else None


def apply_follow_up_revision(
    response: dict[str, Any],
    prior: dict[str, Any] | None,
    *,
    answered_variable: str | None = None,
) -> dict[str, Any]:
    """Attach diagnosis_revision and gate panel updates when ranking did not improve."""
    out = dict(response)
    revision = compute_diagnosis_revision(prior, out, answered_variable=answered_variable)
    out["diagnosis_revision"] = revision

    if not revision.get("improved"):
        out["panel_updates"] = []
        if not out.get("panel_update_explanation"):
            out["panel_update_explanation"] = revision.get("summary")
    elif revision.get("summary") and not out.get("panel_update_explanation"):
        out["panel_update_explanation"] = revision["summary"]

    return out
