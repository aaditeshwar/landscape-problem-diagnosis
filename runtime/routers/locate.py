from pydantic import BaseModel, Field

from fastapi import APIRouter

from db import get_db
from services.resolver import locate_point

router = APIRouter(prefix="/api", tags=["locate"])


class LocateRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


@router.post("/locate")
def locate(body: LocateRequest):
    db = get_db()
    return locate_point(db, body.lon, body.lat)
