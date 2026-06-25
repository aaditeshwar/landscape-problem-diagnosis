"""Unified JSON chat client for diagnosis (Ollama or Anthropic Claude)."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_FOLLOWUP_MODEL,
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_REASON_MODEL,
    ANTHROPIC_REVIEWER_MAX_TOKENS,
    LLM_PROVIDER,
    OLLAMA_FOLLOWUP_MODEL,
    OLLAMA_REASON_MODEL,
)
from services.ollama_client import chat_json as ollama_chat_json

_anthropic_client = None
_llm_provider_override: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_provider_override",
    default=None,
)


def effective_llm_provider() -> str:
    override = _llm_provider_override.get()
    if override in {"ollama", "anthropic"}:
        return override
    return LLM_PROVIDER


@contextmanager
def llm_provider_override(provider: str | None) -> Iterator[None]:
    """Temporarily override LLM_PROVIDER for in-process eval / batch runs."""
    token = _llm_provider_override.set(provider)
    try:
        yield
    finally:
        _llm_provider_override.reset(token)


@dataclass(frozen=True)
class LlmChatResult:
    text: str
    stop_reason: str | None = None
    max_tokens: int | None = None


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
    if effective_llm_provider() == "anthropic":
        return ANTHROPIC_FOLLOWUP_MODEL if follow_up else ANTHROPIC_REASON_MODEL
    return OLLAMA_FOLLOWUP_MODEL if follow_up else OLLAMA_REASON_MODEL


def _anthropic_chat_json(prompt: str, *, model: str, max_tokens: int) -> LlmChatResult:
    client = _get_anthropic_client()
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            return LlmChatResult(
                text=text,
                stop_reason=getattr(message, "stop_reason", None),
                max_tokens=max_tokens,
            )
    raise RuntimeError("Anthropic response contained no text block")


def chat_json_result(
    prompt: str,
    *,
    model: str | None = None,
    follow_up: bool = False,
    reviewer: bool = False,
) -> LlmChatResult:
    """Run a single-turn JSON diagnosis prompt and return raw model text + metadata."""
    if effective_llm_provider() == "anthropic":
        chosen = model or model_for_turn(follow_up=follow_up)
        token_limit = ANTHROPIC_REVIEWER_MAX_TOKENS if reviewer else ANTHROPIC_MAX_TOKENS
        return _anthropic_chat_json(prompt, model=chosen, max_tokens=token_limit)
    chosen = model or model_for_turn(follow_up=follow_up)
    return LlmChatResult(text=ollama_chat_json(prompt, model=chosen))


def chat_json(
    prompt: str,
    *,
    model: str | None = None,
    follow_up: bool = False,
    reviewer: bool = False,
) -> str:
    """Run a single-turn JSON diagnosis prompt and return raw model text."""
    return chat_json_result(
        prompt,
        model=model,
        follow_up=follow_up,
        reviewer=reviewer,
    ).text
