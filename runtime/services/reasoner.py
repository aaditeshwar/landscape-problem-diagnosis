from __future__ import annotations

import json
import re
import time
from typing import Any

from config import LLM_PROVIDER
from services.assembler import authorized_follow_up_questions, find_pathway
from services.diagnosis_revision import (
    apply_follow_up_revision,
    apply_ruled_out_guard,
    apply_scoped_follow_up,
    apply_user_rule_out,
    pathways_ruled_out_from_signal_evaluation,
)
from services.diagnosis_trace import DiagnosisRun
from services.llm_client import chat_json, model_for_turn
from services.panel_updates import apply_panel_updates_from_standards
from services.signal_evaluator import evaluate_bundle_signals
from services.variable_registry import registry_excerpt_block

DERIVED_VARIABLE_NAMES = frozenset(
    {
        "mean_annual_precipitation_mm",
        "trend_annual_precipitation_mm",
        "mean_annual_et_mm",
        "trend_annual_et_mm",
        "mean_annual_runoff_mm",
        "trend_annual_runoff_mm",
        "mean_annual_delta_g_mm",
        "trend_annual_delta_g_mm",
        "mean_cropping_intensity",
        "trend_cropping_intensity",
        "mean_kharif_cropped_area_ha",
        "trend_kharif_cropped_area_ha",
        "mean_double_crop_area_ha",
        "trend_double_crop_area_ha",
        "drought_moderate_return_period",
        "drought_severe_return_period",
        "mean_swb_total_area_ha",
        "trend_swb_total_area_ha",
        "mean_swb_rabi_kharif_ratio",
        "trend_swb_rabi_kharif_ratio",
        "drought_mild_spi_score_latest",
        "drought_mild_mai_score_latest",
        "drought_mild_vci_score_latest",
        "drought_severe_moderate_spi_score_latest",
        "drought_severe_moderate_mai_score_latest",
        "drought_severe_moderate_vci_score_latest",
        "drought_severe_moderate_path_score_latest",
    }
)

DERIVED_VARIABLE_HINTS: dict[str, str] = {
    "trend_annual_precipitation_mm": "linear slope of annual precipitation (mm/year)",
    "trend_annual_et_mm": "linear slope of annual ET (mm/year)",
    "trend_annual_runoff_mm": "linear slope of annual runoff (mm/year)",
    "trend_annual_delta_g_mm": "linear slope of annual_delta_g_mm (mm/year)",
    "trend_cropping_intensity": "linear slope of cropping_intensity (ratio/year)",
    "trend_kharif_cropped_area_ha": "linear slope of kharif cropped area (ha/year)",
    "trend_double_crop_area_ha": "linear slope of double-crop area (ha/year)",
    "trend_swb_total_area_ha": "linear slope of SWB total area (ha/year)",
    "trend_swb_rabi_kharif_ratio": "linear slope of SWB rabi/kharif ratio",
    "mean_annual_delta_g_mm": "mean of annual groundwater recharge balance P−ET−Runoff",
    "drought_moderate_return_period": "average years between moderate drought kharif seasons",
    "drought_severe_return_period": "average years between severe drought kharif seasons",
    "drought_mild_spi_score_latest": "latest-year mild drought SPI trigger score (India Drought Manual)",
    "drought_mild_mai_score_latest": "latest-year mild drought MAI trigger score",
    "drought_mild_vci_score_latest": "latest-year mild drought VCI trigger score",
    "drought_severe_moderate_path_score_latest": "sum of latest-year severe/moderate drought path scores",
}


class DiagnosisLLMParseError(Exception):
    """LLM returned text that could not be parsed as diagnosis JSON."""

    def __init__(
        self,
        message: str,
        *,
        raw: str = "",
        decode_error: json.JSONDecodeError | None = None,
    ):
        super().__init__(message)
        self.raw = raw
        self.decode_error = decode_error
        self.pos = decode_error.pos if decode_error else None
        self.prompt = ""
        self.prompt_profile = ""

    def context_snippet(self, *, radius: int = 100) -> str:
        if not self.raw or self.pos is None:
            return ""
        start = max(0, self.pos - radius)
        end = min(len(self.raw), self.pos + radius)
        snippet = self.raw[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(self.raw):
            snippet = snippet + "..."
        return snippet


def parse_json_response(text: str) -> dict:
    """Parse LLM JSON output with lightweight recovery for common model mistakes."""
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    else:
        raw = _extract_json_object(raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_exc:
        repaired = _repair_json_text(raw)
        if repaired != raw:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as repair_exc:
                raise DiagnosisLLMParseError(str(repair_exc), raw=raw, decode_error=repair_exc) from repair_exc
        raise DiagnosisLLMParseError(str(first_exc), raw=raw, decode_error=first_exc) from first_exc


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return text.strip()
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:].strip()


def _repair_truncated_diagnosis_json(text: str) -> str:
    """Close diagnosis JSON when Ollama stops after the solutions key name."""
    repaired = text.rstrip()
    if not repaired.endswith('"solutions"'):
        return text
    repaired = re.sub(
        r"\}\]\},\s*\n\s*\"solutions\"$",
        '}]}],\n  "solutions"',
        repaired,
    )
    return repaired + ': [], "panel_update_explanation": null, "follow_up_question": null}'


def _repair_json_text(text: str) -> str:
    repaired = _repair_truncated_diagnosis_json(text)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    repaired = _fix_unescaped_quotes_in_strings(repaired)
    return repaired


def _fix_unescaped_quotes_in_strings(text: str) -> str:
    """Escape interior double quotes that prematurely terminate JSON string values."""
    out: list[str] = []
    in_string = False
    escape = False
    index = 0
    while index < len(text):
        char = text[index]
        if not in_string:
            out.append(char)
            if char == '"':
                in_string = True
                escape = False
            index += 1
            continue
        if escape:
            out.append(char)
            escape = False
            index += 1
            continue
        if char == "\\":
            out.append(char)
            escape = True
            index += 1
            continue
        if char == '"':
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead] in " \t\n\r":
                lookahead += 1
            if lookahead >= len(text) or text[lookahead] in ":,}]":
                out.append(char)
                in_string = False
            else:
                out.append('\\"')
            index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v).strip()]
    return [str(value)]


def _normalize_question(entry: Any) -> dict[str, str] | None:
    if isinstance(entry, dict):
        var = entry.get("variable") or entry.get("missing_variable")
        question = entry.get("question") or entry.get("question_to_user") or ""
        if var or question:
            return {"variable": str(var or ""), "question": str(question)}
        return None
    if isinstance(entry, str) and entry.strip():
        return {"variable": entry.strip(), "question": ""}
    return None


_INVALID_PATHWAY_IDS = frozenset(
    {
        "solutions",
        "panel_updates",
        "panel_update_explanation",
        "follow_up_question",
        "follow_up_variable",
        "confirmed_pathways",
        "uncertain_pathways",
        "diagnosis_revision",
        "pathway_retrieval_ranks",
        "session_id",
    }
)


def _is_valid_pathway_id(pathway_id: str, bundle: dict[str, dict] | None = None) -> bool:
    pid = str(pathway_id or "").strip()
    if not pid or pid in _INVALID_PATHWAY_IDS:
        return False
    if bundle is not None:
        return pid in bundle
    return find_pathway(pid) is not None


def _filter_pathways(
    pathways: list[dict[str, Any]],
    bundle: dict[str, dict] | None,
) -> list[dict[str, Any]]:
    return [
        pathway
        for pathway in pathways
        if _is_valid_pathway_id(str(pathway.get("pathway_id") or ""), bundle)
    ]


def _normalize_pathway(entry: Any, *, pathway_id: str | None = None, uncertain: bool = False) -> dict[str, Any] | None:
    if isinstance(entry, str):
        out: dict[str, Any] = {
            "pathway_id": entry,
            "confidence": "medium",
        }
        if uncertain:
            out["missing_variable_questions"] = []
        else:
            out["reasoning"] = ""
        return out
    if not isinstance(entry, dict):
        return None

    out = dict(entry)
    out["pathway_id"] = out.get("pathway_id") or pathway_id
    if not out.get("pathway_id"):
        return None
    out["confidence"] = out.get("confidence") or "medium"

    if uncertain:
        raw_questions = out.get("missing_variable_questions") or []
        if isinstance(raw_questions, dict):
            raw_questions = [raw_questions]
        questions = []
        for q in raw_questions if isinstance(raw_questions, list) else []:
            normalized = _normalize_question(q)
            if normalized:
                questions.append(normalized)
        out["missing_variable_questions"] = questions
        out.setdefault("reasoning", "")
    else:
        out.setdefault("reasoning", "")

    return out


def _normalize_pathway_list(value: Any, *, uncertain: bool = False) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        if value.get("pathway_id") or not any(isinstance(v, dict) for v in value.values()):
            single = _normalize_pathway(value, uncertain=uncertain)
            return [single] if single else []
        out = []
        for key, entry in value.items():
            normalized = _normalize_pathway(entry, pathway_id=str(key), uncertain=uncertain)
            if normalized:
                out.append(normalized)
        return out
    if isinstance(value, list):
        out = []
        for entry in value:
            normalized = _normalize_pathway(entry, uncertain=uncertain)
            if normalized:
                out.append(normalized)
        return out
    single = _normalize_pathway(value, uncertain=uncertain)
    return [single] if single else []


def _collect_prior_follow_up(session: dict | None) -> tuple[dict[str, Any], list[str]]:
    """Variables already supplied by the user and follow-up question texts already asked."""
    if not session:
        return {}, []
    injected = dict(session.get("injected_variables") or {})
    asked_questions: list[str] = []
    for turn in session.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        response = turn.get("llm_response_json") or {}
        fq = response.get("follow_up_question")
        if fq and str(fq).strip():
            asked_questions.append(str(fq).strip())
        for var in turn.get("missing_vars_asked") or []:
            if var:
                injected.setdefault(str(var), turn.get("user_input", ""))
    return injected, asked_questions


def _variable_for_question(question: str, authorized: list[tuple[str, str]]) -> str | None:
    for var, q in authorized:
        if q == question:
            return var
    return None


def _pathway_ids_from_response(response: dict[str, Any], key: str) -> set[str]:
    ids: set[str] = set()
    for entry in response.get(key) or []:
        if isinstance(entry, dict):
            pid = str(entry.get("pathway_id") or "").strip()
            if pid:
                ids.add(pid)
    return ids


def _enrich_pathways_from_bundle(response: dict[str, Any], bundle: dict[str, dict] | None) -> dict[str, Any]:
    if not bundle:
        return response
    out = dict(response)
    for key in ("confirmed_pathways", "uncertain_pathways"):
        enriched: list[dict[str, Any]] = []
        for pathway in out.get(key) or []:
            if not isinstance(pathway, dict):
                continue
            item = dict(pathway)
            data = bundle.get(str(item.get("pathway_id") or "")) or {}
            for field in ("production_system", "observed_stress", "card_id", "aer_tags"):
                value = data.get(field)
                if not value and field == "card_id":
                    value = (data.get("evidence_card") or {}).get("card_id")
                if not value and field == "aer_tags":
                    value = (data.get("evidence_card") or {}).get("aer_tags")
                if value:
                    item[field] = value
            context = data.get("context") or {}
            if context.get("rainfall_regime"):
                item["card_rainfall_regime"] = context.get("rainfall_regime")
            enriched.append(item)
        out[key] = enriched
    return out


def _confirmed_pathway_confidence(response: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pathway in response.get("confirmed_pathways") or []:
        if not isinstance(pathway, dict):
            continue
        pathway_id = str(pathway.get("pathway_id") or "").strip()
        if pathway_id:
            out[pathway_id] = str(pathway.get("confidence") or "medium").lower()
    return out


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _cap_confidence_level(confidence: str | None, max_level: str) -> str:
    current = str(confidence or "medium").lower()
    if current not in _CONFIDENCE_RANK:
        current = "medium"
    cap = max_level.lower()
    if cap not in _CONFIDENCE_RANK:
        return current
    return current if _CONFIDENCE_RANK[current] <= _CONFIDENCE_RANK[cap] else cap


def _pathway_evidence_note(bundle: dict[str, dict] | None, pathway_id: str) -> str:
    if not bundle:
        return ""
    data = bundle.get(pathway_id) or {}
    card = data.get("evidence_card") or {}
    return str(card.get("overall_reasoning_note") or data.get("overall_reasoning_note") or "")


def _min_confirms_required(pathway_id: str, bundle: dict[str, dict] | None) -> int:
    """Minimum confirms+TRUE count required before a pathway may stay confirmed."""
    note = _pathway_evidence_note(bundle, pathway_id).lower()
    if "no single signal is sufficient" in note:
        return 2
    if "at least three" in note or "at least 3" in note:
        return 3
    if "at least two" in note or "at least 2" in note:
        return 2
    if "plus one of" in note or "and one of" in note:
        return 2
    return 2


def apply_signal_confidence_guard(
    response: dict[str, Any],
    *,
    signal_eval: dict[str, dict[str, Any]] | None = None,
    bundle: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Cap confidence from signal counts; demote only when confirms_true is zero."""
    if not signal_eval:
        return response

    out = dict(response)
    kept_confirmed: list[dict[str, Any]] = []
    demoted: list[dict[str, Any]] = []
    uncertain = [
        dict(pathway)
        for pathway in out.get("uncertain_pathways") or []
        if isinstance(pathway, dict)
    ]
    uncertain_ids = {str(p.get("pathway_id") or "") for p in uncertain}

    for pathway in out.get("confirmed_pathways") or []:
        if not isinstance(pathway, dict):
            continue
        item = dict(pathway)
        pathway_id = str(item.get("pathway_id") or "").strip()
        if not pathway_id:
            continue
        summary = (signal_eval.get(pathway_id) or {}).get("summary") or {}
        confirms_true = int(summary.get("confirms_true") or 0)
        min_required = _min_confirms_required(pathway_id, bundle)

        if confirms_true == 0:
            item["confidence"] = "low"
            demoted.append(item)
            continue

        if confirms_true == 1:
            item["confidence"] = _cap_confidence_level(item.get("confidence"), "medium")
            kept_confirmed.append(item)
            continue

        max_level = "high" if confirms_true >= min_required else "medium"
        item["confidence"] = _cap_confidence_level(item.get("confidence"), max_level)
        kept_confirmed.append(item)

    for item in demoted:
        pathway_id = str(item.get("pathway_id") or "").strip()
        if pathway_id and pathway_id not in uncertain_ids:
            uncertain.append(item)
            uncertain_ids.add(pathway_id)

    out["confirmed_pathways"] = kept_confirmed
    out["uncertain_pathways"] = uncertain
    return out


def pick_next_follow_up(
    response: dict[str, Any],
    injected_variables: dict[str, Any] | None = None,
    bundle: dict[str, dict] | None = None,
    *,
    prior_asked_questions: list[str] | None = None,
    pathway_retrieval_ranks: dict[str, int] | None = None,
    ruled_out_pathway_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Keep or select a follow-up question only for genuinely missing variables."""
    out = dict(response)
    if not bundle:
        return out

    injected = injected_variables or {}
    asked_texts = {q.strip() for q in (prior_asked_questions or []) if q and str(q).strip()}
    uncertain_ids = _pathway_ids_from_response(out, "uncertain_pathways")
    confirmed_ids = _pathway_ids_from_response(out, "confirmed_pathways")
    authorized = authorized_follow_up_questions(
        bundle,
        injected,
        uncertain_pathway_ids=uncertain_ids,
        confirmed_pathway_ids=confirmed_ids,
        confirmed_pathway_confidence=_confirmed_pathway_confidence(out),
        ruled_out_pathway_ids=ruled_out_pathway_ids,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
    )
    authorized_questions = {question for _, question in authorized}

    def _set_follow_up(question: str | None, variable: str | None = None) -> dict[str, Any]:
        out["follow_up_question"] = question
        out["follow_up_variable"] = variable
        return out

    current = out.get("follow_up_question")
    if current:
        current = str(current).strip()
        var = _variable_for_question(current, authorized)
        if (
            current in authorized_questions
            and current not in asked_texts
            and not (var and var in injected)
        ):
            return _set_follow_up(current, var)

    for var, question in authorized:
        if question in asked_texts or var in injected:
            continue
        return _set_follow_up(question, var)

    return _set_follow_up(None, None)


def _bundle_authorized_questions_for_pathway(
    pathway_id: str,
    bundle: dict[str, dict],
    *,
    injected: dict[str, Any],
    asked_texts: set[str],
) -> list[dict[str, str]]:
    """Card-backed follow-up questions still eligible for this pathway."""
    data = bundle.get(pathway_id) or {}
    present = set(injected) | set((data.get("present_variables") or {}).keys())
    missing = set(data.get("missing_variables") or [])
    out: list[dict[str, str]] = []
    for q in data.get("missing_variable_questions") or []:
        if not isinstance(q, dict):
            continue
        var = str(q.get("missing_variable") or q.get("variable") or "").strip()
        question = str(q.get("question_to_user") or q.get("question") or "").strip()
        if not var or not question or var not in missing or var in present:
            continue
        if question in asked_texts:
            continue
        out.append({"variable": var, "question": question})
    return out


def sanitize_uncertain_pathways(
    response: dict[str, Any],
    bundle: dict[str, dict] | None = None,
    injected_variables: dict[str, Any] | None = None,
    *,
    prior_asked_questions: list[str] | None = None,
) -> dict[str, Any]:
    """Drop invented follow-up questions; keep only card-authorized bundle questions."""
    if not bundle:
        return response

    out = dict(response)
    injected = injected_variables or {}
    asked_texts = {q.strip() for q in (prior_asked_questions or []) if q and str(q).strip()}

    cleaned_pathways = []
    for pathway in out.get("uncertain_pathways") or []:
        if not isinstance(pathway, dict):
            continue
        item = dict(pathway)
        pathway_id = str(item.get("pathway_id") or "").strip()
        item["missing_variable_questions"] = _bundle_authorized_questions_for_pathway(
            pathway_id,
            bundle,
            injected=injected,
            asked_texts=asked_texts,
        )
        cleaned_pathways.append(item)
    out["uncertain_pathways"] = cleaned_pathways
    return out


def normalize_diagnosis_response(
    parsed: dict[str, Any],
    injected_variables: dict[str, Any] | None = None,
    bundle: dict[str, dict] | None = None,
    *,
    prior_asked_questions: list[str] | None = None,
    follow_up_context: str | None = None,
    pathway_retrieval_ranks: dict[str, int] | None = None,
    ruled_out_pathway_ids: set[str] | None = None,
) -> dict[str, Any]:
    out = dict(parsed)
    out["confirmed_pathways"] = _filter_pathways(
        _normalize_pathway_list(out.get("confirmed_pathways"), uncertain=False),
        bundle,
    )
    out["uncertain_pathways"] = _filter_pathways(
        _normalize_pathway_list(out.get("uncertain_pathways"), uncertain=True),
        bundle,
    )
    out["solutions"] = _as_str_list(out.get("solutions"))
    follow_up = out.get("follow_up_question")
    out["follow_up_question"] = _null_if_placeholder(follow_up)
    panel_expl = out.get("panel_update_explanation")
    out["panel_update_explanation"] = _null_if_placeholder(panel_expl)
    out = sanitize_uncertain_pathways(
        out,
        bundle=bundle,
        injected_variables=injected_variables,
        prior_asked_questions=prior_asked_questions,
    )
    out = _enrich_pathways_from_bundle(out, bundle)
    out = pick_next_follow_up(
        out,
        injected_variables,
        bundle=bundle,
        prior_asked_questions=prior_asked_questions,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
        ruled_out_pathway_ids=ruled_out_pathway_ids,
    )
    return apply_panel_updates_from_standards(out, follow_up_context=follow_up_context)


def _null_if_placeholder(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "null", "none", "..."}:
        return None
    return text


def _split_present_variables(present: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw: dict[str, Any] = {}
    derived: dict[str, Any] = {}
    for name, value in (present or {}).items():
        if name in DERIVED_VARIABLE_NAMES:
            derived[name] = value
        else:
            raw[name] = value
    return raw, derived


def _format_present_variables_block(present: dict[str, Any]) -> list[str]:
    raw, derived = _split_present_variables(present)
    lines: list[str] = []
    if raw:
        lines.append(f"Present variables (raw): {json.dumps(raw, default=str)}")
    if derived:
        annotated = {
            name: {
                "value": value,
                "note": DERIVED_VARIABLE_HINTS.get(name, "system-computed derived statistic"),
            }
            for name, value in derived.items()
        }
        lines.append(f"Derived/computed: {json.dumps(annotated, default=str)}")
    if not lines:
        lines.append("Present variables (raw): {}")
    return lines


def _signal_expression(signal: dict[str, Any]) -> str:
    condition = signal.get("condition") or {}
    return str(condition.get("expression") or condition.get("qualitative_description") or "").strip()


def _signal_explanation_one_line(signal: dict[str, Any], *, max_len: int = 160) -> str:
    text = str(signal.get("explanation") or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _format_signal_line(signal: dict[str, Any]) -> str:
    sig_id = signal.get("signal_id", "?")
    direction = signal.get("direction", "?")
    expression = _signal_expression(signal)
    return f"  {sig_id} | {direction} | {expression}"


def _format_signals_compact(signals: list[dict[str, Any]]) -> list[str]:
    lines = ["Signals:"]
    for signal in signals:
        if isinstance(signal, dict):
            lines.append(_format_signal_line(signal))
    return lines


def _format_signals_ollama(signals: list[dict[str, Any]]) -> list[str]:
    lines = ["Diagnostic signals:"]
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        sig_id = signal.get("signal_id", "?")
        direction = signal.get("direction", "?")
        expression = _signal_expression(signal)
        explanation = _signal_explanation_one_line(signal)
        lines.append(f"  {sig_id} | {direction} | {expression} | {explanation}")
    return lines


def _format_confounders_ollama(confounders: list[dict[str, Any]]) -> str:
    return f"Confounders: {json.dumps(confounders, default=str)[:1500]}"


def _format_confounders_claude(confounders: list[dict[str, Any]]) -> list[str]:
    lines = ["Confounders:"]
    for item in confounders:
        if not isinstance(item, dict):
            continue
        label = str(item.get("confounder") or "").strip()
        distinguish = str(item.get("how_to_distinguish") or "").strip()
        distinguish = re.sub(r"\s+", " ", distinguish)
        if len(distinguish) > 140:
            distinguish = distinguish[:139] + "…"
        lines.append(f"  - {label} | {distinguish}")
    return lines


def _format_solutions_available(bundle: dict[str, dict]) -> str:
    lines = ["[SOLUTIONS AVAILABLE]"]
    for pathway_id, data in bundle.items():
        solutions = data.get("solutions") or []
        if solutions:
            lines.append(f"{pathway_id}: {json.dumps(solutions, ensure_ascii=False)}")
    if len(lines) == 1:
        lines.append("(none)")
    return "\n".join(lines)


def _format_prior_user_blocks(
    injected_variables: dict[str, Any] | None,
    prior_asked_questions: list[str] | None,
) -> str:
    question_lines = ["[QUESTIONS ALREADY ASKED — do not repeat the same or equivalent question]"]
    if prior_asked_questions:
        question_lines.extend(f"- {q}" for q in prior_asked_questions)
    else:
        question_lines.append("(none)")

    data_lines = ["[DATA ALREADY PROVIDED BY USER — do not ask again]"]
    if injected_variables:
        data_lines.append(json.dumps(injected_variables, default=str))
    else:
        data_lines.append("(none)")

    return "\n".join(question_lines) + "\n\n" + "\n".join(data_lines) + "\n"


def _format_bundle(bundle: dict[str, dict], profile: str) -> str:
    parts: list[str] = []
    for pathway_id, data in bundle.items():
        parts.append(f"Pathway: {pathway_id}")
        parts.append(f"Description: {data.get('description', '')}")
        parts.extend(_format_present_variables_block(data.get("present_variables") or {}))
        missing = data.get("missing_variables") or []
        if missing:
            parts.append(f"Missing variables: {', '.join(missing)}")
        parts.extend(_format_follow_up_policy_block(data))
        card = data.get("evidence_card") or {}
        card_aer = (card.get("aer_tags") if isinstance(card, dict) else None) or data.get("aer_tags") or []
        if card_aer:
            parts.append(f"Card AER context: {', '.join(card_aer)}")
        parts.append(f"Evidence note: {card.get('overall_reasoning_note', '')}")
        signals = card.get("diagnostic_signals") or []
        confounders = card.get("confounders") or []
        if profile == "claude":
            parts.extend(_format_signals_compact(signals))
            parts.extend(_format_confounders_claude(confounders))
        else:
            parts.extend(_format_signals_ollama(signals))
            parts.append(_format_confounders_ollama(confounders))
        parts.append("")
    return "\n".join(parts)


def _format_follow_up_policy_block(data: dict[str, Any]) -> list[str]:
    """Show card-authorized follow-up questions vs signal-only missing vars."""
    lines: list[str] = []
    missing = set(data.get("missing_variables") or [])
    authorized: list[str] = []
    for q in data.get("missing_variable_questions") or []:
        if not isinstance(q, dict):
            continue
        var = str(q.get("missing_variable") or q.get("variable") or "").strip()
        question = str(q.get("question_to_user") or q.get("question") or "").strip()
        if var and question and var in missing:
            authorized.append(f"  - {var}: {question}")
    if authorized:
        lines.append(
            "Authorized follow-up questions (ONLY these may be used for follow_up_question; copy question text exactly):"
        )
        lines.extend(authorized)
    signal_only = data.get("missing_signal_only_variables") or []
    if signal_only:
        lines.append(
            "Missing signal/derived variables (do NOT ask the user; use landscape data and signal evaluation): "
            + ", ".join(signal_only)
        )
    return lines


def _format_location(location: dict[str, Any]) -> str:
    village_line = ", ".join(location.get("village_names") or []) or "none listed"
    aer_code = location.get("nbss_lup_aer_code")
    aer_name = location.get("nbss_lup_aer_name")
    aer_line = ""
    if aer_code:
        aer_line = f"NBSS-LUP AER: {aer_code}"
        if aer_name:
            aer_line += f" ({aer_name})"
        aer_line += "\n"
    return f"""MWS UID: {location.get('uid')} | Location: {location.get('tehsil_label') or location.get('tehsil')} | District: {location.get('district')} | State: {location.get('state')}
{aer_line}Intersecting villages: {village_line}
Aquifer: {location.get('aquifer_class')} ({location.get('aquifer_raw')}) | Terrain cluster: {location.get('terrain_cluster')} ({location.get('terrain_description')})
Area: {location.get('area_ha')} ha"""


def _format_signal_result_line(signal: dict[str, Any]) -> str:
    sig_id = signal.get("signal_id", "?")
    direction = signal.get("direction", "?")
    status = signal.get("status", "?")
    if status == "user_provided_unresolved":
        answer = str(signal.get("user_answer") or "").strip()
        if answer:
            answer = re.sub(r"\s+", " ", answer)
        rule = str(signal.get("update_rule") or signal.get("qualitative_hint") or "").strip()
        rule = re.sub(r"\s+", " ", rule)
        if len(rule) > 200:
            rule = rule[:199] + "…"
        line = f"  {sig_id} | {direction} | UNRESOLVED | user_provided_unresolved"
        if answer:
            line += f' | answer="{answer}"'
        note = str(signal.get("inference_note") or "").strip()
        if note:
            line += f" | {note}"
        if rule:
            line += f" | update_rule: {rule}"
        return line
    if status in {"ok", "user_provided"}:
        result = signal.get("result")
        if result is True:
            label = "TRUE"
        elif result is False:
            label = "FALSE"
        else:
            label = "INTERPRET"
        source = "user_provided" if status == "user_provided" else "ok"
        line = f"  {sig_id} | {direction} | {label} | {source}"
        if status == "user_provided":
            answer = str(signal.get("user_answer") or "").strip()
            if answer:
                answer = re.sub(r"\s+", " ", answer)
                if len(answer) > 80:
                    answer = answer[:79] + "…"
                line += f' | answer="{answer}"'
            excerpt = str(signal.get("update_interpretation") or "").strip()
            if excerpt:
                excerpt = re.sub(r"\s+", " ", excerpt)
                if len(excerpt) > 160:
                    excerpt = excerpt[:159] + "…"
                line += f" | card: {excerpt}"
        return line
    hint = signal.get("qualitative_hint") or ""
    if hint:
        hint = re.sub(r"\s+", " ", hint)
        if len(hint) > 120:
            hint = hint[:119] + "…"
        return f"  {sig_id} | {direction} | NEEDS_LLM ({status}) — {hint}"
    return f"  {sig_id} | {direction} | NEEDS_LLM ({status})"


def _format_signal_evaluation_results(eval_results: dict[str, dict[str, Any]]) -> str:
    if not eval_results:
        return "[SIGNAL EVALUATION RESULTS — server-computed; none]\n"

    lines = [
        "[SIGNAL EVALUATION RESULTS — server-computed; authoritative for status=ok and evaluated user_provided]",
        "Use TRUE/FALSE as given for ok and user_provided rows.",
        "For user_provided_unresolved rows: server could not map the answer automatically — infer TRUE/FALSE using the raw answer and update_rule text; do not ignore the user response.",
        "For remaining NEEDS_LLM signals only, use qualitative_hint / signal explanation.",
        "NEEDS_LLM means the variable is missing from landscape data — treat as unknown, not as a user or farmer report.",
        "Map direction: confirms+TRUE supports pathway; rules_out+TRUE rules out; amplifies+TRUE strengthens co-occurring signals.",
    ]
    for pathway_id, data in eval_results.items():
        summary = data.get("summary") or {}
        lines.append(f"Pathway: {pathway_id}")
        for signal in data.get("signals") or []:
            if isinstance(signal, dict):
                lines.append(_format_signal_result_line(signal))
        lines.append(
            "Summary: "
            f"confirms_true={summary.get('confirms_true', 0)}, "
            f"rules_out_true={summary.get('rules_out_true', 0)}, "
            f"amplifies_true={summary.get('amplifies_true', 0)}, "
            f"needs_llm={summary.get('needs_llm', 0)}"
        )
        note = data.get("evidence_note")
        if note:
            lines.append(f"Evidence note: {note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _registry_excerpt_if_needed(eval_results: dict[str, dict[str, Any]]) -> str:
    needs = any((data.get("summary") or {}).get("needs_llm", 0) > 0 for data in eval_results.values())
    if not needs:
        return ""
    return f"\n[VARIABLE REGISTRY — for NEEDS_LLM signals only]\n{registry_excerpt_block()}\n"


def _reasoning_wording_rules() -> str:
    return """REASONING WORDING (apply to every reasoning string in confirmed_pathways, uncertain_pathways, and follow-up revisions):
- Do NOT write "farmer reports", "users report", "community reports", or similar unless that fact appears in [DATA ALREADY PROVIDED BY USER] or was explicitly stated in the problem description.
- Missing variables mean data is NOT yet available — say "data not yet available on …", "follow-up needed on …", or "we do not yet know whether …"; never imply the farmer already reported something.
- When confirming-direction signals are not supported by the available landscape data, state that the pathway is not supported by current landscape data; if it remains uncertain, cite which variables are still missing — not reported symptoms."""


def _ollama_revision_rules() -> str:
    return """
10. FOLLOW-UP REVISION: only change status for pathways whose missing_variables included the answered user variable, or whose server signal results changed because of that answer. Keep all other pathways at their prior confirmed/uncertain status.
11. Treat user_provided signals in [SIGNAL EVALUATION RESULTS] as authoritative — especially confirms+TRUE from a follow-up answer. Do not demote a previously confirmed pathway to uncertain when user_provided confirms+TRUE applies to that pathway; maintain or strengthen confidence instead. Cite the card guidance line when explaining the update.
12. On follow-up revision, add a reasoning string to every confirmed_pathways and uncertain_pathways entry whose missing_variables included the answered variable. Explain how the user's answer strengthens, weakens, or leaves that pathway unchanged. If user_provided confirms+FALSE for a primary signal and no other confirms are TRUE, remove that pathway from uncertain_pathways rather than keeping it listed.
"""


def _claude_revision_rules() -> str:
    return """
10. FOLLOW-UP REVISION: only change status for pathways whose missing_variables included the answered user variable, or whose interpretation of that answer materially changes pathway support. Keep all other pathways at their prior confirmed/uncertain status.
11. Treat [USER FOLLOW-UP ANSWER] and [DATA ALREADY PROVIDED BY USER] as authoritative new evidence. Do not demote a previously confirmed pathway to uncertain when the new user evidence supports it; maintain or strengthen confidence instead. Cite the card guidance line when explaining the update.
12. On follow-up revision, add a reasoning string to every confirmed_pathways and uncertain_pathways entry whose missing_variables included the answered variable. Explain how the user's answer strengthens, weakens, or leaves that pathway unchanged.
"""


def _ollama_signal_interpretation_task(uid: str | None, *, is_revision: bool = False) -> str:
    revision_rules = _ollama_revision_rules() if is_revision else ""
    return f"""[TASK]
0. Answer [USER PROBLEM] first in your own reasoning: what is the user asking, and what would a useful direct response look like for this MWS?
1. Use [SIGNAL EVALUATION RESULTS] for status=ok and evaluated user_provided — do NOT contradict TRUE/FALSE. For user_provided_unresolved, you MUST interpret the raw answer using update_rule and set pathway status accordingly.
2. Apply each pathway's evidence note using the summary counts: ≥2 confirming TRUE → high confidence in confirmed_pathways; exactly 1 confirming TRUE → medium confidence in confirmed_pathways (do NOT demote single-confirm pathways to uncertain_pathways unless confirms_true=0); confirms_true=0 with missing data still needed → uncertain_pathways; confirms_true=0 with confirms-direction signals FALSE → do not confirm.
3. For NEEDS_LLM signals only: use qualitative_hint and signal explanations; do not invent numeric values.
{_reasoning_wording_rules()}
4. Put confirmed pathways in confirmed_pathways with confidence high/medium/low. Each reasoning string must cite signal IDs with TRUE/FALSE outcomes from [SIGNAL EVALUATION RESULTS] AND include an explicit "For this question:" clause linking that pathway to [USER PROBLEM].
5. In each confirmed_pathways and uncertain_pathways reasoning string, mention MWS UID {uid}, relevant intersecting village names, and how this pathway bears on the user's question — not only landscape stress in the abstract.
6. CRITICAL — do not re-ask for data already in the prompt. Before writing follow_up_question or uncertain_pathways, check every variable against present_variables, derived/computed values, and [DATA ALREADY PROVIDED BY USER]. Put a pathway in uncertain_pathways only when genuinely required variables remain in missing_variables; uncertain reasoning must also state what remains unknown for answering [USER PROBLEM].
7. List solutions from the framework for confirmed pathways only; prefer solutions that directly help answer [USER PROBLEM].
8. Set panel_update_explanation to 2–4 sentences: (a) a direct answer to [USER PROBLEM], (b) name each confirmed pathway_id and the key evidence behind it, (c) why the highlighted charts help verify those pathways. Do not include a panel_updates field.
9. Set follow_up_question ONLY from the pathway's "Authorized follow-up questions" list in the bundle above — copy the question text exactly and use the listed variable. Do NOT ask about variables listed under "Missing signal/derived variables". Never repeat a question from [QUESTIONS ALREADY ASKED].{revision_rules}
"""


def _user_query_directive() -> str:
    return """
[ANSWER THE USER'S QUESTION]
Treat [USER PROBLEM] as the primary deliverable. Pathway evaluation supports a direct, practical answer — do not stop at listing diagnoses.
- Read [USER PROBLEM] carefully and identify what the user is trying to decide, compare, explain, or prioritise. Keep that question in view in every reasoning string.
- Every confirmed_pathways and uncertain_pathways reasoning string MUST have two linked parts:
  (1) Evidence — cite signal IDs and TRUE/FALSE outcomes (from [SIGNAL EVALUATION RESULTS] when provided, or from your own assessment when not) with the key variable values.
  (2) For this question — one or two sentences stating what this pathway means for [USER PROBLEM] specifically (e.g. whether rainfall vs recharge drives the problem, whether past investment worked, what to prioritise).
  Do not write pathway reasoning that only audits signals without tying them to the user's question.
- panel_update_explanation MUST synthesise the answer from your confirmed pathways — name each confirmed pathway_id and explain how its evidence jointly answers [USER PROBLEM]. Do not give a generic landscape summary that ignores which pathways you confirmed.
- After the answer, briefly note which highlighted charts help verify the confirmed pathways behind that answer.
- Select solutions that address both the confirmed pathways and what the user is trying to accomplish (e.g. intervention choice, prioritisation, explanation).
- If evidence is insufficient to fully answer the question, say so explicitly in panel_update_explanation, name which uncertain pathways block the answer, and use follow_up_question for the single highest-value missing fact.
"""


def _reviewer_user_query_directive() -> str:
    return """
[ANSWER THE USER'S QUESTION — REVIEWER]
Treat [USER PROBLEM] as the primary deliverable. You are reviewing server-computed pathways, not re-classifying them.
- Read [USER PROBLEM] first: what is the user trying to decide, compare, explain, or prioritise?
- panel_update_explanation MUST open with a direct, practical answer to [USER PROBLEM] in plain language.
  Then explain how the server-confirmed pathways (from [SERVER DIAGNOSIS].confirmed_pathways) jointly support that answer.
  Name each confirmed pathway_id and cite key server TRUE/FALSE signals. Do not give a generic landscape summary that ignores the user's question.
- Reference [SERVER DIAGNOSIS].panel_updates — briefly say why those highlighted charts help verify the answer (the server chose them; explain their relevance to [USER PROBLEM]).
- For each server_review entry with a pathway_comment, include an explicit "For this question:" clause linking that pathway to [USER PROBLEM].
- If evidence is insufficient to fully answer [USER PROBLEM], say so in panel_update_explanation and note which uncertain pathways or follow-up gaps block a complete answer.
- Do not contradict server TRUE/FALSE for status=ok signals. Use partial/disagree only for interpretation or emphasis, not to invent new pathway lists.
"""


def _claude_interpretation_task(uid: str | None, *, is_revision: bool = False) -> str:
    revision_rules = _claude_revision_rules() if is_revision else ""
    return f"""[TASK]
0. Answer [USER PROBLEM] first in your own reasoning: what is the user asking, and what would a useful direct response look like for this MWS?
1. Evaluate each pathway's diagnostic signals yourself using present variable values, signal expressions, qualitative descriptions, and your domain knowledge of Indian watershed hydrology, aquifers, cropping systems, and rural livelihoods. Do NOT assume server-side TRUE/FALSE results — you must reason them out.
2. Apply each pathway's evidence note from your signal assessment: ≥2 confirming signals supported → high confidence in confirmed_pathways; exactly 1 confirming signal supported → medium confidence in confirmed_pathways; insufficient support with missing data still needed → uncertain_pathways; confirming signals clearly contradicted by available data → do not confirm.
3. When a signal expression references variables in missing_variables, treat the signal as unevaluated and rely on qualitative_description only; do not invent numeric values.
{_reasoning_wording_rules()}
4. Put confirmed pathways in confirmed_pathways with confidence high/medium/low. Each reasoning string must cite signal IDs with your TRUE/FALSE assessment AND include an explicit "For this question:" clause linking that pathway to [USER PROBLEM].
5. In each confirmed_pathways and uncertain_pathways reasoning string, mention MWS UID {uid}, relevant intersecting village names, and how this pathway bears on the user's question — not only landscape stress in the abstract.
6. CRITICAL — do not re-ask for data already in the prompt. Before writing follow_up_question or uncertain_pathways, check every variable against present_variables, derived/computed values, and [DATA ALREADY PROVIDED BY USER]. Put a pathway in uncertain_pathways only when genuinely required variables remain in missing_variables; uncertain reasoning must also state what remains unknown for answering [USER PROBLEM].
7. List solutions from the framework for confirmed pathways only; prefer solutions that directly help answer [USER PROBLEM].
8. Set panel_update_explanation to 2–4 sentences: (a) a direct answer to [USER PROBLEM], (b) name each confirmed pathway_id and the key evidence behind it, (c) why the highlighted charts help verify those pathways. Do not include a panel_updates field.
9. Set follow_up_question ONLY from the pathway's "Authorized follow-up questions" list in the bundle above — copy the question text exactly and use the listed variable. Do NOT ask about variables listed under "Missing signal/derived variables". Never repeat a question from [QUESTIONS ALREADY ASKED].{revision_rules}
"""


def _signal_interpretation_task(uid: str | None, profile: str, *, is_revision: bool = False) -> str:
    if profile == "claude":
        return _claude_interpretation_task(uid, is_revision=is_revision)
    return _ollama_signal_interpretation_task(uid, is_revision=is_revision)


def _task_section(uid: str | None, profile: str, *, is_revision: bool = False) -> str:
    shared = _signal_interpretation_task(uid, profile, is_revision=is_revision) + """
Return JSON with exactly these keys:
{
  "confirmed_pathways": [{"pathway_id": "...", "confidence": "high|medium|low", "reasoning": "..."}],
  "uncertain_pathways": [{"pathway_id": "...", "confidence": "high|medium|low", "reasoning": "...", "missing_variable_questions": [{"variable": "...", "question": "..."}]}],
  "solutions": ["..."],
  "panel_update_explanation": null,
  "follow_up_question": null
}"""
    if profile == "ollama":
        return (
            shared
            + """
Output valid JSON only. No prose outside JSON.

IMPORTANT: Output ONLY the JSON object. No preamble, no explanation, no markdown fences.
The first character of your response must be '{' and the last must be '}'."""
        )
    return shared + "\nOutput valid JSON only. No prose outside JSON."


def _reviewer_intro_line() -> str:
    return (
        "You are reviewing a server-computed watershed diagnosis for Indian micro-watersheds. "
        "The server owns confirmed_pathways, uncertain_pathways, follow-up selection, and the base "
        "solutions list. Your job is to comment on the server evaluation, answer [USER PROBLEM], "
        "and optionally suggest solution prioritisation — not to re-classify pathways."
    )


def _format_server_diagnosis_for_reviewer(server_response: dict[str, Any]) -> str:
    payload = {
        "confirmed_pathways": server_response.get("confirmed_pathways") or [],
        "uncertain_pathways": server_response.get("uncertain_pathways") or [],
        "solutions": server_response.get("solutions") or [],
        "panel_updates": server_response.get("panel_updates") or [],
        "panel_update_explanation": server_response.get("panel_update_explanation"),
        "follow_up_question": server_response.get("follow_up_question"),
        "follow_up_variable": server_response.get("follow_up_variable"),
        "diagnosis_revision": server_response.get("diagnosis_revision"),
    }
    return json.dumps(payload, default=str, indent=2)


def _reviewer_task_section(*, is_revision: bool = False) -> str:
    change_task = ""
    if is_revision:
        change_task = """
6. Set change_review to a short object summarising whether you agree with the server diagnosis_revision
   (pathway moves and MCQ implication). Example:
   {"summary": "...", "agrees_with_revision": true}
"""
    else:
        change_task = """
6. Set change_review to null on the initial turn.
"""
    return f"""[REVIEWER TASK]
1. Read [SERVER DIAGNOSIS] and [SIGNAL EVALUATION RESULTS]. Do NOT output confirmed_pathways or uncertain_pathways.
2. For each pathway in confirmed_pathways or uncertain_pathways, add a server_review entry with:
   pathway_id, agreement (agree|partial|disagree), optional signal_notes (signal_id, server_result, comment),
   and pathway_comment linking the pathway to [USER PROBLEM] when relevant.
3. Set panel_update_explanation to 2–4 sentences: (a) direct answer to [USER PROBLEM] first,
   (b) how server-confirmed pathways address it with pathway_id names and key signals,
   (c) why [SERVER DIAGNOSIS].panel_updates charts help verify that answer,
   (d) note any partial disagreement in server_review without contradicting server TRUE/FALSE for status=ok signals.
4. Optionally set solutions_review with notes and priority_order — priority_order must be a reordering
   of items from [SERVER DIAGNOSIS].solutions only (subset allowed).
5. Set follow_up_question to null — the server selects follow-up questions.
{change_task}
{_reviewer_user_query_directive()}
Return JSON with exactly these keys:
{{
  "server_review": [
    {{
      "pathway_id": "...",
      "agreement": "agree|partial|disagree",
      "signal_notes": [{{"signal_id": "...", "server_result": true, "comment": "..."}}],
      "pathway_comment": "..."
    }}
  ],
  "change_review": null,
  "panel_update_explanation": "...",
  "solutions_review": {{"notes": "...", "priority_order": ["..."]}},
  "follow_up_question": null
}}
Output valid JSON only. No prose outside JSON.
IMPORTANT: Output ONLY the JSON object. No markdown fences."""


def _build_reviewer_prompt(
    *,
    location: dict,
    problem_description: str,
    bundle: dict[str, dict],
    server_response: dict[str, Any],
    signal_eval: dict[str, dict[str, Any]],
    follow_up_context: str | None = None,
    injected_variables: dict[str, Any] | None = None,
    prior_asked_questions: list[str] | None = None,
    is_revision: bool = False,
) -> str:
    follow_block = ""
    if follow_up_context:
        follow_block = f"\n[USER FOLLOW-UP ANSWER]\n{follow_up_context}\n"

    revision_block = ""
    if is_revision and server_response.get("diagnosis_revision"):
        revision_block = (
            "\n[SERVER REVISION — after follow-up answer]\n"
            f"{json.dumps(server_response.get('diagnosis_revision'), default=str, indent=2)}\n"
        )

    signal_results_block = _format_signal_evaluation_results(signal_eval)
    registry_block = _registry_excerpt_if_needed(signal_eval)

    return f"""{_reviewer_intro_line()}

[LOCATION CONTEXT]
{_format_location(location)}

[USER PROBLEM]
{problem_description}
{follow_block}{revision_block}
[SERVER DIAGNOSIS — canonical; do not replace pathway lists]
{_format_server_diagnosis_for_reviewer(server_response)}

[MWS VARIABLE VALUES AND CANDIDATE PATHWAYS]
{_format_bundle(bundle, "ollama")}

{signal_results_block}{registry_block}
{_format_solutions_available(bundle)}

{_format_prior_user_blocks(injected_variables, prior_asked_questions)}
{_reviewer_task_section(is_revision=is_revision)}
"""


def _normalize_reviewer_response(parsed: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    reviews = parsed.get("server_review") or []
    normalized_reviews: list[dict[str, Any]] = []
    if isinstance(reviews, list):
        for item in reviews:
            if not isinstance(item, dict):
                continue
            pathway_id = str(item.get("pathway_id") or "").strip()
            if not pathway_id:
                continue
            agreement = str(item.get("agreement") or "partial").lower()
            if agreement not in {"agree", "partial", "disagree"}:
                agreement = "partial"
            entry: dict[str, Any] = {
                "pathway_id": pathway_id,
                "agreement": agreement,
            }
            if item.get("pathway_comment"):
                entry["pathway_comment"] = str(item.get("pathway_comment")).strip()
            notes = []
            for note in item.get("signal_notes") or []:
                if isinstance(note, dict) and note.get("signal_id"):
                    notes.append(
                        {
                            "signal_id": str(note.get("signal_id")),
                            "server_result": note.get("server_result"),
                            "comment": str(note.get("comment") or "").strip(),
                        }
                    )
            if notes:
                entry["signal_notes"] = notes
            normalized_reviews.append(entry)
    out["server_review"] = normalized_reviews

    change = parsed.get("change_review")
    out["change_review"] = change if isinstance(change, dict) else None

    panel = parsed.get("panel_update_explanation")
    out["panel_update_explanation"] = _null_if_placeholder(panel)

    sol_review = parsed.get("solutions_review")
    if isinstance(sol_review, dict):
        out["solutions_review"] = {
            "notes": str(sol_review.get("notes") or "").strip(),
            "priority_order": _as_str_list(sol_review.get("priority_order")),
        }
    else:
        out["solutions_review"] = None
    return out


def _merge_reviewer_into_response(
    server_response: dict[str, Any],
    reviewer: dict[str, Any],
) -> dict[str, Any]:
    out = dict(server_response)
    out["reviewer_commentary"] = reviewer.get("server_review") or []

    panel = reviewer.get("panel_update_explanation")
    if panel:
        out["panel_update_explanation"] = panel

    change = reviewer.get("change_review")
    if change:
        out["change_review"] = change

    sol_review = reviewer.get("solutions_review") or {}
    notes = str(sol_review.get("notes") or "").strip()
    if notes:
        out["solutions_review_notes"] = notes
    priority = sol_review.get("priority_order") or []
    base = list(out.get("solutions") or [])
    if priority and base:
        seen = set()
        ordered: list[str] = []
        for item in priority:
            text = str(item or "").strip()
            if text and text in base and text not in seen:
                ordered.append(text)
                seen.add(text)
        for item in base:
            if item not in seen:
                ordered.append(item)
        out["solutions"] = ordered
    return out


def _prompt_profile() -> str:
    return "claude" if LLM_PROVIDER == "anthropic" else "ollama"


def _intro_line(profile: str) -> str:
    if profile == "claude":
        return (
            "You are an expert agro-ecological diagnostician for Indian micro-watersheds. "
            "Use the variable values, evidence notes, and your domain knowledge of NBSS-LUP "
            "agro-ecological regions, aquifer behaviour, and rural livelihood systems. "
            "Your job is to answer the user's specific question in [USER PROBLEM] — not merely "
            "to classify pathways in isolation."
        )
    return (
        "You are an agro-ecological diagnosis assistant for Indian micro-watersheds. "
        "Interpret the server-computed signal results and evidence notes, then answer the user's "
        "specific question in [USER PROBLEM] — not merely classify pathways in isolation."
    )


def _format_prior_diagnosis(prior: dict[str, Any] | None) -> str:
    if not prior:
        return ""
    return json.dumps(
        {
            "confirmed_pathways": prior.get("confirmed_pathways", []),
            "uncertain_pathways": prior.get("uncertain_pathways", []),
            "solutions": prior.get("solutions", []),
        },
        default=str,
        indent=2,
    )


def _build_prompt(
    *,
    location: dict,
    problem_description: str,
    bundle: dict[str, dict],
    follow_up_context: str | None = None,
    injected_variables: dict[str, Any] | None = None,
    prior_asked_questions: list[str] | None = None,
    prior_diagnosis: dict[str, Any] | None = None,
    is_revision: bool = False,
    profile: str | None = None,
    signal_eval: dict[str, dict[str, Any]] | None = None,
) -> str:
    profile = profile or _prompt_profile()
    follow_block = ""
    if follow_up_context:
        follow_block = f"\n[USER FOLLOW-UP ANSWER]\n{follow_up_context}\n"

    prior_diagnosis_block = ""
    if is_revision and prior_diagnosis:
        prior_diagnosis_block = (
            "\n[PRIOR DIAGNOSIS — revise this using new user evidence]\n"
            f"{_format_prior_diagnosis(prior_diagnosis)}\n"
        )

    revision_task = ""
    if is_revision:
        if profile == "claude":
            revision_task = """
[REVISION TASK — follow-up turn]
You are revising the prior diagnosis after a user follow-up answer.
- Re-run your own signal interpretation using updated present variables, injected user evidence, and domain knowledge.
- Only change pathway status for pathways that use the answered variable in missing_variables/diagnostic scope, or where your interpretation changed because of that answer.
- Preserve prior status for all other candidate pathways unless rules_out signals are clearly contradicted by available data.
- Update reasoning on changed pathways to cite signal IDs and the new user evidence.
- Update solutions to match the revised confirmed set.
- Do NOT repeat a follow-up question already listed under QUESTIONS ALREADY ASKED.
"""
        else:
            revision_task = """
[REVISION TASK — follow-up turn]
You are revising the prior diagnosis after a user follow-up answer.
- Re-run interpretation using updated [SIGNAL EVALUATION RESULTS] and injected user evidence.
- Only change pathway status for pathways that use the answered variable in missing_variables/diagnostic scope, or where ok-signal TRUE/FALSE counts changed because of that answer.
- Preserve prior status for all other candidate pathways unless rules_out signals are now TRUE.
- Update reasoning on changed pathways to cite signal IDs, the new user evidence, and how the revision affects the answer to [USER PROBLEM].
- Update solutions to match the revised confirmed set and the user's question.
- Do NOT repeat a follow-up question already listed under QUESTIONS ALREADY ASKED.
"""

    uid = location.get("uid")
    query_block = _user_query_directive()
    if profile == "claude":
        signal_results_block = ""
        registry_block = ""
    else:
        eval_results = signal_eval if signal_eval is not None else evaluate_bundle_signals(bundle, injected=injected_variables)
        signal_results_block = _format_signal_evaluation_results(eval_results)
        registry_block = _registry_excerpt_if_needed(eval_results)

    return f"""{_intro_line(profile)}

[LOCATION CONTEXT]
{_format_location(location)}

[USER PROBLEM]
{problem_description}
{query_block}{follow_block}{prior_diagnosis_block}{revision_task}
[MWS VARIABLE VALUES AND CANDIDATE PATHWAYS]
{_format_bundle(bundle, profile)}

{signal_results_block}{registry_block}
{_format_solutions_available(bundle)}

{_format_prior_user_blocks(injected_variables, prior_asked_questions)}
{_task_section(uid, profile, is_revision=is_revision)}
"""


def _postprocess_diagnosis_response(
    response: dict[str, Any],
    *,
    profile: str,
    signal_eval: dict[str, dict[str, Any]],
    bundle: dict[str, dict],
    injected_variables: dict[str, Any] | None,
    prior_asked_questions: list[str] | None,
    pathway_retrieval_ranks: dict[str, int] | None,
    ruled_out_pathways: set[str],
    follow_up_context: str | None,
) -> dict[str, Any]:
    use_signal_guards = profile != "claude"
    ruled_out_for_follow_up = ruled_out_pathways if use_signal_guards else None

    if use_signal_guards:
        response = apply_signal_confidence_guard(
            response,
            signal_eval=signal_eval,
            bundle=bundle,
        )
    response = sanitize_uncertain_pathways(
        response,
        bundle=bundle,
        injected_variables=injected_variables,
        prior_asked_questions=prior_asked_questions,
    )
    response = pick_next_follow_up(
        response,
        injected_variables,
        bundle=bundle,
        prior_asked_questions=prior_asked_questions,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
        ruled_out_pathway_ids=ruled_out_for_follow_up,
    )
    return apply_panel_updates_from_standards(response, follow_up_context=follow_up_context)


def run_diagnosis(
    *,
    location: dict,
    problem_description: str,
    bundle: dict[str, dict],
    follow_up_context: str | None = None,
    follow_up: bool = False,
    injected_variables: dict[str, Any] | None = None,
    prior_asked_questions: list[str] | None = None,
    prior_diagnosis: dict[str, Any] | None = None,
    pathway_retrieval_ranks: dict[str, int] | None = None,
    answered_variable: str | None = None,
) -> DiagnosisRun:
    profile = _prompt_profile()
    signal_eval = evaluate_bundle_signals(bundle, injected=injected_variables)
    use_signal_guards = profile != "claude"
    ruled_out_pathways = (
        pathways_ruled_out_from_signal_evaluation(signal_eval) if use_signal_guards else set()
    )
    prompt = _build_prompt(
        location=location,
        problem_description=problem_description,
        bundle=bundle,
        follow_up_context=follow_up_context,
        injected_variables=injected_variables,
        prior_asked_questions=prior_asked_questions,
        prior_diagnosis=prior_diagnosis,
        is_revision=follow_up,
        profile=profile,
        signal_eval=signal_eval,
    )
    chosen_model = model_for_turn(follow_up=follow_up)
    t0 = time.perf_counter()
    raw = chat_json(prompt, model=chosen_model, follow_up=follow_up)
    llm_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    try:
        parsed = parse_json_response(raw)
    except DiagnosisLLMParseError as exc:
        exc.prompt = prompt
        exc.prompt_profile = profile
        raise
    response = normalize_diagnosis_response(
        parsed,
        injected_variables=injected_variables,
        bundle=bundle,
        prior_asked_questions=prior_asked_questions,
        follow_up_context=follow_up_context,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
        ruled_out_pathway_ids=ruled_out_pathways if use_signal_guards else None,
    )
    response = _postprocess_diagnosis_response(
        response,
        profile=profile,
        signal_eval=signal_eval,
        bundle=bundle,
        injected_variables=injected_variables,
        prior_asked_questions=prior_asked_questions,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
        ruled_out_pathways=ruled_out_pathways,
        follow_up_context=follow_up_context,
    )
    if follow_up and answered_variable and prior_diagnosis and use_signal_guards:
        response = apply_scoped_follow_up(
            response,
            prior_diagnosis,
            answered_variable,
            signal_evaluation=signal_eval,
        )
        response = apply_user_rule_out(
            response,
            answered_variable,
            signal_evaluation=signal_eval,
        )
        ruled_out_pathways = pathways_ruled_out_from_signal_evaluation(signal_eval)
        response = apply_ruled_out_guard(
            response,
            signal_evaluation=signal_eval,
            answered_variable=answered_variable,
        )
        response = _postprocess_diagnosis_response(
            response,
            profile=profile,
            signal_eval=signal_eval,
            bundle=bundle,
            injected_variables=injected_variables,
            prior_asked_questions=prior_asked_questions,
            pathway_retrieval_ranks=pathway_retrieval_ranks,
            ruled_out_pathways=ruled_out_pathways,
            follow_up_context=follow_up_context,
        )
    postprocess_ms = (time.perf_counter() - t1) * 1000
    run = DiagnosisRun(
        response=response,
        prompt=prompt,
        raw_llm_text=raw,
        model=chosen_model,
        llm_ms=llm_ms,
        postprocess_ms=postprocess_ms,
        prompt_profile=profile,
        signal_evaluation=signal_eval,
    )
    return run


def run_server_diagnosis(
    *,
    location: dict,
    problem_description: str,
    bundle: dict[str, dict],
    follow_up_context: str | None = None,
    follow_up: bool = False,
    injected_variables: dict[str, Any] | None = None,
    prior_asked_questions: list[str] | None = None,
    prior_diagnosis: dict[str, Any] | None = None,
    pathway_retrieval_ranks: dict[str, int] | None = None,
    answered_variable: str | None = None,
) -> DiagnosisRun:
    """Build a complete diagnosis response without calling the LLM."""
    from services.evidence_note import (
        build_follow_up_panel_summary,
        build_server_panel_summary,
        pathway_status_from_evaluation,
        solutions_for_confirmed_pathways,
    )
    from services.signal_evaluator import collect_follow_up_signal_updates, evaluate_bundle_signals

    t0 = time.perf_counter()
    signal_eval = evaluate_bundle_signals(bundle, injected=injected_variables)
    ruled_out = pathways_ruled_out_from_signal_evaluation(signal_eval)

    status = pathway_status_from_evaluation(
        signal_eval,
        bundle,
        injected_variables=injected_variables,
        ruled_out_ids=ruled_out,
        location=location,
    )
    response: dict[str, Any] = {
        "confirmed_pathways": status["confirmed_pathways"],
        "uncertain_pathways": status["uncertain_pathways"],
        "solutions": [],
        "panel_updates": [],
        "panel_update_explanation": None,
        "follow_up_question": None,
        "follow_up_variable": None,
    }

    response = apply_signal_confidence_guard(
        response,
        signal_eval=signal_eval,
        bundle=bundle,
    )

    if follow_up and answered_variable and prior_diagnosis:
        response = apply_scoped_follow_up(
            response,
            prior_diagnosis,
            answered_variable,
            signal_evaluation=signal_eval,
        )
        response = apply_user_rule_out(
            response,
            answered_variable,
            signal_evaluation=signal_eval,
        )
        response = apply_ruled_out_guard(
            response,
            signal_evaluation=signal_eval,
            answered_variable=answered_variable,
        )
        ruled_out = pathways_ruled_out_from_signal_evaluation(signal_eval)

    confirmed_ids = [
        str(p.get("pathway_id") or "")
        for p in response.get("confirmed_pathways") or []
        if isinstance(p, dict) and p.get("pathway_id")
    ]
    response["solutions"] = solutions_for_confirmed_pathways(confirmed_ids, bundle)

    response = _enrich_pathways_from_bundle(response, bundle)
    response = sanitize_uncertain_pathways(
        response,
        bundle=bundle,
        injected_variables=injected_variables,
        prior_asked_questions=prior_asked_questions,
    )
    response = pick_next_follow_up(
        response,
        injected_variables,
        bundle=bundle,
        prior_asked_questions=prior_asked_questions,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
        ruled_out_pathway_ids=ruled_out,
    )
    response = apply_panel_updates_from_standards(response, follow_up_context=follow_up_context)

    if follow_up and prior_diagnosis:
        signal_updates = collect_follow_up_signal_updates(signal_eval, answered_variable)
        response = apply_follow_up_revision(
            response,
            prior_diagnosis,
            answered_variable=answered_variable,
            follow_up_signal_updates=signal_updates,
            signal_evaluation=signal_eval,
        )
        if not response.get("panel_update_explanation"):
            response["panel_update_explanation"] = build_follow_up_panel_summary(
                response.get("diagnosis_revision")
            )
    else:
        summary = build_server_panel_summary(
            location,
            response.get("confirmed_pathways") or [],
            response.get("uncertain_pathways") or [],
            signal_eval,
            problem_description=problem_description or None,
        )
        updates = response.get("panel_updates") or []
        if updates:
            from services.panel_updates import build_panel_update_explanation

            chart_part = build_panel_update_explanation(
                response.get("confirmed_pathways") or [],
                updates,
            )
            response["panel_update_explanation"] = (
                f"{summary} {chart_part}" if chart_part else summary
            )
        else:
            response["panel_update_explanation"] = summary

    from services.follow_up_mcq import attach_follow_up_mcq

    response = attach_follow_up_mcq(response, bundle)

    postprocess_ms = (time.perf_counter() - t0) * 1000
    return DiagnosisRun(
        response=response,
        prompt="",
        raw_llm_text="",
        model="server",
        llm_ms=0.0,
        postprocess_ms=postprocess_ms,
        prompt_profile="server",
        signal_evaluation=signal_eval,
    )


def run_llm_reviewer_diagnosis(
    *,
    location: dict,
    problem_description: str,
    bundle: dict[str, dict],
    follow_up_context: str | None = None,
    follow_up: bool = False,
    injected_variables: dict[str, Any] | None = None,
    prior_asked_questions: list[str] | None = None,
    prior_diagnosis: dict[str, Any] | None = None,
    pathway_retrieval_ranks: dict[str, int] | None = None,
    answered_variable: str | None = None,
) -> DiagnosisRun:
    """Server-canonical diagnosis plus optional LLM reviewer commentary."""
    profile = _prompt_profile()
    server_run = run_server_diagnosis(
        location=location,
        problem_description=problem_description,
        bundle=bundle,
        follow_up_context=follow_up_context,
        follow_up=follow_up,
        injected_variables=injected_variables,
        prior_asked_questions=prior_asked_questions,
        prior_diagnosis=prior_diagnosis,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
        answered_variable=answered_variable,
    )
    signal_eval = server_run.signal_evaluation or {}
    prompt = _build_reviewer_prompt(
        location=location,
        problem_description=problem_description,
        bundle=bundle,
        server_response=server_run.response,
        signal_eval=signal_eval,
        follow_up_context=follow_up_context,
        injected_variables=injected_variables,
        prior_asked_questions=prior_asked_questions,
        is_revision=follow_up,
    )
    chosen_model = model_for_turn(follow_up=follow_up)
    t0 = time.perf_counter()
    raw = chat_json(prompt, model=chosen_model, follow_up=follow_up)
    llm_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    try:
        parsed = parse_json_response(raw)
    except DiagnosisLLMParseError as exc:
        exc.prompt = prompt
        exc.prompt_profile = f"{profile}_reviewer"
        raise
    reviewer = _normalize_reviewer_response(parsed)
    response = _merge_reviewer_into_response(server_run.response, reviewer)
    postprocess_ms = (time.perf_counter() - t1) * 1000
    return DiagnosisRun(
        response=response,
        prompt=prompt,
        raw_llm_text=raw,
        model=chosen_model,
        llm_ms=llm_ms,
        postprocess_ms=postprocess_ms + server_run.postprocess_ms,
        prompt_profile=f"{profile}_reviewer",
        signal_evaluation=signal_eval,
    )
