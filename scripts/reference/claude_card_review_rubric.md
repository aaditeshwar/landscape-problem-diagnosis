# Claude evidence card review rubric

Use this rubric when reviewing one complete evidence card JSON. Return structured JSON only (see `metadata/claude_review_finding_schema.json`).

**Primary goal:** catch **semantic mismatches** between human prose and executable logic — not type/syntax/registry issues already covered by deterministic preflight and the variable catalog in the prompt.

**Priority order:** D3 (confirmation policy ↔ note) → D1 (expression ↔ qualitative prose) → D4 (follow-ups ↔ prose) → D2 (temporal prose, time-series only) → D5 (schema).

**Do NOT spend findings on:**
- Unregistered variable names already in the allowed list
- Valid `[-1]` / `[0]` on time-series variables listed in the prompt
- Static variables misclassified as time series (especially `soge_dev_percent`, `soge_class_name`)
- `variables[]` array housekeeping (sync is handled by maintenance scripts; only flag if it causes a clear prose/expression contradiction)
- **Qualitative-only signals** (`condition.type: qualitative` with no `expression`) whose variables appear in `missing_variable_questions` with MCQ `choices[].effects` — these are evaluated via user follow-up, not server expressions. **Do not flag “no expression” or emit info findings for this pattern.**
- MCQ schema shape (stay within existing choice structure)
- **`confidence_when` amplifier leaks** — see D3 runtime semantics below (common false positive)

---

## D3 — Confirmation policy ↔ overall_reasoning_note (most important)

Compare `confirmation_policy` to `overall_reasoning_note`:

- Minimum confirm count (`min_confirms_true`, `min_from_set.min`) matches prose (“at least two primary signals”)
- Primary signal set matches note (confirm signals, not amplifiers)
- Amplifiers (`direction: amplifies`) must not confirm alone **via `confirm_when`**
- `confidence_when` **high** tier matches note when prose distinguishes high vs medium (e.g. “two high-severity primaries”)
- Required AND groups in prose reflected in `required_all` / `required_any`

On mismatch: prefer fixing `confirmation_policy` to match correct prose. Provide full `suggested_patch.confirmation_policy` (v1 schema). Only suggest note edits if prose is wrong.

### Runtime semantics (read before flagging D3)

Policy evaluation is **two-phase** in `runtime/services/confirmation_policy.py` + `reasoner.apply_signal_confidence_guard`:

| Phase | When it runs | What it controls |
|-------|----------------|------------------|
| **`confirm_when`** | Always first | Pathway **confirmed vs uncertain** (`pathway_is_confirmed`) |
| **`confidence_when`** | **Only if already confirmed** | Caps **high / medium / low** among confirmed pathways |

**If `confirm_when` fails** → pathway is demoted to **uncertain** with confidence **low**; **`confidence_when` is never evaluated.**

**`confirms_true`** counts only signals with **`direction: confirms`** and **`result: true`**. Signals with **`direction: amplifies`** increment `amplifies_true` only — they **never** enter `confirms_true` or `true_ids` used by policy rules.

**`amplifiers_do_not_confirm`** in `confirm_when` is a **documentation guard** — the runtime does **not** read this flag. Amplifier exclusion is enforced by **`direction: amplifies`**, not by copying the flag into `confidence_when`.

### D3 false positives — do NOT flag

1. **“Medium `confidence_when` with `min_confirms_true: 1` lets amplifiers reach medium confidence.”**  
   **Wrong.** Amplifiers do not increment `confirms_true`. Unconfirmed pathways never reach `confidence_when`. Do not suggest scoping medium tier to primaries solely to block this imaginary leak.

2. **“`confidence_when` should repeat `amplifiers_do_not_confirm: true`.”**  
   **Wrong.** Flag not enforced at runtime; amplifiers already excluded from confirm counts via `direction`.

3. **Medium tier is a permissive catch-all** (`min_confirms_true: 1` or `min_from_set min: 1` on primaries) **after** a strict `confirm_when` (e.g. 2-of-3 primaries).  
   This usually means **“confirmed but not high”** — **not a bug**. Only flag medium tier if the **note explicitly requires a stricter medium rule** *and* the current medium rule would assign a **different tier** on a realistically confirmed evaluation (show the scenario).

4. **Nested `{ "min_from_set": … }` objects inside `required_any`.**  
   **Unsupported.** `required_any` accepts **lists of signal ID strings** only; dict groups are skipped. Do not suggest nested `min_from_set` in `required_any` — suggest explicit signal-id groups or a single top-level `min_from_set`.

5. **`required_all: ["sig_X"]` combined with another path via OR.**  
   **`required_all` is AND**, not OR. Do not use it to express “sig_05 alone **or** all primaries” — use `required_any` with explicit groups.

6. **Invalid nested `min_from_set` inside `required_any`** (e.g. forest_degradation-style “2-of-3 OR sig_05 alone” encoded as dict branches).  
   Mark as needing **`required_any`: `[["sig_01","sig_02"], …, ["sig_05"]]`** or note/prose change — not nested objects.

### Policy syntax quick reference

| Construct | Meaning | OR support? |
|-----------|---------|-------------|
| `confirm_when.min_from_set` | ≥ `min` TRUE **confirms** from listed ids | One set per `confirm_when` |
| `confirm_when.required_all` | Every listed id must be TRUE | AND only |
| `confirm_when.required_any` | Each group = list of ids, all in group TRUE; **OR** across groups | OR, but **not** “k-of-n” inside a group |
| `confidence_when[]` | First matching rule wins (after confirm) | Same rule types as above |

---

## D1 — Expression ↔ qualitative prose (core semantic check)

**Skip signals without `condition.expression`.** Signals with `condition.type: qualitative` (and no expression) that reference `missing_variable` keys answered via MCQ follow-ups are **intentionally unevaluated server-side** — do not report them, even as informational findings.

For **each remaining active signal** with `condition.expression`, read the expression and compare to:

1. **`condition.qualitative_description`** — thresholds, variables named, direction of comparison (>, <, in [...])
2. **`explanation`** — same consistency
3. **`overall_reasoning_note`** — when the note references this signal, does it describe what the expression actually checks?
4. **`severity` / `direction`** — amplifier vs primary confirm matches prose role

**This is the main value-add.** Example findings:
- Prose says “SOGE above 70%” but expression uses `> 90`
- Prose says “alluvial fraction below 20%” but expression checks wrong ACWADAM key
- Note lists sig_03 as prerequisite but expression treats it as optional amplifier

Only flag D1e (unregistered identifier) if the name is **absent** from the prompt catalog.

Registry reference (do not re-litigate if already documented in prompt):
- Time-series vars: `[-1]` / `.get('kharif')` valid where listed
- `aquifer_class`: categorical string scalar (`==` / `in`)
- `acwadam_class_percent`: dict with lowercase ACWADAM keys
- `soge_dev_percent`, `soge_class_name`: **static block-level snapshot** — not a time series

On mismatch: suggest `suggested_patch` correcting expression and/or prose/severity/direction.

---

## D2 — Temporal aggregation (time-series variables only)

Apply **only** when **both** are true:
1. The expression uses a **time-series** variable from the prompt list (`annual_*`, `drought_weeks_*`, `delta_g_mm`, etc.)
2. Prose **explicitly** requires multi-year persistence (“chronic”, “recurrent”, “over several years”, “sustained trend”)

Do **not** apply D2 to static variables (`soge_dev_percent`, `soge_class_name`, `nrega_swc_count`, distances, etc.). A note mentioning “multi-year trends are more reliable” does **not** require adding temporal guards to unrelated static SOGE checks — flag that as a **note/policy** nuance (prefer sig_02 trend signals), not a D2 error on sig_01.

When D2 applies, suggest `mean_*`, `trend_*`, `drought_*_return_period`, or `max(var)` — not stripping valid `[-1]`.

---

## D4 — Missing-variable questions (MCQ)

For each `missing_variable_questions[]` with `response_type: mcq`:

- `question_to_user` and `how_answer_updates_diagnosis` align with pathway prose
- Choice labels match `how_answer_updates_diagnosis` semantics
- `choices[].effects.signals[].result` direction matches prose (confirm vs rule out)
- **Stay within the MCQ schema** — do not invent bounds fields or restructure choices

### `normalized` vs `effects` (do not conflate)

**Signal confirmation at runtime uses `choices[].effects.signals[].result` first** (keyed by `choice_id`). When `effects` is present and specifies `result`, that is authoritative — do not second-guess it from `normalized.present`.

**`normalized` is a structured mirror of the answer** for mode validation, LLM context, and legacy prose-matching fallbacks — not a duplicate confirm gate.

| `question_mode` | `normalized.present` | Meaning |
|-----------------|----------------------|---------|
| **`magnitude`** (e.g. `borewell_density`, `household_income_inr`, `migrant_household_percent`) | **Must be `true` on every choice** (schema audit rule) | User gave a **graded magnitude answer**; level is in `band` (low/moderate/high). **`present: true` does NOT mean the pathway-stress condition is confirmed.** |
| **`trend`** (e.g. `annual_well_depth_m`) | `false` on stable/absent; `true` on worsening | Whether the reported change/feature is present |
| **`presence_graded`** / **`presence_binary`** (e.g. `groundwater_salinity`) | `false` when feature absent; `true` when present | Whether the feature exists; `band` grades severity if present |

**Do NOT flag** `present: true` on a low-band magnitude choice (e.g. borewell_density `few`) when `effects` correctly sets `result: false`. That pattern is **correct**: `band: low` + `present: true` + `effects → false` means “answered low density; does not confirm high-density stress.”

**Do NOT suggest** changing magnitude-mode choices to `present: false` — it fails `audit_mcq_normalized.py` and breaks template consistency with `runtime/services/follow_up_mcq.py`.

On mismatch: suggest corrected prose/effects within schema.

---

## D5 — Schema and envelope

Note schema issues only if not already in deterministic preflight rows.

---

## Output rules

1. Set `overall_score` from semantic dimensions (D3/D1/D4); do not fail a card solely for registry/type false positives.
2. Each actionable issue in `findings[]` with stable `issue_id`.
3. `suggested_patch` as partial objects; D3 policy under `suggested_patch.confirmation_policy`.
4. Prefer **zero findings** over speculative warnings when prose and expressions align.
5. Do not duplicate preflight unless adding interpretation the preflight cannot make.
6. **Never emit info-only “for completeness” findings** (e.g. noting a qualitative signal has no expression). Omit such issues entirely.
