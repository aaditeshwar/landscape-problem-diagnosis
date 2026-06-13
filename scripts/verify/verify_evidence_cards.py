"""Verify evidence_cards in MongoDB."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

from dotenv import load_dotenv
from pymongo import MongoClient

bootstrap()
load_dotenv(ROOT / ".env")


def main() -> int:
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    col = client["diagnosis_db"]["evidence_cards"]

    total = col.count_documents({})
    with_emb = col.count_documents({"embedding": {"$exists": True, "$ne": []}})
    reviewed = col.count_documents({"metadata.reviewed_by_expert": True})

    print("=== evidence_cards status ===")
    print(f"  Total cards:      {total}")
    print(f"  With embeddings:  {with_emb}")
    print(f"  Expert reviewed:  {reviewed}")

    pathways = col.distinct("pathway_tags")
    print(f"  Pathway tags:     {len(pathways)}")
    for tag in sorted(pathways):
        n = col.count_documents({"pathway_tags": tag})
        print(f"    {tag}: {n}")

    sample = col.find_one({}, {"card_id": 1, "causal_pathway": 1, "pathway_tags": 1, "aer_tags": 1})
    if sample:
        print("\n=== Sample card ===")
        print(f"  card_id: {sample.get('card_id')}")
        print(f"  pathway: {sample.get('causal_pathway')}")
        print(f"  pathway_tags: {sample.get('pathway_tags')}")
        print(f"  aer_tags: {sample.get('aer_tags')}")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
