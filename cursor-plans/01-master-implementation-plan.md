# Master Implementation Plan

**Date:** 2026-06-07  
**Based on:** `plan.md` v3, adapted to workspace layout (`scripts/`, `metadata/`)

---

## Guiding Principles

1. **Data first** — MongoDB must contain ingested MWS/village data and vector-indexed evidence before runtime work is meaningful.
2. **Schema-driven** — All variable access, chart rendering, and evidence card validation flow from `metadata/` JSON artifacts.
3. **Incremental validation** — Each preprocessing step and each API endpoint gets a standalone smoke test before integration.
4. **Minimal scope per PR** — Preprocessing scripts, runtime services, and frontend components in separate deliverable chunks.

---

## Phase 0 — Environment & Project Scaffolding

**Goal:** Runnable dev environment with all secrets and dependencies.

### Steps

| # | Task | Deliverable |
|---|------|-------------|
| 0.1 | Create `.env` from template with `MONGO_URI`, `CORE_STACK_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_MAPS_KEY` | `.env` (gitignored) |
| 0.2 | Install AtlasLocalDev (MongoDB 8.2.5) via Atlas CLI | Running local MongoDB |
| 0.3 | Create `scripts/requirements.txt` (openpyxl, pandas, pymongo, shapely, requests, pdfplumber, anthropic, python-dotenv, jsonschema) | requirements file |
| 0.4 | Pull Ollama models: `nomic-embed-text`, `qwen2.5:14b`, `llama3.1:8b` | Models ready on GPU |
| 0.5 | Create directory skeleton: `data/raw_excel/`, `data/papers/pdfs/`, `data/papers/metadata/`, `runtime/`, `frontend/` | Directory tree |
| 0.6 | Load `diagnosis_framework.json` and `data_dictionary_v2.json` into MongoDB as versioned single docs | `diagnosis_framework`, `data_dictionary` collections |

**Exit criteria:** `pip install -r scripts/requirements.txt` succeeds; MongoDB reachable; Ollama serves embeddings.

---

## Phase 1 — Data Ingest (Step 1 of preprocessing)

**Goal:** Darwha tehsil fully ingested with geometries.

### Steps

| # | Task | Notes |
|---|------|-------|
| 1.1 | Place `Darwha_data.xlsx` in `data/raw_excel/` | Source tehsil for all E2E tests |
| 1.2 | Run `python scripts/ingest_excel.py --excel data/raw_excel/Darwha_data.xlsx --state Maharashtra --district Yavatmal --tehsil Darwha` | ~5 min |
| 1.3 | Verify MongoDB: ~99 MWS docs, ~116 village docs, manifest status `complete` | Query `ingest_manifest`, `mws_data.count_documents()` |
| 1.4 | Verify geometries: `mws_boundaries`, `village_boundaries`, `tehsil_boundaries` with 2dsphere indexes | Spot-check MWS `4_100672` |
| 1.5 | Validate key transforms: `delta_g_mm` recomputed, drainage `/100`, time-series nested by year, BANAYAT excluded | Sample doc inspection |

**Exit criteria:** Manifest complete; MWS `4_100672` has hydrological, aquifer, SOGE, and intersect_villages fields populated.

---

## Phase 2 — Paper Corpus (Step 2)

**Goal:** ~265–396 open-access papers stored locally, tagged by pathway.

### Steps

| # | Task | Deliverable |
|---|------|-------------|
| 2.1 | Implement `scripts/fetch_papers.py` | Script |
| 2.2 | Read queries from `metadata/pathway_queries.json` (one set per pathway key) | — |
| 2.3 | Query Semantic Scholar + OpenAlex; deduplicate by DOI/title | — |
| 2.4 | Resolve PDF URLs via Unpaywall; download to `data/papers/pdfs/` | PDF files |
| 2.5 | Write metadata JSON per paper to `data/papers/metadata/` (title, authors, year, abstract, pathway_tags, doi) | Metadata files |
| 2.6 | Track fetch progress in MongoDB or local manifest for resumability | Idempotent re-runs |

**Exit criteria:** 8–12 papers per pathway; PDF + metadata for each; no duplicate DOIs.

**Estimated runtime:** 2–4 hours (rate-limited API calls).

---

## Phase 3 — Chunking & Embedding (Step 3)

**Goal:** Searchable `paper_chunks` collection with Atlas Vector Search index.

### Steps

| # | Task | Deliverable |
|---|------|-------------|
| 3.1 | Implement `scripts/chunk_and_embed.py` | Script |
| 3.2 | Extract PDF text with pdfplumber; abstract → separate chunk (`retrieval_weight: 2.0`) | — |
| 3.3 | Body → 512-token chunks, 128-token overlap | — |
| 3.4 | Tag chunks: `paper_id`, `pathway_tags[]`, `aer_tags[]`, `aquifer_tags[]`, `rainfall_regime`, `page`, `section_heading` | — |
| 3.5 | Embed via Ollama `nomic-embed-text` (768-dim cosine) | Embeddings |
| 3.6 | Upsert to `paper_chunks`; create Atlas Vector Search index via CLI | Index: `paper_chunk_vector_index` |

**Exit criteria:** Vector search returns relevant chunks for a test query like "groundwater depletion hard rock".

**Estimated runtime:** 1–2 hours (GPU).

---

## Phase 4 — Evidence Cards (Step 4)

**Goal:** ~100 evidence cards in MongoDB, schema-validated, vector-indexed.

### Steps

| # | Task | Deliverable |
|---|------|-------------|
| 4.1 | Implement `scripts/generate_evidence_cards.py` | Script |
| 4.2 | Build Claude extraction prompt using `evidence_card_schema.json`, `evidence_card_example.json`, `reference_standards.json`, `diagnosis_framework.json` | Prompt template |
| 4.3 | Include AER-from-text instruction (no geometry; approximate AER assignment from paper location/climate) | Per plan.md §Step 4 |
| 4.4 | Generate one card per pathway × context cluster (aquifer + AER); validate against JSON Schema | ~100 cards |
| 4.5 | Embed card text; upsert to `evidence_cards`; create vector index with pre-filters on `pathway_tags`, `aer_tags`, `aquifer_tags` | Index: `evidence_card_vector_index` |
| 4.6 | Set `reviewed_by_expert: false` initially; `review_weight: 1.0` | Expert review later |

**Exit criteria:** Cards validate against schema; vector search with aquifer pre-filter returns groundwater_stress cards for volcanic/hard-rock contexts.

**Estimated cost:** ~$3 Claude API.

---

## Phase 5 — Spatial Index Export (Step 5)

**Goal:** Lightweight tehsil GeoJSON for fast frontend initial load.

### Steps

| # | Task | Deliverable |
|---|------|-------------|
| 5.1 | Implement `scripts/build_spatial_index.py` | Script |
| 5.2 | Query `tehsil_boundaries` for state, district, tehsil, geometry, mws_count | — |
| 5.3 | Write GeoJSON FeatureCollection to `runtime/static/tehsil_list.geojson` | Static file |

**Exit criteria:** Valid GeoJSON; Darwha tehsil polygon present with correct properties.

---

## Phase 6 — FastAPI Runtime Backend

**Goal:** REST API serving map geometries, MWS data, diagnosis queries, and code-act execution.

### Directory structure

```
runtime/
├── main.py
├── routers/
│   ├── map.py          # /api/map/*
│   ├── mws.py          # /api/mws/{uid}
│   ├── village.py      # /api/village/{id}
│   ├── query.py        # /api/query, /api/answer, /api/locate
│   └── execute.py      # /api/execute
├── services/
│   ├── resolver.py     # lat/lon → MWS + village
│   ├── retriever.py    # Atlas vector search on evidence_cards + paper_chunks
│   ├── assembler.py    # Variable bundle from diagnosis_framework + mws_data
│   ├── reasoner.py     # Ollama Qwen/Llama prompts
│   ├── code_executor.py # Sandboxed Python subprocess
│   └── session_manager.py
├── static/
│   └── tehsil_list.geojson
└── requirements.txt
```

### Steps

| # | Task | Endpoint / Service |
|---|------|-------------------|
| 6.1 | Scaffold FastAPI app with CORS, MongoDB connection, Ollama client | `main.py` |
| 6.2 | Map geometry endpoints | `GET /api/map/tehsils`, `/api/map/mws/{tehsil}`, `/api/map/villages/{tehsil}` |
| 6.3 | MWS and village data endpoints | `GET /api/mws/{uid}`, `GET /api/village/{id}` |
| 6.4 | Location resolver | `POST /api/locate` — `$geoIntersects` on `mws_boundaries` |
| 6.5 | Diagnosis query flow | `POST /api/query` — embed → retrieve cards → assemble vars → Qwen2.5 14B → JSON response |
| 6.6 | Follow-up answers | `POST /api/answer` — inject user variable → Llama 3.1 8B re-reason |
| 6.7 | Session persistence | `sessions` collection with turns, retrieved cards, panel_updates |
| 6.8 | Code-act execution | `POST /api/execute` — Llama generates Python → sandbox (10s, no network/file I/O) → GeoJSON choropleth |
| 6.9 | Serve static tehsil GeoJSON | `StaticFiles` mount |

**Exit criteria:** `POST /api/query` for MWS `4_100672` + "wells drying up" returns JSON with `confirmed_pathways`, `panel_updates`, and optional follow-up question.

---

## Phase 7 — React Frontend

**Goal:** Interactive India map with MWS diagnosis workflow.

### Stack

React 18 + TypeScript + Leaflet + Recharts + TailwindCSS

### Components

| Component | Responsibility |
|-----------|----------------|
| `MapView.tsx` | OSM base, tehsil/MWS/village layers, code-act choropleth |
| `SearchBox.tsx` | Google Places + Nominatim fallback |
| `SidePanel.tsx` | Tehsil/MWS info + query box |
| `InfoSection.tsx` | 5 default MWS panel sections per `visualization_spec.default_mws_panel` |
| `DiagnosisPanel.tsx` | Pathway rankings, solutions, follow-up questions |
| `DynamicCharts.tsx` | Query-triggered Recharts from `visualization_spec.query_triggered_panel_updates` |
| `CodeActLayer.tsx` | Choropleth from `/api/execute` |
| `chartSpec.ts` | Maps variable names → Recharts config from `reference_standards.json` |

### Interaction flow

1. Load `tehsil_list.geojson` → render amber tehsil polygons
2. Click tehsil → load MWS + village boundaries → side panel summary
3. Click MWS → default 5-section info panel + query box
4. Submit diagnosis query → render diagnosis + activate chart pairs
5. Answer follow-up → re-query backend
6. Code-act natural language → choropleth overlay with toggle

**Exit criteria:** Full E2E test passes (Darwha → MWS 4_100672 → groundwater query → charts update).

---

## Phase 8 — Quality, Review & Iteration

| Task | When |
|------|------|
| Expert review CLI for evidence cards (`reviewed_by_expert`, `review_weight: 2.0`) | After Phase 4 |
| Session feedback loop (flag rejected diagnoses) | After Phase 7 |
| Incremental tehsil ingest (new Excel → run ingest only) | Ongoing |
| Pathway-specific re-fetch/re-embed when framework changes | As needed |

---

## Implementation Order Summary

```
Phase 0  Environment setup
   ↓
Phase 1  ingest_excel.py (EXISTS — run & verify)
   ↓
Phase 2  fetch_papers.py
   ↓
Phase 3  chunk_and_embed.py
   ↓
Phase 4  generate_evidence_cards.py
   ↓
Phase 5  build_spatial_index.py
   ↓
Phase 6  FastAPI runtime
   ↓
Phase 7  React frontend
   ↓
Phase 8  Quality & iteration
```

**Parallelization opportunity:** Phase 6 map/data endpoints can begin after Phase 1 (no LLM needed for geometry + MWS panel). Phases 2–4 must complete before diagnosis query endpoints.

---

## Risk Register

| Risk | Mitigation |
|------|------------|
| CoRE Stack API unavailable | `--skip-geometries`; reuse cached boundaries from manifest |
| SOGE is block-level, masks MWS stress | Require corroboration from well depth + delta_g (in evidence cards) |
| 20 not-available variables | Missing-variable questions in evidence cards + follow-up flow |
| Code-act sandbox timeout on complex joins | 10s limit; restrict to pymongo + stdlib; tehsil-scoped filters |
| Google Places cost | GCP budget cap; OSM Nominatim fallback |
| Pathway query count < 33 in current JSON | Verify `pathway_queries.json` covers all framework pathways before fetch |
