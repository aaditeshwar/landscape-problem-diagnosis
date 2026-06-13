"""Summarize paper fetch results for manual review in fetch_manifest.json."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap()
META_DIR = ROOT / "data" / "papers" / "metadata"
PDF_DIR = ROOT / "data" / "papers" / "pdfs"
MANIFEST = ROOT / "data" / "papers" / "fetch_manifest.json"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    if not MANIFEST.exists():
        print("No fetch_manifest.json found — run fetch_papers.py first.")
        return 1

    with MANIFEST.open(encoding="utf-8") as fh:
        manifest = json.load(fh)

    papers = manifest.get("papers", {})
    pathways = manifest.get("pathways", {})

    print("=== Paper corpus status ===")
    print(f"  Metadata files: {len(list(META_DIR.glob('*.json')))}")
    print(f"  PDF files:      {len(list(PDF_DIR.glob('*.pdf')))}")
    print(f"  Pathways:       {len(pathways)}")
    print(f"  Unique papers:  {len(papers)}")
    print(f"  include_in_corpus=true:  {sum(1 for p in papers.values() if p.get('include_in_corpus', True))}")
    print(f"  include_in_corpus=false: {sum(1 for p in papers.values() if not p.get('include_in_corpus', True))}")

    for pathway, state in sorted(pathways.items()):
        ids = state.get("paper_ids", [])
        selected = sum(1 for pid in ids if papers.get(pid, {}).get("include_in_corpus", True))
        print(f"\n--- {pathway} ({state.get('count', 0)}/{state.get('target', '?')}) ---")
        for pid in ids:
            entry = papers.get(pid, {})
            flag = "KEEP" if entry.get("include_in_corpus", True) else "SKIP"
            pdf = "pdf" if entry.get("pdf_downloaded") or (PDF_DIR / f"{pid}.pdf").exists() else "no-pdf"
            title = (entry.get("title") or pid)[:75]
            query = (entry.get("discovered_via_query") or "")[:55]
            print(f"  [{flag}] [{pdf}] {pid}")
            print(f"         {title}")
            if query:
                print(f"         query: {query}...")
            abstract = (entry.get("abstract") or "")[:120]
            if abstract:
                print(f"         {abstract}...")

    print("\nTo exclude a paper, set include_in_corpus: false in data/papers/fetch_manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
