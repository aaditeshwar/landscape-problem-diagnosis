"""Audit paper_chunks coverage for include_in_corpus papers with PDFs."""

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
load_dotenv(ROOT / ".env")
MANIFEST = ROOT / "data" / "papers" / "fetch_manifest.json"
PDF_DIR = ROOT / "data" / "papers" / "pdfs"

BATCH_TAGS = {
    "ntfp_forest_biodiversity__ntfp_decline__forest_degradation",
    "ntfp_forest_biodiversity__ntfp_decline__encroachment",
    "socio_economic__economic_hardship__multi_sector_vulnerability",
    "socio_economic__low_income__small_landholding",
}


def main() -> int:
    load_dotenv(ROOT / ".env")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    papers = manifest.get("papers") or {}

    eligible = sorted(
        pid
        for pid, entry in papers.items()
        if entry.get("include_in_corpus", True) and (PDF_DIR / f"{pid}.pdf").exists()
    )

    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000)
    col = client["diagnosis_db"]["paper_chunks"]

    complete: list[str] = []
    partial_embed: list[tuple[str, int, int, int]] = []
    no_chunks: list[str] = []

    for pid in eligible:
        total = col.count_documents({"paper_id": pid})
        if total == 0:
            no_chunks.append(pid)
            continue
        embedded = col.count_documents(
            {"paper_id": pid, "embedding": {"$exists": True, "$ne": []}}
        )
        if embedded == total:
            complete.append(pid)
        else:
            partial_embed.append((pid, total, embedded, total - embedded))

    print("=== Eligible corpus audit (include_in_corpus=true + PDF on disk) ===")
    print(f"Eligible papers:            {len(eligible)}")
    print(f"Fully chunked + embedded:   {len(complete)}")
    print(f"Chunked with missing embed: {len(partial_embed)}")
    print(f"No chunks at all:           {len(no_chunks)}")

    if no_chunks:
        print("\n--- No chunks ---")
        for pid in no_chunks:
            title = (papers.get(pid, {}).get("title") or "")[:70]
            print(f"  {pid}: {title}")

    if partial_embed:
        print("\n--- Incomplete embeddings (total / embedded / missing) ---")
        for pid, total, embedded, missing in partial_embed:
            title = (papers.get(pid, {}).get("title") or "")[:60]
            print(f"  {pid}: {total}/{embedded}/{missing} | {title}")

    batch_eligible = [
        p
        for p in eligible
        if any(t in (papers[p].get("pathway_tags") or []) for t in BATCH_TAGS)
    ]
    batch_complete = [p for p in batch_eligible if p in complete]
    print("\n=== NTFP + Socio batch (eligible with PDF) ===")
    print(f"Eligible: {len(batch_eligible)}")
    print(f"Fully embedded: {len(batch_complete)}")
    print(f"Gaps: {len(batch_eligible) - len(batch_complete)}")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
