#!/usr/bin/env python3
"""Review evidence cards via Claude API — one call per card (Plan 15)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
from anthropic import Anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.variable_registry import full_review_registry_block  # noqa: E402

META = ROOT / "metadata"
RAW_DIR = ROOT / "data" / "evidence_cards" / "raw"
REVIEW_DIR = ROOT / "reports" / "claude_review"
RESULTS_DIR = REVIEW_DIR / "results"
BASELINE_INDEX = REVIEW_DIR / "baseline" / "preflight_by_card.json"
RUBRIC_PATH = ROOT / "scripts" / "reference" / "claude_card_review_rubric.md"
FINDING_SCHEMA_PATH = META / "claude_review_finding_schema.json"
CARD_SCHEMA_PATH = META / "evidence_card_schema.json"

load_dotenv(ROOT / ".env")

CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
REVIEW_DELAY_SECONDS = float(os.getenv("CLAUDE_REVIEW_DELAY_SECONDS", "0"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def parse_json_response(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


def git_commit_short() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def load_preflight_index() -> dict[str, list]:
    if not BASELINE_INDEX.exists():
        return {}
    with BASELINE_INDEX.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def policy_schema_excerpt(schema: dict) -> dict:
    props = schema.get("properties") or {}
    policy = props.get("confirmation_policy")
    if policy:
        return {"confirmation_policy": policy}
    return {}


def build_prompt(
    card: dict,
    *,
    rubric: str,
    finding_schema: dict,
    policy_excerpt: dict,
    preflight_rows: list,
) -> str:
    preflight_block = json.dumps(preflight_rows, indent=2, ensure_ascii=False) if preflight_rows else "[]"
    schema_block = json.dumps(finding_schema, indent=2)
    policy_block = json.dumps(policy_excerpt, indent=2)
    card_block = json.dumps(card, indent=2, ensure_ascii=False)

    return f"""You are reviewing an evidence card for semantic alignment between prose and executable logic.

Follow the rubric below. Priority: D3 (confirmation policy) → D1 (expression vs qualitative prose) → D4 (MCQ follow-ups) → D2 (time-series temporal, only when prose requires it) → D5.

Your main job: does each signal expression match its qualitative_description, explanation, and overall_reasoning_note? Does confirmation_policy match the note?

Deterministic preflight below already checks syntax/schema/registry. The variable catalog documents types. Do not re-flag type or indexing issues documented there — focus on prose ↔ logic mismatches.

## Rubric

{rubric}

## Output JSON schema (your response must validate against this)

{schema_block}

## confirmation_policy schema excerpt

{policy_block}

## Variable registry (allowed expression identifiers — complete list)

{full_review_registry_block()}

## Deterministic preflight findings for this card (already checked — do not repeat unless adding interpretation)

{preflight_block}

## Evidence card to review

{card_block}

## Instructions

Return ONLY a single JSON object matching the output schema. Set card_id to "{card.get("card_id", "")}".
Do not rewrite the entire card. Put fixes in findings[].suggested_patch as partial objects.

Focus findings on D3 (policy vs note), D1 (expression vs qualitative_description/explanation/note), and D4 (MCQ prose/effects).
Skip D1e/D2 unless you find a genuine prose contradiction — not catalog/type issues already documented below.
Do not flag signals that lack condition.expression when they are qualitative follow-up signals (MCQ choice effects set result at runtime).
Do not emit info-only findings for expected patterns (qualitative-only signals, variables[] sync).
soge_dev_percent and soge_class_name are static block-level values (not time series). Do not suggest temporal guards on SOGE.
For D3 policy fixes use suggested_patch.confirmation_policy only (full v1 object).
"""


def review_card(client: Anthropic, prompt: str) -> dict:
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_json_response(msg.content[0].text)


def card_pathway(stem: str) -> str:
    match = re.match(r"^(.*)__\d+$", stem)
    return match.group(1) if match else stem


def list_card_paths(
    *,
    pathway_prefix: str,
    card_ids: set[str],
    limit: int,
    per_pathway: int = 0,
) -> list[Path]:
    paths = sorted(RAW_DIR.glob("*.json"))
    if card_ids:
        paths = [p for p in paths if p.stem in card_ids]
    elif pathway_prefix:
        paths = [p for p in paths if p.stem.startswith(pathway_prefix)]
    if per_pathway and not card_ids:
        from collections import defaultdict

        groups: dict[str, list[Path]] = defaultdict(list)
        for path in paths:
            groups[card_pathway(path.stem)].append(path)
        paths = []
        for key in sorted(groups):
            paths.extend(sorted(groups[key])[:per_pathway])
    if limit:
        paths = paths[:limit]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Build prompts only; no API calls")
    parser.add_argument("--limit", type=int, default=0, help="Review only N cards")
    parser.add_argument(
        "--per-pathway",
        type=int,
        default=0,
        help="Review first N cards per unique production_system__stress__pathway (ignores --limit unless smaller)",
    )
    parser.add_argument("--pathway", default="", help="Filter card_id prefix (e.g. agriculture__water_scarcity__drought)")
    parser.add_argument("--resume", action="store_true", help="Skip cards with existing result JSON")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=None,
        help="Pause between API calls (default: CLAUDE_REVIEW_DELAY_SECONDS env or 0)",
    )
    parser.add_argument("--card-id", action="append", dest="card_ids", metavar="ID")
    parser.add_argument("--card-id-file", type=Path)
    parser.add_argument(
        "--run-preflight",
        action="store_true",
        help="Run scripts/review/run_preflight.py before reviewing",
    )
    args = parser.parse_args()

    delay_seconds = REVIEW_DELAY_SECONDS if args.delay_seconds is None else args.delay_seconds

    selected_ids: set[str] = set(args.card_ids or [])
    if args.card_id_file:
        lines = args.card_id_file.read_text(encoding="utf-8").splitlines()
        selected_ids.update(line.strip() for line in lines if line.strip() and not line.startswith("#"))

    if args.run_preflight:
        cmd = [sys.executable, str(ROOT / "scripts" / "review" / "run_preflight.py")]
        log.info("Running preflight: %s", " ".join(cmd))
        if subprocess.call(cmd, cwd=ROOT) != 0:
            log.warning("Preflight reported issues (continuing)")

    preflight_index = load_preflight_index()
    if not preflight_index and not args.dry_run:
        log.warning(
            "No preflight index at %s — run: python scripts/review/run_preflight.py",
            BASELINE_INDEX,
        )

    rubric = RUBRIC_PATH.read_text(encoding="utf-8")
    with FINDING_SCHEMA_PATH.open(encoding="utf-8") as handle:
        finding_schema = json.load(handle)
    with CARD_SCHEMA_PATH.open(encoding="utf-8") as handle:
        card_schema = json.load(handle)
    policy_excerpt = policy_schema_excerpt(card_schema)

    paths = list_card_paths(
        pathway_prefix=args.pathway,
        card_ids=selected_ids,
        limit=args.limit,
        per_pathway=args.per_pathway,
    )
    if not paths:
        log.error("No cards matched filters")
        return 1

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not args.dry_run and not api_key:
        log.error("ANTHROPIC_API_KEY is not set in .env")
        return 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    prompts_dir = REVIEW_DIR / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    client = Anthropic(api_key=api_key) if not args.dry_run else None
    processed = 0
    skipped = 0
    failed = 0

    log.info("Cards to review: %s", len(paths))
    if not args.dry_run:
        log.info("Model: %s", CLAUDE_MODEL)

    for n, path in enumerate(paths, start=1):
        with path.open(encoding="utf-8") as handle:
            card = json.load(handle)
        card_id = str(card.get("card_id") or path.stem)
        result_path = RESULTS_DIR / f"{card_id}.json"

        if args.resume and result_path.exists():
            log.info("[%s/%s] %s — skip (result exists)", n, len(paths), card_id)
            skipped += 1
            continue

        preflight_rows = preflight_index.get(card_id, [])
        prompt = build_prompt(
            card,
            rubric=rubric,
            finding_schema=finding_schema,
            policy_excerpt=policy_excerpt,
            preflight_rows=preflight_rows,
        )
        prompt_path = prompts_dir / f"{card_id}.prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        log.info("[%s/%s] %s (%s chars)", n, len(paths), card_id, len(prompt))

        if args.dry_run:
            continue

        try:
            result = review_card(client, prompt)  # type: ignore[arg-type]
            if str(result.get("card_id") or "") != card_id:
                result["card_id"] = card_id
            jsonschema.validate(result, finding_schema)
            result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            processed += 1
            if delay_seconds > 0 and n < len(paths):
                time.sleep(delay_seconds)
        except Exception as exc:
            failed += 1
            log.exception("Failed %s: %s", card_id, exc)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": CLAUDE_MODEL,
        "git_commit": git_commit_short(),
        "pathway_filter": args.pathway or None,
        "dry_run": args.dry_run,
        "planned": len(paths),
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
    }
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEW_DIR / "review_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    if args.dry_run:
        log.info("=== DRY RUN: %s prompt(s) in %s ===", len(paths), prompts_dir)
    else:
        log.info("=== Done: %s reviewed, %s skipped, %s failed ===", processed, skipped, failed)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
