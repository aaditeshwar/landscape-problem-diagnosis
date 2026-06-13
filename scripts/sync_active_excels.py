"""
sync_active_excels.py
=====================
Fetch active CoRE Stack locations, copy matching stats Excel files into
data/raw_excel using the standard naming convention, report missing files,
and optionally run the Excel / CoRE Stack audit.

Usage:
    # Full sync for all active locations
    python scripts/sync_active_excels.py

    # Preview without copying
    python scripts/sync_active_excels.py --dry-run

    # Scope to one state / district / tehsil
    python scripts/sync_active_excels.py --state Bihar
    python scripts/sync_active_excels.py --state Bihar --district Nalanda --tehsil Hilsa
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import ROOT, bootstrap
from lib.excel_audit import audit_locations
from lib.tehsil_excel_catalog import RAW_EXCEL_DIR, resolve_catalog

ROOT = bootstrap()
SYNC_REPORT = RAW_EXCEL_DIR / "sync_report.json"
AUDIT_REPORT = ROOT / "data" / "excel_core_stack_audit.json"


def copy_excel(source: Path, destination: Path, *, dry_run: bool, force: bool) -> str:
    if destination.exists() and not force:
        if destination.stat().st_size == source.stat().st_size:
            return "skipped_existing"
        return "skipped_different_size"

    if dry_run:
        return "would_copy"

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return "copied"


def summarize_audit(report: dict[str, dict]) -> dict[str, int]:
    with_excel_issues = sum(1 for item in report.values() if item["excel_export_issues"])
    with_api_issues = sum(1 for item in report.values() if item["core_stack_api_issues"])
    return {
        "audited": len(report),
        "with_excel_export_issues": with_excel_issues,
        "with_core_stack_api_issues": with_api_issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync active tehsil Excel files into data/raw_excel")
    parser.add_argument("--state", help="Filter by state label (case/spacing insensitive)")
    parser.add_argument("--district", help="Filter by district label")
    parser.add_argument("--tehsil", help="Filter by tehsil label")
    parser.add_argument("--dry-run", action="store_true", help="Report actions without copying files")
    parser.add_argument("--force", action="store_true", help="Overwrite existing destination files")
    parser.add_argument("--skip-audit", action="store_true", help="Skip Excel / CoRE Stack audit")
    parser.add_argument(
        "--audit-output",
        default=str(AUDIT_REPORT),
        help="Path for audit JSON report",
    )
    parser.add_argument(
        "--report-output",
        default=str(SYNC_REPORT),
        help="Path for sync summary JSON report",
    )
    args = parser.parse_args()

    try:
        found, missing = resolve_catalog(
            state=args.state,
            district=args.district,
            tehsil=args.tehsil,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    copied = 0
    would_copy = 0
    skipped = 0
    sync_entries: list[dict] = []

    for location, source in found:
        destination = location.standard_path
        action = copy_excel(source, destination, dry_run=args.dry_run, force=args.force)
        if action == "copied":
            copied += 1
        elif action == "would_copy":
            would_copy += 1
        elif action.startswith("skipped"):
            skipped += 1
        sync_entries.append(
            {
                "manifest_id": location.manifest_id,
                "state": location.state,
                "district": location.district,
                "tehsil": location.tehsil,
                "source_excel": str(source.relative_to(ROOT)),
                "destination_excel": str(destination.relative_to(ROOT)),
                "action": action,
            }
        )

    missing_entries = [
        {
            "manifest_id": location.manifest_id,
            "state": location.state,
            "district": location.district,
            "tehsil": location.tehsil,
            "expected_stats_filename": f"{location.district.lower()}_{location.tehsil.lower()}.xlsx",
        }
        for location in missing
    ]

    audit_report: dict[str, dict] = {}
    audit_summary: dict[str, int] | None = None
    if not args.skip_audit and found:
        audit_targets = [(location, location.standard_path) for location, _ in found]
        if args.dry_run:
            audit_targets = [(location, source) for location, source in found]
        print(f"Running Excel audit for {len(audit_targets)} tehsil(s)...")
        audit_report = audit_locations(audit_targets)
        audit_summary = summarize_audit(audit_report)
        audit_path = Path(args.audit_output)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit_report, indent=2), encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "state": args.state,
            "district": args.district,
            "tehsil": args.tehsil,
        },
        "dry_run": args.dry_run,
        "summary": {
            "active_locations_matched": len(found),
            "missing_stats_excel": len(missing),
            "copied": copied,
            "would_copy": would_copy,
            "skipped": skipped,
        },
        "sync_entries": sync_entries,
        "missing_locations": missing_entries,
        "audit_summary": audit_summary,
    }

    report_path = Path(args.report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Matched active locations: {len(found)}")
    print(f"Missing stats Excel files: {len(missing)}")
    if args.dry_run:
        print(f"Would copy: {would_copy}  Skipped: {skipped}")
    else:
        print(f"Copied: {copied}  Skipped: {skipped}")
    if missing:
        print("\nMissing Excel for:")
        for entry in missing_entries:
            print(f"  - {entry['manifest_id']}")
    if audit_summary:
        print(
            "\nAudit summary: "
            f"{audit_summary['audited']} audited, "
            f"{audit_summary['with_excel_export_issues']} with Excel export gaps, "
            f"{audit_summary['with_core_stack_api_issues']} with CoRE Stack API gaps"
        )
        print(f"Audit report: {args.audit_output}")
    print(f"Sync report: {args.report_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
