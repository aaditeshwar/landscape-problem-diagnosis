#!/usr/bin/env python3
"""Backfill canonical drought causality nested keys in existing mws_data documents."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from dotenv import load_dotenv  # noqa: E402
from pymongo import MongoClient, UpdateOne  # noqa: E402

from services.variable_registry import collect_drought_nested_keys, drought_source_key_map, normalize_drought_causality  # noqa: E402


def needs_normalization(causality: dict | None) -> bool:
    if not isinstance(causality, dict):
        return False
    raw_keys = drought_source_key_map().keys()
    return bool(collect_drought_nested_keys(causality) & set(raw_keys))


def backfill(*, dry_run: bool = False, limit: int | None = None) -> dict:
    load_dotenv(ROOT / ".env")
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=10000)
    db = client["diagnosis_db"]

    cursor = db.mws_data.find({"drought_causality": {"$exists": True}}, {"uid": 1, "drought_causality": 1})
    if limit:
        cursor = cursor.limit(limit)

    ops: list[UpdateOne] = []
    scanned = 0
    changed = 0
    for doc in cursor:
        scanned += 1
        causality = doc.get("drought_causality")
        if not needs_normalization(causality):
            continue
        normalized = normalize_drought_causality(causality)
        changed += 1
        if not dry_run:
            ops.append(UpdateOne({"uid": doc["uid"]}, {"$set": {"drought_causality": normalized}}))

    modified = 0
    if ops and not dry_run:
        result = db.mws_data.bulk_write(ops, ordered=False)
        modified = result.modified_count

    client.close()
    return {
        "scanned": scanned,
        "needs_normalization": changed,
        "modified": modified,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    stats = backfill(dry_run=args.dry_run, limit=args.limit)
    print("=== MWS drought causality backfill ===")
    print(f"  Scanned:              {stats['scanned']}")
    print(f"  Needs normalization:  {stats['needs_normalization']}")
    print(f"  Modified:             {stats['modified']}")
    if stats["dry_run"]:
        print("  (dry run — no writes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
