# Project Understanding — Agro-Ecological Problem Diagnosis System

**Date:** 2026-06-07  
**Source artifacts:** `README.md`, `plan.md`, `metadata/*.json`, `scripts/ingest_excel.py`

---

## Purpose

Build an **interactive, location-aware system** for diagnosing social-ecological problems in Indian **micro-watersheds (MWSes)** — typically scoped to a tehsil. Users select or locate an MWS on a map, describe a problem in natural language, and receive:

1. Evidence-grounded causal pathway diagnoses (from research literature)
2. Interactive follow-up questions for missing variables
3. Recommended solutions from a structured framework
4. Dynamic charts and choropleth map layers driven by data and queries

---

## Two-Phase Architecture

| Phase | When | Where | Output |
|-------|------|-------|--------|
| **Preprocessing** | One-time / per tehsil update | Local machine | MongoDB collections + paper corpus + evidence cards |
| **Runtime** | Always-on | Local A4500 GPU + AtlasLocalDev MongoDB | FastAPI backend + React/Leaflet frontend |

**Database:** `diagnosis_db` on MongoDB 8.2.5 AtlasLocalDev (`mongodb://localhost:27017`)

---

## Knowledge Artifacts (metadata/)

| File | Role |
|------|------|
| `data_dictionary_v2.json` | 111 variables (91 available, 20 not-available); static vs time-series; Excel column mapping; agricultural year convention (2017 = Jul 2017–Jun 2018) |
| `diagnosis_framework.json` | 4 production systems → 10 stresses → 33 causal pathways → 152 variable mappings → 95 solutions |
| `reference_standards.json` | NBSS-LUP AER-1..20, ACWADAM 6 aquifer types, 5 rainfall regimes, visualization spec (single vars, pairs, default MWS panel, query-triggered charts) |
| `evidence_card_schema.json` | JSON Schema (Draft-07) for literature-grounded evidence cards |
| `evidence_card_example.json` | Worked example: `groundwater_stress` in hard-rock semi-arid context |
| `pathway_queries.json` | 8–13 Semantic Scholar / OpenAlex queries per causal pathway (~22 pathway keys present) |

---

## Existing Implementation

| Component | Status | Location |
|-----------|--------|----------|
| Excel ingest + geometry fetch | **Complete** (923 lines) | `scripts/ingest_excel.py` |
| Paper fetch | Not started | `scripts/fetch_papers.py` (to create) |
| Chunk + embed | Not started | `scripts/chunk_and_embed.py` (to create) |
| Evidence card generation | Not started | `scripts/generate_evidence_cards.py` (to create) |
| Spatial index export | Not started | `scripts/build_spatial_index.py` (to create) |
| FastAPI runtime | Not started | `runtime/` (to create) |
| React frontend | Not started | `frontend/` (to create) |

### ingest_excel.py — Key Behaviors (verified)

- Reads 32 Excel sheets via openpyxl; upserts to `mws_data`, `village_data`
- **Recomputes** `delta_g_mm = P − ET − Runoff` and `cumulative_g_mm` (ignores buggy source G/DeltaG columns)
- Reshapes wide time-series columns to `{year_int: value}` nested objects
- Maps CoRE Stack aquifer labels → ACWADAM 6-class taxonomy
- Applies `/100` correction to drainage density
- Excludes BANAYAT (JUNE) village (`village_id = 0`)
- Fetches MWS/village GeoJSON from CoRE Stack API; builds dissolved tehsil boundary via Shapely `unary_union`
- Maintains idempotent `ingest_manifest` with `--force` and `--skip-geometries` flags
- Creates 2dsphere indexes on boundary collections

---

## Directory Layout Note

`plan.md` references `preprocessing/` and `schemas/`; the workspace uses **`scripts/`** and **`metadata/`**. Implementation should follow the actual layout unless reorganized deliberately.

---

## External Dependencies

| Service | Purpose | Env var |
|---------|---------|---------|
| CoRE Stack API | MWS/village geometries | `CORE_STACK_API_KEY` |
| MongoDB AtlasLocalDev | All data storage | `MONGO_URI` |
| Anthropic Claude API | Evidence card extraction | `ANTHROPIC_API_KEY` |
| Ollama (local GPU) | Embeddings + reasoning LLMs | — |
| Google Places | Map search autocomplete | `GOOGLE_MAPS_KEY` |
| Semantic Scholar / OpenAlex / Unpaywall | Paper acquisition | — |

**Ollama models:** `nomic-embed-text`, `qwen2.5:14b`, `llama3.1:8b`

---

## End-to-End Data Flow

```
Darwha Excel + CoRE Stack API
        ↓ ingest_excel.py
mws_data, village_data, *_boundaries, ingest_manifest
        ↓ fetch_papers.py (pathway_queries.json)
data/papers/pdfs + metadata
        ↓ chunk_and_embed.py (Ollama nomic-embed-text)
paper_chunks (vector index)
        ↓ generate_evidence_cards.py (Claude API + schema)
evidence_cards (vector index)
        ↓ build_spatial_index.py
runtime/static/tehsil_list.geojson
        ↓ FastAPI + React
User: select MWS → query → diagnosis + charts + choropleth
```

---

## Reference End-to-End Test (from README)

Select **Darwha** tehsil → click **MWS 4_100672** → query groundwater stress → verify diagnosis, follow-up questions, and panel chart updates.
