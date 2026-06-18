#!/usr/bin/env python3
"""Extract successful diagnosis runs from logs and replay them via FastAPI."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from config import (  # noqa: E402
    ANTHROPIC_FOLLOWUP_MODEL,
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_REASON_MODEL,
    LLM_PROVIDER,
    LOG_DIR,
    OLLAMA_FOLLOWUP_MODEL,
    OLLAMA_NUM_PREDICT,
    OLLAMA_REASON_MODEL,
    OLLAMA_URL,
)
from logging_setup import startup_config_snapshot  # noqa: E402


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _resolve_log_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    candidates = [
        ROOT / "runtime" / "logs" / "diagnosis.jsonl",
        Path(LOG_DIR) / "diagnosis.jsonl",
        ROOT / "logs" / "diagnosis.jsonl",
    ]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return candidates[0]
    return max(existing, key=lambda path: path.stat().st_size)


def _llm_config_from_env(provider: str | None = None) -> dict[str, Any]:
    provider = provider or LLM_PROVIDER
    base = startup_config_snapshot()
    if provider == "anthropic":
        return {
            "llm_provider": "anthropic",
            "reason_model": ANTHROPIC_REASON_MODEL,
            "followup_model": ANTHROPIC_FOLLOWUP_MODEL,
            "max_tokens": ANTHROPIC_MAX_TOKENS,
        }
    return {
        "llm_provider": "ollama",
        "reason_model": OLLAMA_REASON_MODEL,
        "followup_model": OLLAMA_FOLLOWUP_MODEL,
        "ollama_url": OLLAMA_URL,
        "num_predict": OLLAMA_NUM_PREDICT,
        "runtime_log_snapshot": base,
    }


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            events.append(json.loads(text))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON on line {line_no} of {path}") from exc
    return events


def extract_runs(
    *,
    log_path: Path,
    start_session_id: str,
    output_dir: Path,
) -> Path:
    events = _load_events(log_path)
    start_idx = next(
        (i for i, event in enumerate(events) if event.get("session_id") == start_session_id),
        None,
    )
    if start_idx is None:
        raise RuntimeError(f"Session {start_session_id} not found in {log_path}")

    selected = [
        event
        for event in events[start_idx:]
        if event.get("status") == "ok" and event.get("event") == "diagnosis_query"
    ]
    runs = []
    for idx, event in enumerate(selected, start=1):
        runs.append(
            {
                "run_index": idx,
                "source_log_index": events.index(event),
                "source_session_id": event.get("session_id"),
                "source_timestamp": event.get("timestamp"),
                "query": {
                    "uid": event.get("mws_uid"),
                    "problem_description": event.get("problem_description"),
                    "state": event.get("state"),
                    "district": event.get("district"),
                    "tehsil": event.get("tehsil"),
                    "want_llm_opinion": bool(event.get("want_llm_opinion")),
                },
                "llm_configuration": {
                    "model": event.get("model"),
                    "prompt_profile": event.get("prompt_profile"),
                    **_llm_config_from_env(
                        "ollama" if event.get("prompt_profile") == "ollama" else LLM_PROVIDER
                    ),
                },
                "timings_ms": event.get("timings_ms"),
                "retrieval_query": event.get("retrieval_query"),
                "retrieved_card_ids": event.get("retrieved_card_ids"),
                "prompt": event.get("prompt"),
                "llm_raw_response": event.get("llm_raw_response"),
                "llm_response": event.get("llm_response"),
                "final_response": event.get("llm_response"),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"ollama_baseline_from_{start_session_id}_{_utc_stamp()}.json"
    payload = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "source_log": str(log_path.resolve()),
        "start_session_id": start_session_id,
        "start_log_index": start_idx,
        "run_count": len(runs),
        "runs": runs,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _event_count_from_meta(meta: dict[str, Any]) -> int:
    stats = meta.get("stats") or {}
    count = stats.get("count")
    if isinstance(count, int):
        return count
    legacy = meta.get("event_count")
    if isinstance(legacy, int):
        return legacy
    return 0


def _fetch_log_event(api_base: str, index: int) -> dict[str, Any] | None:
    if index < 0:
        return None
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{api_base.rstrip('/')}/api/logs/events/{index}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


def replay_runs(
    *,
    baseline_path: Path,
    api_base: str,
    output_dir: Path,
    dry_run: bool = False,
    limit: int | None = None,
    want_llm_opinion: bool | None = None,
) -> Path:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    runs = baseline.get("runs") or []
    if dry_run:
        runs = runs[:1]
    elif limit is not None:
        runs = runs[:limit]

    with httpx.Client(timeout=600.0) as client:
        health = client.get(f"{api_base.rstrip('/')}/api/health")
        health.raise_for_status()
        meta = client.get(f"{api_base.rstrip('/')}/api/logs/meta")
        meta.raise_for_status()
        events_before = _event_count_from_meta(meta.json())

        results: list[dict[str, Any]] = []
        for run in runs:
            query = run["query"]
            effective_want_llm = (
                want_llm_opinion
                if want_llm_opinion is not None
                else bool(query.get("want_llm_opinion"))
            )
            body = {
                "uid": query["uid"],
                "problem_description": query["problem_description"],
                "state": query.get("state"),
                "district": query.get("district"),
                "tehsil": query.get("tehsil"),
                "want_llm_opinion": effective_want_llm,
            }
            started = time.perf_counter()
            response = client.post(f"{api_base.rstrip('/')}/api/query", json=body)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            response.raise_for_status()
            final_response = response.json()

            meta_after = client.get(f"{api_base.rstrip('/')}/api/logs/meta").json()
            log_index = _event_count_from_meta(meta_after) - 1
            log_event = _fetch_log_event(api_base, log_index)

            results.append(
                {
                    "run_index": run.get("run_index"),
                    "baseline_source_session_id": run.get("source_session_id"),
                    "baseline_timestamp": run.get("source_timestamp"),
                    "query": body,
                    "llm_configuration": _llm_config_from_env(),
                    "request_elapsed_ms": elapsed_ms,
                    "replay_session_id": final_response.get("session_id"),
                    "prompt": log_event.get("prompt") if log_event else None,
                    "llm_raw_response": log_event.get("llm_raw_response") if log_event else None,
                    "llm_response": log_event.get("llm_response") if log_event else None,
                    "final_response": final_response,
                    "log_event_index": log_event.get("index") if log_event else None,
                    "log_timestamp": log_event.get("timestamp") if log_event else None,
                }
            )
            print(
                f"Replayed run {run.get('run_index')}/{len(runs)} "
                f"session={final_response.get('session_id')} elapsed_ms={elapsed_ms}"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "dry_run" if dry_run else "full"
    out_path = output_dir / f"claude_replay_{suffix}_{_utc_stamp()}.json"
    payload = {
        "replayed_at": datetime.now(timezone.utc).isoformat(),
        "baseline_file": str(baseline_path.resolve()),
        "api_base": api_base,
        "llm_provider_env": os.getenv("LLM_PROVIDER"),
        "llm_configuration": _llm_config_from_env(),
        "dry_run": dry_run,
        "want_llm_opinion_override": want_llm_opinion,
        "run_count": len(results),
        "results": results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract and replay diagnosis runs")
    sub = parser.add_subparsers(dest="command", required=True)

    extract_parser = sub.add_parser("extract", help="Extract baseline runs from diagnosis.jsonl")
    extract_parser.add_argument(
        "--start-session",
        default="session_21aa4a9655f3",
        help="First session id in log order (inclusive)",
    )
    extract_parser.add_argument("--log-path", help="Path to diagnosis.jsonl")
    extract_parser.add_argument(
        "--output-dir",
        default=str(ROOT / "data" / "runs"),
        help="Directory for extracted JSON",
    )

    replay_parser = sub.add_parser("replay", help="Replay baseline runs through FastAPI")
    replay_parser.add_argument("baseline", help="Baseline JSON from extract")
    replay_parser.add_argument(
        "--api-base",
        default=os.getenv("DIAGNOSIS_API_BASE", "http://127.0.0.1:8000"),
        help="FastAPI base URL",
    )
    replay_parser.add_argument(
        "--output-dir",
        default=str(ROOT / "data" / "runs"),
        help="Directory for replay JSON",
    )
    replay_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Replay only the first baseline run",
    )
    replay_parser.add_argument("--limit", type=int, help="Replay only the first N runs")
    replay_parser.add_argument(
        "--want-llm-opinion",
        action="store_true",
        help="Force want_llm_opinion=true on replay requests",
    )
    replay_parser.add_argument(
        "--no-want-llm-opinion",
        action="store_true",
        help="Force want_llm_opinion=false (server-only replay)",
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    if args.command == "extract":
        out = extract_runs(
            log_path=_resolve_log_path(getattr(args, "log_path", None)),
            start_session_id=args.start_session,
            output_dir=output_dir,
        )
        print(out)
        return 0

    want_llm: bool | None = None
    if getattr(args, "want_llm_opinion", False):
        want_llm = True
    elif getattr(args, "no_want_llm_opinion", False):
        want_llm = False

    out = replay_runs(
        baseline_path=Path(args.baseline),
        api_base=args.api_base,
        output_dir=output_dir,
        dry_run=args.dry_run,
        limit=args.limit,
        want_llm_opinion=want_llm,
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
