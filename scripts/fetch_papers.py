"""
fetch_papers.py
===============
Acquire open-access research papers for each causal pathway using Semantic Scholar,
OpenAlex, and Unpaywall. Writes metadata JSON and PDF files under data/papers/.

Usage:
    # Agriculture / water scarcity pathways only (default prefix), metadata for review
    python scripts/fetch_papers.py --dry-run

    # Single pathway
    python scripts/fetch_papers.py --pathway agriculture__water_scarcity__groundwater_stress --dry-run

    # Download PDFs after reviewing fetch_manifest.json (include_in_corpus: true)
    python scripts/fetch_papers.py --download-selected

Environment (.env):
    UNPAYWALL_EMAIL   Required for PDF download (not needed for --dry-run)
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
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
METADATA_DIR = ROOT / "metadata"
PAPERS_META_DIR = ROOT / "data" / "papers" / "metadata"
PAPERS_PDF_DIR = ROOT / "data" / "papers" / "pdfs"
MANIFEST_PATH = ROOT / "data" / "papers" / "fetch_manifest.json"

DEFAULT_PATHWAY_PREFIX = "agriculture__water_scarcity"
DEFAULT_MAX_PER_PATHWAY = 25

S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_SEARCH = "https://api.openalex.org/works"
UNPAYWALL = "https://api.unpaywall.org/v2"

S2_FIELDS = "title,authors,year,abstract,openAccessPdf,externalIds,citationCount,paperId"
REQUEST_DELAY_S = 1.0

load_dotenv(ROOT / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def slugify_doi(doi: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", doi.strip())


def make_paper_id(doi: str | None, title: str) -> str:
    if doi:
        clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
        return f"doi__{slugify_doi(clean)}"
    digest = hashlib.sha256(normalize_title(title).encode()).hexdigest()[:16]
    return f"title__{digest}"


def openalex_abstract(inverted: dict | None) -> str | None:
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return None
    positions.sort()
    return " ".join(w for _, w in positions)


def load_pathway_queries(path: Path | None = None) -> dict[str, list[str]]:
    path = path or METADATA_DIR / "pathway_queries.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data["pathways"]


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open(encoding="utf-8") as fh:
            manifest = json.load(fh)
    else:
        manifest = {"pathways": {}, "papers": {}, "updated_at": None}
    return ensure_manifest_fields(manifest)


def ensure_manifest_fields(manifest: dict) -> dict:
    """Ensure review fields exist; preserve user-edited include_in_corpus values."""
    manifest.setdefault("pathways", {})
    manifest.setdefault("papers", {})
    for paper_id, entry in manifest["papers"].items():
        entry.setdefault("include_in_corpus", True)
        entry.setdefault("pdf_downloaded", False)
        if "title" not in entry:
            meta = load_paper_metadata(paper_id)
            if meta:
                entry.setdefault("title", meta.get("title"))
                entry.setdefault("year", meta.get("year"))
                entry.setdefault("doi", meta.get("doi"))
                entry.setdefault("abstract", (meta.get("abstract") or "")[:500])
    return manifest


def paper_manifest_entry(
    doc: dict,
    pathway_tags: list[str],
    query: str,
    existing: dict | None,
) -> dict:
    entry = {
        "title": doc.get("title"),
        "year": doc.get("year"),
        "doi": doc.get("doi"),
        "abstract": (doc.get("abstract") or "")[:500],
        "pathway_tags": pathway_tags,
        "discovered_via_query": query,
        "source_api": doc.get("source_api"),
        "pdf_downloaded": doc.get("pdf_downloaded", False),
    }
    # Never overwrite a user-set review flag; only default new papers to true.
    if existing is not None and "include_in_corpus" in existing:
        entry["include_in_corpus"] = existing["include_in_corpus"]
    else:
        entry["include_in_corpus"] = True
    if existing:
        for key in ("pdf_path",):
            if key in existing:
                entry[key] = existing[key]
    return entry


def save_manifest(manifest: dict) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)


def load_paper_metadata(paper_id: str) -> dict | None:
    path = PAPERS_META_DIR / f"{paper_id}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_paper_metadata(doc: dict) -> None:
    PAPERS_META_DIR.mkdir(parents=True, exist_ok=True)
    path = PAPERS_META_DIR / f"{doc['paper_id']}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)


def merge_pathway_tag(existing: dict | None, pathway: str) -> list[str]:
    tags = list((existing or {}).get("pathway_tags") or [])
    if pathway not in tags:
        tags.append(pathway)
    return tags


S2_RETRY_DELAYS = [30, 60, 120]


def s2_search(query: str, limit: int = 10) -> list[dict]:
    params = {"query": query, "limit": limit, "fields": S2_FIELDS}
    for attempt, delay in enumerate([0] + S2_RETRY_DELAYS):
        if delay:
            log.warning(f"Semantic Scholar backoff {delay}s (attempt {attempt})")
            time.sleep(delay)
        r = requests.get(S2_SEARCH, params=params, timeout=30)
        if r.status_code == 429:
            continue
        r.raise_for_status()
        return r.json().get("data") or []
    log.warning("Semantic Scholar unavailable after retries — skipping")
    return []


def openalex_search(query: str, limit: int = 10, email: str = "") -> list[dict]:
    headers = {"User-Agent": f"landscape-problem-diagnosis/1.0 (mailto:{email})"} if email else {}
    params = {
        "search": query,
        "filter": "open_access.is_oa:true",
        "per_page": min(limit, 25),
    }
    r = requests.get(OPENALEX_SEARCH, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("results") or []


def unpaywall_pdf_url(doi: str, email: str) -> str | None:
    if not doi or not email:
        return None
    clean = doi.replace("https://doi.org/", "")
    url = f"{UNPAYWALL}/{quote(clean, safe='')}"
    r = requests.get(url, params={"email": email}, timeout=30)
    if r.status_code != 200:
        return None
    data = r.json()
    best = data.get("best_oa_location") or {}
    return best.get("url_for_pdf") or best.get("url")


def normalize_s2_paper(raw: dict) -> dict:
    ext = raw.get("externalIds") or {}
    doi = ext.get("DOI")
    authors = [a.get("name", "") for a in (raw.get("authors") or []) if a.get("name")]
    pdf_url = (raw.get("openAccessPdf") or {}).get("url")
    title = raw.get("title") or ""
    return {
        "paper_id": make_paper_id(doi, title),
        "title": title,
        "authors": authors,
        "year": raw.get("year"),
        "abstract": raw.get("abstract"),
        "doi": doi,
        "pdf_url": pdf_url,
        "source_api": "semantic_scholar",
        "external_ids": {"semantic_scholar": raw.get("paperId"), "doi": doi},
    }


def normalize_openalex_paper(raw: dict) -> dict:
    doi = raw.get("doi", "").replace("https://doi.org/", "") if raw.get("doi") else None
    authors = [
        (a.get("author") or {}).get("display_name", "")
        for a in (raw.get("authorships") or [])
    ]
    authors = [a for a in authors if a]
    oa = raw.get("open_access") or {}
    best = raw.get("best_oa_location") or {}
    pdf_url = best.get("pdf_url") or (best.get("url") if oa.get("is_oa") else None)
    title = raw.get("title") or raw.get("display_name") or ""
    return {
        "paper_id": make_paper_id(doi, title),
        "title": title,
        "authors": authors,
        "year": raw.get("publication_year"),
        "abstract": openalex_abstract(raw.get("abstract_inverted_index")),
        "doi": doi,
        "pdf_url": pdf_url,
        "source_api": "openalex",
        "external_ids": {"openalex": raw.get("id"), "doi": doi},
    }


def download_pdf(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, timeout=120, stream=True, headers={"User-Agent": "landscape-problem-diagnosis/1.0"})
        if r.status_code != 200:
            log.warning(f"  PDF download HTTP {r.status_code}: {url[:80]}")
            return False
        content_type = (r.headers.get("content-type") or "").lower()
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            log.warning(f"  Skipping non-PDF content-type={content_type!r}: {url[:80]}")
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=65536):
                fh.write(chunk)
        if dest.stat().st_size < 1024:
            dest.unlink(missing_ok=True)
            log.warning(f"  PDF too small, discarded: {dest.name}")
            return False
        return True
    except Exception as exc:
        log.warning(f"  PDF download failed: {exc}")
        return False


def resolve_and_download(paper: dict, email: str, dry_run: bool) -> dict:
    """Ensure pdf_url is set; download if missing on disk."""
    pdf_path = PAPERS_PDF_DIR / f"{paper['paper_id']}.pdf"
    rel_pdf = f"data/papers/pdfs/{paper['paper_id']}.pdf"
    paper["pdf_path"] = rel_pdf if pdf_path.exists() else None

    if pdf_path.exists():
        paper["pdf_downloaded"] = True
        paper["pdf_path"] = rel_pdf
        return paper

    if dry_run:
        paper["pdf_downloaded"] = False
        return paper

    url = paper.get("pdf_url")
    if not url and paper.get("doi"):
        url = unpaywall_pdf_url(paper["doi"], email)
        if url:
            paper["pdf_url"] = url
            paper["pdf_source"] = "unpaywall"
        time.sleep(REQUEST_DELAY_S)

    if url and download_pdf(url, pdf_path):
        paper["pdf_downloaded"] = True
        paper["pdf_path"] = rel_pdf
        log.info(f"  Downloaded PDF: {paper['paper_id']}")
    else:
        paper["pdf_downloaded"] = False
        log.warning(f"  No PDF for: {paper['paper_id']} — {paper.get('title', '')[:60]}")

    return paper


def collect_candidates(
    query: str,
    email: str,
    seen_dois: set[str],
    seen_titles: set[str],
    *,
    use_openalex: bool = True,
    use_semantic_scholar: bool = False,
) -> list[dict]:
    candidates: list[dict] = []
    sources: list[tuple[str, Any, Any]] = []
    if use_openalex:
        sources.append(("openalex", lambda q, lim: openalex_search(q, lim, email), normalize_openalex_paper))
    if use_semantic_scholar:
        sources.append(("semantic_scholar", s2_search, normalize_s2_paper))

    for source, search_fn, normalizer in sources:
        try:
            raw_list = search_fn(query, 10)
            time.sleep(REQUEST_DELAY_S)
        except Exception as exc:
            log.warning(f"  {source} search failed for {query!r}: {exc}")
            continue

        for raw in raw_list:
            paper = normalizer(raw)
            title_key = normalize_title(paper.get("title") or "")
            doi = (paper.get("doi") or "").lower()

            if not title_key:
                continue
            if doi and doi in seen_dois:
                continue
            if title_key in seen_titles:
                continue

            if doi:
                seen_dois.add(doi)
            seen_titles.add(title_key)
            candidates.append(paper)

    return candidates


def fetch_pathway(
    pathway: str,
    queries: list[str],
    *,
    max_per_pathway: int,
    email: str,
    dry_run: bool,
    manifest: dict,
    use_openalex: bool = True,
    use_semantic_scholar: bool = False,
) -> dict[str, Any]:
    log.info(f"Pathway: {pathway} ({len(queries)} queries, target {max_per_pathway} papers)")

    pathway_state = manifest["pathways"].get(pathway, {})
    collected_ids: list[str] = list(pathway_state.get("paper_ids") or [])
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()

    for pid in manifest.get("papers", {}):
        existing = load_paper_metadata(pid)
        if existing:
            if existing.get("doi"):
                seen_dois.add(existing["doi"].lower())
            seen_titles.add(normalize_title(existing.get("title") or ""))

    added = 0
    queries_run = 0

    for query in queries:
        if len(collected_ids) >= max_per_pathway:
            break
        queries_run += 1
        log.info(f"  Query [{queries_run}/{len(queries)}]: {query!r}")

        candidates = collect_candidates(
            query, email, seen_dois, seen_titles,
            use_openalex=use_openalex,
            use_semantic_scholar=use_semantic_scholar,
        )
        log.info(f"    → {len(candidates)} new candidate(s)")

        for paper in candidates:
            if len(collected_ids) >= max_per_pathway:
                break

            paper_id = paper["paper_id"]
            existing = load_paper_metadata(paper_id)
            pathway_tags = merge_pathway_tag(existing, pathway)

            doc = {
                **(existing or {}),
                **{k: v for k, v in paper.items() if v is not None},
                "paper_id": paper_id,
                "pathway_tags": pathway_tags,
                "discovered_via_query": query,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            doc = resolve_and_download(doc, email, dry_run)
            save_paper_metadata(doc)

            if paper_id not in collected_ids:
                collected_ids.append(paper_id)
                added += 1

            existing_manifest = manifest["papers"].get(paper_id)
            manifest["papers"][paper_id] = paper_manifest_entry(
                doc, pathway_tags, query, existing_manifest
            )
            log.info(
                f"    + {paper_id} | pdf={'yes' if doc.get('pdf_downloaded') else 'no'} "
                f"| include={manifest['papers'][paper_id]['include_in_corpus']} "
                f"| {doc.get('title', '')[:70]}"
            )

    pathway_result = {
        "paper_ids": collected_ids,
        "count": len(collected_ids),
        "target": max_per_pathway,
        "queries_run": queries_run,
        "added_this_run": added,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest["pathways"][pathway] = pathway_result
    save_manifest(manifest)

    log.info(
        f"  Pathway done: {len(collected_ids)}/{max_per_pathway} papers "
        f"({added} new this run)"
    )
    return pathway_result


def filter_pathways(
    all_queries: dict[str, list[str]],
    *,
    pathway: str | None,
    pathway_prefix: str | None,
) -> dict[str, list[str]]:
    if pathway:
        if pathway not in all_queries:
            raise KeyError(pathway)
        return {pathway: all_queries[pathway]}
    if pathway_prefix:
        filtered = {
            k: v for k, v in all_queries.items()
            if k.startswith(pathway_prefix)
        }
        if not filtered:
            raise ValueError(f"No pathways match prefix {pathway_prefix!r}")
        return filtered
    return all_queries


def download_selected_papers(manifest: dict, email: str) -> None:
    """Download PDFs only for papers marked include_in_corpus: true."""
    selected = [
        pid for pid, entry in manifest.get("papers", {}).items()
        if entry.get("include_in_corpus", True)
    ]
    log.info(f"Downloading PDFs for {len(selected)} selected paper(s)...")
    for paper_id in selected:
        meta = load_paper_metadata(paper_id)
        if not meta:
            log.warning(f"  Missing metadata for {paper_id} — skip")
            continue
        doc = resolve_and_download(meta, email, dry_run=False)
        save_paper_metadata(doc)
        existing_manifest = manifest["papers"].get(paper_id, {})
        # Preserve all review fields; only update download status.
        existing_manifest["pdf_downloaded"] = doc.get("pdf_downloaded", False)
        if doc.get("pdf_path"):
            existing_manifest["pdf_path"] = doc["pdf_path"]
        manifest["papers"][paper_id] = existing_manifest
    save_manifest(manifest)


def print_summary(manifest: dict) -> None:
    pathways = manifest.get("pathways", {})
    papers = manifest.get("papers", {})
    with_pdf = sum(1 for p in papers.values() if p.get("pdf_downloaded"))
    selected = sum(1 for p in papers.values() if p.get("include_in_corpus", True))
    log.info("=== Fetch summary ===")
    log.info(f"  Pathways processed: {len(pathways)}")
    log.info(f"  Unique papers:      {len(papers)}")
    log.info(f"  Marked for corpus:  {selected}")
    log.info(f"  With PDF:           {with_pdf}")
    for pathway, state in sorted(pathways.items()):
        log.info(f"  {pathway}: {state.get('count', 0)}/{state.get('target', '?')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch open-access papers per causal pathway")
    parser.add_argument("--pathway", help="Process only this pathway key")
    parser.add_argument(
        "--pathway-prefix",
        default=DEFAULT_PATHWAY_PREFIX,
        help=f"Process pathways with this prefix (default: {DEFAULT_PATHWAY_PREFIX}). "
             "Use --pathway-prefix '' to process all pathways.",
    )
    parser.add_argument(
        "--max-per-pathway",
        type=int,
        default=DEFAULT_MAX_PER_PATHWAY,
        help=f"Target papers per pathway (default {DEFAULT_MAX_PER_PATHWAY})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and save metadata only, no PDF download",
    )
    parser.add_argument(
        "--download-selected",
        action="store_true",
        help="Download PDFs for papers with include_in_corpus: true in fetch_manifest.json",
    )
    parser.add_argument(
        "--semantic-scholar",
        action="store_true",
        help="Also search Semantic Scholar (often rate-limited without an API key)",
    )
    parser.add_argument(
        "--all-pathways",
        action="store_true",
        help="Ignore --pathway-prefix and process every pathway in pathway_queries.json",
    )
    args = parser.parse_args()

    email = os.getenv("UNPAYWALL_EMAIL", "")
    if not email and not args.dry_run and not args.download_selected:
        log.error("Set UNPAYWALL_EMAIL in .env (required for PDF download)")
        return 1

    PAPERS_META_DIR.mkdir(parents=True, exist_ok=True)
    PAPERS_PDF_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()

    if args.download_selected:
        download_selected_papers(manifest, email)
        print_summary(load_manifest())
        return 0

    all_queries = load_pathway_queries()
    prefix = None if args.all_pathways else (args.pathway_prefix or None)
    try:
        pathways = filter_pathways(all_queries, pathway=args.pathway, pathway_prefix=prefix)
    except KeyError:
        log.error(f"Unknown pathway: {args.pathway}")
        return 1
    except ValueError as exc:
        log.error(str(exc))
        return 1

    log.info(f"Processing {len(pathways)} pathway(s), max {args.max_per_pathway} papers each")
    if prefix:
        log.info(f"  Pathway prefix filter: {prefix!r}")
    if args.dry_run:
        log.info("DRY RUN — metadata only, no PDF downloads")
    if args.semantic_scholar:
        log.info("Semantic Scholar enabled (OpenAlex always used)")
    else:
        log.info("Using OpenAlex only (pass --semantic-scholar to include Semantic Scholar)")

    for pathway, queries in pathways.items():
        existing_count = manifest["pathways"].get(pathway, {}).get("count", 0)
        if existing_count >= args.max_per_pathway:
            log.info(f"Pathway {pathway} already has {existing_count} papers — skipping")
            continue
        fetch_pathway(
            pathway,
            queries,
            max_per_pathway=args.max_per_pathway,
            email=email,
            dry_run=args.dry_run,
            manifest=manifest,
            use_openalex=True,
            use_semantic_scholar=args.semantic_scholar,
        )

    print_summary(load_manifest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
