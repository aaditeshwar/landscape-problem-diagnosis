"""Triage API — case-study catalog, section evaluation, drafts, dashboard artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import ROOT
from db import get_db
from services import triage_draft_store as draft_store
from services import triage_patch_store as patch_store
from services.reviewer_access import ReviewerNotAllowedError, validate_reviewer_name
from services.built_pathways import BUILT_PATHWAY_IDS, NONE_OF_THESE_PATHWAY
from services.triage_card_map import card_map_payload, load_card_with_fallback
from services.triage_eval import evaluate_section
from services.triage_index import list_case_study_catalogs, load_case_study_rows_from_file, load_catalog_bundle, section_key
from services.user_case_study_catalog import (
    EXAMPLE_CATALOG_PATH,
    parse_catalog_bytes,
    save_user_catalog,
    verify_saved_catalog,
)
from services.variable_catalog import build_variable_catalog
from services.dashboard_policy import filter_dashboard_section, load_dashboard_chart_policy
from services.mws_variable_values import mws_variable_values_payload

router = APIRouter(prefix="/api/triage", tags=["triage"])

DASHBOARD_DIR = ROOT / "data" / "triage_dashboard"


class CardEditPayload(BaseModel):
    card_id: str = Field(min_length=1)
    diagnostic_signals: list[dict[str, Any]] | None = None
    confirmation_policy: dict[str, Any] | None = None
    missing_variable_questions: list[dict[str, Any]] | None = None


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
    follow_up_by_mws: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Per MWS uid: missing_variable -> MCQ choice_id",
    )


class SaveDraftBody(BaseModel):
    diagnostic_signals: list[dict[str, Any]] = Field(default_factory=list)
    confirmation_policy: dict[str, Any] | None = None
    section: dict[str, str] | None = None


class CatalogPatchCardBody(BaseModel):
    card_id: str = Field(min_length=1)
    diagnostic_signals: list[dict[str, Any]] = Field(default_factory=list)
    confirmation_policy: dict[str, Any] | None = None


class SaveCatalogPatchesBody(BaseModel):
    reviewer: str = Field(min_length=1)
    cards: list[CatalogPatchCardBody] = Field(default_factory=list)


@router.get("/catalogs")
def triage_catalogs():
    return {"catalogs": list_case_study_catalogs()}


@router.get("/catalogs/example")
def triage_catalog_example():
    if not EXAMPLE_CATALOG_PATH.is_file():
        raise HTTPException(status_code=404, detail="Example catalog template is not available")
    return FileResponse(
        EXAMPLE_CATALOG_PATH,
        media_type="application/json",
        filename="case_study_catalog_example.json",
    )


@router.post("/catalogs/upload")
async def triage_catalog_upload(
    file: UploadFile = File(...),
    filename: str | None = Query(None, max_length=120),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=400, detail="Catalog file is too large (max 2 MB)")

    try:
        payload = parse_catalog_bytes(raw)
        if not isinstance(payload, dict):
            raise ValueError("Catalog must be a JSON object")
        suggested = filename or file.filename
        out_path = save_user_catalog(payload, filename=suggested)
        verify_saved_catalog(out_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rel = f"user-case-studies/{out_path.name}"
    instance_count = len(load_case_study_rows_from_file(rel))
    return {
        "filename": rel,
        "catalog_filename": rel,
        "instance_count": instance_count,
    }


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
def triage_card(card_id: str, catalog: str | None = Query(default=None)):
    db = get_db()
    card = load_card_with_fallback(db, card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")
    raw_card = dict(card)
    catalog_patch = None
    changed_fields = None
    patch_stale = False
    patch_discarded_reason = None
    if catalog:
        doc = patch_store.load_catalog_doc(catalog)
        entry = (doc.get("cards") or {}).get(card_id)
        if isinstance(entry, dict):
            patch_view = patch_store.catalog_patch_view(entry, raw_card, card_id)
            catalog_patch = patch_view.get("patch")
            changed_fields = patch_view.get("changed_fields")
            patch_stale = bool(patch_view.get("patch_stale"))
            patch_discarded_reason = patch_view.get("patch_discarded_reason")
    else:
        draft = draft_store.load_draft(card_id)
        if draft:
            card = draft_store.apply_draft_to_card(card, draft)
    return {
        "card": raw_card,
        "raw_card": raw_card,
        "catalog_patch": catalog_patch,
        "changed_fields": changed_fields,
        "patch_stale": patch_stale,
        "patch_discarded_reason": patch_discarded_reason,
        "batch_id": patch_store.batch_id_for_catalog(catalog) if catalog else None,
    }


@router.post("/evaluate-section")
def triage_evaluate_section(body: EvaluateSectionBody):
    db = get_db()
    card_edits = {
        item.card_id: {
            "diagnostic_signals": item.diagnostic_signals,
            "confirmation_policy": item.confirmation_policy,
            "missing_variable_questions": item.missing_variable_questions,
        }
        for item in body.card_edits
        if item.diagnostic_signals is not None
        or item.confirmation_policy is not None
        or item.missing_variable_questions is not None
    }
    instances = [item.model_dump() for item in body.instances]
    return evaluate_section(
        db,
        production_system=body.production_system,
        observed_stress=body.observed_stress,
        instances=instances,
        card_edits=card_edits,
        follow_up_by_mws=body.follow_up_by_mws,
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


@router.get("/patches/{catalog_filename}")
def triage_get_catalog_patches(catalog_filename: str):
    doc = patch_store.load_catalog_doc(catalog_filename, prune_stale=False)
    return patch_store.enrich_catalog_doc(doc)


@router.post("/patches/{catalog_filename}")
def triage_save_catalog_patches(catalog_filename: str, body: SaveCatalogPatchesBody):
    db = get_db()
    try:
        return patch_store.save_catalog_patches(
            db,
            catalog_filename,
            reviewer=body.reviewer,
            cards=[item.model_dump() for item in body.cards],
        )
    except ReviewerNotAllowedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/variable-catalog")
def triage_variable_catalog():
    return build_variable_catalog()


@router.get("/mws-variable-values/{mws_id}")
def triage_mws_variable_values(mws_id: str):
    db = get_db()
    payload = mws_variable_values_payload(db, mws_id)
    if not payload:
        raise HTTPException(status_code=404, detail=f"MWS not found: {mws_id}")
    return payload


@router.get("/dashboard/chart-defaults")
def triage_dashboard_chart_defaults():
    policy = load_dashboard_chart_policy()
    return {
        "version": policy.get("version", 1),
        "variables": policy.get("variables") or {},
    }


@router.get("/dashboard/manifest")
def triage_dashboard_manifest():
    manifest_path = DASHBOARD_DIR / "manifest.json"
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {"sections": payload.get("sections") or [], "dashboard_dir": str(DASHBOARD_DIR)}

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
    payload = json.loads(path.read_text(encoding="utf-8"))
    return filter_dashboard_section(payload)
