#!/usr/bin/env python3
"""Pack a log event into a claude replay result dict."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def pack_result(*, log_index: int, run_meta: dict, api_base: str = "http://127.0.0.1:8000") -> dict:
    log_event = httpx.get(f"{api_base.rstrip('/')}/api/logs/events/{log_index}", timeout=60).json()
    final = dict(log_event.get("llm_response") or {})
    final["session_id"] = log_event.get("session_id")
    if log_event.get("signal_evaluation") is not None:
        final["signal_evaluation"] = log_event.get("signal_evaluation")
    query = {
        "uid": log_event.get("mws_uid"),
        "problem_description": log_event.get("problem_description"),
        "state": log_event.get("state"),
        "district": log_event.get("district"),
        "tehsil": log_event.get("tehsil"),
    }
    return {
        "run_index": run_meta.get("run_index"),
        "baseline_source_session_id": run_meta.get("source_session_id"),
        "baseline_timestamp": run_meta.get("source_timestamp"),
        "query": query,
        "llm_configuration": run_meta.get("llm_configuration")
        or {
            "llm_provider": "anthropic",
            "reason_model": log_event.get("model"),
            "followup_model": log_event.get("model"),
            "max_tokens": 4096,
            "prompt_profile": log_event.get("prompt_profile"),
        },
        "request_elapsed_ms": (log_event.get("timings_ms") or {}).get("total"),
        "replay_session_id": log_event.get("session_id"),
        "prompt": log_event.get("prompt"),
        "llm_raw_response": log_event.get("llm_raw_response"),
        "llm_response": log_event.get("llm_response"),
        "final_response": final,
        "log_event_index": log_event.get("index", log_index),
        "log_timestamp": log_event.get("timestamp"),
        "capture_note": run_meta.get("capture_note"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-index", type=int, required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--run-index", type=int, required=True)
    parser.add_argument("--output", help="Output JSON path (required unless --append-to)")
    parser.add_argument("--append-to")
    parser.add_argument("--capture-note")
    args = parser.parse_args()
    if not args.output and not args.append_to:
        parser.error("one of --output or --append-to is required")

    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    run_meta = next(r for r in baseline["runs"] if r["run_index"] == args.run_index)
    if args.capture_note:
        run_meta = dict(run_meta)
        run_meta["capture_note"] = args.capture_note
        run_meta["query"] = {
            "uid": run_meta["query"]["uid"],
            "problem_description": run_meta["query"]["problem_description"],
            "state": run_meta["query"].get("state"),
            "district": run_meta["query"].get("district"),
            "tehsil": run_meta["query"].get("tehsil"),
        }

    result = pack_result(log_index=args.log_index, run_meta=run_meta)

    if args.append_to:
        out_path = Path(args.append_to)
        payload = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {
            "replayed_at": datetime.now(timezone.utc).isoformat(),
            "baseline_file": str(Path(args.baseline).resolve()),
            "api_base": "http://127.0.0.1:8000",
            "llm_provider_env": "anthropic",
            "results": [],
        }
        results = [r for r in payload.get("results", []) if r.get("run_index") != args.run_index]
        results.append(result)
        results.sort(key=lambda r: r.get("run_index", 0))
        payload["results"] = results
        payload["run_count"] = len(results)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    else:
        out_path = Path(args.output)
        payload = {
            "replayed_at": datetime.now(timezone.utc).isoformat(),
            "baseline_file": str(Path(args.baseline).resolve()),
            "api_base": "http://127.0.0.1:8000",
            "llm_provider_env": "anthropic",
            "run_count": 1,
            "results": [result],
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
