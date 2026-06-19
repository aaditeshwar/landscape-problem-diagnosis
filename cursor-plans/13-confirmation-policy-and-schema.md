# Confirmation policy, follow-up effects, and evidence-card schema cleanup

> **Status:** In progress — S5a–S5e implemented; S6–S7 pending  
> **Updated:** 2026-06-07  
> **Prerequisite:** Plan 11 (diagnosis feedback + signal editor, S1–S4 complete)  
> **Companion:** This plan **supersedes parts of Plan 11 Phase 3 / S5–S6** for which fields the signal editor exposes and what gets saved in suggestions.

---

## Problem statement

Three gaps block trustworthy server-side diagnosis and a usable signal editor:

1. **Pathway confirmation is too loose.** `pathway_status_from_evaluation` confirms when `confirms_true >= 1`, while `overall_reasoning_note` prose often requires two or more signals. Keyword parsing of the note only caps **confidence**, not **confirmed vs uncertain**.
2. **Follow-up answers are inferred by NLP heuristics.** `how_answer_updates_diagnosis` free text + inconsistent MCQ `normalized` shapes produce fragile TRUE/FALSE overlays. Logic also lives partly in `runtime/services/follow_up_mcq.py`, duplicating card JSON.
3. **Schema surface area exceeds runtime use.** Fields like `threshold_confidence`, `context_sensitivity`, and `interaction_with` appear on every signal but are never read by the evaluator. The signal editor (Plan 11 S5) would let reviewers edit dead fields.

---

## Audit findings (2026-06-07)

### Runtime field usage

| Field | Location | Runtime use today | Recommendation |
|-------|----------|-------------------|----------------|
| `condition.expression`, `condition.type`, `qualitative_description` | signal | Evaluated / displayed | **Keep** — core |
| `direction` | signal | `confirms` / `amplifies` / `rules_out` counting | **Keep** — core |
| `severity` | signal | Not used yet | **Keep** — input to `confirmation_policy` |
| `active` | signal | Evaluator skips `false` | **Keep** — core |
| `explanation` | signal | Reasoning text, LLM prompts | **Keep** |
| `threshold_confidence` | `condition` | Never read | **Remove** from card schema (optional pipeline-only note in `metadata` if needed) |
| `context_sensitivity` | `condition` | Never read | **Remove** |
| `interaction_with` | signal | Never read; stripped from Ollama prompts | **Remove** — express co-occurrence in `confirmation_policy` |
| `direction: suggests` | signal | Enum exists; 0 signals in corpus; not counted | **Remove** from enum |
| `overall_reasoning_note` | card | Display + keyword confidence cap | **Keep** as human prose; stop using for enforcement once policy exists |
| `how_answer_updates_diagnosis` | follow-up Q | Heuristic excerpt matching | **Keep** as prose; add structured `effects` |
| `metadata.*` | card | Pipeline / review tracking only | **Keep** on cards; **hide** from signal editor |
| `context.crop_systems`, `geographic_examples` | card | Retrieval / display | **Keep**; read-only in editor |

### MCQ `normalized` consistency audit

Corpus: **136 cards**, **809 signals**, **225 MCQ questions**.

| Metric | Count |
|--------|------:|
| MCQ questions with **identical** `normalized` key sets across all choices | 106 (47%) |
| MCQ questions with **mixed key sets** within one question | **119 (53%)** |
| Questions where some choices have `band` and others do not | **73** |

**10 variable templates** account for almost all inconsistencies (same pattern repeated across cluster variants):

| Variable | Typical inconsistency |
|----------|----------------------|
| `annual_well_depth_m` | `stable`/`deepening`: `trend+present`; `failed` adds `band` |
| `groundwater_salinity` | `none`: `present+trend`; `mild`/`severe` add `band` |
| `fra_claims_filed_count` | `none`: `present` only; others add `band` |
| `forest_boundary_demarcation_status` | `clear`: `present+trend`; `partial`/`absent` add `band` |
| `forest_patch_connectivity` | `connected`: no `band`; others have `band` |
| `community_forest_governance_status` | `none`: `present` only; others have `band` |
| `market_price_crop` | `near_msp`: no `trend`; others add `trend` |
| `ntfp_collection_trend_qualitative` | varying `percent_lower` / `percent_upper` per choice |
| `tank_siltation_status` | same pattern as salinity |
| `irrigated_area_ha` | mixed (see `follow_up_mcq.py` template) |

**Example — `forest_boundary_demarcation_status` on encroachment card 010:**

| Choice | Current `normalized` | Issue |
|--------|---------------------|-------|
| `clear` | `{ present: false, trend: stable }` | No `band`; different shape from siblings |
| `partial` | `{ band: moderate, present: true }` | Has `band` |
| `absent` | `{ band: high, present: true, trend: worsening }` | Has `band` + `trend` |

Semantically `clear` is correct (`present: false` rules out the precondition), but the **shape mismatch** breaks validation, editor UX, and pushes the server toward excerpt guessing instead of explicit effects.

---

## Design principles

1. **Executable policy in JSON; prose as documentation.** Structured blocks drive the server; free text mirrors intent for humans and LLM fallback.
2. **One source of truth for follow-ups.** Card `choices[].effects` replaces duplicated logic in `follow_up_mcq.py` over time.
3. **Smaller editor surface.** Show only fields the runtime reads or the new policy blocks require.
4. **Validate at authoring time.** Audit script runs in CI and in the signal editor save path.

---

## Part A — `confirmation_policy` (pathway confirm + confidence)

### Purpose

Replace keyword parsing of `overall_reasoning_note` with explicit rules for:

- When a pathway is **confirmed** vs **uncertain** vs **ruled out** (already via `rules_out` signals)
- Pathway **confidence** (`low` / `medium` / `high`)

### Schema (v1)

Add optional top-level object on each evidence card:

```json
{
  "confirmation_policy": {
    "version": 1,
    "primary_confirm_signals": ["sig_01", "sig_03", "sig_04"],
    "confirm_when": {
      "min_confirms_true": 2,
      "min_from_set": {
        "signals": ["sig_01", "sig_03", "sig_04"],
        "min": 2
      },
      "required_all": [],
      "amplifiers_do_not_confirm": true
    },
    "confidence_when": [
      {
        "level": "high",
        "min_from_set": { "signals": ["sig_01", "sig_03", "sig_04"], "min": 2 },
        "min_high_severity_confirms": 2
      },
      {
        "level": "medium",
        "min_confirms_true": 1
      },
      {
        "level": "low",
        "default": true
      }
    ]
  }
}
```

### Rule semantics

| Rule | Meaning |
|------|---------|
| `min_confirms_true` | Count of signals with `direction: confirms` and evaluated TRUE |
| `min_from_set` | At least `min` TRUE confirms from the listed signal ids |
| `min_high_severity_confirms` | TRUE confirms where signal `severity` is `high` (or `critical`) |
| `required_all` | Listed signals must all be TRUE to confirm |
| `amplifiers_do_not_confirm` | Documentation guard; amplifiers already excluded by `direction` |
| `confidence_when` | First matching rule wins; last rule may be `{ default: true, level: "low" }` |

**Simple presets** (document in schema descriptions):

- Two high confirms → high confidence
- One high + one moderate confirm → medium confidence
- Mandatory signal: `required_all: ["sig_04"]`
- “Two of three primaries”: `min_from_set: { signals: [...], min: 2 }`

### Reference encoding — card `005`

Prose says: confirm when at least two of sig_01, sig_03, sig_04; sig_02 and sig_05 amplify only.

Policy above matches that. Today sig_03 alone incorrectly confirms.

### Runtime integration

New module: `runtime/services/confirmation_policy.py`

| Function | Called from |
|----------|-------------|
| `pathway_is_confirmed(pathway_eval, card)` | `evidence_note.pathway_status_from_evaluation` |
| `pathway_confidence_level(pathway_eval, card)` | Same + `reasoner.apply_signal_confidence_guard` |
| `fallback_from_note(note)` | When `confirmation_policy` absent (legacy cards) |

**Behavior change:** If `confirm_when` not satisfied → pathway goes to **uncertain**, not confirmed-with-medium.

### Migration

1. Script `scripts/maintenance/derive_confirmation_policy.py`:
   - Parse `overall_reasoning_note` + signal `direction`/`severity`/`signal_id`
   - Emit draft `confirmation_policy` per card
   - Write `reports/confirmation_policy_review.csv` for expert review (card_id, inferred policy, confidence in parse)
2. Pilot: manually approve **10 cards** (include `005`, `010`, one groundwater, one rainfed).
3. Bulk apply after review; reload Mongo.
4. Deprecate `_min_confirms_required` / `_min_confirms_required_from_note` keyword paths once ≥90% cards have policy.

---

## Part B — Follow-up `effects` (replace heuristic inference)

### Purpose

Make MCQ (and free-text band) answers drive signal overlays **deterministically**.

### Schema additions on `missing_variable_questions[]`

```json
{
  "missing_variable": "forest_boundary_demarcation_status",
  "question_mode": "presence_graded",
  "question_to_user": "...",
  "how_answer_updates_diagnosis": "... human prose unchanged ...",
  "response_type": "mcq",
  "choices": [
    {
      "id": "clear",
      "label": "...",
      "normalized": {
        "present": false,
        "trend": "stable"
      },
      "effects": {
        "signals": [
          { "signal_id": "sig_05", "result": false }
        ]
      }
    },
    {
      "id": "absent",
      "label": "...",
      "normalized": {
        "band": "high",
        "present": true,
        "trend": "worsening"
      },
      "effects": {
        "signals": [
          { "signal_id": "sig_05", "result": true }
        ]
      }
    }
  ]
}
```

- `effects.signals[].result`: `true` | `false` (boolean)
- Optional `effects.pathway_hint`: `"supports"` | `"weakens"` | `"rules_out"` for revision messaging only
- Omit `direction` on effect rows — inherit from target signal unless `direction` override needed for edge cases

### `question_mode` enum (new, required for MCQ)

| Mode | All choices must include | When to use |
|------|--------------------------|-------------|
| `magnitude` | `band`, `present: true` | Percent / income / density scales |
| `presence_graded` | `present`; if `present: true` also `band` | Condition exists at low/med/high |
| `trend` | `trend`, `present` | Worsening / stable / improving |
| `presence_binary` | `present` only | Yes/no feature exists |

**Normalization rules (validation):**

- Within one question, every choice’s `normalized` must satisfy the same `question_mode` shape.
- `band` enum: `low` | `moderate` | `high` (server maps `moderate` → `mid` internally, unchanged).
- `trend` enum: `stable` | `worsening` | `improving`.
- `present`: boolean required for all modes except optional on free-text parse path.

### Runtime integration

In `signal_evaluator._apply_user_answer_overlay`:

1. If choice has `effects.signals` → apply directly (`user_provided`, no excerpt NLP).
2. Else if `follow_up_mcq.MCQ_TEMPLATES` has `confirms_result` → legacy fallback.
3. Else `match_update_rule_excerpt` + `infer_user_signal_result` → legacy fallback.
4. Else `user_provided_unresolved` → LLM path.

### Consolidation of `follow_up_mcq.py`

| Phase | Action |
|-------|--------|
| v1 | Keep templates; migration script copies `confirms_result` into card `effects` |
| v2 | Templates become thin defaults only when card lacks MCQ block |
| v3 | Remove hard-coded per-variable confirms map |

---

## Part C — MCQ normalized cleanup

### Fix strategy for 10 inconsistent variables

| Variable | `question_mode` | Normalization fix |
|----------|-----------------|-------------------|
| `forest_boundary_demarcation_status` | `presence_graded` | Keep `clear` as `present:false`; add `band: "low"` optional for shape parity OR accept mode rule “band omitted when present false” |
| `fra_claims_filed_count` | `presence_graded` | Add `band: "low"` to `none` **or** use `presence_binary` for `none` |
| `annual_well_depth_m` | `trend` | Add `band: "high"` to all choices **or** remove `band` from `failed` |
| `groundwater_salinity`, `tank_siltation_status` | `presence_graded` | Add `band: "low"` to `none` with `present: false` |
| `community_forest_governance_status` | `presence_graded` | Add `band: "low"` to `none` or switch `none` to `present: false` |
| `forest_patch_connectivity` | `presence_graded` | Add `band: "low"` to `connected` |
| `market_price_crop` | `magnitude` | Add `trend: "stable"` to `near_msp` |
| `ntfp_collection_trend_qualitative` | `magnitude` | Standardize percent fields on all three choices |
| `irrigated_area_ha` | `magnitude` | Align all choices to `band+present+percent_*` |

**Preferred rule for presence_graded:** When `present: false`, `band` may be omitted. When `present: true`, `band` is **required**. Validation enforces this instead of requiring identical keys on every choice.

### Audit script

`scripts/verify/audit_mcq_normalized.py`:

- Fail on unknown keys
- Fail when `question_mode` violated
- Warn when `effects` missing for MCQ variables that appear in `follow_up_mcq.py`
- Report per card; exit non-zero in CI

---

## Part D — Schema cleanup (`metadata/evidence_card_schema.json`)

### Remove from public card schema

| Removed field | Rationale |
|---------------|-----------|
| `condition.threshold_confidence` | Never evaluated; confuses reviewers |
| `condition.context_sensitivity` | Never evaluated |
| `diagnostic_signals[].interaction_with` | Never evaluated; replaced by `confirmation_policy` |
| `direction` enum value `suggests` | Unused in corpus and runtime |

### Add to schema

| Added field | Notes |
|-------------|-------|
| `confirmation_policy` | Optional v1 object (required for new cards after migration cutoff) |
| `diagnostic_signals[].active` | Already in corpus; add to schema |
| `missing_variable_questions[].question_mode` | Required when `response_type: mcq` |
| `missing_variable_questions[].response_type` | Already in corpus; document |
| `choices[].normalized` | Document subfields |
| `choices[].effects` | Optional until migration; required after cutoff |
| `choices[].normalized` subschema | `band`, `present`, `trend`, `percent_lower`, `percent_upper` |

### Expand descriptions (keep fields)

Update descriptions to state **runtime role**:

- **`severity`:** “Used by `confirmation_policy` to count high/moderate confirms; not evaluated directly.”
- **`direction`:** “Runtime: only `confirms`+TRUE counts toward confirmation; `amplifies` affects summary counts only; `rules_out`+TRUE removes pathway.”
- **`overall_reasoning_note`:** “Human + LLM narrative. Executable rules belong in `confirmation_policy`.”
- **`how_answer_updates_diagnosis`:** “Human-readable mirror of `effects`. Server prefers `choices[].effects` when present.”
- **`normalized.band`:** “Coarse magnitude when the condition is present.”
- **`normalized.present`:** “Whether the condition/feature exists.”
- **`normalized.trend`:** “Direction of change when relevant.”

### `metadata` block

Keep for pipeline (`created_by`, `extraction_model`, dates, `reviewed_by_expert`). Do **not** expose in signal editor. `confidence_overall` stays as card QA metadata only.

---

## Part E — Plan 11 integration (signal editor + feedback)

> Apply these edits to `cursor-plans/11-diagnosis-feedback-signal-editor.md` when this plan is approved.

### S5 signal editor — fields to show

**Per signal (editable):**

| Field | Editable |
|-------|----------|
| `active` | Yes — toggle |
| `severity` | Yes — enum |
| `direction` | Yes — enum (`confirms`, `amplifies`, `rules_out` only) |
| `explanation` | Yes — textarea |
| `condition.expression`, `variables`, `signal_id`, `condition.type` | Read-only |
| `condition.qualitative_description` | Yes — textarea |

**Remove from editor UI (do not save in suggestions):**

- `threshold_confidence`
- `context_sensitivity`
- `interaction_with`

**New card-level sections (editable):**

| Section | Content |
|---------|---------|
| Confirmation policy | Structured form builder for `confirm_when` + `confidence_when` (or JSON textarea v1) |
| Overall reasoning note | Wiki textarea (prose only) |
| Follow-up questions | List with `question_mode`, choices, `normalized`, **`effects`** |
| Confounders | Unchanged |

### S5 signal editor — read-only context

Keep `context.*`, sources, metadata hidden or collapsed “pipeline info”.

### Mongo `evidence_card_suggestions` shape (update)

```javascript
suggestions: {
  signals: [
    { signal_id, active, severity, direction, explanation }
    // no threshold_confidence, context_sensitivity
  ],
  confirmation_policy: { ... },
  follow_up_questions: [
    { missing_variable, question_mode, choices: [{ id, label, normalized, effects }] }
  ],
  overall_reasoning_note: "...",
  confounders: [...]
}
```

### Sprint reorder (recommended)

| Sprint | Deliverable |
|--------|-------------|
| **S5a** | Schema doc + audit scripts (`audit_mcq_normalized`, `derive_confirmation_policy` report-only) |
| **S5b** | `confirmation_policy` runtime + tests; pilot 10 cards |
| **S5c** | Signal editor: editable policy, severity, direction, active; hide removed fields |
| **S5d** | Follow-up `effects` runtime + MCQ normalization migration (10 variables) |
| **S5e** | Signal editor: follow-up effects editor; save/load suggestions |
| **S6** | Add-signal modal (unchanged scope, no dead metadata fields) |
| **S7** | Bulk card migration, CI audits, polish |

Plan 11 S5–S7 rows should be replaced or annotated with the above when approved.

---

## Part F — Testing checklist

### Confirmation policy

- [ ] Card `005`: one primary confirm → **uncertain**, not confirmed
- [ ] Card `005`: two of {sig_01, sig_03, sig_04} → confirmed, high confidence
- [ ] Card with only amplifiers TRUE → uncertain
- [ ] Legacy card without policy → old behavior via `fallback_from_note`
- [ ] `rules_out` TRUE still drops pathway before policy runs

### Follow-up effects

- [ ] `forest_boundary_demarcation_status` / `clear` → target signal FALSE without excerpt NLP
- [ ] MCQ with `effects` → no `user_provided_unresolved` when effects complete
- [ ] Free-text answer still uses normalize + effects_by_normalized when added

### Schema / audit

- [ ] `audit_mcq_normalized.py` passes on pilot cards
- [ ] Signal editor does not render removed fields
- [ ] Saved suggestions round-trip without stripped dead fields reappearing

---

## Part G — Out of scope (later)

- `context_sensitivity` gating by cluster context (v2)
- Weighting by `threshold_confidence` (v2, if thresholds become uncertain intervals)
- LLM-only pathway confirmation bypassing policy
- Auto-merge agent applying suggestions to raw JSON (Plan 11 Phase 7)

---

## Related files

| Area | Path |
|------|------|
| Current confirmation logic | `runtime/services/evidence_note.py`, `runtime/services/reasoner.py` |
| Follow-up inference | `runtime/services/diagnosis_revision.py`, `runtime/services/signal_evaluator.py` |
| MCQ templates (to consolidate) | `runtime/services/follow_up_mcq.py` |
| Schema | `metadata/evidence_card_schema.json` |
| Signal editor plan | `cursor-plans/11-diagnosis-feedback-signal-editor.md` |
| Example cards | `005` (multi-sector), `010` (encroachment / boundary MCQ) |
