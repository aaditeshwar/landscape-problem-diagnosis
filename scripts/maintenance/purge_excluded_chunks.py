"""Remove paper_chunks for papers marked include_in_corpus=false in fetch_manifest.json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

from dotenv import load_dotenv
from pymongo import MongoClient

bootstrap()
MANIFEST = ROOT / "data" / "papers" / "fetch_manifest.json"
PDF_DIR = ROOT / "data" / "papers" / "pdfs"


def main() -> int:
    load_dotenv(ROOT / ".env")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    papers = manifest.get("papers") or {}
    excluded = {pid for pid, entry in papers.items() if entry.get("include_in_corpus") is False}

    excluded_with_pdf = [
        pid
        for pid in excluded
        if papers[pid].get("pdf_downloaded") or (PDF_DIR / f"{pid}.pdf").exists()
    ]

    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    col = client["diagnosis_db"]["paper_chunks"]

    chunk_paper_ids = set(col.distinct("paper_id"))
    to_purge = sorted(chunk_paper_ids & excluded)

    print("=== Excluded papers with PDF on disk ===")
    print(f"  Count: {len(excluded_with_pdf)}")
    print("\n=== Excluded papers with chunks in MongoDB ===")
    if not to_purge:
        print("  None — corpus is already clean.")
        client.close()
        return 0

    total_chunks = 0
    for pid in to_purge:
        n = col.count_documents({"paper_id": pid})
        total_chunks += n
        entry = papers.get(pid, {})
        print(f"  {pid}: {n} chunk(s) | pdf_downloaded={entry.get('pdf_downloaded')} | {(entry.get('title') or '')[:70]}")

    result = col.delete_many({"paper_id": {"$in": to_purge}})
    remaining = col.count_documents({"paper_id": {"$in": list(excluded)}})

    print(f"\nDeleted {result.deleted_count} chunk document(s) across {len(to_purge)} paper(s).")
    print(f"Remaining chunks tied to excluded papers: {remaining}")
    print(f"Total paper_chunks now: {col.count_documents({})}")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
