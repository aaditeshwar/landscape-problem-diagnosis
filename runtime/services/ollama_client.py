from __future__ import annotations

import httpx

from config import (
    EMBED_CHAR_LIMIT,
    OLLAMA_CHAT_TIMEOUT,
    OLLAMA_EMBED_MODEL,
    OLLAMA_FOLLOWUP_MODEL,
    OLLAMA_REASON_MODEL,
    OLLAMA_URL,
)


def embed_text(text: str, *, client: httpx.Client | None = None) -> list[float]:
    payload = {"model": OLLAMA_EMBED_MODEL, "prompt": text[:EMBED_CHAR_LIMIT]}
    if client is None:
        with httpx.Client(timeout=120.0) as c:
            r = c.post(f"{OLLAMA_URL}/api/embeddings", json=payload)
            r.raise_for_status()
            return r.json()["embedding"]
    r = client.post(f"{OLLAMA_URL}/api/embeddings", json=payload)
    r.raise_for_status()
    return r.json()["embedding"]


def chat_json(
    prompt: str,
    *,
    model: str | None = None,
    client: httpx.Client | None = None,
) -> str:
    chosen = model or OLLAMA_REASON_MODEL
    payload = {
        "model": chosen,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }
    if client is None:
        with httpx.Client(timeout=OLLAMA_CHAT_TIMEOUT) as c:
            r = c.post(f"{OLLAMA_URL}/api/generate", json=payload)
            r.raise_for_status()
            return r.json()["response"]
    r = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
    r.raise_for_status()
    return r.json()["response"]


def reason_model() -> str:
    return OLLAMA_REASON_MODEL


def followup_model() -> str:
    return OLLAMA_FOLLOWUP_MODEL
