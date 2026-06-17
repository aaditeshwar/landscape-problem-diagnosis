# Dual-opinion diagnosis: server evidence + optional LLM reviewer + MCQ follow-ups

> **Status:** Planned — awaiting review (do not implement until approved)  
> **Created:** 2026-06-16 · **Updated:** 2026-06-16 (v2)  
> **Branch:** `llm-in-loop` (implementation work)  
> **Prerequisite:** Plan 07 (backend signal evaluation) — **complete**; query-focused prompt + UI work on `main` (2026-06-16)

---

## Context

Recent Claude replay runs (log events 162–163) showed strong query-focused panel answers but unreliable strict signal booleans when the LLM self-reasons expressions (e.g. `groundwater_stress` sig_02). Card evidence notes carry useful narrative that should not falsify expression results.

**Proposed architecture:**

| Mode | Server (always) | LLM (optional) |
|------|-----------------|----------------|
| **Signal evaluation** | Deterministic TRUE/FALSE, pathway status, evidence note, solutions union, panel chart keys | Reviewer commentary + contextual answer + optional solutions review |
| **Follow-up** | MCQ → re-eval → server revision summary (“what changed”) | Same server re-eval + LLM reviewer + change opinion + panel update |

The LLM is **optional**. Users who only want data-driven diagnosis can turn it off; users who want a second opinion and natural-language synthesis turn it on.

---

## Design principles

| Principle | Rationale |
|-----------|-----------|
| Server owns booleans | Expressions and guards are canonical for confirmed/uncertain lists |
| Server owns solutions when LLM off | Union of framework/card solutions for confirmed pathways |
| MCQ metadata lives on **evidence cards** | Follow-up structure is card-specific; assembler already loads cards into bundle |
| LLM optional end-to-end | Same API; `want_llm_opinion` gates LLM call and UI sections |
| MCQ only for follow-up | No free-text answer box; `choice_id` enables Submit |
| LLM never re-executes `ok` signals | Reviewer interprets; does not change stored TRUE/FALSE |
| Query text optional when LLM off | Landscape diagnosis without a user question; retrieval can use a default probe query |
| Evidence note ≠ user question | Server note is diagnostic; Answer (LLM) or server summary addresses the question when provided |

---

## Target user experience

### Initial query — LLM toggle (above problem description)

**Toggle:** “Include LLM opinion” (default: **off** for faster/cheaper runs; product default TBD at review).

| Toggle | Problem description UI | Run Diagnosis enabled when |
|--------|----------------------|----------------------------|
| **Off** | Hidden (no textbox) | Always (MWS selected) |
| **On** | Visible textbox | User has entered non-empty text |

**Run Diagnosis** calls `POST /api/query` with:

```json
{
  "uid": "4_91594",
  "problem_description": "…",
  "state": "…",
  "district": "…",
  "tehsil": "…",
  "want_llm_opinion": false
}
```

When `want_llm_opinion` is false, `problem_description` may be omitted or ignored; server uses a default retrieval/diagnosis probe (existing behaviour when problem is generic).

### Initial diagnosis — LLM off (`want_llm_opinion: false`)

**Left panel:**

1. **Server diagnosis** — confirmed/uncertain pathways, per-pathway signal table, server evidence note (formatter)
2. **Suggested solutions** — deduplicated union from confirmed pathways (server)
3. **Summary** — short server `panel_update_explanation` template: names confirmed `pathway_id`s, key signal counts, no user-question narrative unless a problem was supplied

**Hidden:** Reviewer notes, LLM Answer block

**Right panel:** Charts from `panel_updates` (unchanged)

**No LLM call** — no reasoner latency; log event records `llm_skipped: true`.

### Initial diagnosis — LLM on (`want_llm_opinion: true`)

**Left panel:**

1. **Server diagnosis** (same as above — always shown first)
2. **Reviewer notes** — LLM `server_review`: agree | partial | disagree per pathway
3. **Answer** — LLM `panel_update_explanation` synthesising server + reviewer + `[USER PROBLEM]`
4. **Suggested solutions** — server union, optionally filtered/reordered with LLM `solutions_review` notes in response

**Right panel:** Charts (unchanged)

### Follow-up turn — MCQ only (no answer textbox)

1. Server exposes next follow-up as **`follow_up_mcq`**: `{ variable, question, choices[] }` (from evidence card).
2. User selects one MCQ option → **Submit answer** enabled (disabled until selection).
3. `POST /api/answer` with `{ session_id, variable, choice_id, want_llm_opinion }` (no free-text `answer`).

**LLM off:**

- Server injects normalized MCQ value → re-runs `evaluate_bundle_signals`
- Server updates pathway status, `panel_updates`, solutions union
- Server builds **`diagnosis_revision`** (pathway_changes + summary of what the MCQ changed)
- Server sets **`panel_update_explanation`** to a deterministic “what changed” narrative
- Response to frontend; **no LLM call**

**LLM on:**

- Same server re-eval and revision diff
- LLM receives: prior state, updated server eval, MCQ choice, revision diff
- LLM outputs: `server_review`, opinion on **changes made**, updated `panel_update_explanation`, optional `solutions_review`
- Post-process merges; response to frontend

Toggle state for `want_llm_opinion` should **persist for the session** (sent on each answer; UI reflects last choice or session default from initial query).

---

## Evidence card MCQ schema (not `diagnosis_framework.json`)

MCQ wiring belongs on **evidence cards** — the same source as `missing_variable_questions`, `how_answer_updates_diagnosis`, and signal `update_rule` text. The assembler already loads cards into the per-pathway bundle; the server reads MCQ definitions from the bundle at runtime.

**Extend each entry in** `missing_variable_questions[]` **on evidence card JSON** (under `data/evidence_cards/raw/*.json`, then reload/index):

```json
{
  "missing_variable": "borewell_density",
  "question_to_user": "Roughly how many borewells or tubewells are there in your village or the surrounding area?",
  "how_answer_updates_diagnosis": "High borewell density…",
  "response_type": "mcq",
  "choices": [
    {
      "id": "few",
      "label": "Very few (fewer than 10 within 2–3 km)",
      "normalized": { "band": "low", "present": true }
    },
    {
      "id": "moderate",
      "label": "Moderate (10–50 within 2–3 km)",
      "normalized": { "band": "moderate", "present": true }
    },
    {
      "id": "many",
      "label": "More than 50 within 2–3 km",
      "normalized": { "band": "high", "present": true }
    }
  ]
}
```

**Rules:**

- `response_type`: `"mcq"` (required for server-generated MCQ UI) or omit/`"text"` only during migration for cards not yet converted.
- `choices[].normalized` must match shapes already consumed by `infer_user_signal_result` / `_injected_payload` in `signal_evaluator.py` and `diagnosis_revision.py`.
- `how_answer_updates_diagnosis` remains the server-side text for revision summaries (maps to existing update_rule matching).
- **Do not** duplicate MCQ definitions in `diagnosis_framework.json`; framework keeps pathway-level **solutions** lists only (or references card_id).

**Card maintenance pipeline:**

1. Update raw card JSON files (136 cards × variables — phased).
2. Re-run existing card reload / Mongo ingest (same as Plan 05/06 card updates).
3. `scripts/maintenance/audit_follow_up_mcq_coverage.py` — report cards/variables missing `response_type: mcq`.

**Assembler (`runtime/services/assembler.py`):** pass `missing_variable_questions` (with MCQ) into bundle unchanged; prompt builder lists authorized questions from bundle, not framework.

---

## Server-only response building

### Pathway status

New: `pathway_status_from_evaluation(signal_eval, bundle) -> { confirmed_pathways, uncertain_pathways }`

- Uses `confirms_true` counts + evidence-note thresholds + `apply_signal_confidence_guard`
- Pathway `reasoning` field becomes **server evidence snippet** (from formatter), not LLM prose

### Solutions union

New: `solutions_for_confirmed_pathways(confirmed_ids, bundle) -> list[str]`

- For each confirmed `pathway_id`, collect `bundle[pathway_id].solutions` (sourced from framework at assemble time)
- **Deduplicate** preserving stable order (first-seen)
- Optional cap (e.g. top 12) to avoid huge lists when many pathways confirm

When **LLM on**, LLM may return:

```json
{
  "solutions_review": {
    "notes": "Prioritise recharge structures given confirmed groundwater_stress…",
    "priority_order": ["Trench and check-dam construction…", "…"]
  }
}
```

Post-process applies `priority_order` if valid subset of server union; otherwise keeps server order and appends notes only.

### Panel explanation (server, LLM off)

New: `build_server_panel_summary(location, confirmed, uncertain, signal_eval, problem_description?) -> str`

- Always lists confirmed `pathway_id`s with confidence and top confirming signals
- If `problem_description` provided (LLM-on path always; LLM-off optional if user typed before toggling off — edge case), append one sentence linking pathways to question
- Does **not** simulate LLM confounder reasoning

### Follow-up revision (server, LLM off)

Extend `diagnosis_revision.py`:

- After MCQ injection + re-eval, compute `pathway_changes` as today
- **`summary`**: template from `how_answer_updates_diagnosis` + signal overlay + which variables changed TRUE/FALSE
- Expose as `diagnosis_revision.summary` and mirror key points into `panel_update_explanation` for the turn

---

## LLM output schema (when `want_llm_opinion: true`)

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
          "comment": "Expression FALSE is correct; card note still supports prioritising mean delta_g."
        }
      ],
      "pathway_comment": "For this question, recharge deficit matters at medium server confidence."
    }
  ],
  "change_review": null,
  "panel_update_explanation": "…",
  "solutions_review": {
    "notes": "…",
    "priority_order": ["…"]
  },
  "follow_up_question": null
}
```

On **follow-up turns**, `change_review` summarises agreement with server `diagnosis_revision` (pathway moves + MCQ implication).

**Never from LLM JSON:** `confirmed_pathways`, `uncertain_pathways`, raw `solutions` list (server-derived).

---

## API changes

| Endpoint | New / changed fields |
|----------|---------------------|
| `POST /api/query` | Request: `want_llm_opinion: boolean`. Response: `want_llm_opinion`, `reviewer_commentary?`, `llm_skipped`, `follow_up_mcq?` |
| `POST /api/answer` | Request: `choice_id` (required), `want_llm_opinion`; deprecate free-text `answer`. Response: same optional LLM fields + `diagnosis_revision` |
| Session | Store `want_llm_opinion` default from first query (optional) |

Update `metadata/response_schema.json` accordingly.

---

## Implementation phases

### Phase 0 — Branch and baseline ✅

- [x] Push prompt/UI/replay work to `main`
- [x] Branch `llm-in-loop`
- [ ] User approves this plan (v2)

---

### Phase 1 — Server evidence note + pathway status + solutions union

**New modules:** `evidence_note.py`, extend `reasoner.py` or `diagnosis_revision.py`

- Evidence formatter per pathway (signal table, verdict, card note excerpt)
- `pathway_status_from_evaluation`
- `solutions_for_confirmed_pathways`
- `build_server_panel_summary` (LLM-off panel text)

**Tests:** `test_evidence_note.py`, `test_server_solutions.py`, golden cases for runs 162–163

**Deliverable:** Server can build a complete diagnosis response **without LLM** (except retrieval embed still runs).

---

### Phase 2 — Evidence card MCQ wiring

**Not** `diagnosis_framework.json`.

1. Define MCQ schema on evidence cards (`missing_variable_questions[].choices`).
2. Migration script to add MCQ blocks to high-traffic variables (`borewell_density`, `annual_well_depth_m`, `migrant_household_percent`, etc.) — derive choices from existing question_to_user wording.
3. Reload cards to Mongo / bundle.
4. Server: `follow_up_mcq_from_bundle(bundle, pick_next_follow_up variable)` → UI payload.
5. Answer handler: `choice_id` → `injected_variables` → re-eval.

**Tests:** MCQ injection → `user_provided` TRUE/FALSE; extend `test_diagnosis_revision.py`

**Audit script:** `audit_follow_up_mcq_coverage.py`

---

### Phase 3 — API: `want_llm_opinion` + server-only path

**Files:** `runtime/routers/query.py`, `reasoner.py`, `session_manager.py`, `diagnosis_trace.py`

1. Accept `want_llm_opinion` on query and answer.
2. When false: skip `run_diagnosis` LLM call; assemble response from Phase 1 helpers + `apply_panel_updates_from_standards`.
3. Log `llm_skipped: true`, `want_llm_opinion: false`.
4. When true: existing LLM path refactored to Phase 4 schema (not legacy reasoning JSON).

---

### Phase 4 — LLM reviewer task (only if `want_llm_opinion`)

**File:** `reasoner.py`

- Prompt: server eval block + confounders + optional `[USER PROBLEM]` + reviewer task + panel task + solutions_review task
- Follow-up prompt adds `[SERVER REVISION]` + `change_review` task
- Claude and Ollama **identical** task; both receive server eval (Claude no longer self-reasons signals)
- Post-process: merge `reviewer_commentary`; never replace server pathway lists

**Tests:** `test_prompt_builder.py` for reviewer schema; skip LLM tests when flag false

---

### Phase 5 — Frontend

**`DiagnosisPanel.tsx` / `App.tsx`:**

| Control | Behaviour |
|---------|-----------|
| Toggle “Include LLM opinion” | Above problem description; controls textbox visibility + Run enabled rule |
| Run Diagnosis | Sends `want_llm_opinion` |
| Server diagnosis section | Always visible |
| Reviewer + Answer sections | Visible only if `want_llm_opinion` was true **and** response includes them |
| Solutions | Always visible (server list) |
| Follow-up | MCQ radio/list; **no textbox**; Submit enabled on selection |
| Submit answer | Sends `choice_id` + `want_llm_opinion` |

Persist toggle in component state; pass on each answer (or lock to session initial value — decide at review).

**Log dashboard:** sections for server evidence, reviewer (if present), `llm_skipped`, solutions, panel explanation, MCQ choice on follow-up logs

---

### Phase 6 — Follow-up: server revision vs LLM change opinion

**LLM off:**

- Full server path: re-eval → pathway status → `diagnosis_revision` → `build_follow_up_summary()` → response

**LLM on:**

- Server revision computed first; LLM asked to comment on changes + update panel + optional solutions_review

**Remove:** free-text follow-up textarea and legacy `answer` string path once MCQ coverage complete

---

### Phase 7 — Replay and comparison

- Replay script passes `want_llm_opinion` flag
- Compare server-only vs LLM-on runs on same MWS
- Record MCQ `choice_id` in logs

---

## Files touched (estimate)

| Area | Files |
|------|--------|
| Evidence cards | `data/evidence_cards/raw/*.json`, card reload scripts |
| MCQ server | `assembler.py`, `signal_evaluator.py`, `diagnosis_revision.py`, `query.py` |
| Server response | `evidence_note.py`, `reasoner.py`, `panel_updates.py` |
| LLM (optional) | `reasoner.py`, `test_prompt_builder.py` |
| API schema | `metadata/response_schema.json` |
| Frontend | `DiagnosisPanel.tsx`, `App.tsx`, types, API client |
| Logs/UI | `dashboard.html`, `diagnosis_trace.py` |
| Tests | `test_evidence_note.py`, `test_server_solutions.py`, `test_diagnosis_revision.py` |

**Explicitly not changed for MCQ:** `diagnosis_framework.json` (except unchanged pathway solutions lists consumed via bundle)

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Card MCQ migration is large (136 cards) | Phased rollout; audit script; block follow-up for variables without MCQ until wired |
| LLM off feels terse | Invest in server summary templates + evidence note formatter quality |
| Toggle + empty problem when LLM on | Enforce non-empty problem client-side when toggle on |
| Solutions union too long | Dedupe + cap; LLM priority_order optional |
| Session toggle drift | Persist `want_llm_opinion` on session document |
| Retrieval without user problem when LLM off | Use default probe query (e.g. pathway retrieval from MWS context) — document in API |

---

## Acceptance criteria

1. **LLM off:** `POST /api/query` with `want_llm_opinion: false` returns in &lt;2s LLM time (no reasoner call); confirmed pathways match server eval; solutions = union of confirmed pathway solutions.
2. **LLM on:** Same server pathway lists + reviewer + Answer; user must supply problem text.
3. **Toggle UI:** Textbox hidden and Run enabled when off; textbox required when on.
4. **Follow-up:** MCQ only; Submit disabled until choice selected; no textarea.
5. **Follow-up LLM off:** `diagnosis_revision.summary` explains MCQ impact without LLM.
6. **Follow-up LLM on:** `change_review` present; panel updates reflect both server diff and LLM opinion.
7. **MCQ source:** `follow_up_mcq.choices` loaded from evidence card JSON in bundle, not framework.
8. Log dashboard reflects `llm_skipped`, server evidence, optional reviewer, solutions.

---

## Suggested implementation order

1. Phase 1 — server response without LLM (pathways, evidence, solutions, summary)
2. Phase 3 — `want_llm_opinion` API gate + server-only path wired end-to-end
3. Phase 5 (partial) — frontend toggle + LLM-off UX
4. Phase 2 — evidence card MCQ + follow-up MCQ UI
5. Phase 6 — follow-up server revision + LLM change review
6. Phase 4 — LLM reviewer when flag on
7. Phase 5 (complete) — reviewer UI + dashboard
8. Phase 7 — replay tooling

Rationale: deliver usable **server-only diagnosis** early; add MCQ and optional LLM incrementally.

---

## Review checklist (v2)

- [ ] MCQ definitions live on **evidence cards** (`missing_variable_questions`), not `diagnosis_framework.json`
- [ ] Accept **optional LLM** via toggle + `want_llm_opinion` API flag
- [ ] LLM off: no problem textbox; Run always enabled (MWS selected)
- [ ] LLM on: problem text required; reviewer + Answer shown
- [ ] Follow-up: **MCQ only**, no answer textbox
- [ ] Follow-up LLM off: server generates change explanation
- [ ] Follow-up LLM on: LLM comments on server revision + panel
- [ ] **Solutions:** server union when LLM off; LLM `solutions_review` optional when on
- [ ] Server-canonical pathway lists in both modes
- [ ] Approve implementation order above

**Do not implement until this checklist is signed off.**
