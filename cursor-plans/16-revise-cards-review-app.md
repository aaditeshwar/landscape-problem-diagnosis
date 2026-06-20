# Revise Cards — Claude review decision app

> **Status:** Implemented — `/revise-cards`  
> **Created:** 2026-06-07  
> **Prerequisite:** Plan 15 Phase 2 complete (`reports/claude_review/*` exists)  
> **Route:** `/revise-cards`  
> **Related:** [15-claude-evidence-card-review.md](./15-claude-evidence-card-review.md), [00-tooling-registry.md](./00-tooling-registry.md)

---

## Stakeholder decisions (approved)

| Question | Decision |
|----------|----------|
| Integration | Route in existing `frontend/` at `/revise-cards` |
| Decision keys | Composite `{card_id}::{issue_id}` |
| Edit UX | **Structured fields** (expression, note, MCQ, policy) |
| Bulk actions | **None** — review each issue individually |
| Finalize | **Per card** — “Finalize card” writes JSON files |
| Edits storage | **Separate file** — never overwrite `suggested_patches.json` |
| Signal editor link | Not needed |

---

## Problem

Plan 15 Phase 3 requires human triage of Claude findings. The revise-cards app walks card-by-card, color-codes severity, highlights current values, supports structured patch edits, and persists decisions on **Finalize card**.

---

## Architecture

| Layer | Path |
|-------|------|
| Frontend route | `frontend/src/routes/ReviseCardsPage.tsx` |
| UI module | `frontend/src/revise-cards/` |
| API client | `frontend/src/api/claudeReview.ts` |
| Backend router | `runtime/routers/claude_review.py` |
| Store | `runtime/services/claude_review_store.py` |

---

## Data files

| File | Written by | Purpose |
|------|------------|---------|
| `reports/claude_review/results/{card_id}.json` | Claude reviewer | Findings (read-only) |
| `reports/claude_review/suggested_patches.json` | Merge script | Claude suggestions (read-only) |
| `metadata/claude_review_decisions.json` | **Finalize card** | accept/reject per `{card_id}::{issue_id}` + `card_status` |
| `metadata/claude_review_edited_patches.json` | **Finalize card** | Human-edited patches only (when different from Claude) |

Claude’s `suggested_patches.json` is never modified by the app.

---

## Decision file schema

```json
{
  "schema_version": 1,
  "decisions": {
    "agriculture__water_scarcity__groundwater_stress__003::D3a_primary_signal_set_vs_prose": {
      "card_id": "…__003",
      "issue_id": "D3a_primary_signal_set_vs_prose",
      "decision": "accept",
      "reviewer_note": "",
      "decided_at": "2026-06-20T14:30:00Z"
    }
  },
  "card_status": {
    "agriculture__water_scarcity__groundwater_stress__003": {
      "status": "finalized",
      "finalized_at": "…",
      "reviewer": "name",
      "accepted_count": 3,
      "rejected_count": 2
    }
  }
}
```

---

## Edited patches file schema

```json
{
  "schema_version": 1,
  "patches": {
    "card_id::issue_id": {
      "card_id": "…",
      "issue_id": "…",
      "field_path": "diagnostic_signals[1].condition.expression",
      "patch": { "diagnostic_signals": […] },
      "finalized_at": "…"
    }
  }
}
```

Apply script prefers `metadata/claude_review_edited_patches.json` over Claude suggestion when present.

---

## User workflow

1. Open `http://localhost:5173/revise-cards` (FastAPI on 8000 required for API)
2. Select batch (from `review_manifest.json`)
3. Pick card in sidebar
4. For each issue: **Accept** or **Reject**; if accepting, edit structured fields if needed
5. Click **Finalize card** → writes `claude_review_decisions.json` + `claude_review_edited_patches.json`
6. Repeat for all cards; then run apply script

```powershell
.venv\Scripts\python.exe scripts\review\apply_claude_review_patches.py --dry-run
.venv\Scripts\python.exe scripts\review\apply_claude_review_patches.py --apply
```

Apply only touches cards with `card_status.finalized` (use `--include-unfinalized` to override).

### Variable highlighting (revise-cards UI)

- Green highlight: identifier in data dictionary + assembler + derived scalars (`GET /api/claude-review/variable-registry`)
- Red highlight: variable-like token not in that set
- Use to reject false-positive D1e findings (e.g. `mean_annual_delta_g_mm` flagged by Claude when registry list was incomplete in prompt)

### Claude prompt fix (2026-06-07)

Pilot used `registry_excerpt_block()` (drought policy only). Reviewer now uses `full_review_registry_block()` with all ~215 allowed names including `mean_annual_delta_g_mm`. Re-run review to refresh findings.

---

## API

Prefix: `/api/claude-review`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/batches` | List review batches |
| GET | `/batch/{batch_id}` | Card list + progress |
| GET | `/batch/{batch_id}/card/{card_id}` | Findings + raw card + saved decisions/edits |
| POST | `/card/{card_id}/finalize` | Persist decisions + human edits for one card |
| GET | `/decisions` | Debug: full decisions doc |
| GET | `/edited-patches` | Debug: full edits doc |

---

## Structured patch editor

Handles common patch shapes from pilot:

- `overall_reasoning_note` → textarea
- `diagnostic_signals[]` → expression + qualitative_description per signal
- `missing_variable_questions[]` → label, band, present
- `confirmation_policy` → primary signal list + read-only JSON reference
- `metadata.evaluator_extension_requested` → textarea
- Unusual flat path keys → read-only JSON fallback

---

## Checklist

- [x] Stakeholder approves plan
- [x] Phase A backend
- [x] Phase B core UI
- [x] Phase C per-card finalize + separate edits file
- [x] Apply script composite keys + edits file
- [ ] Pilot review completed via app
- [ ] Apply dry-run verified after review
