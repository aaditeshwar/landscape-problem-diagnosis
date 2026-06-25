"""Persist query-bank evaluation batches for the /review app."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import ROOT

EVAL_DIR = ROOT / "reports" / "query_eval"
BATCH_PREFIX = "query_eval__"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_batch_id(batch_id: str) -> str:
    text = str(batch_id or "").strip()
    if not text.startswith(BATCH_PREFIX):
        raise ValueError(f"Invalid batch id: {batch_id}")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", text):
        raise ValueError(f"Invalid batch id: {batch_id}")
    return text


def batch_dir(batch_id: str) -> Path:
    return EVAL_DIR / _safe_batch_id(batch_id)


def batch_manifest_path(batch_id: str) -> Path:
    return batch_dir(batch_id) / "manifest.json"


def list_batches() -> list[dict[str, Any]]:
    if not EVAL_DIR.is_dir():
        return []
    batches: list[dict[str, Any]] = []
    for path in sorted(EVAL_DIR.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(manifest, dict):
            batches.append(manifest)
    return batches


def load_batch(batch_id: str) -> dict[str, Any]:
    path = batch_manifest_path(batch_id)
    if not path.is_file():
        raise FileNotFoundError(f"Query eval batch not found: {batch_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid manifest for batch: {batch_id}")
    return data


def save_batch(manifest: dict[str, Any]) -> dict[str, Any]:
    batch_id = str(manifest.get("batch_id") or "").strip()
    if not batch_id:
        raise ValueError("manifest.batch_id is required")
    out_dir = batch_dir(batch_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "responses").mkdir(exist_ok=True)
    (out_dir / "evaluations").mkdir(exist_ok=True)
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path = batch_manifest_path(batch_id)
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(manifest_path)
    return manifest


def write_response_artifact(batch_id: str, filename: str, payload: dict[str, Any]) -> Path:
    out = batch_dir(batch_id) / "responses" / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def write_evaluation_artifact(batch_id: str, filename: str, payload: dict[str, Any]) -> Path:
    out = batch_dir(batch_id) / "evaluations" / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def new_batch_id(label: str = "run") -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", label.strip())[:48] or "run"
    return f"{BATCH_PREFIX}{slug}_{_utc_stamp()}"
