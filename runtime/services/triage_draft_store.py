"""Persist triage signal/policy drafts before revise-cards promotion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import METADATA_DIR

DRAFTS_DIR = METADATA_DIR / "triage_drafts"


def _draft_path(card_id: str) -> Path:
    safe = str(card_id or "").strip().replace("/", "_")
    return DRAFTS_DIR / f"{safe}.json"


def load_draft(card_id: str) -> dict[str, Any] | None:
    path = _draft_path(card_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_draft(
    card_id: str,
    *,
    diagnostic_signals: list[dict[str, Any]],
    confirmation_policy: dict[str, Any] | None,
    section: dict[str, str] | None = None,
) -> dict[str, Any]:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "card_id": card_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_signals": diagnostic_signals,
        "confirmation_policy": confirmation_policy or {},
        "source": "triaging",
        "section": section or {},
    }
    path = _draft_path(card_id)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    tmp.replace(path)
    return payload


def apply_draft_to_card(card: dict[str, Any], draft: dict[str, Any] | None) -> dict[str, Any]:
    if not draft:
        return card
    out = dict(card)
    if draft.get("diagnostic_signals"):
        out["diagnostic_signals"] = draft["diagnostic_signals"]
    if draft.get("confirmation_policy"):
        out["confirmation_policy"] = draft["confirmation_policy"]
    return out
