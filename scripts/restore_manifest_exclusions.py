"""Apply saved include_in_corpus exclusions to fetch_manifest.json."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "papers" / "fetch_manifest.json"
EXCLUSIONS = ROOT / "data" / "papers" / "include_in_corpus_exclusions.json"


def main() -> int:
    with EXCLUSIONS.open(encoding="utf-8") as fh:
        excluded = set(json.load(fh))

    with MANIFEST.open(encoding="utf-8") as fh:
        manifest = json.load(fh)

    papers = manifest.get("papers", {})
    applied = 0
    missing = []

    for pid in excluded:
        if pid not in papers:
            missing.append(pid)
            continue
        papers[pid]["include_in_corpus"] = False
        applied += 1

    for pid, entry in papers.items():
        if pid not in excluded and "include_in_corpus" not in entry:
            entry["include_in_corpus"] = True

    manifest["papers"] = papers
    with MANIFEST.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    kept = sum(1 for e in papers.values() if e.get("include_in_corpus", True))
    skipped = len(papers) - kept
    print(f"Restored exclusions: {applied} set to false")
    if missing:
        print(f"Not in manifest (skipped): {len(missing)}")
        for pid in missing:
            print(f"  {pid}")
    print(f"Manifest now: {kept} keep / {skipped} skip (of {len(papers)} papers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
