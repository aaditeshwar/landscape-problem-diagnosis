"""Verify paper_chunks in MongoDB."""

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
    db = client["diagnosis_db"]
    col = db["paper_chunks"]

    total = col.count_documents({})
    papers = col.distinct("paper_id")
    abstract = col.count_documents({"chunk_type": "abstract"})
    body = col.count_documents({"chunk_type": "body"})
    with_emb = col.count_documents({"embedding": {"$exists": True, "$ne": []}})

    print("=== paper_chunks status ===")
    print(f"  Total chunks:     {total}")
    print(f"  Unique papers:    {len(papers)}")
    print(f"  Abstract chunks:  {abstract}")
    print(f"  Body chunks:      {body}")
    print(f"  With embeddings:  {with_emb}")

    sample = col.find_one({"chunk_type": "abstract"}, {"paper_id": 1, "text": 1, "pathway_tags": 1})
    if sample:
        print("\n=== Sample abstract chunk ===")
        print(f"  paper_id: {sample.get('paper_id')}")
        print(f"  pathway_tags: {sample.get('pathway_tags')}")
        print(f"  text: {(sample.get('text') or '')[:120]}...")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
