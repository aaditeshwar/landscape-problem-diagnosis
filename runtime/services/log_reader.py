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
    "failure_stage",
    "follow_up_count",
    "turn_no",
    "diagnosis_snapshot_id",
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


def find_log_event(
    *,
    session_id: str,
    follow_up_count: int | None = None,
    log_index: int | None = None,
) -> dict[str, Any] | None:
    """Find a successful diagnosis log event for a session snapshot."""
    all_events = load_all_events(include_heavy=True)
    if log_index is not None:
        if 0 <= log_index < len(all_events):
            event = all_events[log_index]
            if event.get("session_id") == session_id and event.get("status", "ok") == "ok":
                out = dict(event)
                out["index"] = log_index
                out.pop("_index", None)
                return out
        return None

    matches: list[tuple[int, dict[str, Any]]] = []
    for idx, event in enumerate(all_events):
        if event.get("parse_error"):
            continue
        if event.get("session_id") != session_id:
            continue
        if event.get("status", "ok") != "ok":
            continue
        if follow_up_count is not None and event.get("follow_up_count") != follow_up_count:
            continue
        matches.append((idx, event))

    if not matches:
        return None
    idx, event = matches[-1]
    out = dict(event)
    out["index"] = idx
    out.pop("_index", None)
    return out


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


def _empirical_cdf(values: list[float]) -> list[dict[str, float]]:
    if not values:
        return []
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return [{"x": round(float(v), 2), "y": round((i + 1) / n, 4)} for i, v in enumerate(sorted_vals)]


def model_timing_cdfs(model: str) -> dict[str, Any]:
    """Empirical CDFs of prompt length and total time for query vs follow-up runs."""
    query_prompts: list[float] = []
    follow_prompts: list[float] = []
    query_times: list[float] = []
    follow_times: list[float] = []

    for row in load_all_events(include_heavy=False):
        if row.get("parse_error"):
            continue
        if str(row.get("model") or "") != model:
            continue
        event = row.get("event")
        if event not in ("diagnosis_query", "diagnosis_follow_up"):
            continue
        prompt_chars = row.get("prompt_chars")
        timings = row.get("timings_ms") or {}
        total_ms = timings.get("total")
        if not isinstance(prompt_chars, (int, float)) or prompt_chars <= 0:
            continue
        if not isinstance(total_ms, (int, float)) or total_ms <= 0:
            continue
        prompt_val = float(prompt_chars)
        time_val = float(total_ms)
        if event == "diagnosis_follow_up":
            follow_prompts.append(prompt_val)
            follow_times.append(time_val)
        else:
            query_prompts.append(prompt_val)
            query_times.append(time_val)

    return {
        "prompt_length": {
            "query": _empirical_cdf(query_prompts),
            "follow_up": _empirical_cdf(follow_prompts),
        },
        "total_time_ms": {
            "query": _empirical_cdf(query_times),
            "follow_up": _empirical_cdf(follow_times),
        },
        "counts": {
            "query": len(query_prompts),
            "follow_up": len(follow_prompts),
        },
    }


def dashboard_meta() -> dict[str, Any]:
    paths = log_paths()
    events = load_all_events(include_heavy=False)
    return {
        "paths": {key: str(path) for key, path in paths.items()},
        "files_exist": {key: path.is_file() for key, path in paths.items()},
        "startup_config": startup_config_snapshot(),
        "stats": aggregate_stats(events),
        "qwen_cdfs": model_timing_cdfs("qwen2.5:14b"),
    }
