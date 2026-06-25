"""Catalog-scoped triage patches for revise-cards integration."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import METADATA_DIR, ROOT
from services.card_patch_utils import apply_patch, build_triage_patch_findings, compute_triage_card_patch
from services.claude_review_store import card_digest, composite_key, normalize_decision, utc_now_iso
from services.review_batch_store import (
    USER_CARD_EDITS_PATH,
    batch_card_status,
    batch_decisions,
    batch_user_edits,
    load_batch_decisions_doc,
    load_batch_user_edits_doc,
    save_batch_decisions_doc,
    save_batch_user_edits_doc,
)
from services.reviewer_access import validate_reviewer_name
from services.triage_card_map import load_card_with_fallback

PATCHES_DIR = METADATA_DIR / "triage_patches"
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
TRIAGE_BATCH_PREFIX = "triage__"
DECISIONS_PATH = METADATA_DIR / "claude_review_decisions.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_catalog_name(filename: str) -> str:
    name = Path(str(filename or "").strip()).name
    if not name or name in {".", ".."}:
        raise ValueError("Invalid catalog filename")
    return name


def _catalog_path(catalog_filename: str) -> Path:
    safe = _safe_catalog_name(catalog_filename)
    return PATCHES_DIR / safe


def batch_id_for_catalog(catalog_filename: str) -> str:
    stem = Path(_safe_catalog_name(catalog_filename)).stem
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem)
    return f"{TRIAGE_BATCH_PREFIX}{slug}"


def catalog_filename_from_batch_id(batch_id: str) -> str | None:
    if not batch_id.startswith(TRIAGE_BATCH_PREFIX):
        return None
    slug = batch_id[len(TRIAGE_BATCH_PREFIX) :]
    for path in sorted(PATCHES_DIR.glob("*.json")):
        if batch_id_for_catalog(path.name) == batch_id:
            return path.name
    return f"{slug}.json"


def is_triage_batch(batch_id: str) -> bool:
    return str(batch_id or "").startswith(TRIAGE_BATCH_PREFIX)


def _empty_doc(catalog_filename: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "catalog_filename": _safe_catalog_name(catalog_filename),
        "batch_id": batch_id_for_catalog(catalog_filename),
        "updated_at": None,
        "reviewer": None,
        "cards": {},
    }


def _load_raw_card_from_disk(card_id: str) -> dict[str, Any] | None:
    path = RAW_DIR / f"{card_id}.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None


def prune_stale_catalog_entries(doc: dict[str, Any]) -> int:
    """Drop patch entries whose raw card changed after the patch was saved."""
    cards = doc.get("cards")
    if not isinstance(cards, dict) or not cards:
        return 0
    removed = 0
    for card_id in list(cards.keys()):
        entry = cards.get(card_id)
        if not isinstance(entry, dict):
            cards.pop(card_id, None)
            removed += 1
            continue
        raw_card = _load_raw_card_from_disk(card_id)
        if is_catalog_patch_stale(entry, raw_card, card_id):
            cards.pop(card_id, None)
            removed += 1
    return removed


def enrich_catalog_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Attach patch_stale flags for API consumers."""
    cards = doc.get("cards")
    if not isinstance(cards, dict):
        return doc
    for card_id, entry in cards.items():
        if not isinstance(entry, dict):
            continue
        raw_card = _load_raw_card_from_disk(card_id)
        patch_view = catalog_patch_view(entry, raw_card, card_id)
        entry["patch_stale"] = bool(patch_view.get("patch_stale"))
        entry["patch_discarded_reason"] = patch_view.get("patch_discarded_reason")
        if patch_view.get("patch_stale"):
            entry["effective_changed_fields"] = None
        else:
            entry["effective_changed_fields"] = entry.get("changed_fields")
    return doc


def load_catalog_doc(catalog_filename: str, *, prune_stale: bool = False) -> dict[str, Any]:
    path = _catalog_path(catalog_filename)
    if not path.is_file():
        return _empty_doc(catalog_filename)
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return _empty_doc(catalog_filename)
    data.setdefault("cards", {})
    data.setdefault("catalog_filename", _safe_catalog_name(catalog_filename))
    data.setdefault("batch_id", batch_id_for_catalog(catalog_filename))
    if prune_stale:
        removed = prune_stale_catalog_entries(data)
        if removed:
            save_catalog_doc(catalog_filename, data)
    return data


def save_catalog_doc(catalog_filename: str, doc: dict[str, Any]) -> dict[str, Any]:
    PATCHES_DIR.mkdir(parents=True, exist_ok=True)
    path = _catalog_path(catalog_filename)
    doc["updated_at"] = _utc_now()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    tmp.replace(path)
    return doc


def list_catalog_manifests() -> list[dict[str, Any]]:
    if not PATCHES_DIR.is_dir():
        return []
    manifests: list[dict[str, Any]] = []
    for path in sorted(PATCHES_DIR.glob("*.json")):
        doc = load_catalog_doc(path.name, prune_stale=True)
        cards = doc.get("cards") or {}
        if not isinstance(cards, dict) or not cards:
            continue
        manifests.append(doc)
    return manifests


def list_triage_batches() -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for doc in list_catalog_manifests():
        cards = doc.get("cards") or {}
        finalized = sum(
            1
            for entry in cards.values()
            if isinstance(entry, dict) and entry.get("finalized")
        )
        batches.append(
            {
                "batch_id": doc.get("batch_id"),
                "generated_at": doc.get("updated_at"),
                "pathway_filter": f"Triaging: {doc.get('catalog_filename')}",
                "model": None,
                "source": "triaging",
                "catalog_filename": doc.get("catalog_filename"),
                "card_count": len(cards),
                "finalized_card_count": finalized,
            }
        )
    return batches


def _patch_baseline_card(db, card_id: str) -> dict[str, Any] | None:
    """Prefer on-disk raw JSON for triage patch diffs (revise-cards applies to raw files)."""
    disk = _load_raw_card_from_disk(card_id)
    if disk is not None:
        return disk
    return _load_raw_card(db, card_id)


def _load_raw_card(db, card_id: str) -> dict[str, Any] | None:
    card = load_card_with_fallback(db, card_id)
    if card:
        return card
    path = RAW_DIR / f"{card_id}.json"
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    return None


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def is_catalog_patch_stale(
    entry: dict[str, Any] | None,
    raw_card: dict[str, Any] | None,
    card_id: str,
) -> bool:
    """True when the on-disk raw card changed after the catalog patch was saved."""
    if not isinstance(entry, dict):
        return False
    patch = entry.get("patch")
    if not isinstance(patch, dict) or not patch:
        return False

    stored_digest = entry.get("raw_card_digest")
    if raw_card is not None and stored_digest:
        if card_digest(raw_card) != stored_digest:
            return True

    patch_updated = _parse_iso_timestamp(entry.get("updated_at"))
    raw_path = RAW_DIR / f"{card_id}.json"
    if patch_updated and raw_path.is_file():
        file_mtime = datetime.fromtimestamp(raw_path.stat().st_mtime, tz=timezone.utc)
        if file_mtime > patch_updated:
            return True

    return False


def catalog_patch_view(
    entry: dict[str, Any] | None,
    raw_card: dict[str, Any] | None,
    card_id: str,
) -> dict[str, Any]:
    """Patch metadata for triaging / revise-cards without auto-applying stale patches."""
    if not isinstance(entry, dict):
        return {
            "patch": None,
            "changed_fields": None,
            "patch_stale": False,
            "patch_discarded_reason": None,
        }
    stale = is_catalog_patch_stale(entry, raw_card, card_id)
    if stale:
        return {
            "patch": entry.get("patch") if isinstance(entry.get("patch"), dict) else None,
            "changed_fields": None,
            "patch_stale": True,
            "patch_discarded_reason": "raw_card_changed_after_patch",
        }
    return {
        "patch": entry.get("patch") if isinstance(entry.get("patch"), dict) else None,
        "changed_fields": entry.get("changed_fields"),
        "patch_stale": False,
        "patch_discarded_reason": None,
    }


def save_catalog_patches(
    db,
    catalog_filename: str,
    *,
    reviewer: str,
    cards: list[dict[str, Any]],
) -> dict[str, Any]:
    reviewer_name = validate_reviewer_name(reviewer)
    doc = load_catalog_doc(catalog_filename)
    doc["reviewer"] = reviewer_name
    stored = doc.setdefault("cards", {})

    saved_count = 0
    for item in cards:
        card_id = str(item.get("card_id") or "").strip()
        if not card_id:
            continue
        raw_card = _patch_baseline_card(db, card_id)
        if not raw_card:
            continue
        diagnostic_signals = item.get("diagnostic_signals") or []
        confirmation_policy = item.get("confirmation_policy")
        patch, changed_fields = compute_triage_card_patch(
            raw_card,
            diagnostic_signals=diagnostic_signals,
            confirmation_policy=confirmation_policy if isinstance(confirmation_policy, dict) else None,
        )
        if not patch:
            stored.pop(card_id, None)
            continue
        prior = stored.get(card_id) if isinstance(stored.get(card_id), dict) else {}
        stale = is_catalog_patch_stale(prior, raw_card, card_id)
        stored[card_id] = {
            "card_id": card_id,
            "patch": patch,
            "changed_fields": changed_fields,
            "updated_at": _utc_now(),
            "reviewer": reviewer_name,
            "raw_card_digest": card_digest(raw_card) if raw_card else None,
            "finalized": bool(prior.get("finalized")) and not stale,
            "finalized_at": prior.get("finalized_at") if not stale else None,
            "finalized_reviewer": prior.get("finalized_reviewer") if not stale else None,
            "replaced_stale_patch": stale,
        }
        saved_count += 1

    prune_stale_catalog_entries(doc)
    doc = save_catalog_doc(catalog_filename, doc)
    return {
        "catalog_filename": doc.get("catalog_filename"),
        "batch_id": doc.get("batch_id"),
        "saved_count": saved_count,
        "card_count": len(doc.get("cards") or {}),
        "updated_at": doc.get("updated_at"),
        "reviewer": reviewer_name,
    }


def triage_batch_summary(batch_id: str) -> dict[str, Any]:
    catalog_filename = catalog_filename_from_batch_id(batch_id)
    if not catalog_filename:
        raise KeyError(f"Unknown triage batch: {batch_id}")
    doc = load_catalog_doc(catalog_filename)
    if doc.get("batch_id") != batch_id:
        raise KeyError(f"Unknown triage batch: {batch_id}")

    decisions_doc = load_batch_decisions_doc()
    decisions = batch_decisions(decisions_doc, batch_id)
    card_status = batch_card_status(decisions_doc, batch_id)

    cards_out: list[dict[str, Any]] = []
    for card_id, entry in sorted((doc.get("cards") or {}).items()):
        if not isinstance(entry, dict):
            continue
        raw_card = _load_raw_card_from_disk(card_id)
        patch_view = catalog_patch_view(entry, raw_card, card_id)
        if patch_view.get("patch_stale"):
            continue
        patch = patch_view.get("patch") or {}
        changed_fields = patch_view.get("changed_fields") or {}
        findings = build_triage_patch_findings(
            card_id,
            raw_card,
            patch if isinstance(patch, dict) else {},
            changed_fields if isinstance(changed_fields, dict) else {},
        )
        if not findings:
            continue
        pending = 0
        handled = 0
        not_handled = 0
        for finding in findings:
            key = composite_key(card_id, str(finding.get("issue_id") or ""))
            decision_entry = decisions.get(key) if isinstance(decisions, dict) else None
            decision = (
                normalize_decision(decision_entry.get("decision"))
                if isinstance(decision_entry, dict)
                else None
            )
            if decision == "handled":
                handled += 1
            elif decision == "not_handled":
                not_handled += 1
            else:
                pending += 1
        status_entry = card_status.get(card_id) if isinstance(card_status, dict) else None
        finalized = bool(entry.get("finalized")) or (
            isinstance(status_entry, dict) and status_entry.get("status") == "finalized"
        )
        cards_out.append(
            {
                "card_id": card_id,
                "overall_score": "triaging",
                "dimensions": {},
                "finding_count": len(findings),
                "handled_count": handled,
                "not_handled_count": not_handled,
                "decided_count": handled + not_handled,
                "pending_count": pending,
                "finalized": finalized,
                "finalized_at": entry.get("finalized_at") or (
                    status_entry.get("finalized_at") if isinstance(status_entry, dict) else None
                ),
                "has_edits": bool(patch),
            }
        )

    return {
        "batch_id": batch_id,
        "manifest": {
            "generated_at": doc.get("updated_at"),
            "pathway_filter": f"Triaging: {catalog_filename}",
            "source": "triaging",
            "catalog_filename": catalog_filename,
        },
        "cards": cards_out,
        "totals": {
            "cards": len(cards_out),
            "finalized_cards": sum(1 for card in cards_out if card["finalized"]),
            "findings": sum(card["finding_count"] for card in cards_out),
        },
    }


def triage_load_card_bundle(batch_id: str, card_id: str) -> dict[str, Any]:
    catalog_filename = catalog_filename_from_batch_id(batch_id)
    if not catalog_filename:
        raise KeyError(f"Unknown triage batch: {batch_id}")
    doc = load_catalog_doc(catalog_filename)
    cards = doc.get("cards") or {}
    entry = cards.get(card_id) if isinstance(cards, dict) else None
    if not isinstance(entry, dict):
        raise KeyError(f"No triage patch for card: {card_id}")

    raw_path = RAW_DIR / f"{card_id}.json"
    raw_card: dict[str, Any] | None = None
    if raw_path.exists():
        with raw_path.open(encoding="utf-8") as handle:
            raw_card = json.load(handle)

    patch = entry.get("patch") if isinstance(entry.get("patch"), dict) else {}
    changed_fields = entry.get("changed_fields") if isinstance(entry.get("changed_fields"), dict) else {}
    patch_view = catalog_patch_view(entry, raw_card, card_id)
    if patch_view.get("patch_stale"):
        patch = {}
        changed_fields = {}

    decisions_doc = load_batch_decisions_doc()
    user_edits_doc = load_batch_user_edits_doc()
    decisions = batch_decisions(decisions_doc, batch_id)
    card_status = batch_card_status(decisions_doc, batch_id)
    user_edits = batch_user_edits(user_edits_doc, batch_id)

    findings_raw = build_triage_patch_findings(card_id, raw_card, patch, changed_fields)
    findings: list[dict[str, Any]] = []
    for finding in findings_raw:
        issue_id = str(finding.get("issue_id") or "")
        key = composite_key(card_id, issue_id)
        decision_entry = decisions.get(key) if isinstance(decisions, dict) else None
        normalized_decision = None
        if isinstance(decision_entry, dict):
            raw_decision = normalize_decision(decision_entry.get("decision"))
            if raw_decision:
                normalized_decision = {**decision_entry, "decision": raw_decision}
        findings.append(
            {
                **finding,
                "composite_key": key,
                "decision": normalized_decision,
                "edited_patch": None,
            }
        )

    user_edit_entry = user_edits.get(card_id) if isinstance(user_edits, dict) else None
    user_card_edit = None
    if isinstance(user_edit_entry, dict) and isinstance(user_edit_entry.get("patch"), dict):
        user_card_edit = user_edit_entry.get("patch")

    user_card_edit_status = {
        "has_saved_edit": bool(user_card_edit),
        "propagated_at": user_edit_entry.get("propagated_at") if isinstance(user_edit_entry, dict) else None,
        "in_sync_with_raw_card": False,
        "last_saved_at": (
            user_edit_entry.get("finalized_at")
            if isinstance(user_edit_entry, dict)
            else entry.get("finalized_at") or entry.get("updated_at")
        ),
    }
    if isinstance(user_edit_entry, dict) and raw_card is not None:
        raw_digest = card_digest(raw_card)
        applied_digest = user_edit_entry.get("applied_card_digest")
        propagated_at = user_edit_entry.get("propagated_at")
        user_card_edit_status["in_sync_with_raw_card"] = bool(
            propagated_at and applied_digest and raw_digest == applied_digest
        )

    status_entry = card_status.get(card_id) if isinstance(card_status, dict) else None
    finalized = bool(entry.get("finalized")) or (
        isinstance(status_entry, dict) and status_entry.get("status") == "finalized"
    )

    return {
        "batch_id": batch_id,
        "card_id": card_id,
        "overall_score": "triaging",
        "dimensions": {},
        "summary": f"Case-study triaging edits from {catalog_filename}",
        "overall_reasoning_note": (raw_card or {}).get("overall_reasoning_note"),
        "findings": findings,
        "raw_card": raw_card,
        "user_card_edit": user_card_edit,
        "user_card_edit_status": user_card_edit_status,
        "finalized": finalized,
        "finalized_at": entry.get("finalized_at") or (
            status_entry.get("finalized_at") if isinstance(status_entry, dict) else None
        ),
        "triage_changed_fields": changed_fields,
        "triage_source_patch": patch if not patch_view.get("patch_stale") else None,
        "patch_stale": bool(patch_view.get("patch_stale")),
        "patch_discarded_reason": patch_view.get("patch_discarded_reason"),
    }


def finalize_triage_card(
    batch_id: str,
    card_id: str,
    *,
    reviewer: str | None,
    user_card_edit: dict[str, Any] | None,
    issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from services.claude_review_store import VALID_DECISIONS

    reviewer_name = validate_reviewer_name(reviewer)
    catalog_filename = catalog_filename_from_batch_id(batch_id)
    if not catalog_filename:
        raise KeyError(f"Unknown triage batch: {batch_id}")

    doc = load_catalog_doc(catalog_filename)
    cards = doc.setdefault("cards", {})
    entry = cards.get(card_id) if isinstance(cards, dict) else None
    if not isinstance(entry, dict):
        raise KeyError(f"No triage patch for card: {card_id}")

    raw_path = RAW_DIR / f"{card_id}.json"
    raw_card: dict[str, Any] | None = None
    if raw_path.exists():
        with raw_path.open(encoding="utf-8") as handle:
            raw_card = json.load(handle)

    patch = user_card_edit if isinstance(user_card_edit, dict) and user_card_edit else entry.get("patch")
    if not isinstance(patch, dict) or not patch:
        raise ValueError("No card edits to finalize")

    findings = build_triage_patch_findings(
        card_id,
        raw_card,
        patch if isinstance(entry.get("patch"), dict) else patch,
        entry.get("changed_fields") if isinstance(entry.get("changed_fields"), dict) else {},
    )
    issue_rows = issues or []
    if findings and not issue_rows:
        raise ValueError("Each triaging patch item needs a handled or not_handled decision")
    if findings and len(issue_rows) != len(findings):
        raise ValueError(
            f"Expected decisions for all {len(findings)} triaging patch items; got {len(issue_rows)}"
        )

    now = utc_now_iso()
    handled = 0
    not_handled = 0

    decisions_doc = load_batch_decisions_doc()
    user_edits_doc = load_batch_user_edits_doc()
    decisions = batch_decisions(decisions_doc, batch_id)
    card_status = batch_card_status(decisions_doc, batch_id)
    user_edits = batch_user_edits(user_edits_doc, batch_id)

    for item in issue_rows:
        issue_id = str(item.get("issue_id") or "").strip()
        decision = normalize_decision(str(item.get("decision") or "pending"))
        if not issue_id:
            raise ValueError("Each issue must include issue_id")
        if decision not in VALID_DECISIONS:
            raise ValueError(
                f"Issue {issue_id}: decision must be handled or not_handled before finalize"
            )
        key = composite_key(card_id, issue_id)
        decisions[key] = {
            "card_id": card_id,
            "issue_id": issue_id,
            "decision": decision,
            "reviewer_note": str(item.get("reviewer_note") or ""),
            "decided_at": now,
        }
        if decision == "handled":
            handled += 1
        else:
            not_handled += 1

    entry["patch"] = patch
    entry["finalized"] = True
    entry["finalized_at"] = now
    entry["finalized_reviewer"] = reviewer_name
    entry["reviewer"] = reviewer_name
    save_catalog_doc(catalog_filename, doc)

    user_edits[card_id] = {
        "card_id": card_id,
        "patch": patch,
        "finalized_at": now,
        "reviewer": reviewer_name,
        "source_batch_id": batch_id,
        "propagated_at": None,
        "applied_card_digest": None,
    }

    card_status[card_id] = {
        "status": "finalized",
        "finalized_at": now,
        "reviewer": reviewer_name,
        "source": "triaging",
        "batch_id": batch_id,
        "handled_count": handled,
        "not_handled_count": not_handled,
    }

    save_batch_user_edits_doc(user_edits_doc)
    save_batch_decisions_doc(decisions_doc)

    return {
        "card_id": card_id,
        "finalized_at": now,
        "handled_count": handled,
        "not_handled_count": not_handled,
        "user_edit_saved": True,
        "decisions_path": str(DECISIONS_PATH.relative_to(ROOT)),
        "edited_patches_path": str((METADATA_DIR / "claude_review_edited_patches.json").relative_to(ROOT)),
        "user_card_edits_path": str(USER_CARD_EDITS_PATH.relative_to(ROOT)),
    }


def apply_catalog_patch_to_card(raw_card: dict[str, Any], catalog_filename: str, card_id: str) -> dict[str, Any]:
    doc = load_catalog_doc(catalog_filename)
    entry = (doc.get("cards") or {}).get(card_id)
    if not isinstance(entry, dict):
        return raw_card
    patch = entry.get("patch")
    if not isinstance(patch, dict) or not patch:
        return raw_card
    return apply_patch(raw_card, patch)
