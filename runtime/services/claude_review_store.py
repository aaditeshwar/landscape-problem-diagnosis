"""File-backed Claude evidence-card review queue for /revise-cards."""

from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import METADATA_DIR, ROOT

REVIEW_DIR = ROOT / "reports" / "claude_review"
RESULTS_DIR = REVIEW_DIR / "results"
MANIFEST_PATH = REVIEW_DIR / "review_manifest.json"
PATCHES_PATH = REVIEW_DIR / "suggested_patches.json"
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
DECISIONS_PATH = METADATA_DIR / "claude_review_decisions.json"
EDITED_PATCHES_PATH = METADATA_DIR / "claude_review_edited_patches.json"
USER_CARD_EDITS_PATH = METADATA_DIR / "claude_review_user_card_edits.json"

COMPOSITE_SEP = "::"


def composite_key(card_id: str, issue_id: str) -> str:
    return f"{card_id}{COMPOSITE_SEP}{issue_id}"


VALID_DECISIONS = frozenset({"handled", "not_handled"})
LEGACY_DECISION_MAP = {"accept": "handled", "reject": "not_handled"}


def normalize_decision(raw: str | None) -> str | None:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    if value in VALID_DECISIONS:
        return value
    return LEGACY_DECISION_MAP.get(value)


def parse_composite_key(key: str) -> tuple[str, str]:
    if COMPOSITE_SEP in key:
        card_id, issue_id = key.split(COMPOSITE_SEP, 1)
        return card_id, issue_id
    return "", key


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def card_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else dict(default)


def _split_field_path(field_path: str) -> list[str | int]:
    if not field_path:
        return []
    parts: list[str | int] = []
    for segment in field_path.split("."):
        while segment:
            match = re.match(r"^([^\[]+)(\[(\d+)\])?(.*)$", segment)
            if not match:
                parts.append(segment)
                break
            name, _, index, rest = match.groups()
            if name:
                parts.append(name)
            if index is not None:
                parts.append(int(index))
            segment = rest
    return parts


def get_by_path(obj: Any, field_path: str) -> Any:
    cur = obj
    for part in _split_field_path(field_path):
        if cur is None:
            return None
        cur = cur[part]
    return cur


def safe_get_by_path(obj: Any, field_path: str) -> Any:
    """Resolve a dotted/bracket field path; return None when path is invalid."""
    if not field_path or not isinstance(obj, dict):
        return None
    if " / " in field_path:
        return None
    try:
        return get_by_path(obj, field_path)
    except (KeyError, IndexError, TypeError):
        return None


def batch_id_from_manifest(manifest: dict[str, Any]) -> str:
    generated = str(manifest.get("generated_at") or "")
    date_part = generated[:10] if generated else "unknown"
    pathway = str(manifest.get("pathway_filter") or "full").strip() or "full"
    slug = pathway.split("__")[-1] if "__" in pathway else pathway.replace("/", "_")
    return f"{date_part}_{slug}"


def load_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    return {}


def list_result_card_ids() -> list[str]:
    if not RESULTS_DIR.exists():
        return []
    return sorted(path.stem for path in RESULTS_DIR.glob("*.json"))


def load_suggested_patches_index() -> dict[str, dict[str, dict[str, Any]]]:
    if not PATCHES_PATH.exists():
        return {}
    with PATCHES_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    index: dict[str, dict[str, dict[str, Any]]] = {}
    if not isinstance(raw, dict):
        return index
    for card_id, items in raw.items():
        if not isinstance(items, list):
            continue
        card_map: dict[str, dict[str, Any]] = {}
        for item in items:
            if isinstance(item, dict):
                issue_id = str(item.get("issue_id") or "")
                if issue_id:
                    card_map[issue_id] = item
        index[str(card_id)] = card_map
    return index


def load_decisions_doc() -> dict[str, Any]:
    from services.review_batch_store import load_batch_decisions_doc

    return load_batch_decisions_doc()


def load_user_card_edits_doc() -> dict[str, Any]:
    from services.review_batch_store import load_batch_user_edits_doc

    return load_batch_user_edits_doc()


def load_edited_patches_doc() -> dict[str, Any]:
    return load_json(
        EDITED_PATCHES_PATH,
        {"schema_version": 1, "patches": {}},
    )


def variable_registry_payload() -> dict[str, Any]:
    from services.variable_registry import (
        ASSEMBLER_DERIVED_VARIABLE_NAMES,
        DROUGHT_DERIVED_VARIABLE_NAMES,
        all_expression_allowed_names,
        variable_type_catalog,
    )

    allowed = sorted(all_expression_allowed_names())
    return {
        "allowed_names": allowed,
        "assembler_derived": sorted(ASSEMBLER_DERIVED_VARIABLE_NAMES),
        "drought_derived": sorted(DROUGHT_DERIVED_VARIABLE_NAMES),
        "variable_types": variable_type_catalog(),
        "count": len(allowed),
    }


def list_batches() -> list[dict[str, Any]]:
    from services.review_batch_store import batch_card_status, claude_batch_card_ids
    from services.triage_patch_store import list_triage_batches

    batches: list[dict[str, Any]] = []
    manifest = load_manifest()
    review_card_ids = claude_batch_card_ids()
    if review_card_ids:
        batch_id = batch_id_from_manifest(manifest)
        decisions_doc = load_decisions_doc()
        card_status = batch_card_status(decisions_doc, batch_id)
        finalized = sum(
            1
            for card_id in review_card_ids
            if isinstance(card_status.get(card_id), dict)
            and card_status[card_id].get("status") == "finalized"
        )
        batches.append(
            {
                "batch_id": batch_id,
                "generated_at": manifest.get("generated_at"),
                "pathway_filter": manifest.get("pathway_filter"),
                "model": manifest.get("model"),
                "source": "claude_review",
                "card_count": len(review_card_ids),
                "finalized_card_count": finalized,
            }
        )
    batches.extend(list_triage_batches())
    batches.sort(key=lambda row: str(row.get("batch_id") or ""), reverse=True)
    return batches


def load_card_result(card_id: str) -> dict[str, Any] | None:
    path = RESULTS_DIR / f"{card_id}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None


def enrich_findings(card_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    patch_index = load_suggested_patches_index().get(card_id, {})
    findings: list[dict[str, Any]] = []
    for finding in result.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        issue_id = str(finding.get("issue_id") or "")
        merged = dict(finding)
        if not merged.get("suggested_patch") and issue_id in patch_index:
            merged["suggested_patch"] = patch_index[issue_id].get("suggested_patch")
        findings.append(merged)
    return findings


def batch_summary(batch_id: str) -> dict[str, Any]:
    from services.review_batch_store import batch_card_status, batch_decisions, claude_batch_card_ids
    from services.triage_patch_store import is_triage_batch, triage_batch_summary

    if is_triage_batch(batch_id):
        return triage_batch_summary(batch_id)

    manifest = load_manifest()
    expected_id = batch_id_from_manifest(manifest)
    if batch_id != expected_id:
        raise KeyError(f"Unknown review batch: {batch_id}")

    decisions_doc = load_decisions_doc()
    card_status = batch_card_status(decisions_doc, batch_id)
    decisions = batch_decisions(decisions_doc, batch_id)
    edited_doc = load_edited_patches_doc()
    edited = edited_doc.get("patches") or {}

    cards: list[dict[str, Any]] = []
    for card_id in claude_batch_card_ids():
        result = load_card_result(card_id)
        if not result:
            continue
        findings = enrich_findings(card_id, result)
        pending = 0
        handled = 0
        not_handled = 0
        for finding in findings:
            key = composite_key(card_id, str(finding.get("issue_id") or ""))
            entry = decisions.get(key) if isinstance(decisions, dict) else None
            decision = (
                normalize_decision(entry.get("decision"))
                if isinstance(entry, dict)
                else None
            )
            if decision == "handled":
                handled += 1
            elif decision == "not_handled":
                not_handled += 1
            else:
                pending += 1
        status_entry = card_status.get(card_id) if isinstance(card_status, dict) else None
        finalized = (
            isinstance(status_entry, dict) and status_entry.get("status") == "finalized"
        )
        cards.append(
            {
                "card_id": card_id,
                "overall_score": result.get("overall_score") or "unknown",
                "dimensions": result.get("dimensions") or {},
                "finding_count": len(findings),
                "handled_count": handled,
                "not_handled_count": not_handled,
                "decided_count": handled + not_handled,
                "pending_count": pending,
                "finalized": finalized,
                "finalized_at": status_entry.get("finalized_at") if isinstance(status_entry, dict) else None,
                "has_edits": any(
                    isinstance(edited.get(composite_key(card_id, str(f.get("issue_id") or ""))), dict)
                    for f in findings
                ),
            }
        )

    return {
        "batch_id": batch_id,
        "manifest": manifest,
        "cards": cards,
        "totals": {
            "cards": len(cards),
            "finalized_cards": sum(1 for card in cards if card["finalized"]),
            "findings": sum(card["finding_count"] for card in cards),
        },
    }


def load_card_bundle(batch_id: str, card_id: str) -> dict[str, Any]:
    from services.review_batch_store import batch_card_status, batch_decisions, batch_user_edits
    from services.triage_patch_store import is_triage_batch, triage_load_card_bundle

    if is_triage_batch(batch_id):
        return triage_load_card_bundle(batch_id, card_id)

    manifest = load_manifest()
    if batch_id != batch_id_from_manifest(manifest):
        raise KeyError(f"Unknown review batch: {batch_id}")

    result = load_card_result(card_id)
    if not result:
        raise KeyError(f"No review result for card: {card_id}")

    raw_path = RAW_DIR / f"{card_id}.json"
    raw_card: dict[str, Any] | None = None
    if raw_path.exists():
        with raw_path.open(encoding="utf-8") as handle:
            raw_card = json.load(handle)

    decisions_doc = load_decisions_doc()
    user_edits_doc = load_user_card_edits_doc()
    edited_doc = load_edited_patches_doc()
    decisions = batch_decisions(decisions_doc, batch_id)
    edited = edited_doc.get("patches") or {}
    card_status = batch_card_status(decisions_doc, batch_id)
    user_edits = batch_user_edits(user_edits_doc, batch_id)

    findings: list[dict[str, Any]] = []
    for finding in enrich_findings(card_id, result):
        issue_id = str(finding.get("issue_id") or "")
        key = composite_key(card_id, issue_id)
        field_path = str(finding.get("field_path") or "")
        current_from_card = safe_get_by_path(raw_card, field_path) if raw_card else None
        current_value = finding.get("current_value")
        if current_value is None:
            current_value = current_from_card
        decision_entry = decisions.get(key) if isinstance(decisions, dict) else None
        normalized_decision = None
        if isinstance(decision_entry, dict):
            raw_decision = normalize_decision(decision_entry.get("decision"))
            if raw_decision:
                normalized_decision = {**decision_entry, "decision": raw_decision}
        edit_entry = edited.get(key) if isinstance(edited, dict) else None
        finding_out = {
            **finding,
            "composite_key": key,
            "current_value": current_value,
            "current_from_card": current_from_card,
            "decision": normalized_decision,
            "edited_patch": edit_entry.get("patch") if isinstance(edit_entry, dict) else None,
        }
        expr_text = ""
        if "expression" in field_path and isinstance(current_value, str):
            expr_text = current_value
        elif isinstance(current_from_card, str):
            expr_text = current_from_card
        if expr_text:
            from services.variable_registry import audit_dict_access_keys

            finding_out["dict_key_issues"] = audit_dict_access_keys(expr_text)
        findings.append(finding_out)

    status_entry = card_status.get(card_id) if isinstance(card_status, dict) else None
    user_edit_entry = user_edits.get(card_id) if isinstance(user_edits, dict) else None
    user_card_edit = None
    user_card_edit_status: dict[str, Any] | None = None
    if isinstance(user_edit_entry, dict):
        user_card_edit = user_edit_entry.get("patch")
        raw_digest = card_digest(raw_card) if raw_card is not None else None
        applied_digest = user_edit_entry.get("applied_card_digest")
        propagated_at = user_edit_entry.get("propagated_at")
        user_card_edit_status = {
            "has_saved_edit": isinstance(user_card_edit, dict) and bool(user_card_edit),
            "propagated_at": propagated_at,
            "in_sync_with_raw_card": bool(
                propagated_at and raw_digest and applied_digest and raw_digest == applied_digest
            ),
            "last_saved_at": user_edit_entry.get("finalized_at"),
        }
    if user_card_edit_status is None:
        user_card_edit_status = {
            "has_saved_edit": False,
            "propagated_at": None,
            "in_sync_with_raw_card": True,
            "last_saved_at": None,
        }
    return {
        "batch_id": batch_id,
        "card_id": card_id,
        "overall_score": result.get("overall_score"),
        "dimensions": result.get("dimensions") or {},
        "summary": result.get("summary"),
        "overall_reasoning_note": (raw_card or {}).get("overall_reasoning_note") if raw_card else None,
        "findings": findings,
        "raw_card": raw_card,
        "user_card_edit": user_card_edit if isinstance(user_card_edit, dict) else None,
        "user_card_edit_status": user_card_edit_status,
        "finalized": isinstance(status_entry, dict) and status_entry.get("status") == "finalized",
        "finalized_at": status_entry.get("finalized_at") if isinstance(status_entry, dict) else None,
    }


def finalize_card(
    card_id: str,
    issues: list[dict[str, Any]],
    reviewer: str | None = None,
    user_card_edit: dict[str, Any] | None = None,
    *,
    batch_id: str | None = None,
) -> dict[str, Any]:
    from services.review_batch_store import (
        batch_card_status,
        batch_decisions,
        batch_user_edits,
        save_batch_decisions_doc,
        save_batch_user_edits_doc,
    )
    from services.triage_patch_store import finalize_triage_card, is_triage_batch

    if batch_id and is_triage_batch(batch_id):
        return finalize_triage_card(
            batch_id,
            card_id,
            reviewer=reviewer,
            user_card_edit=user_card_edit,
            issues=issues,
        )

    if not batch_id:
        batch_id = batch_id_from_manifest(load_manifest())

    result = load_card_result(card_id)
    if not result:
        raise KeyError(f"No review result for card: {card_id}")
    expected_findings = len(enrich_findings(card_id, result))
    if expected_findings and not issues:
        raise ValueError("Each finding on this card needs a handled or not_handled decision")
    if expected_findings and len(issues) != expected_findings:
        raise ValueError(
            f"Expected decisions for all {expected_findings} findings; got {len(issues)}"
        )

    decisions_doc = load_decisions_doc()
    edited_doc = load_edited_patches_doc()
    user_edits_doc = load_user_card_edits_doc()
    decisions = batch_decisions(decisions_doc, batch_id)
    card_status = batch_card_status(decisions_doc, batch_id)
    user_edits = batch_user_edits(user_edits_doc, batch_id)
    patches = edited_doc.setdefault("patches", {})
    now = utc_now_iso()

    handled = 0
    not_handled = 0
    user_edit_saved = False

    for item in issues:
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

    if user_card_edit:
        user_edits[card_id] = {
            "card_id": card_id,
            "patch": user_card_edit,
            "finalized_at": now,
            "reviewer": reviewer or None,
            "source_batch_id": batch_id,
            "propagated_at": None,
            "applied_card_digest": None,
        }
        user_edit_saved = True

    card_status[card_id] = {
        "status": "finalized",
        "finalized_at": now,
        "reviewer": reviewer or None,
        "handled_count": handled,
        "not_handled_count": not_handled,
        "batch_id": batch_id,
        "source": "claude_review",
    }

    decisions_doc["schema_version"] = 2
    edited_doc["schema_version"] = 1
    user_edits_doc["schema_version"] = 2
    save_batch_decisions_doc(decisions_doc)
    atomic_write_json(EDITED_PATCHES_PATH, edited_doc)
    save_batch_user_edits_doc(user_edits_doc)

    return {
        "card_id": card_id,
        "finalized_at": now,
        "handled_count": handled,
        "not_handled_count": not_handled,
        "user_edit_saved": user_edit_saved,
        "decisions_path": str(DECISIONS_PATH.relative_to(ROOT)),
        "edited_patches_path": str(EDITED_PATCHES_PATH.relative_to(ROOT)),
        "user_card_edits_path": str(USER_CARD_EDITS_PATH.relative_to(ROOT)),
    }
