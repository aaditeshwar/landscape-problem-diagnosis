import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from db import get_db
from services.geojson import boundaries_to_feature_collection

router = APIRouter(prefix="/api/map", tags=["map"])

STATIC_GEOJSON = Path(__file__).resolve().parents[1] / "static" / "tehsil_list.geojson"


@router.get("/tehsils")
def get_tehsils():
    """Return tehsil boundary FeatureCollection for initial map load."""
    if STATIC_GEOJSON.exists():
        return json.loads(STATIC_GEOJSON.read_text(encoding="utf-8"))

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
                "geometry": geom,
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
    docs = list(
        db.mws_boundaries.find(
            {"state": state, "district": district, "tehsil": tehsil},
            {"uid": 1, "geometry": 1, "state": 1, "district": 1, "tehsil": 1},
        )
    )
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
