# System Architecture and Implementation Plan
## Agro-Ecological Problem Diagnosis System — v3

---

## Overview

A location-aware, interactive system to diagnose agricultural, ecological, and socio-economic
problems in micro-watersheds (MWSes) across India. Two phases:

- **Preprocessing pipeline**: one-time or per-update; runs on local machine or cloud
- **Runtime system**: always-on; local NVIDIA A4500 (16 GB VRAM) + Ollama + MongoDB 8.2.5 AtlasLocalDev

MongoDB is deployed locally as **AtlasLocalDev** (MongoDB 8.2.5 via Atlas CLI). No cloud storage
limits — collections grow to disk capacity.

---

## Standards Used

| Dimension            | Standard                                   | Reference file              |
|----------------------|--------------------------------------------|-----------------------------|
| Agro-ecological zone | NBSS & LUP 20 AERs (AER-1 to AER-20)      | `reference_standards.json`  |
| Aquifer type         | ACWADAM 6-class taxonomy                   | `reference_standards.json`  |
| Rainfall regime      | 5 bands: arid <740, semi-arid 740–960, sub-humid 960–1200, humid 1200–1620, perhumid >1620 mm | `reference_standards.json` |
| Variable time series | Agricultural year label = start year (2017 = Jul 2017–Jun 2018) | `data_dictionary_v2.json` |

---

## Part 1: MongoDB Collections Design

Database: `diagnosis_db` on local AtlasLocalDev.

```
diagnosis_db/
├── mws_data              # One doc per MWS: all static + time-series variables
├── village_data          # One doc per village: social, economic, NREGA
├── mws_boundaries        # GeoJSON polygon per MWS; 2dsphere index
├── village_boundaries    # GeoJSON polygon per village; 2dsphere index
├── tehsil_boundaries     # Dissolved tehsil polygons; 2dsphere index
├── ingest_manifest       # Tracks (state, district, tehsil) ingest state
├── evidence_cards        # Evidence cards; vector search index
├── paper_chunks          # Paper text chunks; vector search index
├── diagnosis_framework   # Versioned framework JSON (single doc)
├── data_dictionary       # Versioned data dictionary JSON (single doc)
└── sessions              # User query session history
```

### Key indexes

```javascript
db.mws_data.createIndex({ "uid": 1 }, { unique: true })
db.mws_data.createIndex({ "state": 1, "district": 1, "tehsil": 1 })
db.village_data.createIndex({ "village_id": 1 }, { unique: true })
db.village_data.createIndex({ "state": 1, "district": 1, "tehsil": 1 })
db.mws_boundaries.createIndex({ "geometry": "2dsphere" })
db.village_boundaries.createIndex({ "geometry": "2dsphere" })
db.tehsil_boundaries.createIndex({ "geometry": "2dsphere" })
```

Atlas Vector Search indexes (via Atlas CLI for local dev) on `paper_chunks.embedding`
and `evidence_cards.embedding` — cosine similarity, 768 dims, with pre-filters on
`pathway_tags`, `aer_tags`, `aquifer_tags`.

---

## Part 2: Preprocessing Pipeline

### Step 0 — Install Dependencies

```bash
pip install openpyxl pandas pymongo geopandas shapely requests \
            pdfplumber anthropic ollama python-dotenv jsonschema

# Pull Ollama models
ollama pull nomic-embed-text
ollama pull qwen2.5:14b
ollama pull llama3.1:8b
```

Environment file `.env`:

```
CORE_STACK_API_KEY=<your key from dashboard.core-stack.org>
ANTHROPIC_API_KEY=<your Anthropic key>
GOOGLE_MAPS_KEY=<your key>
MONGO_URI=mongodb://localhost:27017
```

---

### Step 1 — Excel Ingest + CoRE Stack Geometry Fetch

**Script:** `preprocessing/ingest_excel.py` *(fully generated — see file)*

#### 1a. CoRE Stack API

Base URL: `https://geoserver.core-stack.org/api/v1`
Authentication: `X-API-Key: <CORE_STACK_API_KEY>` header

Endpoints used:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/get_mws_geometries/` | GeoJSON FeatureCollection of MWS polygons for a tehsil |
| `GET /api/v1/get_village_geometries/` | GeoJSON FeatureCollection of village polygons |

Query parameters for both: `state`, `district`, `tehsil`

Additional discovery endpoints (not used in ingest but available):

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/get_active_locations/` | List all tehsils with data activated |
| `GET /api/v1/get_admin_details_by_latlon/` | Resolve lat/lon → state/district/tehsil |
| `GET /api/v1/get_mwsid_by_latlon/` | Resolve lat/lon → MWS UID |

#### 1b. Manifest management

`ingest_manifest` collection tracks one document per `{state}__{district}__{tehsil}`:

```json
{
  "_id": "Maharashtra__Yavatmal__Darwha",
  "state": "Maharashtra",
  "district": "Yavatmal",
  "tehsil": "Darwha",
  "excel_file": "Darwha_data.xlsx",
  "status": "complete",
  "started_at": "...",
  "completed_at": "...",
  "mws_count": 99,
  "village_count": 116,
  "geometries_fetched": true
}
```

Re-run with `--force` to overwrite an existing complete entry. The script is idempotent
(MongoDB upserts) and safe to re-run on failure.

#### 1c. Key data transformations

All transformations are implemented in `ingest_excel.py`:

| Transformation | Rule |
|----------------|------|
| `drainage_density` | Store raw + `corrected_km_per_km2 = raw / 100` |
| `delta_g_mm` | **Recomputed** as `P − ET − Runoff` per year and season. Raw `DeltaG_in_mm` and `G_in_mm` columns are **ignored** (buggy). |
| `cumulative_g_mm` | Rolling sum of computed `delta_g_mm` from agricultural year 2017 (base = 0) |
| `drought_causality` JSON | Parsed from string to BSON object |
| Time-series columns | Reshaped from wide (`variable_<YYYY-YYYY>`) to nested `{year_int: value}` |
| `kharif_cropped_sqkm` | Multiplied by 100 and stored as `kharif_cropped_ha` |
| `BANAYAT (JUNE)` | Excluded (village_id = 0) from all village collections |
| `aquifer_class` | Mapped from CoRE Stack labels (e.g. "Hard Rock") to ACWADAM taxonomy (e.g. "crystalline_basement") |
| Tehsil boundary | Built by `unary_union` of all MWS polygons via Shapely; stored in `tehsil_boundaries` |

#### 1d. Running the script

```bash
# Basic usage
python preprocessing/ingest_excel.py \
  --excel data/raw_excel/Darwha_data.xlsx \
  --state Maharashtra \
  --district Yavatmal \
  --tehsil Darwha

# Skip geometry fetch (if API key unavailable or already fetched)
python preprocessing/ingest_excel.py \
  --excel data/raw_excel/Darwha_data.xlsx \
  --state Maharashtra --district Yavatmal --tehsil Darwha \
  --skip-geometries

# Force re-ingest (overwrite existing complete manifest)
python preprocessing/ingest_excel.py \
  --excel data/raw_excel/Darwha_data.xlsx \
  --state Maharashtra --district Yavatmal --tehsil Darwha \
  --force
```

---

### Step 2 — Paper Corpus Acquisition

**Script:** `preprocessing/fetch_papers.py`

Uses queries from `schemas/pathway_queries.json`. Queries cover all 33 causal pathways
stratified across India's agro-ecological diversity: all 6 ACWADAM aquifer types, all 20
NBSS-LUP AERs (via geographic terms), and all 5 rainfall regime bands.

**APIs (free):**

```python
# Semantic Scholar
GET https://api.semanticscholar.org/graph/v1/paper/search
    ?query=<query>&fields=title,authors,year,abstract,openAccessPdf,externalIds

# OpenAlex
GET https://api.openalex.org/works?search=<query>&filter=open_access.is_oa:true

# Unpaywall (PDF URL discovery)
GET https://api.unpaywall.org/v2/<doi>?email=<your_email>
```

Target: 8–12 papers per pathway (265–396 papers total). Metadata stored in
`data/papers/metadata/<paper_id>.json`; PDFs in `data/papers/pdfs/<paper_id>.pdf`.

---

### Step 3 — Chunking, Embedding, and Indexing

**Script:** `preprocessing/chunk_and_embed.py`

- PDF text extracted with `pdfplumber`
- Abstract → separate chunk with `retrieval_weight: 2.0`
- Body → 512-token chunks with 128-token overlap
- Each chunk tagged: `paper_id`, `pathway_tags[]`, `aer_tags[]`, `aquifer_tags[]`,
  `rainfall_regime`, `page`, `section_heading`
- Embedded with `nomic-embed-text` via Ollama (768-dim)
- Stored in `paper_chunks` collection with Atlas Vector Search index

---

### Step 4 — Evidence Card Generation

**Script:** `preprocessing/generate_evidence_cards.py`

**AER assignment from paper text (not from geometries):**

When extracting evidence cards from research papers, the Claude API extraction prompt
instructs the model to map the study location to AER codes using textual and climatic
description alone — no spatial computation is needed. The reference in
`reference_standards.json` provides sufficient detail (state names, rainfall ranges,
dominant aquifer, typical crops, physiography) for approximate AER assignment. Approximate
resolution is acceptable because research papers rarely specify precise sub-district
locations either. The extraction prompt includes:

```
Map the study location to its NBSS-LUP AER code (AER-1 to AER-20) using the state name,
rainfall amount, aquifer description, and physiographic terms mentioned in the paper.
Use reference_standards.json for the mapping. Approximate assignment is acceptable —
pick the best-matching AER based on the textual description. If a paper covers multiple
zones, list all applicable AER codes.

Examples:
  "Vidarbha, Maharashtra, ~700–900mm rainfall, basalt/hard rock aquifer" → AER-6
  "Indo-Gangetic Plains, Punjab, canal irrigation, alluvial aquifer"     → AER-9
  "Bundelkhand, UP/MP, 700–1000mm, sedimentary formations"               → AER-10
  "Coastal Tamil Nadu, 900–1200mm, deltaic alluvium"                     → AER-18
  "Western Ghats, Kerala, >2000mm, laterite"                             → AER-19
```

**Card generation pattern:** one card per pathway × context combination (aquifer + AER
cluster), approximately 100 cards total. ~$3 USD one-time Claude API cost.

---

### Step 5 — Spatial Index and Tehsil GeoJSON Export

After all tehsils in the manifest are complete, export a lightweight tehsil list for
frontend initial load:

```python
# preprocessing/build_spatial_index.py
tehsils = db.tehsil_boundaries.find(
    {}, {"state": 1, "district": 1, "tehsil": 1, "geometry": 1, "mws_count": 1}
)
# Write as GeoJSON FeatureCollection to runtime/static/tehsil_list.geojson
```

---

### Preprocessing Summary

| Step | Script | Approx runtime | Cost |
|------|--------|---------------|------|
| 1. Excel ingest + geometries | `ingest_excel.py` | ~5 min/tehsil | Free |
| 2. Paper fetch | `fetch_papers.py` | ~2–4 hr | Free (OA papers) |
| 3. Chunk + embed | `chunk_and_embed.py` | ~1–2 hr (GPU) | Free (local) |
| 4. Evidence cards | `generate_evidence_cards.py` | ~30 min | ~$3 Claude API |
| 5. Spatial export | `build_spatial_index.py` | ~1 min | Free |

---

## Part 3: Runtime Architecture

### Components

```
Browser (React + Leaflet + Recharts)
        │  HTTP
        ▼
FastAPI Application (port 8000)
   ├── /api/map/*           ← geometry serving (tehsil, MWS, village polygons)
   ├── /api/mws/{uid}       ← MWS variable data
   ├── /api/village/{id}    ← village variable data
   ├── /api/locate          ← lat/lon → MWS + village
   ├── /api/query           ← diagnosis query (POST)
   ├── /api/answer          ← follow-up answer (POST)
   └── /api/execute         ← code-act map/data queries (POST)
        │
   ┌────┴──────────────────────────┐
   │                               │
   ▼                               ▼
MongoDB 8.2.5 AtlasLocalDev     Ollama (A4500 GPU)
(all collections)                ├── nomic-embed-text  ~0.5 GB VRAM, always resident
                                 ├── qwen2.5:14b Q4    ~9.0 GB, first-turn reasoning
                                 └── llama3.1:8b Q4    ~5.0 GB, follow-ups + code-act
```

---

### Frontend: Map Interface

**Stack:** React 18 + TypeScript + Leaflet.js + Recharts + TailwindCSS

#### Map layers (bottom to top)

1. OSM base tiles
2. Ingested tehsil polygons (amber fill, from `tehsil_list.geojson`)
3. MWS polygons for selected tehsil (loaded on demand)
4. Village polygons for selected tehsil (loaded on demand, togglable)
5. Code-act choropleth layer (dynamic, from `/api/execute` results)

#### Search box

Google Places Autocomplete → resolves name to lat/lon → map flies to location →
if tehsil has data, highlights it → calls `/api/locate` to find and select the MWS.
OSM Nominatim used as free fallback.

#### Interaction flow

```
Click ingested tehsil polygon
  → highlight tehsil boundary
  → side panel: tehsil name, district, state, MWS count
  → load MWS polygons + village polygons for tehsil

Click MWS polygon
  → highlight MWS
  → side panel: MWS UID, intersecting village names
  → load default MWS info panel (5 sections, see below)
  → query box appears

Click point within MWS (within village polygon)
  → reverse lookup: show village name + MWS UID
  → highlight village polygon
```

#### Default MWS Info Panel (before any query)

Powered by `/api/mws/{uid}`. Organized into 5 collapsible sections per
`reference_standards.json → visualization_spec.default_mws_panel`:

| Section | Key widgets |
|---------|-------------|
| **Identity** | UID, area (ha), terrain cluster, aquifer class (ACWADAM), NBSS-LUP AER, river/canal |
| **Water** | SOGE gauge (colour by class), well depth trend (inverted Y), annual delta_g diverging bar, SWB area multi-line (kharif/rabi/zaid) |
| **Land Use** | LULC stacked area 2017–2024, cropping intensity line, degradation/afforestation paired bar |
| **Climate & Drought** | Annual precipitation bar with historical mean, drought severity stacked bar (18 kharif weeks), dry spell weeks bar |
| **Livelihoods** | NREGA works stacked bar (cumulative by category 2005–2024), facility distances spider chart |

All charts use Recharts; data from `/api/mws/{uid}`.

When a query triggers a diagnosis, the panel adds query-triggered chart pairs
(defined in `reference_standards.json → visualization_spec.query_triggered_panel_updates`),
for example adding a cropping_intensity vs delta_g dual-axis chart when groundwater
stress + cropping pressure are diagnosed together.

---

### Diagnosis Query Flow

#### Step A: Location resolution

```python
# /api/query receives {location, problem_description, session_id?}
# If uid known: use directly
# If lat/lon:
db.mws_boundaries.find_one({
    "geometry": {"$geoIntersects": {"$geometry": {"type": "Point", "coordinates": [lon, lat]}}}
})
# Load full mws_data doc + compute corrected drainage_density, delta_g, cumulative_g
```

#### Step B: Retrieval

```python
query_embedding = ollama.embeddings(model="nomic-embed-text", prompt=problem_description)
# Atlas Vector Search on evidence_cards
pipeline = [{"$vectorSearch": {
    "index": "evidence_card_vector_index",
    "path": "embedding",
    "queryVector": query_embedding,
    "numCandidates": 50,
    "limit": 5,
    "filter": {"aquifer_tags": {"$in": [mws_doc["aquifer"]["acwadam_class"]]}}
}}]
cards = list(db.evidence_cards.aggregate(pipeline))
# For each card: fetch top-3 paper_chunks for citation grounding
```

#### Step C: Variable assembly

For each retrieved pathway, fetch required `diagnostic_variables` from
`diagnosis_framework.json`, resolve against `mws_data` document, tag as
`present | missing`, and load `missing_variable_questions` from the evidence card
for any missing variables.

#### Step D: LLM reasoning (Qwen2.5 14B, first turn)

Prompt structure:

```
[LOCATION CONTEXT]
MWS: {uid} | Tehsil: {tehsil} | District: {district} | State: {state}
Aquifer: {acwadam_class} | Terrain: {cluster} | AER: {aer_code} | Rainfall: {regime}

[USER PROBLEM]
{problem_description}

[MWS VARIABLE VALUES]
{structured bundle of present variables with values, units, year ranges}

[CANDIDATE CAUSAL PATHWAYS — top 5 by vector similarity]
For each:
  Pathway: {pathway_id}
  Evidence reasoning note: {overall_reasoning_note}
  Diagnostic signals: {signal expressions and qualitative conditions}
  Confounders: {confounder list}

[TASK]
1. Assess each pathway: confirmed / suggested / ruled_out — cite variable values.
2. Rank confirmed pathways by confidence (high/medium/low).
3. For uncertain pathways: list most important missing variable + question for user.
4. For confirmed pathways: list solutions from the framework.
5. Identify any pathway not in candidates that the user description suggests.
6. Output field panel_updates: list visualization pair keys to activate in info panel.

Output valid JSON only. No prose outside JSON.
```

#### Step E: Interactive follow-up

```
LLM output parsed for:
  confirmed_pathways[]
  uncertain_pathways[] with missing_variable_questions[]
  solutions[]
  panel_updates[]

Frontend:
  - Renders diagnosis in side panel
  - Activates chart pairs from panel_updates in info panel
  - If uncertain_pathways non-empty: shows top-priority follow-up question in query box

User answers → POST /api/answer {session_id, answer}
  → variable injected as natural-language text into session context
  → re-run reasoning with LLaMA 3.1 8B (faster, narrower context)
  → repeat until all high-priority vars answered or user opts out
```

---

### Code-Act Map and Data Queries

Supports natural language queries that produce **choropleth map layers** or
**tabular/chart responses** over all MWSes or villages in a tehsil.

#### Supported query targets

The system supports code-act queries over **both MWSes and villages**:

| Query type | Example | Target collection |
|------------|---------|-------------------|
| MWS attribute map | "Show MWSes with water balance worse than -200mm" | `mws_data` |
| MWS stress pattern | "Show MWSes with similar groundwater stress to this one" | `mws_data` |
| MWS filter | "Show MWSes in basaltic aquifer with severe drought weeks > 4" | `mws_data` |
| MWS time series | "Show cropping intensity across all MWSes in this tehsil" | `mws_data` |
| Village attribute map | "Show villages with literacy rate below 60%" | `village_data` |
| Village access map | "Show villages more than 10km from the nearest APMC" | `village_data` |
| Village NREGA map | "Show cumulative NREGA soil and water conservation works by village" | `village_data` |
| Cross-entity | "Show villages in MWSes with high groundwater stress" | Both, joined via `intersect_villages` |

#### Architecture

```
User natural language query → POST /api/execute
  → LLM (LLaMA 3.1 8B) generates Python snippet:
      def run_query(mws_col, village_col, mws_boundaries, village_boundaries) -> list[dict]:
          # Returns [{uid_or_vid, geometry_id, color, label, value, entity_type}]

  → FastAPI executes snippet in sandboxed subprocess:
      - Timeout: 10 seconds
      - No network access, no file I/O
      - Access restricted to: mws_data, village_data collections (read-only cursor)
      - No imports except pymongo and standard library math/statistics

  → Returns GeoJSON FeatureCollection with color + tooltip properties
  → Frontend renders as new Leaflet choropleth layer (replaces previous code-act layer)
  → Layer toggle control added to map so user can show/hide it
```

#### LLM code-generation system prompt

```
You are a Python code generator for MongoDB queries on MWS and village data.
Generate a function: run_query(mws_col, village_col, mws_boundaries, village_boundaries) -> list[dict]

The function must:
- Query mws_col (mws_data) and/or village_col (village_data) as needed
- Return a list of dicts: {
    "id": str,           # uid (MWS) or village_id (village)
    "entity_type": str,  # "mws" or "village"
    "color": str,        # hex color, e.g. "#e74c3c"
    "label": str,        # tooltip label
    "value": float|str   # underlying numeric or categorical value
  }
- Use only pymongo cursor operations (find, aggregate) and Python builtins
- Apply the tehsil filter: {"tehsil": "{tehsil}", "district": "{district}", "state": "{state}"}
- For MWS queries: time-series fields are nested dicts keyed by integer year
  e.g. doc["hydrological_annual"][2023]["delta_g_mm"]
- For village queries: use doc["facility_distances_km"]["apmc"] etc.
- For cross-entity queries: use doc["intersect_villages"]["village_ids"] to join
- Use a sensible color scale (e.g. red=bad, green=good, or sequential blues)
- Be safe: no imports beyond pymongo, no file I/O, no network calls

Available MWS fields (key paths): {mws_field_summary}
Available village fields (key paths): {village_field_summary}
Query: "{user_query}"
```

#### Example generated code — village APMC distance

```python
def run_query(mws_col, village_col, mws_boundaries, village_boundaries):
    import colorsys
    results = []
    for doc in village_col.find(
        {"tehsil": "Darwha", "district": "Yavatmal", "state": "Maharashtra"},
        {"village_id": 1, "village_name": 1, "facility_distances_km.apmc": 1}
    ):
        dist = (doc.get("facility_distances_km") or {}).get("apmc")
        if dist is None:
            continue
        # Red > 20km, green < 5km
        norm = min(max(dist / 25.0, 0), 1)
        r, g, b = colorsys.hsv_to_rgb((1 - norm) * 0.33, 0.85, 0.9)
        color = "#{:02x}{:02x}{:02x}".format(int(r*255), int(g*255), int(b*255))
        results.append({
            "id": str(doc["village_id"]),
            "entity_type": "village",
            "color": color,
            "label": f"{doc.get('village_name','?')}: {dist:.1f} km to APMC",
            "value": dist,
        })
    return results
```

The frontend resolves entity geometry from `mws_boundaries` or `village_boundaries`
collection by `entity_type` + `id`, then renders the choropleth.

---

### Session Document

```json
{
  "_id": "session_abc123",
  "created_at": "ISO datetime",
  "mws_uid": "4_100672",
  "state": "Maharashtra", "district": "Yavatmal", "tehsil": "Darwha",
  "aquifer_class": "volcanic",
  "aer_code": "AER-6",
  "turns": [
    {
      "turn": 1,
      "user_input": "Our wells are drying up and cotton yields are falling",
      "retrieved_cards": ["agriculture__water_scarcity__groundwater_stress__001"],
      "llm_model": "qwen2.5:14b",
      "llm_response_json": {...},
      "panel_updates_triggered": ["cropping_intensity + annual_delta_g_mm dual_axis"],
      "missing_vars_asked": ["borewell_density"]
    },
    {
      "turn": 2,
      "user_input": "There are more than 50 borewells in our village",
      "injected_variable": {"borewell_density": "high (>50, user estimate)"},
      "llm_model": "llama3.1:8b",
      "llm_response_json": {...}
    }
  ],
  "final_diagnosis": {
    "confirmed_pathways": ["groundwater_stress", "monocropping"],
    "confidence": {"groundwater_stress": "high", "monocropping": "medium"},
    "solutions": [...]
  }
}
```

---

### A4500 GPU Resource Allocation

| Process | VRAM (Q4 quant) | Notes |
|---------|-----------------|-------|
| nomic-embed-text | ~0.5 GB | Always resident for fast embedding |
| qwen2.5:14b Q4 | ~9.0 GB | First-turn diagnosis (best reasoning) |
| llama3.1:8b Q4 | ~5.0 GB | Follow-up turns, code-act generation |
| **Peak total** | **~9.5 GB** | Well within 16 GB; swap reasoning models |

Run: `OLLAMA_GPU_LAYERS=999 ollama serve`

---

## Part 4: Directory Structure

```
project/
├── preprocessing/
│   ├── ingest_excel.py             # Step 1: Excel + CoRE Stack geometry ingest (generated)
│   ├── fetch_papers.py             # Step 2: Paper acquisition
│   ├── chunk_and_embed.py          # Step 3: PDF chunking + embedding
│   ├── generate_evidence_cards.py  # Step 4: Claude API → evidence cards
│   ├── build_spatial_index.py      # Step 5: Export tehsil_list.geojson
│   └── requirements.txt            # openpyxl, pymongo, shapely, pdfplumber, anthropic, requests, python-dotenv
│
├── runtime/
│   ├── main.py
│   ├── routers/
│   │   ├── map.py                  # /api/map/* geometry endpoints
│   │   ├── mws.py                  # /api/mws/{uid}
│   │   ├── village.py              # /api/village/{id}
│   │   ├── query.py                # /api/query, /api/answer, /api/locate
│   │   └── execute.py              # /api/execute code-act endpoint
│   ├── services/
│   │   ├── resolver.py             # lat/lon → MWS uid + village id
│   │   ├── retriever.py            # Atlas vector search
│   │   ├── assembler.py            # Variable bundle assembly
│   │   ├── reasoner.py             # Ollama prompt + LLM call
│   │   ├── code_executor.py        # Sandboxed Python execution
│   │   └── session_manager.py      # MongoDB session CRUD
│   ├── static/
│   │   └── tehsil_list.geojson     # Pre-built for fast initial map load
│   └── requirements.txt            # fastapi, pymongo, ollama, uvicorn
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── MapView.tsx          # Leaflet: tehsil/MWS/village layers + choropleth
│   │   │   ├── SearchBox.tsx        # Google Places / Nominatim autocomplete
│   │   │   ├── SidePanel.tsx        # MWS info panel + query box
│   │   │   ├── InfoSection.tsx      # Default MWS info sections (5 panels)
│   │   │   ├── DiagnosisPanel.tsx   # Diagnosis + solutions display
│   │   │   ├── DynamicCharts.tsx    # Query-triggered Recharts visualizations
│   │   │   └── CodeActLayer.tsx     # Dynamic choropleth from /api/execute
│   │   └── utils/
│   │       ├── api.ts
│   │       └── chartSpec.ts         # Maps variable pairs → Recharts config
│   └── package.json
│
├── schemas/
│   ├── evidence_card_schema.json
│   ├── evidence_card_example.json
│   ├── data_dictionary_v2.json
│   ├── diagnosis_framework.json
│   ├── pathway_queries.json
│   └── reference_standards.json
│
├── data/
│   ├── papers/pdfs/
│   ├── papers/metadata/
│   └── raw_excel/
│
├── .env
└── README.md
```

---

## Part 5: Quality, Iteration, and Known Gaps

### Expert review of evidence cards

Cards start with `reviewed_by_expert: false`. A CLI review script displays each card's
signals with source citations for expert editing. Reviewed cards get `review_weight: 2.0`
in Atlas Vector Search scoring.

### Feedback loop from sessions

Sessions where diagnosis was rejected by the user are flagged. Periodic review identifies
underperforming evidence cards for re-extraction.

### Incremental updates

| Update type | Action needed |
|-------------|---------------|
| New tehsil Excel | Run `ingest_excel.py` for that tehsil only |
| New papers for a pathway | Re-run Steps 3–4 for that pathway only |
| New causal pathway in framework | Re-run Steps 3–4 for the new pathway |
| Framework schema change | Full re-run of Steps 3–4 |

### Known limitations and mitigations

| Limitation | Mitigation |
|------------|------------|
| SOGE is block-level, may mask micro-watershed stress | Require corroboration from well depth trend + delta_g |
| 20 not-available variables reduce completeness | Missing variable questions elicit these from users |
| AER assignment in evidence cards is approximate | Acceptable — papers are rarely more precise; multi-AER cards allowed |
| Code-act sandbox: complex joins may be slow | 10s timeout; limit to mws_data + village_data only; no cross-collection loops |
| Google Maps Places API cost | GCP budget cap; OSM Nominatim as free fallback |
| CoRE Stack API unavailability | Cache geometry in MongoDB; re-use if already in manifest |
