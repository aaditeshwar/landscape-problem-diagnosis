from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from services.log_reader import dashboard_meta, get_event, list_events

router = APIRouter(prefix="/api/logs", tags=["logs"])

DASHBOARD_HTML = Path(__file__).resolve().parents[1] / "static" / "logs" / "dashboard.html"


@router.get("/meta")
def logs_meta():
    return dashboard_meta()


@router.get("/events")
def logs_events(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return list_events(offset=offset, limit=limit)


@router.get("/events/{index}")
def logs_event_detail(index: int):
    if index < 0:
        raise HTTPException(status_code=400, detail="index must be non-negative")
    event = get_event(index)
    if event is None:
        raise HTTPException(status_code=404, detail=f"No event at index {index}")
    return event


@router.get("/dashboard")
def logs_dashboard_page():
    if not DASHBOARD_HTML.is_file():
        raise HTTPException(status_code=404, detail="Dashboard HTML not found")
    return FileResponse(DASHBOARD_HTML, media_type="text/html")
