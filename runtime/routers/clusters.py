from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

import httpx

from config import CLUSTER_COG_URL, CLUSTER_COG_VIEWER_URL
from services.cluster_palette import load_cluster_palette, suffix_for_raster_value
from services.cluster_raster_query import query_cluster_at_point
from services.context_clusters import cluster_by_suffix

router = APIRouter(prefix="/api/clusters", tags=["clusters"])

ROOT = Path(__file__).resolve().parents[2]
LOCAL_COG_PATH = ROOT / "data" / "clusters.tif"


def public_cluster_cog_url() -> str | None:
    if LOCAL_COG_PATH.is_file() or CLUSTER_COG_URL:
        return "/api/clusters/cog"
    return None


@router.get("/cog")
def cluster_cog():
    if LOCAL_COG_PATH.is_file():
        return FileResponse(LOCAL_COG_PATH, media_type="image/tiff", filename="clusters.tif")
    if CLUSTER_COG_URL:
        def iter_remote():
            with httpx.Client(timeout=120.0) as client:
                with client.stream("GET", CLUSTER_COG_URL) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        yield chunk

        return StreamingResponse(iter_remote(), media_type="image/tiff")
    raise HTTPException(status_code=404, detail="Cluster COG is not configured")


@router.get("/palette")
def cluster_palette():
    palette = load_cluster_palette()
    clusters = cluster_by_suffix()
    enriched = []
    for entry in palette:
        suffix = entry.get("suffix")
        cluster = clusters.get(str(suffix)) if suffix else None
        enriched.append(
            {
                **entry,
                "cluster": cluster,
            }
        )
    return {"palette": enriched}


@router.get("/suffix/{raster_value}")
def cluster_suffix_lookup(raster_value: int):
    suffix = suffix_for_raster_value(raster_value)
    cluster = cluster_by_suffix().get(suffix) if suffix else None
    return {"raster_value": raster_value, "suffix": suffix, "cluster": cluster}


@router.get("/raster-query")
def cluster_raster_query(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    try:
        result = query_cluster_at_point(lat, lon)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail="No cluster at this location") from error

    if not result.get("cluster_suffix"):
        raise HTTPException(status_code=404, detail="No cluster at this location")
    return result
