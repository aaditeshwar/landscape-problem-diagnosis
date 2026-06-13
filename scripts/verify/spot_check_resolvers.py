#!/usr/bin/env python3
"""Spot-check variable resolvers for newly inducted pathways."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from db import get_db  # noqa: E402
from services.assembler import find_pathway, resolve_variable  # noqa: E402
from services.mws_enrich import enrich_mws_doc  # noqa: E402

DEFAULT_PATHWAYS = [
    "forest_degradation",
    "encroachment",
    "multi_sector_vulnerability",
    "small_landholding",
    "groundwater_stress",
]

DERIVED_VARS = [
    "trend_annual_delta_g_mm",
    "mean_annual_delta_g_mm",
    "drought_moderate_return_period",
    "mean_swb_rabi_kharif_ratio",
]


def pathway_variables(pathway_id: str) -> list[str]:
    found = find_pathway(pathway_id)
    if not found:
        return []
    cfg, _prod, _stress = found
    return [
        v["variable"]
        for v in cfg.get("diagnostic_variables", [])
        if v.get("availability") == "available"
    ]


def pick_sample_mws(db, prefer_forest: bool = False) -> dict | None:
    query: dict = {}
    if prefer_forest:
        query["lulc_ha"] = {"$exists": True, "$ne": {}}
    doc = db.mws_data.find_one(query, sort=[("uid", 1)])
    if not doc:
        return None
    return enrich_mws_doc(db, doc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pathway",
        action="append",
        dest="pathways",
        help="Pathway id (repeatable). Defaults to NTFP + socio batch.",
    )
    parser.add_argument("--uid", help="Specific MWS uid to test against")
    args = parser.parse_args()
    pathways = args.pathways or DEFAULT_PATHWAYS

    db = get_db()
    if args.uid:
        raw = db.mws_data.find_one({"uid": args.uid})
        if not raw:
            print(f"MWS not found: {args.uid}")
            return 1
        mws = enrich_mws_doc(db, raw)
    else:
        mws = pick_sample_mws(db, prefer_forest=True) or pick_sample_mws(db)
        if not mws:
            print("No MWS documents in database.")
            return 1

    print(f"\n=== Resolver spot-check (MWS {mws.get('uid')}) ===")
    failures = 0
    for pathway_id in pathways:
        vars_ = pathway_variables(pathway_id)
        if not vars_:
            print(f"\n{pathway_id}: pathway not found in framework")
            failures += 1
            continue

        print(f"\n{pathway_id}:")
        for var in vars_:
            val = resolve_variable(mws, var)
            status = "OK" if val is not None else "MISSING"
            preview = json.dumps(val, default=str)[:80] if val is not None else "—"
            print(f"  {status:7} {var:30} {preview}")
            if val is None:
                failures += 1

    print("\nderived variables:")
    for var in DERIVED_VARS:
        val = resolve_variable(mws, var)
        status = "OK" if val is not None else "MISSING"
        preview = json.dumps(val, default=str)[:80] if val is not None else "—"
        print(f"  {status:7} {var:30} {preview}")
        if val is None:
            failures += 1

    blocked = ["annual_cumulative_g_mm", "drainage_density_km_per_km2", "restoration_protection_ha"]
    print("\nblocked variables (expect MISSING):")
    for var in blocked:
        val = resolve_variable(mws, var)
        status = "OK" if val is None else "UNEXPECTED"
        print(f"  {status:11} {var}")
        if val is not None:
            failures += 1

    print(f"\n=== {'PASS' if failures == 0 else f'{failures} missing value(s)'} ===")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
