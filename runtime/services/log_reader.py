"""Read diagnosis JSONL logs for the dashboard API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import LOG_DIR
from logging_setup import startup_config_snapshot

SUMMARY_FIELDS = (
    "timestamp",
    "event",
    "session_id",
    "mws_uid",
    "tehsil",
    "district",
    "state",
    "turn_type",
    "model",
    "timings_ms",
    "prompt_chars",
    "llm_raw_chars",
    "follow_up_question",
    "follow_up_variable",
    "follow_up_answer",
    "retrieval_query",
    "problem_description",
    "retrieved_card_ids",
    "mws_aer_code",
    "status",
    "error",
)

HEAVY_FIELDS = frozenset({"prompt", "llm_raw_response", "llm_response"})


def log_paths() -> dict[str, Path]:
    root = Path(LOG_DIR)
    return {
        "log_dir": root.resolve(),
        "diagnosis_jsonl": (root / "diagnosis.jsonl").resolve(),
        "diagnosis_log": (root / "diagnosis.log").resolve(),
        "server_log": (root / "server.log").resolve(),
    }


def _jsonl_path() -> Path:
    return log_paths()["diagnosis_jsonl"]


def load_all_events(*, include_heavy: bool = False) -> list[dict[str, Any]]:
    path = _jsonl_path()
    if not path.is_file():
        return []

    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                event = {"parse_error": True, "line_no": line_no, "raw": text[:500]}
            event["_index"] = len(events)
            if not include_heavy:
                for key in HEAVY_FIELDS:
                    event.pop(key, None)
            events.append(event)
    return events


def event_summary(event: dict[str, Any], index: int) -> dict[str, Any]:
    summary = {"index": index}
    for key in SUMMARY_FIELDS:
        if key in event:
            summary[key] = event[key]
    if event.get("parse_error"):
        summary["parse_error"] = True
        summary["line_no"] = event.get("line_no")
    return summary


def list_events(*, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    all_events = load_all_events(include_heavy=False)
    total = len(all_events)
    # Newest first
    ordered = list(reversed(all_events))
    page = ordered[offset : offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "events": [event_summary(item, int(item.get("_index", 0))) for item in page],
    }


def get_event(index: int) -> dict[str, Any] | None:
    all_events = load_all_events(include_heavy=True)
    if index < 0 or index >= len(all_events):
        return None
    event = dict(all_events[index])
    event["index"] = index
    event.pop("_index", None)
    return event


def aggregate_stats(events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = events if events is not None else load_all_events(include_heavy=False)
    if not rows:
        return {
            "count": 0,
            "avg_total_ms": None,
            "avg_llm_ms": None,
            "by_event": {},
        }

    totals: list[float] = []
    llm_times: list[float] = []
    by_event: dict[str, int] = {}
    for row in rows:
        if row.get("parse_error"):
            continue
        event_name = str(row.get("event") or "unknown")
        by_event[event_name] = by_event.get(event_name, 0) + 1
        timings = row.get("timings_ms") or {}
        if isinstance(timings.get("total"), (int, float)):
            totals.append(float(timings["total"]))
        if isinstance(timings.get("llm"), (int, float)):
            llm_times.append(float(timings["llm"]))

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    return {
        "count": len([r for r in rows if not r.get("parse_error")]),
        "avg_total_ms": _avg(totals),
        "avg_llm_ms": _avg(llm_times),
        "by_event": by_event,
    }


def dashboard_meta() -> dict[str, Any]:
    paths = log_paths()
    events = load_all_events(include_heavy=False)
    return {
        "paths": {key: str(path) for key, path in paths.items()},
        "files_exist": {key: path.is_file() for key, path in paths.items()},
        "startup_config": startup_config_snapshot(),
        "stats": aggregate_stats(events),
    }
