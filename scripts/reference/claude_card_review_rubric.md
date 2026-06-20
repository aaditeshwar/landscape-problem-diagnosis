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

---

## D3 — Confirmation policy ↔ overall_reasoning_note (most important)

Compare `confirmation_policy` to `overall_reasoning_note`:

- Minimum confirm count (`min_confirms_true`, `min_from_set.min`) matches prose (“at least two primary signals”)
- Primary signal set matches note (confirm signals, not amplifiers)
- Amplifiers (`direction: amplifies`) must not confirm alone
- `confidence_when` tiers match note (high confidence needs more signals than medium)
- Required AND groups in prose reflected in `required_all` / `required_any`

On mismatch: prefer fixing `confirmation_policy` to match correct prose. Provide full `suggested_patch.confirmation_policy` (v1 schema). Only suggest note edits if prose is wrong.

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
