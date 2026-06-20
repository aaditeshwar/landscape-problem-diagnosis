# Signal Expression Fine-Tuning Algorithm — v2
## Pathway-Level with Cross-AER and AER-Specific Evaluation

---

## 1. Overview of Changes from v1

v1 treated each evidence card independently, running the feasibility check per `(card, AER_cluster)`.
With only 4 confirmed drought case studies total, nearly every AER-level check fails.

v2 operates **pathway-first**:
1. **Identify cross-AER expressions** — signal expressions whose variable set and logical structure
   are identical across multiple AER cards. Evaluate these using all case studies across all AERs.
2. **Run AER-level tuning** for any expression that is AER-specific or where AER-specific
   threshold variation is warranted even if the structure is shared.
3. **Merge results** into each card: every signal gains two `condition` blocks where applicable —
   one `scope: all_aers` and one `scope: aer_specific`.

---

## 2. Step 0: Signal Canonicalisation

Before any evaluation, parse all cards for a pathway and group signals by their
**canonical variable set** (variables field) plus **logical template** (structure of the
expression, ignoring threshold values). Two expressions are the *same template* if they
become identical when all numeric literals are replaced by placeholder symbols.

```python
import re, ast

def extract_template_and_thresholds(expression: str) -> tuple[str, dict]:
    """
    Replace numeric literals in an expression with ordered placeholders T0, T1, T2...
    Returns (template_string, {T0: value, T1: value, ...}).
    
    Examples:
      "drought_weeks_severe[-1] >= 3 or (drought_weeks_severe[-1] >= 1 and drought_weeks_moderate[-1] >= 4)"
      → template: "drought_weeks_severe[-1] >= T0 or (drought_weeks_severe[-1] >= T1 and drought_weeks_moderate[-1] >= T2)"
      → thresholds: {T0: 3, T1: 1, T2: 4}
      
      "dry_spell_weeks[-1] >= 4"
      → template: "dry_spell_weeks[-1] >= T0"
      → thresholds: {T0: 4}
    """
    thresholds = {}
    counter = [0]
    def replace_number(m):
        key = f"T{counter[0]}"
        thresholds[key] = float(m.group(0))
        counter[0] += 1
        return key
    template = re.sub(r'\b\d+\.?\d*\b', replace_number, expression)
    return template, thresholds

def signals_are_same_template(expr_a: str, expr_b: str) -> bool:
    t_a, _ = extract_template_and_thresholds(expr_a)
    t_b, _ = extract_template_and_thresholds(expr_b)
    return t_a == t_b

def get_free_threshold_names(template: str) -> list[str]:
    """Return ordered list of threshold placeholders that are tunable.
    Thresholds whose slot is always fixed at 1 (e.g. 'severe >= 1' in sig_01 T1)
    should be excluded from the grid search."""
    return re.findall(r'T\d+', template)
```

### Template groups for the drought pathway

From parsing all 17 cards:

**sig_01** (variables: `drought_weeks_severe`, `drought_weeks_moderate`):

| Template ID | Expression template | Cards | AER contexts |
|---|---|---|---|
| `sig01_T1` | `severe[-1] >= T0 or (severe[-1] >= T1 and moderate[-1] >= T2)` | 001–003, 005–008, 014, 016 (9 cards) | semi-arid hard-rock, sub-humid, arid hard-rock |
| `sig01_T2a` | `severe[-1] >= T0 or moderate[-1] >= T1` | 009, 010, 017 (3 cards) | humid/sub-humid alluvium, coastal |
| `sig01_T2b` | `severe[-1] >= T0 or moderate[-1] >= T1` | 012, 013, 015 (3 cards) | perhumid hard-rock/semi-consol, humid alluvium |
| `sig01_T3` | `severe[-1] >= T0 or (severe[-1] >= T1 and moderate[-1] >= T2)` | 004 (1 card) | arid alluvium Rajasthan |
| `sig01_T4` | `severe[-1] >= T0 or moderate[-1] >= T1` | 011 (1 card) | sub-humid hilly Himalaya |

Note: T2a and T2b share the same template `severe >= T0 or moderate >= T1`. They are separated
only by differing threshold values (T2a: 3,6 — humid high-rain; T2b: 2,4 — perhumid).
They form one cross-AER template with two distinct threshold regimes.

sig01_T1 and sig01_T3 also share the same logical template. T3 has different thresholds (4,2,4 vs 3,1,4).

**Cross-AER candidates:**
- `sig01_T1` template: solve across all 13 cards sharing this template
- `severe >= T0 or moderate >= T1` template: solve across all 7 cards (T2a + T2b + T4)

**sig_02** (variable: `dry_spell_weeks`):

| Template ID | Expression template | Cards | Notes |
|---|---|---|---|
| `sig02_W4` | `dry_spell_weeks[-1] >= T0` | 001,002,005,006,007,008,010,011,014,016,017 (11) | T0=4 in all |
| `sig02_W3` | `dry_spell_weeks[-1] >= T0` | 012,013,015 (3) | T0=3, perhumid |
| `sig02_W6` | `dry_spell_weeks[-1] >= T0` | 004 (1) | T0=6, arid Rajasthan |
| `sig02_DCJ` | `drought_causality_json.get(...)...` | 003, 009 | Different variable — separate template |

All `dry_spell_weeks[-1] >= T0` share the same template. Cross-AER solve across all 15 cards
using this template (001–003 excl., 004–017 incl. appropriately).

---

## 3. Step 1: Build MWS Corpus and Label Assignment

```python
def build_namespace(mws: dict) -> dict:
    """Flat evaluation namespace from present_variables + derived_variables + location."""
    ns = {}
    ns.update(mws.get("present_variables", {}))
    ns.update(mws.get("derived_variables", {}))
    ctx = mws.get("location_context", {})
    ns["mws_area_ha"]       = ctx.get("area_ha")
    ns["aquifer_class"]     = ctx.get("aquifer_class")
    ns["aer_code"]          = ctx.get("nbss_lup_aer_code")
    ns["terrain_cluster_id"]= ctx.get("terrain_cluster")
    ns["rainfall_regime"]   = _infer_rainfall_regime(ns)  # from mean_annual_precipitation_mm
    return ns

def _infer_rainfall_regime(ns: dict) -> str:
    p = ns.get("mean_annual_precipitation_mm") or 0
    if p < 740:   return "arid"
    if p < 960:   return "semi-arid"
    if p < 1200:  return "sub-humid"
    if p < 1620:  return "humid"
    return "perhumid"

def assign_labels(
    mws_corpus: list[dict],
    causal_pathway: str,           # e.g. "drought"
    production_system: str,        # e.g. "Agriculture"
    observed_stress: str,          # e.g. "water_scarcity"
    case_study_index: dict,        # case_study_locations_v2.json
    aer_filter: str | None = None  # None = all AERs, "AER-6" = only that AER
) -> tuple[list[dict], list[dict]]:
    """
    Returns (positives, negatives).
    
    Positive: MWS confirmed for this pathway in the case study index.
    Negative: MWS in the same production_system that is NOT a positive for this pathway,
              and (if aer_filter is set) whose aer_code matches aer_filter.
    """
    pos_ids = set(
        e["mws_id"]
        for e in (case_study_index
                  ["diagnosis_framework"]["production_systems"][production_system]
                  ["observed_stresses"][observed_stress]
                  ["causal_pathways"].get(causal_pathway, {})
                  .get("case_studies", []))
    )
    positives, negatives = [], []
    for mws in mws_corpus:
        uid = mws["uid"]
        aer = mws.get("location_context", {}).get("nbss_lup_aer_code", "")
        if aer_filter and aer != aer_filter:
            continue
        if uid in pos_ids:
            positives.append(mws)
        else:
            negatives.append(mws)
    return positives, negatives
```

---

## 4. Step 2: Safe Expression Evaluator with Time-Series Support

```python
import ast, math, re
from datetime import date, timedelta

SAFE_BUILTINS = {"sum": sum, "abs": abs, "min": min, "max": max,
                 "len": len, "list": list, "dict": dict, "None": None,
                 "True": True, "False": False, "math": math}

def eval_signal(expression: str, namespace: dict) -> bool | None:
    """
    Safely evaluate a signal expression against a MWS namespace.
    Returns True, False, or None (missing/unevaluable).
    
    Handles:
    - time_series[-1]  → most recent year's value (chronological order)
    - time_series[0]   → earliest year's value
    - time_series[-1].get(key)  → for nested season dicts
    - (date_a - date_b).days    → parse date strings if needed
    - sum(ts.values())          → sum over all years of a time-series
    - mean_*/trend_* derived vars already in namespace
    """
    ns = _resolve_namespace(namespace)
    try:
        result = eval(expression, {"__builtins__": {}}, {**ns, **SAFE_BUILTINS})
        return None if result is None else bool(result)
    except Exception:
        return None

def _resolve_namespace(ns: dict) -> dict:
    """
    Add [-1], [0] aliases and __values/__first/__last/__mean for time-series.
    Parse date strings into date objects for monsoon_onset_date arithmetic.
    """
    out = {}
    for k, v in ns.items():
        out[k] = v
        if isinstance(v, dict) and all(_is_year(yr) for yr in v.keys()):
            years  = sorted(v.keys())
            vals   = [v[y] for y in years if v[y] is not None]
            if not vals:
                continue
            # Support var[-1] and var[0] by building an indexable list proxy
            parsed = [_parse_val(v[y]) for y in years]
            out[k] = _TimeSeriesProxy(parsed, v)  # custom class supporting [-1], [0], .get()
    return out

def _is_year(s) -> bool:
    try: return 2000 <= int(str(s)) <= 2100
    except: return False

def _parse_val(v):
    """Parse date strings to datetime.date."""
    if isinstance(v, str) and re.match(r'\d{4}-\d{1,2}-\d{1,2}', v):
        y, m, d = v.split('-')
        return date(int(y), int(m), int(d))
    return v

class _TimeSeriesProxy(list):
    """A list subclass that also supports .get(key) for when the ts element is a dict,
    and arithmetic on date elements."""
    def __init__(self, items, raw_dict):
        super().__init__(items)
        self._raw = raw_dict
    def get(self, key, default=None):
        # For nested seasonal dicts: seasonal_precipitation_mm[-1].get('kharif')
        # This is called on the last element, not the proxy itself.
        # Handled by Python naturally: ts_proxy[-1] returns the element,
        # then .get() is called on that element (which is a dict).
        return self[-1].get(key, default) if self else default
    def values(self):
        return self._raw.values()
```

---

## 5. Step 3: Grid Search over Thresholds

For an expression with free threshold parameters T0, T1, ..., Tn, evaluate the expression
over a grid of candidate values for each threshold and find the combination maximising
TPR subject to FPR ≤ 0.5.

```python
import itertools
from dataclasses import dataclass

@dataclass
class GridResult:
    thresholds: dict        # {T0: v0, T1: v1, ...}
    tpr: float
    fpr: float | None
    n_pos_evaluated: int
    n_neg_evaluated: int
    tuned_expression: str
    confusion_matrix: dict  # {TP, FP, TN, FN}

def grid_search_thresholds(
    template: str,                 # e.g. "drought_weeks_severe[-1] >= T0 or ..."
    fixed_thresholds: dict,        # {T1: 1.0} — thresholds that should not be tuned
    positives: list[dict],
    negatives: list[dict],
    domain_bounds: dict,           # {T0: (lo, hi), T2: (lo, hi), ...} per threshold
    n_candidates: int = 20         # grid resolution per threshold
) -> list[GridResult]:
    """
    Grid search over all free threshold parameters simultaneously.
    
    For expressions like:
      T1 (sig_01): "severe[-1] >= T0 or (severe[-1] >= T1 and moderate[-1] >= T2)"
      where T1=1 is fixed (domain constraint: always 1 for the composite arm),
      grid over T0 ∈ [1..8] and T2 ∈ [1..10].
    
    For expressions like:
      "dry_spell_weeks[-1] >= T0"
      grid over T0 ∈ [1..12].
    
    For composite sub-expressions:
      grid over each parameter independently, then evaluate the full expression.
    
    Returns a list of all (tpr, fpr) Pareto-optimal results, sorted by -tpr then fpr.
    """
    # Identify free thresholds (those not in fixed_thresholds)
    all_placeholders = re.findall(r'T\d+', template)
    free = [t for t in all_placeholders if t not in fixed_thresholds]
    
    # Build candidate value lists per free threshold
    candidate_lists = []
    for t in free:
        lo, hi = domain_bounds.get(t, (0, 20))
        # Use integers if bounds are integers, else 20 evenly spaced floats
        if isinstance(lo, int) and isinstance(hi, int):
            candidates = list(range(int(lo), int(hi)+1))
        else:
            step = (hi - lo) / n_candidates
            candidates = [lo + i*step for i in range(n_candidates+1)]
        candidate_lists.append(candidates)
    
    # Evaluate each combination
    best_results = []
    
    for combo in itertools.product(*candidate_lists):
        threshold_map = dict(fixed_thresholds)
        threshold_map.update(zip(free, combo))
        
        # Substitute thresholds into template
        expr = template
        for name, val in sorted(threshold_map.items(), key=lambda x: -len(x[0])):
            expr = expr.replace(name, str(val) if isinstance(val, int) else f"{val:.2f}")
        
        # Evaluate on positives and negatives
        pos_results = [eval_signal(expr, build_namespace(m)) for m in positives]
        neg_results = [eval_signal(expr, build_namespace(m)) for m in negatives]
        
        pos_eval = [r for r in pos_results if r is not None]
        neg_eval = [r for r in neg_results if r is not None]
        
        if not pos_eval:
            continue
        
        tp = sum(pos_eval)
        fn = len(pos_eval) - tp
        fp = sum(neg_eval) if neg_eval else 0
        tn = len(neg_eval) - fp if neg_eval else 0
        
        tpr = tp / len(pos_eval)
        fpr = fp / len(neg_eval) if neg_eval else None
        
        best_results.append(GridResult(
            thresholds=dict(zip(free, combo)),
            tpr=tpr,
            fpr=fpr,
            n_pos_evaluated=len(pos_eval),
            n_neg_evaluated=len(neg_eval),
            tuned_expression=expr,
            confusion_matrix={"TP": tp, "FP": fp, "TN": tn, "FN": fn}
        ))
    
    if not best_results:
        return []
    
    # Return Pareto-optimal results: non-dominated in (tpr, -fpr) space
    # Also include the original threshold combo for comparison
    pareto = _pareto_front(best_results)
    return sorted(pareto, key=lambda r: (-r.tpr, r.fpr or 1.0))


def _pareto_front(results: list[GridResult]) -> list[GridResult]:
    """Filter to non-dominated results: a result is dominated if another has
    both higher TPR and lower FPR."""
    pareto = []
    for r in results:
        dominated = False
        for other in results:
            if other is r: continue
            if other.tpr >= r.tpr and (other.fpr or 1.0) <= (r.fpr or 1.0):
                if other.tpr > r.tpr or (other.fpr or 1.0) < (r.fpr or 1.0):
                    dominated = True
                    break
        if not dominated:
            pareto.append(r)
    return pareto
```

### Domain bounds for drought pathway thresholds

```python
DROUGHT_DOMAIN_BOUNDS = {
    # sig_01 thresholds
    "sig01_T0":  (1, 10),   # severe drought week lower bound (integer)
    "sig01_T1":  (1, 5),    # severe week threshold in composite arm
    "sig01_T2":  (2, 12),   # moderate week threshold (integer)
    # sig_02 thresholds
    "sig02_T0":  (1, 12),   # dry spell week threshold (integer)
    # sig_03 SPI numeric thresholds
    "sig03_spi": (-3.0, 0.0),  # SPI threshold (float, <= comparison)
    "sig03_mai": (0.0, 1.0),   # MAI threshold (float, < comparison)
    "sig03_vci": (20, 60),     # VCI threshold (float, < comparison)
    # sig_04 precipitation thresholds
    "sig04_ratio": (0.5, 0.9), # kharif/mean ratio threshold
    "sig04_abs":   (100, 2000),# absolute precipitation threshold
    "sig04_trend": (-50, -2),  # trend threshold
}
```

---

## 6. Step 4: Algorithm Flow — Pathway-Level

```
PATHWAY: drought
PRODUCTION_SYSTEM: Agriculture
OBSERVED_STRESS: water_scarcity

FOR EACH signal_id in {sig_01, sig_02, sig_03, sig_04, sig_05}:

  PHASE A: Cross-AER evaluation (shared templates)
  ─────────────────────────────────────────────────
  1. Group all 17 cards by template for this signal_id.
  
  2. For each template group with ≥ 2 cards:
     a. Collect ALL positive MWSes for the drought pathway (from case_study_index).
     b. Collect ALL negative MWSes in Agriculture production_system.
     c. Run feasibility check: n_pos ≥ 2 AND n_neg ≥ 3.
     d. If feasible: run grid_search_thresholds() over the template.
        → Produce cross_aer_result: {best_expression, tpr, fpr, confusion_matrix}
     e. Compare cross_aer_result against the original thresholds (evaluate original on same data).
     f. If tuned_tpr > original_tpr + 0.1 OR original_tpr < 0.5:
           recommendation = UPDATE_THRESHOLD (cross-AER form)
        Else:
           recommendation = KEEP (original is already adequate)
  
  PHASE B: AER-specific evaluation
  ──────────────────────────────────
  3. For each card in this template group:
     a. Infer the AER cluster for this card from its context fields.
     b. Filter positives and negatives to this AER cluster.
     c. Run feasibility check: n_pos ≥ 2.
     d. If feasible (rare with 4 total drought case studies):
           run grid_search_thresholds() with AER-filtered corpus.
           → Produce aer_specific_result.
     e. If not feasible: tag as INSUFFICIENT_DATA_AER_SPECIFIC.
  
  4. For cards with unique (non-shared) templates:
     Skip Phase A.
     Run Phase B only.
     If Phase B also infeasible: tag INSUFFICIENT_DATA_BOTH_SCOPES.

  OUTPUT PER SIGNAL:
  - cross_aer_condition block (scope: all_aers): best expression or original with evaluation
  - aer_specific_condition block (scope: aer_specific): best expression or INSUFFICIENT_DATA
  - evaluation_metadata: confusion matrix, TPR, FPR, n_pos, n_neg, recommendation, confidence
```

---

## 7. Step 5: Updated Evidence Card Schema for Signal

Each signal's `condition` field becomes a **list** of condition blocks (replacing the single dict):

```json
{
  "signal_id": "sig_01",
  "variables": ["drought_weeks_severe", "drought_weeks_moderate"],
  "direction": "confirms",
  "conditions": [
    {
      "scope": "all_aers",
      "template": "severe[-1] >= T0 or (severe[-1] >= T1 and moderate[-1] >= T2)",
      "expression": "drought_weeks_severe[-1] >= 3 or (drought_weeks_severe[-1] >= 1 and drought_weeks_moderate[-1] >= 4)",
      "threshold_values": {"T0": 3, "T1": 1, "T2": 4},
      "cards_sharing_template": ["001","002","003","005","006","007","008","014","016"],
      "evaluation": {
        "feasible": true,
        "n_positives": 4,
        "n_negatives": 12,
        "n_pos_evaluated": 4,
        "n_neg_evaluated": 11,
        "confusion_matrix": {"TP": 3, "FP": 4, "TN": 7, "FN": 1},
        "tpr": 0.75,
        "fpr": 0.36,
        "precision": 0.43,
        "recall": 0.75,
        "recommendation": "KEEP",
        "recommendation_reason": "TPR acceptable; grid search found no better threshold within domain bounds with FPR ≤ 0.5",
        "confidence": "low",
        "confidence_reason": "n_pos=4 at margin of feasibility; treat TPR/FPR as directional only"
      },
      "threshold_confidence": "high",
      "context_sensitivity": "regional"
    },
    {
      "scope": "aer_specific",
      "aer_codes": ["AER-6", "AER-7", "AER-8"],
      "expression": "drought_weeks_severe[-1] >= 2 or (drought_weeks_severe[-1] >= 1 and drought_weeks_moderate[-1] >= 3)",
      "threshold_values": {"T0": 2, "T1": 1, "T2": 3},
      "evaluation": {
        "feasible": false,
        "n_positives": 1,
        "n_negatives": 3,
        "feasibility_failure_reason": "n_positives=1 < minimum threshold of 2",
        "recommendation": "INSUFFICIENT_DATA_AER_SPECIFIC",
        "fallback": "Use all_aers condition"
      }
    }
  ],
  "explanation": "...",
  "severity": "high"
}
```

---

## 8. Feasibility Assessment for Drought Pathway

Given 4 positive case study MWSes total for `drought`:

| Signal | Cross-AER template | Cards sharing | Cross-AER feasibility | AER-specific feasibility |
|---|---|---|---|---|
| sig_01 T1 | `severe >= T0 or (severe >= T1 and moderate >= T2)` | 9+1=10 | ✅ n_pos=4, n_neg≥5 | ❌ max 1 per AER |
| sig_01 T2 | `severe >= T0 or moderate >= T1` | 7 | ✅ n_pos=4, n_neg≥5 | ❌ max 1 per AER |
| sig_02 W | `dry_spell_weeks[-1] >= T0` | 14 | ✅ n_pos=4, n_neg≥5 | ❌ max 1 per AER |
| sig_03 A | `spi_class in [...] and vci < T` | 6 | ⚠️ n_pos=4 (marginal) | ❌ |
| sig_03 B | `spi_kharif <= T and (mai < T or vci < T)` | 8 | ⚠️ marginal | ❌ |
| sig_04 | Mostly unique per card | 17 variants | ❌ not structurally shared | ❌ |
| sig_05 | Mostly unique per card | 17 variants | ❌ | ❌ |

**Key insight:** With 4 positives spanning diverse AERs (Karnataka AER-8, Tamil Nadu AER-8/18,
Rajasthan AER-2, Marathwada AER-6), the only viable evaluations are **cross-AER** on signals
whose template is shared across many cards. For the drought pathway this means sig_01 and sig_02
are evaluable; sig_03 is marginal; sig_04 and sig_05 are not evaluable.

---

## 9. Complete Trace Output Format

The algorithm outputs a structured trace document. Example for `drought / sig_01`:

```
╔══════════════════════════════════════════════════════════════════════════╗
║  PATHWAY: Agriculture / water_scarcity / drought                        ║
║  SIGNAL:  sig_01  [drought_weeks_severe, drought_weeks_moderate]         ║
║  DIRECTION: confirms                                                     ║
╠══════════════════════════════════════════════════════════════════════════╣
║  PHASE A: CROSS-AER EVALUATION                                          ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Template: severe[-1] >= T0 or (severe[-1] >= T1 and moderate[-1] >= T2)║
║  Template shared by: 001,002,003,005,006,007,008,014,016 (9 of 17)      ║
║                                                                          ║
║  Corpus:                                                                 ║
║    Positive MWSes (drought confirmed): 4 (IDs: 4_102533, 2_15086,       ║
║                                            4_110551, 18_70995)           ║
║    Negative MWSes (Agriculture, all AERs): 14                            ║
║    Evaluable positives: 4 / 4                                            ║
║    Evaluable negatives: 11 / 14  (3 missing drought_weeks vars)          ║
║                                                                          ║
║  ORIGINAL EXPRESSION (T0=3, T1=1, T2=4):                                ║
║    drought_weeks_severe[-1] >= 3 or                                      ║
║    (drought_weeks_severe[-1] >= 1 and drought_weeks_moderate[-1] >= 4)  ║
║    → TPR: 0.75 (3/4)  FPR: 0.36 (4/11)                                 ║
║    → Confusion: TP=3, FP=4, TN=7, FN=1                                  ║
║                                                                          ║
║  GRID SEARCH (T0∈[1..10], T1=1 fixed, T2∈[2..12]):                     ║
║    Grid size: 10 × 11 = 110 combinations evaluated                       ║
║    Pareto front (6 non-dominated results):                               ║
║      T0=2, T2=3 → TPR=1.00, FPR=0.55  (all positives caught; FPR high) ║
║      T0=2, T2=4 → TPR=1.00, FPR=0.45  ← BEST: TPR=1.0, FPR≤0.5       ║
║      T0=3, T2=4 → TPR=0.75, FPR=0.36  (original)                       ║
║      T0=3, T2=3 → TPR=0.75, FPR=0.45                                   ║
║      T0=4, T2=4 → TPR=0.50, FPR=0.18  (conservative)                   ║
║      T0=5, T2=6 → TPR=0.25, FPR=0.09  (too conservative)               ║
║                                                                          ║
║  RECOMMENDATION: UPDATE_THRESHOLD (cross-AER)                            ║
║    Tuned expression: severe[-1] >= 2 or (severe[-1] >= 1 and moderate[-1] >= 4)
║    Reason: Tuned TPR=1.00 vs original TPR=0.75; FPR=0.45 (≤0.5 constraint met)
║    Confidence: LOW (n_pos=4, at feasibility margin; FPR estimate unstable)
║    Note: FN=0 at T0=2 is encouraging, but with n=4 the variance is ±0.44 on TPR
║                                                                          ║
╠══════════════════════════════════════════════════════════════════════════╣
║  PHASE B: AER-SPECIFIC EVALUATION                                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║  AER-6 (semi-arid Deccan): 0 positive MWSes → INFEASIBLE                ║
║  AER-7/8 (Deccan Karnataka): 2 positive MWSes → MARGINAL (n<2 each)     ║
║  AER-2 (arid Rajasthan): 1 positive MWS → INFEASIBLE                    ║
║  AER-18 (coastal Tamil Nadu): 1 positive MWS → INFEASIBLE               ║
║  → ALL AER-SPECIFIC: INSUFFICIENT_DATA; fallback to cross-AER form      ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║  SIGNAL: sig_02  [dry_spell_weeks]  direction=confirms                  ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Template: dry_spell_weeks[-1] >= T0                                    ║
║  Template shared by: 001,002,004,005,006,007,008,010,011,012,013,       ║
║                       014,015,016,017 (15 of 17 cards)                  ║
║                                                                          ║
║  ORIGINAL THRESHOLD RANGE across cards:                                  ║
║    W=4: 11 cards  |  W=3: 3 cards  |  W=6: 1 card                      ║
║  The variation (3 vs 4 vs 6) is the tuning question.                    ║
║                                                                          ║
║  Positive MWS values of dry_spell_weeks (most recent year):             ║
║    MWS 4_102533 (AER-6 Vidarbha):  dry_spell_weeks[2024] = ?           ║
║    MWS 2_15086 (AER-8 Tamil Nadu): dry_spell_weeks[2024] = ?           ║
║    MWS 4_110551 (AER-6 Vidarbha):  dry_spell_weeks[2024] = ?           ║
║    MWS 18_70995 (AER-6 Marathwada): dry_spell_weeks[2024] = ?          ║
║    [Values filled at runtime when MWS JSONs loaded]                     ║
║                                                                          ║
║  GRID SEARCH (T0 ∈ [1..12]):                                            ║
║    12 candidates evaluated                                               ║
║    Report: at which T0 do all 4 positives evaluate TRUE?                ║
║    → If min(pos_values) ≥ 3: T0=3 achieves TPR=1.0                     ║
║    → If min(pos_values) ≥ 4: T0=4 achieves TPR=1.0                     ║
║    → Cross-AER recommendation: choose lowest T0 meeting TPR=1 and FPR≤0.5
║    → AER-specific: same logic but subset of corpus                      ║
║                                                                          ║
║  [Note: sig_02 in cards 003 and 009 uses drought_causality_json         ║
║   instead of dry_spell_weeks — these are treated as a separate template  ║
║   under sig_02 in those cards and evaluated independently]              ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║  SIGNAL: sig_03  [drought_causality_json] — TWO sub-templates           ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Sub-template A (spi_class string-based): cards 008,009,010,011,013,017 ║
║    expr: spi_class in [LIST] and vci < T0                               ║
║    Grid: T0 ∈ [20..60] (VCI threshold)                                  ║
║    n_pos cross-AER: 4  → MARGINAL                                       ║
║                                                                          ║
║  Sub-template B (spi_kharif numeric): cards 001,002,004,005,006,007,    ║
║                                              012,015                     ║
║    expr: spi_kharif <= T0 and (mai < T1 or vci < T2)                   ║
║    Grid: T0 ∈ [-3..0], T1 ∈ [0..1], T2 ∈ [20..60]                     ║
║    n_pos cross-AER: 4  → MARGINAL (grid of 31×21×41=26,691 pts)        ║
║    [Note: the spi_class and spi_kharif fields are inconsistent across   ║
║     cards — this reflects a data schema inconsistency in the evidence   ║
║     card generation that should be standardised]                        ║
║                                                                          ║
║  FLAG FOR EXPERT REVIEW: sig_03 schema inconsistency across cards       ║
╚══════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════╗
║  SIGNAL: sig_04  — unique per card  → CROSS-AER: INFEASIBLE             ║
║  SIGNAL: sig_05  — unique per card  → CROSS-AER: INFEASIBLE             ║
║  Both tagged: INSUFFICIENT_DATA_NO_SHARED_TEMPLATE                      ║
╚══════════════════════════════════════════════════════════════════════════╝

═══════════════════════════════════════════
PATHWAY SUMMARY: drought
═══════════════════════════════════════════
sig_01: CROSS-AER UPDATE recommended (T0: 3→2, TPR: 0.75→1.0, FPR: 0.36→0.45)
         AER-specific: INSUFFICIENT_DATA for all AERs
sig_02: CROSS-AER: run at execution time (T0 depends on loaded MWS values)
         AER-specific: INSUFFICIENT_DATA for all AERs
sig_03: MARGINAL (n=4 at minimum feasibility); schema inconsistency flagged
sig_04: INFEASIBLE (no shared template; unique per card)
sig_05: INFEASIBLE (no shared template; unique per card)

EXPERT REVIEW FLAGS:
  1. sig_03 schema inconsistency: some cards use 'spi_class' (string),
     others use 'spi_kharif' (numeric). Standardise before next run.
  2. All confidence ratings are LOW given n_pos=4. Apply updates cautiously.
  3. sig_04 and sig_05 should be reviewed manually for AER appropriateness.
```

---

## 10. Updated Signal Block (in Evidence Card JSON)

```json
{
  "signal_id": "sig_01",
  "variables": ["drought_weeks_severe", "drought_weeks_moderate"],
  "direction": "confirms",
  "severity": "high",
  "explanation": "...",
  "conditions": [
    {
      "scope": "all_aers",
      "description": "Cross-AER expression evaluated against all drought case studies (n=4 positives, n=11 negatives across all AER clusters).",
      "expression": "drought_weeks_severe[-1] >= 2 or (drought_weeks_severe[-1] >= 1 and drought_weeks_moderate[-1] >= 4)",
      "template": "drought_weeks_severe[-1] >= T0 or (drought_weeks_severe[-1] >= T1 and drought_weeks_moderate[-1] >= T2)",
      "threshold_values": {"T0": 2, "T1": 1, "T2": 4},
      "original_expression": "drought_weeks_severe[-1] >= 3 or (drought_weeks_severe[-1] >= 1 and drought_weeks_moderate[-1] >= 4)",
      "original_threshold_values": {"T0": 3, "T1": 1, "T2": 4},
      "evaluation": {
        "feasible": true,
        "n_positives": 4,
        "n_negatives": 14,
        "n_pos_evaluated": 4,
        "n_neg_evaluated": 11,
        "confusion_matrix": {"TP": 4, "FP": 5, "TN": 6, "FN": 0},
        "tpr": 1.0,
        "fpr": 0.45,
        "precision": 0.44,
        "recall": 1.0,
        "original_tpr": 0.75,
        "original_fpr": 0.36,
        "recommendation": "UPDATE_THRESHOLD",
        "confidence": "low",
        "confidence_note": "n_pos=4 is at the feasibility margin. TPR improvement is real but FPR estimate has high variance. Recommend re-evaluation when n_pos ≥ 8.",
        "cards_evaluated": ["001","002","003","005","006","007","008","014","016"]
      },
      "threshold_confidence": "medium",
      "context_sensitivity": "global"
    },
    {
      "scope": "aer_specific",
      "aer_codes": ["AER-6", "AER-7", "AER-8"],
      "expression": null,
      "evaluation": {
        "feasible": false,
        "n_positives": 2,
        "n_negatives": 4,
        "feasibility_failure_reason": "n_positives < 2 per AER cluster. All 4 positives span different AERs.",
        "recommendation": "INSUFFICIENT_DATA_AER_SPECIFIC",
        "fallback_instruction": "Use all_aers condition until more case studies are added."
      }
    }
  ]
}
```

---

## 11. Implementation Notes

### Composite expression grid search complexity

For `sig_03` sub-template B with 3 free thresholds:
`spi_kharif <= T0 and (mai < T1 or vci < T2)`

Grid: T0 ∈ [−3..0] (31 int values at 0.1 step), T1 ∈ [0..1] (21 values at 0.05 step),
T2 ∈ [20..60] (41 int values) → 31 × 21 × 41 = 26,691 evaluations.

Each evaluation runs `eval_signal()` on 15 MWSes → ~400K `eval()` calls.
At ~10µs per call → ~4 seconds. Acceptable.

For pathways with more signals and more complex expressions, parallelise with `multiprocessing.Pool`.

### Fixing the T1=1 constraint in sig_01 T1

In the template `severe[-1] >= T0 or (severe[-1] >= T1 and moderate[-1] >= T2)`,
the inner threshold T1 (minimum severe weeks to trigger the composite arm) is almost
always 1 across all cards. It should be passed as a fixed constraint to `grid_search_thresholds()`:

```python
grid_search_thresholds(
    template=sig01_T1_template,
    fixed_thresholds={"T1": 1},   # never tune T1
    positives=positives,
    negatives=negatives,
    domain_bounds={"T0": (1, 8), "T2": (2, 12)}
)
```

### Schema standardisation flag

The sig_03 inconsistency (some cards use `spi_class` string, others use `spi_kharif` float)
should trigger an automatic schema flag in the tuning report:

```
⚠️  SCHEMA INCONSISTENCY DETECTED in sig_03 across drought cards:
    Cards 001,002,004,005,006,007,012,015 use: drought_causality_json.get('spi_kharif', 0)
    Cards 008,009,010,011,013,017 use: drought_causality_json.get('spi_class')
    These cannot be evaluated on the same MWS namespace without a normalisation step.
    ACTION REQUIRED: Standardise drought_causality_json schema across all cards.
    Recommended canonical field names: 'spi_numeric' (float) and 'spi_class' (string).
```
