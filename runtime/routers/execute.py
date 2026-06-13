from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["execute"])


class ExecuteRequest(BaseModel):
    state: str
    district: str
    tehsil: str
    query: str


@router.post("/execute")
def execute_code_act(_body: ExecuteRequest):
    raise HTTPException(
        status_code=501,
        detail="Code-act execution not implemented yet (Phase 6.8)",
    )
