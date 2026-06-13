"""
chunk_and_embed.py
==================
Extract text from selected PDFs, chunk, embed via Ollama nomic-embed-text,
and upsert into MongoDB paper_chunks.

Only processes papers where fetch_manifest.json has:
  include_in_corpus: true  AND  PDF file exists on disk

Usage:
    # Dry run — extract/chunk only, no Ollama or MongoDB writes
    python scripts/chunk_and_embed.py --dry-run

    # Smoke test on GPU machine (1 paper, real embed + DB write)
    python scripts/chunk_and_embed.py --limit 1

    # Full run — all include_in_corpus papers with PDFs on disk
    python scripts/chunk_and_embed.py

Set OLLAMA_URL in .env to point at your GPU machine before the main run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data" / "papers" / "fetch_manifest.json"
META_DIR = ROOT / "data" / "papers" / "metadata"
PDF_DIR = ROOT / "data" / "papers" / "pdfs"
DB_NAME = "diagnosis_db"
COLLECTION = "paper_chunks"

load_dotenv(ROOT / ".env")

CHUNK_WORDS = 512
OVERLAP_WORDS = 128
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
# nomic-embed-text context is ~2048 tokens; dense PDF text can exceed 8000 chars.
EMBED_CHAR_LIMIT = int(os.getenv("OLLAMA_EMBED_CHAR_LIMIT", "6000"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def selected_papers_with_pdf(manifest: dict) -> list[str]:
    papers = manifest.get("papers", {})
    ids = []
    for pid, entry in papers.items():
        if not entry.get("include_in_corpus", True):
            continue
        if (PDF_DIR / f"{pid}.pdf").exists():
            ids.append(pid)
    return sorted(ids)


def load_paper_meta(paper_id: str) -> dict | None:
    path = META_DIR / f"{paper_id}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def extract_pdf_text(pdf_path: Path) -> tuple[str, dict[int, str]]:
    """Return full text and page_num -> page_text mapping."""
    pages: dict[int, str] = {}
    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages[i] = text
                parts.append(text)
    return "\n\n".join(parts), pages


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)  # strip simple HTML entities/tags
    text = re.sub(r"\s+", " ", text).strip()
    return text


def word_chunks(text: str, size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + size)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = max(0, end - overlap)
    return chunks


def page_for_offset(char_offset: int, page_texts: list[tuple[int, str]]) -> int | None:
    cumulative = 0
    for page_num, text in page_texts:
        cumulative += len(text) + 2
        if char_offset < cumulative:
            return page_num
    return page_texts[-1][0] if page_texts else None


def embed_text(prompt: str, retries: int = 3) -> list[float]:
    payload_text = prompt[:EMBED_CHAR_LIMIT]
    last_exc = None
    for attempt in range(retries):
        try:
            r = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": payload_text},
                timeout=120,
            )
            if not r.ok:
                detail = r.text[:300]
                try:
                    detail = r.json().get("error", detail)
                except Exception:
                    pass
                raise requests.HTTPError(f"{r.status_code} {detail}", response=r)
            return r.json()["embedding"]
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise last_exc  # type: ignore[misc]


def chunk_id(paper_id: str, kind: str, index: int) -> str:
    return f"{paper_id}__{kind}__{index:04d}"


def build_chunks(paper_id: str, meta: dict, pdf_path: Path) -> list[dict]:
    full_text, page_map = extract_pdf_text(pdf_path)
    full_text = normalize_whitespace(full_text)
    abstract = normalize_whitespace(meta.get("abstract") or "")
    title = meta.get("title") or ""
    pathway_tags = meta.get("pathway_tags") or []

    page_list = sorted(page_map.items())

    # Body text: remove abstract substring if present to reduce duplication
    body_text = full_text
    if abstract and len(abstract) > 80 and abstract[:120] in full_text:
        body_text = full_text.replace(abstract, " ", 1).strip()
    elif abstract and len(abstract) > 80:
        body_text = full_text

    chunks: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    if abstract:
        chunks.append({
            "_id": chunk_id(paper_id, "abstract", 0),
            "paper_id": paper_id,
            "chunk_type": "abstract",
            "chunk_index": 0,
            "text": abstract,
            "title": title,
            "pathway_tags": pathway_tags,
            "aer_tags": [],
            "aquifer_tags": [],
            "rainfall_regime": None,
            "page": None,
            "section_heading": "Abstract",
            "retrieval_weight": 2.0,
            "created_at": now,
        })

    for i, text in enumerate(word_chunks(body_text, CHUNK_WORDS, OVERLAP_WORDS)):
        chunks.append({
            "_id": chunk_id(paper_id, "body", i),
            "paper_id": paper_id,
            "chunk_type": "body",
            "chunk_index": i,
            "text": text,
            "title": title,
            "pathway_tags": pathway_tags,
            "aer_tags": [],
            "aquifer_tags": [],
            "rainfall_regime": None,
            "page": None,
            "section_heading": None,
            "retrieval_weight": 1.0,
            "created_at": now,
        })

    return chunks


def ensure_indexes(db) -> None:
    col = db[COLLECTION]
    col.create_index("paper_id")
    col.create_index("pathway_tags")
    log.info("Indexes ensured on paper_chunks")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunk and embed selected papers")
    parser.add_argument("--dry-run", action="store_true", help="Extract/chunk only; no embed or DB")
    parser.add_argument("--limit", type=int, default=0, help="Process only N papers (smoke test)")
    parser.add_argument("--force", action="store_true", help="Re-process papers already in paper_chunks")
    args = parser.parse_args()

    manifest = load_manifest()
    paper_ids = selected_papers_with_pdf(manifest)
    if args.limit:
        paper_ids = paper_ids[: args.limit]

    if not paper_ids:
        log.error("No selected papers with PDFs found.")
        return 1

    log.info(f"Processing {len(paper_ids)} paper(s) with PDFs (include_in_corpus=true)")
    log.info(f"Ollama: {OLLAMA_URL}  model: {EMBED_MODEL}")
    if args.dry_run:
        log.info("DRY RUN — no embeddings or MongoDB writes")

    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[DB_NAME]
    ensure_indexes(db)
    col = db[COLLECTION]

    total_chunks = 0
    total_embedded = 0
    skipped = 0

    for n, paper_id in enumerate(paper_ids, start=1):
        meta = load_paper_meta(paper_id)
        pdf_path = PDF_DIR / f"{paper_id}.pdf"
        if not meta or not pdf_path.exists():
            log.warning(f"Missing meta or PDF for {paper_id}")
            continue

        stored = col.count_documents({"paper_id": paper_id})

        log.info(f"[{n}/{len(paper_ids)}] Chunking {paper_id}...")
        try:
            chunks = build_chunks(paper_id, meta, pdf_path)
        except Exception as exc:
            log.warning(f"  Failed to extract {paper_id}: {exc}")
            continue

        if not chunks:
            log.warning(f"  No text extracted for {paper_id}")
            continue

        if not args.force and stored >= len(chunks) and stored > 0:
            log.info(f"  Skip {paper_id} ({stored} chunks, complete)")
            skipped += 1
            continue

        log.info(f"  {len(chunks)} chunk(s)")
        total_chunks += len(chunks)

        if args.dry_run:
            continue

        if stored > 0:
            col.delete_many({"paper_id": paper_id})
            if stored < len(chunks):
                log.info(f"  Replacing incomplete set ({stored}/{len(chunks)} chunks were stored)")

        ops: list[UpdateOne] = []
        embed_failed = 0
        for ch in chunks:
            try:
                ch["embedding"] = embed_text(ch["text"])
                total_embedded += 1
            except Exception as exc:
                embed_failed += 1
                log.warning(f"  Embed failed {ch['_id']}: {exc}")
                continue
            ops.append(UpdateOne({"_id": ch["_id"]}, {"$set": ch}, upsert=True))

        if ops:
            col.bulk_write(ops)
            log.info(f"  Stored {len(ops)} chunk(s) in MongoDB")
        if embed_failed:
            log.warning(f"  {embed_failed} chunk(s) failed to embed for {paper_id}")

    if not args.dry_run:
        db_count = col.count_documents({})
        log.info(f"=== Done: {total_chunks} chunks built, {total_embedded} embedded, {skipped} papers skipped ===")
        log.info(f"  paper_chunks collection size: {db_count}")
    else:
        log.info(f"=== DRY RUN: {total_chunks} chunks would be built ===")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
