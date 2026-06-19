from fastapi import APIRouter

from services.context_clusters import load_context_clusters

router = APIRouter(prefix="/api/context-clusters", tags=["context"])


@router.get("")
def list_context_clusters():
    return {"clusters": load_context_clusters()}
