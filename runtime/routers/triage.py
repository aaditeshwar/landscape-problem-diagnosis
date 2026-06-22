"""Triage API — case-study catalog, section evaluation, drafts, dashboard artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import ROOT
from db import get_db
from services import triage_draft_store as draft_store
from services.built_pathways import BUILT_PATHWAY_IDS, NONE_OF_THESE_PATHWAY
from services.triage_card_map import card_map_payload, load_card_with_fallback
from services.triage_eval import evaluate_section
from services.triage_index import list_case_study_catalogs, load_catalog_bundle, section_key
from services.variable_catalog import build_variable_catalog

router = APIRouter(prefix="/api/triage", tags=["triage"])

DASHBOARD_DIR = ROOT / "data" / "triage_dashboard"
CHART_DEFAULTS_PATH = ROOT / "metadata" / "dashboard_chart_defaults.json"


class CardEditPayload(BaseModel):
    card_id: str = Field(min_length=1)
    diagnostic_signals: list[dict[str, Any]] | None = None
    confirmation_policy: dict[str, Any] | None = None


class EvaluateInstancePayload(BaseModel):
    case_study_id: int | None = None
    mws_id: str = Field(min_length=1)
    expected_pathway: str | None = None
    stress_only: bool = False


class EvaluateSectionBody(BaseModel):
    production_system: str = Field(min_length=1)
    observed_stress: str = Field(min_length=1)
    instances: list[EvaluateInstancePayload] = Field(min_length=1)
    card_edits: list[CardEditPayload] = Field(default_factory=list)


class SaveDraftBody(BaseModel):
    diagnostic_signals: list[dict[str, Any]] = Field(default_factory=list)
    confirmation_policy: dict[str, Any] | None = None
    section: dict[str, str] | None = None


@router.get("/catalogs")
def triage_catalogs():
    return {"catalogs": list_case_study_catalogs()}


@router.get("/catalog/{filename}")
def triage_catalog(filename: str):
    db = get_db()
    try:
        return load_catalog_bundle(db, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/built-pathways")
def triage_built_pathways():
    return {
        "built_pathways": sorted(BUILT_PATHWAY_IDS),
        "none_of_these": NONE_OF_THESE_PATHWAY,
    }


@router.get("/card-map")
def triage_card_map(mws_id: str = Query(min_length=1)):
    db = get_db()
    payload = card_map_payload(db, mws_id)
    if not payload.get("found"):
        raise HTTPException(status_code=404, detail=f"MWS not found: {mws_id}")
    cards = payload.pop("cards", {})
    # Return full cards for UI init (signals + policy)
    payload["cards_full"] = cards
    return payload


@router.get("/card/{card_id:path}")
def triage_card(card_id: str):
    db = get_db()
    card = load_card_with_fallback(db, card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")
    draft = draft_store.load_draft(card_id)
    if draft:
        card = draft_store.apply_draft_to_card(card, draft)
    return {"card": card, "draft": draft}


@router.post("/evaluate-section")
def triage_evaluate_section(body: EvaluateSectionBody):
    db = get_db()
    card_edits = {
        item.card_id: {
            "diagnostic_signals": item.diagnostic_signals,
            "confirmation_policy": item.confirmation_policy,
        }
        for item in body.card_edits
        if item.diagnostic_signals is not None or item.confirmation_policy is not None
    }
    instances = [item.model_dump() for item in body.instances]
    return evaluate_section(
        db,
        production_system=body.production_system,
        observed_stress=body.observed_stress,
        instances=instances,
        card_edits=card_edits,
    )


@router.get("/drafts/{card_id:path}")
def triage_get_draft(card_id: str):
    draft = draft_store.load_draft(card_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.post("/drafts/{card_id:path}")
def triage_save_draft(card_id: str, body: SaveDraftBody):
    return draft_store.save_draft(
        card_id,
        diagnostic_signals=body.diagnostic_signals,
        confirmation_policy=body.confirmation_policy,
        section=body.section,
    )


@router.get("/variable-catalog")
def triage_variable_catalog():
    return build_variable_catalog()


@router.get("/dashboard/chart-defaults")
def triage_dashboard_chart_defaults():
    if not CHART_DEFAULTS_PATH.is_file():
        return {"version": 1, "variables": {}}
    return json.loads(CHART_DEFAULTS_PATH.read_text(encoding="utf-8"))


@router.get("/dashboard/manifest")
def triage_dashboard_manifest():
    sections: list[dict[str, str]] = []
    if DASHBOARD_DIR.is_dir():
        for path in sorted(DASHBOARD_DIR.glob("*.json")):
            if path.name == "manifest.json":
                continue
            sections.append(
                {
                    "section_key": path.stem,
                    "filename": path.name,
                }
            )
    return {"sections": sections, "dashboard_dir": str(DASHBOARD_DIR)}


@router.get("/dashboard/{section_key}")
def triage_dashboard_section(section_key: str):
    path = DASHBOARD_DIR / f"{section_key}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Dashboard section not found: {section_key}")
    return json.loads(path.read_text(encoding="utf-8"))
