#!/usr/bin/env python3
"""Export lithology x AER cluster-mapping matrix with MWS counts and gap analysis."""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from dotenv import load_dotenv  # noqa: E402
from generate_evidence_cards import CONTEXT_CLUSTERS  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from services.aquifer_classification import (  # noqa: E402
    LITHOLOGY_COLUMNS,
    card_aquifer_tags,
    infer_acwadam_class,
)
from services.retriever import (  # noqa: E402
    AER_RETRIEVAL_NEIGHBORS,
    _aer_tags_for_retrieval,
    _card_aquifer_tags,
    _card_query,
    load_mws_scoped_evidence_cards,
)

REPORT_DIR = ROOT / "data" / "reports"
CSV_PATH = REPORT_DIR / "aquifer_aer_cluster_matrix.csv"
GAPS_PATH = REPORT_DIR / "aquifer_aer_cluster_gaps.json"
LITHOLOGIES = list(LITHOLOGY_COLUMNS)
AERS = [f"AER-{i}" for i in range(1, 21)]
CARD_SUFFIX_RE = re.compile(r"__(\d{3})$")


def retrieval_set(aer: str) -> list[str]:
    neighbors = AER_RETRIEVAL_NEIGHBORS.get(aer, [aer])
    ordered: list[str] = []
    for tag in [aer, *neighbors]:
        if tag not in ordered:
            ordered.append(tag)
    return ordered


def cluster_by_suffix() -> dict[str, dict]:
    return {c["suffix"]: c for c in CONTEXT_CLUSTERS}


def eligible_clusters(card_tags: list[str], aer: str) -> list[dict]:
    rs = set(retrieval_set(aer))
    out: list[dict] = []
    for cluster in CONTEXT_CLUSTERS:
        if not any(tag in cluster["aquifer_types"] for tag in card_tags):
            continue
        if not any(tag in rs for tag in cluster["aer_tags"]):
            continue
        out.append(cluster)
    return out


def preferred_cluster(aer: str, clusters: list[dict]) -> str | None:
    if not clusters:
        return None
    direct = [c for c in clusters if aer in c["aer_tags"]]
    pool = direct or clusters
    pool = sorted(pool, key=lambda c: (len(c["aer_tags"]), c["suffix"]))
    return pool[0]["suffix"]


def build_pathways_by_cluster(db) -> dict[str, list[str]]:
    by_suffix: dict[str, set[str]] = defaultdict(set)
    for doc in db.evidence_cards.find({}, {"card_id": 1, "causal_pathway": 1}):
        card_id = str(doc.get("card_id") or "")
        match = CARD_SUFFIX_RE.search(card_id)
        if not match:
            continue
        suffix = match.group(1)
        pathway = str(doc.get("causal_pathway") or "")
        if not pathway and "__" in card_id:
            parts = card_id.rsplit("__", 1)
            pathway = parts[0].split("__")[-1] if parts else card_id
        if pathway:
            by_suffix[suffix].add(pathway)
    return {suffix: sorted(paths) for suffix, paths in sorted(by_suffix.items())}


def format_pathways_by_cluster(
    clusters: list[dict],
    pathways_by_cluster: dict[str, list[str]],
) -> str:
    parts: list[str] = []
    for cluster in sorted(clusters, key=lambda c: c["suffix"]):
        suffix = cluster["suffix"]
        pathways = pathways_by_cluster.get(suffix, [])
        label = cluster["label"]
        if pathways:
            parts.append(f"{suffix} ({label}): {', '.join(pathways)}")
        else:
            parts.append(f"{suffix} ({label}): [no cards in Mongo]")
    return " | ".join(parts)


def cluster_match_description(
    lithology: str,
    aer: str,
    acwadam: str,
    card_tags: list[str],
    retrieval: list[str],
    clusters: list[dict],
) -> str:
    cluster_labels = ", ".join(f"{c['suffix']}={c['label']}" for c in clusters) or "none"
    return (
        f"Dominant lithology {lithology} -> ACWADAM {acwadam}. "
        f"Retrieval filters evidence cards where aquifer_tags matches {card_tags} "
        f"AND aer_tags intersects MWS neighbour set {retrieval}. "
        f"Eligible CONTEXT_CLUSTERS (suffix=label): {cluster_labels}. "
        f"Non-LLM diagnosis then picks one card per causal_pathway from that pool, "
        f"preferring a card whose aer_tags includes exact MWS AER {aer}."
    )


def non_llm_selection_note(aer: str, clusters: list[dict], preferred: str | None) -> str:
    n = len(clusters)
    if n == 0:
        return (
            f"No cluster-matched cards; retriever falls back to AER-only pool for {aer} "
            f"(aquifer filter dropped)."
        )
    if n == 1:
        only = clusters[0]
        return (
            f"Single cluster {only['suffix']} ({only['label']}); each pathway uses its "
            f"__{only['suffix']} card if present in Mongo."
        )
    suffixes = ", ".join(c["suffix"] for c in clusters)
    pref = preferred or "?"
    return (
        f"Multiple clusters ({suffixes}); non-LLM picks one card per pathway from the "
        f"union of eligible cards, preferring exact AER {aer} on the card (else highest "
        f"card_id). Typical direct-AER cluster for this row: {pref}."
    )


def card_cluster_suffix(card_id: str | None) -> str | None:
    match = CARD_SUFFIX_RE.search(str(card_id or ""))
    return match.group(1) if match else None


def build_mws_doc(
    aer: str,
    acwadam: str,
    lith_key: str | None,
) -> dict:
    return {
        "nbss_lup_aer_code": aer,
        "aquifer": {
            "acwadam_class": acwadam,
            "dominant_lithology": lith_key,
        },
    }


def simulate_non_llm_clusters(
    db,
    aer: str,
    acwadam: str,
    lith_key: str | None,
    clusters_map: dict[str, dict],
) -> dict[str, str | int]:
    """Run the same card selection as load_mws_scoped_evidence_cards and map to clusters."""
    mws_doc = build_mws_doc(aer, acwadam, lith_key)
    aquifer_tags = _card_aquifer_tags(mws_doc)
    aer_tags = _aer_tags_for_retrieval(mws_doc)

    aquifer_aer_pool = list(db.evidence_cards.find(_card_query(aquifer_tags, aer_tags)))
    retrieval_pool = "aquifer+aer" if aquifer_aer_pool else "aer_only_fallback"

    result = load_mws_scoped_evidence_cards(db, mws_doc)
    cards = result.cards

    pathway_cluster: dict[str, str] = {}
    for card in cards:
        pathway = str(card.get("causal_pathway") or "").strip()
        suffix = card_cluster_suffix(card.get("card_id"))
        if pathway and suffix:
            pathway_cluster[pathway] = suffix

    suffixes = sorted(set(pathway_cluster.values()))
    suffix_counts = Counter(pathway_cluster.values())
    if len(suffixes) == 1:
        resolved = suffixes[0]
        resolved_label = clusters_map.get(resolved, {}).get("label", "")
    elif suffixes:
        resolved = "mixed"
        resolved_label = ""
    else:
        resolved = ""
        resolved_label = ""

    pathway_map = "; ".join(
        f"{pathway}={suffix}" for pathway, suffix in sorted(pathway_cluster.items())
    )
    suffix_labels = "; ".join(
        f"{suffix}={clusters_map.get(suffix, {}).get('label', '?')}" for suffix in suffixes
    )

    if not suffixes:
        simulation_note = (
            f"Non-LLM pool={retrieval_pool} returned no pathway cards for "
            f"aquifer_tags={aquifer_tags} and AER set {aer_tags}."
        )
    elif retrieval_pool == "aer_only_fallback":
        dominant = suffix_counts.most_common(1)[0][0]
        dom_label = clusters_map.get(dominant, {}).get("label", "?")
        if resolved == "mixed":
            simulation_note = (
                f"No aquifer+cluster match; retriever used AER-only fallback and loaded "
                f"{len(pathway_cluster)} pathways across clusters [{', '.join(suffixes)}] "
                f"({suffix_labels}). Pathways disagree; mode cluster is {dominant} ({dom_label})."
            )
        else:
            simulation_note = (
                f"No aquifer+cluster match; retriever used AER-only fallback and resolved "
                f"all {len(pathway_cluster)} pathways to cluster {resolved} ({resolved_label})."
            )
    elif resolved == "mixed":
        dominant = suffix_counts.most_common(1)[0][0]
        dom_label = clusters_map.get(dominant, {}).get("label", "?")
        simulation_note = (
            f"Aquifer+AER pool matched multiple clusters; non-LLM loaded {len(pathway_cluster)} "
            f"pathways across [{', '.join(suffixes)}] ({suffix_labels}). "
            f"Mode cluster {dominant} ({dom_label}); exact picks per pathway in "
            f"non_llm_pathway_cluster_map."
        )
    else:
        simulation_note = (
            f"Aquifer+AER pool resolved all {len(pathway_cluster)} pathways to cluster "
            f"{resolved} ({resolved_label})."
        )

    return {
        "non_llm_retrieval_pool": retrieval_pool,
        "non_llm_pathways_loaded": len(pathway_cluster),
        "non_llm_selected_cluster_suffixes": ",".join(suffixes),
        "non_llm_resolved_cluster_suffix": resolved,
        "non_llm_resolved_cluster_label": resolved_label,
        "non_llm_pathway_cluster_map": pathway_map,
        "non_llm_simulation_note": simulation_note,
    }


def load_mws_counts(db) -> Counter[tuple[str | None, str | None]]:
    counts: Counter[tuple[str | None, str | None]] = Counter()
    cursor = db.mws_data.find(
        {},
        {"aquifer.dominant_lithology": 1, "nbss_lup_aer_code": 1},
    )
    for doc in cursor:
        aer = doc.get("nbss_lup_aer_code")
        lith = (doc.get("aquifer") or {}).get("dominant_lithology")
        counts[(lith, aer)] += 1
    return counts


def main() -> int:
    load_dotenv(ROOT / ".env")
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB", "diagnosis_db")
    db = MongoClient(mongo_uri, serverSelectionTimeoutMS=15000)[db_name]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    mws_counts = load_mws_counts(db)
    pathways_by_cluster = build_pathways_by_cluster(db)
    clusters_map = cluster_by_suffix()

    rows: list[dict[str, str | int]] = []
    by_aer_aquifer: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for lithology in LITHOLOGIES:
        if lithology == "None":
            lithology_pct = {"None": 100.0}
        else:
            lithology_pct = {lithology: 80.0, "None": 20.0}
        for aer in AERS:
            inferred = infer_acwadam_class(lithology_pct, aer)
            acwadam = inferred["acwadam_class"]
            card_tags = card_aquifer_tags(acwadam, aer)
            retrieval = retrieval_set(aer)
            clusters = eligible_clusters(card_tags, aer)
            suffixes = [c["suffix"] for c in clusters]
            pref = preferred_cluster(aer, clusters)
            card_filter = ";".join(card_tags)
            lith_key = None if lithology == "None" else lithology
            mws_count = mws_counts.get((lith_key, aer), 0)

            sim = simulate_non_llm_clusters(db, aer, acwadam, lith_key, clusters_map)

            row = {
                "dominant_lithology": lithology,
                "mws_aer": aer,
                "acwadam_class": acwadam,
                "acwadam_source": inferred["acwadam_source"],
                "card_aquifer_filter": card_filter,
                "aer_retrieval_neighbors": ";".join(retrieval),
                "eligible_cluster_suffixes": ",".join(suffixes) if suffixes else "",
                "eligible_cluster_count": len(suffixes),
                "unique_cluster_available": "yes" if len(suffixes) == 1 else "no",
                "preferred_cluster_suffix": pref or "",
                "eligible_cluster_labels": "; ".join(
                    f"{c['suffix']}={c['label']}" for c in clusters
                ),
                "pathways_by_cluster": format_pathways_by_cluster(clusters, pathways_by_cluster),
                "cluster_match_description": cluster_match_description(
                    lithology, aer, acwadam, card_tags, retrieval, clusters
                ),
                "non_llm_selection_note": non_llm_selection_note(aer, clusters, pref),
                "non_llm_retrieval_pool": sim["non_llm_retrieval_pool"],
                "non_llm_pathways_loaded": sim["non_llm_pathways_loaded"],
                "non_llm_selected_cluster_suffixes": sim["non_llm_selected_cluster_suffixes"],
                "non_llm_resolved_cluster_suffix": sim["non_llm_resolved_cluster_suffix"],
                "non_llm_resolved_cluster_label": sim["non_llm_resolved_cluster_label"],
                "non_llm_pathway_cluster_map": sim["non_llm_pathway_cluster_map"],
                "non_llm_simulation_note": sim["non_llm_simulation_note"],
                "mws_count": mws_count,
            }
            rows.append(row)
            by_aer_aquifer[(aer, card_filter)].append(row)

    fieldnames = list(rows[0].keys()) if rows else []
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    no_cluster_pairs: list[dict] = []
    multi_cluster_pairs: list[dict] = []
    seen_aer_aquifer: set[tuple[str, str]] = set()

    for (aer, card_filter), group in sorted(by_aer_aquifer.items()):
        sample = group[0]
        suffixes = sample["eligible_cluster_suffixes"]
        count = int(sample["eligible_cluster_count"])
        total_mws = sum(int(r["mws_count"]) for r in group)
        key = (aer, card_filter)
        if key in seen_aer_aquifer:
            continue
        seen_aer_aquifer.add(key)

        entry = {
            "mws_aer": aer,
            "card_aquifer_filter": card_filter,
            "eligible_cluster_suffixes": suffixes,
            "eligible_cluster_count": count,
            "preferred_cluster_suffix": sample["preferred_cluster_suffix"],
            "pathways_by_cluster": sample["pathways_by_cluster"],
            "non_llm_selection_note": sample["non_llm_selection_note"],
            "non_llm_retrieval_pool": sample["non_llm_retrieval_pool"],
            "non_llm_resolved_cluster_suffix": sample["non_llm_resolved_cluster_suffix"],
            "non_llm_resolved_cluster_label": sample["non_llm_resolved_cluster_label"],
            "non_llm_selected_cluster_suffixes": sample["non_llm_selected_cluster_suffixes"],
            "non_llm_pathway_cluster_map": sample["non_llm_pathway_cluster_map"],
            "non_llm_simulation_note": sample["non_llm_simulation_note"],
            "lithologies_in_group": sorted({r["dominant_lithology"] for r in group}),
            "mws_count_total": total_mws,
        }
        if count == 0:
            no_cluster_pairs.append(entry)
        elif count > 1:
            multi_cluster_pairs.append(entry)

    gaps_report = {
        "csv_path": str(CSV_PATH.relative_to(ROOT)).replace("\\", "/"),
        "row_count": len(rows),
        "total_mws_in_db": sum(mws_counts.values()),
        "pairs_with_no_eligible_cluster": no_cluster_pairs,
        "pairs_with_multiple_eligible_clusters": multi_cluster_pairs,
        "cluster_catalog": {
            c["suffix"]: {
                "label": c["label"],
                "aquifer_types": c["aquifer_types"],
                "aer_tags": c["aer_tags"],
                "pathways_in_mongo": pathways_by_cluster.get(c["suffix"], []),
            }
            for c in CONTEXT_CLUSTERS
        },
    }
    GAPS_PATH.write_text(json.dumps(gaps_report, indent=2), encoding="utf-8")

    print(f"Wrote {len(rows)} rows -> {CSV_PATH}")
    print(f"Gap analysis -> {GAPS_PATH}")
    print(f"Total MWS in DB: {gaps_report['total_mws_in_db']}")
    print(f"(AER, aquifer) pairs with NO eligible cluster: {len(no_cluster_pairs)}")
    for item in no_cluster_pairs:
        print(
            f"  {item['mws_aer']} + {item['card_aquifer_filter']} "
            f"(mws={item['mws_count_total']}, lithologies={len(item['lithologies_in_group'])}) "
            f"-> non-LLM cluster {item['non_llm_resolved_cluster_suffix']} "
            f"({item['non_llm_resolved_cluster_label'] or 'mixed/none'}) "
            f"via {item['non_llm_retrieval_pool']}"
        )
    print(f"(AER, aquifer) pairs with MULTIPLE eligible clusters: {len(multi_cluster_pairs)}")
    for item in multi_cluster_pairs:
        print(
            f"  {item['mws_aer']} + {item['card_aquifer_filter']} -> "
            f"clusters [{item['eligible_cluster_suffixes']}] preferred={item['preferred_cluster_suffix']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
