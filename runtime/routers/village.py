from fastapi import APIRouter, HTTPException

from db import get_db
from services.geojson import sanitize_mongo_doc

router = APIRouter(prefix="/api/village", tags=["village"])


@router.get("/{village_id}")
def get_village(village_id: int):
    db = get_db()
    doc = db.village_data.find_one({"village_id": village_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Village not found: {village_id}")
    return sanitize_mongo_doc(doc)
