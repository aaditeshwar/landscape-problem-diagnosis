# Case study triaging app + global variable dashboard

> **Status:** Implemented (v1) — `/triaging`, `/dashboard`  
> **Created:** 2026-06-21  
> **Prerequisite:** Plan 17 (production-system gating), 8 built pathways with evidence cards  
> **Routes:** `/triaging`, `/dashboard`  
> **Related:** [16-revise-cards-review-app.md](./16-revise-cards-review-app.md), [12-aer-retrieval-neighbors.md](./12-aer-retrieval-neighbors.md), `scripts/eval/run_case_study_diagnoses.py`

---

## Stakeholder decisions (approved)

| Topic | Decision |
|-------|----------|
| Card resolution | **Same as server-only “Run diagnosis”** — `load_mws_scoped_evidence_cards()` (aquifer + AER filter, `_best_card_per_pathway`); **not** cluster-raster lookup |
| Matrix rows (actual) | Pathways valid for that `(production_system, observed_stress)` in the framework, **including `__stress_only__`** |
| Matrix columns (predicted) | **Only the 8 built pathways** + **`None of these`** |
| Matrix granularity | One entry per **case-study instance** (`case_study_id`) |
| Matrix styling | **Colour-code** confirmed vs unconfirmed instances in each cell |
| Variable table rows | Static vars + **each list access** (`var[-1]`, `mean(var)`, etc.) as separate rows; skip for-loop / comprehension bodies |
| Dashboard population | **All MWS with available data** in Mongo (global CDF), not case-study subset only |
| Case-study overlay | Mark case-study instance values on global CDFs for context |
| MWS variable source | Prefer `data/raw_jsons/{uid}.json`; **auto-create from Mongo** if missing (reuse export script internals) |
| Draft persistence | **Yes** — save drafts before promoting to revise-cards |
| Case-study file selector | Dropdown of `metadata/case_study_locations*.json` |
| Parallel work | Dashboard precompute may run **in parallel** with triaging app backend/UI |

---

## Problem

Batch case-study eval scripts and deleted markdown reports are poor iteration surfaces for tuning signal expressions and confirmation policy. We need an interactive triaging workspace (like `/revise-cards`) plus a global variable dashboard so reviewers can see where each case study sits in the full MWS distribution.

---

## Architecture overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  /triaging                              /dashboard                    │
│  TriagingPage.tsx                       DashboardPage.tsx             │
│  triaging/*                             dashboard/*                   │
└────────────┬────────────────────────────────────┬────────────────────┘
             │                                    │
             ▼                                    ▼
┌────────────────────────────┐      ┌────────────────────────────────┐
│  runtime/routers/triage.py │      │  data/triage_dashboard/          │
│  runtime/services/triage_* │      │    {ps}__{stress}.json           │
│  runtime/services/mws_export.py     │  (global CDFs + case markers)  │
└────────────┬───────────────┘      └────────────────────────────────┘
             │
   ┌─────────┼──────────┬─────────────────┬──────────────────────┐
   ▼         ▼          ▼                 ▼                      ▼
case_study  mws_data   load_mws_scoped   signal_evaluator +    raw_jsons/
_locations  (Mongo)    _evidence_cards   confirmation_policy   ensure_export
*.json
```

| Layer | Path |
|-------|------|
| Routes | `frontend/src/App.tsx` → `/triaging`, `/dashboard` |
| Triaging UI | `frontend/src/routes/TriagingPage.tsx`, `frontend/src/triaging/` |
| Dashboard UI | `frontend/src/routes/DashboardPage.tsx`, `frontend/src/dashboard/` |
| API client | `frontend/src/api/triage.ts` |
| Backend router | `runtime/routers/triage.py` |
| Services | `runtime/services/triage_index.py`, `triage_eval.py`, `triage_card_map.py`, `mws_export.py`, `expression_variable_access.py` |
| Precompute | `scripts/triage/build_variable_dashboard.py` |
| Drafts | `metadata/triage_drafts/{card_id}.json` (gitignored) |
| Deep link | `DiagnosisApp.tsx` — `/?mws=…&state=…&district=…&tehsil=…` |

---

## 1. Card resolution (server-only diagnosis path)

**Critical:** Do **not** use `query_cluster_at_point()` / cluster raster for card selection. That path is used by the signal editor map, not by “Run diagnosis” with LLM off.

Server-only diagnosis (`want_llm_opinion: false`) in `POST /api/query`:

1. `load_mws_scoped_evidence_cards(db, mws_doc)` (`runtime/services/retriever.py`)
2. Aquifer tags from MWS lithology (`card_aquifer_tags_for_mws`)
3. AER neighbour set from `AER_RETRIEVAL_NEIGHBORS` (`_aer_tags_for_retrieval`)
4. Mongo filter: `{ aquifer_tags, aer_tags: { $in: … } }` → candidate pool
5. `_best_card_per_pathway(candidates, mws_aer)` — one card per `causal_pathway`; prefer direct AER match, tie-break `card_id`
6. Context cluster suffix is **embedded in `card_id`** (e.g. `…__groundwater_stress__006`), not sampled separately

**Triage implementation (`triage_card_map.py`):**

```python
def resolve_cards_for_mws(db, mws_doc) -> dict[str, dict]:
    """pathway_id -> evidence card (same as server-only initial turn)."""
    result = load_mws_scoped_evidence_cards(db, mws_doc)
    return {card["causal_pathway"]: card for card in result.cards}
```

For an instance with `expected_pathway = "drought"`, the column’s card is `cards.get("drought")`. If the pathway is built but no card was retrieved (AER/aquifer gap), show **“not retrieved”** — same failure mode as live diagnosis.

**Production-system gating:** Apply `evaluate_production_system_gates` before eval (Plan 17). Skipped systems surface as a section banner; NTFP instances may not receive forest cards.

---

## 2. Data model

### 2.1 Case-study catalog

**Source files:** glob `metadata/case_study_locations*.json` (dropdown in UI).

Flatten to **instances** (reuse / extend `scripts/eval/case_study_index.py`):

```typescript
type CaseStudyInstance = {
  case_study_id: number
  mws_id: string
  lat: number
  lng: number
  production_system: string       // e.g. "Agriculture"
  observed_stress: string         // e.g. "water_scarcity"
  expected_pathway: string | null // null when stress_only
  stress_only: boolean
  state?: string
  district?: string
  tehsil?: string
}
```

One MWS may appear in multiple instances. UI columns and matrix entries are keyed by **instance**, not MWS alone.

### 2.2 Section grouping

Each section = `(production_system, observed_stress)`.

Framework metadata from `metadata/diagnosis_framework.json`:

| Axis | Source | Notes |
|------|--------|-------|
| **Actual (rows)** | `causal_pathways` under that stress + `__stress_only__` | Only pathways defined for this PS/stress |
| **Predicted (cols)** | `BUILT_PATHWAY_IDS` (8 today) | `drought`, `groundwater_stress`, `rainfed_risk`, `irrigation_challenges`, `forest_degradation`, `encroachment`, `multi_sector_vulnerability`, `small_landholding` |
| **Extra col** | `None of these` | Instances where no built pathway is **confirmed** |

Built pathway set is shared constant (`scripts/eval/case_study_index.py` → move to `runtime/services/built_pathways.py` or `triage_index.py`).

### 2.3 MWS variable exports

**Policy:** JSON-first, Mongo fallback.

| Step | Action |
|------|--------|
| 1 | Check `data/raw_jsons/{mws_id}.json` |
| 2 | If missing, call `ensure_mws_export(db, mws_id)` |
| 3 | `ensure_mws_export` loads `mws_data`, `enrich_mws_doc`, runs same logic as `scripts/export_case_study_mws_variables.py::export_mws_variables`, writes JSON |

**Refactor:** Extract `export_mws_variables` + `EXPORT_VARIABLES` into `runtime/services/mws_export.py` so both the CLI script and triage API import one implementation. Script becomes a thin wrapper.

Eval context: `merge_export_variables(export)` + `build_eval_context_from_export` (existing `signal_evaluator`).

### 2.4 Play evaluation (local, no LLM)

Per instance column, using the **expected-pathway card** from server-only resolution (with UI-edited signals/policy):

1. `ensure_mws_export` → load variables
2. `evaluate_bundle_signals` on a single-pathway mini-bundle **or** `evaluate_signal_condition` per signal
3. `confirmation_policy` → `confirmed` | `uncertain` | `not_confirmed`
4. **Predicted column assignment:**
   - If exactly one built pathway is `confirmed` → that column
   - If multiple confirmed (edge case) → highest primary-signal count / policy rank (document in `triage_eval.py`)
   - If none confirmed → **`None of these`**
   - `uncertain` on expected pathway still places in that pathway column but styled **unconfirmed**

**Play scope:** Entire section; POST carries current in-memory edits for all instance columns.

---

## 3. Confusion matrix

### 3.1 Layout

```
                    │ drought │ gw_stress │ … │ small_land │ None of these │
────────────────────┼─────────┼───────────┼───┼────────────┼───────────────┤
drought             │  inst…  │           │   │            │               │
groundwater_stress  │         │  inst…    │   │            │               │
…                   │         │           │   │            │               │
__stress_only__     │         │           │   │            │  inst…        │
```

- **Row** = `expected_pathway` or `__stress_only__` (display label: “Stress only”)
- **Column** = predicted built pathway, or `None of these`
- **Cell** = list of instance chips after Play

### 3.2 Colour coding

| Style | Condition |
|-------|-----------|
| **Confirmed** (e.g. green) | `expected_pathway` matches predicted column **and** `predicted_status == confirmed` |
| **Unconfirmed** (e.g. amber/red) | `uncertain`, wrong pathway, or in `None of these` |

Stress-only rows: confirmed only if **no** pathway confirmed (correct negative) — treat as confirmed when prediction is `None of these` and status is intentionally N/A; otherwise unconfirmed if any pathway confirmed.

Each chip links to instance column scroll + `/?mws=…` deep link.

---

## 4. Variable table (top-right panel)

### 4.1 Row identification

Do **not** use bare `expression_load_names()` only — it collapses `cropping_intensity[-1]` to `cropping_intensity`.

New helper `expression_variable_accesses(expression) -> list[VariableAccess]` in `runtime/services/expression_variable_access.py`:

| Expression fragment | Display key | Resolved value |
|--------------------|-------------|----------------|
| `borewell_density` | `borewell_density` | scalar from export |
| `cropping_intensity[-1]` | `cropping_intensity[-1]` | last element of series |
| `mean(dry_spell_weeks)` | `mean(dry_spell_weeks)` | compute mean over series |
| `annual_precipitation_mm.get('2023')` | `annual_precipitation_mm['2023']` | dict lookup |

**AST rules:**

- Walk `ast.parse(expression, mode="eval")`
- Emit one access per **Load** of a known variable name
- For **Subscript** on a variable: include base + index literal in key (`var[-1]`, `var['2023']`)
- For **Call** where func is `mean|min|max|sum|len|sorted` and first arg is a variable name: key = `f"{func}({name})"`
- **Skip** names bound inside `ast.comprehension` (for-loops / list comps) — same bound-name logic as `missing_context_keys`
- Union accesses across all active signals for the column’s card

### 4.2 Table layout

| Row | Inst A | Inst B | … |
|-----|--------|--------|---|
| MWS | link | link | |
| Card | `/revise-cards?card_id=…` | … | |
| `var` / `mean(var)` / `var[-1]` | formatted value | … | |

Compact formatting: truncate long dicts; series show resolved scalar for that access pattern.

---

## 5. Triaging UI (`/triaging`)

### 5.1 Layout

```
┌─ Header: [case_study_locations*.json ▼]  links: Dashboard | Diagnosis ─┐
├─ Section: Agriculture · water_scarcity  [▶ Play] [Save draft] [→ Dashboard] ─┤
│  ┌─ Top ─────────────────────────────────────────────────────────────┐ │
│  │ Confusion matrix (left)     │  MWS / card / variable table (right)   │ │
│  └─────────────────────────────┴────────────────────────────────────────┘ │
│  ┌─ Bottom: signal grid (full width) ───────────────────────────────────┐ │
│  │ rows: sig_01…sig_0N, confirmation_policy JSON                         │ │
│  │ cols: one per instance (case_study_id)                                │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─ repeat per (production_system, observed_stress) ───────────────────────────┘
```

### 5.2 Bottom panel — editable signal grid

Per instance column:

| Row | Contents |
|-----|----------|
| `sig_01` … `sig_0N` | expression textarea · direction select · readonly result (after Play) |
| **Confirmation policy** | JSON textarea, initialized from mapped card |

**Edit sharing:** Instances with the same `card_id` share one edit buffer (fingerprint). Changing one column updates all columns mapped to that card.

### 5.3 Draft persistence

**Path:** `metadata/triage_drafts/{card_id}.json` (add to `.gitignore`)

```json
{
  "schema_version": 1,
  "card_id": "agriculture__water_scarcity__drought__002",
  "updated_at": "2026-06-21T…",
  "diagnostic_signals": [ … ],
  "confirmation_policy": { … },
  "source": "triaging",
  "section": { "production_system": "Agriculture", "observed_stress": "water_scarcity" }
}
```

| Action | Behaviour |
|--------|-----------|
| **Save draft** | POST `/api/triage/drafts/{card_id}` — persists current edits for that card fingerprint |
| **Load** | On section mount, overlay drafts on top of Mongo/raw card |
| **Copy to revise-cards** | Opens `/revise-cards?card_id=…`; revise-cards Phase 2 may read draft file (optional hook) |

Draft save is **required in v1** (not deferred).

### 5.4 Section dashboard link

```text
/dashboard?production_system=Agriculture&observed_stress=water_scarcity#agriculture__water_scarcity
```

---

## 6. Global variable dashboard (`/dashboard`)

### 6.1 Purpose

Empirical **CDFs across all MWS with assembler data in Mongo**, grouped by `(production_system, observed_stress)`. Case-study instances appear as **markers** on the same charts so reviewers see where a case study sits globally.

### 6.2 MWS universe

```python
# build_variable_dashboard.py
for doc in db.mws_data.find({}, {"uid": 1}):
    export = ensure_mws_export(db, doc["uid"])  # creates raw_json if needed
    if export has minimum variable coverage: include in global pool
```

Not limited to case-study UIDs (~32 today). Expect hundreds–thousands depending on ingest scope.

### 6.3 Variables per section

Default set = union of `expression_variable_accesses` across all **built** cards that belong to pathways under that section’s stress (for the relevant production system). Plus `--add-variable` CLI flag for exploration.

### 6.4 Precomputed artifact

`data/triage_dashboard/{snake_ps}__{stress}.json`:

```json
{
  "production_system": "Agriculture",
  "observed_stress": "water_scarcity",
  "generated_at": "2026-06-21T12:00:00Z",
  "mws_count": 842,
  "case_study_instances": [
    { "case_study_id": 34, "mws_id": "4_102533", "expected_pathway": "drought" }
  ],
  "variables": {
    "dry_spell_weeks[-1]": {
      "access": "dry_spell_weeks[-1]",
      "scalar_values": [0, 1, 3, 4, …],
      "cdf": [[0, 0.0], [1, 0.05], …],
      "case_study_values": [
        { "case_study_id": 34, "mws_id": "4_102533", "value": 6, "percentile": 0.72 }
      ]
    }
  }
}
```

Percentile computed from global `scalar_values` so case-study position is explicit.

### 6.5 Build script

```powershell
.\.venv\Scripts\python.exe scripts/triage/build_variable_dashboard.py
.\.venv\Scripts\python.exe scripts/triage/build_variable_dashboard.py --add-variable borewell_density --section agriculture/water_scarcity
```

**Parallel track:** This script + sample JSON can ship while triaging API/UI is in progress.

### 6.6 Dashboard page

- Load manifest (`GET /api/triage/dashboard/manifest`) or static index file
- One anchored block per section (`id="{ps}__{stress}"`)
- Line chart: CDF curve + case-study tick marks (colour by confirmed/unconfirmed if eval snapshot available; else neutral)
- URL query scrolls to section on mount

---

## 7. Backend API

`runtime/routers/triage.py` — prefix `/api/triage`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/catalogs` | List `metadata/case_study_locations*.json` |
| GET | `/catalog/{filename}` | Sections + instances + admin enrichment |
| GET | `/card-map` | `?mws_id` → `resolve_cards_for_mws` (full pathway map) |
| POST | `/evaluate-section` | Section + instance edits → signal results + matrix cells |
| GET | `/drafts/{card_id}` | Load draft if exists |
| POST | `/drafts/{card_id}` | Save draft |
| GET | `/dashboard/manifest` | List precomputed section keys |
| GET | `/dashboard/{section_key}` | CDF JSON |

**Evaluate-section response (sketch):**

```json
{
  "matrix": {
    "cells": [
      {
        "actual_pathway": "drought",
        "predicted_pathway": "drought",
        "instances": [
          {
            "case_study_id": 34,
            "mws_id": "4_102533",
            "match": true,
            "predicted_status": "confirmed"
          }
        ]
      }
    ]
  },
  "instances": [
    {
      "case_study_id": 34,
      "card_id": "agriculture__water_scarcity__drought__002",
      "signals": [ { "signal_id": "sig_01", "result": true, "value": "…" } ],
      "predicted_pathway": "drought",
      "predicted_status": "confirmed"
    }
  ]
}
```

---

## 8. Deep links

### 8.1 Diagnosis app

```text
/?mws=4_102533&state=Maharashtra&district=Yavatmal&tehsil=Ghatanji
```

On mount: resolve tehsil → select tehsil → fetch MWS → fly map → populate panel. **Do not** auto-run diagnosis.

### 8.2 Revise cards (existing)

```text
/revise-cards?card_id=agriculture__water_scarcity__drought__002
```

### 8.3 Dashboard

```text
/dashboard?production_system=Agriculture&observed_stress=water_scarcity#agriculture__water_scarcity
```

---

## 9. Implementation phases

### Phase A — Foundation (parallel tracks)

**Track A1 — Triage backend**

1. `runtime/services/mws_export.py` — extract from export script; `ensure_mws_export`
2. `runtime/services/expression_variable_access.py`
3. `triage_index.py` — catalog glob, section grouping, built pathways
4. `triage_card_map.py` — `load_mws_scoped_evidence_cards` wrapper
5. `triage_eval.py` — section Play + matrix assignment
6. `triage.py` router + `main.py` wire-up
7. Thin refactor: `scripts/export_case_study_mws_variables.py` imports `mws_export`

**Track A2 — Dashboard precompute (parallel)**

1. `scripts/triage/build_variable_dashboard.py` — global MWS loop, CDF + percentiles
2. Emit `data/triage_dashboard/*.json` + manifest
3. Document in `scripts/README.md` + `00-tooling-registry.md`

### Phase B — Triaging UI

1. `TriagingPage` + `frontend/src/api/triage.ts`
2. Catalog dropdown (`case_study_locations*.json`)
3. `TriageSection`: matrix (colours), variable table, signal grid
4. Play + draft save/load
5. Hyperlinks (MWS, card, dashboard)

### Phase C — Dashboard UI

1. `DashboardPage` — CDF charts, case-study markers, URL scroll
2. Section anchors matching triaging links

### Phase D — Diagnosis deep link

1. `DiagnosisApp` URL param handler
2. Verify from triaging MWS links

### Phase E — Polish (optional)

1. “Copy to revise-cards” imports draft into revise-cards editor
2. Eval snapshot on dashboard markers (confirmed/unconfirmed colours)
3. Manual card override when retrieval returns empty

---

## 10. Relationship to existing tooling

| Existing | After this plan |
|----------|-----------------|
| `load_mws_scoped_evidence_cards` | **Authoritative** card map for triage (not cluster raster) |
| `scripts/export_case_study_mws_variables.py` | Shared `mws_export` module; script remains for batch export |
| `scripts/eval/run_case_study_diagnoses.py` | Kept for full `/api/query` session replay / CI |
| `scripts/verify/evaluate_signal_matrix.py` | Overlaps eval logic; triage reuses runtime services directly |
| `/revise-cards` | Receives promoted patches from drafts |
| `reports/case_study_eval/` | Remains deprecated for human triage |

---

## 11. Testing checklist

- [ ] Card map for a known MWS matches `/api/query` `want_llm_opinion=false` retrieved `card_id`s
- [ ] Missing `raw_jsons/{uid}.json` auto-creates on first Play
- [ ] Matrix: stress-only row; `None of these` column; instance granularity
- [ ] Matrix colours: confirmed match vs unconfirmed
- [ ] Variable table shows `var[-1]` and `mean(var)` as distinct rows with correct values
- [ ] Dashboard CDF `mws_count` >> case-study count; case-study percentiles sensible
- [ ] Draft round-trip save/load
- [ ] `/?mws=` deep link selects tehsil and zooms without auto-run
- [ ] Production-system gate skips NTFP where tree cover below threshold

---

## 12. Files to add / touch

| Action | Path |
|--------|------|
| Add | `cursor-plans/18-case-study-triaging-app.md` (this file) |
| Add | `runtime/services/mws_export.py` |
| Add | `runtime/services/expression_variable_access.py` |
| Add | `runtime/services/triage_index.py` |
| Add | `runtime/services/triage_card_map.py` |
| Add | `runtime/services/triage_eval.py` |
| Add | `runtime/routers/triage.py` |
| Add | `scripts/triage/build_variable_dashboard.py` |
| Add | `frontend/src/routes/TriagingPage.tsx` |
| Add | `frontend/src/routes/DashboardPage.tsx` |
| Add | `frontend/src/triaging/*`, `frontend/src/dashboard/*` |
| Add | `frontend/src/api/triage.ts` |
| Edit | `frontend/src/App.tsx` — routes |
| Edit | `frontend/src/routes/DiagnosisApp.tsx` — deep link |
| Edit | `runtime/main.py` — include router |
| Edit | `scripts/export_case_study_mws_variables.py` — use `mws_export` |
| Edit | `.gitignore` — `metadata/triage_drafts/` |
| Edit | `scripts/README.md`, `cursor-plans/00-tooling-registry.md` |
