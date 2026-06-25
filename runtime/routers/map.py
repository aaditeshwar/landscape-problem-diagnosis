import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from db import get_db
from services.geojson import boundaries_to_feature_collection, dissolve_boundary_geometry
from services.tehsil_refs import make_tehsil_ref, tehsil_membership_query

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/map", tags=["map"])

STATIC_GEOJSON = Path(__file__).resolve().parents[1] / "static" / "tehsil_list.geojson"


@router.get("/tehsils")
def get_tehsils():
    """Return tehsil boundary FeatureCollection for initial map load."""
    if STATIC_GEOJSON.exists():
        return json.loads(STATIC_GEOJSON.read_text(encoding="utf-8"))

    log.warning(
        "%s is missing — serving dissolved tehsil_boundaries from MongoDB. "
        "Run scripts/build_spatial_index.py for faster loads and SOI admin boundaries.",
        STATIC_GEOJSON,
    )
    db = get_db()
    docs = list(db.tehsil_boundaries.find({}, {"state": 1, "district": 1, "tehsil": 1, "geometry": 1, "mws_count": 1}))
    features = []
    for doc in docs:
        geom = doc.get("geometry")
        if not geom:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "state": doc.get("state"),
                    "district": doc.get("district"),
                    "tehsil": doc.get("tehsil"),
                    "mws_count": doc.get("mws_count"),
                },
                "geometry": dissolve_boundary_geometry(geom),
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("/mws")
def get_mws_boundaries(
    state: str = Query(...),
    district: str = Query(...),
    tehsil: str = Query(...),
):
    db = get_db()
    tehsil_ref = make_tehsil_ref(state, district, tehsil)
    docs = list(
        db.mws_boundaries.find(
            {"state": state, "district": district, "tehsil": tehsil},
            {"uid": 1, "geometry": 1, "state": 1, "district": 1, "tehsil": 1},
        )
    )
    if not docs:
        uids = [
            row["uid"]
            for row in db.mws_data.find(tehsil_membership_query(tehsil_ref), {"uid": 1})
            if row.get("uid")
        ]
        if uids:
            docs = list(
                db.mws_boundaries.find(
                    {"uid": {"$in": uids}, "geometry": {"$exists": True}},
                    {"uid": 1, "geometry": 1, "state": 1, "district": 1, "tehsil": 1},
                )
            )
            for doc in docs:
                doc["state"] = state
                doc["district"] = district
                doc["tehsil"] = tehsil
    if not docs:
        raise HTTPException(status_code=404, detail="No MWS boundaries found for tehsil")
    return boundaries_to_feature_collection(docs, id_field="uid")


@router.get("/villages")
def get_village_boundaries(
    state: str = Query(...),
    district: str = Query(...),
    tehsil: str = Query(...),
):
    db = get_db()
    docs = list(
        db.village_boundaries.find(
            {"state": state, "district": district, "tehsil": tehsil},
            {"village_id": 1, "geometry": 1, "state": 1, "district": 1, "tehsil": 1},
        )
    )
    if not docs:
        raise HTTPException(status_code=404, detail="No village boundaries found for tehsil")
    return boundaries_to_feature_collection(docs, id_field="village_id")
