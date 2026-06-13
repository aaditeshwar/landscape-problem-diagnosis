"""Validate fetch_manifest.json after manual review."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "papers" / "fetch_manifest.json"
META_DIR = ROOT / "data" / "papers" / "metadata"

REQUIRED_PAPER_FIELDS = {"title", "include_in_corpus", "pathway_tags"}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not MANIFEST.exists():
        print("ERROR: fetch_manifest.json not found")
        return 1

    with MANIFEST.open(encoding="utf-8") as fh:
        manifest = json.load(fh)

    papers = manifest.get("papers", {})
    pathways = manifest.get("pathways", {})

    if not papers:
        errors.append("papers section is empty")
    if not pathways:
        errors.append("pathways section is empty")

    # Field checks on every paper entry
    for pid, entry in papers.items():
        missing = REQUIRED_PAPER_FIELDS - set(entry.keys())
        if missing:
            errors.append(f"{pid}: missing fields {missing}")
        if "include_in_corpus" in entry and not isinstance(entry["include_in_corpus"], bool):
            errors.append(f"{pid}: include_in_corpus must be boolean, got {entry['include_in_corpus']!r}")

    # Cross-reference pathway paper_ids
    referenced: set[str] = set()
    for pathway, state in pathways.items():
        ids = state.get("paper_ids") or []
        if state.get("count") != len(ids):
            warnings.append(
                f"{pathway}: count={state.get('count')} but len(paper_ids)={len(ids)}"
            )
        for pid in ids:
            referenced.add(pid)
            if pid not in papers:
                errors.append(f"{pathway}: paper_id {pid} not in papers section")

    orphan = set(papers.keys()) - referenced
    if orphan:
        warnings.append(f"{len(orphan)} paper(s) in papers section not listed under any pathway")

    # Metadata file existence
    missing_meta = [pid for pid in papers if not (META_DIR / f"{pid}.json").exists()]
    if missing_meta:
        errors.append(f"{len(missing_meta)} paper(s) missing metadata JSON files")

    # Summary stats
    kept = [pid for pid, e in papers.items() if e.get("include_in_corpus", True)]
    skipped = [pid for pid, e in papers.items() if not e.get("include_in_corpus", True)]

    print("=== Manifest validation ===\n")
    print(f"Pathways:     {len(pathways)}")
    print(f"Total papers: {len(papers)}")
    print(f"KEEP (true):  {len(kept)}")
    print(f"SKIP (false): {len(skipped)}")

    print("\n--- Per pathway ---")
    for pathway, state in sorted(pathways.items()):
        ids = state.get("paper_ids") or []
        k = sum(1 for pid in ids if papers.get(pid, {}).get("include_in_corpus", True))
        s = len(ids) - k
        print(f"  {pathway}: {k} keep / {s} skip (of {len(ids)} candidates)")

    if skipped:
        print("\n--- Excluded papers (include_in_corpus: false) ---")
        for pid in sorted(skipped):
            title = papers[pid].get("title", pid)[:72]
            tags = ", ".join(papers[pid].get("pathway_tags") or [])
            print(f"  {pid}")
            print(f"    {title}")
            print(f"    pathways: {tags}")

    if warnings:
        print("\n--- Warnings ---")
        for w in warnings:
            print(f"  ! {w}")

    if errors:
        print("\n--- ERRORS (must fix before proceeding) ---")
        for e in errors:
            print(f"  X {e}")
        return 1

    print("\nResult: VALID — ready for --download-selected")
    print(f"  Will download PDFs for {len(kept)} paper(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
