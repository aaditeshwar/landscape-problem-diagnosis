# Runtime Phase — Detailed Checklist

**Scope:** Phases 6–7 from master plan  
**Backend:** FastAPI on port 8000  
**Frontend:** React 18 + Leaflet + Recharts

---

## Backend API Endpoints

### Map & Data (no LLM required — build after Phase 1)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/map/tehsils` | Serve `tehsil_list.geojson` or query `tehsil_boundaries` |
| GET | `/api/map/mws?state=&district=&tehsil=` | MWS boundary FeatureCollection |
| GET | `/api/map/villages?state=&district=&tehsil=` | Village boundary FeatureCollection |
| GET | `/api/mws/{uid}` | Full MWS document for info panel |
| GET | `/api/village/{id}` | Village social/economic data |
| POST | `/api/locate` | `{lat, lon}` → MWS uid + village_id via `$geoIntersects` |

### Diagnosis (requires Phases 3–4)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/query` | First-turn diagnosis |
| POST | `/api/answer` | Follow-up with user-provided missing variable |

#### POST `/api/query` request

```json
{
  "uid": "4_100672",
  "problem_description": "Our wells are drying up and cotton yields are falling",
  "session_id": null
}
```

#### POST `/api/query` response (expected fields)

```json
{
  "session_id": "session_abc123",
  "confirmed_pathways": [
    {"pathway_id": "groundwater_stress", "confidence": "high", "reasoning": "..."}
  ],
  "uncertain_pathways": [
    {
      "pathway_id": "monocropping",
      "confidence": "medium",
      "missing_variable_questions": [{"variable": "borewell_density", "question": "..."}]
    }
  ],
  "solutions": ["MGNREGA-funded SWC works...", "..."],
  "panel_updates": ["cropping_intensity + annual_delta_g_mm dual_axis"],
  "follow_up_question": "Roughly how many borewells..."
}
```

### Code-Act (requires Phase 1 data + Llama 3.1 8B)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/execute` | Natural language → choropleth GeoJSON |

#### Sandbox constraints

- Timeout: 10 seconds
- No network, no file I/O
- Allowed imports: pymongo, math, statistics, colorsys
- Function signature: `run_query(mws_col, village_col, mws_boundaries, village_boundaries) -> list[dict]`
- Return items: `{id, entity_type, color, label, value}`

---

## Service Layer Responsibilities

### `resolver.py`

```python
def locate_mws(db, lon: float, lat: float) -> dict:
    # $geoIntersects on mws_boundaries
    # Return uid, tehsil, district, state
```

### `retriever.py`

```python
def retrieve_evidence_cards(db, ollama, problem_text: str, aquifer_class: str, limit=5):
    # 1. Embed problem_text with nomic-embed-text
    # 2. $vectorSearch on evidence_cards with aquifer pre-filter
    # 3. For each card: fetch top-3 paper_chunks for citations
```

### `assembler.py`

```python
def assemble_variable_bundle(mws_doc, framework, retrieved_pathways):
    # For each pathway's diagnostic_variables:
    #   resolve from mws_doc → present | missing
    #   attach missing_variable_questions from evidence card
```

### `reasoner.py`

| Turn | Model | Role |
|------|-------|------|
| First | `qwen2.5:14b` | Full diagnosis prompt with location, variables, candidate pathways |
| Follow-up | `llama3.1:8b` | Narrow re-reason with injected user answer |

Prompt structure per `plan.md` §Diagnosis Query Flow Step D.

Output: **valid JSON only** — parse with strict schema validation.

### `session_manager.py`

- Create/read/update `sessions` collection
- Append turns with `retrieved_cards`, `llm_response_json`, `panel_updates_triggered`
- Track `injected_variable` on follow-up turns

### `code_executor.py`

- Generate Python via Llama 3.1 8B with field summary from data dictionary
- Execute in subprocess with restricted globals
- Join results with geometries → GeoJSON FeatureCollection

---

## Frontend Components

### Map layers (bottom → top)

1. OSM tiles
2. Tehsil polygons (amber, from `/api/map/tehsils`)
3. MWS polygons (on tehsil select)
4. Village polygons (toggleable)
5. Code-act choropleth (dynamic, replaces previous)

### Default MWS Info Panel (5 sections)

From `metadata/reference_standards.json → visualization_spec.default_mws_panel`:

| Section | Key widgets |
|---------|-------------|
| Identity | UID, area, terrain cluster, aquifer, AER, river/canal |
| Water | SOGE gauge, well depth trend (inverted Y), delta_g diverging bar, SWB multi-line |
| Land Use | LULC stacked area, cropping intensity, degradation/afforestation bars |
| Climate & Drought | Precipitation bar, drought severity stacked bar, dry spell weeks |
| Livelihoods | NREGA stacked bar, facility distances spider chart |

Data source: `GET /api/mws/{uid}`  
Chart config: `frontend/src/utils/chartSpec.ts` driven by visualization spec.

### Query-triggered panel updates

When diagnosis returns `panel_updates[]`, activate chart pairs from:
`reference_standards.json → visualization_spec.query_triggered_panel_updates`

Example: `cropping_intensity + annual_delta_g_mm` → dual-axis line chart.

### Search box

1. Google Places Autocomplete → lat/lon
2. Fly map to location
3. Highlight tehsil if ingested
4. `POST /api/locate` → select MWS
5. Fallback: OSM Nominatim

---

## GPU Resource Plan (A4500 16 GB)

| Model | VRAM | Usage |
|-------|------|-------|
| nomic-embed-text | ~0.5 GB | Always resident |
| qwen2.5:14b Q4 | ~9.0 GB | First-turn diagnosis |
| llama3.1:8b Q4 | ~5.0 GB | Follow-ups + code-act |

Peak ~9.5 GB — swap reasoning models between first turn and follow-up if needed.

```bash
OLLAMA_GPU_LAYERS=999 ollama serve
```

---

## Frontend Scaffold Commands (planned)

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install leaflet react-leaflet recharts tailwindcss
```

Proxy API calls to `http://localhost:8000` in Vite config.

---

## Integration Test Scenarios

| # | Scenario | Expected |
|---|----------|----------|
| T1 | Load map → Darwha tehsil visible | Amber polygon renders |
| T2 | Click tehsil → MWS layer loads | ~99 MWS polygons |
| T3 | Click MWS 4_100672 | 5-section info panel populates |
| T4 | Query "wells drying up" | groundwater_stress confirmed, SOGE + well depth cited |
| T5 | Answer borewell follow-up | Confidence increases; pathway ranking updates |
| T6 | Code-act "villages >10km from APMC" | Village choropleth with red-green scale |
| T7 | panel_updates triggered | Dual-axis chart appears in info panel |

---

## Session Document Shape

Stored in `sessions` collection — see `plan.md` §Session Document for full schema.

Key fields: `mws_uid`, `turns[]`, `final_diagnosis.confirmed_pathways`, `final_diagnosis.solutions`.
