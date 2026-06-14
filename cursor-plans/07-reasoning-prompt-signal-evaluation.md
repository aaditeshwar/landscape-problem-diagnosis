# Reasoning prompt + backend signal evaluation

> **Status:** Done (2026-06-15)  
> **Created:** 2026-06-14 · **Updated:** 2026-06-15  
> **Prerequisite:** [06-variable-naming-normalization.md](./06-variable-naming-normalization.md) — **complete**

---

## Context

Plan 06 is done: canonical variable registry, Mongo backfill, assembler alignment, 136-card expression reload, and audit baseline are in place. `runtime/services/signal_evaluator.py` is implemented and verified separately (`scripts/verify/evaluate_signal_matrix.py` — 32 case-study MWS × 136 cards × all signals = 20,832 evaluations; **18,784 OK**, **0 hard runtime errors**, **2,048 qualitative-only** with no expression).

**Current diagnosis gap:** the reasoner still asks the LLM to evaluate Python signal expressions itself (Ollama only, via `[SIGNAL EVALUATION]`). Claude gets no eval instructions at all. Neither profile receives pre-computed TRUE/FALSE results. This leads to inconsistent pathway ranking, invented signal outcomes, and follow-up turns that re-reason pathways unrelated to the answered variable.

**New approach:** evaluate signals **on the backend** before the LLM call; inject results into the prompt; ask the LLM to **interpret** results (confounders, evidence note thresholds, user follow-up), not re-run Python unless backend evaluation failed.

---

## Design principles

| Principle | Rationale |
|-----------|-----------|
| Backend evaluates first | Deterministic, registry-aligned namespace; same logic as matrix audit |
| LLM interprets, not re-executes | Avoid duplicate eval and hallucinated TRUE/FALSE |
| Re-evaluate only on failure | Signals with `status: ok` are authoritative; LLM uses qualitative fallback only for `needs_llm` signals |
| Same path for Claude + Ollama | Both profiles get identical signal-result blocks; profile differences stay JSON-fence / intro tone only |
| Bundle-scoped pathways only | Confirmed/uncertain lists must stay within retrieved bundle (existing filter in `normalize_diagnosis_response`) |

---

## Signal evaluation statuses

Extend / use `classify_eval_error()` in `signal_evaluator.py`:

| Status | Meaning | LLM instruction |
|--------|---------|-----------------|
| `ok` | Expression returned boolean | **Do not re-evaluate.** Use TRUE/FALSE as given. |
| `no_expression` | Qualitative-only signal | Use `qualitative_description`; lower confidence. |
| `name_error` | Unknown identifier(s) | Check if variable is in `missing_variables`; if present in bundle but eval failed, use qualitative fallback. |
| `syntax_error` / `type_error` / `key_error` / `other_error` | Eval failed | Use qualitative fallback; do not invent numeric values. |

Optional helper: `missing_context_keys(expression, present_variables)` to list identifiers absent from eval context (informational in prompt).

---

## Implementation plan

### Phase 1 — Bundle signal evaluation helper

**New module surface** in `runtime/services/signal_evaluator.py` (or thin wrapper `runtime/services/signal_evaluation.py` if preferred):

```python
def evaluate_bundle_signals(
    bundle: dict[str, dict],
    injected: dict | None = None,
) -> dict[str, dict]:
    """Per pathway_id → per signal_id eval result + pathway summary counts."""
```

For each pathway in the bundle:

1. Merge `present_variables` + injected user values into eval context (same as `eval_context()` today).
2. For each `diagnostic_signals[]` entry, call `evaluate_signal_condition()`.
3. Attach: `signal_id`, `direction`, `expression`, `result` (true/false/null), `status`, `error`, `missing_vars` (if name_error).
4. Compute pathway summary: counts of `confirms` TRUE, `rules_out` TRUE, `amplifies` TRUE, `needs_llm` count.

Apply `normalize_expression()` from `variable_registry.py` before eval (same rewrites as card audit).

**Unit tests:** `scripts/test/test_signal_evaluator.py` — add bundle-level test with `SAMPLE_BUNDLE` shape from `test_prompt_builder.py`.

---

### Phase 2 — Prompt: inject `[SIGNAL EVALUATION RESULTS]`

**File:** `runtime/services/reasoner.py`

1. **Remove** `_ollama_eval_block()` instructions that tell the LLM to evaluate Python expressions for every signal.
2. **Add** `_format_signal_evaluation_results(eval_results)` — compact per-pathway block, e.g.:

   ```
   [SIGNAL EVALUATION RESULTS — server-computed; authoritative for status=ok]
   Pathway: groundwater_stress
     sig_01 | confirms | TRUE
     sig_02 | rules_out | FALSE
     sig_05 | confirms | NEEDS_LLM (no_expression) — use qualitative_description only
   Summary: confirms_true=2, rules_out_true=1, needs_llm=1
   Evidence note: Confirm with at least two primary signals.
   ```

3. Call `evaluate_bundle_signals()` inside `_build_prompt()` / `run_diagnosis()` and insert block **after** `[MWS VARIABLE VALUES AND CANDIDATE PATHWAYS]` (or interleaved per pathway — prefer **separate section** first for clarity, then optional inline duplication later).

4. **Both Claude and Ollama** receive the same results block.

---

### Phase 3 — Prompt: revised task instructions (both profiles)

Replace expression-evaluation task with interpretation task:

**Core rules (shared `_task_section`):**

1. Use **pre-computed signal results** for all `status=ok` signals. Do not contradict TRUE/FALSE.
2. Apply each card's `overall_reasoning_note` using the summary counts (e.g. ≥2 confirming TRUE → high confidence pathway).
3. Map `direction`: `confirms`+TRUE supports pathway; `rules_out`+TRUE rules out; `amplifies` strengthens co-occurring signals.
4. For `needs_llm` signals only: read `qualitative_description` / signal explanation; do not invent variable values.
5. Put pathway in `confirmed_pathways` / `uncertain_pathways` based on signal support + missing_variables (unchanged follow-up gating rules).
6. Cite specific signal IDs and TRUE/FALSE outcomes in `reasoning` strings.
7. Keep existing CRITICAL blocks: no re-ask for present data, bundle-scoped pathway IDs only, authorized follow-up questions.

**Remove** from task: "evaluate each signal expression against present_variables" (backend does this).

**Optional slim registry excerpt** — include `registry_excerpt_block()` only when any pathway has `needs_llm > 0`, to help LLM with qualitative fallback context (not for re-running Python).

---

### Phase 4 — Follow-up / revision prompt tightening

Update `[REVISION TASK — follow-up turn]` (same PR or immediate follow-up):

- Re-run backend signal evaluation with injected user evidence before LLM call (new variable may change eval context).
- **Scope revision:** only move pathways whose diagnostic variables include the answered follow-up variable **or** whose signal results changed vs prior turn. Do not promote/demote unrelated pathways solely because retrieval changed.
- **Do not re-retrieve evidence cards on follow-up** (keep initial 5 cards; inject answer into bundle only). *(Separate from signal eval but addresses observed session_40a2230a00e7 behaviour; recommend including in this PR.)*

Revision diff (`diagnosis_revision.py`): only attribute `answered_variable` in `reason` when pathway uses that variable in framework `diagnostic_variables`.

---

### Phase 5 — Tests and verification

| Test | Assert |
|------|--------|
| `scripts/test/test_prompt_builder.py` | Both profiles contain `[SIGNAL EVALUATION RESULTS]`; neither asks LLM to eval all expressions; Ollama retains JSON fence |
| `scripts/test/test_signal_evaluator.py` | `evaluate_bundle_signals()` returns expected TRUE/FALSE for sample card |
| Manual smoke | Run diagnosis on 2–3 case-study MWS; reasoning cites `sig_XX TRUE/FALSE`; no `solutions` or other invalid pathway IDs |
| Log comparison | Compare pre/post session logs: pathway count stability, signal IDs cited in reasoning |

Re-run `scripts/verify/evaluate_signal_matrix.py` only if eval namespace changes (not expected).

---

## Files to touch

| File | Change |
|------|--------|
| `runtime/services/signal_evaluator.py` | Add `evaluate_bundle_signals()`, result dataclass/dict shape |
| `runtime/services/reasoner.py` | Inject results block; rewrite task + revision instructions; remove LLM-side eval block |
| `runtime/services/variable_registry.py` | Reuse existing `registry_excerpt_block()` (conditional) |
| `runtime/routers/query.py` | Follow-up: skip re-retrieval; reuse initial card IDs from session |
| `runtime/services/diagnosis_revision.py` | Scope reason text to pathways using answered variable |
| `scripts/test/test_prompt_builder.py` | Update assertions for new prompt shape |
| `scripts/test/test_signal_evaluator.py` | Bundle eval tests |

**Out of scope for this plan:** changing evidence card corpus, registry schema, or matrix audit tooling.

---

## Success criteria

- Every diagnosis prompt includes server-computed signal TRUE/FALSE for evaluable expressions.
- LLM prompts **do not** instruct re-evaluation of `status=ok` signals.
- Claude and Ollama share the same signal-results block and interpretation task.
- Confirmed pathway reasoning cites signal IDs with TRUE/FALSE (manual smoke on ≥3 MWS).
- Follow-up answer for variable *V* does not produce revision reasons citing *V* on pathways that do not list *V* in framework diagnostic variables.
- `test_prompt_builder.py` and `test_signal_evaluator.py` pass.

---

## Suggested implementation order

1. `evaluate_bundle_signals()` + unit tests  
2. Prompt injection + task rewrite (initial query only)  
3. Smoke on case-study MWS; compare logs  
4. Follow-up: freeze retrieval + scoped revision prompt + revision reason fix  
5. Update this plan status to **Done**

---

## Confirmation checklist

- [x] Backend-first eval (LLM interprets results)
- [x] Follow-up retrieval freeze + scoped revision in same change
- [x] Conditional registry excerpt when `needs_llm > 0`
- [x] Implemented 2026-06-15
