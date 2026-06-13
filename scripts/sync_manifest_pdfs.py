"""Sync pdf_downloaded flags in fetch_manifest.json from files on disk."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "papers" / "fetch_manifest.json"
PDF_DIR = ROOT / "data" / "papers" / "pdfs"


def main() -> int:
    with MANIFEST.open(encoding="utf-8") as fh:
        manifest = json.load(fh)

    on_disk = {p.stem for p in PDF_DIR.glob("*.pdf")}
    papers = manifest.get("papers", {})

    for pid, entry in papers.items():
        entry["pdf_downloaded"] = pid in on_disk

    manifest["papers"] = papers
    with MANIFEST.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    selected = [pid for pid, e in papers.items() if e.get("include_in_corpus", True)]
    sel_ok = sum(1 for pid in selected if pid in on_disk)
    missing = [pid for pid in selected if pid not in on_disk]

    print(f"Selected (include_in_corpus): {len(selected)}")
    print(f"PDFs on disk:                 {len(on_disk)}")
    print(f"Selected with PDF:            {sel_ok}")
    print(f"Selected missing PDF:         {len(missing)}")
    if missing:
        print("\nMissing PDFs:")
        for pid in sorted(missing):
            title = (papers[pid].get("title") or pid)[:72]
            print(f"  {pid}")
            try:
                print(f"    {title}")
            except UnicodeEncodeError:
                print(f"    {title.encode('ascii', 'replace').decode()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
