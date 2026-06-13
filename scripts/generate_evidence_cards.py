"""
generate_evidence_cards.py
==========================
Extract schema-validated evidence cards from paper chunks via Claude API,
embed with Ollama, and upsert into MongoDB evidence_cards.

One card per pathway x agro-ecological context cluster (aquifer + AER + rainfall).

Usage:
    python scripts/generate_evidence_cards.py --dry-run
    python scripts/generate_evidence_cards.py --limit 1
    python scripts/generate_evidence_cards.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import jsonschema
import requests
from anthropic import Anthropic
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from lib.card_embedding_text import (  # noqa: E402
    aliases_for_pathway,
    card_embed_text,
    format_alias_paragraph,
    stamp_embedding_metadata,
)

META = ROOT / "metadata"
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
DB_NAME = "diagnosis_db"
COLLECTION = "evidence_cards"

load_dotenv(ROOT / ".env")

EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
EMBED_CHAR_LIMIT = int(os.getenv("OLLAMA_EMBED_CHAR_LIMIT", "6000"))
CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
DEFAULT_PATHWAY_PREFIX = "agriculture__water_scarcity"
MAX_CHUNKS_PER_PATHWAY = 12
MAX_CHUNK_CHARS = 2500

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Context clusters for card generation (pathway × cluster).
CONTEXT_CLUSTERS = [
    {
        "suffix": "001",
        "label": "Deccan basalt semi-arid (Vidarbha/Marathwada)",
        "aquifer_types": ["hard_rock"],
        "aer_tags": ["AER-6"],
        "rainfall_regime": "semi-arid",
        "agro_climatic_zones": ["semi-arid"],
        "terrain_types": ["plateau", "plains"],
        "geographic_examples": ["Vidarbha Maharashtra", "Marathwada", "Telangana"],
    },
    {
        "suffix": "002",
        "label": "Peninsular crystalline semi-arid",
        "aquifer_types": ["hard_rock"],
        "aer_tags": ["AER-7", "AER-8"],
        "rainfall_regime": "semi-arid",
        "agro_climatic_zones": ["semi-arid"],
        "terrain_types": ["plateau", "hilly"],
        "geographic_examples": ["Andhra Pradesh", "Karnataka interior", "Odisha"],
    },
    {
        "suffix": "003",
        "label": "Indo-Gangetic alluvial sub-humid",
        "aquifer_types": ["alluvium"],
        "aer_tags": ["AER-9"],
        "rainfall_regime": "sub-humid",
        "agro_climatic_zones": ["sub-humid"],
        "terrain_types": ["plains"],
        "geographic_examples": ["Punjab", "Haryana", "western Uttar Pradesh"],
    },
    {
        "suffix": "004",
        "label": "Rajasthan-Gujarat arid alluvial",
        "aquifer_types": ["alluvium"],
        "aer_tags": ["AER-2", "AER-4"],
        "rainfall_regime": "arid",
        "agro_climatic_zones": ["arid", "semi-arid"],
        "terrain_types": ["plains", "slopes"],
        "geographic_examples": ["Rajasthan", "Kachchh Gujarat", "Haryana arid belt"],
    },
    {
        "suffix": "005",
        "label": "Bundelkhand sedimentary sub-humid",
        "aquifer_types": ["semi-consolidated"],
        "aer_tags": ["AER-10"],
        "rainfall_regime": "sub-humid",
        "agro_climatic_zones": ["sub-humid"],
        "terrain_types": ["plateau", "slopes"],
        "geographic_examples": ["Bundelkhand UP/MP", "Madhya Pradesh Malwa"],
    },
    {
        "suffix": "006",
        "label": "Coastal alluvial sub-humid",
        "aquifer_types": ["coastal", "alluvium"],
        "aer_tags": ["AER-18"],
        "rainfall_regime": "sub-humid",
        "agro_climatic_zones": ["sub-humid", "semi-arid"],
        "terrain_types": ["plains"],
        "geographic_examples": ["coastal Tamil Nadu", "coastal Andhra Pradesh", "Odisha coast"],
    },
]


def load_json(path: Path) -> dict | list:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


PRODUCTION_SYSTEM_KEYS = {
    "agriculture": "Agriculture",
    "livestock": "Livestock",
    "ntfp_forest_biodiversity": "NTFP_Forest_Biodiversity",
    "socio_economic": "Socio_Economic",
    "fishery": "Fishery",
}


def card_id_for(pathway_key: str, cluster_suffix: str) -> str:
    return f"{pathway_key}__{cluster_suffix}"


def pathway_keys(prefix: str) -> list[str]:
    queries = load_json(META / "pathway_queries.json")
    return sorted(k for k in queries.get("pathways", {}) if k.startswith(prefix))


def pathway_framework_info(pathway_key: str) -> dict:
    """Return pathway metadata from diagnosis_framework.json."""
    parts = pathway_key.split("__")
    if len(parts) != 3:
        raise ValueError(f"Unexpected pathway key: {pathway_key}")
    system_map = PRODUCTION_SYSTEM_KEYS
    production_system = system_map.get(parts[0], parts[0].title())
    stress, pathway = parts[1], parts[2]

    framework = load_json(META / "diagnosis_framework.json")["diagnosis_framework"]
    ps = framework["production_systems"][production_system]
    stress_obj = ps["observed_stresses"][stress]
    pathway_obj = stress_obj["causal_pathways"][pathway]
    return {
        "production_system": production_system,
        "observed_stress": stress,
        "causal_pathway": pathway,
        "pathway_key": pathway_key,
        "description": pathway_obj.get("description", ""),
        "diagnostic_variables": pathway_obj.get("diagnostic_variables", []),
        "solutions": pathway_obj.get("solutions", []),
        "stress_description": stress_obj.get("description", ""),
    }


def aer_reference_snippet(aer_tags: list[str]) -> str:
    standards = load_json(META / "reference_standards.json")
    regions = standards["nbss_lup_agro_ecological_regions"]["regions"]
    lines = []
    for tag in aer_tags:
        info = regions.get(tag, {})
        if info:
            lines.append(
                f"{tag}: {info.get('name')} | states={info.get('states')} | "
                f"rainfall={info.get('rainfall_mm')}mm | aquifer={info.get('dominant_aquifer')}"
            )
    return "\n".join(lines)


def fetch_paper_chunks(db, pathway_key: str, limit: int = MAX_CHUNKS_PER_PATHWAY) -> list[dict]:
    col = db["paper_chunks"]
    cursor = (
        col.find(
            {"pathway_tags": pathway_key},
            {"text": 1, "title": 1, "chunk_type": 1, "paper_id": 1, "retrieval_weight": 1},
        )
        .sort([("retrieval_weight", -1), ("chunk_type", 1)])
        .limit(limit)
    )
    return list(cursor)


def format_chunks_for_prompt(chunks: list[dict]) -> str:
    parts = []
    for i, ch in enumerate(chunks, start=1):
        text = (ch.get("text") or "")[:MAX_CHUNK_CHARS]
        parts.append(
            f"[Chunk {i}] paper={ch.get('paper_id')} type={ch.get('chunk_type')} "
            f"title={ch.get('title', '')[:120]}\n{text}"
        )
    return "\n\n".join(parts)


def build_prompt(
    pathway_info: dict,
    cluster: dict,
    chunks: list[dict],
    schema: dict,
    example: list,
) -> str:
    vars_block = json.dumps(pathway_info["diagnostic_variables"], indent=2)
    solutions = json.dumps(pathway_info["solutions"], indent=2)
    example_card = json.dumps(example[0], indent=2)
    context_json = json.dumps(
        {
            "agro_climatic_zones": cluster["agro_climatic_zones"],
            "aquifer_types": cluster["aquifer_types"],
            "terrain_types": cluster["terrain_types"],
            "rainfall_regime": cluster["rainfall_regime"],
            "geographic_examples": cluster["geographic_examples"],
        },
        indent=2,
    )
    card_id = card_id_for(pathway_info["pathway_key"], cluster["suffix"])
    alias_preview = format_alias_paragraph(aliases_for_pathway(pathway_info["causal_pathway"]))
    alias_note = ""
    if alias_preview:
        alias_note = (
            f"\nSemantic aliases (appended at embed time, not in card JSON):\n"
            f"{alias_preview[:400]}{'...' if len(alias_preview) > 400 else ''}\n"
        )

    return f"""You are extracting one evidence card for an agro-ecological diagnosis system in India.

Return ONLY a single JSON object (no markdown fences) matching the EvidenceCard schema.

Required card_id: {card_id}
Production system: {pathway_info['production_system']}
Observed stress: {pathway_info['observed_stress']}
Causal pathway: {pathway_info['causal_pathway']}

Pathway description: {pathway_info['description']}
Stress description: {pathway_info['stress_description']}

Target context (use exactly these context field values):
{context_json}

AER reference for this context:
{aer_reference_snippet(cluster['aer_tags'])}

Diagnostic variables from the framework (use these variable names in signals):
{vars_block}

Recommended solutions for this pathway:
{solutions}

Rules:
- Include 3-5 diagnostic_signals using available variables where possible.
- For variables marked availability not_available, add missing_variable_questions.
- Include 1-2 confounders distinguishing this pathway from alternatives.
- Ground claims in the paper excerpts below; cite sources with realistic source_id citekeys.
- Each source source_type must be exactly one of: peer_reviewed_journal, government_report, ngo_report, grey_literature, expert_guideline, book_chapter (use grey_literature for theses/working papers).
- Each diagnostic_signals[].condition.type must be exactly one of: quantitative, qualitative, trend, composite (use composite for multi-part conditions, not "compound").
- Set metadata.created_by to "llm_extraction_v1", reviewed_by_expert to false,
  extraction_model to "{CLAUDE_MODEL}", confidence_overall to medium/high/low as appropriate,
  created_at and last_updated to today's date.
- At embedding time, semantic aliases from metadata/semantic_aliases.json are appended
  automatically for pathway "{pathway_info['causal_pathway']}" — do not duplicate alias
  phrases in overall_reasoning_note.

Example card (structure reference):
{example_card}

Paper excerpts:
{format_chunks_for_prompt(chunks)}
{alias_note}
JSON schema summary (required top-level keys):
{json.dumps(schema.get('required', []))}
"""


def normalize_card(card: dict, schema: dict) -> dict:
    """Map LLM field values outside schema enums to allowed values."""
    props = schema.get("properties", {})

    source_allowed = (
        props.get("sources", {})
        .get("items", {})
        .get("properties", {})
        .get("source_type", {})
        .get("enum", [])
    )
    source_aliases = {
        "thesis": "grey_literature",
        "dissertation": "grey_literature",
        "phd_thesis": "grey_literature",
        "masters_thesis": "grey_literature",
        "policy_report": "government_report",
        "policy_brief": "government_report",
        "working_paper": "grey_literature",
        "report": "grey_literature",
        "journal_article": "peer_reviewed_journal",
        "research_article": "peer_reviewed_journal",
        "book": "book_chapter",
    }
    if source_allowed:
        for source in card.get("sources") or []:
            if not isinstance(source, dict):
                continue
            raw = str(source.get("source_type") or "").strip().lower().replace(" ", "_").replace("-", "_")
            if raw in source_allowed:
                source["source_type"] = raw
            elif raw in source_aliases:
                source["source_type"] = source_aliases[raw]
            else:
                source["source_type"] = "grey_literature"

    condition_allowed = (
        props.get("diagnostic_signals", {})
        .get("items", {})
        .get("properties", {})
        .get("condition", {})
        .get("properties", {})
        .get("type", {})
        .get("enum", [])
    )
    condition_aliases = {
        "compound": "composite",
        "combined": "composite",
        "multi": "composite",
        "multi_part": "composite",
    }
    if condition_allowed:
        for signal in card.get("diagnostic_signals") or []:
            if not isinstance(signal, dict):
                continue
            condition = signal.get("condition")
            if not isinstance(condition, dict):
                continue
            raw = str(condition.get("type") or "").strip().lower().replace(" ", "_").replace("-", "_")
            if raw in condition_allowed:
                condition["type"] = raw
            elif raw in condition_aliases:
                condition["type"] = condition_aliases[raw]
            else:
                condition["type"] = "qualitative"

    return card


def parse_json_response(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


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


def enrich_for_storage(card: dict, pathway_key: str, cluster: dict) -> dict:
    today = date.today().isoformat()
    meta = card.setdefault("metadata", {})
    meta.setdefault("created_by", "llm_extraction_v1")
    meta.setdefault("reviewed_by_expert", False)
    meta.setdefault("created_at", today)
    meta.setdefault("last_updated", today)
    meta.setdefault("extraction_model", CLAUDE_MODEL)

    doc = dict(card)
    doc["_id"] = card["card_id"]
    doc["pathway_tags"] = [pathway_key]
    doc["aer_tags"] = cluster["aer_tags"]
    doc["aquifer_tags"] = cluster["aquifer_types"]
    doc["rainfall_regime"] = cluster["rainfall_regime"]
    doc["review_weight"] = 1.0
    doc["context_cluster"] = cluster["label"]
    stamp_embedding_metadata(doc)
    return doc


def generate_card(client: Anthropic, prompt: str) -> dict:
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text
    return parse_json_response(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate evidence cards via Claude API")
    parser.add_argument("--dry-run", action="store_true", help="Build prompts only; no API or DB")
    parser.add_argument("--limit", type=int, default=0, help="Generate only N cards (smoke test)")
    parser.add_argument("--force", action="store_true", help="Replace existing cards with same card_id")
    parser.add_argument(
        "--pathway-prefix",
        default=DEFAULT_PATHWAY_PREFIX,
        help=f"Pathway key prefix filter (default: {DEFAULT_PATHWAY_PREFIX})",
    )
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not args.dry_run and not api_key:
        log.error("ANTHROPIC_API_KEY is not set in .env")
        return 1

    schema = load_json(META / "evidence_card_schema.json")
    example = load_json(META / "evidence_card_example.json")
    pathways = pathway_keys(args.pathway_prefix)
    if not pathways:
        log.error(f"No pathways match prefix '{args.pathway_prefix}'")
        return 1

    jobs: list[tuple[str, dict]] = []
    for pathway_key in pathways:
        info = pathway_framework_info(pathway_key)
        for cluster in CONTEXT_CLUSTERS:
            jobs.append((pathway_key, cluster))

    if args.limit:
        jobs = jobs[: args.limit]

    log.info(f"Pathways: {len(pathways)}  context clusters: {len(CONTEXT_CLUSTERS)}")
    log.info(f"Planned cards: {len(jobs)}")
    if not args.dry_run:
        log.info(f"Claude model: {CLAUDE_MODEL}  Ollama: {OLLAMA_URL}")

    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    db_client.admin.command("ping")
    db = db_client[DB_NAME]
    col = db[COLLECTION]
    col.create_index("pathway_tags")
    col.create_index("aer_tags")
    col.create_index("aquifer_tags")

    claude = Anthropic(api_key=api_key) if not args.dry_run else None
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0
    failed = 0

    for n, (pathway_key, cluster) in enumerate(jobs, start=1):
        info = pathway_framework_info(pathway_key)
        card_id = card_id_for(pathway_key, cluster["suffix"])
        log.info(f"[{n}/{len(jobs)}] {card_id} ({cluster['label']})")

        if not args.force and col.count_documents({"_id": card_id}, limit=1):
            log.info("  Skip (already exists)")
            skipped += 1
            continue

        chunks = fetch_paper_chunks(db, pathway_key)
        if not chunks:
            log.warning(f"  No paper chunks for {pathway_key}; skipping")
            failed += 1
            continue

        prompt = build_prompt(info, cluster, chunks, schema, example)
        raw_path = RAW_DIR / f"{card_id}.prompt.txt"
        raw_path.write_text(prompt, encoding="utf-8")

        if args.dry_run:
            log.info(f"  Dry run — prompt saved ({len(chunks)} chunks, {len(prompt)} chars)")
            continue

        try:
            card = generate_card(claude, prompt)  # type: ignore[arg-type]
            card = normalize_card(card, schema)
            jsonschema.validate(card, schema)
            doc = enrich_for_storage(card, pathway_key, cluster)
            if doc["card_id"] != card_id:
                log.warning(f"  Model returned card_id={doc['card_id']}; expected {card_id}")
                doc["card_id"] = card_id
                doc["_id"] = card_id

            doc["embedding"] = embed_text(card_embed_text(doc))
            doc["embedding_model"] = EMBED_MODEL
            col.replace_one({"_id": card_id}, doc, upsert=True)
            (RAW_DIR / f"{card_id}.json").write_text(
                json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            log.info("  Stored in evidence_cards")
            generated += 1
        except Exception as exc:
            failed += 1
            log.error(f"  Failed: {exc}")

    if args.dry_run:
        log.info(f"=== DRY RUN: {len(jobs)} prompts prepared in {RAW_DIR} ===")
    else:
        total = col.count_documents({})
        log.info(
            f"=== Done: {generated} generated, {skipped} skipped, {failed} failed ==="
        )
        log.info(f"  evidence_cards collection size: {total}")

    db_client.close()
    return 0 if failed == 0 or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
