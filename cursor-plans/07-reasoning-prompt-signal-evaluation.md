# Reasoning prompt updates for signal expression evaluation

> **Status:** Blocked — do after [06-variable-naming-normalization.md](./06-variable-naming-normalization.md).  
> **Created:** 2026-06-14  
> **Prerequisite:** Canonical variable registry, ingest backfill, assembler alignment, and evidence-card expression fixes from plan 06.

---

## Why after variable naming normalization?

Reasoning prompts should teach the LLM **how to evaluate Python signal expressions** against `present_variables`. That only works reliably once the full stack agrees on names and shapes:

| If done before plan 06 | Problem |
|------------------------|---------|
| Prompt documents `drought_causality` nested access | Cards still say `spi_class`; Mongo has `mild_drought_spi_score` |
| Prompt says `cd_*` are static scalars | Cards still use `cd_total_urbanization_ha[-1]` |
| Prompt lists evaluable variable names | Assembler may still expose `drought_causality_json` while cards use mixed aliases |

**Order:** normalize data → fix card expressions → **then** lock reasoning-prompt syntax rules to the canonical registry. Otherwise prompt text will be rewritten twice and may contradict what the LLM actually receives in `present_variables`.

Optional later step (plan 06 Phase 6): server-side `signal_evaluator.py` pre-computes TRUE/FALSE and injects results — can be added after prompt updates or in parallel once expressions are registry-valid.

---

## Current gaps (as of 2026-06-14)

| Aspect | Ollama (`reasoner.py`) | Claude |
|--------|------------------------|--------|
| Signal expressions shown in bundle | Yes | Yes |
| Explicit evaluate-TRUE/FALSE instructions | Yes — `[SIGNAL EVALUATION]` block | **No** |
| Variable shape rules (`[-1]`, static vs series, `.get()`) | **No** | **No** |
| Derived vars usable in expressions | Shown in `Derived/computed:` but not stated as in-scope for eval | Same |
| Link to `overall_reasoning_note` thresholds | Implicit | Implicit |

Evidence cards now include strict Python `expression` fields (see `generate_evidence_cards.py` `expression_rules_block()`), but reasoning prompts were designed for the older qualitative-signal era.

---

## Implementation plan

### Phase 1 — Shared evaluation instructions (Claude + Ollama)

Add a **shared** block in `runtime/services/reasoner.py` (replace or extend `_ollama_eval_block()`):

1. For each pathway, evaluate every signal `expression` against the combined namespace: `Present variables (raw)` + `Derived/computed` + `[DATA ALREADY PROVIDED BY USER]`.
2. Map results to `direction`: `confirms` + TRUE → supporting; `rules_out` + TRUE → ruling out; `amplifies` → strengthen co-occurring signals.
3. Apply `overall_reasoning_note` confirmation logic (e.g. ≥2 confirming signals TRUE → high confidence).
4. If an expression is malformed or references missing variables, use `qualitative_description` only and lower confidence — do not invent values.

**Claude:** add the same logic (currently only Ollama gets `[SIGNAL EVALUATION]`).

**Ollama:** keep “internal reasoning; do not output this section” framing if useful for JSON-only output.

### Phase 2 — Expression syntax cheat sheet (both profiles)

Add a compact block sourced from the **canonical variable registry** (plan 06), not duplicated prose. Cover:

- **Time series** — year-keyed dicts; `var[-1]` latest, `var[0]` earliest (`annual_delta_g_mm`, `drought_weeks_severe`, `lulc_*_ha`, …).
- **Derived scalars** — `trend_*`, `mean_*`, return periods; use directly from `Derived/computed:`.
- **Static scalars** — no indexing (`soge_dev_percent`, `cd_total_deforestation_ha`, `village_*`, …).
- **Nested time series** — e.g. `drought_causality[-1]["severe_moderate"]["spi_score"]` (exact path from registry after plan 06).
- **Nested per-year dicts** — `seasonal_precipitation_mm[-1].get('kharif', 0)`.
- **Object `.get()`** — `aquifer_lithology_percent.get('Alluvium', 0)` (key casing per registry).
- **Lists** — `'fisheries' not in organization_domains`.
- **Null** — `canal_name is None`.

Import registry snippet or a thin helper in `variable_registry.py` so reasoning and card-generation prompts stay in sync.

### Phase 3 — Richer signal lines in bundle (optional)

In `_format_signals_compact` / `_format_signals_ollama`, optionally include per signal:

- `condition.type` (quantitative / trend / composite / qualitative)
- `variables` list from the card
- Truncated `qualitative_description` when expression is empty or flagged non-evaluable by audit

### Phase 4 — Tests and smoke checks

- Extend `scripts/test/test_prompt_builder.py`:
  - Claude prompt contains shared eval block + syntax cheat sheet
  - Ollama retains JSON fence + eval block
  - Example expressions from a real card appear with matching variable names from sample bundle
- Smoke: run diagnosis on a case-study MWS (`metadata/case_study_locations_v2.json`) and verify reasoning cites signal TRUE/FALSE outcomes, not invented variable names

### Phase 5 — Optional: pre-computed signal results (plan 06 Phase 6)

If LLM eval remains unreliable:

- `runtime/services/signal_evaluator.py` — safe eval namespace from registry + assembler output
- Inject `[SIGNAL EVALUATION RESULTS]` into prompt: `{sig_01: true, sig_02: false, …}`
- Reasoning task becomes interpret results + confounders, not parse Python

Defer until after plan 06 and Phase 1–2 unless eval quality is still poor in testing.

---

## Files to touch

| File | Change |
|------|--------|
| `runtime/services/reasoner.py` | Shared eval block, syntax cheat sheet, optional richer signal formatting |
| `runtime/services/variable_registry.py` | New (from plan 06) — export prompt snippet for expression rules |
| `scripts/test/test_prompt_builder.py` | Assert new blocks for both profiles |
| `cursor-plans/06-variable-naming-normalization.md` | Cross-link Phase 6 evaluator to this plan |

---

## Success criteria

- Claude and Ollama prompts both instruct step-by-step expression evaluation against `present_variables` + derived + user data.
- Syntax cheat sheet uses **canonical names only** (matches registry and assembler output after plan 06).
- `test_prompt_builder.py` passes for both profiles.
- Manual smoke on ≥3 case-study MWS: confirmed pathways cite evaluable signals; no requests for variables already in `present_variables`.
- After plan 06 card fixes, audit shows no BLOCKER expression identifiers; reasoning prompts reference the same names.

---

## Suggested first PR (after plan 06)

1. Merge plan 06 registry + assembler + card expression fixes.
2. Add shared eval block + registry-driven syntax cheat sheet to `reasoner.py`.
3. Update `test_prompt_builder.py` only — no card regeneration.

Do **not** start this plan while plan 06 audit still reports BLOCKER mismatches between card expressions and MWS/assembler variable names.
