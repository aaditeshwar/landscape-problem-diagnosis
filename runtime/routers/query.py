import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import LLM_PROVIDER, OLLAMA_CHAT_TIMEOUT, OLLAMA_URL
from db import get_db
from logging_setup import log_diagnosis_event
from services.assembler import assemble_variable_bundle, location_context
from services.diagnosis_revision import (
    apply_follow_up_revision,
    normalize_qualitative_answer,
    prior_diagnosis_from_session,
)
from services.diagnosis_trace import DiagnosisRequestTrace
from services.llm_client import model_for_turn
from services.mws_enrich import enrich_mws_doc
from services.reasoner import DiagnosisLLMParseError, _collect_prior_follow_up, run_diagnosis
from services.retriever import (
    frozen_retrieval_result,
    load_evidence_cards_by_ids,
    pathway_retrieval_ranks,
    retrieve_evidence_cards,
    _aer_tags_for_retrieval,
)
from services.signal_evaluator import (
    collect_follow_up_signal_updates,
    evaluate_bundle_signals,
    summarize_evaluation_for_log,
    summarize_pathway_evidence,
)
from services.session_manager import append_turn, create_session, get_session

router = APIRouter(prefix="/api", tags=["diagnosis"])


def _llm_failure_hint() -> str:
    if LLM_PROVIDER == "anthropic":
        return "check ANTHROPIC_API_KEY and LLM_PROVIDER=anthropic"
    return f"Ollama at {OLLAMA_URL}"


def _format_llm_error(exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    lower = msg.lower()
    if isinstance(exc, httpx.TimeoutException) or "timed out" in lower or "timeout" in lower:
        return (
            f"Ollama generation timed out after {OLLAMA_CHAT_TIMEOUT:.0f}s "
            f"(server reachable at {OLLAMA_URL}; qwen2.5:14b may still be busy): {msg}"
        )
    if isinstance(exc, httpx.ConnectError) or "connect" in lower or "connection refused" in lower:
        return f"Cannot connect to Ollama at {OLLAMA_URL}: {msg}"
    return f"Diagnosis LLM call failed ({_llm_failure_hint()}): {msg}"


def _llm_http_exception(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=_format_llm_error(exc))


def _mws_trace_fields(mws_doc: dict) -> dict:
    return {
        "mws_uid": str(mws_doc.get("uid")),
        "tehsil": mws_doc.get("tehsil"),
        "district": mws_doc.get("district"),
        "state": mws_doc.get("state"),
        "mws_aer_code": mws_doc.get("nbss_lup_aer_code"),
    }


def _log_failed_diagnosis(
    *,
    event: str,
    turn_type: str,
    session_id: str,
    mws_doc: dict,
    problem_description: str,
    retrieval_query: str,
    cards: list[dict],
    bundle: dict[str, dict],
    injected: dict,
    retrieval,
    assemble_ms: float,
    request_started: float,
    llm_started: float,
    exc: Exception,
    model: str,
    follow_up_answer: str | None = None,
    follow_up_variable: str | None = None,
    llm_raw_response: str | None = None,
    prompt: str | None = None,
    prompt_profile: str | None = None,
) -> None:
    signal_eval = evaluate_bundle_signals(bundle, injected=injected or None)
    llm_ms = (time.perf_counter() - llm_started) * 1000
    total_ms = (time.perf_counter() - request_started) * 1000
    trace = DiagnosisRequestTrace(
        event=event,
        session_id=session_id,
        turn_type=turn_type,
        model=model,
        retrieval_query=retrieval_query,
        problem_description=problem_description,
        retrieved_card_ids=_card_ids(cards),
        pathway_evidence=summarize_pathway_evidence(
            bundle, mws_aer_code=mws_doc.get("nbss_lup_aer_code"), retrieval_aer_tags=_aer_tags_for_retrieval(mws_doc)
        ),
        signal_evaluation=summarize_evaluation_for_log(signal_eval),
        timings_ms={
            **retrieval.metrics.as_dict(),
            "assemble_bundle": round(assemble_ms, 2),
            "llm": round(llm_ms, 2),
            "total": round(total_ms, 2),
        },
        status="failed",
        error=_format_llm_error(exc),
        llm_raw_response=llm_raw_response or getattr(exc, "raw", "") or "",
        prompt=prompt or getattr(exc, "prompt", "") or "",
        prompt_profile=prompt_profile or getattr(exc, "prompt_profile", "") or "",
        follow_up_variable=follow_up_variable,
        follow_up_answer=follow_up_answer,
        **_mws_trace_fields(mws_doc),
    )
    _emit_diagnosis_log(trace)


class QueryRequest(BaseModel):
    uid: str
    problem_description: str
    session_id: str | None = None


class AnswerRequest(BaseModel):
    session_id: str
    variable: str
    answer: str


def _load_mws(uid: str) -> dict:
    db = get_db()
    doc = db.mws_data.find_one({"uid": uid})
    if not doc:
        raise HTTPException(status_code=404, detail=f"MWS not found: {uid}")
    return enrich_mws_doc(db, doc)


def _card_ids(cards: list[dict]) -> list[str]:
    return [str(c.get("card_id")) for c in cards if c.get("card_id")]


def _emit_diagnosis_log(trace: DiagnosisRequestTrace) -> None:
    log_diagnosis_event(trace.to_log_event())


def _run_query(mws_doc: dict, problem_description: str, session_id: str | None) -> dict:
    request_started = time.perf_counter()
    db = get_db()
    if session_id:
        session = get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        if session.get("mws_uid") != mws_doc.get("uid"):
            raise HTTPException(status_code=400, detail="Session MWS does not match request uid")
    else:
        session = create_session(db, mws_doc)
        session_id = session["_id"]

    injected = session.get("injected_variables") or {}
    try:
        retrieval = retrieve_evidence_cards(db, problem_description, mws_doc)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Embedding/retrieval failed — is Ollama reachable at {OLLAMA_URL}? ({exc})",
        ) from exc

    cards = retrieval.cards
    t0 = time.perf_counter()
    bundle = assemble_variable_bundle(mws_doc, cards, injected=injected or None)
    assemble_ms = (time.perf_counter() - t0) * 1000
    ranks = pathway_retrieval_ranks(cards)

    llm_started = time.perf_counter()
    try:
        diagnosis = run_diagnosis(
            location=location_context(mws_doc),
            problem_description=problem_description,
            bundle=bundle,
            injected_variables=injected or None,
            pathway_retrieval_ranks=ranks,
        )
    except Exception as exc:
        _log_failed_diagnosis(
            event="diagnosis_query",
            turn_type="initial",
            session_id=session_id,
            mws_doc=mws_doc,
            problem_description=problem_description,
            retrieval_query=problem_description,
            cards=cards,
            bundle=bundle,
            injected=injected,
            retrieval=retrieval,
            assemble_ms=assemble_ms,
            request_started=request_started,
            llm_started=llm_started,
            exc=exc,
            model=model_for_turn(follow_up=False),
        )
        raise _llm_http_exception(exc) from exc

    llm_response = diagnosis.response
    total_ms = (time.perf_counter() - request_started) * 1000
    timings = {
        **retrieval.metrics.as_dict(),
        "assemble_bundle": round(assemble_ms, 2),
        **diagnosis.as_timing_dict(),
        "total": round(total_ms, 2),
    }

    trace = DiagnosisRequestTrace(
        event="diagnosis_query",
        session_id=session_id,
        turn_type="initial",
        model=diagnosis.model,
        retrieval_query=problem_description,
        problem_description=problem_description,
        retrieved_card_ids=_card_ids(cards),
        pathway_evidence=summarize_pathway_evidence(
            bundle, mws_aer_code=mws_doc.get("nbss_lup_aer_code"), retrieval_aer_tags=_aer_tags_for_retrieval(mws_doc)
        ),
        signal_evaluation=summarize_evaluation_for_log(diagnosis.signal_evaluation or {}),
        timings_ms=timings,
        prompt=diagnosis.prompt,
        prompt_profile=diagnosis.prompt_profile,
        llm_raw_response=diagnosis.raw_llm_text,
        llm_response=llm_response,
        follow_up_question=llm_response.get("follow_up_question"),
        follow_up_variable=llm_response.get("follow_up_variable"),
        **_mws_trace_fields(mws_doc),
    )
    _emit_diagnosis_log(trace)

    append_turn(
        db,
        session_id,
        user_input=problem_description,
        retrieved_cards=_card_ids(cards),
        llm_model=model_for_turn(follow_up=False),
        llm_response=llm_response,
    )

    return {
        "session_id": session_id,
        "mws_aer_code": mws_doc.get("nbss_lup_aer_code"),
        "retrieval_aer_tags": _aer_tags_for_retrieval(mws_doc) or [],
        "pathway_retrieval_ranks": ranks,
        "signal_evaluation": summarize_evaluation_for_log(diagnosis.signal_evaluation or {}),
        **llm_response,
    }


@router.post("/query")
def diagnosis_query(body: QueryRequest):
    mws_doc = _load_mws(body.uid)
    return _run_query(mws_doc, body.problem_description, body.session_id)


@router.post("/answer")
def diagnosis_answer(body: AnswerRequest):
    request_started = time.perf_counter()
    db = get_db()
    session = get_session(db, body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {body.session_id}")

    mws_doc = _load_mws(session["mws_uid"])
    injected = dict(session.get("injected_variables") or {})
    normalized_answer = normalize_qualitative_answer(body.variable, body.answer)
    injected[body.variable] = normalized_answer

    first_turn = (session.get("turns") or [{}])[0]
    problem_description = first_turn.get("user_input") or ""
    frozen_card_ids = first_turn.get("retrieved_cards") or []
    if not frozen_card_ids:
        raise HTTPException(status_code=400, detail="Session has no retrieved evidence cards to revise against")

    cards = load_evidence_cards_by_ids(db, frozen_card_ids)
    if not cards:
        raise HTTPException(status_code=502, detail="Failed to reload evidence cards for this session")
    retrieval = frozen_retrieval_result(cards)
    retrieval_query = f"{problem_description} | follow-up: {body.variable}={normalized_answer.get('raw', body.answer)}"
    t0 = time.perf_counter()
    bundle = assemble_variable_bundle(mws_doc, cards, injected=injected)
    assemble_ms = (time.perf_counter() - t0) * 1000
    ranks = pathway_retrieval_ranks(cards)

    follow_up_context = f"{body.variable}: {normalized_answer.get('raw', body.answer)}"
    if normalized_answer.get("present") is not None:
        follow_up_context += f" (present={normalized_answer['present']}"
        if normalized_answer.get("trend"):
            follow_up_context += f", trend={normalized_answer['trend']}"
        follow_up_context += ")"

    _injected, prior_asked_questions = _collect_prior_follow_up(session)
    prior_diagnosis = prior_diagnosis_from_session(session)
    llm_started = time.perf_counter()
    try:
        diagnosis = run_diagnosis(
            location=location_context(mws_doc),
            problem_description=problem_description,
            bundle=bundle,
            follow_up_context=follow_up_context,
            follow_up=True,
            injected_variables=injected,
            prior_asked_questions=prior_asked_questions,
            prior_diagnosis=prior_diagnosis,
            pathway_retrieval_ranks=ranks,
            answered_variable=body.variable,
        )
    except Exception as exc:
        _log_failed_diagnosis(
            event="diagnosis_follow_up",
            turn_type="follow_up",
            session_id=body.session_id,
            mws_doc=mws_doc,
            problem_description=problem_description,
            retrieval_query=retrieval_query,
            cards=cards,
            bundle=bundle,
            injected=injected,
            retrieval=retrieval,
            assemble_ms=assemble_ms,
            request_started=request_started,
            llm_started=llm_started,
            exc=exc,
            model=model_for_turn(follow_up=True),
            follow_up_answer=body.answer,
            follow_up_variable=body.variable,
        )
        raise _llm_http_exception(exc) from exc

    t1 = time.perf_counter()
    signal_updates = collect_follow_up_signal_updates(
        diagnosis.signal_evaluation or {},
        body.variable,
    )
    llm_response = apply_follow_up_revision(
        diagnosis.response,
        prior_diagnosis,
        answered_variable=body.variable,
        follow_up_signal_updates=signal_updates,
        signal_evaluation=diagnosis.signal_evaluation or {},
    )
    revision_ms = (time.perf_counter() - t1) * 1000

    total_ms = (time.perf_counter() - request_started) * 1000
    timings = {
        **retrieval.metrics.as_dict(),
        "assemble_bundle": round(assemble_ms, 2),
        **diagnosis.as_timing_dict(),
        "follow_up_revision": round(revision_ms, 2),
        "total": round(total_ms, 2),
    }

    trace = DiagnosisRequestTrace(
        event="diagnosis_follow_up",
        session_id=body.session_id,
        turn_type="follow_up",
        model=diagnosis.model,
        retrieval_query=retrieval_query,
        problem_description=problem_description,
        retrieved_card_ids=_card_ids(cards),
        pathway_evidence=summarize_pathway_evidence(
            bundle, mws_aer_code=mws_doc.get("nbss_lup_aer_code"), retrieval_aer_tags=_aer_tags_for_retrieval(mws_doc)
        ),
        signal_evaluation=summarize_evaluation_for_log(diagnosis.signal_evaluation or {}),
        timings_ms=timings,
        prompt=diagnosis.prompt,
        prompt_profile=diagnosis.prompt_profile,
        llm_raw_response=diagnosis.raw_llm_text,
        llm_response=llm_response,
        follow_up_question=llm_response.get("follow_up_question"),
        follow_up_variable=body.variable,
        follow_up_answer=body.answer,
        follow_up_signal_updates=llm_response.get("follow_up_signal_updates") or signal_updates,
        **_mws_trace_fields(mws_doc),
    )
    _emit_diagnosis_log(trace)

    append_turn(
        db,
        body.session_id,
        user_input=body.answer,
        retrieved_cards=_card_ids(cards),
        llm_model=model_for_turn(follow_up=True),
        llm_response=llm_response,
        injected_variable={body.variable: normalized_answer},
    )

    return {
        "session_id": body.session_id,
        "mws_aer_code": mws_doc.get("nbss_lup_aer_code"),
        "retrieval_aer_tags": _aer_tags_for_retrieval(mws_doc) or [],
        "pathway_retrieval_ranks": ranks,
        "signal_evaluation": summarize_evaluation_for_log(diagnosis.signal_evaluation or {}),
        **llm_response,
    }
