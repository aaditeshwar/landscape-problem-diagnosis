#!/usr/bin/env python3
"""Audit evidence-card AER coverage vs all NBSS-LUP regions and ingested MWS distribution."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from dotenv import load_dotenv
from pymongo import MongoClient

from services.retriever import AER_RETRIEVAL_NEIGHBORS, _fetch_candidates  # noqa: E402

# Eastern plateau AERs where alluvium-tagged MWS often hit aquifer fallback (no alluvium cards).
ALLUVIUM_GAP_AERS = ("AER-11", "AER-12")


def neighbor_set(aer: str) -> list[str]:
    neighbors = AER_RETRIEVAL_NEIGHBORS.get(aer, [aer])
    ordered: list[str] = []
    for tag in [aer, *neighbors]:
        if tag not in ordered:
            ordered.append(tag)
    return ordered


def count_pool(db, aer_tags: list[str], aquifer: str | None = None) -> int:
    filt: dict = {"aer_tags": {"$in": aer_tags}}
    if aquifer:
        filt["aquifer_tags"] = aquifer
    return db.evidence_cards.count_documents(filt)


def main() -> int:
    load_dotenv(ROOT / ".env")
    db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[
        os.getenv("MONGO_DB", "diagnosis_db")
    ]
    ref = json.loads((ROOT / "metadata" / "reference_standards.json").read_text(encoding="utf-8"))
    all_aers = sorted(
        ref["nbss_lup_agro_ecological_regions"]["regions"].keys(),
        key=lambda x: int(x.split("-")[1]),
    )

    aer_card_count: Counter[str] = Counter()
    aer_pathways: dict[str, set[str]] = defaultdict(set)
    for doc in db.evidence_cards.find({}, {"aer_tags": 1, "causal_pathway": 1}):
        for aer in doc.get("aer_tags") or []:
            aer_card_count[aer] += 1
            aer_pathways[aer].add(doc.get("causal_pathway") or "?")

    print("=== Direct card coverage (card lists this AER in aer_tags) ===")
    no_direct: list[str] = []
    for aer in all_aers:
        n = aer_card_count.get(aer, 0)
        if n == 0:
            no_direct.append(aer)
        print(f"  {aer}: {n:3d} cards | {len(aer_pathways.get(aer, set()))} pathways")

    print(f"\nAERs with NO direct cards ({len(no_direct)}): {', '.join(no_direct)}")

    print("\n=== Neighbor retrieval pool (any aquifer) ===")
    zero_neighbor: list[str] = []
    weak_neighbor: list[str] = []
    for aer in all_aers:
        tags = neighbor_set(aer)
        total = count_pool(db, tags)
        if total == 0:
            zero_neighbor.append(aer)
        elif total < 8:
            weak_neighbor.append(aer)
        print(f"  {aer}: pool={total:3d} | neighbors={tags}")

    print(f"\nAERs with ZERO cards after neighbor expansion: {', '.join(zero_neighbor) or 'none'}")
    print(f"AERs with weak pool (<8 cards): {', '.join(weak_neighbor) or 'none'}")

    mws_aers: Counter[str] = Counter()
    for doc in db.mws_data.find({"nbss_lup_aer_code": {"$exists": True, "$ne": None}}, {"nbss_lup_aer_code": 1}):
        code = doc.get("nbss_lup_aer_code")
        if code:
            mws_aers[code] += 1

    print("\n=== Alluvium aquifer gaps (high-volume eastern-plateau AERs) ===")
    alluvium_fallback_aers: list[str] = []
    for aer in ALLUVIUM_GAP_AERS:
        tags = neighbor_set(aer)
        alluvium_pool = count_pool(db, tags, "alluvium")
        mws_total = mws_aers.get(aer, 0)
        mws_alluvium = db.mws_data.count_documents(
            {"nbss_lup_aer_code": aer, "aquifer.acwadam_class": "alluvium"},
        )
        if alluvium_pool == 0 and mws_alluvium > 0:
            alluvium_fallback_aers.append(aer)
            risk = "AQUIFER FALLBACK (no alluvium cards in neighbor pool)"
        elif alluvium_pool == 0:
            risk = "no alluvium cards (low alluvium MWS count)"
        else:
            risk = "ok"
        print(
            f"  {aer}: {mws_total} MWS total, {mws_alluvium} alluvium-classified, "
            f"alluvium pool={alluvium_pool} -> {risk}"
        )
    if alluvium_fallback_aers:
        print(
            f"\n  WARNING: {', '.join(alluvium_fallback_aers)} alluvium MWS always drop aquifer filter "
            "and may retrieve hard_rock neighbor-proxy cards."
        )

    print("\n=== Sample retrieval (alluvium MWS, generic stress query) ===")
    try:
        from services.retriever import retrieve_evidence_cards  # noqa: E402

        for aer in ALLUVIUM_GAP_AERS:
            sample = db.mws_data.find_one(
                {"nbss_lup_aer_code": aer, "aquifer.acwadam_class": "alluvium"},
            )
            if not sample:
                sample = db.mws_data.find_one({"nbss_lup_aer_code": aer})
            if not sample:
                print(f"  {aer}: no sample MWS")
                continue
            uid = sample.get("uid")
            result = retrieve_evidence_cards(
                db,
                "what stresses exist in this landscape?",
                sample,
                limit=5,
            )
            cards = result.cards
            direct = sum(1 for c in cards if aer in (c.get("aer_tags") or []))
            print(f"  {aer} MWS {uid}: {direct}/{len(cards)} cards list {aer} directly")
            for card in cards:
                tags = card.get("aer_tags") or []
                marker = "direct" if aer in tags else "proxy"
                print(f"    [{marker}] {card.get('card_id')} aer={tags}")
    except Exception as exc:
        print(f"  (retrieval simulation skipped: {exc})")

    print("\n=== By aquifer type (neighbor pool) ===")
    aquifers = ["hard_rock", "alluvium", "semi-consolidated", "coastal"]
    gaps_by_aquifer: list[tuple[str, str, int]] = []
    for aer in all_aers:
        tags = neighbor_set(aer)
        for aq in aquifers:
            n = count_pool(db, tags, aq)
            if n == 0:
                gaps_by_aquifer.append((aer, aq, count_pool(db, tags)))
            print(f"  {aer} + {aq:18s}: {n:3d}", end="")
            if n == 0:
                print(f"  (AER-only fallback pool: {count_pool(db, tags)} total)")
            else:
                print()

    print("\n=== Ingested MWS by AER (top gaps for deployed tehsils) ===")
    print(f"  Total tagged MWS: {sum(mws_aers.values())}")
    print(f"  {'AER':<8} {'MWS':>7} {'direct':>7} {'neighbor':>9} {'risk'}")
    for aer, n in mws_aers.most_common():
        direct = aer_card_count.get(aer, 0)
        neighbor = count_pool(db, neighbor_set(aer))
        if neighbor == 0:
            risk = "NO POOL"
        elif direct == 0:
            risk = "neighbor-only"
        else:
            risk = "ok"
        print(f"  {aer:<8} {n:7d} {direct:7d} {neighbor:9d} {risk}")

    # Pathway gaps for high-volume AERs with no direct cards
    print("\n=== Pathway coverage within neighbor pool (AERs with MWS but no direct cards) ===")
    all_pathways = sorted(
        {
            doc.get("causal_pathway")
            for doc in db.evidence_cards.find({}, {"causal_pathway": 1})
            if doc.get("causal_pathway")
        }
    )
    for aer, n in mws_aers.most_common():
        if aer_card_count.get(aer, 0) > 0:
            continue
        tags = neighbor_set(aer)
        covered = set()
        for doc in db.evidence_cards.find({"aer_tags": {"$in": tags}}, {"causal_pathway": 1}):
            covered.add(doc.get("causal_pathway"))
        missing = [p for p in all_pathways if p not in covered]
        print(f"  {aer} ({n} MWS): neighbor covers {len(covered)}/{len(all_pathways)} pathways")
        if missing:
            print(f"    missing pathways: {', '.join(missing)}")

    return 1 if zero_neighbor else 0


if __name__ == "__main__":
    raise SystemExit(main())
