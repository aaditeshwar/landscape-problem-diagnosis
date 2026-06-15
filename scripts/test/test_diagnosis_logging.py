#!/usr/bin/env python3
"""Tests for diagnosis failure logging fields."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.diagnosis_trace import DiagnosisRequestTrace  # noqa: E402


def test_diagnosis_trace_serializes_failure_stage():
    trace = DiagnosisRequestTrace(
        event="diagnosis_query",
        session_id="s1",
        mws_uid="15_33759",
        turn_type="initial",
        model="test-model",
        retrieval_query="water stress",
        retrieved_card_ids=[],
        status="failed",
        failure_stage="assembly",
        error="Variable assembly failed: boom",
    )
    payload = trace.to_log_event()
    assert payload["status"] == "failed"
    assert payload["failure_stage"] == "assembly"
    assert payload["error"] == "Variable assembly failed: boom"


def test_failure_stages_cover_pipeline():
    stages = {"load_mws", "session", "retrieval", "assembly", "validation", "llm"}
    for stage in stages:
        trace = DiagnosisRequestTrace(
            event="diagnosis_query",
            session_id="s1",
            mws_uid="15_33759",
            turn_type="initial",
            model="test-model",
            retrieval_query="q",
            retrieved_card_ids=[],
            status="failed",
            failure_stage=stage,
            error=f"{stage} failed",
        )
        assert trace.to_log_event()["failure_stage"] == stage
