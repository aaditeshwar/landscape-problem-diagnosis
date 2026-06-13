#!/usr/bin/env python3
"""Remove a pathway tag and its evidence cards from MongoDB."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

from dotenv import load_dotenv
from pymongo import MongoClient

bootstrap()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pathway_tag", help="Full pathway key, e.g. prod__stress__pathway")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB", "diagnosis_db")
    tag = args.pathway_tag

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db = client[db_name]

    cards = db.evidence_cards
    prefix = f"^{tag}__"
    by_tag = cards.delete_many({"pathway_tags": tag})
    by_prefix = cards.delete_many({"card_id": {"$regex": prefix}})
    print(f"evidence_cards deleted by tag: {by_tag.deleted_count}")
    print(f"evidence_cards deleted by card_id prefix: {by_prefix.deleted_count}")

    chunks = db.paper_chunks
    tagged = list(chunks.find({"pathway_tags": tag}, {"_id": 1}))
    for doc in tagged:
        chunks.update_one({"_id": doc["_id"]}, {"$pull": {"pathway_tags": tag}})
    print(f"paper_chunks tag removed from: {len(tagged)}")
    print(f"remaining evidence_cards with tag: {cards.count_documents({'pathway_tags': tag})}")
    print(f"remaining paper_chunks with tag: {chunks.count_documents({'pathway_tags': tag})}")
    print(f"total evidence_cards now: {cards.count_documents({})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
