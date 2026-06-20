# Diagnosis feedback + evidence signal editor

> **Status:** Feedback complete (S1–S4); signal **viewer** complete (S4–S5e read-only). **Signal editing deferred** (S6–S7 out of scope for now).  
> **Updated:** 2026-06-19 (v4 — read-only editor, server raster query, editing deferred)  
> **Branch:** `llm-in-loop`  
> **Prerequisite:** Plan 10 (dual-opinion diagnosis + MCQ follow-ups) — largely complete on `llm-in-loop`  
> **Companion:** [`13-confirmation-policy-and-schema.md`](./13-confirmation-policy-and-schema.md) — confirmation policy, follow-up `effects`, MCQ normalization audit, schema cleanup. Policy + follow-up **review/propagation** is done via local CSV/JSON workflow (`reports/REVIEW_WORKFLOW.md`, gitignored).

---

## Decision: signal editing turned off (2026-06-19)

After building the signal editor UI, we **disabled all editing** and ship it as a **read-only review surface** only:

- Page title: **“Evidence signal editor (editing disabled)”**
- No save panel, no expression builder, no add-signal modal
- Signals, confirmation policy, follow-ups, and confounders display in full (no scroll-truncated textareas)
- Cluster map uses **server-side** `GET /api/clusters/raster-query?lat=&lon=` (local `data/clusters.tif` via `rasterio`, or remote proxy) — not client-side `georaster.getValuesAtPoint`

**Rationale:** Domain review is better done via CSV fingerprint workflow (Plan 13 + `reports/REVIEW_WORKFLOW.md`) and raw JSON maintenance scripts. A wiki-style editor adds complexity without a clear near-term merge path.

**Revisit later if:** reviewers need in-browser diffs, or the future Claude “apply suggestions” agent (Phase 7) is prioritized. Deferred work: S6 (add-signal modal + expression builder), S7 (bulk migration polish), `PUT /api/evidence-suggestions/{card_id}` UI wiring.

---

## Goals

1. Let reviewers give structured feedback on server (and optional LLM) diagnosis output for a completed session.
2. Let domain experts **browse** evidence-card signals via a cluster-map–driven read-only app (editing deferred).
3. Persist feedback in MongoDB with **log-backed reconstruction** of diagnosis context.
4. Keep only the **latest version** per reviewer per **diagnosis snapshot** (feedback). Evidence-card suggestion upserts remain API-ready but **no editor UI** for now.
5. Lay groundwork for a future Claude agent that applies suggestions to raw evidence cards (Phase 7 — still out of scope).

---

## Architecture overview

```mermaid
flowchart TB
  subgraph main [Main diagnosis app]
    DP[DiagnosisPanel]
    FBBtn[Give feedback buttons]
    Link[Signal editor link]
  end

  subgraph feedback [Feedback app /feedback]
    P1[MWS reference panel]
    P2[Follow-up Q&A panel]
    P3[Diagnosis vs feedback columns]
    P4[Name/email + Save]
  end

  subgraph signals [Signal editor /signals]
    Map[Cluster COG map]
    Panel[Evidence card editor]
    Expr[Expression builder popup]
  end

  subgraph backend [FastAPI]
    LogsAPI[/api/logs/*]
    SessAPI[sessions collection]
    FBAPI[/api/feedback/*]
    SigAPI[/api/evidence-suggestions/*]
    MetaAPI[/api/context-clusters]
  end

  subgraph mongo [MongoDB]
    Sess[(sessions)]
    FB[(diagnosis_feedback)]
    Sig[(evidence_card_suggestions)]
    Cards[(evidence_cards)]
  end

  DP --> FBBtn
  FBBtn -->|new tab + snapshot_id| feedback
  Link --> signals
  feedback --> FBAPI
  signals --> SigAPI
  FBAPI --> FB
  FBAPI --> LogsAPI
  FBAPI --> SessAPI
  SigAPI --> Sig
  SigAPI --> Cards
  SigAPI --> MetaAPI
```

---

## Phase 0 — Foundation (small, do first)

| Task | Detail |
|------|--------|
| Add `react-router-dom` | Split single-page `App.tsx` into routes: `/` (diagnosis), `/feedback`, `/signals`. |
| Export `CONTEXT_CLUSTERS` | Move cluster metadata to `metadata/context_clusters.json` (generated from or synced with `scripts/generate_evidence_cards.py`) and expose via `GET /api/context-clusters`. |
| Cluster palette API | Parse `data/clusters.qml` server-side (or ship parsed JSON) for map legend colours/labels 1–17. |
| Add `active` on signals | Extend evidence-card schema: `diagnostic_signals[].active: bool = true`. One-off script to set `active: true` on all existing raw cards + Mongo reload. |
| Variable search API | `GET /api/variables?q=...` over `metadata/variable_registry.json` + data dictionary labels — powers expression builder. |
| Cluster COG env vars | Add `CLUSTER_COG_URL` and `CLUSTER_COG_VIEWER_URL` to `.env.example` / `.env`; expose via `runtime/config.py` and `GET /api/config/public` (or equivalent) for the frontend signal editor. |

---

## Diagnosis snapshot identity (session vs stage)

**Problem:** Query and all follow-ups today share one `session_id`. Reviewers can give feedback at any stage — before any follow-up is answered, after one follow-up, after two, and so on. Feedback on the initial diagnosis and feedback after revisions must be **separate records** so later analysis can measure agreement/disagreement by stage and test whether more follow-ups lead to convergence.

**Solution:** Introduce **`diagnosis_snapshot_id`** — a stable id for one rendered diagnosis state within a session.

| Field | Meaning |
|-------|---------|
| `session_id` | Unchanged; groups the whole conversation (query + follow-ups). |
| `follow_up_count` | Number of follow-up answers **already applied** when this diagnosis was produced (`0` = initial query only). |
| `turn_no` | Session turn index from `db.sessions.turns` (1 = initial query, 2 = first follow-up answer, …). |
| `log_index` | Index of the matching row in `diagnosis.jsonl` (authoritative replay pointer). |
| `diagnosis_snapshot_id` | **`{session_id}::fu_{follow_up_count}`** — e.g. `session_a1b2c3::fu_0`, `session_a1b2c3::fu_1`. |

**Backend changes (part of S1):**

- Every `POST /api/query` and `POST /api/answer` response includes `diagnosis_snapshot_id`, `follow_up_count`, `turn_no`, and `log_index`.
- Main-app “Give feedback” buttons pass **`snapshot_id`** (not session alone) in the feedback URL.
- Feedback upsert key: **`diagnosis_snapshot_id + email`**, not `session_id + email`.

**Analysis use case:** Aggregate `sections.*.server_agreement` grouped by `follow_up_count` (or `session_id` + ordered snapshots) to plot agreement trajectories as follow-ups accumulate.

---

## Phase 1 — Log-centric context API

Feedback must **not** duplicate full diagnosis payloads in the browser alone; the server reconstructs authoritative state from logs + session.

### New endpoint: `GET /api/feedback/context`

**Query:** `snapshot_id` (required, format `{session_id}::fu_{n}`), **or** `session_id` + `follow_up_count` / `log_index` as alternate lookup keys.

**Resolution:** Parse `snapshot_id` → load session → find log event where `session_id` matches and event `follow_up_count` (or turn) matches → rebuild diagnosis at that stage.

**Sources merged:**

| Source | What it provides |
|--------|------------------|
| `db.sessions` | MWS uid, tehsil ref, turns, injected variables, retrieved card ids, `want_llm_opinion` |
| `diagnosis.jsonl` via `log_reader` | Full `llm_response`, `signal_evaluation`, `pathway_evidence`, timings, follow-up Q&A per turn |
| `db.mws` | MWS document for charts |
| `db.evidence_cards` | Card ids → pathway metadata |

**Response shape (sketch):**

```typescript
{
  session_id, diagnosis_snapshot_id, follow_up_count, turn_no, log_index,
  mws_uid, mws_doc,
  follow_up_history: FollowUpExchange[],  // only exchanges up to this snapshot
  server_diagnosis: {
    confirmed_pathways, uncertain_pathways,
    summary, solutions, signal_evaluation,
    pathway_notes: Record<pathway_id, string>  // post-revision server text
  },
  llm_diagnosis?: {
    reviewer_commentary, change_review, solutions_review_notes
  },
  retrieved_cards: { card_id, pathway_id, cluster_suffix }[]
}
```

### Why logs are required

- `DiagnosisRequestTrace` already captures per-turn prompts, raw LLM text, signal evaluation, and follow-up answers.
- Feedback documents store **`diagnosis_snapshot_id` + `log_index`** (and `updated_at`) so any saved feedback can be replayed against the exact diagnosis stage.
- Multiple snapshots per session (`::fu_0`, `::fu_1`, …) are independent; re-saving overwrites only the latest doc for that snapshot + email pair.
- A new diagnosis run gets a new `session_id`; old feedback remains on prior sessions/snapshots.

---

## Phase 2 — Diagnosis feedback UI

### Entry points (main app)

Add a compact **“Give feedback”** link/button beside:

- Each pathway reasoning block (confirmed + uncertain)
- Summary / Answer heading
- Suggested solutions section

Each opens `/feedback?snapshot_id={session_id}::fu_{follow_up_count}&focus=pathway&pathway_id=…` (or `focus=summary` / `focus=solutions`) in a **new tab** (`target=_blank`). The main app reads `diagnosis_snapshot_id` from the latest API response when wiring buttons.

Top-right of main app: **“Edit evidence signals”** → `/signals`.

Disable feedback buttons until `session_id` exists and diagnosis has loaded (session may still be active — allow feedback once at least one diagnosis response exists).

### Layout — four horizontal panels (scroll vertically as a page)

**Panel 1 — MWS reference (compact, read-only)**  
Reuse existing chart helpers from `MwsCharts.tsx` / `InfoPanel` data prep (`mwsData.ts`): hydrology sparkline, cropping, drought, land-use stacked bars, key aquifer/AER/cluster chips. Collapsible sections to keep height ~200–250px.

**Panel 2 — Follow-up Q&A (read-only)**  
List from `follow_up_history`: question, answer, MCQ choice label, signal updates summary. Same data already in `App.tsx` state; feedback page loads from context API instead.

**Panel 3 — Diagnosis vs feedback (main work area)**

| Column A (read-only) | Column B (editable) | Column C (read-only, if LLM enabled) |
|----------------------|---------------------|--------------------------------------|
| Server pathway notes | Per-section feedback | LLM pathway commentary |
| Server summary | agree / partial / disagree + free text | LLM change_review summary |
| Server solutions | agree / partial / disagree + free text | LLM solutions_review_notes |

**Sections** (one block each, scroll-to-focus from query param):

- `pathway:{pathway_id}` — server reasoning from `signal_evaluation.evidence_note` or pathway `reasoning`
- `summary` — final summary after all follow-ups
- `solutions` — `diagnosis.solutions[]`

**Per-section feedback controls:**

- Radio: **Agree / Partially agree / Disagree** (server column)
- Radio: same (LLM column, hidden if `llm_skipped`)
- Textarea: free-text feedback
- Button: **Edit signals — advanced** → `/signals?cluster={suffix}&pathway={causal_pathway}&card_id={card_id}&snapshot_id=…&return=/feedback?…`

**Panel 4 — Identity + save**

- Name (required), Email (required, basic format validation)
- **Save** → `PUT /api/feedback/{snapshot_id}` (upsert; URL-encoded snapshot id)
- Show “Last saved at …” on reload; form pre-fills from existing feedback for same email.

### MongoDB: `diagnosis_feedback`

```javascript
{
  _id: "{diagnosis_snapshot_id}::{email_lower}",
  diagnosis_snapshot_id,
  session_id,
  follow_up_count,
  turn_no,
  log_index,
  reviewer: { name, email },
  mws_uid,
  updated_at,
  sections: {
    "pathway:agriculture/water_scarcity/groundwater_stress": {
      server_agreement: "partial",
      llm_agreement: "disagree" | null,
      free_text: "...",
      linked_card_id: "...",
      linked_cluster_suffix: "009"
    },
    summary: { ... },
    solutions: { ... }
  }
}
```

**Indexes:** unique on `_id`; secondary on `session_id`, `follow_up_count`, `mws_uid`, `updated_at` (for convergence analysis).

**Upsert rule:** same `diagnosis_snapshot_id` + `email` overwrites entire document (latest only). Different snapshots in the same session produce **separate** documents.

---

## Phase 3 — Evidence signal viewer (read-only; editing deferred)

### Route: `/signals`

Query params:

| Param | Purpose |
|-------|---------|
| `cluster` | Pre-select cluster suffix `001`–`017` |
| `pathway` / `card_id` | Pre-select evidence card |
| `snapshot_id` | Provenance when arriving from feedback (with `session_id` derived from it) |
| `return` | Back-link URL (reserved; not wired in v1 read-only UI) |

### Left panel — cluster map (~40% width)

**Implementation: GeoRaster display + server point query**

- Fetch the cluster COG from **`CLUSTER_COG_URL`** (env; local fallback serves `data/clusters.tif` at `/api/clusters/cog`).
- Render with `georaster` + `georaster-layer-for-leaflet` on Leaflet (display only; raster layer has `pointer-events: none`).
- Apply palette from `clusters.qml` (17 classes + nodata) via `GET /api/clusters/palette`.
- **Click handler:** `GET /api/clusters/raster-query?lat=&lon=` → `cluster_suffix` + cluster metadata (implemented in `runtime/services/cluster_raster_query.py`; uses `rasterio` locally).
- Legend list below map; selected cluster highlighted with ring. Popup on map click.
- Link to **`CLUSTER_COG_VIEWER_URL`** for external reference/debug.

**Configuration:**

| Env var | Purpose |
|---------|---------|
| `CLUSTER_COG_URL` | Remote COG URL, or omitted when `data/clusters.tif` exists (API serves `/api/clusters/cog`) |
| `CLUSTER_COG_VIEWER_URL` | Human-readable COG viewer page (e.g. `http://100.102.70.41:10001/raster.html`) |

Both are read in `runtime/config.py` and passed to the frontend via `GET /api/config/public`.

**Reference assets:**

- `data/clusters.tif` — local cluster raster (~400 KB)
- `data/clusters.qml` — QGIS palette (17 classes + nodata)
- `metadata/context_clusters.json` — cluster metadata (sync via `scripts/maintenance/sync_context_clusters.py`)

### Right panel — read-only card viewer (~60% width)

**Step 1 — Selectors (top)**  
- Pathway dropdown: all pathways that have a card for selected cluster.  
- Show `card_id`, production system, observed stress, causal pathway.

**Step 2 — Read-only cluster context**  
`ContextClusterInfo` renders `CONTEXT_CLUSTERS` fields for selected suffix.

**Step 3 — Signals list (read-only)**

For each `diagnostic_signals[]` item:

| Field | Shown |
|-------|-------|
| `signal_id`, `variables`, `condition.expression`, `condition.type`, `severity`, `direction`, `explanation`, `active`, `condition.qualitative_description` | Yes — full text, no edit controls |
| Legacy fields (`threshold_confidence`, etc.) | Stripped from corpus (Plan 13) |

**Step 4 — Card-level policy and prose (read-only)**

- **`confirmation_policy`** — `ConfirmationPolicySummary` compact read-only view
- `overall_reasoning_note` — read-only prose block
- **`missing_variable_questions[]`** — question + choices with effect summaries (no JSON editor)
- `confounders[]` — read-only list

**Step 5 — Save / add signal**

**Not implemented.** Deferred to S6–S7. Backend `PUT /api/evidence-suggestions/{card_id}` exists but has no UI.

When navigated from feedback page, cluster and pathway are **pre-selected** via query params.

### MongoDB: `evidence_card_suggestions` (API only for now)

```javascript
{
  _id: "{card_id}::{email_lower}",
  card_id, cluster_suffix, pathway_id,
  reviewer: { name, email },
  updated_at,
  base_card_snapshot: { ... },  // server card at save time for diffing
  suggestions: {
    signals: [
      { signal_id, active, severity, direction, explanation,
        // new signals only:
        is_new: true, expression, variables, condition_type }
    ],
    confirmation_policy: { confirm_when, confidence_when, ... },
    follow_up_questions: [
      { missing_variable, question_mode, choices: [{ id, label, normalized, effects }] }
    ],
    overall_reasoning_note: "...",
    confounders: [...]
  },
  provenance: { diagnosis_snapshot_id?, session_id?, feedback_section? }
}
```

**Do not** write directly to `data/evidence_cards/raw/` or Mongo `evidence_cards` — suggestions queue for the future agent.

---

## Phase 4 — Backend routers

| Router | Endpoints |
|--------|-----------|
| `feedback.py` | `GET /context`, `GET /{snapshot_id}`, `PUT /{snapshot_id}` |
| `evidence_suggestions.py` | `GET /{card_id}`, `PUT /{card_id}`, `POST /validate-expression`, `GET /by-cluster/{suffix}` |
| `clusters.py` | `GET /palette`, `GET /cog`, `GET /raster-query?lat&lon`, `GET /suffix/{raster_value}` |
| `context.py` | `GET /context-clusters` |

Wire in `runtime/main.py`. Add Pydantic models mirroring frontend types.

---

## Phase 5 — Frontend structure

```
frontend/src/
  routes/
    DiagnosisApp.tsx      # current App logic
    FeedbackPage.tsx
    SignalEditorPage.tsx
  components/
    feedback/
      FeedbackReferencePanel.tsx
      FeedbackFollowUpPanel.tsx
      FeedbackComparisonGrid.tsx
      AgreementControl.tsx
    signals/
      ClusterMap.tsx
      SignalEditorPanel.tsx      # read-only
      ContextClusterInfo.tsx
      ConfirmationPolicySummary.tsx
  api/
    feedback.ts
    evidenceSuggestions.ts       # API client; no save UI yet
    signals.ts
```

Shared: existing `MwsCharts`, `SignalRichText`, `pathwayLabels`, types extended in `types/index.ts`.

---

## Phase 6 — Evidence card schema migration

1. ~~Script `scripts/maintenance/add_signal_active_flag.py`~~ — **applied**; archived at `scripts/archive/maintenance/add_signal_active_flag.py`.
2. `scripts/reload_evidence_cards.py` to Mongo.
3. Update `generate_evidence_cards.py` prompt/schema so new cards include `active`.
4. Update `signal_evaluator.py` to **skip** signals where `active === false`.

---

## Phase 7 — Future agent (out of scope now, design for it)

Batch job or admin endpoint:

```
Input: evidence_card_suggestions document
→ Claude prompt with base card + user diff + CONTEXT_CLUSTER
→ Output: patched raw JSON
→ Human review gate before merge
```

Store agent run id on suggestion doc: `agent_status`, `proposed_card_path`.

---

## Implementation order (recommended sprints)

| Sprint | Deliverable |
|--------|-------------|
| **S1** | Router setup, `diagnosis_snapshot_id` on diagnosis APIs, context API, `active` flag migration, context-clusters + variables + COG env/config APIs |
| **S2** | Feedback page panels 1–2 + save/load Mongo; “Give feedback” buttons on DiagnosisPanel |
| **S3** | Feedback panel 3 (comparison grid, agreement controls, advanced link) |
| **S4** | Cluster map + palette + server raster-query; card load by cluster/pathway |
| **S5a–S5e** | Plan 13: policy runtime, schema audit, **read-only** signal viewer, backend suggestion API (no save UI) |
| **S6** | *(Deferred)* Add-signal modal + expression builder + validation |
| **S7** | *(Deferred)* Bulk card migration polish, deep links, error states |

---

## Open decisions (defaults assumed)

| Question | Proposed default |
|----------|------------------|
| Popup vs new tab | **New tab** (simpler state; user asked for either) |
| Feedback before closing session? | Allowed once first diagnosis response exists |
| Upsert key | `diagnosis_snapshot_id + email` (feedback), `card_id + email` (signals) |
| Email verification | Format check only; no auth in v1 |
| COG integration | GeoRaster display + **`GET /api/clusters/raster-query`** for clicks; `rasterio` in `runtime/requirements.txt` |
| Signal editing | **Off** — read-only viewer; CSV/JSON maintenance workflow instead (Plan 13 + local `reports/`) |
| LLM column visibility | Hidden when `llm_skipped === true` |

---

## Testing checklist

- Save feedback, reload page, confirm fields restore for same email + snapshot.
- Save again with changes; confirm single Mongo doc updated (`updated_at` changes).
- Different email on same snapshot → second document.
- Feedback after initial diagnosis (`::fu_0`) and after one follow-up (`::fu_1`) → **two** Mongo docs; editing one does not overwrite the other.
- Context API returns same pathway text as main app for a given `diagnosis_snapshot_id`.
- Diagnosis API responses include `diagnosis_snapshot_id` and `follow_up_count` matching the UI state when feedback was opened.
- Signal editor deep-link from feedback pre-selects cluster + pathway without map click.
- Map click selects correct cluster suffix via `/api/clusters/raster-query`.
- Read-only viewer shows full signal text, confirmation policy, and follow-up effects.
- *(Deferred)* Deactivating a signal in suggestions / expression builder tests.

---

## Related files

| Area | Path |
|------|------|
| Diagnosis UI | `frontend/src/components/DiagnosisPanel.tsx` |
| Session + logs | `runtime/services/session_manager.py`, `runtime/services/log_reader.py` |
| Trace schema | `runtime/services/diagnosis_trace.py` |
| Context clusters | `metadata/context_clusters.json` (sync: `scripts/maintenance/sync_context_clusters.py`) |
| Cluster map assets | `data/clusters.tif`, `data/clusters.qml` |
| Evidence card example | `data/evidence_cards/raw/*__009.json` |
| Variable registry | `metadata/variable_registry.json` |
| AER retrieval neighbours | `cursor-plans/12-aer-retrieval-neighbors.md`, `runtime/services/retriever.py` |
| Confirmation policy + schema | `cursor-plans/13-confirmation-policy-and-schema.md` |
