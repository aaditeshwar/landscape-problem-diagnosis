from fastapi import APIRouter, HTTPException

from db import get_db
from services.geojson import sanitize_mongo_doc
from services.mws_enrich import enrich_mws_doc

router = APIRouter(prefix="/api/mws", tags=["mws"])


@router.get("/{uid}")
def get_mws(uid: str):
    db = get_db()
    doc = db.mws_data.find_one({"uid": uid})
    if not doc:
        raise HTTPException(status_code=404, detail=f"MWS not found: {uid}")
    return sanitize_mongo_doc(enrich_mws_doc(db, doc))
