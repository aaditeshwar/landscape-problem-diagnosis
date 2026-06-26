"""Shared helpers for query-bank evaluation batches."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = ROOT / "runtime"
SCRIPTS_DIR = ROOT / "scripts"
for path in (RUNTIME_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

EVAL_MODES = ("server", "llm_ollama", "server_plus_llm_ollama", "llm_claude")


def feedback_url(frontend_base: str, diagnosis: dict[str, Any]) -> str:
    snapshot_id = str(diagnosis.get("diagnosis_snapshot_id") or "").strip()
    if not snapshot_id:
        return ""
    params: dict[str, str] = {"snapshot_id": snapshot_id}
    log_index = diagnosis.get("log_index")
    if isinstance(log_index, int) and log_index >= 0:
        params["log_index"] = str(log_index)
    # frontend_base must include any Apache subpath (e.g. http://host/core-insights)
    base = frontend_base.rstrip("/")
    return f"{base}/feedback?{urlencode(params)}"


def diagnostics_url(frontend_base: str, mws_id: str) -> str:
    base = frontend_base.rstrip("/")
    return f"{base}/diagnose?uid={quote(mws_id, safe='')}"


def session_ref(diagnosis: dict[str, Any], frontend_base: str) -> dict[str, Any]:
    return {
        "session_id": str(diagnosis.get("session_id") or ""),
        "diagnosis_snapshot_id": str(diagnosis.get("diagnosis_snapshot_id") or ""),
        "log_index": diagnosis.get("log_index"),
        "feedback_url": feedback_url(frontend_base, diagnosis),
        "llm_model": diagnosis.get("llm_model") or diagnosis.get("model"),
        "want_llm_opinion": bool(diagnosis.get("want_llm_opinion")),
        "llm_skipped": bool(diagnosis.get("llm_skipped")),
    }


def load_response_artifact(batch_id: str, filename: str) -> dict[str, Any] | None:
    from services.query_eval_store import batch_dir

    path = batch_dir(batch_id) / "responses" / filename
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def load_evaluation_artifact(batch_id: str, filename: str) -> dict[str, Any] | None:
    from services.query_eval_store import batch_dir

    path = batch_dir(batch_id) / "evaluations" / filename
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def response_artifact_name(case_study_id: int | str, query_id: str | None, mode: str | None) -> str:
    cs = f"cs{case_study_id}"
    if mode == "server" and not query_id:
        return f"{cs}__server.json"
    if query_id and mode:
        return f"{cs}__{query_id}__{mode}.json"
    raise ValueError("Invalid artifact name parameters")


def evaluation_artifact_name(case_study_id: int | str, query_id: str, mode: str) -> str:
    return f"cs{case_study_id}__{query_id}__{mode}.json"
