"""Unified JSON chat client for diagnosis (Ollama or Anthropic Claude)."""

from __future__ import annotations

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_FOLLOWUP_MODEL,
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_REASON_MODEL,
    LLM_PROVIDER,
    OLLAMA_FOLLOWUP_MODEL,
    OLLAMA_REASON_MODEL,
)
from services.ollama_client import chat_json as ollama_chat_json

_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (required when LLM_PROVIDER=anthropic)")
        from anthropic import Anthropic

        _anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def model_for_turn(*, follow_up: bool = False) -> str:
    """Return the model name recorded in session turns for this diagnosis step."""
    if LLM_PROVIDER == "anthropic":
        return ANTHROPIC_FOLLOWUP_MODEL if follow_up else ANTHROPIC_REASON_MODEL
    return OLLAMA_FOLLOWUP_MODEL if follow_up else OLLAMA_REASON_MODEL


def _anthropic_chat_json(prompt: str, *, model: str) -> str:
    client = _get_anthropic_client()
    message = client.messages.create(
        model=model,
        max_tokens=ANTHROPIC_MAX_TOKENS,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            return text
    raise RuntimeError("Anthropic response contained no text block")


def chat_json(prompt: str, *, model: str | None = None, follow_up: bool = False) -> str:
    """Run a single-turn JSON diagnosis prompt and return raw model text."""
    if LLM_PROVIDER == "anthropic":
        chosen = model or model_for_turn(follow_up=follow_up)
        return _anthropic_chat_json(prompt, model=chosen)
    chosen = model or model_for_turn(follow_up=follow_up)
    return ollama_chat_json(prompt, model=chosen)
