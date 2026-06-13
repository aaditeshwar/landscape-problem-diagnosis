"""Audit tehsil Excel exports and CoRE Stack API for bug reporting."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402
from lib.excel_audit import audit_locations  # noqa: E402
from lib.tehsil_excel_catalog import RAW_EXCEL_DIR, TehsilLocation, resolve_catalog  # noqa: E402

ROOT = bootstrap()
DEFAULT_OUTPUT = ROOT / "data" / "excel_core_stack_audit.json"

LEGACY_TEHSILS = [
    ("Jharkhand__Dumka__Masalia_data.xlsx", "Jharkhand", "Dumka", "Masalia"),
    ("Bihar__Jamui__Jamui_data.xlsx", "Bihar", "Jamui", "Jamui"),
    ("Gujarat__Amreli__Amreli_data.xlsx", "Gujarat", "Amreli", "Amreli"),
    ("Karnataka__Bagalkot__Hungund_data.xlsx", "Karnataka", "Bagalkot", "Hungund"),
    ("Karnataka__Raichur__Devadurga_data.xlsx", "Karnataka", "Raichur", "Devadurga"),
    ("Odisha__Anugul__Anugul_data.xlsx", "Odisha", "Anugul", "Anugul"),
    ("Rajasthan__Bhilwara__Mandalgarh_data.xlsx", "Rajasthan", "Bhilwara", "Mandalgarh"),
    ("Telangana__Medak__Tupran_data.xlsx", "Telangana", "Medak", "Tupran"),
    ("Maharashtra__Yavatmal__Darwha_data.xlsx", "Maharashtra", "Yavatmal", "Darwha"),
]


def legacy_entries() -> list[tuple[TehsilLocation, Path]]:
    entries: list[tuple[TehsilLocation, Path]] = []
    for filename, state, district, tehsil in LEGACY_TEHSILS:
        path = RAW_EXCEL_DIR / filename
        if path.is_file():
            entries.append((TehsilLocation(state=state, district=district, tehsil=tehsil), path))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit tehsil Excel exports against CoRE Stack APIs")
    parser.add_argument("--state", help="Filter active locations by state")
    parser.add_argument("--district", help="Filter active locations by district")
    parser.add_argument("--tehsil", help="Filter active locations by tehsil")
    parser.add_argument(
        "--from-active",
        action="store_true",
        help="Audit all active locations with synced Excel files (default when no legacy flag)",
    )
    parser.add_argument(
        "--legacy-nine",
        action="store_true",
        help="Audit the original nine manually synced tehsils only",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON report path")
    args = parser.parse_args()

    if args.legacy_nine:
        entries = legacy_entries()
    else:
        found, missing = resolve_catalog(
            state=args.state,
            district=args.district,
            tehsil=args.tehsil,
        )
        entries = []
        for location, _source in found:
            path = location.standard_path
            if path.is_file():
                entries.append((location, path))
        if missing:
            print(f"Skipping {len(missing)} active location(s) with no stats Excel source.", file=sys.stderr)

    if not entries:
        print("No Excel files found to audit.", file=sys.stderr)
        return 1

    report = audit_locations(entries)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
