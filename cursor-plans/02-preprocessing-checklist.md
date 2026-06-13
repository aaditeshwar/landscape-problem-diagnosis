# Preprocessing Phase — Detailed Checklist

**Scope:** Phases 0–5 from master plan  
**Scripts directory:** `scripts/` (see `scripts/README.md` for layout: pipeline scripts, `verify/`, `test/`, `maintenance/`, `lib/`)  
**Metadata directory:** `metadata/`

---

## Step 0 — Dependencies

```bash
pip install -r scripts/requirements.txt

# Ollama models
ollama pull nomic-embed-text
ollama pull qwen2.5:14b
ollama pull llama3.1:8b
```

### `.env` template

```
CORE_STACK_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_MAPS_KEY=
MONGO_URI=mongodb://localhost:27017
```

---

## Step 1 — Excel Ingest (`scripts/ingest_excel.py`) ✅ EXISTS

### Command

```bash
python scripts/ingest_excel.py \
  --excel data/raw_excel/Darwha_data.xlsx \
  --state Maharashtra \
  --district Yavatmal \
  --tehsil Darwha
```

### Verification queries (mongosh)

```javascript
use diagnosis_db

// Manifest
db.ingest_manifest.findOne({_id: "Maharashtra__Yavatmal__Darwha"})

// Counts
db.mws_data.countDocuments({tehsil: "Darwha"})
db.village_data.countDocuments({tehsil: "Darwha"})

// Sample MWS — check recomputed hydrology
db.mws_data.findOne({uid: "4_100672"}, {
  uid: 1,
  aquifer_class: 1,
  soge_dev_percent: 1,
  hydrological_annual: 1,
  drainage_density_km_per_km2: 1
})

// BANAYAT excluded
db.village_data.findOne({village_id: 0})  // should be null

// Geometries
db.mws_boundaries.countDocuments({tehsil: "Darwha"})
db.tehsil_boundaries.findOne({tehsil: "Darwha"}, {mws_count: 1})
```

### Transform rules to spot-check

| Rule | Field | Expected |
|------|-------|----------|
| Delta-G recomputed | `hydrological_annual.{year}.delta_g_mm` | P − ET − Runoff, not raw DeltaG |
| Cumulative G | `hydrological_annual.{year}.cumulative_g_mm` | Rolling sum from 2017 |
| Drainage correction | `drainage_density_km_per_km2` | raw / 100 |
| Time series shape | any `*_annual` nested object | keys are integers 2017..2024 |
| Aquifer mapping | `aquifer_class` | ACWADAM enum (e.g. `volcanic`) |

---

## Step 2 — Paper Fetch (`scripts/fetch_papers.py`) — TO BUILD

### Input

- `metadata/pathway_queries.json` → `pathways` object (pathway_key → query list)

### Output

```
data/papers/
├── pdfs/{paper_id}.pdf
└── metadata/{paper_id}.json
```

### Metadata schema (per paper)

```json
{
  "paper_id": "sha256_or_doi_slug",
  "title": "...",
  "authors": ["..."],
  "year": 2023,
  "abstract": "...",
  "doi": "...",
  "pathway_tags": ["agriculture__water_scarcity__groundwater_stress"],
  "source_api": "semantic_scholar|openalex",
  "pdf_path": "data/papers/pdfs/{paper_id}.pdf",
  "fetched_at": "ISO8601"
}
```

### APIs

| API | URL | Notes |
|-----|-----|-------|
| Semantic Scholar | `GET https://api.semanticscholar.org/graph/v1/paper/search` | Rate limit: respect backoff |
| OpenAlex | `GET https://api.openalex.org/works?search=...&filter=open_access.is_oa:true` | OA filter |
| Unpaywall | `GET https://api.unpaywall.org/v2/{doi}?email=...` | PDF URL discovery |

### Acceptance

- [ ] 8–12 unique papers per pathway key
- [ ] Deduplication by DOI
- [ ] Resumable (skip already-downloaded paper_ids)
- [ ] Log failures without aborting entire run

---

## Step 3 — Chunk & Embed (`scripts/chunk_and_embed.py`) — TO BUILD

### Processing pipeline

1. Iterate `data/papers/metadata/*.json`
2. Extract PDF text (pdfplumber)
3. Chunk abstract separately (`chunk_type: "abstract"`, `retrieval_weight: 2.0`)
4. Chunk body: 512 tokens, 128 overlap
5. Inherit `pathway_tags` from paper metadata; infer `aer_tags`, `aquifer_tags`, `rainfall_regime` from paper text keywords or Claude batch tagger (optional)
6. Embed each chunk: Ollama `nomic-embed-text`
7. Upsert to `paper_chunks`

### Vector index (Atlas CLI)

```javascript
{
  "name": "paper_chunk_vector_index",
  "type": "vectorSearch",
  "definition": {
    "fields": [{
      "type": "vector",
      "path": "embedding",
      "numDimensions": 768,
      "similarity": "cosine"
    }]
  }
}
```

### Acceptance

- [ ] Test query returns ≥3 relevant chunks for "well depth decline Deccan Plateau"
- [ ] Abstract chunks score higher with `retrieval_weight: 2.0`

---

## Step 4 — Evidence Cards (`scripts/generate_evidence_cards.py`) — TO BUILD

### Inputs

| File | Use |
|------|-----|
| `metadata/evidence_card_schema.json` | Validate output |
| `metadata/evidence_card_example.json` | Few-shot prompt example |
| `metadata/reference_standards.json` | AER/aquifer/rainfall enums + AER-from-text examples |
| `metadata/diagnosis_framework.json` | Pathway keys, diagnostic_variables, solutions |
| Top paper chunks per pathway | Claude context |

### Generation pattern

- One card per pathway × (aquifer_type, AER_cluster) ≈ 100 cards
- `card_id` format: `{system}__{stress}__{pathway}__{NNN}`
- Validate each card with `jsonschema` before insert
- Embed `overall_reasoning_note` + signal explanations → store in `evidence_cards.embedding`

### AER assignment rule (from plan.md)

> Map study location to AER-1..AER-20 from paper text (state, rainfall, aquifer, physiography). Approximate assignment acceptable. Multi-AER papers list all applicable codes.

### Vector index

Pre-filter fields: `pathway_tags`, `aer_tags`, `aquifer_tags`

### Acceptance

- [ ] All generated cards pass JSON Schema validation
- [ ] Example card structure matches `evidence_card_example.json` pattern
- [ ] Vector search with aquifer pre-filter returns context-appropriate cards

---

## Step 5 — Spatial Index (`scripts/build_spatial_index.py`) — TO BUILD

### Command (planned)

```bash
python scripts/build_spatial_index.py
```

### Output

`runtime/static/tehsil_list.geojson` — FeatureCollection of tehsil polygons with properties:

```json
{
  "type": "Feature",
  "properties": {
    "state": "Maharashtra",
    "district": "Yavatmal",
    "tehsil": "Darwha",
    "mws_count": 99
  },
  "geometry": { "type": "Polygon", "coordinates": [...] }
}
```

### Acceptance

- [ ] Valid GeoJSON parseable by Leaflet
- [ ] Darwha feature present with correct `mws_count`

---

## MongoDB Collections After Preprocessing

| Collection | Populated by |
|------------|--------------|
| `mws_data` | Step 1 |
| `village_data` | Step 1 |
| `mws_boundaries` | Step 1 |
| `village_boundaries` | Step 1 |
| `tehsil_boundaries` | Step 1 |
| `ingest_manifest` | Step 1 |
| `diagnosis_framework` | Step 0 |
| `data_dictionary` | Step 0 |
| `paper_chunks` | Step 3 |
| `evidence_cards` | Step 4 |
