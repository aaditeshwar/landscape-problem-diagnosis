#!/usr/bin/env python3
"""Reload evidence cards from data/evidence_cards/raw into Mongo with fresh embeddings."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import jsonschema
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "scripts"))

from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from services.card_embedding_text import card_embed_text, stamp_embedding_metadata  # noqa: E402

from generate_evidence_cards import (  # noqa: E402
    CONTEXT_CLUSTERS,
    DB_NAME,
    RAW_DIR,
    card_id_for,
    embed_text,
    enrich_for_storage,
    load_json,
)

load_dotenv(ROOT / ".env")

COLLECTION = "evidence_cards"
META = ROOT / "metadata"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def pathway_key_from_card_id(card_id: str) -> str:
    parts = card_id.rsplit("__", 1)
    if len(parts) != 2:
        raise ValueError(f"Unexpected card_id: {card_id}")
    return parts[0]


def cluster_for_suffix(suffix: str) -> dict | None:
    for cluster in CONTEXT_CLUSTERS:
        if cluster["suffix"] == suffix:
            return cluster
    return None


def build_doc(card: dict, pathway_key: str, cluster: dict, existing: dict | None) -> dict:
    doc = enrich_for_storage(card, pathway_key, cluster)
    doc["metadata"]["last_updated"] = date.today().isoformat()
    if existing:
        for key in (
            "pathway_tags",
            "aer_tags",
            "aquifer_tags",
            "rainfall_regime",
            "review_weight",
            "context_cluster",
        ):
            if key in existing:
                doc[key] = existing[key]
        if existing.get("metadata"):
            for key in ("created_at", "created_by", "extraction_model"):
                if key in existing["metadata"]:
                    doc["metadata"][key] = existing["metadata"][key]
    return doc


def iter_card_paths(prefix: str | None) -> list[Path]:
    paths = sorted(RAW_DIR.glob("*.json"))
    if prefix:
        paths = [p for p in paths if p.stem.startswith(prefix)]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        help="Only reload cards whose card_id starts with this prefix",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate only; no embed or DB writes")
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
        cluster = cluster_for_suffix(suffix)
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

        if args.dry_run:
            log.info("[%s/%s] %s OK (dry run)", n, len(paths), card_id)
            ok += 1
            continue

        try:
            doc["embedding"] = embed_text(card_embed_text(doc))
            doc["embedding_model"] = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
            col.replace_one({"_id": card_id}, doc, upsert=True)
            log.info("[%s/%s] %s reloaded", n, len(paths), card_id)
            ok += 1
        except Exception as exc:
            log.error("[%s/%s] %s failed: %s", n, len(paths), card_id, exc)
            failed += 1

    db_client.close()
    log.info("=== Done: %s reloaded, %s failed ===", ok, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
