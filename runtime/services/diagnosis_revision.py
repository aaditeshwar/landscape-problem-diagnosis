"""Compare diagnosis turns and normalize qualitative follow-up answers."""

from __future__ import annotations

import json
import re
from typing import Any

from services.assembler import pathway_uses_variable


def card_update_rule_for_variable(card: dict[str, Any] | None, variable: str) -> str:
    """Return how_answer_updates_diagnosis text for a missing variable on an evidence card."""
    if not card or not variable:
        return ""
    for question in card.get("missing_variable_questions") or []:
        if not isinstance(question, dict):
            continue
        var = question.get("missing_variable") or question.get("variable")
        if str(var or "") == variable:
            return str(question.get("how_answer_updates_diagnosis") or "").strip()
    return ""


def _parse_percent_band(text: str) -> dict[str, Any]:
    """Extract a coarse band label from free-text percentage answers."""
    lower = text.lower()
    band: str | None = None
    percent_upper: float | None = None
    percent_lower: float | None = None

    less_match = re.search(
        r"(?:less than|below|under|fewer than|<)\s*(\d+(?:\.\d+)?)\s*%",
        lower,
    )
    more_match = re.search(
        r"(?:more than|above|over|greater than|>)\s*(\d+(?:\.\d+)?)\s*%",
        lower,
    )
    between_match = re.search(
        r"(?:between|from)\s*(\d+(?:\.\d+)?)\s*(?:%?\s*[-–to]+\s*|\s*and\s*)(\d+(?:\.\d+)?)\s*%",
        lower,
    )

    if less_match:
        percent_upper = float(less_match.group(1))
        if percent_upper <= 10:
            band = "low"
        elif percent_upper <= 30:
            band = "mid"
        else:
            band = "high"
    elif more_match:
        percent_lower = float(more_match.group(1))
        if percent_lower >= 30:
            band = "high"
        elif percent_lower >= 10:
            band = "mid"
        else:
            band = "low"
    elif between_match:
        lo = float(between_match.group(1))
        hi = float(between_match.group(2))
        percent_lower, percent_upper = lo, hi
        if hi <= 10:
            band = "low"
        elif lo >= 30:
            band = "high"
        else:
            band = "mid"
    else:
        approx_match = re.search(
            r"(?:about|around|approximately|roughly|~|approx\.?)\s*(\d+(?:\.\d+)?)\s*%",
            lower,
        )
        bare_match = re.search(
            r"(?<![<>=-])(\d+(?:\.\d+)?)\s*%\s*(?:of|is|are|households|irrigated|farmland|land|cultivated)?",
            lower,
        )
        value_match = approx_match or bare_match
        if value_match:
            value = float(value_match.group(1))
            if value < 10:
                band = "low"
            elif value <= 30:
                band = "mid"
                percent_lower, percent_upper = 10.0, 30.0
            else:
                band = "high"
                percent_lower = value
    if "very few" in lower or lower.strip() in {"few", "very few"}:
        band = "low"

    out: dict[str, Any] = {}
    if band:
        out["band"] = band
    if percent_lower is not None:
        out["percent_lower"] = percent_lower
    if percent_upper is not None:
        out["percent_upper"] = percent_upper
    return out


UNABLE_TO_EVALUATE_NOTE = (
    "Server unable to evaluate user response automatically; infer TRUE/FALSE using the raw answer and card update rule."
)


def match_update_rule_excerpt(update_rule: str, normalized: dict[str, Any]) -> tuple[str, bool]:
    """Pick the card sentence that best matches the user's answer band or polarity.

    Returns (excerpt, matched). When matched is False, callers must not treat excerpt as band-specific guidance.
    """
    text = str(update_rule or "").strip()
    if not text:
        return "", False

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if not sentences:
        sentences = [text]

    band = normalized.get("band")
    present = normalized.get("present")
    band_keywords = {
        "low": (
            "below 10",
            "less than 10",
            "low migration",
            "low out-migration",
            "fewer than 10",
        ),
        "mid": ("10–30", "10-30", "between 10", "10 to 30"),
        "high": (
            ">30",
            "more than 30",
            "above 30",
            "high out-migration",
            "high out migration",
            "high rates",
        ),
    }

    if band:
        keys = band_keywords.get(str(band), ())
        for sentence in sentences:
            lower = sentence.lower()
            if any(key in lower for key in keys):
                return sentence, True
        percent_lower = normalized.get("percent_lower")
        percent_upper = normalized.get("percent_upper")
        for sentence in sentences:
            lower = sentence.lower()
            if str(band) == "mid" and any(
                phrase in lower for phrase in ("10–30", "10-30", "partially confirmed", "partially")
            ):
                return sentence, True
            if str(band) == "high" and percent_lower is not None:
                if f"{int(percent_lower)}" in lower or "more than 30" in lower or "weakened" in lower:
                    return sentence, True
            if str(band) == "low" and percent_upper is not None:
                if f"{int(percent_upper)}" in lower or "less than 10" in lower or "strongly confirm" in lower:
                    return sentence, True
        return "", False

    if present is True:
        for sentence in sentences:
            lower = sentence.lower()
            if any(
                phrase in lower
                for phrase in (
                    "strongly confirm",
                    "confirms the",
                    "confirms multi",
                    "confirms groundwater",
                    "deepening",
                    "well depth",
                    "reported increase",
                    "gone dry",
                    "dug-well",
                    "dug well",
                    "deepens severity",
                    "trapped",
                )
            ):
                return sentence, True
        return "", False

    if present is False:
        for sentence in sentences:
            lower = sentence.lower()
            if any(
                phrase in lower
                for phrase in ("does not", "unlikely", "weakened", "less likely", "coping")
            ):
                return sentence, True
        return "", False

    return "", False


def _confirm_threshold_percent(update_rule: str) -> float | None:
    """Extract a minimum percent threshold from card guidance like 'more than 30%'."""
    text = str(update_rule or "").lower()
    for pattern in (
        r"more than\s+(\d+(?:\.\d+)?)\s*%",
        r"greater than\s+(\d+(?:\.\d+)?)\s*%",
        r"above\s+(\d+(?:\.\d+)?)\s*%",
        r"over\s+(\d+(?:\.\d+)?)\s*%",
    ):
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


def _band_representative_percent(normalized: dict[str, Any]) -> float | None:
    lower = normalized.get("percent_lower")
    upper = normalized.get("percent_upper")
    if lower is not None and upper is not None:
        return (float(lower) + float(upper)) / 2.0
    if upper is not None:
        return float(upper)
    if lower is not None:
        return float(lower)
    band = normalized.get("band")
    if band == "low":
        return 5.0
    if band == "mid":
        return 20.0
    if band == "high":
        return 40.0
    return None


def infer_from_update_rule_threshold(
    *,
    direction: str,
    normalized: dict[str, Any],
    update_rule: str,
) -> bool | None:
    """Infer TRUE/FALSE from percent bands when card guidance states an explicit threshold."""
    if direction != "confirms":
        return None
    threshold = _confirm_threshold_percent(update_rule)
    if threshold is None:
        return None
    value = _band_representative_percent(normalized)
    if value is None:
        return None
    if value > threshold:
        return True
    return False


def infer_user_signal_result(
    *,
    direction: str,
    normalized: dict[str, Any],
    update_excerpt: str,
    update_rule: str = "",
) -> bool | None:
    """Map card update text + normalized answer to TRUE/FALSE when unambiguous."""
    excerpt = str(update_excerpt or "").lower()
    present = normalized.get("present")
    band = normalized.get("band")
    trend = normalized.get("trend")

    if present is True and direction == "confirms":
        if trend == "worsening" or any(
            phrase in excerpt
            for phrase in ("strongly confirm", "confirms the", "confirms multi", "confirms groundwater")
        ):
            return True
        if any(
            phrase in excerpt
            for phrase in ("deepens severity", "trapped", "also confirms", "confirms economic")
        ):
            return True
        if band in {"low", "high"} and excerpt:
            if "does not strengthen" in excerpt or "weakened" in excerpt:
                return False
            if "strongly confirm" in excerpt or "confirms" in excerpt:
                return True
            if band == "low" and any(
                phrase in excerpt for phrase in ("trapped", "deepens severity", "acute")
            ):
                return True
        if present is True and not excerpt:
            return True

    if present is False and direction == "confirms":
        return False

    if band == "high" and direction == "confirms" and "strongly confirm" in excerpt:
        return True
    if band and direction == "confirms" and update_excerpt:
        lower = update_excerpt.lower()
        if any(
            phrase in lower
            for phrase in (
                "does not strengthen",
                "weakened",
                "less likely",
                "coping mechanisms",
                "effective local coping",
            )
        ):
            return False
        return True

    threshold_result = infer_from_update_rule_threshold(
        direction=direction,
        normalized=normalized,
        update_rule=update_rule,
    )
    if threshold_result is not None:
        return threshold_result

    return None


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

    out: dict[str, Any] = {
        "variable": variable,
        "raw": text,
        "present": present,
        "trend": trend,
    }
    out.update(_parse_percent_band(text))
    return out


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


def user_confirms_pathway_from_signals(
    signal_evaluation: dict[str, dict[str, Any]] | None,
    pathway_id: str,
    answered_variable: str,
) -> bool:
    """True when follow-up answer produced user_provided confirms+TRUE for this pathway."""
    pathway = (signal_evaluation or {}).get(pathway_id) or {}
    for signal in pathway.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        if signal.get("status") != "user_provided":
            continue
        if signal.get("answered_variable") != answered_variable:
            continue
        if signal.get("direction") == "confirms" and signal.get("result") is True:
            return True
    return False


def user_rules_out_pathway_from_signals(
    signal_evaluation: dict[str, dict[str, Any]] | None,
    pathway_id: str,
    answered_variable: str,
) -> bool:
    """True when user_provided confirms+FALSE, no confirms TRUE remain, for this pathway."""
    pathway = (signal_evaluation or {}).get(pathway_id) or {}
    summary = pathway.get("summary") or {}
    if summary.get("confirms_true", 0) > 0:
        return False
    for signal in pathway.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        if signal.get("status") != "user_provided":
            continue
        if signal.get("answered_variable") != answered_variable:
            continue
        if signal.get("direction") == "confirms" and signal.get("result") is False:
            return True
    return False


def pathways_ruled_out_from_signal_evaluation(
    signal_evaluation: dict[str, dict[str, Any]] | None,
) -> set[str]:
    """Pathways ruled out by any user_provided confirms+FALSE while confirms_true remains 0."""
    ruled_out: set[str] = set()
    for pathway_id, data in (signal_evaluation or {}).items():
        summary = data.get("summary") or {}
        if summary.get("confirms_true", 0) > 0:
            continue
        for signal in data.get("signals") or []:
            if not isinstance(signal, dict):
                continue
            if signal.get("status") != "user_provided":
                continue
            if signal.get("direction") == "confirms" and signal.get("result") is False:
                ruled_out.add(str(pathway_id))
                break
    return ruled_out


def pathway_has_new_confirming_evidence(
    pathway_id: str,
    signal_evaluation: dict[str, dict[str, Any]] | None,
    answered_variable: str | None = None,
) -> bool:
    """True when server signals show fresh support that overrides a prior rule-out."""
    pathway = (signal_evaluation or {}).get(pathway_id) or {}
    summary = pathway.get("summary") or {}
    if summary.get("confirms_true", 0) > 0:
        return True
    if answered_variable and user_confirms_pathway_from_signals(
        signal_evaluation,
        pathway_id,
        answered_variable,
    ):
        return True
    return False


def apply_ruled_out_guard(
    current: dict[str, Any],
    *,
    signal_evaluation: dict[str, dict[str, Any]] | None = None,
    answered_variable: str | None = None,
) -> dict[str, Any]:
    """Drop pathways the LLM re-added after a prior user rule-out without new confirming evidence."""
    ruled_out = pathways_ruled_out_from_signal_evaluation(signal_evaluation)
    if not ruled_out:
        return current

    out = dict(current)

    def _keep(pathway: dict[str, Any]) -> bool:
        pathway_id = str(pathway.get("pathway_id") or "")
        if not pathway_id or pathway_id not in ruled_out:
            return True
        return pathway_has_new_confirming_evidence(
            pathway_id,
            signal_evaluation,
            answered_variable,
        )

    out["confirmed_pathways"] = [
        pathway for pathway in out.get("confirmed_pathways") or [] if _keep(pathway)
    ]
    out["uncertain_pathways"] = [
        pathway for pathway in out.get("uncertain_pathways") or [] if _keep(pathway)
    ]
    return out


def apply_user_rule_out(
    current: dict[str, Any],
    answered_variable: str,
    *,
    signal_evaluation: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Drop pathways ruled out by user_provided confirms+FALSE when no confirms TRUE remain."""
    if not answered_variable or not signal_evaluation:
        return current

    out = dict(current)
    filtered_confirmed: list[dict[str, Any]] = []
    for pathway in out.get("confirmed_pathways") or []:
        pathway_id = str(pathway.get("pathway_id") or "")
        if pathway_id and pathway_uses_variable(pathway_id, answered_variable):
            if user_rules_out_pathway_from_signals(
                signal_evaluation,
                pathway_id,
                answered_variable,
            ):
                continue
        filtered_confirmed.append(pathway)

    filtered_uncertain: list[dict[str, Any]] = []
    for pathway in out.get("uncertain_pathways") or []:
        pathway_id = str(pathway.get("pathway_id") or "")
        if pathway_id and pathway_uses_variable(pathway_id, answered_variable):
            if user_rules_out_pathway_from_signals(
                signal_evaluation,
                pathway_id,
                answered_variable,
            ):
                continue
        filtered_uncertain.append(pathway)

    out["confirmed_pathways"] = filtered_confirmed
    out["uncertain_pathways"] = filtered_uncertain
    return out


def apply_scoped_follow_up(
    current: dict[str, Any],
    prior: dict[str, Any] | None,
    answered_variable: str,
    *,
    signal_evaluation: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Keep prior status for pathways that do not use the answered follow-up variable."""
    if not prior or not answered_variable:
        return current

    prior_conf, prior_unc = _pathway_maps(prior)
    curr_conf, curr_unc = _pathway_maps(current)
    all_ids = set(prior_conf) | set(prior_unc) | set(curr_conf) | set(curr_unc)

    new_confirmed: list[dict[str, Any]] = []
    new_uncertain: list[dict[str, Any]] = []

    for pathway_id in sorted(all_ids, key=_humanize_pathway):
        if pathway_uses_variable(pathway_id, answered_variable):
            if pathway_id in prior_conf and pathway_id in curr_unc:
                if user_confirms_pathway_from_signals(
                    signal_evaluation,
                    pathway_id,
                    answered_variable,
                ):
                    kept = dict(prior_conf[pathway_id])
                    new_confirmed.append(kept)
                    continue
            if pathway_id in curr_conf:
                new_confirmed.append(curr_conf[pathway_id])
            elif pathway_id in curr_unc:
                new_uncertain.append(curr_unc[pathway_id])
            continue

        if pathway_id in prior_conf:
            new_confirmed.append(prior_conf[pathway_id])
        elif pathway_id in prior_unc:
            new_uncertain.append(prior_unc[pathway_id])

    out = dict(current)
    out["confirmed_pathways"] = new_confirmed
    out["uncertain_pathways"] = new_uncertain
    return out


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

        if answered_variable and pathway_uses_variable(pathway_id, answered_variable):
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


def _interpretation_for_pathway(
    pathway_id: str,
    follow_up_updates: list[dict[str, Any]] | None,
) -> str | None:
    for item in follow_up_updates or []:
        if item.get("pathway_id") != pathway_id:
            continue
        excerpt = str(item.get("update_interpretation") or "").strip()
        if excerpt:
            return excerpt
    return None


def _signal_update_reasoning(
    pathway_id: str,
    follow_up_updates: list[dict[str, Any]] | None,
    *,
    answered_variable: str | None = None,
) -> str:
    """Plain-language summary from server-evaluated follow-up signal overlays."""
    parts: list[str] = []
    for item in follow_up_updates or []:
        if item.get("pathway_id") != pathway_id:
            continue
        if answered_variable and item.get("variable") not in {answered_variable, None}:
            continue
        sig_id = str(item.get("signal_id") or "?")
        direction = str(item.get("direction") or "confirms")
        result = item.get("result")
        if result is True:
            label = "TRUE"
        elif result is False:
            label = "FALSE"
        else:
            label = "unresolved"
        excerpt = str(item.get("update_interpretation") or "").strip()
        if excerpt:
            parts.append(f"{sig_id} ({direction}) evaluated {label}: {excerpt}")
        else:
            parts.append(f"{sig_id} ({direction}) evaluated {label} from your answer on {item.get('variable') or answered_variable}.")
    return " ".join(parts)


def _confidence_change_reasoning(
    pathway_id: str,
    *,
    prior_confidence: str | None,
    next_confidence: str | None,
    answered_variable: str | None,
    pathway: dict[str, Any],
    follow_up_updates: list[dict[str, Any]] | None,
) -> str:
    reasoning = str(pathway.get("reasoning") or "").strip()
    if reasoning:
        return reasoning
    signal_text = _signal_update_reasoning(
        pathway_id,
        follow_up_updates,
        answered_variable=answered_variable,
    )
    if signal_text:
        return signal_text
    label = _humanize_pathway(pathway_id).title()
    if prior_confidence and next_confidence and prior_confidence != next_confidence:
        return (
            f"{label} confidence moved from {prior_confidence} to {next_confidence} "
            f"after follow-up on {answered_variable}."
        )
    return ""


def _rule_out_interpretation(
    pathway_id: str,
    answered_variable: str,
    signal_evaluation: dict[str, dict[str, Any]] | None,
) -> str:
    """Plain-language explanation when a pathway is dropped after user confirms+FALSE."""
    label = _humanize_pathway(pathway_id).title()
    pathway = (signal_evaluation or {}).get(pathway_id) or {}
    summary = pathway.get("summary") or {}
    user_signals = [
        sig
        for sig in pathway.get("signals") or []
        if isinstance(sig, dict)
        and sig.get("answered_variable") == answered_variable
        and sig.get("status") == "user_provided"
    ]
    sig_parts = [
        f"{sig.get('signal_id')} evaluated FALSE from your answer"
        for sig in user_signals
        if sig.get("signal_id")
    ]
    evidence = "; ".join(sig_parts) if sig_parts else f"your answer on {answered_variable}"
    confirms = summary.get("confirms_true", 0)
    return (
        f"{label} was ruled out after this follow-up: {evidence}. "
        f"No confirming signals remain TRUE (confirms_true={confirms}), so this stress is no longer listed."
    )


def collect_pathway_interpretations(
    response: dict[str, Any],
    answered_variable: str | None,
    *,
    prior: dict[str, Any] | None = None,
    signal_evaluation: dict[str, dict[str, Any]] | None = None,
    follow_up_updates: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Extract follow-up interpretations: rule-outs, status changes, and confidence updates."""
    if not answered_variable:
        return []

    prior_conf, prior_unc = _pathway_maps(prior or {})
    curr_conf, curr_unc = _pathway_maps(response)
    all_ids = set(prior_conf) | set(prior_unc) | set(curr_conf) | set(curr_unc)
    items: list[dict[str, str]] = []

    for pathway_id in sorted(all_ids, key=_humanize_pathway):
        if not pathway_uses_variable(pathway_id, answered_variable):
            continue
        before = _status(pathway_id, prior_conf, prior_unc)
        after = _status(pathway_id, curr_conf, curr_unc)

        if before in {"uncertain", "confirmed"} and after == "absent":
            if user_rules_out_pathway_from_signals(
                signal_evaluation,
                pathway_id,
                answered_variable,
            ):
                items.append(
                    {
                        "pathway_id": pathway_id,
                        "status": "ruled_out",
                        "reasoning": _rule_out_interpretation(
                            pathway_id,
                            answered_variable,
                            signal_evaluation,
                        ),
                    }
                )
            continue

        if before == after == "confirmed":
            prev_confidence = str(prior_conf.get(pathway_id, {}).get("confidence") or "")
            next_confidence = str(curr_conf.get(pathway_id, {}).get("confidence") or "")
            if prev_confidence and next_confidence and prev_confidence != next_confidence:
                reasoning = _confidence_change_reasoning(
                    pathway_id,
                    prior_confidence=prev_confidence,
                    next_confidence=next_confidence,
                    answered_variable=answered_variable,
                    pathway=curr_conf[pathway_id],
                    follow_up_updates=follow_up_updates,
                )
                if reasoning:
                    items.append(
                        {
                            "pathway_id": pathway_id,
                            "status": "confirmed",
                            "reasoning": reasoning,
                        }
                    )
            continue

        if before == after == "uncertain":
            pathway = curr_unc.get(pathway_id)
            if not pathway:
                continue
            reasoning = str(pathway.get("reasoning") or "").strip()
            if not reasoning:
                reasoning = _signal_update_reasoning(
                    pathway_id,
                    follow_up_updates,
                    answered_variable=answered_variable,
                )
            if reasoning:
                items.append(
                    {
                        "pathway_id": pathway_id,
                        "status": "uncertain",
                        "reasoning": reasoning,
                    }
                )
            continue

        pathway = curr_conf.get(pathway_id) or curr_unc.get(pathway_id)
        if not pathway:
            continue
        reasoning = str(pathway.get("reasoning") or "").strip()
        if not reasoning:
            reasoning = _signal_update_reasoning(
                pathway_id,
                follow_up_updates,
                answered_variable=answered_variable,
            )
        if not reasoning:
            continue
        status = "confirmed" if pathway_id in curr_conf else "uncertain"
        items.append(
            {
                "pathway_id": pathway_id,
                "status": status,
                "reasoning": reasoning,
            }
        )
    return items


def apply_follow_up_revision(
    response: dict[str, Any],
    prior: dict[str, Any] | None,
    *,
    answered_variable: str | None = None,
    follow_up_signal_updates: list[dict[str, Any]] | None = None,
    signal_evaluation: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach diagnosis_revision and gate panel updates when ranking did not improve."""
    out = dict(response)
    revision = compute_diagnosis_revision(prior, out, answered_variable=answered_variable)

    enriched_changes: list[dict[str, Any]] = []
    for change in revision.get("pathway_changes") or []:
        item = dict(change)
        interpretation = _interpretation_for_pathway(
            str(item.get("pathway_id") or ""),
            follow_up_signal_updates,
        )
        if interpretation:
            item["interpretation"] = interpretation
            if interpretation not in str(item.get("reason") or ""):
                item["reason"] = f"{item.get('reason', '').rstrip('.')}. Card guidance: {interpretation}"
        elif answered_variable:
            pathway_id = str(item.get("pathway_id") or "")
            prior_conf, prior_unc = _pathway_maps(prior or {})
            curr_conf, curr_unc = _pathway_maps(out)
            pathway = curr_conf.get(pathway_id) or curr_unc.get(pathway_id) or {}
            detail = _confidence_change_reasoning(
                pathway_id,
                prior_confidence=str(prior_conf.get(pathway_id, {}).get("confidence") or ""),
                next_confidence=str(curr_conf.get(pathway_id, {}).get("confidence") or ""),
                answered_variable=answered_variable,
                pathway=pathway,
                follow_up_updates=follow_up_signal_updates,
            )
            if detail and detail not in str(item.get("reason") or ""):
                item["reason"] = f"{item.get('reason', '').rstrip('.')}. {detail}"
        enriched_changes.append(item)
    revision["pathway_changes"] = enriched_changes
    revision["pathway_interpretations"] = collect_pathway_interpretations(
        out,
        answered_variable,
        prior=prior,
        signal_evaluation=signal_evaluation,
        follow_up_updates=follow_up_signal_updates,
    )
    out["diagnosis_revision"] = revision

    if follow_up_signal_updates:
        out["follow_up_signal_updates"] = follow_up_signal_updates

    if not revision.get("improved"):
        out["panel_updates"] = []
        if not out.get("panel_update_explanation"):
            out["panel_update_explanation"] = revision.get("summary")
    elif revision.get("summary") and not out.get("panel_update_explanation"):
        out["panel_update_explanation"] = revision["summary"]

    return out
