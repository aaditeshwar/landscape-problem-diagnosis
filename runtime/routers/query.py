import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import OLLAMA_URL, LLM_PROVIDER
from db import get_db
from logging_setup import log_diagnosis_event
from services.assembler import assemble_variable_bundle, location_context
from services.diagnosis_revision import (
    apply_follow_up_revision,
    build_retrieval_query,
    normalize_qualitative_answer,
    prior_diagnosis_from_session,
)
from services.diagnosis_trace import DiagnosisRequestTrace
from services.llm_client import model_for_turn
from services.mws_enrich import enrich_mws_doc
from services.reasoner import _collect_prior_follow_up, run_diagnosis
from services.retriever import pathway_retrieval_ranks, retrieve_evidence_cards
from services.session_manager import append_turn, create_session, get_session

router = APIRouter(prefix="/api", tags=["diagnosis"])


def _llm_failure_hint() -> str:
    if LLM_PROVIDER == "anthropic":
        return "check ANTHROPIC_API_KEY and LLM_PROVIDER=anthropic"
    return f"is Ollama reachable at {OLLAMA_URL}?"


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

    try:
        diagnosis = run_diagnosis(
            location=location_context(mws_doc),
            problem_description=problem_description,
            bundle=bundle,
            injected_variables=injected or None,
            pathway_retrieval_ranks=ranks,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Diagnosis model failed — {_llm_failure_hint()}: {exc}") from exc

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
        mws_uid=str(mws_doc.get("uid")),
        turn_type="initial",
        model=diagnosis.model,
        retrieval_query=problem_description,
        problem_description=problem_description,
        retrieved_card_ids=_card_ids(cards),
        timings_ms=timings,
        prompt=diagnosis.prompt,
        prompt_profile=diagnosis.prompt_profile,
        llm_raw_response=diagnosis.raw_llm_text,
        llm_response=llm_response,
        follow_up_question=llm_response.get("follow_up_question"),
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
        "pathway_retrieval_ranks": ranks,
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
    retrieval_query = build_retrieval_query(problem_description, injected)
    try:
        retrieval = retrieve_evidence_cards(db, retrieval_query, mws_doc)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Embedding/retrieval failed — is Ollama reachable at {OLLAMA_URL}? ({exc})",
        ) from exc

    cards = retrieval.cards
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
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Follow-up diagnosis failed — {_llm_failure_hint()}: {exc}") from exc

    t1 = time.perf_counter()
    llm_response = apply_follow_up_revision(
        diagnosis.response,
        prior_diagnosis,
        answered_variable=body.variable,
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
        mws_uid=str(mws_doc.get("uid")),
        turn_type="follow_up",
        model=diagnosis.model,
        retrieval_query=retrieval_query,
        problem_description=problem_description,
        retrieved_card_ids=_card_ids(cards),
        timings_ms=timings,
        prompt=diagnosis.prompt,
        prompt_profile=diagnosis.prompt_profile,
        llm_raw_response=diagnosis.raw_llm_text,
        llm_response=llm_response,
        follow_up_question=llm_response.get("follow_up_question"),
        follow_up_variable=body.variable,
        follow_up_answer=body.answer,
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
        "pathway_retrieval_ranks": ranks,
        **llm_response,
    }
