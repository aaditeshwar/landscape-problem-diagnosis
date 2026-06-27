#!/usr/bin/env python3
"""Rebase triage catalog patches onto current raw evidence cards.

Preserves each patch's intended edited card state (apply old patch), then
recomputes the patch as a diff against the current raw baseline and refreshes
raw_card_digest so the triaging app no longer marks entries stale.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.card_patch_utils import apply_patch, compute_triage_card_patch  # noqa: E402
from services.claude_review_store import card_digest  # noqa: E402
from services.triage_patch_store import PATCHES_DIR, RAW_DIR  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rebase_catalog_patches(doc: dict, *, dry_run: bool = False) -> dict:
    cards = doc.get("cards")
    if not isinstance(cards, dict):
        return {"updated": [], "removed": [], "skipped": [], "missing_raw": [], "dry_run": dry_run}

    updated: list[str] = []
    removed: list[str] = []
    skipped: list[str] = []
    missing_raw: list[str] = []
    details: dict[str, list[str]] = {}

    for card_id in list(cards.keys()):
        entry = cards.get(card_id)
        if not isinstance(entry, dict):
            cards.pop(card_id, None)
            removed.append(card_id)
            continue

        patch = entry.get("patch")
        if not isinstance(patch, dict) or not patch:
            cards.pop(card_id, None)
            removed.append(card_id)
            continue

        raw_path = RAW_DIR / f"{card_id}.json"
        if not raw_path.is_file():
            missing_raw.append(card_id)
            continue

        raw_card = json.loads(raw_path.read_text(encoding="utf-8"))
        intended = apply_patch(copy.deepcopy(raw_card), patch)
        new_patch, changed_fields = compute_triage_card_patch(
            raw_card,
            diagnostic_signals=intended.get("diagnostic_signals") or [],
            confirmation_policy=intended.get("confirmation_policy")
            if isinstance(intended.get("confirmation_policy"), dict)
            else None,
        )

        if not new_patch:
            removed.append(card_id)
            details[card_id] = ["patch empty after rebase — raw already matches intended state"]
            if not dry_run:
                cards.pop(card_id, None)
            continue

        new_digest = card_digest(raw_card)
        needs_update = (
            new_patch != patch
            or changed_fields != entry.get("changed_fields")
            or str(entry.get("raw_card_digest") or "") != new_digest
        )
        if not needs_update:
            skipped.append(card_id)
            continue

        updated.append(card_id)
        notes: list[str] = []
        if new_patch != patch:
            notes.append("patch rebased onto current raw")
        if str(entry.get("raw_card_digest") or "") != new_digest:
            notes.append("raw_card_digest updated")
        details[card_id] = notes

        if not dry_run:
            entry["patch"] = new_patch
            entry["changed_fields"] = changed_fields
            entry["raw_card_digest"] = new_digest
            entry["updated_at"] = _utc_now()
            entry.pop("patch_stale", None)
            entry.pop("patch_discarded_reason", None)

    if (updated or removed) and not dry_run:
        doc["updated_at"] = _utc_now()

    return {
        "updated": updated,
        "updated_count": len(updated),
        "removed": removed,
        "removed_count": len(removed),
        "skipped": skipped,
        "missing_raw": missing_raw,
        "details": details,
        "dry_run": dry_run,
    }


def sync_all_catalogs(*, dry_run: bool = False, catalog: str | None = None) -> dict:
    if not PATCHES_DIR.is_dir():
        return {"catalogs": {}, "dry_run": dry_run}

    paths = sorted(PATCHES_DIR.glob("*.json"))
    if catalog:
        paths = [p for p in paths if p.name == catalog or p.stem == Path(catalog).stem]

    reports: dict[str, dict] = {}
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        report = rebase_catalog_patches(doc, dry_run=dry_run)
        reports[path.name] = report
        if not dry_run and (report["updated_count"] or report["removed_count"]):
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(path)

    return {"catalogs": reports, "dry_run": dry_run}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--catalog", help="Limit to one catalog filename under metadata/triage_patches/")
    args = parser.parse_args()

    result = sync_all_catalogs(dry_run=args.dry_run, catalog=args.catalog)
    print("=== Sync triage patches from raw cards ===")
    for name, report in result["catalogs"].items():
        print(f"\n{name}:")
        print(f"  Updated: {report['updated_count']}")
        print(f"  Removed (now in raw): {report['removed_count']}")
        print(f"  Skipped (already aligned): {len(report['skipped'])}")
        if report["missing_raw"]:
            print(f"  Missing raw: {len(report['missing_raw'])}")
        for card_id in report["updated"][:15]:
            print(f"    - {card_id}: {', '.join(report['details'].get(card_id, []))}")
        if report["updated_count"] > 15:
            print(f"    ... and {report['updated_count'] - 15} more")
        for card_id in report["removed"][:10]:
            print(f"    x {card_id}: {', '.join(report['details'].get(card_id, ['removed']))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
