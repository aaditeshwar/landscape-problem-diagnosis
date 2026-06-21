"""Structured trace objects for diagnosis request logging."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievalMetrics:
    embed_ms: float
    search_ms: float
    citations_ms: float

    @property
    def total_ms(self) -> float:
        return self.embed_ms + self.search_ms + self.citations_ms

    def as_dict(self) -> dict[str, float]:
        return {
            "embed": round(self.embed_ms, 2),
            "evidence_search": round(self.search_ms, 2),
            "citations": round(self.citations_ms, 2),
            "retrieval_total": round(self.total_ms, 2),
        }


@dataclass(frozen=True)
class RetrievalResult:
    cards: list[dict]
    metrics: RetrievalMetrics


@dataclass
class DiagnosisRun:
    response: dict[str, Any]
    prompt: str
    raw_llm_text: str
    model: str
    llm_ms: float
    postprocess_ms: float
    prompt_profile: str = "ollama"
    signal_evaluation: dict[str, dict[str, Any]] | None = None

    def as_timing_dict(self) -> dict[str, float]:
        return {
            "llm": round(self.llm_ms, 2),
            "postprocess": round(self.postprocess_ms, 2),
        }


@dataclass
class DiagnosisRequestTrace:
    event: str
    session_id: str
    mws_uid: str
    turn_type: str
    model: str
    retrieval_query: str
    retrieved_card_ids: list[str]
    timings_ms: dict[str, float] = field(default_factory=dict)
    prompt: str = ""
    prompt_profile: str = ""
    llm_raw_response: str = ""
    llm_response: dict[str, Any] = field(default_factory=dict)
    follow_up_question: str | None = None
    follow_up_variable: str | None = None
    follow_up_answer: str | None = None
    follow_up_choice_id: str | None = None
    problem_description: str | None = None
    state: str | None = None
    district: str | None = None
    tehsil: str | None = None
    mws_aer_code: str | None = None
    pathway_evidence: list[dict[str, Any]] = field(default_factory=list)
    signal_evaluation: dict[str, Any] = field(default_factory=dict)
    follow_up_signal_updates: list[dict[str, Any]] = field(default_factory=list)
    want_llm_opinion: bool = False
    llm_skipped: bool = False
    skipped_production_systems: list[dict[str, Any]] = field(default_factory=list)
    follow_up_count: int = 0
    turn_no: int | None = None
    log_index: int | None = None
    diagnosis_snapshot_id: str | None = None
    status: str = "ok"
    error: str | None = None
    failure_stage: str | None = None

    def to_log_event(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["prompt_chars"] = len(self.prompt)
        payload["llm_raw_chars"] = len(self.llm_raw_response)
        return payload
