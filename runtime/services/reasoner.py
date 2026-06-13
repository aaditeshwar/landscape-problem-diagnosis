from __future__ import annotations

import json
import re
from typing import Any

from services.assembler import authorized_follow_up_questions
from services.ollama_client import chat_json, reason_model
from services.panel_updates import apply_panel_updates_from_standards


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
    out["follow_up_question"] = follow_up if follow_up not in (None, "", "null") else None
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


def _format_bundle(bundle: dict[str, dict]) -> str:
    parts = []
    for pathway_id, data in bundle.items():
        parts.append(f"Pathway: {pathway_id}")
        parts.append(f"Description: {data.get('description', '')}")
        parts.append(f"Present variables: {json.dumps(data.get('present_variables', {}), default=str)}")
        missing = data.get("missing_variables") or []
        if missing:
            parts.append(f"Missing variables: {', '.join(missing)}")
        card = data.get("evidence_card") or {}
        parts.append(f"Evidence note: {card.get('overall_reasoning_note', '')}")
        parts.append(f"Diagnostic signals: {json.dumps(card.get('diagnostic_signals', []), default=str)[:3000]}")
        parts.append(f"Confounders: {json.dumps(card.get('confounders', []), default=str)[:1500]}")
        parts.append("")
    return "\n".join(parts)


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
) -> str:
    follow_block = ""
    if follow_up_context:
        follow_block = f"\n[USER FOLLOW-UP ANSWER]\n{follow_up_context}\n"

    prior_block = ""
    if injected_variables:
        prior_block += (
            "\n[DATA ALREADY PROVIDED BY USER — do not ask again]\n"
            f"{json.dumps(injected_variables, default=str)}\n"
        )
    if prior_asked_questions:
        prior_block += (
            "\n[QUESTIONS ALREADY ASKED — do not repeat the same or equivalent question]\n"
            + "\n".join(f"- {q}" for q in prior_asked_questions)
            + "\n"
        )

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

    village_line = ", ".join(location.get("village_names") or []) or "none listed"
    uid = location.get("uid")

    return f"""You are an agro-ecological diagnosis assistant for Indian micro-watersheds.

[LOCATION CONTEXT]
MWS UID: {uid} | Tehsil: {location.get('tehsil')} | District: {location.get('district')} | State: {location.get('state')}
Intersecting villages: {village_line}
Aquifer: {location.get('aquifer_class')} ({location.get('aquifer_raw')}) | Terrain cluster: {location.get('terrain_cluster')} ({location.get('terrain_description')})
Area: {location.get('area_ha')} ha

[USER PROBLEM]
{problem_description}
{follow_block}{prior_block}{prior_diagnosis_block}{revision_task}
[MWS VARIABLE VALUES AND CANDIDATE PATHWAYS]
{_format_bundle(bundle)}

[TASK]
1. Assess each candidate pathway: confirmed / suggested / ruled_out — cite variable values from present_variables and any injected user evidence.
2. Put confirmed pathways in confirmed_pathways with confidence high/medium/low and short reasoning.
3. In each confirmed_pathways reasoning string, explicitly mention MWS UID {uid} and relevant intersecting village names from the list above.
4. Put a pathway in uncertain_pathways ONLY when key variables remain in missing_variables. Do NOT ask the user to supply values already listed under present_variables (e.g. single kharif area, double-crop area, cropping intensity, SWB areas, canal name, NREGA counts, hydrological trends, village SC/ST/literacy/population aggregates).
5. List solutions from the framework for confirmed pathways.
6. Set panel_update_explanation to 1–3 sentences explaining WHY the charts linked to your confirmed pathways help interpret the diagnosis — especially how they relate to the user's latest answer when a follow-up is present. Explain diagnostic purpose; do not mechanically list chart names or repeat "highlighted in the info panel".
7. Set follow_up_question ONLY for variables in missing_variables that have an authorized missing_variable_questions entry in the bundle — typically borewell_density, groundwater_salinity, irrigated_area_ha, or similar fields not in the Excel corpus. Never ask for Excel-backed landscape metrics already in present_variables. Never repeat a question from [QUESTIONS ALREADY ASKED] or ask for a variable listed in [DATA ALREADY PROVIDED BY USER].
Note: panel_updates chart keys are assigned server-side from reference_standards.json — do not include panel_updates in your JSON.

Return JSON with exactly these keys:
{{
  "confirmed_pathways": [{{"pathway_id": "...", "confidence": "high|medium|low", "reasoning": "..."}}],
  "uncertain_pathways": [{{"pathway_id": "...", "confidence": "high|medium|low", "missing_variable_questions": [{{"variable": "...", "question": "..."}}]}}],
  "solutions": ["..."],
  "panel_update_explanation": "..." or null,
  "follow_up_question": "..." or null
}}
Output valid JSON only. No prose outside JSON.
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
) -> dict[str, Any]:
    prompt = _build_prompt(
        location=location,
        problem_description=problem_description,
        bundle=bundle,
        follow_up_context=follow_up_context,
        injected_variables=injected_variables,
        prior_asked_questions=prior_asked_questions,
        prior_diagnosis=prior_diagnosis,
        is_revision=follow_up,
    )
    model = reason_model()
    raw = chat_json(prompt, model=model)
    parsed = parse_json_response(raw)
    return normalize_diagnosis_response(
        parsed,
        injected_variables=injected_variables,
        bundle=bundle,
        prior_asked_questions=prior_asked_questions,
        follow_up_context=follow_up_context,
        pathway_retrieval_ranks=pathway_retrieval_ranks,
    )
