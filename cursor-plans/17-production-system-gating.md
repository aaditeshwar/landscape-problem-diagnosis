# Production-system gating

Skip entire production systems for an MWS when framework eligibility rules fire (e.g. NTFP when tree cover &lt; 10%).

## Rules source

`metadata/diagnosis_framework.json` — per production system:

```json
"NTFP_Forest_Biodiversity": {
  "eligibility": {
    "skip_when": [
      {
        "id": "min_tree_cover",
        "expression": "tree_cover_percent_mws < 10",
        "message": "Tree cover is below 10% of MWS area — NTFP/forestry pathways skipped."
      }
    ]
  },
  "observed_stresses": { ... }
}
```

Expressions use the same Python boolean syntax and evaluator as evidence-card signals (`signal_evaluator.evaluate_expression`).

## Gate variable

| Variable | Type | Computation |
|----------|------|-------------|
| `tree_cover_percent_mws` | derived static | `latest(lulc_ha.tree_forest) / area_ha × 100` |

Registered in `data_dictionary_v2.json`, `variable_registry.json`, `derived_variables.py`, and `assembler.VARIABLE_RESOLVERS`.

**Fail-open:** if the expression cannot be evaluated (missing LULC or area), the production system stays eligible.

## Pipeline (single evaluation per turn)

```
load MWS → evaluate gates → retrieve cards → filter cards → assemble bundle → filter bundle → reasoner
```

Implemented in `runtime/services/production_system_gate.py`, called from `runtime/routers/query.py` (initial query and follow-up).

Outputs persisted on the diagnosis log and API response as `skipped_production_systems`:

```json
{
  "production_system": "NTFP_Forest_Biodiversity",
  "rule_id": "min_tree_cover",
  "message": "...",
  "expression": "tree_cover_percent_mws < 10",
  "tree_cover_percent_mws": 4.2
}
```

## Surfaces

| Surface | Behaviour |
|---------|-----------|
| Diagnosis panel | Banner listing skipped systems + reasons |
| Feedback comparison grid | Hide pathways for skipped systems (from log snapshot) |
| Info panel / charts | Unchanged — MWS facts, not gated |
| Signal editor | Unchanged — global card editing |

## Mongo metadata

Run after editing `diagnosis_framework.json`:

```powershell
py scripts/load_metadata_to_mongo.py
```

Loads `diagnosis_framework` and `data_dictionary` only (variable registry stays file-based at runtime).

## Verify

```powershell
py scripts/test/test_production_system_gate.py
```
