#!/usr/bin/env python3
"""Run query-bank evaluation for case-study MWS locations (server + LLM modes)."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = ROOT / "runtime"
SCRIPTS_DIR = ROOT / "scripts"
for path in (RUNTIME_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

load_dotenv(ROOT / ".env")

from eval.case_study_index import (  # noqa: E402
    enrich_case_study_rows,
    load_case_study_rows,
)
from eval.pathway_agreement import query_run_agreement  # noqa: E402
from eval.query_bank_index import excluded_queries, queries_for_case_study  # noqa: E402
from eval.query_eval_common import (  # noqa: E402
    EVAL_MODES,
    case_study_queries_complete,
    diagnostics_url,
    evaluation_artifact_name,
    load_evaluation_artifact,
    load_response_artifact,
    missing_query_run_artifacts,
    response_artifact_name,
    session_ref,
)
from eval.rubric_evaluator import evaluate_response  # noqa: E402
from services.llm_client import llm_provider_override  # noqa: E402
from services.query_eval_store import (  # noqa: E402
    batch_dir,
    batch_manifest_path,
    latest_batch_id_for_label,
    load_batch,
    new_batch_id,
    save_batch,
    write_evaluation_artifact,
    write_response_artifact,
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_mws_variable_summary(mws_id: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if mws_id in cache:
        return cache[mws_id]
    import json
    from services.signal_evaluator import merge_export_variables  # noqa: E402

    path = ROOT / "data" / "raw_jsons" / f"{mws_id}.json"
    if path.is_file():
        export = json.loads(path.read_text(encoding="utf-8"))
        merged = merge_export_variables(export)
        cache[mws_id] = {k: v for k, v in merged.items() if v is not None}
        return cache[mws_id]
    cache[mws_id] = {}
    return {}


def _run_diagnosis(
    mws_id: str,
    *,
    problem_description: str,
    want_llm_opinion: bool,
    llm_provider: str | None,
) -> dict[str, Any]:
    from routers.query import _load_mws, _run_query  # noqa: E402

    mws_doc = _load_mws(mws_id)
    with llm_provider_override(llm_provider):
        return _run_query(
            mws_doc,
            problem_description,
            session_id=None,
            want_llm_opinion=want_llm_opinion,
        )


def _rebuild_runs(manifest: dict[str, Any]) -> None:
    manifest["runs"] = []
    for cs_entry in manifest.get("case_studies") or []:
        case_study_id = cs_entry.get("case_study_id")
        mws_id = cs_entry.get("mws_id")
        for query_run in cs_entry.get("query_runs") or []:
            manifest["runs"].append(
                {"case_study_id": case_study_id, "mws_id": mws_id, **query_run},
            )


def _merge_cs_entry(existing: dict[str, Any] | None, cs_entry: dict[str, Any]) -> dict[str, Any]:
    if not existing:
        return cs_entry
    merged = {**existing, **cs_entry}
    runs_by_id = {
        str(row.get("query_id") or ""): row for row in (existing.get("query_runs") or []) if row.get("query_id")
    }
    for row in cs_entry.get("query_runs") or []:
        qid = str(row.get("query_id") or "")
        if qid:
            runs_by_id[qid] = row
    merged["query_runs"] = sorted(
        runs_by_id.values(),
        key=lambda row: (0 if row.get("query_id") == "Q000" else 1, str(row.get("query_id") or "")),
    )
    merged["query_ids"] = sorted(set((existing.get("query_ids") or []) + (cs_entry.get("query_ids") or [])))
    merged["sessions"] = {**(existing.get("sessions") or {}), **(cs_entry.get("sessions") or {})}
    return merged


def _upsert_case_study(manifest: dict[str, Any], cs_entry: dict[str, Any]) -> None:
    mws_id = str(cs_entry.get("mws_id") or "")
    existing = next(
        (row for row in (manifest.get("case_studies") or []) if str(row.get("mws_id") or "") == mws_id),
        None,
    )
    merged_entry = _merge_cs_entry(existing, cs_entry)
    kept = [
        row
        for row in (manifest.get("case_studies") or [])
        if str(row.get("mws_id") or "") != mws_id
    ]
    kept.append(merged_entry)
    manifest["case_studies"] = sorted(kept, key=lambda row: (int(row.get("case_study_id") or 0), str(row.get("mws_id") or "")))
    _rebuild_runs(manifest)


def _load_or_run_diagnosis(
    batch_id: str,
    case_study_id: int | str,
    *,
    mws_id: str,
    query_id: str | None,
    mode: str,
    problem_description: str,
    want_llm_opinion: bool,
    llm_provider: str | None,
) -> tuple[dict[str, Any] | None, bool]:
    """Return (diagnosis, loaded_from_disk)."""
    artifact_mode = "server" if mode == "server" else mode
    filename = response_artifact_name(case_study_id, query_id, artifact_mode)
    existing = load_response_artifact(batch_id, filename)
    if existing:
        return existing, True
    diagnosis = _run_diagnosis(
        mws_id,
        problem_description=problem_description,
        want_llm_opinion=want_llm_opinion,
        llm_provider=llm_provider,
    )
    write_response_artifact(batch_id, filename, diagnosis)
    return diagnosis, False


def _load_or_evaluate(
    batch_id: str,
    *,
    case_study_id: int | str,
    query_id: str,
    mode: str,
    query: dict[str, Any],
    diagnosis: dict[str, Any] | None,
    mws_summary: dict[str, Any],
    evaluator_provider: str,
    case_study_meta: dict[str, Any],
    server_diagnosis: dict[str, Any] | None,
) -> dict[str, Any]:
    filename = evaluation_artifact_name(case_study_id, query_id, mode)
    existing = load_evaluation_artifact(batch_id, filename)
    if existing and not existing.get("error"):
        return existing
    if not diagnosis:
        return {"error": f"no diagnosis for {mode}"}
    evaluation = evaluate_response(
        query=query,
        diagnosis=diagnosis,
        mws_variable_summary=mws_summary,
        mode=mode,
        evaluator_provider=evaluator_provider,
        case_study=case_study_meta,
        server_diagnosis=server_diagnosis,
    )
    write_evaluation_artifact(batch_id, filename, evaluation)
    return evaluation


def _process_query_run(
    *,
    batch_id: str,
    case_study_id: int | str,
    mws_id: str,
    query: dict[str, Any],
    frontend_base: str,
    server_diagnosis: dict[str, Any] | None,
    skip_eval: bool,
    evaluator_provider: str,
    case_study_meta: dict[str, Any],
    present_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    query_id = str(query.get("id") or "")
    query_text = str(query.get("query") or "")
    query_run: dict[str, Any] = {
        "query_id": query_id,
        "persona": query.get("persona"),
        "production_system": query.get("production_system"),
        "query": query_text,
        "expected_pathway_candidates": query.get("expected_pathway_candidates"),
        "sessions": {},
        "evaluations": {},
        "agreement": {},
    }

    ollama_diagnosis: dict[str, Any] | None = None
    claude_diagnosis: dict[str, Any] | None = None

    for mode, provider in (("llm_ollama", "ollama"), ("llm_claude", "anthropic")):
        try:
            started = time.perf_counter()
            diagnosis, loaded = _load_or_run_diagnosis(
                batch_id,
                case_study_id,
                mws_id=mws_id,
                query_id=query_id,
                mode=mode,
                problem_description=query_text,
                want_llm_opinion=True,
                llm_provider=provider,
            )
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            query_run["sessions"][mode] = {
                **session_ref(diagnosis, frontend_base),
                "elapsed_ms": None if loaded else elapsed,
                "llm_provider": provider,
            }
            if mode == "llm_ollama":
                ollama_diagnosis = diagnosis
            else:
                claude_diagnosis = diagnosis
            action = "loaded" if loaded else "ran"
            print(f"  {query_id} {mode} {action} session={diagnosis.get('session_id')}")
        except Exception as exc:
            query_run["sessions"][mode] = {"error": str(exc)}
            print(f"  {query_id} {mode} FAILED: {exc}")

    query_run["agreement"] = query_run_agreement(
        server_diagnosis=server_diagnosis,
        ollama_diagnosis=ollama_diagnosis,
        claude_diagnosis=claude_diagnosis,
    )

    if not skip_eval:
        mws_summary = _load_mws_variable_summary(mws_id, present_cache)
        eval_plan: list[tuple[str, dict[str, Any] | None]] = [
            ("server", server_diagnosis),
            ("llm_ollama", ollama_diagnosis),
            ("server_plus_llm_ollama", ollama_diagnosis),
            ("llm_claude", claude_diagnosis),
        ]
        for mode, diagnosis in eval_plan:
            if not diagnosis:
                continue
            try:
                missing = missing_query_run_artifacts(batch_id, case_study_id, query_id)
                if f"{mode}_eval" not in missing:
                    query_run["evaluations"][mode] = load_evaluation_artifact(
                        batch_id,
                        evaluation_artifact_name(case_study_id, query_id, mode),
                    ) or {}
                    continue
                print(f"  Evaluating {query_id} · {mode}")
                query_run["evaluations"][mode] = _load_or_evaluate(
                    batch_id,
                    case_study_id=case_study_id,
                    query_id=query_id,
                    mode=mode,
                    query=query,
                    diagnosis=diagnosis,
                    mws_summary=mws_summary,
                    evaluator_provider=evaluator_provider,
                    case_study_meta=case_study_meta,
                    server_diagnosis=server_diagnosis,
                )
            except Exception as exc:
                query_run["evaluations"][mode] = {"error": str(exc)}
                print(f"  {query_id} {mode} eval FAILED: {exc}")

    return query_run


def _build_cs_entry_from_artifacts(
    row: dict[str, Any],
    queries: list[dict[str, Any]],
    *,
    batch_id: str,
    frontend_base: str,
) -> dict[str, Any] | None:
    case_study_id = row.get("case_study_id")
    mws_id = str(row.get("mws_id") or "")
    query_ids = [str(q.get("id") or "") for q in queries]
    if not case_study_queries_complete(batch_id, case_study_id, query_ids):
        return None

    server_diagnosis = load_response_artifact(
        batch_id,
        response_artifact_name(case_study_id, None, "server"),
    )
    cs_entry: dict[str, Any] = {
        "case_study_id": case_study_id,
        "mws_id": mws_id,
        "tehsil": row.get("tehsil"),
        "district": row.get("district"),
        "state": row.get("state"),
        "production_system": row.get("production_system") or "",
        "observed_stress": row.get("observed_stress") or "",
        "expected_pathway": row.get("expected_pathway") or "",
        "stress_only": bool(row.get("stress_only")),
        "diagnostics_url": diagnostics_url(frontend_base, mws_id),
        "query_ids": query_ids,
        "sessions": {},
        "query_runs": [],
    }
    if server_diagnosis:
        cs_entry["sessions"]["server"] = session_ref(server_diagnosis, frontend_base)

    for query in queries:
        query_id = str(query.get("id") or "")
        query_run: dict[str, Any] = {
            "query_id": query_id,
            "persona": query.get("persona"),
            "production_system": query.get("production_system"),
            "query": str(query.get("query") or ""),
            "expected_pathway_candidates": query.get("expected_pathway_candidates"),
            "sessions": {},
            "evaluations": {},
            "agreement": {},
        }
        ollama = load_response_artifact(batch_id, response_artifact_name(case_study_id, query_id, "llm_ollama"))
        claude = load_response_artifact(batch_id, response_artifact_name(case_study_id, query_id, "llm_claude"))
        if ollama:
            query_run["sessions"]["llm_ollama"] = {**session_ref(ollama, frontend_base), "llm_provider": "ollama"}
        if claude:
            query_run["sessions"]["llm_claude"] = {**session_ref(claude, frontend_base), "llm_provider": "anthropic"}
        query_run["agreement"] = query_run_agreement(
            server_diagnosis=server_diagnosis,
            ollama_diagnosis=ollama,
            claude_diagnosis=claude,
        )
        for mode in EVAL_MODES:
            ev = load_evaluation_artifact(batch_id, evaluation_artifact_name(case_study_id, query_id, mode))
            if ev:
                query_run["evaluations"][mode] = ev
        cs_entry["query_runs"].append(query_run)

    return cs_entry


def sync_artifacts_to_manifest(
    manifest: dict[str, Any],
    *,
    batch_id: str,
    rows: list[dict[str, Any]],
    frontend_base: str,
    query_ids: set[str] | None,
    limit_queries: int | None,
) -> int:
    synced = 0
    for row in rows:
        queries = queries_for_case_study(row)
        if query_ids:
            queries = [query for query in queries if str(query.get("id") or "") in query_ids]
        if limit_queries is not None:
            queries = queries[: 1 + limit_queries]
        if not queries:
            continue
        cs_entry = _build_cs_entry_from_artifacts(row, queries, batch_id=batch_id, frontend_base=frontend_base)
        if cs_entry:
            _upsert_case_study(manifest, cs_entry)
            synced += 1
            print(f"Synced case study {row.get('case_study_id')} · {row.get('mws_id')} from artifacts")
    if synced:
        save_batch(manifest)
    return synced


def run_batch(
    *,
    case_studies: list[dict[str, Any]],
    frontend_base: str,
    batch_id: str,
    limit_queries: int | None,
    query_ids: set[str] | None,
    skip_eval: bool,
    skip_complete: bool,
    evaluator_provider: str,
    dry_run: bool,
    base_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if base_manifest:
        manifest: dict[str, Any] = dict(base_manifest)
        manifest["batch_id"] = batch_id
        manifest["dry_run"] = dry_run
        manifest["excluded_queries"] = excluded_queries()
        manifest["modes"] = list(EVAL_MODES)
    else:
        manifest = {
            "batch_id": batch_id,
            "generated_at": _utc_iso(),
            "catalog": "case_study_locations_v3.json",
            "modes": list(EVAL_MODES),
            "dry_run": dry_run,
            "excluded_queries": excluded_queries(),
            "case_studies": [],
            "runs": [],
        }

    if not dry_run:
        batch_dir(batch_id).mkdir(parents=True, exist_ok=True)

    present_cache: dict[str, dict[str, Any]] = {}

    for row in case_studies:
        mws_id = str(row.get("mws_id") or "")
        queries = queries_for_case_study(row)
        if query_ids:
            queries = [query for query in queries if str(query.get("id") or "") in query_ids]
        if limit_queries is not None:
            # Q000 always included; limit applies to additional bank queries
            queries = queries[: 1 + limit_queries]
        if not queries:
            print(f"Case study {row.get('case_study_id')} · {mws_id} — no queries matched filters", file=sys.stderr)
            continue

        case_study_id = row.get("case_study_id")
        filtered_query_ids = [str(q.get("id") or "") for q in queries]

        if skip_complete and case_study_queries_complete(batch_id, case_study_id, filtered_query_ids):
            cs_entry = _build_cs_entry_from_artifacts(
                row, queries, batch_id=batch_id, frontend_base=frontend_base,
            )
            if cs_entry:
                _upsert_case_study(manifest, cs_entry)
                save_batch(manifest)
                print(f"Case study {case_study_id} · {mws_id} — complete, synced from artifacts")
            else:
                print(f"Case study {case_study_id} · {mws_id} — complete, already in manifest")
            continue

        case_study_meta = {
            "case_study_id": case_study_id,
            "mws_id": mws_id,
            "tehsil": row.get("tehsil"),
            "district": row.get("district"),
            "state": row.get("state"),
        }

        cs_entry: dict[str, Any] = {
            **case_study_meta,
            "production_system": row.get("production_system") or "",
            "observed_stress": row.get("observed_stress") or "",
            "expected_pathway": row.get("expected_pathway") or "",
            "stress_only": bool(row.get("stress_only")),
            "diagnostics_url": diagnostics_url(frontend_base, mws_id),
            "query_ids": [q.get("id") for q in queries],
            "sessions": {},
            "query_runs": [],
        }

        if dry_run:
            _upsert_case_study(manifest, cs_entry)
            continue

        print(f"Case study {case_study_id} · {mws_id} · {len(queries)} queries")

        server_diagnosis: dict[str, Any] | None = None
        try:
            started = time.perf_counter()
            server_diagnosis, loaded = _load_or_run_diagnosis(
                batch_id,
                case_study_id,
                mws_id=mws_id,
                query_id=None,
                mode="server",
                problem_description="",
                want_llm_opinion=False,
                llm_provider=None,
            )
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            cs_entry["sessions"]["server"] = {
                **session_ref(server_diagnosis, frontend_base),
                "elapsed_ms": None if loaded else elapsed,
            }
            action = "loaded" if loaded else "ran"
            print(f"  server {action} session={server_diagnosis.get('session_id')}" + ("" if loaded else f" ({elapsed}ms)"))
        except Exception as exc:
            cs_entry["sessions"]["server"] = {"error": str(exc)}
            print(f"  server FAILED: {exc}")

        for query in queries:
            query_run = _process_query_run(
                batch_id=batch_id,
                case_study_id=case_study_id,
                mws_id=mws_id,
                query=query,
                frontend_base=frontend_base,
                server_diagnosis=server_diagnosis,
                skip_eval=skip_eval,
                evaluator_provider=evaluator_provider,
                case_study_meta=case_study_meta,
                present_cache=present_cache,
            )
            cs_entry["query_runs"].append(query_run)

        _upsert_case_study(manifest, cs_entry)
        save_batch(manifest)
        print(f"  saved manifest ({len(manifest.get('case_studies') or [])} case studies)")

    return manifest


def dedupe_rows_by_mws(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        mws_id = str(row.get("mws_id") or "").strip()
        if not mws_id or mws_id in seen:
            continue
        seen.add(mws_id)
        out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-study-id", type=int, action="append", dest="case_study_ids")
    parser.add_argument("--include-stress-only", action="store_true")
    parser.add_argument(
        "--limit-queries",
        type=int,
        default=0,
        help="Max bank queries per case study excluding Q000 (0=all)",
    )
    parser.add_argument("--batch-id", default="", help="Use or append to an existing batch id")
    parser.add_argument(
        "--batch-label",
        default="pilot_v3",
        help="Label for auto batch id; reuses the latest matching batch when present",
    )
    parser.add_argument(
        "--query-id",
        action="append",
        dest="query_ids",
        help="Run only these query ids (must be eligible for the case study)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Merge results into an existing batch (requires --batch-id or an existing --batch-label batch)",
    )
    parser.add_argument("--mws-id", action="append", dest="mws_ids", help="Run only these MWS ids (bypasses mws dedupe)")
    parser.add_argument(
        "--skip-complete",
        action="store_true",
        help="Skip case studies whose on-disk artifacts are already complete",
    )
    parser.add_argument(
        "--sync-artifacts",
        action="store_true",
        help="Import complete case studies from on-disk artifacts into the manifest (no new runs)",
    )
    parser.add_argument("--frontend-base", default="http://localhost:5173")
    parser.add_argument("--evaluator-provider", choices=["anthropic", "ollama"], default="anthropic")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = enrich_case_study_rows(load_case_study_rows(include_stress_only=args.include_stress_only))
    if args.case_study_ids:
        wanted = set(args.case_study_ids)
        rows = [r for r in rows if r.get("case_study_id") in wanted]
    if args.mws_ids:
        wanted_mws = {str(m).strip() for m in args.mws_ids if str(m).strip()}
        rows = [r for r in rows if str(r.get("mws_id") or "").strip() in wanted_mws]
    else:
        rows = dedupe_rows_by_mws(rows)
    if not rows:
        print("No case studies matched filters", file=sys.stderr)
        return 1

    limit_queries = args.limit_queries or None
    query_ids = {str(qid).strip() for qid in (args.query_ids or []) if str(qid).strip()} or None

    batch_id = args.batch_id.strip()
    if not batch_id:
        batch_id = latest_batch_id_for_label(args.batch_label) or new_batch_id(args.batch_label)

    base_manifest: dict[str, Any] | None = None
    if batch_manifest_path(batch_id).is_file():
        base_manifest = load_batch(batch_id)
    elif args.append:
        print(f"Batch not found for append: {batch_id}", file=sys.stderr)
        return 1

    if args.sync_artifacts and not args.dry_run:
        manifest = base_manifest or {
            "batch_id": batch_id,
            "generated_at": _utc_iso(),
            "catalog": "case_study_locations_v3.json",
            "modes": list(EVAL_MODES),
            "dry_run": False,
            "excluded_queries": excluded_queries(),
            "case_studies": [],
            "runs": [],
        }
        synced = sync_artifacts_to_manifest(
            manifest,
            batch_id=batch_id,
            rows=rows,
            frontend_base=args.frontend_base,
            query_ids=query_ids,
            limit_queries=limit_queries,
        )
        base_manifest = manifest
        print(f"Synced {synced} complete case studies into {batch_id}")

    if args.sync_artifacts and args.dry_run:
        print("--sync-artifacts ignored in dry-run mode", file=sys.stderr)
        return 0

    manifest = run_batch(
        case_studies=rows,
        frontend_base=args.frontend_base,
        batch_id=batch_id,
        limit_queries=limit_queries,
        query_ids=query_ids,
        skip_eval=args.skip_eval,
        skip_complete=args.skip_complete,
        evaluator_provider=args.evaluator_provider,
        dry_run=args.dry_run,
        base_manifest=base_manifest if (args.append or base_manifest) else None,
    )

    if not args.dry_run:
        save_batch(manifest)

    print(f"Wrote batch {manifest.get('batch_id')}")
    print(f"Case studies: {len(manifest.get('case_studies') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
