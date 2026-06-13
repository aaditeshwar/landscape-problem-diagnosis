#!/usr/bin/env python3
"""Re-embed evidence cards using alias-augmented embedding text.

Default is dry-run (preview counts only). Pass --apply to call Ollama and update MongoDB.
Run scripts/maintenance/preview_card_embedding_text.py first and confirm with stakeholders.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import jsonschema
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from generate_evidence_cards import (  # noqa: E402
    CONTEXT_CLUSTERS,
    DB_NAME,
    EMBED_MODEL,
    RAW_DIR,
    embed_text,
    enrich_for_storage,
    load_json,
)
from reload_evidence_cards import build_doc, cluster_for_suffix, pathway_key_from_card_id  # noqa: E402
from lib.card_embedding_text import build_card_embedding_text, stamp_embedding_metadata  # noqa: E402

load_dotenv(ROOT / ".env")

COLLECTION = "evidence_cards"
META = ROOT / "metadata"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def iter_card_paths(prefix: str | None) -> list[Path]:
    paths = sorted(RAW_DIR.glob("*.json"))
    if prefix:
        paths = [p for p in paths if p.stem.startswith(prefix)]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", help="Only re-embed cards whose card_id starts with this prefix")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Call Ollama and write embeddings to MongoDB (default: dry-run)",
    )
    args = parser.parse_args()

    schema = load_json(META / "evidence_card_schema.json")
    paths = iter_card_paths(args.prefix)
    if not paths:
        log.error("No raw card JSON files matched")
        return 1

    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    db_client.admin.command("ping")
    col = db_client[DB_NAME][COLLECTION]

    ok = 0
    failed = 0
    for n, path in enumerate(paths, start=1):
        card = json.loads(path.read_text(encoding="utf-8"))
        card_id = card.get("card_id") or path.stem
        suffix = card_id.rsplit("__", 1)[-1]
        pathway_key = pathway_key_from_card_id(card_id)
        cluster = next((c for c in CONTEXT_CLUSTERS if c["suffix"] == suffix), None)
        if cluster is None:
            log.error("[%s/%s] %s: unknown cluster suffix %s", n, len(paths), card_id, suffix)
            failed += 1
            continue

        try:
            jsonschema.validate(card, schema)
        except jsonschema.ValidationError as exc:
            log.error("[%s/%s] %s: schema invalid: %s", n, len(paths), card_id, exc.message)
            failed += 1
            continue

        existing = col.find_one({"_id": card_id})
        doc = build_doc(card, pathway_key, cluster, existing)
        stamp_embedding_metadata(doc)
        text = build_card_embedding_text(doc)

        if not args.apply:
            log.info(
                "[%s/%s] %s OK (dry run) chars=%s aliases=%s",
                n,
                len(paths),
                card_id,
                len(text),
                doc.get("metadata", {}).get("semantic_alias_count", 0),
            )
            ok += 1
            continue

        try:
            doc["embedding"] = embed_text(text)
            doc["embedding_model"] = EMBED_MODEL
            col.replace_one({"_id": card_id}, doc, upsert=True)
            log.info("[%s/%s] %s re-embedded", n, len(paths), card_id)
            ok += 1
        except Exception as exc:
            log.error("[%s/%s] %s failed: %s", n, len(paths), card_id, exc)
            failed += 1

    db_client.close()
    mode = "re-embedded" if args.apply else "previewed"
    log.info("=== Done: %s %s, %s failed ===", ok, mode, failed)
    if not args.apply:
        log.info("Pass --apply to write embeddings after review")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
