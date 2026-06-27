#!/usr/bin/env python3
"""Re-export data/raw_jsons/{uid}.json for every MWS in Mongo (full corpus)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

load_dotenv(ROOT / ".env")

from db import get_db  # noqa: E402
from services.mws_export import ensure_mws_export  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Limit MWS count (debug)")
    args = parser.parse_args()

    db = get_db()
    cursor = db.mws_data.find({}, {"uid": 1}).sort("uid", 1)
    if args.limit:
        cursor = cursor.limit(args.limit)

    uids = [str(row["uid"]) for row in cursor if row.get("uid")]
    print(f"Re-exporting {len(uids)} MWS to data/raw_jsons/")
    ok = 0
    for index, uid in enumerate(uids, start=1):
        export = ensure_mws_export(db, uid, force_refresh=True)
        if export:
            ok += 1
        if index % 100 == 0 or index == len(uids):
            print(f"  {index}/{len(uids)} ({ok} written)")
    print(f"Done — {ok}/{len(uids)} exports written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
