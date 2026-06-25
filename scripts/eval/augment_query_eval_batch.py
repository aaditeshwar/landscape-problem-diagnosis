#!/usr/bin/env python3
"""Augment an existing query-eval batch: fix links, Q000, server+ollama evals, agreement."""

from __future__ import annotations

import argparse
import json
import sys
import time
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

from eval.pathway_agreement import query_run_agreement  # noqa: E402
from eval.query_bank_index import built_systems_query  # noqa: E402
from eval.query_eval_common import (  # noqa: E402
    EVAL_MODES,
    evaluation_artifact_name,
    feedback_url,
    load_evaluation_artifact,
    load_response_artifact,
    response_artifact_name,
    session_ref,
)
from eval.rubric_evaluator import evaluate_response  # noqa: E402
from services.llm_client import llm_provider_override  # noqa: E402
from services.query_eval_store import (  # noqa: E402
    load_batch,
    save_batch,
    write_evaluation_artifact,
    write_response_artifact,
)


def _load_mws_variable_summary(mws_id: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if mws_id in cache:
        return cache[mws_id]
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


def _query_dict(query_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": query_run.get("query_id"),
        "persona": query_run.get("persona"),
        "production_system": query_run.get("production_system") or "Multi-system",
        "query": query_run.get("query") or "",
        "expected_pathway_candidates": query_run.get("expected_pathway_candidates") or [],
    }


def _repair_session_refs(
    cs_entry: dict[str, Any],
    *,
    batch_id: str,
    case_study_id: int,
    frontend_base: str,
) -> None:
    server = load_response_artifact(batch_id, response_artifact_name(case_study_id, None, "server"))
    if server:
        cs_entry["sessions"]["server"] = {
            **session_ref(server, frontend_base),
            "elapsed_ms": cs_entry.get("sessions", {}).get("server", {}).get("elapsed_ms"),
        }

    for query_run in cs_entry.get("query_runs") or []:
        qid = str(query_run.get("query_id") or "")
        for mode in ("llm_ollama", "llm_claude"):
            diagnosis = load_response_artifact(
                batch_id,
                response_artifact_name(case_study_id, qid, mode),
            )
            if diagnosis:
                prior = (query_run.get("sessions") or {}).get(mode) or {}
                query_run.setdefault("sessions", {})[mode] = {
                    **session_ref(diagnosis, frontend_base),
                    "elapsed_ms": prior.get("elapsed_ms"),
                    "llm_provider": prior.get("llm_provider") or ("ollama" if mode == "llm_ollama" else "anthropic"),
                }


def _ensure_q000(
    cs_entry: dict[str, Any],
    *,
    batch_id: str,
    case_study_id: int,
    frontend_base: str,
    skip_llm_runs: bool,
) -> dict[str, Any]:
    q000 = built_systems_query()
    query_runs = cs_entry.get("query_runs") or []
    existing = next((row for row in query_runs if row.get("query_id") == "Q000"), None)
    if existing:
        return existing

    query_run: dict[str, Any] = {
        "query_id": "Q000",
        "persona": q000.get("persona"),
        "production_system": q000.get("production_system"),
        "query": q000.get("query"),
        "expected_pathway_candidates": q000.get("expected_pathway_candidates"),
        "sessions": {},
        "evaluations": {},
        "agreement": {},
    }
    mws_id = str(cs_entry.get("mws_id") or "")

    for mode, provider in (("llm_ollama", "ollama"), ("llm_claude", "anthropic")):
        if skip_llm_runs:
            diagnosis = load_response_artifact(batch_id, response_artifact_name(case_study_id, "Q000", mode))
        else:
            print(f"  Q000 {mode} — running diagnosis…")
            started = time.perf_counter()
            diagnosis = _run_diagnosis(
                mws_id,
                problem_description=str(q000.get("query") or ""),
                want_llm_opinion=True,
                llm_provider=provider,
            )
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            write_response_artifact(
                batch_id,
                response_artifact_name(case_study_id, "Q000", mode),
                diagnosis,
            )
            query_run["sessions"][mode] = {
                **session_ref(diagnosis, frontend_base),
                "elapsed_ms": elapsed,
                "llm_provider": provider,
            }
            print(f"  Q000 {mode} session={diagnosis.get('session_id')} ({elapsed}ms)")
            continue

        if diagnosis:
            query_run["sessions"][mode] = {
                **session_ref(diagnosis, frontend_base),
                "llm_provider": provider,
            }

    cs_entry["query_runs"] = [query_run] + query_runs
    ids = cs_entry.get("query_ids") or []
    if "Q000" not in ids:
        cs_entry["query_ids"] = ["Q000"] + [q for q in ids if q != "Q000"]
    return query_run


def augment_batch(
    batch_id: str,
    *,
    frontend_base: str,
    evaluator_provider: str,
    skip_llm_runs: bool,
    skip_eval: bool,
    re_eval_server: bool,
    force_re_eval: bool = False,
) -> dict[str, Any]:
    manifest = load_batch(batch_id)
    manifest["modes"] = list(EVAL_MODES)
    present_cache: dict[str, dict[str, Any]] = {}

    for cs_entry in manifest.get("case_studies") or []:
        case_study_id = int(cs_entry.get("case_study_id") or 0)
        mws_id = str(cs_entry.get("mws_id") or "")
        print(f"Augmenting case study {case_study_id} · {mws_id}")

        _repair_session_refs(
            cs_entry,
            batch_id=batch_id,
            case_study_id=case_study_id,
            frontend_base=frontend_base,
        )

        q000_run = _ensure_q000(
            cs_entry,
            batch_id=batch_id,
            case_study_id=case_study_id,
            frontend_base=frontend_base,
            skip_llm_runs=skip_llm_runs,
        )

        server_diagnosis = load_response_artifact(
            batch_id,
            response_artifact_name(case_study_id, None, "server"),
        )
        mws_summary = _load_mws_variable_summary(mws_id, present_cache)
        case_study_meta = {
            "case_study_id": case_study_id,
            "mws_id": mws_id,
            "tehsil": cs_entry.get("tehsil"),
            "district": cs_entry.get("district"),
            "state": cs_entry.get("state"),
        }

        all_runs = cs_entry.get("query_runs") or []
        if q000_run not in all_runs:
            all_runs = [q000_run] + [r for r in all_runs if r.get("query_id") != "Q000"]
        cs_entry["query_runs"] = sorted(
            all_runs,
            key=lambda row: (0 if row.get("query_id") == "Q000" else 1, str(row.get("query_id") or "")),
        )

        for query_run in cs_entry["query_runs"]:
            qid = str(query_run.get("query_id") or "")
            if qid == "Q000":
                q000 = built_systems_query()
                query_run["persona"] = q000.get("persona")
                query_run["query"] = q000.get("query")
                query_run["production_system"] = q000.get("production_system")
                query = q000
            else:
                query = _query_dict(query_run)

            ollama_diagnosis = load_response_artifact(
                batch_id,
                response_artifact_name(case_study_id, qid, "llm_ollama"),
            )
            claude_diagnosis = load_response_artifact(
                batch_id,
                response_artifact_name(case_study_id, qid, "llm_claude"),
            )
            query_run["agreement"] = query_run_agreement(
                server_diagnosis=server_diagnosis,
                ollama_diagnosis=ollama_diagnosis,
                claude_diagnosis=claude_diagnosis,
            )

            if skip_eval:
                continue

            evaluations = query_run.setdefault("evaluations", {})
            eval_plan: list[tuple[str, dict[str, Any] | None]] = [
                ("server", server_diagnosis),
                ("llm_ollama", ollama_diagnosis),
                ("server_plus_llm_ollama", ollama_diagnosis),
                ("llm_claude", claude_diagnosis),
            ]
            for mode, diagnosis in eval_plan:
                if not diagnosis:
                    continue
                existing = evaluations.get(mode)
                if not force_re_eval:
                    if existing and not existing.get("error"):
                        if mode == "server" and not re_eval_server:
                            continue
                        if mode in {"llm_ollama", "llm_claude", "server_plus_llm_ollama"} and existing.get("weighted_total") is not None:
                            continue
                    if mode == "server" and existing and not re_eval_server:
                        continue
                    if mode == "server_plus_llm_ollama" and existing and not re_eval_server:
                        continue
                try:
                    print(f"  Evaluating {qid} · {mode}")
                    evaluations[mode] = evaluate_response(
                        query=query,
                        diagnosis=diagnosis,
                        mws_variable_summary=mws_summary,
                        mode=mode,
                        evaluator_provider=evaluator_provider,
                        case_study=case_study_meta,
                        server_diagnosis=server_diagnosis,
                    )
                    write_evaluation_artifact(
                        batch_id,
                        evaluation_artifact_name(case_study_id, qid, mode),
                        evaluations[mode],
                    )
                except Exception as exc:
                    evaluations[mode] = {"error": str(exc)}
                    print(f"  {qid} {mode} eval FAILED: {exc}")

    manifest["runs"] = []
    for cs_entry in manifest.get("case_studies") or []:
        for query_run in cs_entry.get("query_runs") or []:
            manifest["runs"].append(
                {
                    "case_study_id": cs_entry.get("case_study_id"),
                    "mws_id": cs_entry.get("mws_id"),
                    **query_run,
                }
            )

    return save_batch(manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--frontend-base", default="http://localhost:5173")
    parser.add_argument("--evaluator-provider", choices=["anthropic", "ollama"], default="anthropic")
    parser.add_argument("--skip-llm-runs", action="store_true", help="Do not run missing Q000 LLM diagnoses")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument(
        "--re-eval-server",
        action="store_true",
        help="Re-run server rubric evaluations (applies similarity_context note)",
    )
    parser.add_argument(
        "--force-re-eval",
        action="store_true",
        help="Re-run all rubric evaluations (server, LLM modes, server+ollama)",
    )
    args = parser.parse_args()

    manifest = augment_batch(
        args.batch_id,
        frontend_base=args.frontend_base,
        evaluator_provider=args.evaluator_provider,
        skip_llm_runs=args.skip_llm_runs,
        skip_eval=args.skip_eval,
        re_eval_server=args.re_eval_server or args.force_re_eval,
        force_re_eval=args.force_re_eval,
    )
    print(f"Updated batch {manifest.get('batch_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
