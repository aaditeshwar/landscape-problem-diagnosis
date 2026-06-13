# Agro-Ecological Problem Diagnosis System — Artifact Reference

This directory contains all design and implementation artifacts for the MWS-level
problem diagnosis system. Each artifact is described below with its purpose and
relationship to the rest of the pipeline.

---

## Implementation Code

### `ingest_excel.py`
**What it is:** Fully runnable Python script (923 lines) for Step 1 of the preprocessing
pipeline. Reads a tehsil-level Excel workbook and writes all MWS and village documents
into MongoDB (`diagnosis_db`), then fetches geometries from the CoRE Stack API.

**Why it exists:** The Excel format is complex (32 sheets, wide time-series columns, JSON
strings embedded in cells) and requires careful transformation before it is useful for
querying. This script encodes all transformation rules precisely:
- Recomputes `delta_g_mm = P − ET − Runoff` and `cumulative_g_mm` (rolling sum from 2017)
  from raw annual and seasonal hydrological columns, ignoring the buggy source `G` and
  `DeltaG` columns entirely.
- Reshapes all wide time-series columns (`variable_<YYYY-YYYY>`) into nested year-keyed
  objects (`{2017: value, 2018: value, ...}`).
- Maps CoRE Stack aquifer class labels to ACWADAM 6-class taxonomy.
- Applies the `/100` correction to drainage density.
- Excludes the placeholder BANAYAT (JUNE) village (village_id = 0).
- Fetches MWS and village GeoJSON from `https://geoserver.core-stack.org/api/v1/`,
  builds a dissolved tehsil boundary polygon via Shapely, and stores all geometries
  with 2dsphere indexes in MongoDB.
- Maintains an `ingest_manifest` collection tracking status per tehsil; is idempotent
  and resumable.

**Usage:**
```bash
python preprocessing/ingest_excel.py \
  --excel data/raw_excel/Darwha_data.xlsx \
  --state Maharashtra --district Yavatmal --tehsil Darwha

# Options: --skip-geometries, --force
```

---

## Schemas and Standards

### `data_dictionary_v2.json`
**What it is:** Complete variable-level data dictionary. 111 variables total:
91 available (with source sheet/column), 20 not-available (recommended additions).

**Why it exists:** Single source of truth for variable names, units, and availability.
Distinguishes `static` (one value per MWS) from `time_series` (nested by agricultural
year integer) variables. Time-series convention: label = start year of the Jul–Jun
cycle (e.g. `2017` = 2017-18). Used by `ingest_excel.py` for column mapping, by
`assembler.py` for variable bundle construction, and by the frontend for chart rendering.

### `evidence_card_schema.json`
**What it is:** JSON Schema (Draft-07) for evidence cards — the unit of knowledge
grounding each causal pathway in research literature.

**Why it exists:** Each card encodes diagnostic signals (quantitative expressions or
qualitative conditions), threshold confidence levels, context (NBSS-LUP AER code,
ACWADAM aquifer type, rainfall regime), confounders, and questions to ask users when
variables are missing. The schema enforces consistency so that auto-extracted cards
(via Claude API) and human-reviewed cards are structurally identical.

### `evidence_card_example.json`
**What it is:** A fully worked example card for `groundwater_stress` in a hard-rock
semi-arid context (AER-6, volcanic aquifer).

**Why it exists:** Template for the Claude API extraction prompt and for domain expert
review. Shows all schema fields in use including a quantitative signal (SOGE > 70%),
a trend signal (well depth deepening), an amplifying signal (low NREGA SWC investment),
confounders (drought vs extraction), and two missing-variable questions.

### `reference_standards.json`
**What it is:** Canonical reference for all three classification systems plus the
visualization specification.

**Contents:**
- **NBSS-LUP AERs (AER-1 to AER-20):** name, states, rainfall range, LGP, dominant
  aquifer — used for evidence card context tagging and AER assignment from paper text.
- **ACWADAM aquifer types (6 classes):** description, dominant AERs, groundwater
  behavior — used in evidence card schema, data dictionary, and aquifer mapping in ingest.
- **Rainfall regime bands (5 classes):** mm ranges and typical AERs.
- **Visualization spec:** per-variable chart types, variable-pair charts (dual-axis,
  scatter, stacked area water balance), three-variable small-multiples layouts, default
  MWS info panel definition, and query-triggered panel update rules.

### `diagnosis_framework.json`
**What it is:** The full hierarchy: 4 production systems → 10 observed stresses →
33 causal pathways → 152 variable-to-cause diagnostic mappings → 95 solution entries.

**Why it exists:** Central knowledge structure of the system. The LLM reasoning prompt
is built around this framework. Evidence cards are organized by pathway. Solutions are
delivered to users from here. Updated as new stresses or pathways are identified.

### `pathway_queries.json`
**What it is:** 8–13 search queries per causal pathway (33 pathways) for Semantic Scholar
and OpenAlex paper acquisition.

**Why it exists:** Drives the paper corpus acquisition step. Queries are stratified to
cover all 6 ACWADAM aquifer types, all 20 NBSS-LUP AERs (via geographic terms), and all
5 rainfall regime bands — ensuring evidence cards are grounded in diverse Indian contexts,
not only the Deccan Plateau where Darwha sits.

---

## Implementation Plan

### `plan.md`
**What it is:** Full technical specification (712 lines) of the preprocessing pipeline
and runtime architecture.

**Key sections:**
- **CoRE Stack API:** base URL `https://geoserver.core-stack.org/api/v1`, endpoint table,
  authentication (`X-API-Key` header)
- **Ingest script:** all transformation rules, manifest design, command-line usage
- **AER assignment:** done from paper text/climate description, not geometries — the
  `reference_standards.json` table provides sufficient detail for approximate matching
- **Paper corpus:** query stratification across all Indian agro-ecological contexts
- **Evidence card generation:** Claude API prompt including AER-from-text instruction
  with worked examples
- **Runtime query flow:** location resolution → vector retrieval → variable assembly →
  LLM reasoning → interactive follow-up → panel updates
- **Code-act queries:** supports both MWS-level and village-level natural language map
  queries (water balance, stress patterns, facility access, NREGA coverage, etc.);
  sandboxed Python execution; choropleth rendering in Leaflet
- **Frontend:** India map with ingested tehsils, MWS/village polygon layers, default
  info panel, query box, dynamic chart updates, code-act choropleth layer

---

## Artifact Relationships

```
reference_standards.json
  └─ AER codes, aquifer types, rainfall bands, visualization spec
       ├─ data_dictionary_v2.json (variable context)
       ├─ evidence_card_schema.json (context fields enum values)
       ├─ ingest_excel.py (aquifer class mapping)
       └─ plan.md (AER-from-text instruction, frontend chart spec)

diagnosis_framework.json
  └─ production systems → stresses → causal pathways → solutions
       ├─ pathway_queries.json (one query set per pathway key)
       ├─ evidence_card_schema.json (pathway reference)
       └─ plan.md (LLM reasoning prompt structure)

pathway_queries.json
  └─ drives fetch_papers.py → paper_chunks in MongoDB
       └─ drives generate_evidence_cards.py → evidence_cards in MongoDB
            └─ used by runtime retriever → LLM reasoner → frontend panel

data_dictionary_v2.json
  └─ defines all variables + source columns
       ├─ ingest_excel.py (column mapping)
       ├─ assembler.py (variable bundle construction)
       └─ frontend chartSpec.ts (chart rendering)

ingest_excel.py
  └─ reads raw Excel → writes mws_data, village_data to MongoDB
       └─ calls CoRE Stack API → writes mws_boundaries, village_boundaries,
          tehsil_boundaries to MongoDB
```

---

## Next Steps

1. `pip install -r preprocessing/requirements.txt`
2. Configure `.env` with `CORE_STACK_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_MAPS_KEY`, `MONGO_URI`
3. Run `python preprocessing/ingest_excel.py --excel data/raw_excel/Darwha_data.xlsx --state Maharashtra --district Yavatmal --tehsil Darwha`
4. Run `python preprocessing/fetch_papers.py` (~4 hours, ~300 papers)
5. Run `python preprocessing/chunk_and_embed.py` (~2 hours, GPU)
6. Run `python preprocessing/generate_evidence_cards.py` (~$3 Claude API)
7. Scaffold React frontend; connect to FastAPI; render tehsil map
8. End-to-end test: select Darwha → click MWS 4_100672 → query groundwater → verify diagnosis
