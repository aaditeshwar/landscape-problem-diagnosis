from fastapi import APIRouter, Query

from config import CLUSTER_COG_URL, CLUSTER_COG_VIEWER_URL
from routers.clusters import public_cluster_cog_url
from services.variable_search import search_variables

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config/public")
def public_config():
    return {
        "cluster_cog_url": public_cluster_cog_url(),
        "cluster_cog_viewer_url": CLUSTER_COG_VIEWER_URL,
        "remote_cluster_cog_url": CLUSTER_COG_URL,
    }


@router.get("/variables")
def variables_search(q: str = Query("", max_length=200), limit: int = Query(50, ge=1, le=200)):
    return {"query": q, "variables": search_variables(q, limit=limit)}
