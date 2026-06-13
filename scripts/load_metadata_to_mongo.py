"""
Load versioned metadata JSON into MongoDB diagnosis_db.

Usage:
    py scripts/load_metadata_to_mongo.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "metadata"
DB_NAME = "diagnosis_db"

DOCUMENTS = [
    {
        "_id": "diagnosis_framework_v1",
        "collection": "diagnosis_framework",
        "source_file": "diagnosis_framework.json",
        "payload_key": "diagnosis_framework",
    },
    {
        "_id": "data_dictionary_v2",
        "collection": "data_dictionary",
        "source_file": "data_dictionary_v2.json",
        "payload_key": "data_dictionary",
    },
]


def main() -> int:
    load_dotenv(ROOT / ".env")
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as exc:
        print(f"ERROR: Cannot connect to MongoDB at {mongo_uri}")
        print(f"  {exc}")
        print("Start MongoDB (AtlasLocalDev or local mongod) and retry.")
        return 1

    db = client[DB_NAME]
    now = datetime.now(timezone.utc).isoformat()

    for spec in DOCUMENTS:
        path = METADATA / spec["source_file"]
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)

        doc = {
            "_id": spec["_id"],
            "version": spec["_id"],
            "source_file": spec["source_file"],
            "loaded_at": now,
            spec["payload_key"]: raw[spec["payload_key"]],
        }
        db[spec["collection"]].replace_one({"_id": spec["_id"]}, doc, upsert=True)
        print(f"Loaded {spec['source_file']} -> {spec['collection']} ({spec['_id']})")

    client.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
