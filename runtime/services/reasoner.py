from __future__ import annotations

import json
import re
import time
from typing import Any

from config import LLM_PROVIDER
from services.assembler import authorized_follow_up_questions
from services.diagnosis_trace import DiagnosisRun
from services.llm_client import chat_json, model_for_turn
from services.panel_updates import apply_panel_updates_from_standards

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
}


def parse_json_response(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


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


def pick_next_follow_up(
    response: dict[str, Any],
    injected_variables: dict[str, Any] | None = None,
    bundle: dict[str, dict] | None = None,
    *,
    prior_asked_questions: list[str] | None = None,
    pathway_retrieval_ranks: dict[str, int] | None = None,
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
        pathway_retrieval_ranks=pathway_retrieval_ranks,
    )
    authorized_questions = {question for _, question in authorized}

    current = out.get("follow_up_question")
    if current:
        current = str(current).strip()
        var = _variable_for_question(current, authorized)
        if (
            current not in authorized_questions
            or current in asked_texts
            or (var and var in injected)
        ):
            out["follow_up_question"] = None
        else:
            out["follow_up_question"] = current

    if out.get("follow_up_question"):
        return out

    for var, question in authorized:
        if question in asked_texts or var in injected:
            continue
        out["follow_up_question"] = question
        return out

    return out


def sanitize_uncertain_pathways(
    response: dict[str, Any],
    bundle: dict[str, dict] | None = None,
    injected_variables: dict[str, Any] | None = None,
    *,
    prior_asked_questions: list[str] | None = None,
) -> dict[str, Any]:
    """Drop follow-up questions that refer to variables already present in MWS data."""
    if not bundle:
        return response

    out = dict(response)
    injected = injected_variables or {}
    asked_texts = {q.strip() for q in (prior_asked_questions or []) if q and str(q).strip()}
    present: set[str] = set(injected)
    truly_missing: set[str] = set()
    for data in bundle.values():
        present.update((data.get("present_variables") or {}).keys())
        truly_missing.update(data.get("missing_variables") or [])

    cleaned_pathways = []
    for pathway in out.get("uncertain_pathways") or []:
        if not isinstance(pathway, dict):
            continue
        item = dict(pathway)
        questions = []
        for q in item.get("missing_variable_questions") or []:
            if not isinstance(q, dict):
                continue
            var = q.get("variable") or q.get("missing_variable")
            question = str(q.get("question") or q.get("question_to_user") or "").strip()
            if var and (var in present or var not in truly_missing):
                continue
            if question and question in asked_texts:
                continue
            questions.append(q)
        item["missing_variable_questions"] = questions
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
) -> dict[str, Any]:
    out = dict(parsed)
    out["confirmed_pathways"] = _normalize_pathway_list(out.get("confirmed_pathways"), uncertain=False)
    out["uncertain_pathways"] = _normalize_pathway_list(out.get("uncertain_pathways"), uncertain=True)
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
    out = pick_next_follow_up(
        out,
        injected_variables,
        bundle=bundle,
        prior_asked_questions=prior_asked_questions,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
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
    return f"""MWS UID: {location.get('uid')} | Tehsil: {location.get('tehsil')} | District: {location.get('district')} | State: {location.get('state')}
{aer_line}Intersecting villages: {village_line}
Aquifer: {location.get('aquifer_class')} ({location.get('aquifer_raw')}) | Terrain cluster: {location.get('terrain_cluster')} ({location.get('terrain_description')})
Area: {location.get('area_ha')} ha"""


def _ollama_eval_block() -> str:
    return """
[SIGNAL EVALUATION — internal reasoning; do not output this section]
For each pathway below:
1. Evaluate each signal expression against present_variables and derived/computed values (TRUE/FALSE).
2. Apply the evidence note confirmation logic.
3. Assign confidence: high when ≥2 confirming signals are TRUE; medium when exactly 1 is TRUE;
   low when none are TRUE but the pathway remains plausible from context.
Then produce only the JSON object described below.
"""


def _task_section(uid: str | None, profile: str) -> str:
    shared = f"""[TASK]
1. Assess each candidate pathway: confirmed / suggested / ruled_out — cite variable values from present_variables, derived/computed values, and any injected user evidence.
2. Put confirmed pathways in confirmed_pathways with confidence high/medium/low and short reasoning.
3. In each confirmed_pathways reasoning string, explicitly mention MWS UID {uid} and relevant intersecting village names from the list above.
4. CRITICAL — do not re-ask for data already in the prompt. Before writing follow_up_question or uncertain_pathways, check every variable against present_variables, derived/computed values, and [DATA ALREADY PROVIDED BY USER]. If a value is already there (including time-series and derived fields such as cropping_intensity, lulc_*_ha, hydrological trends, NREGA counts, village SC/ST/literacy/population), do NOT ask the user for it. Put a pathway in uncertain_pathways only when genuinely required variables remain in missing_variables.
5. List solutions from the framework for confirmed pathways.
6. Set panel_update_explanation to 1–3 sentences explaining WHY the charts linked to your confirmed pathways help interpret the diagnosis — especially how they relate to the user's latest answer when a follow-up is present. Explain diagnostic purpose; do not mechanically list chart names or repeat "highlighted in the info panel". Do not include a panel_updates field — chart selection is applied automatically from your confirmed pathways.
7. Set follow_up_question ONLY for variables in missing_variables that have an authorized missing_variable_questions entry in the bundle — typically borewell_density, groundwater_salinity, irrigated_area_ha, or similar fields not in the Excel corpus. Never repeat a question from [QUESTIONS ALREADY ASKED] or ask for a variable listed in [DATA ALREADY PROVIDED BY USER].

Return JSON with exactly these keys:
{{
  "confirmed_pathways": [{{"pathway_id": "...", "confidence": "high|medium|low", "reasoning": "..."}}],
  "uncertain_pathways": [{{"pathway_id": "...", "confidence": "high|medium|low", "missing_variable_questions": [{{"variable": "...", "question": "..."}}]}}],
  "solutions": ["..."],
  "panel_update_explanation": null,
  "follow_up_question": null
}}"""
    if profile == "ollama":
        return (
            shared
            + """
Output valid JSON only. No prose outside JSON.

IMPORTANT: Output ONLY the JSON object. No preamble, no explanation, no markdown fences.
The first character of your response must be '{' and the last must be '}'."""
        )
    return shared + "\nOutput valid JSON only. No prose outside JSON."


def _prompt_profile() -> str:
    return "claude" if LLM_PROVIDER == "anthropic" else "ollama"


def _intro_line(profile: str) -> str:
    if profile == "claude":
        return (
            "You are an expert agro-ecological diagnostician for Indian micro-watersheds. "
            "Use the variable values, evidence notes, and your domain knowledge of NBSS-LUP "
            "agro-ecological regions, aquifer behaviour, and rural livelihood systems."
        )
    return (
        "You are an agro-ecological diagnosis assistant for Indian micro-watersheds. "
        "Reason step-by-step through the signal evaluation instructions before writing the final JSON."
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
        revision_task = """
[REVISION TASK — follow-up turn]
You are revising the prior diagnosis after a user follow-up answer.
- Re-assess every candidate pathway using present_variables (including newly injected user evidence).
- Move pathways from uncertain_pathways to confirmed_pathways when the new evidence satisfies the evidence-card signals.
- Remove pathways from confirmed_pathways if the new evidence contradicts them or support is weak.
- Update reasoning on every confirmed pathway to cite the new user evidence where relevant.
- Update solutions to match the revised confirmed set.
- Do NOT repeat a follow-up question already listed under QUESTIONS ALREADY ASKED.
"""

    uid = location.get("uid")
    eval_block = _ollama_eval_block() if profile == "ollama" else ""

    return f"""{_intro_line(profile)}

[LOCATION CONTEXT]
{_format_location(location)}

[USER PROBLEM]
{problem_description}
{follow_block}{prior_diagnosis_block}{revision_task}{eval_block}
[MWS VARIABLE VALUES AND CANDIDATE PATHWAYS]
{_format_bundle(bundle, profile)}

{_format_solutions_available(bundle)}

{_format_prior_user_blocks(injected_variables, prior_asked_questions)}
{_task_section(uid, profile)}
"""


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
) -> DiagnosisRun:
    profile = _prompt_profile()
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
    )
    chosen_model = model_for_turn(follow_up=follow_up)
    t0 = time.perf_counter()
    raw = chat_json(prompt, model=chosen_model, follow_up=follow_up)
    llm_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    parsed = parse_json_response(raw)
    response = normalize_diagnosis_response(
        parsed,
        injected_variables=injected_variables,
        bundle=bundle,
        prior_asked_questions=prior_asked_questions,
        follow_up_context=follow_up_context,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
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
    )
    return run
