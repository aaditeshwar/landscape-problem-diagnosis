#!/usr/bin/env python3
"""Attach nbss_lup_aer_code to all ingested MWS documents from boundary geometries.

Uses point-in-polygon against data/India_AER_NBSS_LUP.geojson. To refresh that
file from the official Esri Living Atlas NBSS-LUP layer, run:
  python scripts/maintenance/fetch_aer_geojson.py --print-source
  python scripts/maintenance/fetch_aer_geojson.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap()

from dotenv import load_dotenv
from pymongo import MongoClient

from lib.aer_lookup import DEFAULT_AER_GEOJSON, attach_aer_to_mws, validate_aer_geojson  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geojson", type=Path, default=DEFAULT_AER_GEOJSON, help="AER boundary GeoJSON")
    parser.add_argument("--state", help="Limit to one state")
    parser.add_argument("--district", help="Limit to one district (requires --state)")
    parser.add_argument("--tehsil", help="Limit to one tehsil (requires --district)")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    report = validate_aer_geojson(args.geojson)
    for line in report.summary_lines():
        print(line)
    if not report.ok:
        print("Fix AER GeoJSON first (run scripts/maintenance/fetch_aer_geojson.py).")
        return 1

    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB", "diagnosis_db")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db = client[db_name]

    filt: dict = {}
    if args.state:
        filt["state"] = args.state
    if args.district:
        filt["district"] = args.district
    if args.tehsil:
        filt["tehsil"] = args.tehsil

    uids = [doc["uid"] for doc in db.mws_data.find(filt, {"uid": 1}) if doc.get("uid")]
    print(f"MWS documents selected: {len(uids)}")

    if args.dry_run:
        with_boundary = db.mws_boundaries.count_documents({"uid": {"$in": uids}, "geometry": {"$exists": True}})
        already = db.mws_data.count_documents({**filt, "nbss_lup_aer_code": {"$exists": True, "$ne": None}})
        print(f"With boundary geometry: {with_boundary}")
        print(f"Already tagged with nbss_lup_aer_code: {already}")
        return 0

    stats = attach_aer_to_mws(db, uids, geojson_path=args.geojson)
    print(
        "Updated: {updated} | missing boundary: {missing_boundary} | "
        "lookup failed: {lookup_failed} | requested: {requested}".format(**stats)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
