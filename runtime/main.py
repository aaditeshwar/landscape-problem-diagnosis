from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import CORS_ORIGINS
from db import get_client
from logging_setup import configure_logging, log_startup_config
from routers import (
    claude_review,
    clusters,
    config_public,
    context,
    evidence_cards,
    evidence_suggestions,
    execute,
    feedback,
    locate,
    logs,
    map as map_router,
    mws,
    query,
    triage,
    village,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log_startup_config()
    get_client().admin.command("ping")
    yield
    get_client().close()


app = FastAPI(
    title="Landscape Problem Diagnosis API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(map_router.router)
app.include_router(mws.router)
app.include_router(village.router)
app.include_router(locate.router)
app.include_router(query.router)
app.include_router(feedback.router)
app.include_router(claude_review.router)
app.include_router(context.router)
app.include_router(clusters.router)
app.include_router(evidence_cards.router)
app.include_router(evidence_suggestions.router)
app.include_router(config_public.router)
app.include_router(execute.router)
app.include_router(logs.router)
app.include_router(triage.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health")
def health():
    get_client().admin.command("ping")
    return {"status": "ok"}


@app.get("/api/ingested-tehsils")
def ingested_tehsils():
    from db import get_db

    db = get_db()
    rows = []
    for doc in db.ingest_manifest.find({"status": "complete"}).sort("_id", 1):
        rows.append(
            {
                "id": doc["_id"],
                "mws_count": doc.get("mws_count"),
                "village_count": doc.get("village_count"),
                "geometries_fetched": doc.get("geometries_fetched"),
            }
        )
    return {"tehsils": rows, "count": len(rows)}
