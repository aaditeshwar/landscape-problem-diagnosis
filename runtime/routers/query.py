import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import LLM_PROVIDER, OLLAMA_CHAT_TIMEOUT, OLLAMA_URL
from db import get_db
from logging_setup import log_diagnosis_event
from services.assembler import assemble_variable_bundle, location_context
from services.diagnosis_revision import prior_diagnosis_from_session
from services.diagnosis_snapshot import build_snapshot_id, snapshot_fields, turn_metrics_from_session
from services.diagnosis_trace import DiagnosisRequestTrace
from services.llm_client import model_for_turn
from services.mws_enrich import enrich_mws_doc
from services.follow_up_mcq import attach_follow_up_mcq, normalized_answer_from_mcq_choice
from services.reasoner import (
    DiagnosisLLMParseError,
    _collect_prior_follow_up,
    run_llm_reviewer_diagnosis,
    run_server_diagnosis,
)
from services.retriever import (
    frozen_retrieval_result,
    load_evidence_cards_by_ids,
    load_mws_scoped_evidence_cards,
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
from services.session_manager import (
    append_turn,
    create_session,
    get_session,
    session_want_llm_opinion,
    set_session_want_llm_opinion,
)
from services.tehsil_refs import make_tehsil_ref, resolve_active_tehsil

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


def _mws_trace_fields(mws_doc: dict, tehsil_ref: dict | None = None) -> dict:
    active = resolve_active_tehsil(mws_doc, tehsil_ref)
    return {
        "mws_uid": str(mws_doc.get("uid")),
        "tehsil": active["tehsil"] if active else mws_doc.get("tehsil"),
        "district": active["district"] if active else mws_doc.get("district"),
        "state": active["state"] if active else mws_doc.get("state"),
        "mws_aer_code": mws_doc.get("nbss_lup_aer_code"),
    }


def _tehsil_ref_from_request(body: "QueryRequest") -> dict | None:
    if body.state and body.district and body.tehsil:
        return make_tehsil_ref(body.state, body.district, body.tehsil)
    return None


def _format_failure_error(failure_stage: str, exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    if failure_stage == "llm":
        return _format_llm_error(exc)
    if failure_stage == "retrieval":
        return f"Embedding/retrieval failed — is Ollama reachable at {OLLAMA_URL}? ({msg})"
    if failure_stage == "assembly":
        return f"Variable assembly failed: {msg}"
    if failure_stage == "load_mws":
        return msg
    if failure_stage == "session":
        return msg
    if failure_stage == "validation":
        return msg
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, list):
            return str(detail)
        return str(detail)
    return f"{failure_stage} failed: {msg}"


def _empty_retrieval_metrics() -> dict[str, float]:
    return {
        "embed": 0.0,
        "evidence_search": 0.0,
        "citations": 0.0,
        "retrieval_total": 0.0,
    }


def _trace_timings(
    *,
    request_started: float,
    retrieval=None,
    assemble_ms: float = 0.0,
    llm_started: float | None = None,
    extra: dict[str, float] | None = None,
) -> dict[str, float]:
    timings = dict(retrieval.metrics.as_dict()) if retrieval is not None else _empty_retrieval_metrics()
    if assemble_ms:
        timings["assemble_bundle"] = round(assemble_ms, 2)
    if llm_started is not None:
        timings["llm"] = round((time.perf_counter() - llm_started) * 1000, 2)
    if extra:
        timings.update(extra)
    timings["total"] = round((time.perf_counter() - request_started) * 1000, 2)
    return timings


def _log_diagnosis_failure(
    *,
    event: str,
    turn_type: str,
    failure_stage: str,
    exc: Exception,
    request_started: float,
    session_id: str | None = None,
    mws_doc: dict | None = None,
    mws_uid: str | None = None,
    problem_description: str = "",
    retrieval_query: str = "",
    cards: list[dict] | None = None,
    bundle: dict[str, dict] | None = None,
    injected: dict | None = None,
    retrieval=None,
    assemble_ms: float = 0.0,
    llm_started: float | None = None,
    model: str = "",
    follow_up_answer: str | None = None,
    follow_up_variable: str | None = None,
    llm_raw_response: str | None = None,
    prompt: str | None = None,
    prompt_profile: str | None = None,
    tehsil_ref: dict | None = None,
) -> None:
    cards = cards or []
    bundle = bundle or {}
    injected = injected or {}
    aer_tags = _aer_tags_for_retrieval(mws_doc) if mws_doc else []
    mws_fields = _mws_trace_fields(mws_doc, tehsil_ref) if mws_doc else {"mws_uid": str(mws_uid or "")}

    if bundle:
        signal_eval = summarize_evaluation_for_log(
            evaluate_bundle_signals(bundle, injected=injected or None)
        )
        pathway_evidence = summarize_pathway_evidence(
            bundle,
            mws_aer_code=(mws_doc or {}).get("nbss_lup_aer_code"),
            retrieval_aer_tags=aer_tags,
        )
    else:
        signal_eval = {}
        pathway_evidence = []

    trace = DiagnosisRequestTrace(
        event=event,
        session_id=session_id or "",
        turn_type=turn_type,
        model=model or model_for_turn(follow_up=turn_type == "follow_up"),
        retrieval_query=retrieval_query or problem_description,
        problem_description=problem_description or None,
        retrieved_card_ids=_card_ids(cards),
        pathway_evidence=pathway_evidence,
        signal_evaluation=signal_eval,
        timings_ms=_trace_timings(
            request_started=request_started,
            retrieval=retrieval,
            assemble_ms=assemble_ms,
            llm_started=llm_started,
        ),
        status="failed",
        failure_stage=failure_stage,
        error=_format_failure_error(failure_stage, exc),
        llm_raw_response=llm_raw_response or getattr(exc, "raw", "") or "",
        prompt=prompt or getattr(exc, "prompt", "") or "",
        prompt_profile=prompt_profile or getattr(exc, "prompt_profile", "") or "",
        follow_up_variable=follow_up_variable,
        follow_up_answer=follow_up_answer,
        **mws_fields,
    )
    _emit_diagnosis_log(trace)


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
    _log_diagnosis_failure(
        event=event,
        turn_type=turn_type,
        failure_stage="llm",
        exc=exc,
        request_started=request_started,
        session_id=session_id,
        mws_doc=mws_doc,
        problem_description=problem_description,
        retrieval_query=retrieval_query,
        cards=cards,
        bundle=bundle,
        injected=injected,
        retrieval=retrieval,
        assemble_ms=assemble_ms,
        llm_started=llm_started,
        model=model,
        follow_up_answer=follow_up_answer,
        follow_up_variable=follow_up_variable,
        llm_raw_response=llm_raw_response,
        prompt=prompt,
        prompt_profile=prompt_profile,
    )


class QueryRequest(BaseModel):
    uid: str
    problem_description: str = ""
    session_id: str | None = None
    state: str | None = None
    district: str | None = None
    tehsil: str | None = None
    want_llm_opinion: bool = False


class AnswerRequest(BaseModel):
    session_id: str
    variable: str
    answer: str = ""
    choice_id: str | None = None
    want_llm_opinion: bool | None = None


SERVER_SCOPED_RETRIEVAL_QUERY = "[server-scoped: all MWS-relevant pathways, no embedding]"


def _effective_retrieval_query(problem_description: str, *, want_llm_opinion: bool) -> str:
    text = str(problem_description or "").strip()
    if want_llm_opinion and not text:
        raise HTTPException(
            status_code=400,
            detail="problem_description is required when want_llm_opinion is true",
        )
    if not want_llm_opinion:
        return SERVER_SCOPED_RETRIEVAL_QUERY if not text else text
    return text


def _resolve_want_llm_opinion(request_flag: bool | None, session: dict | None) -> bool:
    if request_flag is not None:
        return bool(request_flag)
    return session_want_llm_opinion(session)


def _load_mws(uid: str) -> dict:
    db = get_db()
    doc = db.mws_data.find_one({"uid": uid})
    if not doc:
        raise HTTPException(status_code=404, detail=f"MWS not found: {uid}")
    return enrich_mws_doc(db, doc)


def _card_ids(cards: list[dict]) -> list[str]:
    return [str(c.get("card_id")) for c in cards if c.get("card_id")]


def _emit_diagnosis_log(trace: DiagnosisRequestTrace) -> int:
    return log_diagnosis_event(trace.to_log_event())


def _run_query(
    mws_doc: dict,
    problem_description: str,
    session_id: str | None,
    *,
    tehsil_ref: dict | None = None,
    request_started: float | None = None,
    want_llm_opinion: bool = False,
) -> dict:
    request_started = request_started or time.perf_counter()
    db = get_db()
    retrieval_query = _effective_retrieval_query(problem_description, want_llm_opinion=want_llm_opinion)
    user_problem = str(problem_description or "").strip()
    if session_id:
        session = get_session(db, session_id)
        if not session:
            exc = HTTPException(status_code=404, detail=f"Session not found: {session_id}")
            _log_diagnosis_failure(
                event="diagnosis_query",
                turn_type="initial",
                failure_stage="session",
                exc=exc,
                request_started=request_started,
                session_id=session_id,
                mws_doc=mws_doc,
                problem_description=problem_description,
                retrieval_query=problem_description,
                tehsil_ref=tehsil_ref,
            )
            raise exc
        if session.get("mws_uid") != mws_doc.get("uid"):
            exc = HTTPException(status_code=400, detail="Session MWS does not match request uid")
            _log_diagnosis_failure(
                event="diagnosis_query",
                turn_type="initial",
                failure_stage="session",
                exc=exc,
                request_started=request_started,
                session_id=session_id,
                mws_doc=mws_doc,
                problem_description=problem_description,
                retrieval_query=problem_description,
                tehsil_ref=tehsil_ref or session.get("tehsil_ref"),
            )
            raise exc
        tehsil_ref = tehsil_ref or session.get("tehsil_ref")
    else:
        session = create_session(db, mws_doc, tehsil_ref)
        session_id = session["_id"]

    set_session_want_llm_opinion(db, session_id, want_llm_opinion)

    injected = session.get("injected_variables") or {}
    try:
        if want_llm_opinion:
            retrieval = retrieve_evidence_cards(db, retrieval_query, mws_doc)
        else:
            retrieval = load_mws_scoped_evidence_cards(db, mws_doc)
    except Exception as exc:
        _log_diagnosis_failure(
            event="diagnosis_query",
            turn_type="initial",
            failure_stage="retrieval",
            exc=exc,
            request_started=request_started,
            session_id=session_id,
            mws_doc=mws_doc,
            problem_description=user_problem,
            retrieval_query=retrieval_query,
            injected=injected,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Embedding/retrieval failed — is Ollama reachable at {OLLAMA_URL}? ({exc})",
        ) from exc

    cards = retrieval.cards
    t0 = time.perf_counter()
    try:
        bundle = assemble_variable_bundle(mws_doc, cards, injected=injected or None)
    except Exception as exc:
        assemble_ms = (time.perf_counter() - t0) * 1000
        _log_diagnosis_failure(
            event="diagnosis_query",
            turn_type="initial",
            failure_stage="assembly",
            exc=exc,
            request_started=request_started,
            session_id=session_id,
            mws_doc=mws_doc,
            problem_description=user_problem,
            retrieval_query=retrieval_query,
            cards=cards,
            injected=injected,
            retrieval=retrieval,
            assemble_ms=assemble_ms,
        )
        raise HTTPException(status_code=500, detail=f"Variable assembly failed: {exc}") from exc
    assemble_ms = (time.perf_counter() - t0) * 1000
    ranks = pathway_retrieval_ranks(cards)

    llm_started = time.perf_counter()
    llm_skipped = not want_llm_opinion
    try:
        if want_llm_opinion:
            diagnosis = run_llm_reviewer_diagnosis(
                location=location_context(mws_doc, tehsil_ref),
                problem_description=user_problem,
                bundle=bundle,
                injected_variables=injected or None,
                pathway_retrieval_ranks=ranks,
            )
        else:
            diagnosis = run_server_diagnosis(
                location=location_context(mws_doc, tehsil_ref),
                problem_description=user_problem,
                bundle=bundle,
                injected_variables=injected or None,
                pathway_retrieval_ranks=ranks,
            )
    except Exception as exc:
        if llm_skipped:
            _log_diagnosis_failure(
                event="diagnosis_query",
                turn_type="initial",
                failure_stage="validation",
                exc=exc,
                request_started=request_started,
                session_id=session_id,
                mws_doc=mws_doc,
                problem_description=user_problem,
                retrieval_query=retrieval_query,
                cards=cards,
                bundle=bundle,
                injected=injected,
                retrieval=retrieval,
                assemble_ms=assemble_ms,
            )
            raise HTTPException(status_code=500, detail=f"Server diagnosis failed: {exc}") from exc
        _log_failed_diagnosis(
            event="diagnosis_query",
            turn_type="initial",
            session_id=session_id,
            mws_doc=mws_doc,
            problem_description=user_problem,
            retrieval_query=retrieval_query,
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
    llm_response = attach_follow_up_mcq(llm_response, bundle)
    total_ms = (time.perf_counter() - request_started) * 1000
    timings = {
        **retrieval.metrics.as_dict(),
        "assemble_bundle": round(assemble_ms, 2),
        **diagnosis.as_timing_dict(),
        "total": round(total_ms, 2),
    }

    follow_up_count, turn_no = turn_metrics_from_session(session, is_follow_up=False)

    trace = DiagnosisRequestTrace(
        event="diagnosis_query",
        session_id=session_id,
        turn_type="initial",
        model=diagnosis.model,
        retrieval_query=retrieval_query,
        problem_description=user_problem or None,
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
        want_llm_opinion=want_llm_opinion,
        llm_skipped=llm_skipped,
        follow_up_count=follow_up_count,
        turn_no=turn_no,
        diagnosis_snapshot_id=build_snapshot_id(session_id, follow_up_count),
        **_mws_trace_fields(mws_doc, tehsil_ref),
    )
    log_index = _emit_diagnosis_log(trace)

    append_turn(
        db,
        session_id,
        user_input=user_problem,
        retrieved_cards=_card_ids(cards),
        llm_model=diagnosis.model if want_llm_opinion else "server",
        llm_response=llm_response,
    )

    return {
        **llm_response,
        "session_id": session_id,
        "mws_aer_code": mws_doc.get("nbss_lup_aer_code"),
        "retrieval_aer_tags": _aer_tags_for_retrieval(mws_doc) or [],
        "pathway_retrieval_ranks": ranks,
        "signal_evaluation": summarize_evaluation_for_log(diagnosis.signal_evaluation or {}),
        "want_llm_opinion": want_llm_opinion,
        "llm_skipped": llm_skipped,
        **snapshot_fields(
            session_id,
            follow_up_count=follow_up_count,
            turn_no=turn_no,
            log_index=log_index,
        ),
    }


@router.post("/query")
def diagnosis_query(body: QueryRequest):
    request_started = time.perf_counter()
    try:
        _effective_retrieval_query(body.problem_description, want_llm_opinion=body.want_llm_opinion)
    except HTTPException as exc:
        _log_diagnosis_failure(
            event="diagnosis_query",
            turn_type="initial",
            failure_stage="validation",
            exc=exc,
            request_started=request_started,
            session_id=body.session_id,
            mws_uid=body.uid,
            problem_description=body.problem_description,
            retrieval_query=body.problem_description,
        )
        raise
    try:
        mws_doc = _load_mws(body.uid)
    except HTTPException as exc:
        _log_diagnosis_failure(
            event="diagnosis_query",
            turn_type="initial",
            failure_stage="load_mws",
            exc=exc,
            request_started=request_started,
            session_id=body.session_id,
            mws_uid=body.uid,
            problem_description=body.problem_description,
            retrieval_query=body.problem_description,
        )
        raise
    return _run_query(
        mws_doc,
        body.problem_description,
        body.session_id,
        tehsil_ref=_tehsil_ref_from_request(body),
        request_started=request_started,
        want_llm_opinion=body.want_llm_opinion,
    )


@router.post("/answer")
def diagnosis_answer(body: AnswerRequest):
    request_started = time.perf_counter()
    db = get_db()
    session = get_session(db, body.session_id)
    if not session:
        exc = HTTPException(status_code=404, detail=f"Session not found: {body.session_id}")
        _log_diagnosis_failure(
            event="diagnosis_follow_up",
            turn_type="follow_up",
            failure_stage="session",
            exc=exc,
            request_started=request_started,
            session_id=body.session_id,
            follow_up_variable=body.variable,
            follow_up_answer=body.answer,
        )
        raise exc

    try:
        mws_doc = _load_mws(session["mws_uid"])
    except HTTPException as exc:
        _log_diagnosis_failure(
            event="diagnosis_follow_up",
            turn_type="follow_up",
            failure_stage="load_mws",
            exc=exc,
            request_started=request_started,
            session_id=body.session_id,
            mws_uid=session.get("mws_uid"),
            follow_up_variable=body.variable,
            follow_up_answer=body.answer,
        )
        raise

    injected = dict(session.get("injected_variables") or {})
    session_tehsil_ref = session.get("tehsil_ref")

    first_turn = (session.get("turns") or [{}])[0]
    problem_description = first_turn.get("user_input") or ""
    frozen_card_ids = first_turn.get("retrieved_cards") or []
    if not frozen_card_ids:
        exc = HTTPException(status_code=400, detail="Session has no retrieved evidence cards to revise against")
        _log_diagnosis_failure(
            event="diagnosis_follow_up",
            turn_type="follow_up",
            failure_stage="validation",
            exc=exc,
            request_started=request_started,
            session_id=body.session_id,
            mws_doc=mws_doc,
            problem_description=problem_description,
            follow_up_variable=body.variable,
            follow_up_answer=body.answer,
            injected=injected,
        )
        raise exc

    cards = load_evidence_cards_by_ids(db, frozen_card_ids)
    if not cards:
        exc = HTTPException(status_code=502, detail="Failed to reload evidence cards for this session")
        _log_diagnosis_failure(
            event="diagnosis_follow_up",
            turn_type="follow_up",
            failure_stage="validation",
            exc=exc,
            request_started=request_started,
            session_id=body.session_id,
            mws_doc=mws_doc,
            problem_description=problem_description,
            follow_up_variable=body.variable,
            follow_up_answer=body.answer,
            injected=injected,
        )
        raise exc

    if body.choice_id:
        normalized_answer = normalized_answer_from_mcq_choice(cards, body.variable, body.choice_id)
        if not normalized_answer:
            exc = HTTPException(status_code=400, detail=f"Unknown MCQ choice for {body.variable}: {body.choice_id}")
            _log_diagnosis_failure(
                event="diagnosis_follow_up",
                turn_type="follow_up",
                failure_stage="validation",
                exc=exc,
                request_started=request_started,
                session_id=body.session_id,
                mws_doc=mws_doc,
                problem_description=problem_description,
                follow_up_variable=body.variable,
                follow_up_answer=body.choice_id,
                injected=injected,
            )
            raise exc
        answer_text = normalized_answer.get("raw", body.choice_id)
    elif str(body.answer or "").strip():
        exc = HTTPException(
            status_code=400,
            detail="Follow-up requires choice_id; free-text answer is no longer supported",
        )
        _log_diagnosis_failure(
            event="diagnosis_follow_up",
            turn_type="follow_up",
            failure_stage="validation",
            exc=exc,
            request_started=request_started,
            session_id=body.session_id,
            mws_doc=mws_doc,
            problem_description=problem_description,
            follow_up_variable=body.variable,
            follow_up_answer=body.answer,
            injected=injected,
        )
        raise exc
    else:
        exc = HTTPException(status_code=400, detail="Provide choice_id or answer for follow-up")
        _log_diagnosis_failure(
            event="diagnosis_follow_up",
            turn_type="follow_up",
            failure_stage="validation",
            exc=exc,
            request_started=request_started,
            session_id=body.session_id,
            mws_doc=mws_doc,
            problem_description=problem_description,
            follow_up_variable=body.variable,
            follow_up_answer=body.answer,
            injected=injected,
        )
        raise exc

    injected[body.variable] = normalized_answer

    retrieval = frozen_retrieval_result(cards)
    retrieval_query = f"{problem_description} | follow-up: {body.variable}={answer_text}"
    t0 = time.perf_counter()
    try:
        bundle = assemble_variable_bundle(mws_doc, cards, injected=injected)
    except Exception as exc:
        assemble_ms = (time.perf_counter() - t0) * 1000
        _log_diagnosis_failure(
            event="diagnosis_follow_up",
            turn_type="follow_up",
            failure_stage="assembly",
            exc=exc,
            request_started=request_started,
            session_id=body.session_id,
            mws_doc=mws_doc,
            problem_description=problem_description,
            retrieval_query=retrieval_query,
            cards=cards,
            injected=injected,
            retrieval=retrieval,
            assemble_ms=assemble_ms,
            follow_up_variable=body.variable,
            follow_up_answer=body.answer,
        )
        raise HTTPException(status_code=500, detail=f"Variable assembly failed: {exc}") from exc
    assemble_ms = (time.perf_counter() - t0) * 1000
    ranks = pathway_retrieval_ranks(cards)

    follow_up_context = f"{body.variable}: {answer_text}"
    if normalized_answer.get("present") is not None:
        follow_up_context += f" (present={normalized_answer['present']}"
        if normalized_answer.get("trend"):
            follow_up_context += f", trend={normalized_answer['trend']}"
        follow_up_context += ")"

    _injected, prior_asked_questions = _collect_prior_follow_up(session)
    prior_diagnosis = prior_diagnosis_from_session(session)
    want_llm_opinion = _resolve_want_llm_opinion(body.want_llm_opinion, session)
    set_session_want_llm_opinion(db, body.session_id, want_llm_opinion)
    llm_skipped = not want_llm_opinion

    llm_started = time.perf_counter()
    try:
        if want_llm_opinion:
            diagnosis = run_llm_reviewer_diagnosis(
                location=location_context(mws_doc, session_tehsil_ref),
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
        else:
            diagnosis = run_server_diagnosis(
                location=location_context(mws_doc, session_tehsil_ref),
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
        if llm_skipped:
            _log_diagnosis_failure(
                event="diagnosis_follow_up",
                turn_type="follow_up",
                failure_stage="validation",
                exc=exc,
                request_started=request_started,
                session_id=body.session_id,
                mws_doc=mws_doc,
                problem_description=problem_description,
                retrieval_query=retrieval_query,
                cards=cards,
                bundle=bundle,
                injected=injected,
                retrieval=retrieval,
                assemble_ms=assemble_ms,
                follow_up_variable=body.variable,
                follow_up_answer=body.answer,
            )
            raise HTTPException(status_code=500, detail=f"Server follow-up failed: {exc}") from exc
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
    llm_response = diagnosis.response
    signal_updates = llm_response.get("follow_up_signal_updates") or collect_follow_up_signal_updates(
        diagnosis.signal_evaluation or {},
        body.variable,
    )
    revision_ms = (time.perf_counter() - t1) * 1000
    llm_response = attach_follow_up_mcq(llm_response, bundle)

    total_ms = (time.perf_counter() - request_started) * 1000
    timings = {
        **retrieval.metrics.as_dict(),
        "assemble_bundle": round(assemble_ms, 2),
        **diagnosis.as_timing_dict(),
        "follow_up_revision": round(revision_ms, 2),
        "total": round(total_ms, 2),
    }

    follow_up_count, turn_no = turn_metrics_from_session(session, is_follow_up=True)

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
        follow_up_answer=answer_text,
        follow_up_choice_id=body.choice_id,
        follow_up_signal_updates=llm_response.get("follow_up_signal_updates") or signal_updates,
        want_llm_opinion=want_llm_opinion,
        llm_skipped=llm_skipped,
        follow_up_count=follow_up_count,
        turn_no=turn_no,
        diagnosis_snapshot_id=build_snapshot_id(body.session_id, follow_up_count),
        **_mws_trace_fields(mws_doc, session_tehsil_ref),
    )
    log_index = _emit_diagnosis_log(trace)

    append_turn(
        db,
        body.session_id,
        user_input=answer_text,
        retrieved_cards=_card_ids(cards),
        llm_model=diagnosis.model if want_llm_opinion else "server",
        llm_response=llm_response,
        injected_variable={body.variable: normalized_answer},
    )

    return {
        **llm_response,
        "session_id": body.session_id,
        "mws_aer_code": mws_doc.get("nbss_lup_aer_code"),
        "retrieval_aer_tags": _aer_tags_for_retrieval(mws_doc) or [],
        "pathway_retrieval_ranks": ranks,
        "signal_evaluation": summarize_evaluation_for_log(diagnosis.signal_evaluation or {}),
        "want_llm_opinion": want_llm_opinion,
        "llm_skipped": llm_skipped,
        **snapshot_fields(
            body.session_id,
            follow_up_count=follow_up_count,
            turn_no=turn_no,
            log_index=log_index,
        ),
    }
