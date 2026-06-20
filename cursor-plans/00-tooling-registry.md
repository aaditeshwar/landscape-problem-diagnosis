# Tooling registry

> **Purpose:** Ready reckoner for scripts — what they do, when to run them, which plan introduced them, and known gotchas.  
> **Quick index (commands only):** [`scripts/README.md`](../scripts/README.md)  
> **Last updated:** 2026-06-07 (minimal seed; grow when closing plans)

---

## How to use

| When | Action |
|------|--------|
| Starting a new plan | Search this doc + `scripts/README.md` before writing new scripts |
| Closing a plan | Add/update entries for every new/changed/removed script |
| Re-running evergreen plans (05, 09) | Check **Script inventory** sections in those plans match this file |

### Entry template (copy for new scripts)

```markdown
### `scripts/path/script.py`
- **Category:** pipeline | verify | test | maintenance | review | lib
- **Purpose:** one line
- **When:** gate / ad hoc / one-off
- **Added:** Plan N (~YYYY-MM)
- **Produces:** outputs
- **Depends on:** key inputs/modules
- **Related plans:** …
- **Gotchas:** …
- **Supersedes / superseded by:** …
```

---

## Pipeline (core data path)

### `scripts/ingest_excel.py`
- **Category:** pipeline
- **Purpose:** Ingest one tehsil Excel into Mongo (`mws_data`, `village_data`, boundaries)
- **When:** After Excel sync (Plan 09); new tehsil onboarding (Plan 05)
- **Added:** early stack (~2026-05)
- **Produces:** Mongo collections; canonical drought nested keys on ingest
- **Depends on:** `metadata/data_dictionary_v2.json`, `data/raw_excel/*.xlsx`
- **Related plans:** 05, 09, 08 (multi-tehsil)
- **Gotchas:** Drought keys normalized to canonical names; stale Mongo if Excel re-ingested without this script

### `scripts/sync_active_excels.py`
- **Category:** pipeline
- **Purpose:** Copy CoRE Stack Excel exports into `data/raw_excel/`
- **When:** Plan 09 Step 0 before audit/ingest
- **Added:** Plan 09 (~2026-06)
- **Produces:** `data/raw_excel/`, `sync_report.json`
- **Depends on:** `lib/tehsil_excel_catalog.py`, `lib/excel_audit.py`
- **Related plans:** 09

### `scripts/generate_evidence_cards.py`
- **Category:** pipeline
- **Purpose:** Extract evidence cards via Claude API + embed + Mongo upsert
- **When:** New pathway cluster (Plan 05 Phase 5); **not** for corpus review (use Plan 15)
- **Added:** early stack; `--card-id` / `--resume` added later
- **Produces:** `data/evidence_cards/raw/{card_id}.json`, Mongo `evidence_cards`
- **Depends on:** paper chunks, schema, `expression_audit.validate_card_expressions`
- **Related plans:** 05, 13
- **Gotchas:** One Claude call per card; expressions validated before write

### `scripts/reload_evidence_cards.py`
- **Category:** pipeline
- **Purpose:** Reload raw card JSON → Mongo with fresh embeddings (no LLM)
- **When:** After any raw card edit; Plan 15 Phase 5
- **Added:** Plan 05 Phase 5b
- **Produces:** Updated Mongo `evidence_cards`
- **Depends on:** `data/evidence_cards/raw/*.json`, Ollama embed
- **Related plans:** 05, 13, 15
- **Gotchas:** Does not fix bad expressions — run audits first

---

## Verify (audit gates)

### `scripts/verify/audit_excel_core_stack.py`
- **Category:** verify
- **Purpose:** Compare local Excel vs CoRE Stack API (sheets, columns, geometry)
- **When:** Plan 09 Step 1 (mandatory before ingest changes)
- **Added:** Plan 09
- **Produces:** `data/excel_core_stack_audit.json` or stdout report
- **Related plans:** 09
- **Gotchas:** Fix upstream export issues before patching ingest when possible

### `scripts/verify/audit_variable_registry.py`
- **Category:** verify
- **Purpose:** Registry ↔ framework ↔ assembler ↔ card expression consistency
- **When:** Plan 05 Phase 7; after framework variable changes
- **Added:** Plan 06/05
- **Related plans:** 05, 06, 09

### `scripts/verify/evaluate_signal_matrix.py`
- **Category:** verify (hard gate)
- **Purpose:** Full signal eval matrix across fixture MWS; zero hard errors required
- **When:** Before pathway go-live; after expression edits
- **Added:** Plan 07
- **Related plans:** 05, 07, 15 (post-apply smoke)

### `scripts/verify/audit_confirmation_policy.py`
- **Category:** verify
- **Purpose:** Heuristic check: `confirmation_policy` vs `overall_reasoning_note` vs signal directions
- **When:** Plan 13; Plan 15 Phase 0 preflight; before Mongo reload
- **Added:** Plan 13 (~2026-06)
- **Produces:** `reports/policy_audit.csv` (one row per issue, with note/policy context columns), `reports/policy_audit_summary.csv` (all 136 cards)
- **Depends on:** `lib/card_policy_utils.py`
- **Related plans:** 13, 15
- **Gotchas:** Heuristics only — semantic gaps need Claude review (Plan 15). Prior manual fixes in `reports/POLICY_FIXES_FOR_REVIEW.md`

### `scripts/verify/audit_follow_up_effects.py`
- **Category:** verify
- **Purpose:** MCQ `choices[].effects.signals` shape, linkage, boolean results
- **When:** Plan 13; Plan 15 Phase 0
- **Added:** Plan 13
- **Produces:** `reports/follow_up_effects_audit.csv`
- **Related plans:** 13, 15
- **Gotchas:** Flags **error** on any choice missing `effects`, including template-neutral bands (`confirms_result: None` in `follow_up_mcq.py`) — **not** a confirmation-policy failure. Affected pathways: rainfed_risk, NTFP forest_degradation, socio_economic MCQs. groundwater_stress / irrigation_challenges typically pass. Policy review (`apply_policy_corrections.py`) did not populate these effects.

### `scripts/verify/audit_card_expressions.py`
- **Category:** verify
- **Purpose:** Per-card expression audit CSV (unknown identifiers, syntax, static index misuse)
- **When:** Plan 15 Phase 0; before reload after expression edits
- **Added:** Plan 15 (~2026-06-07)
- **Produces:** `reports/expression_audit.csv`
- **Depends on:** `lib/expression_audit.py`
- **Related plans:** 15

### `scripts/verify/audit_card_schema.py`
- **Category:** verify
- **Purpose:** JSON Schema validate all raw evidence cards
- **When:** Plan 15 Phase 0; before reload
- **Added:** Plan 15 (~2026-06-07)
- **Produces:** `reports/schema_audit.csv`
- **Related plans:** 15

### `scripts/verify/spot_check_drought_ingest.py`
- **Category:** verify (spot)
- **Purpose:** Compare Mongo drought series vs raw Excel for case-study MWS
- **When:** After re-ingest; debugging stale/wrong drought charts
- **Added:** ad hoc (~2026-06) — Darwha/Gande stale Mongo found
- **Related plans:** 09, 14 (archived)
- **Gotchas:** Mismatch often means Mongo not re-ingested after Excel update

---

## Review (Plan 15 — Claude corpus review)

### `scripts/review/run_preflight.py`
- **Category:** review
- **Purpose:** Run all Plan 15 deterministic audits; index rows by `card_id`
- **When:** Before Claude review; after card edits (baseline comparison)
- **Added:** Plan 15 (~2026-06-07)
- **Produces:** `reports/claude_review/baseline/*.csv`, `preflight_by_card.json`
- **Related plans:** 15

### `scripts/review/claude_card_reviewer.py`
- **Category:** review
- **Purpose:** One Claude call per card — semantic alignment review (D1–D5)
- **When:** Plan 15 Phase 1 (pilot: `--pathway agriculture__water_scarcity__drought`)
- **Added:** Plan 15 (~2026-06-07)
- **Produces:** `reports/claude_review/results/{card_id}.json`
- **Depends on:** preflight index, rubric, `ANTHROPIC_API_KEY`
- **Related plans:** 15
- **Gotchas:** Mirrors `generate_evidence_cards.py` loop; `--resume` skips existing results

### `scripts/review/merge_claude_review_report.py`
- **Category:** review
- **Purpose:** Merge per-card results → summary MD, issues CSV, `suggested_patches.json`
- **When:** Plan 15 Phase 2
- **Added:** Plan 15 (~2026-06-07)
- **Related plans:** 15

### `scripts/review/apply_claude_review_patches.py`
- **Category:** review
- **Purpose:** Apply human-approved patches to raw cards (per `card_id`, no fingerprint propagation)
- **When:** Plan 15 Phase 4 after finalize in `/revise-cards`
- **Added:** Plan 15 (~2026-06-07)
- **Depends on:** `metadata/claude_review_decisions.json`, optional `metadata/claude_review_edited_patches.json`, `reports/claude_review/suggested_patches.json`
- **Related plans:** 15, 16
- **Gotchas:** Only finalized cards unless `--include-unfinalized`; human edits live in **separate** `claude_review_edited_patches.json` (never overwrites Claude `suggested_patches.json`); backs up to `.backup_pre_claude_review/`

### Revise Cards UI (`/revise-cards`)
- **Category:** review (frontend + API)
- **Purpose:** Card-by-card Claude finding review; structured patch edits; per-card finalize
- **When:** Plan 15 Phase 3
- **Added:** Plan 16 (~2026-06-07)
- **Route:** `http://localhost:5173/revise-cards`
- **API:** `runtime/routers/claude_review.py` → `/api/claude-review/*`
- **Writes:** `metadata/claude_review_decisions.json`, `metadata/claude_review_edited_patches.json`
- **Related plans:** 15, 16

---

## Maintenance (occasional ops)

### `scripts/maintenance/normalize_evidence_card_expressions.py`
- **Category:** maintenance
- **Purpose:** Registry-based expression rewrites on raw cards
- **When:** After alias/canonical name changes (Plan 06)
- **Added:** Plan 06
- **Related plans:** 05, 06, 13

### `scripts/maintenance/derive_confirmation_policy.py`
- **Category:** maintenance
- **Purpose:** Auto-generate `confirmation_policy` from signals + note
- **When:** Plan 13 bulk policy generation; review output before trusting
- **Added:** Plan 13
- **Depends on:** `lib/card_policy_utils.py`
- **Related plans:** 13
- **Gotchas:** Derive can drift from nuanced prose — use `audit_confirmation_policy.py` + Plan 15 review

### `scripts/maintenance/apply_policy_corrections.py`
- **Category:** maintenance
- **Purpose:** Apply reviewed policy corrections from `metadata/policy_corrections.json`
- **When:** After manual policy review (46 cards fixed pre–Plan 15)
- **Added:** Plan 13
- **Related plans:** 13, 15 (superseded for bulk semantic review by Claude pipeline)

### `scripts/maintenance/backfill_mws_variable_names.py`
- **Category:** maintenance (idempotent)
- **Purpose:** Normalize drought nested keys in existing Mongo docs
- **When:** Plan 09 after ingest schema changes
- **Added:** Plan 06/09
- **Related plans:** 09

---

## Shared libraries (referenced by many scripts)

### `scripts/lib/expression_audit.py`
- **Category:** lib
- **Purpose:** AST name extraction, drought key checks, `validate_card_expressions()`
- **When:** Any expression edit; card generation; Plan 15 preflight
- **Added:** Plan 05/06
- **Gotchas:** `[-1]` on time series = latest year in evaluator; blocking severities: BLOCKER, SHAPE, NESTED

### `scripts/lib/card_policy_utils.py`
- **Category:** lib
- **Purpose:** Policy derive, fingerprints, note parsing, confirm signal sets
- **When:** Plan 13 audits and maintenance
- **Added:** Plan 13
- **Related plans:** 13, 15

---

## Removed scripts (do not recreate)

| Script | Removed | Reason |
|--------|---------|--------|
| `strip_legacy_signal_fields.py` | 2026-06-19 | Applied; fields stripped from corpus |
| `propagate_confirmation_policies.py` | 2026-06-19 | Fingerprint propagation abandoned (Plan 15: per-card only) |
| `apply_follow_up_mcq_templates.py` | 2026-06-19 | Replaced by `propagate_follow_up_templates.py` + Plan 13 migration |

See `scripts/README.md` **Removed** section and `scripts/archive/README.md`.

---

## Plan cross-reference

| Plan | Primary scripts | Registry sync |
|------|-----------------|---------------|
| [05-induct-new-pathway.md](./05-induct-new-pathway.md) | ingest, generate, reload, audit gates | **Evergreen** — update inventory on change |
| [09-excel-source-update.md](./09-excel-source-update.md) | sync, audit_excel, ingest, backfills | **Evergreen** — update inventory on change |
| [13-confirmation-policy-and-schema.md](./13-confirmation-policy-and-schema.md) | derive_policy, policy audits, follow-up audits | Stable |
| [15-claude-evidence-card-review.md](./15-claude-evidence-card-review.md) | `scripts/review/*`, expression/schema audits | **Active** |

Plan 14 (re-ingest/tuning) is **archived** until Plan 15 completes.
