# MWS multi-tehsil membership — implementation plan

> **Status:** Implemented (2026-06-07)  
> **Problem:** MWS polygons on tehsil boundaries appear in multiple tehsil excels. Per-tehsil ingest upserts by `uid` only, so the last ingested tehsil overwrites `state` / `district` / `tehsil` on `mws_data` and `mws_boundaries`.

---

## Root cause

- `scripts/ingest_excel.py` tags each MWS with scalar `tehsil` and `$set`s the full doc on `{"uid": uid}`.
- `fetch_core_stack_geometries` upserts `mws_boundaries` on `{"uid": uid}` only.
- Map API queries `mws_boundaries` by `{state, district, tehsil}` — MWS missing if last ingest was another tehsil.

---

## Target schema

### `mws_data` (one doc per UID)

```json
{
  "uid": "4_122144",
  "tehsils": [
    {"state": "Maharashtra", "district": "Yavatmal", "tehsil": "Darwha"},
    {"state": "Maharashtra", "district": "Yavatmal", "tehsil": "Digras"}
  ]
}
```

- `tehsils` is source of truth (array of `{state, district, tehsil}`).
- Legacy scalar `state` / `district` / `tehsil` kept in sync with **primary** (first) ref for backward compatibility during migration.

### `mws_boundaries` (one doc per UID × tehsil)

Unique key: `(uid, state, district, tehsil)`.

---

## Implementation checklist

| Phase | Item | Location |
|-------|------|----------|
| 1 | Shared helpers | `runtime/services/tehsil_refs.py` |
| 2 | Backfill from raw excels | `scripts/maintenance/backfill_mws_tehsils.py` |
| 3 | Ingest writes + indexes | `scripts/ingest_excel.py` |
| 4 | Diagnosis uses active tehsil ref | `query.py`, `session_manager.py`, `assembler.py`, `reasoner.py` |
| 5 | Map boundaries | `map.py` (query unchanged after boundary fix) |
| 6 | Frontend | `types`, `client.ts`, `App.tsx`, `InfoPanel.tsx` |
| 7 | Maintenance / verify | `backfill_mws_aer.py`, `verify_ingest.py`, `test_prompt_builder.py` |

---

## Operations

### Backfill tehsil lists (run once on existing MongoDB)

```bash
python scripts/maintenance/backfill_mws_tehsils.py
python scripts/maintenance/backfill_mws_tehsils.py --dry-run
```

Uses `data/raw_excel/*_data.xlsx` mws sheet UIDs + `ingest_manifest` metadata.

### Re-fetch boundaries (optional, needs API key)

Re-run ingest with `--force` per tehsil, or geometry-only repair script, to populate per-tehsil `mws_boundaries` rows.

---

## Design decisions

- **Stats are per UID** — sheet fields remain one canonical record; only membership is multi-tehsil.
- **Diagnosis tehsil** — taken from user map selection (`tehsil_ref` on query), not from stored scalar on MWS doc.
- **Locate** — geo query returns tehsil from the boundary polygon hit (unchanged).
- **Villages** — same overwrite pattern exists on `village_data` / `village_boundaries`; out of scope unless extended later.

---

## Verification

1. Backfill report: count UIDs in 2+ tehsils; spot-check on map in both tehsils.
2. `python scripts/test/test_tehsil_refs.py`
3. Re-ingest one tehsil with `--force`; confirm `$addToSet` preserves other tehsils.
4. End-to-end diagnosis from boundary MWS; session/logs show selected tehsil.
