# Diagnosis feedback + evidence signal editor

> **Status:** In progress — S1–S5e complete; S6–S7 pending  
> **Updated:** 2026-06-07 (v3 — Plan 13 cross-ref, trimmed editor fields)  
> **Branch:** `llm-in-loop`  
> **Prerequisite:** Plan 10 (dual-opinion diagnosis + MCQ follow-ups) — largely complete on `llm-in-loop`  
> **Companion:** [`13-confirmation-policy-and-schema.md`](./13-confirmation-policy-and-schema.md) — confirmation policy, follow-up `effects`, MCQ normalization audit, schema cleanup. **Do not implement S5 field edits until Plan 13 is approved.**

---

## Goals

1. Let reviewers give structured feedback on server (and optional LLM) diagnosis output for a completed session.
2. Let domain experts suggest edits to evidence-card signals via a cluster-map–driven wiki app.
3. Persist everything in MongoDB with **log-backed reconstruction** of diagnosis context.
4. Keep only the **latest version** per reviewer per **diagnosis snapshot** (feedback) or per card (signal suggestions).
5. Lay groundwork for a future Claude agent that applies suggestions to raw evidence cards.

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

## Phase 3 — Evidence signal editor (“wiki” app)

### Route: `/signals`

Query params:

| Param | Purpose |
|-------|---------|
| `cluster` | Pre-select cluster suffix `001`–`017` |
| `pathway` / `card_id` | Pre-select evidence card |
| `snapshot_id` | Provenance when arriving from feedback (with `session_id` derived from it) |
| `return` | Back-link URL |

### Left panel — cluster map (~40% width)

**Implementation (fixed): GeoRaster + Leaflet**

- Fetch the cluster COG from **`CLUSTER_COG_URL`** (env; see `.env.example`).
- Render with `georaster` + `georaster-layer-for-leaflet` on the existing Leaflet stack.
- Apply palette from `clusters.qml` (17 classes + nodata) via server `GET /api/clusters/palette`.
- **Click handler:** point-query the loaded GeoRaster at lat/lon → cluster id 1–17 → map to suffix `001`–`017` via static lookup matching `CONTEXT_CLUSTERS`.
- Legend overlay with cluster names; link to **`CLUSTER_COG_VIEWER_URL`** for external reference/debug.
- If `cluster` query present, highlight that cluster and skip requiring a map click.

**Configuration:**

| Env var | Purpose |
|---------|---------|
| `CLUSTER_COG_URL` | Direct HTTP URL to the GeoTIFF COG fetched by GeoRaster in the browser |
| `CLUSTER_COG_VIEWER_URL` | Human-readable COG viewer page (e.g. `http://100.102.70.41:10001/raster.html`) |

Both are read in `runtime/config.py` and passed to the frontend via a small public config endpoint. If COG fetch fails due to CORS, add a fallback `GET /api/clusters/at?lon=&lat=` proxy (S4 only if needed).

**Reference assets:**

- `data/clusters.tif` — local cluster raster (~400 KB; dev fallback if remote COG unavailable)
- `data/clusters.qml` — QGIS palette (17 classes + nodata)

### Right panel — card editor (~60% width)

**Step 1 — Selectors (top)**  
- Pathway dropdown: all pathways that have a card for selected cluster (from evidence_cards index or static manifest).  
- Show `card_id`, production system, observed stress, causal pathway.

**Step 2 — Read-only cluster context**  
Render fields from `CONTEXT_CLUSTERS` for selected suffix: label, aquifer_types, aer_tags, rainfall_regime, terrain_types, geographic_examples.

**Step 3 — Signals list**

For each `diagnostic_signals[]` item (see Plan 13 for rationale — hide unused fields):

| Field | Editable? |
|-------|-----------|
| `signal_id`, `variables`, `condition.expression`, `condition.type` | **No** (read-only) |
| `severity`, `direction`, `explanation` | Yes |
| `condition.qualitative_description` | Yes (textarea) |
| **`active`** | Yes — toggle |
| ~~`threshold_confidence`~~, ~~`context_sensitivity`~~, ~~`interaction_with`~~ | **Hidden** — removed from schema (Plan 13); not shown in editor |

**Step 4 — Card-level policy and prose**

- **`confirmation_policy`** — editable structured form (or JSON textarea v1): `confirm_when`, `confidence_when`, primary signal sets. Replaces relying on `overall_reasoning_note` keywords for server enforcement.
- `overall_reasoning_note` — editable wiki textarea (human prose only); support `(sig_01)` references with inline preview (reuse `SignalRichText` pattern).
- **`missing_variable_questions[]`** — editable: `question_mode`, MCQ choices with `normalized` + **`effects.signals`** (not `how_answer_updates_diagnosis` alone). See Plan 13 for `question_mode` / normalization rules.
- `confounders[]` — editable list (add/remove items, text only).

**Step 5 — Add signal**

- **Add signal** opens modal:
  - New `signal_id` auto (`sig_XX` next free)
  - **Expression builder:** search variables → insert into expression → operators (`>`, `<`, `and`, `or`, `in`, `.get()`)
  - Full editable: expression, severity, direction, explanation, active=true (no threshold_confidence / context_sensitivity)
  - Validates expression via backend `POST /api/evidence-suggestions/validate-expression` (reuse `variable_registry` + assembler sandbox on dummy MWS or syntax-only check)

**Step 6 — Save**

- Name + email (required)
- **Save** → `PUT /api/evidence-suggestions/{card_id}` upsert

When navigated from feedback page, cluster and pathway should be **pre-selected** (no map click required).

### MongoDB: `evidence_card_suggestions`

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
| `clusters.py` | `GET /palette`, `GET /at?lon&lat` (optional proxy) |
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
      SignalEditorPanel.tsx
      ExpressionBuilderModal.tsx
      ContextClusterInfo.tsx
  api/
    feedback.ts
    evidenceSuggestions.ts
```

Shared: existing `MwsCharts`, `SignalRichText`, `pathwayLabels`, types extended in `types/index.ts`.

---

## Phase 6 — Evidence card schema migration

1. Script `scripts/maintenance/add_signal_active_flag.py`: set `"active": true` on every signal in raw JSON.
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
| **S4** | Cluster map + palette; card load by cluster/pathway |
| **S5a–S5e** | See Plan 13 sprint split: policy runtime, schema audit, editor (signals + policy + follow-up effects), save |
| **S6** | Add-signal modal + expression builder + validation |
| **S7** | Bulk card migration, CI audits, polish (deep links, reload persistence, error states) |

---

## Open decisions (defaults assumed)

| Question | Proposed default |
|----------|------------------|
| Popup vs new tab | **New tab** (simpler state; user asked for either) |
| Feedback before closing session? | Allowed once first diagnosis response exists |
| Upsert key | `diagnosis_snapshot_id + email` (feedback), `card_id + email` (signals) |
| Email verification | Format check only; no auth in v1 |
| COG integration | GeoRaster + Leaflet; URLs from `CLUSTER_COG_URL` / `CLUSTER_COG_VIEWER_URL`; backend point proxy only if CORS blocks |
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
- Map click selects correct cluster suffix vs `CONTEXT_CLUSTERS`.
- Deactivating a signal in suggestions persists; evaluator ignores inactive signals after agent merge.
- Expression builder rejects unknown variables.

---

## Related files

| Area | Path |
|------|------|
| Diagnosis UI | `frontend/src/components/DiagnosisPanel.tsx` |
| Session + logs | `runtime/services/session_manager.py`, `runtime/services/log_reader.py` |
| Trace schema | `runtime/services/diagnosis_trace.py` |
| Context clusters | `scripts/generate_evidence_cards.py` (`CONTEXT_CLUSTERS`) |
| Cluster map assets | `data/clusters.tif`, `data/clusters.qml` |
| Evidence card example | `data/evidence_cards/raw/*__009.json` |
| Variable registry | `metadata/variable_registry.json` |
| AER retrieval neighbours | `cursor-plans/12-aer-retrieval-neighbors.md`, `runtime/services/retriever.py` |
| Confirmation policy + schema | `cursor-plans/13-confirmation-policy-and-schema.md` |
