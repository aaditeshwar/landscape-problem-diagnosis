"""File logging for the FastAPI runtime (server + structured diagnosis events)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from config import (
    ANTHROPIC_FOLLOWUP_MODEL,
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_MODEL,
    ANTHROPIC_REASON_MODEL,
    CORS_ORIGINS,
    DB_NAME,
    EMBED_CHAR_LIMIT,
    LLM_PROVIDER,
    LOG_DIR,
    LOG_LEVEL,
    MONGO_URI,
    OLLAMA_CHAT_TIMEOUT,
    OLLAMA_EMBED_MODEL,
    OLLAMA_FOLLOWUP_MODEL,
    OLLAMA_REASON_MODEL,
    OLLAMA_URL,
)
from services.retriever import CANDIDATE_POOL, DEFAULT_LIMIT

_CONFIGURED = False
_DIAGNOSIS_LOG_PATH: Path | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_mongo_uri(uri: str) -> str:
    try:
        parsed = urlparse(uri)
    except Exception:
        return "<invalid-uri>"
    if parsed.password:
        netloc = parsed.hostname or ""
        if parsed.username:
            netloc = f"{parsed.username}:***@{netloc}"
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        parsed = parsed._replace(netloc=netloc)
    return urlunparse(parsed)


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _attach_handler(logger: logging.Logger, handler: logging.Handler) -> None:
    handler.setFormatter(_make_formatter())
    logger.addHandler(handler)
    logger.propagate = False


def configure_logging() -> Path:
    """Configure server and diagnosis log files. Safe to call multiple times."""
    global _CONFIGURED, _DIAGNOSIS_LOG_PATH

    log_dir = Path(LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    if _CONFIGURED:
        return log_dir

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    formatter = _make_formatter()

    server_handler = RotatingFileHandler(
        log_dir / "server.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    server_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(server_handler)
    root.addHandler(console_handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        named = logging.getLogger(name)
        named.handlers.clear()
        named.setLevel(level)
        _attach_handler(named, server_handler)
        _attach_handler(named, console_handler)

    diagnosis_logger = logging.getLogger("diagnosis")
    diagnosis_logger.handlers.clear()
    diagnosis_logger.setLevel(level)
    diagnosis_text_handler = RotatingFileHandler(
        log_dir / "diagnosis.log",
        maxBytes=20 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    diagnosis_text_handler.setFormatter(formatter)
    _attach_handler(diagnosis_logger, diagnosis_text_handler)
    _attach_handler(diagnosis_logger, console_handler)

    _DIAGNOSIS_LOG_PATH = log_dir / "diagnosis.jsonl"
    _CONFIGURED = True
    return log_dir


def startup_config_snapshot() -> dict[str, Any]:
    """Non-secret runtime configuration for startup logging."""
    if LLM_PROVIDER == "anthropic":
        active_reason_model = ANTHROPIC_REASON_MODEL
        active_followup_model = ANTHROPIC_FOLLOWUP_MODEL
    else:
        active_reason_model = OLLAMA_REASON_MODEL
        active_followup_model = OLLAMA_FOLLOWUP_MODEL

    return {
        "timestamp": _utc_now_iso(),
        "llm_provider": LLM_PROVIDER,
        "active_reason_model": active_reason_model,
        "active_followup_model": active_followup_model,
        "anthropic_model_default": ANTHROPIC_MODEL,
        "anthropic_reason_model": ANTHROPIC_REASON_MODEL,
        "anthropic_followup_model": ANTHROPIC_FOLLOWUP_MODEL,
        "anthropic_max_tokens": ANTHROPIC_MAX_TOKENS,
        "ollama_url": OLLAMA_URL,
        "ollama_chat_timeout_s": OLLAMA_CHAT_TIMEOUT,
        "ollama_embed_model": OLLAMA_EMBED_MODEL,
        "ollama_reason_model": OLLAMA_REASON_MODEL,
        "ollama_followup_model": OLLAMA_FOLLOWUP_MODEL,
        "embed_char_limit": EMBED_CHAR_LIMIT,
        "retrieval_candidate_pool": CANDIDATE_POOL,
        "retrieval_default_limit": DEFAULT_LIMIT,
        "mongo_uri": _redact_mongo_uri(MONGO_URI),
        "mongo_db": DB_NAME,
        "cors_origins": CORS_ORIGINS,
        "log_dir": str(Path(LOG_DIR).resolve()),
        "log_level": LOG_LEVEL,
    }


def log_startup_config() -> None:
    log = logging.getLogger("runtime")
    snapshot = startup_config_snapshot()
    log.info("Runtime configuration: %s", json.dumps(snapshot, ensure_ascii=False))
    log.info("Diagnosis structured log: %s", _DIAGNOSIS_LOG_PATH)


def log_diagnosis_event(event: dict[str, Any]) -> int:
    """Append one structured diagnosis event to diagnosis.jsonl and log a summary.

    Returns the zero-based index of the new event in diagnosis.jsonl.
    """
    payload = {"timestamp": _utc_now_iso(), **event}
    log_dir = configure_logging()
    jsonl_path = _DIAGNOSIS_LOG_PATH or (log_dir / "diagnosis.jsonl")
    log_index = 0
    if jsonl_path.is_file():
        with jsonl_path.open(encoding="utf-8") as handle:
            log_index = sum(1 for line in handle if line.strip())
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str))
        handle.write("\n")

    timings = payload.get("timings_ms") or {}
    total_ms = timings.get("total")
    summary = (
        f"event={payload.get('event')} session={payload.get('session_id')} "
        f"mws={payload.get('mws_uid')} model={payload.get('model')} "
        f"status={payload.get('status', 'ok')} total_ms={total_ms}"
    )
    if payload.get("error"):
        summary += f" error={str(payload.get('error'))[:160]}"
    logging.getLogger("diagnosis").info(summary)
    return log_index
