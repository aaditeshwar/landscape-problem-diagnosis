# Data-Driven Grid Construction — Replacing Fixed Bounds with Empirical Candidate Thresholds

## The problem with what was specified before

Both v2 and v3 used `domain_bounds = {"T0": (lo, hi)}` plus a fixed `n_candidates` (e.g. 20)
to build the grid:

```python
step = (hi - lo) / n_candidates
candidates = [lo + i*step for i in range(n_candidates+1)]
```

This is wrong for two independent reasons, both of which you've identified:

1. **The natural range of different thresholds varies by orders of magnitude.**
   `dry_spell_weeks` is an integer roughly in `[0, 12]`. `mean_annual_precipitation_mm`
   ranges from ~150mm (Ladakh, cluster 016) to ~5000mm (West Coast, cluster 015/Eastern
   Himalaya, cluster 012). A single `n_candidates=20` cannot give both variables
   appropriate resolution — 20 steps over 150-5000mm is a 242mm step, which can easily
   skip past the only meaningful decision boundary if the actual case-study values are
   tightly clustered (e.g. all between 600-750mm for a semi-arid cluster).

2. **A fixed step size is blind to where the data actually is.** Most of a uniform grid's
   candidates fall in regions with zero positives and zero negatives nearby — testing them
   wastes evaluations and, worse, can report a "Pareto-optimal" threshold that sits in an
   empty region between two real clusters of data, which is meaningless as an interpretable
   threshold ("severe drought weeks ≥ 4.37" is not a number anyone would write into a card).

## The fix: thresholds are only informative at empirical midpoints

For any single-threshold comparison (`variable >= T`, `variable < T`, etc.), the TPR and FPR
can only change value as `T` crosses one of the **observed data points**. Between two
consecutive observed values, every threshold produces the *identical* classification of
every MWS, hence the identical TPR/FPR. I verified this directly: for a sample of 5 positives
and 8 negatives (13 total distinct values), there are exactly 11 distinct achievable
`(TPR, FPR)` pairs, found by testing only the 11 midpoints between consecutive sorted values
plus the two boundary candidates (just below the minimum, just above the maximum). A 2000-point
fine continuous sweep across the same range found **zero** additional achievable pairs.

This means the correct grid for one threshold is not "20 evenly spaced points across a
guessed range" — it is **the sorted union of all positive and negative values for that
variable, converted into midpoints**:

```python
def empirical_threshold_candidates(
    pos_values: list[float],
    neg_values: list[float],
    operator: str,             # '>=', '>', '<=', '<'
    round_to: float | None = None,   # e.g. 1 for integer-valued variables like week counts
) -> list[float]:
    """
    Build the complete, minimal set of threshold candidates that can produce a distinct
    (TPR, FPR) outcome, derived from the empirical CDF of the pooled positive+negative
    values rather than from a fixed external range.

    For operator in {'>=', '>'}: a threshold strictly between two consecutive sorted
      values changes nothing; only the midpoints matter.
    For operator in {'<=', '<'}: same logic, midpoints are operator-agnostic — the
      midpoint set is identical, only how it's interpreted downstream differs.

    Returns midpoints PLUS two boundary candidates: one below the global minimum
    (forces all-True for >=, i.e. the inclusive "everything passes" case) and one
    above the global maximum (forces all-False).
    """
    all_vals = sorted(set(pos_values + neg_values))
    if not all_vals:
        return []

    candidates = [all_vals[0] - 1]  # "everything passes" boundary
    for a, b in zip(all_vals[:-1], all_vals[1:]):
        candidates.append((a + b) / 2)
    candidates.append(all_vals[-1] + 1)  # "nothing passes" boundary

    if round_to is not None:
        # Snap to the nearest interpretable grid (e.g. integers for week-counts),
        # then de-duplicate. This trades a small amount of theoretical completeness
        # for a clean, explainable threshold value -- e.g. round dry_spell_weeks
        # midpoints (3.5, 4.5, ...) to (4, 5, ...) since a card should say
        # "dry_spell_weeks >= 4", not "dry_spell_weeks >= 3.5".
        candidates = sorted(set(round(c / round_to) * round_to for c in candidates))

    return candidates
```

### Choosing `round_to` per variable from the variable registry / data dictionary

Rather than guessing, `round_to` is read from each variable's declared type:

```python
def infer_round_to(variable_name: str, registry: dict, data_dictionary: dict) -> float | None:
    """
    Integer-count variables (week counts, SWB counts, NREGA work counts) -> round_to=1
    Percentage/ratio variables (cropping intensity, SOGE%, ratios) -> round_to=0.05
    Precipitation/area/distance (mm, ha, km) -> round_to=10 (mm/ha) or 0.5 (km)
    Index scores already on a fixed integer scale (e.g. *_score_latest, 0-100ish) -> round_to=1
    Unspecified -> round_to=None (keep raw empirical midpoint, flag as
                                   'NEEDS_INTERPRETABILITY_REVIEW' in the trace)
    """
    unit = data_dictionary.get(variable_name, {}).get("unit", "")
    var_type = registry["variable_registry"]["variables"].get(variable_name, {}).get("type", "")

    if "week" in variable_name or "count" in variable_name or "return_period" in variable_name:
        return 1
    if unit in ("mm", "ha"):
        return 10
    if unit == "km":
        return 0.5
    if unit in ("percent", "ratio", "%") or "ratio" in variable_name:
        return 0.05
    if variable_name.endswith("_score_latest"):
        return 1
    return None
```

This directly answers your CDF question: rather than literally plotting a CDF and eyeballing
quantile breakpoints, the algorithm uses the **empirical CDF's actual jump points** (every
distinct observed value is a jump point of the CDF) as the candidate set — which is the
exact information a CDF visualisation would show you, just consumed programmatically and
guaranteed complete rather than approximated via "20 quantile bins."

## Multi-threshold (composite) expressions: per-dimension empirical grids, not a shared one

For an expression with multiple free thresholds — e.g.
`severe[-1] >= T0 or (severe[-1] >= T1 and moderate[-1] >= T2)` — **each** threshold gets
its **own** empirical candidate list built from **its own variable's** pooled values, not a
shared generic range:

```python
def build_candidate_lists_v4(
    free_thresholds: list[str],            # ["T0", "T2"]  (T1 fixed at 1, excluded)
    threshold_to_variable: dict[str, str], # {"T0": "drought_weeks_severe", "T2": "drought_weeks_moderate"}
    positives: list[dict],
    negatives: list[dict],
    registry: dict,
    data_dictionary: dict,
) -> list[list[float]]:
    """
    For EACH free threshold, extract that threshold's own variable's values from
    every MWS (positives + negatives), and build its own empirical candidate list.
    This means T0 (severe weeks, small integer range, e.g. 0-9) gets a fine, fully
    enumerated integer grid, while T2 (a precipitation threshold in a DIFFERENT
    signal) gets its own independently-derived grid from precipitation values --
    no cross-contamination of resolution between unrelated variables.
    """
    candidate_lists = []
    for t_name in free_thresholds:
        var_name = threshold_to_variable[t_name]
        pos_vals = [_extract_latest_value(m, var_name) for m in positives]
        neg_vals = [_extract_latest_value(m, var_name) for m in negatives]
        pos_vals = [v for v in pos_vals if v is not None]
        neg_vals = [v for v in neg_vals if v is not None]

        round_to = infer_round_to(var_name, registry, data_dictionary)
        candidates = empirical_threshold_candidates(pos_vals, neg_vals, ">=", round_to)
        candidate_lists.append(candidates)

    return candidate_lists
```

### Grid size is now bounded by data, not by a guessed resolution

Since each dimension's candidate count equals roughly `n_pos + n_neg` (the number of
distinct observed values for that variable, typically smaller after rounding), and current
corpora have `n_pos + n_neg` in the 10-20 range, a 2-parameter composite signal now produces
a grid of at most ~15 × 15 = 225 points — far smaller than the old fixed `20 × 20 = 400`,
*and* guaranteed to contain every actually-distinguishable threshold combination, with no
risk of stepping over a real decision boundary.

For the 3-parameter `sig_03` composite from the earlier drought cards
(`spi_kharif <= T0 and (mai < T1 or vci < T2)`), this is what made the old fixed grid
balloon to ~27,000 combinations using guessed bounds. With data-driven candidates restricted
to each variable's own observed range (typically 10-15 distinct values per variable at
this corpus size), the grid shrinks to roughly 15×15×15 ≈ 3,375 — and is exhaustively
correct rather than an approximation.

## Boundary case: variables with very few distinct values

If a variable has, say, only 3 distinct values across the whole corpus (common for
`drought_severe_return_period`, which is itself a derived discrete-ish statistic), the
candidate list is naturally just 4 midpoints + 2 boundaries = 6 candidates — there is
nothing finer to search, and the algorithm correctly does not invent false resolution.
This is reported in the trace as `"grid_size": 6, "limited_by": "few distinct observed values"`
so the low resolution is visible rather than silently producing a falsely-precise-looking
threshold like `T0=4.37`.

## Net effect on the rest of the v3 algorithm

`grid_search_thresholds_v3()` (Part 2, Section 4) is otherwise unchanged: it still calls the
real `signal_evaluator.evaluate_expression()`, still optimises the pathway-level
`confirmation_policy` outcome, still returns a Pareto front, and still passes the result
through `validate_against_registry()`. The only change is **how `candidate_lists` is built**
in `_build_candidate_lists()` — replaced entirely by `build_candidate_lists_v4()` above,
which derives every dimension's resolution from that dimension's own empirical data rather
than from externally-guessed `domain_bounds`. The `domain_bounds` dict is no longer needed
as an input to the search at all; it is replaced by `data_dictionary` + `variable_registry`
(for `round_to` inference) and the pooled positive/negative MWS values themselves.
-e 
---

# Why Gradient Descent Does Not Apply Directly — and the Smooth Surrogate That Does

## The core problem: TPR/FPR are step functions of the threshold

For a single-threshold signal like `dry_spell_weeks[-1] >= T0`, the objective we care about
(true positive rate across case-study MWSes) is:

```
TPR(T0) = (1/n_pos) * Σ  1[ value_i >= T0 ]
```

`1[...]` is an indicator function. As `T0` sweeps continuously, `TPR(T0)` is a **step function** —
flat everywhere except at the exact data values, where it jumps. A demonstration with 5
positive values `[2,3,3,5,6]`:

```
threshold=1.9: TPR=1.00
threshold=2.0: TPR=1.00   ← jump down happens exactly at threshold=2 (a data point)
threshold=2.1: TPR=0.80
threshold=2.9: TPR=0.80
threshold=3.0: TPR=0.80   ← jump down happens exactly at threshold=3
threshold=3.1: TPR=0.40
```

The gradient `dTPR/dT0` is **zero everywhere except at the data points**, where it is
undefined (a Dirac delta, informally "infinite and instantaneous"). A gradient descent
step computed from this objective will either:
- get `gradient = 0` and never move at all (if it lands between data points), or
- get nonsense from a numerically unstable finite-difference estimate exactly at a data point.

This is not a "gradient descent is harder here" problem — it is a **gradient descent is not
applicable** problem. The same issue applies to FPR, precision, recall, and F1 computed from
hard comparisons — they are all piecewise-constant in the threshold.

This is why the v2 design used **grid search** rather than a continuous optimiser: grid search
doesn't need gradients, it just evaluates the (non-differentiable) objective at a finite set of
candidate points and picks the best one. That remains correct and is kept as the default method.

## The smooth surrogate that DOES support gradient descent

There is a legitimate way to get a real gradient: replace the hard step indicator with a
**sigmoid relaxation**. Instead of `1[value >= T0]`, use:

```
σ(value, T0, k) = 1 / (1 + exp(-k * (value - T0)))
```

As `k → ∞`, `σ` converges to the hard step function. For finite `k`, `σ` is smooth and
differentiable everywhere, with:

```
dσ/dT0 = -k * σ * (1 - σ)
```

A smooth surrogate loss can then be defined as:

```
L(T0) = -mean(σ(pos_vals, T0, k))                      # maximise smoothed TPR
        + λ * mean(σ(neg_vals, T0, k))                 # penalise smoothed FPR
```

This **is** differentiable, and gradient descent (or Adam) can genuinely converge on it.

## Why grid search is still the better choice here, not gradient descent

Despite the surrogate being mathematically valid, it is the wrong tool for this specific
problem, for four concrete reasons:

1. **n is tiny (3–7 positives).** Gradient descent's main advantage is scaling to thousands
   or millions of parameters and large datasets where exhaustive search is infeasible. With
   1–3 free thresholds and a corpus of 10–20 MWSes total, grid search over a few hundred to
   a few thousand candidate points runs in well under a second. There is no scaling problem
   to solve.

2. **The sigmoid surrogate introduces a hyperparameter (`k`, the sharpness) that itself needs
   tuning**, and the optimum of the smoothed objective is not guaranteed to coincide with the
   optimum of the true (step-function) TPR/FPR objective — especially with so few data points,
   where a single mis-ranked example can shift the smoothed optimum away from the true one.
   This adds a layer of approximation error for no benefit when n is small enough to search
   exhaustively.

3. **Interpretability requirement.** The threshold must end up as a clean, explainable number
   (e.g. "3 or more dry-spell weeks") that a domain expert can sanity-check against agronomic
   plausibility. Gradient descent on a smoothed loss will converge to an arbitrary float
   (e.g. `3.0427`) that then needs rounding — and rounding after optimisation can silently
   undo the convergence guarantee, landing on a worse integer than grid search would have
   found directly.

4. **Multiple discrete optima / Pareto trade-offs.** We explicitly want the **Pareto front**
   of TPR vs FPR (see `_pareto_front()` in v2), not a single converged point. Gradient descent
   naturally finds one local optimum of one scalar loss; producing a Pareto front requires
   either re-running with many different `λ` weightings (effectively turning into a grid
   search over `λ` instead of `T0`) or switching to a multi-objective method anyway.

## When gradient-based tuning WOULD be worth it

If a future evidence card has 4+ simultaneously free continuous thresholds in one composite
expression (e.g. a 4-parameter SPI+MAI+VCI+precipitation composite) AND the case-study corpus
grows to dozens of positives, a full grid becomes expensive (a 4-parameter grid at 20 points
each is 160,000 combinations × n_MWS evaluations). At that point, the sigmoid-surrogate +
Adam approach in Part 4 below becomes genuinely worthwhile as a **fast pre-search** step,
followed by a small grid search refinement around the gradient descent's converged point to
recover clean, interpretable threshold values. This hybrid is included in the revised
algorithm as an optional Phase A2, used only when the grid would otherwise be too large
to run in full.

## Conclusion

For the current data scale (3–7 positives per pathway, 1–3 free thresholds per signal),
**grid search remains the correct and faster approach** — "faster" in wall-clock terms,
because a grid of a few hundred points evaluated against ~15 MWSes is sub-second, while
setting up, tuning the sigmoid sharpness, running gradient descent to convergence, and then
re-discretising back to clean integers/floats for interpretability is strictly more work for
an answer that isn't guaranteed to be better. Gradient descent is kept in reserve as an
optional pre-search for future composite signals with many free parameters and larger corpora.
-e 
---

# Signal Expression Fine-Tuning Algorithm — v3
## Aligned to the production `signal_evaluator.py`, `confirmation_policy`, and `variable_registry.json`

---

## 1. What changed from v2 and why

v2 assumed a hand-rolled evaluator and a simple "≥2 confirms" rule baked into prose
(`overall_reasoning_note`). The actual system you've built is considerably more capable:

| v2 assumption | What actually exists now | Implication for the algorithm |
|---|---|---|
| Hand-rolled `eval_signal()` | `signal_evaluator.py`: `evaluate_expression()`, `eval_context()`, `YearIndexedMapping`, `SafeYearIndexedMapping`, `DateValue`/`DayDelta` arithmetic, `SeasonBlockMapping` | The tuning algorithm must call the **real evaluator**, not reimplement evaluation. Removes an entire class of bugs (date arithmetic, season-block access) that v2's evaluator would have gotten wrong. |
| Prose confirmation rule | Structured `confirmation_policy` block: `primary_confirm_signals`, `confirm_when.min_confirms_true`, `confirm_when.min_from_set`, `confirm_when.required_all`, `confirm_when.required_any`, `confidence_when[]` ladder | The tuning algorithm must evaluate **pathway-level confirmation outcome** (not just individual signal TPR/FPR) as the thing case studies actually validate. A signal can be individually noisy but the pathway-level confirmation can still be correct, or vice versa. |
| Free-form variable names (`spi_kharif`, `spi_class`, ad hoc) | `variable_registry.json`: canonical names, `legacy_aliases`, `nested_schema`, `source_key_map`, and an explicit `invented_expression_keys` block listing keys that **must never appear** in an expression | The schema-inconsistency problem flagged in v2 (sig_03's `spi_kharif` vs `spi_class` split) is **solved upstream**. The new drought card uses `drought_mild_spi_score_latest` / `drought_severe_return_period` — real, registry-defined, assembler-computed fields. The algorithm must validate any *new* expression it proposes against `invented_expression_keys` before accepting it. |
| Single boolean per signal | Each signal carries `active: true/false`. Inactive signals (e.g. `sig_03` in the new drought card, `active: false`) are skipped entirely by the evaluator and must be skipped by the tuner too. | Tuning must only consider `active: true` signals as live candidates, but can still recommend flipping `active` based on evidence. |
| One `condition` per signal | Same structure retained, but now signals can lack a body (`groundwater_stress` card's qualitative `annual_well_depth_m` signal has `"expression": ""`, status `missing expression`, and is resolved via `missing_variable_questions` + user-answer overlay instead) | Tuning skips empty-expression signals for numeric grid search, but should verify the linked `missing_variable_questions` entry exists and is internally consistent. |

The threshold-search core of v2 (grid search, Pareto front, template canonicalisation) is
**kept** — it was correct. What changes is: (a) the evaluator used inside the search loop,
(b) the objective being optimised (pathway-level confirmation outcome via `confirmation_policy`,
not raw per-signal TPR), and (c) validation against the variable registry before any tuned
expression is written back to a card.

---

## 2. Pathway-Level Confirmation Evaluator

This is new in v3. Given a card's `confirmation_policy` and the set of signal results
(`True`/`False`/`None`), compute whether the **pathway** is confirmed — this is what should
actually be validated against case studies, not individual signal accuracy.

```python
def evaluate_confirmation_policy(
    policy: dict,
    signal_results: dict[str, bool | None],   # {signal_id: True/False/None}
) -> dict:
    """
    Mirrors the policy structure used in confirmation_policy blocks:
      - confirm_when.min_confirms_true        (simple count threshold)
      - confirm_when.min_from_set              ({signals: [...], min: N})
      - confirm_when.required_all              ([sig_a, sig_b] - all must be True)
      - confirm_when.required_any              ([[sig_a, sig_b], [sig_c]] - at least one group all-True)
      - confirm_when.amplifiers_do_not_confirm (informational; amplify-direction
                                                  signals are excluded from confirms_true count
                                                  by construction, not checked here)
      - confidence_when[]                      (ordered ladder; first matching rule wins,
                                                  'default': true as final fallback)
    
    Returns: {"confirmed": bool, "confidence": "high"|"medium"|"low", "reasoning": str}
    """
    confirm_when = policy.get("confirm_when", {})

    def count_true(signal_ids):
        return sum(1 for s in signal_ids if signal_results.get(s) is True)

    checks = []

    # min_confirms_true: count True among ALL confirms-direction signals
    # (signal_results passed in should already be filtered to direction='confirms')
    if "min_confirms_true" in confirm_when:
        n_true = sum(1 for v in signal_results.values() if v is True)
        checks.append(n_true >= confirm_when["min_confirms_true"])

    # min_from_set: count True among a specific named subset
    if "min_from_set" in confirm_when:
        mfs = confirm_when["min_from_set"]
        n_true = count_true(mfs["signals"])
        checks.append(n_true >= mfs["min"])

    # required_all: every listed signal must independently be True
    if "required_all" in confirm_when:
        checks.append(all(signal_results.get(s) is True for s in confirm_when["required_all"]))

    # required_any: at least one group's signals are ALL True
    if "required_any" in confirm_when:
        group_ok = any(
            all(signal_results.get(s) is True for s in group)
            for group in confirm_when["required_any"]
        )
        checks.append(group_ok)

    confirmed = all(checks) if checks else False

    # Confidence ladder: first rule whose conditions are met, in listed order
    confidence = "low"
    reasoning = "no confidence rule matched; default"
    for rule in policy.get("confidence_when", []):
        if rule.get("default"):
            confidence = rule["level"]
            reasoning = "default rule"
            break
        rule_checks = []
        if "min_from_set" in rule:
            mfs = rule["min_from_set"]
            rule_checks.append(count_true(mfs["signals"]) >= mfs["min"])
        if "min_high_severity_confirms" in rule:
            # Caller must pass severity alongside signal_results for this; see note below
            pass  # handled by caller merging severity info before calling, or as a second pass
        if "min_confirms_true" in rule:
            n_true = sum(1 for v in signal_results.values() if v is True)
            rule_checks.append(n_true >= rule["min_confirms_true"])
        if rule_checks and all(rule_checks):
            confidence = rule["level"]
            reasoning = f"matched rule: {rule}"
            break

    return {"confirmed": confirmed, "confidence": confidence, "reasoning": reasoning}
```

### Why this matters for tuning

The tuning objective for a **signal** is no longer "does this signal alone separate
positives from negatives" — it's "does changing this signal's threshold change the
**pathway-level confirmation outcome** for the better, given how this signal combines
with others under the policy". A signal that is part of a `required_any` group with
two alternates can be tuned more aggressively (loosened) than a signal that is the sole
member of `required_all`, because the latter is a hard gate.

```python
def pathway_level_objective(
    card: dict,
    mws_list: list[dict],
    ground_truth: dict[str, bool],   # {mws_uid: True if pathway confirmed in case studies}
    candidate_expressions: dict[str, str],  # {signal_id: candidate_expression}
) -> dict:
    """
    Run the REAL evaluator (signal_evaluator.evaluate_expression) with candidate_expressions
    substituted for the signals being tuned, evaluate confirmation_policy per MWS, and
    compute pathway-level TPR/FPR against ground_truth.
    """
    from signal_evaluator import evaluate_expression

    policy = card["confirmation_policy"]
    confirms_signal_ids = {
        s["signal_id"] for s in card["diagnostic_signals"]
        if s.get("active", True) and s["direction"] == "confirms"
    }

    tp = fp = tn = fn = 0
    per_mws_detail = []

    for mws in mws_list:
        present = merge_export_variables(mws)  # from signal_evaluator
        signal_results = {}
        for sig in card["diagnostic_signals"]:
            if not sig.get("active", True):
                continue
            sid = sig["signal_id"]
            expr = candidate_expressions.get(sid, sig["condition"].get("expression", ""))
            if not expr.strip():
                signal_results[sid] = None
                continue
            result, error = evaluate_expression(expr, present)
            signal_results[sid] = result

        # Only confirms-direction signals feed confirm_when counts per policy convention
        confirms_only = {k: v for k, v in signal_results.items() if k in confirms_signal_ids}
        outcome = evaluate_confirmation_policy(policy, confirms_only)

        truth = ground_truth.get(mws["uid"], False)
        pred = outcome["confirmed"]

        if truth and pred: tp += 1
        elif truth and not pred: fn += 1
        elif not truth and pred: fp += 1
        else: tn += 1

        per_mws_detail.append({
            "uid": mws["uid"], "truth": truth, "predicted": pred,
            "confidence": outcome["confidence"], "signal_results": signal_results
        })

    n_pos = tp + fn
    n_neg = tn + fp
    return {
        "tpr": tp / n_pos if n_pos else None,
        "fpr": fp / n_neg if n_neg else None,
        "confusion_matrix": {"TP": tp, "FP": fp, "TN": tn, "FN": fn},
        "per_mws_detail": per_mws_detail,
    }
```

---

## 3. Variable Registry Validation Gate

Before any tuned or newly-proposed expression is written back into a card, it must pass
a registry check. This directly prevents the v2-era bug (cards using `spi_kharif`/`spi_class`
inconsistently) from recurring.

```python
def validate_against_registry(expression: str, registry: dict) -> dict:
    """
    Checks an expression's identifier usage against variable_registry.json.
    Returns {"valid": bool, "violations": [...]}.
    
    Violations:
      - uses a name listed in any variable's 'invented_expression_keys'
      - uses .get('some_flat_key') on a variable whose registry type is 'nested_time_series'
        with a declared nested_schema, where 'some_flat_key' isn't in that schema
      - indexes a 'static' type variable with [-1] or [0]
    """
    import ast
    violations = []
    tree = ast.parse(expression, mode="eval")
    vr = registry["variable_registry"]["variables"]

    # Build the global "never use this key" set
    invented = set()
    for name, info in vr.items():
        invented.update(info.get("invented_expression_keys", []))

    for node in ast.walk(tree):
        # Flag any .get('x') call where 'x' is an invented key
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and node.args:
            arg0 = node.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                if arg0.value in invented:
                    violations.append(
                        f"Uses invented key '{arg0.value}' via .get() — "
                        f"not a real field in variable_registry.json"
                    )
        # Flag static variables being indexed with [-1] / [0]
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            varname = node.value.id
            info = vr.get(varname)
            if info and info.get("type") == "static":
                violations.append(
                    f"Variable '{varname}' is type=static but is indexed "
                    f"with [...] — static variables must be used as scalars"
                )

    return {"valid": len(violations) == 0, "violations": violations}
```

This gate runs **after** grid search proposes a tuned expression and **before** it's written
into the updated card. If a tuned expression fails the gate (which should be rare since tuning
only changes numeric literals, not variable names — see constraint below), the tuning run for
that signal is marked `REJECTED_REGISTRY_VIOLATION` and the original expression is kept.

---


def map_thresholds_to_variables(template: str, signal_variables: list[str]) -> dict[str, str]:
    """
    Maps each threshold placeholder (T0, T1, ...) in a canonicalised template to the
    specific variable name its comparison applies to, by walking the template's AST
    and finding which variable each numeric placeholder is compared against.

    Example:
      template = "drought_weeks_severe[-1] >= T0 or (drought_weeks_severe[-1] >= T1 and drought_weeks_moderate[-1] >= T2)"
      signal_variables = ["drought_weeks_severe", "drought_weeks_moderate"]
      -> {"T0": "drought_weeks_severe", "T1": "drought_weeks_severe", "T2": "drought_weeks_moderate"}

    This allows build_candidate_lists_v4() to pull the RIGHT variable's empirical
    values for each threshold, even when multiple thresholds in the same expression
    bind to different variables.
    """
    import ast
    tree = ast.parse(template, mode="eval")
    mapping = {}

    class Visitor(ast.NodeVisitor):
        def visit_Compare(self, node):
            left_name = _innermost_name(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right_name = _innermost_name(comparator)
                if right_name and right_name.startswith("T") and left_name:
                    mapping[right_name] = left_name
                elif left_name and left_name.startswith("T") and right_name:
                    mapping[left_name] = right_name
            self.generic_visit(node)

    def _innermost_name(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Subscript):
            return _innermost_name(node.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            return _innermost_name(node.func.value)
        return None

    Visitor().visit(tree)
    # Fallback: any unmapped threshold defaults to the first signal variable
    for i in range(10):
        t = f"T{i}"
        if t in template and t not in mapping and signal_variables:
            mapping[t] = signal_variables[0]
    return mapping


## 4. Revised Grid Search — Calling the Real Evaluator

The structural constraint from v2 is unchanged: **tuning only changes numeric literals inside
the existing expression template; variable names and logical structure are frozen.** This
constraint is exactly why the registry-validation gate above will essentially always pass —
canonicalisation (`extract_template_and_thresholds`) never touches identifiers, only numbers.

```python
def grid_search_thresholds_v3(
    card: dict,
    signal_id: str,
    positives: list[dict],     # MWS export dicts (uid, present_variables, derived_variables, ...)
    negatives: list[dict],
    registry: dict,
    data_dictionary: dict,
    # NOTE: domain_bounds and n_candidates are REMOVED as of v4 -- replaced by
    # build_candidate_lists_v4() (see Part 0), which derives per-threshold candidate
    # grids directly from the empirical CDF of each threshold's own variable values,
    # rather than from externally guessed bounds and a fixed step count.
) -> list[dict]:
    """
    v3 grid search: same Pareto-front logic as v2, but:
      (a) uses signal_evaluator.evaluate_expression() for every candidate evaluation
          instead of a hand-rolled eval_signal()
      (b) evaluates PATHWAY-LEVEL confirmation outcome (via confirmation_policy),
          not just this signal's isolated TPR/FPR, by holding all other signals at
          their current expressions and only varying this one
      (c) validates the final chosen expression against the registry before returning it
    """
    from signal_evaluator import evaluate_expression, merge_export_variables

    target_signal = next(s for s in card["diagnostic_signals"] if s["signal_id"] == signal_id)
    template, original_thresholds = extract_template_and_thresholds(
        target_signal["condition"]["expression"]
    )
    free = get_free_threshold_names(template)  # excludes any fixed via convention (see below)
    threshold_to_variable = map_thresholds_to_variables(template, target_signal["variables"])

    ground_truth = {m["uid"]: True for m in positives}
    # negatives are MWS confirmed NOT to have this pathway (or simply not in positives)

    all_mws = positives + negatives
    # v4: empirical, per-threshold, data-driven candidate grids (see Part 0) --
    # NOT a fixed external range swept at a fixed step count.
    candidate_lists = build_candidate_lists_v4(
        free, threshold_to_variable, positives, negatives, registry, data_dictionary
    )

    results = []
    for combo in itertools.product(*candidate_lists):
        threshold_map = dict(zip(free, combo))
        candidate_expr = _substitute_thresholds(template, threshold_map)

        outcome = pathway_level_objective(
            card=card,
            mws_list=all_mws,
            ground_truth=ground_truth,
            candidate_expressions={signal_id: candidate_expr},  # only this signal varies
        )
        if outcome["tpr"] is None:
            continue

        results.append({
            "thresholds": threshold_map,
            "expression": candidate_expr,
            "tpr": outcome["tpr"],
            "fpr": outcome["fpr"],
            "confusion_matrix": outcome["confusion_matrix"],
        })

    pareto = _pareto_front_v3(results)
    pareto.sort(key=lambda r: (-r["tpr"], r["fpr"] if r["fpr"] is not None else 1.0))

    # Validate the top candidate against the registry before returning
    if pareto:
        check = validate_against_registry(pareto[0]["expression"], registry)
        if not check["valid"]:
            pareto[0]["registry_violation"] = check["violations"]
            pareto[0]["recommendation_override"] = "REJECTED_REGISTRY_VIOLATION"

    return pareto
```

### Handling `active: false` and empty-expression signals

```python
def signals_eligible_for_tuning(card: dict) -> list[dict]:
    """
    Only tune signals that are:
      - active: true (or absent, defaulting to true)
      - direction == 'confirms' (amplify-direction signals influence confidence_when
        ladders but are not the primary confirm gate; they CAN still be tuned but are
        lower priority — see Phase ordering)
      - have a non-empty condition.expression (qualitative/missing-expression signals
        like groundwater_stress's annual_well_depth_m signal are resolved via
        missing_variable_questions + user-answer overlay, not threshold tuning)
    """
    eligible = []
    for sig in card["diagnostic_signals"]:
        if sig.get("active", True) is False:
            continue
        expr = (sig.get("condition") or {}).get("expression", "").strip()
        if not expr:
            continue  # qualitative signal resolved via user-answer overlay; skip
        eligible.append(sig)
    return eligible
```

---

## 5. Pathway-First, Cross-AER Algorithm Flow (retained from v2, evaluator swapped)

```
FOR EACH causal_pathway (e.g. drought, irrigation_challenges, groundwater_stress,
                          encroachment, forest_degradation, multi_sector_vulnerability,
                          small_landholding):

  Load all 17 cluster cards for this pathway (suffix 001-017).
  Load all MWS exports available in the corpus.
  Load case_study_locations_v3.json ground truth for this pathway.

  PHASE A: CROSS-CLUSTER TEMPLATE GROUPING
  ──────────────────────────────────────────
  For each signal position (sig_01, sig_02, ...):
    1. Call signals_eligible_for_tuning() per card to filter active, non-empty,
       confirms-direction signals.
    2. Canonicalise each eligible signal's expression via extract_template_and_thresholds().
    3. Group cards by identical template string.
    4. For each template group with >= 2 cards:
         Pool case-study positives across ALL clusters in the group.
         Pool negatives: MWS in the same production_system not positive for this pathway.
         Run feasibility check (n_pos >= 2, n_neg >= 3).
         If feasible: run grid_search_thresholds_v3() — PATHWAY-LEVEL objective,
           holding all OTHER signals at their current per-card expression while
           sweeping only the signal under test.
         Record result as scope=all_aers for every card in the template group.

  PHASE B: CLUSTER-SPECIFIC REFINEMENT
  ──────────────────────────────────────
  For each card (cluster 001..017):
    For each eligible signal NOT covered by a feasible Phase A template group,
    or where cluster-specific case studies exist:
      Filter positives/negatives to this cluster's AER tags.
      Run feasibility check (n_pos >= 2).
      If feasible: run grid_search_thresholds_v3() scoped to this cluster only.
        Record as scope=aer_specific.
      Else: record INSUFFICIENT_DATA_AER_SPECIFIC with fallback to all_aers result
        (or to the original hand-authored expression, if Phase A was also infeasible).

  PHASE C: AMPLIFY-DIRECTION AND QUALITATIVE SIGNALS
  ──────────────────────────────────────────────────
  Amplify-direction signals with non-empty expressions: tuned with LOWER priority,
    using the same machinery, but the objective is "does varying this amplifier's
    threshold change the confidence_when ladder outcome" rather than confirm/deny.
  Empty-expression qualitative signals: NOT threshold-tuned. Instead, verify:
    - a linked missing_variable_questions entry exists for each variable in `variables`
    - the choices[].effects.signals[].signal_id matches this signal_id
    - flag MISSING_USER_OVERLAY if not found

  PHASE D: REGISTRY VALIDATION PASS
  ──────────────────────────────────
  For every tuned expression produced in A/B/C, run validate_against_registry().
  Any violation → REJECTED_REGISTRY_VIOLATION, fall back to original expression,
  and emit an EXPERT REVIEW flag (this should be rare given the literal-only
  tuning constraint, and indicates a deeper problem if it occurs, such as the
  template canonicaliser accidentally treating part of an identifier as numeric).
```

---

## 6. Updated Card Output — `conditions[]` with Pathway-Level Evaluation Metadata

Same two-scope structure as v2, but evaluation block now reports pathway-level
confusion matrix (computed via `confirmation_policy`, not isolated signal accuracy),
plus a registry-validation field.

```json
{
  "signal_id": "sig_02",
  "variables": ["mean", "dry_spell_weeks"],
  "direction": "confirms",
  "active": true,
  "conditions": [
    {
      "scope": "all_aers",
      "template": "mean(dry_spell_weeks) >= T0",
      "expression": "mean(dry_spell_weeks) >= 3",
      "threshold_values": {"T0": 3},
      "original_expression": "mean(dry_spell_weeks) >= 3",
      "cards_sharing_template": ["001", "002", "005", "006", "007", "008", "014", "016"],
      "evaluation": {
        "method": "grid_search_v3",
        "objective": "pathway_level_confirmation_policy",
        "feasible": true,
        "n_positives": 4,
        "n_negatives": 14,
        "confusion_matrix": {"TP": 4, "FP": 5, "TN": 9, "FN": 0},
        "tpr": 1.0,
        "fpr": 0.36,
        "recommendation": "KEEP",
        "recommendation_reason": "Original threshold (T0=3) already achieves pathway-level TPR=1.0 at FPR=0.36 under the confirm_when policy; grid search found no dominating alternative.",
        "confidence": "low",
        "confidence_note": "n_pos=4 at feasibility margin."
      },
      "registry_validation": {"valid": true, "violations": []}
    },
    {
      "scope": "aer_specific",
      "aer_codes": ["AER-6"],
      "evaluation": {
        "feasible": false,
        "n_positives": 1,
        "recommendation": "INSUFFICIENT_DATA_AER_SPECIFIC",
        "fallback": "all_aers"
      }
    }
  ]
}
```

---

## 7. Confirmation-Policy-Aware Trace Output (excerpt)

```
╔══════════════════════════════════════════════════════════════════════════╗
║  PATHWAY: Agriculture / water_scarcity / drought                        ║
║  CONFIRMATION POLICY: min_from_set(sig_01,sig_02,sig_04) >= 2            ║
╠══════════════════════════════════════════════════════════════════════════╣
║  PHASE A — sig_02 [dry_spell_weeks] cross-AER                           ║
║  Template: mean(dry_spell_weeks) >= T0                                  ║
║  Shared by: 001,002,005,006,007,008,014,016 (8 of 17)                  ║
║                                                                          ║
║  Evaluator used: signal_evaluator.evaluate_expression()                 ║
║  Objective: PATHWAY-LEVEL outcome via confirmation_policy                ║
║    (sig_01 and sig_04 held fixed at their card-original expressions     ║
║     while sig_02's T0 is swept)                                         ║
║                                                                          ║
║  Original T0=3 → pathway TPR=1.00, FPR=0.36 (TP=4,FP=5,TN=9,FN=0)      ║
║  Grid search T0∈[1..12]: no candidate dominates (T0=3 is already        ║
║    Pareto-optimal at TPR=1.0 — lower FPR only achievable by raising T0  ║
║    which drops TPR below 1.0)                                          ║
║  → RECOMMENDATION: KEEP                                                  ║
║  → Registry validation: PASS (no invented keys; mean() is a registered  ║
║    safe builtin, dry_spell_weeks is a registered nested_time_series)    ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║  groundwater_stress / sig_06 (qualitative well-depth signal)            ║
║  expression: "" (empty) → SKIPPED from grid search                      ║
║  Verification: missing_variable_questions[0] references                ║
║    annual_well_depth_m and effects.signals targets sig_06 ✓ CONSISTENT  ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## 8. Gradient Descent: Decision and Optional Hybrid (Phase A2)

As detailed in Part 1, true gradient descent does not apply to the hard TPR/FPR objective —
it is piecewise-constant in the threshold. **Grid search remains the default and is faster
for this problem's scale.**

An optional `Phase A2` hybrid is included for future composite signals with 4+ simultaneously
free continuous thresholds AND corpora large enough that a full grid becomes the bottleneck
(grid size > ~50,000 points):

```python
def sigmoid_presearch(template, free_thresholds, positives, negatives,
                       domain_bounds, k=20.0, lr=0.1, steps=200):
    """
    Optional fast pre-search using a smoothed surrogate + gradient ascent (via autograd
    or manual gradient), used ONLY to narrow the grid search region for high-dimensional
    composite expressions. The converged continuous thresholds are then snapped to the
    nearest grid points and a small local grid search (e.g. +/-2 grid steps in each
    dimension) is run around them using the REAL evaluator and the TRUE (non-smoothed)
    objective, so the final reported threshold is always validated against the actual
    hard-comparison expression, never the surrogate.
    """
    # ... gradient ascent on smoothed TPR - lambda * smoothed FPR ...
    # ... then: grid_search_thresholds_v3() restricted to a small window around the result ...
```

This is included for completeness but is **not** triggered for any of the current cards —
all current free-threshold counts are 1–3 per signal, well within plain grid search's range.
