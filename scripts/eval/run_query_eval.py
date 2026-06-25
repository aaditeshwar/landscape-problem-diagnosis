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
    diagnostics_url,
    evaluation_artifact_name,
    response_artifact_name,
    session_ref,
)
from eval.rubric_evaluator import evaluate_response  # noqa: E402
from services.llm_client import llm_provider_override  # noqa: E402
from services.query_eval_store import (  # noqa: E402
    batch_dir,
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


def run_batch(
    *,
    case_studies: list[dict[str, Any]],
    frontend_base: str,
    batch_id: str,
    limit_queries: int | None,
    skip_eval: bool,
    evaluator_provider: str,
    dry_run: bool,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
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
        if limit_queries is not None:
            # Q000 always included; limit applies to additional bank queries
            queries = queries[: 1 + limit_queries]

        case_study_id = row.get("case_study_id")
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
            manifest["case_studies"].append(cs_entry)
            continue

        print(f"Case study {case_study_id} · {mws_id} · {len(queries)} queries")

        server_diagnosis: dict[str, Any] | None = None
        try:
            started = time.perf_counter()
            server_diagnosis = _run_diagnosis(
                mws_id,
                problem_description="",
                want_llm_opinion=False,
                llm_provider=None,
            )
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            cs_entry["sessions"]["server"] = {**session_ref(server_diagnosis, frontend_base), "elapsed_ms": elapsed}
            write_response_artifact(batch_id, response_artifact_name(case_study_id, None, "server"), server_diagnosis)
            print(f"  server session={server_diagnosis.get('session_id')} ({elapsed}ms)")
        except Exception as exc:
            cs_entry["sessions"]["server"] = {"error": str(exc)}
            print(f"  server FAILED: {exc}")

        for query in queries:
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
                    diagnosis = _run_diagnosis(
                        mws_id,
                        problem_description=query_text,
                        want_llm_opinion=True,
                        llm_provider=provider,
                    )
                    elapsed = round((time.perf_counter() - started) * 1000, 2)
                    query_run["sessions"][mode] = {
                        **session_ref(diagnosis, frontend_base),
                        "elapsed_ms": elapsed,
                        "llm_provider": provider,
                    }
                    write_response_artifact(
                        batch_id,
                        response_artifact_name(case_study_id, query_id, mode),
                        diagnosis,
                    )
                    if mode == "llm_ollama":
                        ollama_diagnosis = diagnosis
                    else:
                        claude_diagnosis = diagnosis
                    print(f"  {query_id} {mode} session={diagnosis.get('session_id')} ({elapsed}ms)")
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
                        evaluation = evaluate_response(
                            query=query,
                            diagnosis=diagnosis,
                            mws_variable_summary=mws_summary,
                            mode=mode,
                            evaluator_provider=evaluator_provider,
                            case_study=case_study_meta,
                            server_diagnosis=server_diagnosis,
                        )
                        query_run["evaluations"][mode] = evaluation
                        write_evaluation_artifact(
                            batch_id,
                            evaluation_artifact_name(case_study_id, query_id, mode),
                            evaluation,
                        )
                    except Exception as exc:
                        query_run["evaluations"][mode] = {"error": str(exc)}
                        print(f"  {query_id} {mode} eval FAILED: {exc}")

            cs_entry["query_runs"].append(query_run)
            manifest["runs"].append({"case_study_id": case_study_id, "mws_id": mws_id, **query_run})

        manifest["case_studies"].append(cs_entry)

    return save_batch(manifest)


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
    parser.add_argument("--batch-id", default="", help="Override batch id")
    parser.add_argument("--batch-label", default="pilot", help="Label for auto batch id")
    parser.add_argument("--frontend-base", default="http://localhost:5173")
    parser.add_argument("--evaluator-provider", choices=["anthropic", "ollama"], default="anthropic")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = enrich_case_study_rows(load_case_study_rows(include_stress_only=args.include_stress_only))
    if args.case_study_ids:
        wanted = set(args.case_study_ids)
        rows = [r for r in rows if r.get("case_study_id") in wanted]
    rows = dedupe_rows_by_mws(rows)
    if not rows:
        print("No case studies matched filters", file=sys.stderr)
        return 1

    limit_queries = args.limit_queries or None
    batch_id = args.batch_id.strip() or new_batch_id(args.batch_label)

    manifest = run_batch(
        case_studies=rows,
        frontend_base=args.frontend_base,
        batch_id=batch_id,
        limit_queries=limit_queries,
        skip_eval=args.skip_eval,
        evaluator_provider=args.evaluator_provider,
        dry_run=args.dry_run,
    )

    print(f"Wrote batch {manifest.get('batch_id')}")
    print(f"Case studies: {len(manifest.get('case_studies') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
