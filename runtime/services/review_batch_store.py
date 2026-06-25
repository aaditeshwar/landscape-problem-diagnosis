"""Batch-scoped revise-cards state (decisions, card status, user edits)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import METADATA_DIR, ROOT

DECISIONS_PATH = METADATA_DIR / "claude_review_decisions.json"
USER_CARD_EDITS_PATH = METADATA_DIR / "claude_review_user_card_edits.json"

BATCH_SCHEMA_VERSION = 2


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    import json

    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else dict(default)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _default_claude_batch_id() -> str:
    from services.claude_review_store import batch_id_from_manifest, load_manifest

    return batch_id_from_manifest(load_manifest())


def _migrate_decisions_doc(doc: dict[str, Any]) -> dict[str, Any]:
    if doc.get("schema_version", 1) >= BATCH_SCHEMA_VERSION and isinstance(doc.get("batches"), dict):
        return doc

    claude_batch = _default_claude_batch_id()
    batches: dict[str, Any] = {}
    flat_decisions = doc.get("decisions") if isinstance(doc.get("decisions"), dict) else {}
    flat_status = doc.get("card_status") if isinstance(doc.get("card_status"), dict) else {}

    claude_decisions = dict(flat_decisions)
    claude_status: dict[str, Any] = {}
    for card_id, entry in flat_status.items():
        if not isinstance(entry, dict):
            continue
        batch_id = str(entry.get("batch_id") or "")
        if entry.get("source") == "triaging" and batch_id.startswith("triage__"):
            state = batches.setdefault(
                batch_id,
                {"decisions": {}, "card_status": {}},
            )
            state["card_status"][card_id] = entry
        else:
            claude_status[card_id] = entry

    if claude_decisions or claude_status:
        batches.setdefault(
            claude_batch,
            {"decisions": claude_decisions, "card_status": claude_status},
        )

    return {"schema_version": BATCH_SCHEMA_VERSION, "batches": batches}


def _migrate_user_edits_doc(doc: dict[str, Any]) -> dict[str, Any]:
    if doc.get("schema_version", 1) >= BATCH_SCHEMA_VERSION and isinstance(doc.get("batches"), dict):
        return doc

    claude_batch = _default_claude_batch_id()
    batches: dict[str, Any] = {}
    flat_edits = doc.get("edits") if isinstance(doc.get("edits"), dict) else {}

    claude_edits: dict[str, Any] = {}
    for card_id, entry in flat_edits.items():
        if not isinstance(entry, dict):
            continue
        source_batch = str(entry.get("source_batch_id") or "")
        if source_batch.startswith("triage__"):
            batch_edits = batches.setdefault(source_batch, {"edits": {}})
            batch_edits["edits"][card_id] = entry
        else:
            claude_edits[card_id] = entry

    if claude_edits:
        batches.setdefault(claude_batch, {"edits": claude_edits})

    return {"schema_version": BATCH_SCHEMA_VERSION, "batches": batches}


def load_batch_decisions_doc(*, persist_migration: bool = True) -> dict[str, Any]:
    raw = _load_json(
        DECISIONS_PATH,
        {"schema_version": 1, "decisions": {}, "card_status": {}},
    )
    migrated = _migrate_decisions_doc(raw)
    if persist_migration and migrated is not raw and raw.get("schema_version", 1) < BATCH_SCHEMA_VERSION:
        _atomic_write_json(DECISIONS_PATH, migrated)
    return migrated


def load_batch_user_edits_doc(*, persist_migration: bool = True) -> dict[str, Any]:
    raw = _load_json(
        USER_CARD_EDITS_PATH,
        {"schema_version": 1, "edits": {}},
    )
    migrated = _migrate_user_edits_doc(raw)
    if persist_migration and migrated is not raw and raw.get("schema_version", 1) < BATCH_SCHEMA_VERSION:
        _atomic_write_json(USER_CARD_EDITS_PATH, migrated)
    return migrated


def _batch_state(doc: dict[str, Any], batch_id: str) -> dict[str, Any]:
    batches = doc.setdefault("batches", {})
    if not isinstance(batches, dict):
        batches = {}
        doc["batches"] = batches
    state = batches.setdefault(batch_id, {})
    if not isinstance(state, dict):
        state = {}
        batches[batch_id] = state
    return state


def batch_decisions(doc: dict[str, Any], batch_id: str) -> dict[str, Any]:
    decisions = _batch_state(doc, batch_id).setdefault("decisions", {})
    return decisions if isinstance(decisions, dict) else {}


def batch_card_status(doc: dict[str, Any], batch_id: str) -> dict[str, Any]:
    status = _batch_state(doc, batch_id).setdefault("card_status", {})
    return status if isinstance(status, dict) else {}


def batch_user_edits(doc: dict[str, Any], batch_id: str) -> dict[str, Any]:
    edits = _batch_state(doc, batch_id).setdefault("edits", {})
    return edits if isinstance(edits, dict) else {}


def save_batch_decisions_doc(doc: dict[str, Any]) -> None:
    doc["schema_version"] = BATCH_SCHEMA_VERSION
    _atomic_write_json(DECISIONS_PATH, doc)


def save_batch_user_edits_doc(doc: dict[str, Any]) -> None:
    doc["schema_version"] = BATCH_SCHEMA_VERSION
    _atomic_write_json(USER_CARD_EDITS_PATH, doc)


def claude_batch_card_ids() -> list[str]:
    """All cards in the Claude review results directory."""
    from services.claude_review_store import list_result_card_ids

    return list_result_card_ids()
