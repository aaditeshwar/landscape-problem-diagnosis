"""Query-bank evaluation batches for the /review app."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.query_eval_store import list_batches, load_batch

router = APIRouter(prefix="/api/query-eval", tags=["query-eval"])


@router.get("/batches")
def query_eval_batches():
    batches = list_batches()
    return {
        "batches": [
            {
                "batch_id": row.get("batch_id"),
                "generated_at": row.get("generated_at"),
                "updated_at": row.get("updated_at"),
                "catalog": row.get("catalog"),
                "case_study_count": len(row.get("case_studies") or []),
                "modes": row.get("modes") or [],
                "dry_run": row.get("dry_run"),
            }
            for row in batches
        ]
    }


@router.get("/batch/{batch_id}")
def query_eval_batch(batch_id: str):
    try:
        return load_batch(batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
