"""Load flat case-study rows from metadata/case_study_locations_v2.json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CASE_STUDY_PATH = ROOT / "metadata" / "case_study_locations_v2.json"

DEFAULT_PROBLEM = (
    "What landscape stresses and production-system problems exist in this micro-watershed?"
)


def load_mws_admin_by_uid(uids: list[str]) -> dict[str, dict[str, str]]:
    """Return uid -> {state, district, tehsil} from Mongo mws_data (primary tehsil)."""
    unique = sorted({str(u).strip() for u in uids if str(u).strip()})
    if not unique:
        return {}

    from dotenv import load_dotenv
    from pymongo import MongoClient

    load_dotenv(ROOT / ".env")
    runtime_dir = ROOT / "runtime"
    if str(runtime_dir) not in sys.path:
        sys.path.insert(0, str(runtime_dir))
    from services.tehsil_refs import primary_tehsil  # noqa: E402

    client = MongoClient(
        os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        serverSelectionTimeoutMS=5000,
    )
    db = client["diagnosis_db"]
    out: dict[str, dict[str, str]] = {}
    for doc in db.mws_data.find(
        {"uid": {"$in": unique}},
        {"uid": 1, "state": 1, "district": 1, "tehsil": 1, "tehsils": 1},
    ):
        uid = str(doc.get("uid") or "").strip()
        if not uid:
            continue
        ref = primary_tehsil(doc)
        if ref:
            out[uid] = {
                "state": ref["state"],
                "district": ref["district"],
                "tehsil": ref["tehsil"],
            }
    return out


def enrich_case_study_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach state/district/tehsil from mws_data for each row's mws_id."""
    admin = load_mws_admin_by_uid([str(r.get("mws_id") or "") for r in rows])
    for row in rows:
        loc = admin.get(str(row.get("mws_id") or ""), {})
        row["state"] = loc.get("state", "")
        row["district"] = loc.get("district", "")
        row["tehsil"] = loc.get("tehsil", "")
    return rows


def load_case_study_rows(*, include_stress_only: bool = False) -> list[dict[str, Any]]:
    """Return one dict per case-study row with expected pathway metadata."""
    with CASE_STUDY_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    rows: list[dict[str, Any]] = []

    def walk(
        node: Any,
        production: str | None = None,
        stress: str | None = None,
        pathway: str | None = None,
    ) -> None:
        if isinstance(node, dict):
            if "case_studies" in node and isinstance(node["case_studies"], list):
                is_stress_only = pathway == "__stress_only__"
                if is_stress_only and not include_stress_only:
                    return
                for entry in node["case_studies"]:
                    mws_id = str(entry.get("mws_id") or "").strip()
                    if not mws_id:
                        continue
                    rows.append(
                        {
                            "case_study_id": entry.get("case_study_id"),
                            "mws_id": mws_id,
                            "lat": entry.get("lat"),
                            "lng": entry.get("lng"),
                            "production_system": production,
                            "observed_stress": stress,
                            "expected_pathway": None if is_stress_only else pathway,
                            "stress_only": is_stress_only,
                        }
                    )
            for key, value in node.items():
                if key == "production_systems":
                    for prod, pdata in (value or {}).items():
                        for stress_name, sdata in (pdata.get("observed_stresses") or {}).items():
                            for pathway_id, pdata2 in (sdata.get("causal_pathways") or {}).items():
                                walk(pdata2, prod, stress_name, pathway_id)
                elif key not in ("meta", "diagnosis_framework", "normalisation_note", "note"):
                    walk(value, production, stress, pathway)
        elif isinstance(node, list):
            for item in node:
                walk(item, production, stress, pathway)

    walk(raw.get("diagnosis_framework") or raw)
    return rows
