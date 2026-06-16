# Scripts layout

Python tooling for preprocessing, evidence cards, and diagnostics. Run from the repo root:

```powershell
.venv\Scripts\python.exe scripts\<script>.py [args]
```

Shared bootstrap: `scripts/_bootstrap.py` (repo `ROOT`, optional `runtime/` on `sys.path`).

**Plans:** `cursor-plans/05-induct-new-pathway.md` (pathway induction), `cursor-plans/09-excel-source-update.md` (Excel changes).

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

## `lib/` — shared modules

| Module | Used by |
|--------|---------|
| `lib/card_embedding_text.py` | Evidence card embed text + semantic aliases |
| `lib/expression_audit.py` | Variable/expression audit helpers |
| `lib/tehsil_excel_catalog.py` | `batch_ingest_excel.py`, `sync_active_excels.py`, verify audit |
| `lib/excel_audit.py` | `sync_active_excels.py`, `verify/audit_excel_core_stack.py` |

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
| `test/test_diagnosis_revision.py` | Follow-up diagnosis revision |
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

## `maintenance/` — occasional ops

| Script | Purpose |
|--------|---------|
| `maintenance/normalize_evidence_card_expressions.py` | Registry-based expression rewrites on raw cards |
| `maintenance/audit_evidence_card_prompts.py` | Prompt / JSON staleness audit |
| `maintenance/audit_aer_card_coverage.py` | AER tag coverage vs NBSS-LUP regions |
| `maintenance/wire_follow_up_signals.py` | Wire follow-up questions → diagnostic signals |
| `maintenance/preview_card_embedding_text.py` | Preview embed text before re-embed |
| `maintenance/backfill_mws_variable_names.py` | Drought nested key backfill (idempotent) |
| `maintenance/backfill_mws_tehsils.py` | Multi-tehsil `tehsils[]` backfill |
| `maintenance/backfill_mws_aer.py` | AER code point-in-polygon backfill |
| `maintenance/fetch_aer_geojson.py` | Download NBSS-LUP AER GeoJSON |
| `maintenance/purge_pathway_from_mongo.py` | Remove a pathway's evidence cards |
| `maintenance/purge_excluded_chunks.py` | Drop chunks for excluded papers |

**Removed (obsolete):** `patch_deccan_aer_tags.py` (one-off AER patch), `test/test_bundle_signal_eval.py` (superseded by `test_follow_up_signals.py`).

## `reference/`

| File | Notes |
|------|-------|
| `reference/embed_utils.py` | Reference only; canonical code is `scripts/lib/card_embedding_text.py` |

## Dependencies

```powershell
pip install -r scripts/requirements.txt
```
