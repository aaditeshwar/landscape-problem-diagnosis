#!/usr/bin/env python3
"""Add AER-3 to Deccan hard-rock evidence cards (clusters 001/002) in MongoDB and raw JSON."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap()

from dotenv import load_dotenv
from pymongo import MongoClient

RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
PATCHES = {
    "__001": ["AER-3", "AER-6"],
    "__002": ["AER-3", "AER-7", "AER-8"],
}


def main() -> int:
    load_dotenv(ROOT / ".env")
    db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[
        os.getenv("MONGO_DB", "diagnosis_db")
    ]
    col = db.evidence_cards
    updated_mongo = 0
    updated_files = 0

    for suffix, aer_tags in PATCHES.items():
        for path in sorted(RAW_DIR.glob(f"*{suffix}.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("aer_tags") == aer_tags:
                continue
            doc["aer_tags"] = aer_tags
            ctx = doc.get("context") or {}
            if "agro_climatic_zones" in ctx and "AER-3" not in str(doc.get("card_id", "")):
                pass
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            updated_files += 1
            result = col.update_one({"_id": doc["card_id"]}, {"$set": {"aer_tags": aer_tags}})
            if result.matched_count:
                updated_mongo += 1

    print(f"Updated raw JSON files: {updated_files}")
    print(f"Updated MongoDB documents: {updated_mongo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
