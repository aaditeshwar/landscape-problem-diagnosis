#!/usr/bin/env python3
"""Recompute aquifer.acwadam_class from lithology + nbss_lup_aer_code for ingested MWS."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(ROOT / "scripts"))

load_dotenv(ROOT / ".env")

from ingest_excel import refine_aquifer_acwadam  # noqa: E402

DB_NAME = "diagnosis_db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Refine ACWADAM aquifer class on existing mws_data")
    parser.add_argument("--state", help="Limit to MWS with this state")
    parser.add_argument("--district", help="Limit to MWS with this district")
    parser.add_argument("--tehsil", help="Limit to MWS with this tehsil")
    args = parser.parse_args()

    filt: dict = {}
    if args.state:
        filt["state"] = args.state
    if args.district:
        filt["district"] = args.district
    if args.tehsil:
        filt["tehsil"] = args.tehsil

    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]
    uids = [doc["uid"] for doc in db.mws_data.find(filt, {"uid": 1})]
    stats = refine_aquifer_acwadam(db, uids)
    print(
        f"Refined aquifer ACWADAM: requested={stats['requested']} "
        f"updated={stats['updated']} missing_lithology={stats['missing']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
