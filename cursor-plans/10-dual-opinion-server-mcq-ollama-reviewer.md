# Dual-opinion diagnosis: server evidence + LLM reviewer + MCQ follow-ups

> **Status:** Planned — awaiting review (do not implement until approved)  
> **Created:** 2026-06-16  
> **Branch:** `llm-in-loop` (implementation work)  
> **Prerequisite:** Plan 07 (backend signal evaluation) — **complete**; query-focused prompt + UI work on `main` (2026-06-16)

---

## Context

Recent Claude replay runs (log events 162–163, `claude_replay_full_20260616T172601Z.json`) showed:

- **Strong** query-focused `panel_update_explanation` when the prompt requires pathway-linked answers.
- **Weak** strict signal evaluation when the LLM self-reasons booleans — e.g. `groundwater_stress` sig_02 marked TRUE despite server FALSE (trend +12 mm/yr, mean −95 mm/yr; expression requires **both** trend &lt; 0 and mean &lt; 0).
- Card **evidence note narrative** (“if SOGE Safe but delta_g negative, prioritise water balance”) is valuable but should not falsify expression booleans.

Current Ollama runs already treat pathway **reasoning strings** as signal audits; they rarely tie the user question into per-pathway evidence. The **Answer** / `panel_update_explanation` layer is the right place for `[USER PROBLEM]`.

**Proposed architecture:** split diagnosis into three user-visible layers:

| Layer | Source | Role |
|-------|--------|------|
| **Server evidence** | `signal_evaluator` + guards | Deterministic TRUE/FALSE, pathway status, formatted evidence note |
| **Reviewer commentary** | LLM (Ollama / Claude) | Agree / partial / disagree with server eval using variables + confounders + card notes |
| **Answer** | LLM | `panel_update_explanation` synthesising server + reviewer to answer `[USER PROBLEM]` |

Follow-up turns use **MCQ** choices so **all** signal evaluation (including user-provided signals) stays server-side.

---

## Design principles

| Principle | Rationale |
|-----------|-----------|
| Server owns booleans | Expressions and `apply_signal_confidence_guard` are canonical for confirmed/uncertain lists |
| LLM never re-executes `ok` signals | Same as Plan 07; reviewer may *interpret* outcomes, not change stored TRUE/FALSE |
| MCQ over free text for structured follow-ups | Maps to existing `infer_user_signal_result` / band thresholds; eliminates `user_provided_unresolved` |
| Dual opinion, single answer | Transparency for users and graders; preserves card-narrative nuance without fake sig_02 TRUE |
| Same LLM task for Ollama and Claude | Fair comparison: both receive identical server eval block; differ only by model |
| Evidence note ≠ user question | Server note is diagnostic; Answer addresses the question |

---

## Target user experience

### Initial diagnosis

1. User submits problem for an MWS.
2. **Left panel — Server diagnosis**
   - Confirmed / uncertain pathways (from server status + guards)
   - Per-pathway signal table (from logged `signal_evaluation`)
   - Short server-generated evidence summary (new formatter)
3. **Left panel — Reviewer notes** (new section)
   - Per-pathway: `agree` | `partial` | `disagree` + 1–3 sentences
   - Explicit call-outs where card evidence note overrides strict booleans (e.g. sig_02 FALSE but chronic mean ΔG)
4. **Left panel — Answer** (existing `panel_update_explanation` UI)
   - Direct response to user question citing **both** server pathway IDs and reviewer nuance
5. **Right panel — Charts** (unchanged; driven by `panel_updates` from standards)

### Follow-up turn

1. Server picks next MCQ from authorized questions (`pick_next_follow_up` driven by server uncertain set).
2. User selects an option (not free text).
3. Server re-evaluates bundle with injected canonical answer → updates pathway status.
4. LLM re-runs reviewer + Answer only (no full signal re-audit in JSON).

---

## LLM output schema (new)

Replace per-pathway `reasoning` essays with:

```json
{
  "server_review": [
    {
      "pathway_id": "groundwater_stress",
      "agreement": "partial",
      "signal_notes": [
        {
          "signal_id": "sig_02",
          "server_result": false,
          "comment": "Expression FALSE is correct, but card note supports prioritising mean delta_g for this MWS."
        }
      ],
      "pathway_comment": "For this question, recharge deficit matters even at medium server confidence."
    }
  ],
  "panel_update_explanation": "…direct answer naming confirmed pathway_ids…",
  "solutions": ["…"],
  "follow_up_variable": null,
  "follow_up_question": null
}
```

**Server-derived fields** (not from LLM JSON):

- `confirmed_pathways` / `uncertain_pathways` — built from `signal_eval` + guards + card rules
- `panel_updates` — from `apply_panel_updates_from_standards`
- `signal_evaluation` — already logged

Post-process merges LLM `server_review` into API response as `reviewer_commentary` (new field) for UI and logs.

---

## Implementation phases

### Phase 0 — Branch and baseline (done before Phase 1)

- [x] Push query-focused prompt, log dashboard, frontend Answer, replay scripts to `main`
- [x] Create `llm-in-loop` branch for this plan
- [ ] User approves this plan

---

### Phase 1 — Server evidence note formatter

**Goal:** Deterministic prose for UI/logs without LLM.

**New:** `runtime/services/evidence_note.py` (or extend `signal_evaluator.py`)

- Input: `eval_results`, `bundle`, optional `mws_uid`, `location`
- Output per pathway:
  - Signal table (id, direction, result, status) — reuse log summary shape
  - Summary line: `confirms_true`, `amplifies_true`, `needs_llm`
  - Card `overall_reasoning_note` excerpt (already in bundle)
  - **Server pathway verdict:** confirmed | uncertain | not_supported (from guards, not LLM)
- **No** `[USER PROBLEM]` in this block

**Tests:** `scripts/test/test_evidence_note.py` — golden cases for runs 162/163 pathway summaries.

**UI:** Optional rename “Confirmed pathways” reasoning to show server table + verdict; hide LLM pathway reasoning when empty.

---

### Phase 2 — MCQ follow-up infrastructure

**Goal:** Server-only evaluation for user-provided signals.

#### 2a — Metadata / card wiring

- Audit all `Authorized follow-up questions` in bundle for band-style wording already compatible with `infer_from_update_rule_threshold`.
- Extend `diagnosis_framework.json` (or card metadata) with optional `response_type: "mcq"` and `choices[]`:

  ```json
  {
    "variable": "borewell_density",
    "question": "Roughly how many borewells…",
    "choices": [
      { "id": "few", "label": "Very few (<10)", "normalized": { "band": "low" } },
      { "id": "moderate", "label": "10–50", "normalized": { "band": "moderate" } },
      { "id": "many", "label": "More than 50", "normalized": { "band": "high" } }
    ]
  }
  ```

- Script: `scripts/maintenance/audit_follow_up_mcq_coverage.py` — report variables still requiring free text.

#### 2b — API contract

- `GET /api/query/...` or diagnosis response includes `follow_up_mcq: { variable, question, choices[] }` when structured follow-up available.
- `POST` follow-up accepts `choice_id` (preferred) or legacy `answer` string for transition.

**Files:** `runtime/routers/query.py`, `frontend/src/types`, `App.tsx`, `DiagnosisPanel.tsx`

#### 2c — Injection path

- Map `choice_id` → `injected_variables[variable]` using choice `normalized` payload (same shape `signal_evaluator` expects today).
- Ensure `evaluate_bundle_signals` re-run on follow-up uses injection before LLM call.

**Tests:** Extend `test_diagnosis_revision.py` for MCQ injection → `user_provided` TRUE/FALSE without LLM.

---

### Phase 3 — Pathway status from server only

**Goal:** LLM no longer emits `confirmed_pathways` / `uncertain_pathways` with reasoning strings.

**File:** `runtime/services/reasoner.py`

1. New function `pathway_status_from_evaluation(signal_eval, bundle) -> { confirmed, uncertain }`:
   - Apply evidence-note thresholds (≥2 confirms → confirmed high, 1 → medium, 0 + missing → uncertain)
   - Reuse `apply_signal_confidence_guard` logic or call it on a synthetic response shell
2. After LLM parse, **replace** LLM pathway lists with server-derived lists (keep LLM solutions filtered to confirmed server pathways).
3. Remove from Ollama/Claude prompt task:
   - Per-pathway reasoning requirements
   - Self signal evaluation (Claude)
4. Keep `[USER PROBLEM]` + `[ANSWER THE USER'S QUESTION]` for panel only.

**Claude profile:** Inject `[SIGNAL EVALUATION RESULTS]` same as Ollama; remove “Do NOT assume server-side TRUE/FALSE” self-reason task.

**Tests:** Update `test_prompt_builder.py`; add `test_pathway_status_from_evaluation.py`.

---

### Phase 4 — LLM reviewer + panel task

**Goal:** Ollama/Claude critique server eval and write Answer.

**Prompt block:** `[SERVER SIGNAL EVALUATION — authoritative booleans]` (existing formatter) plus:

```
[REVIEWER TASK]
For each pathway in the bundle, state agreement with server summary (agree | partial | disagree).
- agree: server booleans and pathway verdict fit the variables and card evidence note.
- partial: booleans correct but card note or confounders change how the pathway bears on [USER PROBLEM].
- disagree: a confounder or variable pattern suggests a different reading (cite signal_ids; do NOT change server booleans).

[PANEL TASK]
Write panel_update_explanation: (a) answer [USER PROBLEM], (b) name server-confirmed pathway_ids and key evidence, (c) integrate reviewer partial/disagree notes where they change the practical answer, (d) mention charts that verify the diagnosis.
```

**Post-process:** `parse_json_response` validates `server_review`; store as `reviewer_commentary` on diagnosis response and in JSONL logs.

**Tests:** Prompt builder asserts absence of old reasoning task; presence of `server_review` schema.

---

### Phase 5 — Frontend and log dashboard

**Frontend (`DiagnosisPanel.tsx`):**

| Section | Source |
|---------|--------|
| Server pathways | `confirmed_pathways` / `uncertain_pathways` + `signal_evaluation` |
| Reviewer notes | `reviewer_commentary` (new) |
| Answer | `panel_update_explanation` |
| Follow-up | MCQ radio/buttons when `follow_up_mcq` present |

**Log dashboard (`dashboard.html`):**

- Server signal table (existing merged pathways block)
- **Reviewer commentary** section (new)
- Panel explanation + solutions (existing)

**Types:** `DiagnosisResponse.reviewer_commentary`, `FollowUpMcq`.

---

### Phase 6 — Follow-up revision path

**File:** `runtime/services/diagnosis_revision.py`, `reasoner.py`

- Follow-up turn: server re-eval → server pathway status → LLM reviewer + panel only
- MCQ answer injected before eval; no `user_provided_unresolved` path for structured variables
- `diagnosis_revision` summary can cite server signal overlay + reviewer update

**Tests:** Extend `test_diagnosis_revision.py` for MCQ follow-up end-to-end mock.

---

### Phase 7 — Replay and comparison hygiene

- Update `scripts/replay_diagnosis_runs.py` to record `reviewer_commentary` and server pathway status separately from LLM raw JSON.
- Re-run baseline 20 queries on `llm-in-loop` with Ollama reviewer task; compare to Claude on **same** server eval.
- Optional: `scripts/maintenance/compare_server_vs_reviewer.py` — flags pathways where reviewer `disagree` rate is high.

---

## Files touched (estimate)

| Area | Files |
|------|--------|
| Server evidence | `signal_evaluator.py` or new `evidence_note.py`, `reasoner.py` |
| Pathway status | `reasoner.py`, possibly `diagnosis_revision.py` |
| MCQ | `diagnosis_framework.json`, `assembler.py`, `query.py`, `session_manager.py`, frontend follow-up UI |
| LLM prompt | `reasoner.py`, `test_prompt_builder.py` |
| API types | `frontend/src/types`, API client |
| UI | `DiagnosisPanel.tsx`, `dashboard.html` |
| Tests | `test_evidence_note.py`, `test_diagnosis_revision.py`, prompt tests |
| Plans/docs | this file |

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Card narrative not in expressions (sig_02 groundwater) | Reviewer `partial` + panel cites card note; optional Phase 1b server **derived signals** later if needed |
| MCQ cannot cover all variables | Audit script; keep free-text fallback behind feature flag until coverage ≥ 90% |
| LLM reviewer contradicts server in panel | Prompt: “do not change server booleans”; panel may *qualify* not *override* |
| Claude/Ollama comparison unfair if tasks differ | Phase 3 forces identical server eval + reviewer task for both profiles |
| Larger API response | `reviewer_commentary` compact; full detail in logs |

---

## Acceptance criteria

1. Initial query: pathway confirmed/uncertain lists match server `confirms_true` counts (± guard rules), not LLM invention.
2. Run 1 (4_91594): server shows sig_02 **FALSE**; reviewer **partial** on groundwater_stress; panel still answers “recharge not rainfall deficit”.
3. Run 2 (4_92694): server does **not** confirm `irrigation_challenges`; reviewer agrees; panel addresses MGNREGA effectiveness.
4. Follow-up: MCQ for `borewell_density`, `annual_well_depth_m`, etc. resolves to `user_provided` without LLM interpretation.
5. Log dashboard shows server evidence, reviewer notes, solutions, panel explanation.
6. Frontend shows Answer + Reviewer notes + server pathways in separate sections.
7. All existing `test_diagnosis_revision.py` and prompt builder tests pass; new golden tests for evidence note and MCQ injection.

---

## Out of scope (this plan)

- Encoding card narrative overrides as new Python expressions (future plan if reviewer variance is too high)
- Committing `data/runs/` replay JSON or `runtime/logs/` to git
- Changing retrieval or evidence card corpus

---

## Suggested implementation order

1. Phase 1 — evidence note formatter (read-only UI improvement)
2. Phase 3 — server pathway status (backend truth)
3. Phase 4 — reviewer + panel LLM task
4. Phase 5 — UI/dashboard
5. Phase 2 — MCQ follow-ups (can parallelize with 4–5 for initial queries)
6. Phase 6 — follow-up revision
7. Phase 7 — replay comparison

---

## Review checklist for user

- [ ] Accept server-canonical pathway lists (LLM no longer confirms pathways)
- [ ] Accept MCQ-only follow-ups for structured variables (free text deprecated)
- [ ] Accept three-layer UI: Server evidence | Reviewer | Answer
- [ ] Accept same task for Claude and Ollama after Phase 3
- [ ] Approve phase order or request reprioritisation (e.g. MCQ before reviewer)

**Do not merge implementation PRs until this checklist is signed off.**
