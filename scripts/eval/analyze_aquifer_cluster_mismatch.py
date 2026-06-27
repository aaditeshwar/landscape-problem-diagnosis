#!/usr/bin/env python3
"""Analyze MWS → evidence-card cluster aquifer mismatches under server diagnosis retrieval."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = ROOT / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

load_dotenv(ROOT / ".env")

from db import get_db  # noqa: E402
from services.aquifer_classification import (  # noqa: E402
    aquifer_tag_similarity,
    card_aquifer_tag_from_evidence_card,
    card_aquifer_tags_for_mws,
)
from services.context_clusters import cluster_by_suffix  # noqa: E402
from services.mws_enrich import enrich_mws_doc  # noqa: E402
from services.retriever import (  # noqa: E402
    AER_RETRIEVAL_NEIGHBORS,
    _card_aer_tag,
    clear_aer_aquifer_inventory_cache,
    load_mws_scoped_evidence_cards,
)

CARD_SUFFIX_RE = re.compile(r"__(\d{3})$")


def _cluster_aquifer_tags(cluster: dict) -> set[str]:
    return {str(t) for t in (cluster.get("aquifer_types") or [])}


def _mws_card_aquifer_tag(mws_doc: dict) -> str | None:
    tags = card_aquifer_tags_for_mws(mws_doc)
    return tags[0] if tags else None


def _card_suffix(card_id: str | None) -> str | None:
    match = CARD_SUFFIX_RE.search(str(card_id or ""))
    return match.group(1) if match else None


def _literal_aquifer_classes_in_card(card: dict) -> set[str]:
    literals: set[str] = set()
    for signal in card.get("diagnostic_signals") or []:
        expr = str((signal.get("condition") or {}).get("expression") or "")
        for token in (
            "alluvium",
            "himalayan_and_sub_himalayan",
            "volcanic",
            "sedimentary_soft_rock",
            "sedimentary_hard_rock",
            "crystalline_basement",
        ):
            if token in expr:
                literals.add(token)
    return literals


def analyze_mws(db, mws_doc: dict, clusters: dict[str, dict]) -> dict[str, Any]:
    uid = str(mws_doc.get("uid") or "")
    acwadam = (mws_doc.get("aquifer") or {}).get("acwadam_class")
    card_tag = _mws_card_aquifer_tag(mws_doc)
    aer = _card_aer_tag(mws_doc)
    retrieval = load_mws_scoped_evidence_cards(db, mws_doc)
    pathway_rows: list[dict[str, Any]] = []
    cluster_mismatch = False
    literal_mismatch = False
    card_tag_mismatch = False
    mws_aquifer_tags = card_aquifer_tags_for_mws(mws_doc)

    for card in retrieval.cards:
        suffix = _card_suffix(card.get("card_id"))
        cluster = clusters.get(suffix or "") if suffix else None
        cluster_tags = _cluster_aquifer_tags(cluster) if cluster else set()
        cluster_ok = not cluster_tags or (card_tag in cluster_tags if card_tag else True)
        literals = _literal_aquifer_classes_in_card(card)
        literal_ok = not literals or (acwadam in literals if acwadam else True)
        retrieved_tag = card_aquifer_tag_from_evidence_card(card)
        tag_similarity = aquifer_tag_similarity(mws_aquifer_tags, retrieved_tag)
        tag_exact = bool(retrieved_tag and retrieved_tag in mws_aquifer_tags)
        if not cluster_ok:
            cluster_mismatch = True
        if not literal_ok:
            literal_mismatch = True
        if retrieved_tag and tag_similarity < 1.0:
            card_tag_mismatch = True
        pathway_rows.append(
            {
                "pathway_id": card.get("causal_pathway"),
                "card_id": card.get("card_id"),
                "cluster_suffix": suffix,
                "cluster_label": (cluster or {}).get("label"),
                "cluster_aquifer_types": sorted(cluster_tags),
                "retrieved_aquifer_tag": retrieved_tag,
                "aquifer_tag_similarity": round(tag_similarity, 2),
                "aquifer_tag_exact_match": tag_exact,
                "card_literal_aquifers": sorted(literals),
                "cluster_match": cluster_ok,
                "literal_match": literal_ok,
            }
        )

    return {
        "uid": uid,
        "aer": aer,
        "acwadam_class": acwadam,
        "card_aquifer_tag": card_tag,
        "aer_neighbors": AER_RETRIEVAL_NEIGHBORS.get(aer or "", [aer] if aer else []),
        "cluster_mismatch": cluster_mismatch,
        "literal_mismatch": literal_mismatch,
        "card_tag_mismatch": card_tag_mismatch,
        "pathways": pathway_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Limit MWS count")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "aquifer_cluster_mismatch_post_retriever_fix.json")
    args = parser.parse_args()

    db = get_db()
    clear_aer_aquifer_inventory_cache()
    clusters = cluster_by_suffix()
    cursor = db.mws_data.find({}, {"uid": 1}).sort("uid", 1)
    if args.limit:
        cursor = cursor.limit(args.limit)

    mismatches: list[dict[str, Any]] = []
    literal_only: list[dict[str, Any]] = []
    cluster_only: list[dict[str, Any]] = []
    card_tag_only: list[dict[str, Any]] = []
    by_aer: Counter[str] = Counter()
    by_suffix: Counter[str] = Counter()
    by_tag_pair: Counter[str] = Counter()
    by_similarity_bucket: Counter[str] = Counter()

    total = 0
    for row in cursor:
        uid = row.get("uid")
        if not uid:
            continue
        raw = db.mws_data.find_one({"uid": uid})
        if not raw:
            continue
        mws_doc = enrich_mws_doc(db, raw)
        total += 1
        report = analyze_mws(db, mws_doc, clusters)
        any_mismatch = (
            report["cluster_mismatch"]
            or report["literal_mismatch"]
            or report["card_tag_mismatch"]
        )
        if any_mismatch:
            mismatches.append(report)
            if report["cluster_mismatch"]:
                cluster_only.append(report)
                by_aer[report.get("aer") or "?"] += 1
                for pw in report["pathways"]:
                    if not pw.get("cluster_match"):
                        by_suffix[pw.get("cluster_suffix") or "?"] += 1
            if report["literal_mismatch"]:
                literal_only.append(report)
            if report["card_tag_mismatch"]:
                card_tag_only.append(report)
                for pw in report["pathways"]:
                    if pw.get("retrieved_aquifer_tag") and not pw.get("aquifer_tag_exact_match"):
                        mws_tag = report.get("card_aquifer_tag") or "?"
                        pair = f"{mws_tag}->{pw['retrieved_aquifer_tag']}@{pw.get('aquifer_tag_similarity')}"
                        by_tag_pair[pair] += 1
                        bucket = "exact" if pw.get("aquifer_tag_exact_match") else (
                            "partial" if (pw.get("aquifer_tag_similarity") or 0) > 0 else "none"
                        )
                        by_similarity_bucket[bucket] += 1

    summary = {
        "mws_total": total,
        "mws_with_any_mismatch": len(mismatches),
        "mws_cluster_aquifer_mismatch": len(cluster_only),
        "mws_literal_aquifer_mismatch": len(literal_only),
        "mws_card_aquifer_tag_mismatch": len(card_tag_only),
        "by_aer_cluster_mismatch": dict(by_aer.most_common()),
        "by_cluster_suffix_mismatch": dict(by_suffix.most_common(20)),
        "by_mws_to_card_aquifer_tag_pair": dict(by_tag_pair.most_common(25)),
        "by_aquifer_tag_similarity_bucket": dict(by_similarity_bucket),
        "prior_run_comparison": {
            "pre_fix_mws_with_any_mismatch": 7683,
            "pre_fix_mws_cluster_mismatch": 4464,
            "pre_fix_mws_literal_mismatch": 5785,
        },
        "mismatches_sample": mismatches[:50],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "mismatches_sample"}, indent=2))
    print(f"\nWrote {args.output} ({len(mismatches)} mismatched MWS of {total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
