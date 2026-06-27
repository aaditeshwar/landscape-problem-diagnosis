# Scripts layout

Python tooling for preprocessing, evidence cards, and diagnostics. Run from the repo root:

```powershell
.venv\Scripts\python.exe scripts\<script>.py [args]
```

Shared bootstrap: `scripts/_bootstrap.py` (repo `ROOT`, optional `runtime/` on `sys.path`).

**Plans:** `cursor-plans/00-tooling-registry.md` (lifecycle + context), `cursor-plans/05-induct-new-pathway.md`, `cursor-plans/09-excel-source-update.md`, `cursor-plans/13-confirmation-policy-and-schema.md`, `cursor-plans/15-claude-evidence-card-review.md`.

## Pipeline (run in order for a new pathway / tehsil)

| Script | Purpose |
|--------|---------|
| `load_metadata_to_mongo.py` | Load `metadata/*.json` into MongoDB |
| `sync_active_excels.py` | Copy stats Excel files into `data/raw_excel/` |
| `ingest_excel.py` | Ingest one tehsil Excel + fetch MWS/village geometries |
| `batch_ingest_excel.py` | Batch ingest from synced Excel catalog |
| `fetch_papers.py` | Download papers per pathway; build `fetch_manifest.json` |
| `chunk_and_embed.py` | Chunk PDFs and embed into `paper_chunks` |
| `generate_evidence_cards.py` | Extract evidence cards (Claude) + embed + Mongo |
| `reload_evidence_cards.py` | Reload raw card JSON → Mongo with fresh embeddings |
| `reembed_evidence_cards.py` | Re-embed cards after alias changes (`--apply`) |
| `build_spatial_index.py` | Export tehsil spatial index for the frontend |
| `patch_framework_expression_vars.py` | Add framework variables referenced in card expressions |

Paper manifest helpers: `validate_manifest.py`, `sync_manifest_pdfs.py`, `restore_manifest_exclusions.py`

### After Excel re-ingest — refresh MWS exports

Mongo ingest alone does not update `data/raw_jsons/`. Downstream tools (triage dashboard, tuning, query eval) read cached assembler exports. **Required after every re-ingest:**

```powershell
# Case-study snapshots (tuning, query eval)
.\.venv\Scripts\python.exe scripts/export_case_study_mws_variables.py

# Full corpus + variable dashboard (pass --refresh-exports so CDFs use fresh Mongo values)
.\.venv\Scripts\python.exe scripts/triage/build_variable_dashboard.py --refresh-exports
```

See `cursor-plans/00-tooling-registry.md` → **Post Excel re-ingest**.

| Script | Purpose |
|--------|---------|
| `export_case_study_mws_variables.py` | Case-study MWS → `data/raw_jsons/` (with `case_study_refs`) |

## `lib/` — shared modules

| Module | Used by |
|--------|---------|
| `lib/card_embedding_text.py` | Evidence card embed text + semantic aliases |
| `lib/expression_audit.py` | Variable/expression audit helpers |
| `lib/tehsil_excel_catalog.py` | `batch_ingest_excel.py`, `sync_active_excels.py`, verify audit |
| `lib/excel_audit.py` | `sync_active_excels.py`, `verify/audit_excel_core_stack.py` |
| `lib/card_policy_utils.py` | Plan 13 policy derive/apply + verify audits |
| `lib/follow_up_utils.py` | `propagate_follow_up_templates.py` |
| `lib/policy_overrides.py` | `derive_confirmation_policy.py`, `apply_policy_corrections.py` |
| `lib/aer_lookup.py` | AER GeoJSON fetch + backfill |

## `verify/` — post-step checks & audit gates

| Script | Checks |
|--------|--------|
| `verify/verify_ingest.py` | MWS/village counts, drought key normalization |
| `verify/verify_papers.py` | `fetch_manifest.json` vs PDFs on disk |
| `verify/verify_chunks.py` | `paper_chunks` counts and embeddings |
| `verify/verify_evidence_cards.py` | `evidence_cards` counts |
| `verify/audit_chunk_coverage.py` | Chunk coverage for corpus papers |
| `verify/audit_excel_core_stack.py` | Excel sheets vs CoRE Stack API |
| `verify/audit_variable_registry.py` | Registry ↔ framework ↔ assembler ↔ cards |
| `verify/evaluate_signal_matrix.py` | Full signal eval matrix (0 hard errors gate) |
| `verify/spot_check_resolvers.py` | Variable resolver spot checks |
| `verify/audit_confirmation_policy.py` | Plan 13 — policy vs signals / prose; writes `reports/policy_review/policy_audit*.csv` |
| `verify/audit_follow_up_effects.py` | Plan 13 — MCQ `effects.signals` coverage; writes `reports/policy_review/follow_up_effects_audit.csv` |
| `verify/audit_mcq_normalized.py` | Plan 13 — MCQ `normalized` shape consistency |
| `verify/audit_card_expressions.py` | Plan 15 — per-card expression audit CSV |
| `verify/audit_card_schema.py` | Plan 15 — JSON Schema validate raw cards |
| `verify/generate_review_catalog.py` | Local CSV catalogs in `reports/policy_review/` + `REVIEW_WORKFLOW.md` (gitignored) |

## `eval/` — case-study diagnosis batch

| Script | Purpose |
|--------|---------|
| `eval/run_case_study_diagnoses.py` | POST `/api/query` for each case-study MWS (initial turn only); writes CSV/JSON + replay baseline |
| `eval/case_study_index.py` | Load flat rows from `metadata/case_study_locations_v2.json` |

**Server-only batch** (creates real sessions + feedback URLs):

```powershell
.\.venv\Scripts\python.exe scripts/eval/run_case_study_diagnoses.py --dry-run
.\.venv\Scripts\python.exe scripts/eval/run_case_study_diagnoses.py
```

**LLM reviewer batch** (same generic problem text for every MWS):

```powershell
.\.venv\Scripts\python.exe scripts/eval/run_case_study_diagnoses.py --want-llm --problem "What landscape stresses and production-system problems exist in this micro-watershed?"
```

Outputs land in `reports/case_study_eval/` including `replay_baseline_{server|llm}_{stamp}.json`. Compare with Claude via:

```powershell
.\.venv\Scripts\python.exe scripts/replay_diagnosis_runs.py replay --baseline reports/case_study_eval/replay_baseline_server_<stamp>.json
```

Requires FastAPI on `http://127.0.0.1:8000` and Mongo loaded.

## `review/` — Plan 15 Claude corpus review

| Script | Purpose |
|--------|---------|
| `review/run_preflight.py` | Run all preflight audits; index by `card_id` |
| `review/claude_card_reviewer.py` | One Claude call per card (`--dry-run`, `--resume`, `--pathway`) |
| `review/merge_claude_review_report.py` | Merge results → summary MD, CSV, patches JSON |
| `review/apply_claude_review_patches.py` | Apply approved patches (`--dry-run` / `--apply`; reads `metadata/claude_review_edited_patches.json`) |

**Human review UI:** `http://localhost:5173/revise-cards` (Plan 16) — finalize per card → `metadata/claude_review_decisions.json` + `metadata/claude_review_edited_patches.json`.

## `test/` — unit / smoke tests (no pytest required)

| Script | Tests |
|--------|-------|
| `test/test_variable_registry.py` | Canonical names, aliases, expression rewrites |
| `test/test_derived_variables.py` | Derived MWS variables |
| `test/test_expression_audit.py` | Expression audit severities |
| `test/test_expression_eval_fixes.py` | Eval context edge cases (absent org/river fields) |
| `test/test_signal_evaluator.py` | Signal expression evaluation |
| `test/test_signal_evaluator_matrix.py` | CI wrapper for signal matrix gate |
| `test/test_follow_up_signals.py` | Follow-up answer → signal eval |
| `test/test_follow_up_effects.py` | Plan 13 — MCQ `effects` path |
| `test/test_confirmation_policy.py` | Plan 13 — confirmation policy runtime |
| `test/test_card_policy_utils.py` | Policy derive/apply helpers |
| `test/test_diagnosis_revision.py` | Follow-up diagnosis revision |
| `test/test_diagnosis_snapshot.py` | Diagnosis snapshot IDs |
| `test/test_feedback_context.py` | Feedback context API |
| `test/test_feedback_store.py` | Feedback Mongo upsert |
| `test/test_evidence_card_api.py` | Evidence card read API |
| `test/test_evidence_suggestions_store.py` | Evidence suggestion store |
| `test/test_prompt_builder.py` | Reasoner prompt shape + signal blocks |
| `test/test_parse_json_response.py` | LLM JSON parse/repair |
| `test/test_retrieval_and_followup.py` | Retrieval diversity + follow-up order |
| `test/test_retriever_aer.py` | AER-tagged retrieval |
| `test/test_aer_alignment.py` | AER alignment classification |
| `test/test_pathway_filter.py` | Pathway list normalization |
| `test/test_variable_bundle.py` | Present/missing variable bundling |
| `test/test_card_embedding_text.py` | Alias-augmented embedding text |
| `test/test_tehsil_refs.py` | Multi-tehsil MWS membership |
| `test/test_diagnosis_logging.py` | Diagnosis trace logging |
| `test/test_panel_updates.py` | Panel update mapping (extend for new pathways) |
| `test/smoke_test_diagnosis.py` | Live API smoke tests |

## `tuning/` — signal expression fine-tuning (Plan 14 Phase 3)

Uses `expression_tuning_algorithm_v4.md`: empirical threshold grids, production `signal_evaluator`, pathway-level `confirmation_policy` objective.

```powershell
# One pathway
.\.venv\Scripts\python.exe scripts/tuning/tune_pathway_signals.py --pathway drought --write-patches

# All built pathways → reports + triage patches
.\.venv\Scripts\python.exe scripts/tuning/tune_pathway_signals.py --all-built --write-patches
```

| Output | Location |
|--------|----------|
| Per-pathway JSON + MD | `reports/signal_tuning/{pathway}_tuning_report.*` |
| Summary CSV | `reports/signal_tuning/summary.csv` |
| Triage patches (review) | `metadata/triage_patches/case_study_locations_signal_tuning.json` |

**Review in triaging app:** select catalog **`case_study_locations_signal_tuning.json`** (same case-study instances as v3). Patches overlay proposed signal expressions; use Play to compare, then Save patches / revise-cards when satisfied.

**Prerequisite:** fresh `data/raw_jsons/` after re-ingest (`export_case_study_mws_variables.py`).

## `triage/` — case-study triaging dashboards

| Script | Purpose |
|--------|---------|
| `triage/build_variable_dashboard.py` | Precompute global variable CDFs per `(production_system, observed_stress)` → `data/triage_dashboard/` |

```powershell
.\.venv\Scripts\python.exe scripts/triage/build_variable_dashboard.py
.\.venv\Scripts\python.exe scripts/triage/build_variable_dashboard.py --section Agriculture/water_scarcity
# After Excel re-ingest — refresh all MWS exports from Mongo, then rebuild CDFs:
.\.venv\Scripts\python.exe scripts/triage/build_variable_dashboard.py --refresh-exports
```

## `maintenance/` — occasional ops

| Script | Purpose |
|--------|---------|
| `maintenance/normalize_evidence_card_expressions.py` | Registry-based expression rewrites on raw cards; also syncs `variables` into user-edit patches |
| `maintenance/sync_user_edit_patches_from_raw.py` | Refresh user-edit patches + `applied_card_digest` from current raw cards (run after raw maintenance) |
| `maintenance/align_qualitative_descriptions.py` | Template-based `qualitative_description` alignment; mirrors qual into user-edit patches |
| `maintenance/derive_confirmation_policy.py` | Auto-generate `confirmation_policy` from signals + note |
| `maintenance/apply_policy_corrections.py` | Apply reviewed policy corrections to raw cards |
| `maintenance/propagate_follow_up_templates.py` | Propagate reviewed follow-up templates by fingerprint |
| `maintenance/sync_context_clusters.py` | Export `CONTEXT_CLUSTERS` → `metadata/context_clusters.json` |
| `maintenance/audit_evidence_card_prompts.py` | Prompt / JSON staleness audit |
| `maintenance/audit_aer_card_coverage.py` | AER tag coverage vs NBSS-LUP regions |
| `maintenance/audit_follow_up_mcq_coverage.py` | MCQ wiring coverage report |
| `maintenance/wire_follow_up_signals.py` | Pathway induction — wire follow-up questions → signals |
| `maintenance/preview_card_embedding_text.py` | Preview embed text before re-embed |
| `maintenance/backfill_mws_variable_names.py` | Drought nested key backfill (idempotent) |
| `maintenance/backfill_mws_tehsils.py` | Multi-tehsil `tehsils[]` backfill |
| `maintenance/backfill_mws_aer.py` | AER code point-in-polygon backfill |
| `maintenance/fetch_aer_geojson.py` | Download NBSS-LUP AER GeoJSON |
| `maintenance/purge_pathway_from_mongo.py` | Remove a pathway's evidence cards |
| `maintenance/purge_excluded_chunks.py` | Drop chunks for excluded papers |

## `archive/` — applied one-off migrations

See `archive/README.md`. Re-run only when re-importing pre-migration card JSON.

## `reference/`

| File | Notes |
|------|-------|
| `reference/embed_utils.py` | Reference only; canonical code is `scripts/lib/card_embedding_text.py` |

## Removed (2026-06-19)

`strip_legacy_signal_fields.py`, `apply_follow_up_mcq_templates.py`, `propagate_confirmation_policies.py`, `write_policy_review_doc.py`, `mapwiki/` — see plan 05 script inventory.

**Earlier removals:** `patch_deccan_aer_tags.py`, `test/test_bundle_signal_eval.py`.

## Dependencies

```powershell
pip install -r scripts/requirements.txt
```
