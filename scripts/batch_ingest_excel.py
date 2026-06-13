"""
batch_ingest_excel.py
=====================
Ingest synced tehsil Excel files from data/raw_excel for active CoRE Stack
locations that are not already marked complete in ingest_manifest.

Usage:
    python scripts/batch_ingest_excel.py --state Bihar
    python scripts/batch_ingest_excel.py --state Bihar --district Nalanda
    python scripts/batch_ingest_excel.py --state Bihar --district Nalanda --tehsil Hilsa
    python scripts/batch_ingest_excel.py --dry-run
    python scripts/batch_ingest_excel.py --force
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

from _bootstrap import SCRIPTS_DIR, bootstrap
from lib.tehsil_excel_catalog import RAW_EXCEL_DIR, resolve_catalog

ROOT = bootstrap()
INGEST_SCRIPT = SCRIPTS_DIR / "ingest_excel.py"
DB_NAME = "diagnosis_db"


def is_ingested(db, manifest_id: str) -> bool:
    doc = db.ingest_manifest.find_one({"_id": manifest_id}, {"status": 1})
    return bool(doc and doc.get("status") == "complete")


def run_ingest(
    excel_path: Path,
    state: str,
    district: str,
    tehsil: str,
    *,
    force: bool,
    skip_geometries: bool,
) -> int:
    command = [
        sys.executable,
        str(INGEST_SCRIPT),
        "--excel",
        str(excel_path),
        "--state",
        state,
        "--district",
        district,
        "--tehsil",
        tehsil,
    ]
    if force:
        command.append("--force")
    if skip_geometries:
        command.append("--skip-geometries")
    result = subprocess.run(command, cwd=str(ROOT))
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch ingest synced tehsil Excel files")
    parser.add_argument("--state", help="Filter by state label")
    parser.add_argument("--district", help="Filter by district label")
    parser.add_argument("--tehsil", help="Filter by tehsil label")
    parser.add_argument("--dry-run", action="store_true", help="Show planned ingests only")
    parser.add_argument("--force", action="store_true", help="Re-ingest even if manifest is complete")
    parser.add_argument(
        "--skip-geometries",
        action="store_true",
        help="Pass --skip-geometries to ingest_excel.py",
    )
    parser.add_argument(
        "--include-missing-sync",
        action="store_true",
        help="Attempt ingest even when the standard Excel file is missing locally",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")

    try:
        found, missing = resolve_catalog(
            state=args.state,
            district=args.district,
            tehsil=args.tehsil,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if missing:
        print(f"Warning: {len(missing)} active location(s) have no stats Excel source file.")
        for location in missing:
            print(f"  - {location.manifest_id}")

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]

    planned: list[tuple[str, Path, str, str, str]] = []
    skipped_complete = 0
    skipped_missing_file = 0

    for location, _source in found:
        excel_path = location.standard_path
        if not excel_path.is_file():
            if args.include_missing_sync:
                skipped_missing_file += 1
                print(f"Missing synced file, skipping: {excel_path}")
                continue
            skipped_missing_file += 1
            print(f"Missing synced file, skipping: {excel_path}")
            continue

        if is_ingested(db, location.manifest_id) and not args.force:
            skipped_complete += 1
            continue

        planned.append(
            (location.manifest_id, excel_path, location.state, location.district, location.tehsil)
        )

    print(f"Planned ingests: {len(planned)}")
    print(f"Already complete (skipped): {skipped_complete}")
    print(f"Missing local Excel (skipped): {skipped_missing_file}")

    if args.dry_run:
        for manifest_id, excel_path, state, district, tehsil in planned:
            print(f"  would ingest {manifest_id} <- {excel_path}")
        return 0

    failures = 0
    for manifest_id, excel_path, state, district, tehsil in planned:
        print(f"Ingesting {manifest_id}...")
        code = run_ingest(
            excel_path,
            state,
            district,
            tehsil,
            force=args.force,
            skip_geometries=args.skip_geometries,
        )
        if code != 0:
            failures += 1
            print(f"Failed ingest for {manifest_id} (exit code {code})", file=sys.stderr)

    if failures:
        print(f"Completed with {failures} failure(s).", file=sys.stderr)
        return 1

    print(f"Successfully ingested {len(planned)} tehsil(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
