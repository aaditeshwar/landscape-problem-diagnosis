"""LLM rubric evaluator for query-bank diagnosis responses."""

from __future__ import annotations

import json
import re
from typing import Any

from eval.query_bank_index import RUBRIC_PATH, load_rubric

ROOT = RUBRIC_PATH.parents[2]

CARD_SUFFIX_RE = re.compile(r"__(\d{3})$")


def _runtime_import():
    import sys
    from pathlib import Path

    runtime_dir = Path(__file__).resolve().parents[2] / "runtime"
    if str(runtime_dir) not in sys.path:
        sys.path.insert(0, str(runtime_dir))


def _card_cluster_suffix(card_id: str | None) -> str | None:
    match = CARD_SUFFIX_RE.search(str(card_id or ""))
    return match.group(1) if match else None


def build_similarity_context_line(
    diagnosis: dict[str, Any],
    *,
    case_study: dict[str, Any] | None = None,
    mws_variable_summary: dict[str, Any] | None = None,
) -> str:
    """Clarify that server pathway notes come from cluster-matched evidence cards."""
    _runtime_import()
    from services.context_clusters import cluster_by_suffix

    mws_id = str((case_study or {}).get("mws_id") or diagnosis.get("mws_uid") or "").strip()
    tehsil = str((case_study or {}).get("tehsil") or "").strip()
    district = str((case_study or {}).get("district") or "").strip()
    state = str((case_study or {}).get("state") or "").strip()
    area_bits = [bit for bit in (f"MWS {mws_id}" if mws_id else "", tehsil, district, state) if bit]
    area_label = ", ".join(area_bits) if area_bits else "this micro-watershed"

    clusters = cluster_by_suffix()
    cluster_labels: list[str] = []
    for bucket in ("confirmed_pathways", "uncertain_pathways"):
        for item in diagnosis.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            suffix = _card_cluster_suffix(str(item.get("card_id") or ""))
            if suffix and suffix in clusters:
                label = str(clusters[suffix].get("label") or suffix)
                cluster_labels.append(f"cluster {suffix} ({label})")
    cluster_labels = sorted(set(cluster_labels))
    cluster_text = "; ".join(cluster_labels) if cluster_labels else "the nearest matching evidence-card cluster"

    summary = mws_variable_summary or {}
    aquifer = summary.get("aquifer_class") or summary.get("aquifer_raw")
    lithology = summary.get("aquifer_lithology_percent")
    mws_aquifer = ""
    if aquifer:
        mws_aquifer = f" This MWS aquifer_class is {aquifer}"
        if isinstance(lithology, dict) and lithology:
            top = max(lithology.items(), key=lambda kv: float(kv[1]) if kv[1] is not None else 0)
            mws_aquifer += f" with dominant lithology {top[0]} ({top[1]}%)."

    return (
        f"Context: This server analysis for {area_label} is based on similarity with {cluster_text}. "
        f"Evidence notes and thresholds describe the matched cluster context, not necessarily this MWS's exact "
        f"hydrogeology.{mws_aquifer}"
    )


def build_production_system_gating_note(diagnosis: dict[str, Any]) -> str | None:
    skipped = diagnosis.get("skipped_production_systems") or []
    if not skipped:
        return None
    lines: list[str] = []
    for item in skipped:
        if not isinstance(item, dict):
            continue
        production = str(item.get("production_system") or "")
        message = str(item.get("message") or "").strip()
        expression = str(item.get("expression") or "").strip()
        tree_cover = item.get("tree_cover_percent_mws")
        detail = message or expression or "production system gated out"
        if production == "NTFP_Forest_Biodiversity":
            threshold = "tree_cover_percent_mws < 20"
            if tree_cover is not None:
                detail = (
                    f"NTFP / forest biodiversity pathways were not evaluated because tree cover is "
                    f"{tree_cover}% of MWS area, below the {threshold}% eligibility threshold "
                    f"({expression or threshold})."
                )
            else:
                detail = (
                    f"NTFP / forest biodiversity pathways were not evaluated: {detail} "
                    f"(gate rule: {expression or threshold})."
                )
        elif production:
            detail = f"{production.replace('_', ' ')} pathways were not evaluated: {detail}"
        lines.append(detail)
    return " ".join(lines) if lines else None


def _pathway_eval_map(signal_evaluation: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in (signal_evaluation or {}).get("pathways") or []:
        if isinstance(item, dict) and item.get("pathway_id"):
            out[str(item["pathway_id"])] = item
    return out


def _enrich_pathways_for_eval(
    pathways: list[dict[str, Any]],
    signal_evaluation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    eval_map = _pathway_eval_map(signal_evaluation)
    enriched: list[dict[str, Any]] = []
    for item in pathways:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        pid = str(entry.get("pathway_id") or "")
        pathway_eval = eval_map.get(pid) or {}
        signal_bits: list[str] = []
        for sig in pathway_eval.get("signals") or []:
            if not isinstance(sig, dict):
                continue
            sig_id = str(sig.get("signal_id") or "?")
            result = sig.get("result")
            var_rows = sig.get("variable_values") or []
            if var_rows:
                vals = ", ".join(
                    f"{row.get('access')}={row.get('formatted')}"
                    for row in var_rows
                    if isinstance(row, dict)
                )
                signal_bits.append(f"{sig_id} ({result}): {vals}")
            elif sig.get("expression"):
                signal_bits.append(f"{sig_id} ({result}): {sig.get('expression')}")
        if signal_bits:
            entry["signal_variable_grounding"] = signal_bits
        if pathway_eval.get("evidence_note"):
            entry["evidence_note"] = pathway_eval.get("evidence_note")
        enriched.append(entry)
    return enriched


def resolve_solutions_for_eval(
    diagnosis: dict[str, Any],
    *,
    server_diagnosis: dict[str, Any] | None = None,
) -> list[str]:
    sols = [str(s) for s in (diagnosis.get("solutions") or []) if str(s).strip()]
    if sols:
        return sols
    review = diagnosis.get("solutions_review") if isinstance(diagnosis.get("solutions_review"), dict) else {}
    priority = [str(s) for s in (review.get("priority_order") or []) if str(s).strip()]
    if priority:
        return priority
    notes = str(diagnosis.get("solutions_review_notes") or review.get("notes") or "").strip()
    if notes:
        return [notes]
    if server_diagnosis:
        return [str(s) for s in (server_diagnosis.get("solutions") or []) if str(s).strip()]
    return []


def _server_eval_base(
    diagnosis: dict[str, Any],
    *,
    case_study: dict[str, Any] | None = None,
    mws_variable_summary: dict[str, Any] | None = None,
    server_diagnosis: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    signal_evaluation = diagnosis.get("signal_evaluation")
    gating = build_production_system_gating_note(diagnosis)
    payload: dict[str, Any] = {
        "similarity_context": build_similarity_context_line(
            diagnosis,
            case_study=case_study,
            mws_variable_summary=mws_variable_summary,
        ),
        "production_system_gating": gating,
        "confirmed_pathways": _enrich_pathways_for_eval(
            diagnosis.get("confirmed_pathways") or [],
            signal_evaluation,
        ),
        "uncertain_pathways": _enrich_pathways_for_eval(
            diagnosis.get("uncertain_pathways") or [],
            signal_evaluation,
        ),
        "solutions": resolve_solutions_for_eval(diagnosis, server_diagnosis=server_diagnosis),
        "panel_updates": diagnosis.get("panel_updates") or [],
        "panel_update_explanation": diagnosis.get("panel_update_explanation"),
        "follow_up_question": diagnosis.get("follow_up_question"),
        "signal_evaluation": signal_evaluation,
        "mws_variable_summary": mws_variable_summary or {},
    }
    if gating:
        payload["panel_update_explanation"] = (
            f"{gating} {diagnosis.get('panel_update_explanation') or ''}".strip()
        )
    if extra:
        payload.update(extra)
    return payload


def _extract_json(text: str) -> dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        raise ValueError("Empty evaluator response")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    try:
        parsed, _end = decoder.raw_decode(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            parsed, _end = decoder.raw_decode(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
    raise ValueError("Evaluator did not return valid JSON")


def build_eval_response_payload(
    diagnosis: dict[str, Any],
    *,
    mode: str,
    case_study: dict[str, Any] | None = None,
    mws_variable_summary: dict[str, Any] | None = None,
    server_diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shape diagnosis output for rubric evaluation."""
    if mode == "server":
        return _server_eval_base(
            diagnosis,
            case_study=case_study,
            mws_variable_summary=mws_variable_summary,
            server_diagnosis=server_diagnosis,
        )

    if mode == "server_plus_llm_ollama":
        eval_diagnosis = dict(diagnosis)
        if server_diagnosis:
            if server_diagnosis.get("signal_evaluation"):
                eval_diagnosis["signal_evaluation"] = server_diagnosis["signal_evaluation"]
            if server_diagnosis.get("skipped_production_systems"):
                eval_diagnosis["skipped_production_systems"] = server_diagnosis["skipped_production_systems"]
        return _server_eval_base(
            eval_diagnosis,
            case_study=case_study,
            mws_variable_summary=mws_variable_summary,
            server_diagnosis=server_diagnosis or diagnosis,
            extra={
                "reviewer_commentary": diagnosis.get("reviewer_commentary") or [],
                "solutions_review": diagnosis.get("solutions_review"),
                "solutions_review_notes": diagnosis.get("solutions_review_notes"),
                "change_review": diagnosis.get("change_review"),
            },
        )

    confirmed: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    for item in diagnosis.get("independent_pathway_review") or []:
        if not isinstance(item, dict):
            continue
        pathway_id = str(item.get("pathway_id") or "").strip()
        if not pathway_id:
            continue
        present = str(item.get("pathway_present") or "uncertain").lower()
        reasoning_parts = []
        if item.get("reasoning"):
            reasoning_parts.append(str(item.get("reasoning")))
        datapoints = item.get("key_datapoints") or []
        if datapoints:
            reasoning_parts.append("Key datapoints: " + "; ".join(str(d) for d in datapoints))
        reasoning = " ".join(reasoning_parts).strip()
        entry = {
            "pathway_id": pathway_id,
            "reasoning": reasoning,
            "confidence": item.get("confidence") or "medium",
        }
        if present == "yes":
            confirmed.append(entry)
        elif present == "no":
            continue
        else:
            uncertain.append(entry)

    return {
        "confirmed_pathways": confirmed,
        "uncertain_pathways": uncertain,
        "solutions": resolve_solutions_for_eval(diagnosis, server_diagnosis=server_diagnosis),
        "panel_updates": diagnosis.get("panel_updates") or [],
        "panel_update_explanation": diagnosis.get("panel_update_explanation"),
        "follow_up_question": diagnosis.get("follow_up_question"),
        "independent_pathway_review": diagnosis.get("independent_pathway_review") or [],
        "reviewer_commentary": diagnosis.get("reviewer_commentary") or [],
        "solutions_review": diagnosis.get("solutions_review"),
        "solutions_review_notes": diagnosis.get("solutions_review_notes"),
        "mws_variable_summary": mws_variable_summary or {},
    }


def build_evaluator_prompt(
    *,
    query: dict[str, Any],
    eval_response: dict[str, Any],
    mws_variable_summary: dict[str, Any],
    mode: str,
) -> str:
    rubric = load_rubric()
    template = (rubric.get("example_evaluator_prompt") or {}).get("user") or ""
    query_id = str(query.get("id") or "")
    mode_note = ""
    if mode == "server":
        mode_note = (
            "\n\n## Mode note\n"
            "This response is from **server-only** mode (no user query was supplied to the diagnosis engine). "
            "Read the `similarity_context` field first: pathway evidence notes may describe a matched cluster "
            "context (e.g. volcanic hard-rock Malwa/Gujarat) that differs from this MWS's own aquifer_class — "
            "do not penalise D3 for cluster-context wording when `similarity_context` explains the mismatch. "
            "For D1 (Query Relevance), score whether the response contains information that *could* help "
            "answer the query, not whether it was tailored to the query. "
            "Add a `server_query_alignment` field (string, 2–3 sentences) describing how the generic server "
            "response relates to the query and what would improve alignment."
        )
    elif mode == "server_plus_llm_ollama":
        mode_note = (
            "\n\n## Mode note\n"
            "This response combines the **server diagnosis** (pathways, signal_evaluation, solutions) with "
            "**Ollama's reviewer commentary** on the server's signal results (`reviewer_commentary`). "
            "Evaluate how well the combined assessment answers the query when the LLM has access to signal "
            "TRUE/FALSE information. Do not use `independent_pathway_review` (not included). "
            "Apply the `similarity_context` caveat for cluster-matched evidence notes as in server-only mode."
        )
    elif mode.startswith("llm_"):
        mode_note = (
            "\n\n## Mode note\n"
            "This response is from an **LLM reviewer** mode. Evaluate based on the LLM's "
            "`independent_pathway_review` assessment (expression-blind), not only the server's "
            "confirmed/uncertain pathway lists. The confirmed/uncertain lists in the payload "
            "are derived from independent_pathway_review for scoring. "
            "If `solutions` contains a single long paragraph from `solutions_review_notes`, treat it "
            "as actionable recommendations proposed by the reviewer."
        )

    filled = template.format(
        query_id=query_id,
        persona=str(query.get("persona") or ""),
        production_system=str(query.get("production_system") or ""),
        query_text=str(query.get("query") or "").replace('"', '\\"'),
        mws_variable_summary_json=json.dumps(mws_variable_summary, ensure_ascii=False, indent=2),
        diagnosis_response_json=json.dumps(eval_response, ensure_ascii=False, indent=2),
        evaluation_rubric_json=json.dumps(rubric, ensure_ascii=False, indent=2),
    )
    return filled + mode_note


def evaluate_response(
    *,
    query: dict[str, Any],
    diagnosis: dict[str, Any],
    mws_variable_summary: dict[str, Any],
    mode: str,
    evaluator_provider: str = "anthropic",
    case_study: dict[str, Any] | None = None,
    server_diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _runtime_import()
    from services.llm_client import chat_json, llm_provider_override

    eval_response = build_eval_response_payload(
        diagnosis,
        mode=mode,
        case_study=case_study,
        mws_variable_summary=mws_variable_summary,
        server_diagnosis=server_diagnosis,
    )
    prompt = build_evaluator_prompt(
        query=query,
        eval_response=eval_response,
        mws_variable_summary=mws_variable_summary,
        mode=mode,
    )
    system = (load_rubric().get("example_evaluator_prompt") or {}).get("system") or ""
    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    with llm_provider_override(evaluator_provider):
        raw = chat_json(full_prompt, reviewer=True)

    parsed = _extract_json(raw)
    parsed.setdefault("query_id", query.get("id"))
    parsed.setdefault("persona", query.get("persona"))
    parsed["eval_mode"] = mode
    parsed["evaluator_provider"] = evaluator_provider
    return parsed
