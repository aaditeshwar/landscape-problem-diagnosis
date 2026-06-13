# Scripts layout

Python tooling for preprocessing, evidence cards, and diagnostics. Run from the repo root:

```powershell
.venv\Scripts\python.exe scripts\<script>.py [args]
```

Shared bootstrap: `scripts/_bootstrap.py` (repo `ROOT`, optional `runtime/` on `sys.path`).

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

Paper manifest helpers: `validate_manifest.py`, `sync_manifest_pdfs.py`, `restore_manifest_exclusions.py`

## `lib/` — shared modules

| Module | Used by |
|--------|---------|
| `lib/card_embedding_text.py` | Evidence card embed text + semantic aliases |
| `lib/tehsil_excel_catalog.py` | `batch_ingest_excel.py`, `sync_active_excels.py`, verify audit |
| `lib/excel_audit.py` | `sync_active_excels.py`, `verify/audit_excel_core_stack.py` |

## `verify/` — post-step checks

| Script | Checks |
|--------|--------|
| `verify/verify_ingest.py` | MWS/village counts, sample MWS fields |
| `verify/verify_papers.py` | `fetch_manifest.json` vs PDFs on disk |
| `verify/verify_chunks.py` | `paper_chunks` counts and embeddings |
| `verify/verify_evidence_cards.py` | `evidence_cards` counts |
| `verify/audit_chunk_coverage.py` | Chunk coverage for corpus papers |
| `verify/audit_excel_core_stack.py` | Excel sheets vs CoRE Stack API |
| `verify/spot_check_resolvers.py` | Variable resolver spot checks |

## `test/` — unit / smoke tests (no pytest required)

| Script | Tests |
|--------|-------|
| `test/test_derived_variables.py` | Derived MWS variables |
| `test/test_card_embedding_text.py` | Alias-augmented embedding text |
| `test/test_retrieval_and_followup.py` | Retrieval diversity + follow-up order |
| `test/test_diagnosis_revision.py` | Follow-up diagnosis revision |
| `test/test_panel_updates.py` | Panel update mapping |
| `test/smoke_test_diagnosis.py` | Live API smoke tests |

## `maintenance/` — occasional ops

| Script | Purpose |
|--------|---------|
| `maintenance/preview_card_embedding_text.py` | Preview embed text before re-embed |
| `maintenance/purge_pathway_from_mongo.py` | Remove a pathway's evidence cards |
| `maintenance/purge_excluded_chunks.py` | Drop chunks for excluded papers |

## `reference/`

| File | Notes |
|------|-------|
| `reference/embed_utils.py` | Reference only; canonical code is `scripts/lib/card_embedding_text.py` |

## Dependencies

```powershell
pip install -r scripts/requirements.txt
```
