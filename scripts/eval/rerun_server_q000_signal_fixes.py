#!/usr/bin/env python3
"""Re-run server-only Q000 diagnosis for case studies with monsoon/lulc EF3 flags."""

from __future__ import annotations

import argparse
import json
import re
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

from eval.query_bank_index import built_systems_query  # noqa: E402
from eval.query_eval_common import (  # noqa: E402
    evaluation_artifact_name,
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

BATCH_ID = "query_eval__pilot_v3_20260626T184910Z"
EVAL_DIR = ROOT / "reports" / "query_eval" / BATCH_ID / "evaluations"


def _classify_ef3_detail(detail: str) -> tuple[bool, bool, bool]:
    dl = (detail or "").lower()
    monsoon = "monsoon_onset" in dl or "monsoon onset" in dl
    lulc = "lulc_cropland" in dl or (
        "cropland" in dl and ("per-capita" in dl or "landholding" in dl or "0 ha" in dl)
    )
    aquifer = "aquifer_class" in dl or ("aquifer" in dl and "sedimentary" in dl)
    return monsoon, lulc, aquifer


def case_studies_needing_rerun() -> dict[int, dict[str, Any]]:
    """Case study IDs with EF3 monsoon or lulc (not aquifer-only)."""
    by_id: dict[int, dict[str, Any]] = {}
    for path in sorted(EVAL_DIR.glob("cs*__Q000__server.json")):
        match = re.match(r"cs(\d+)__Q000__server\.json", path.name)
        if not match:
            continue
        cs_id = int(match.group(1))
        payload = json.loads(path.read_text(encoding="utf-8"))
        monsoon = lulc = aquifer = False
        for flag in payload.get("error_flags_triggered") or []:
            if flag.get("flag_id") != "EF3":
                continue
            m, l, a = _classify_ef3_detail(str(flag.get("detail") or ""))
            monsoon = monsoon or m
            lulc = lulc or l
            aquifer = aquifer or a
        if (monsoon or lulc) and not (aquifer and not monsoon and not lulc):
            by_id[cs_id] = {"monsoon": monsoon, "lulc": lulc, "aquifer": aquifer}
        elif monsoon or lulc:
            by_id[cs_id] = {"monsoon": monsoon, "lulc": lulc, "aquifer": aquifer}
    return by_id


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


def _run_server_diagnosis(mws_id: str, problem_description: str) -> dict[str, Any]:
    from routers.query import _load_mws, _run_query  # noqa: E402

    mws_doc = _load_mws(mws_id)
    return _run_query(
        mws_doc,
        problem_description,
        session_id=None,
        want_llm_opinion=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", default=BATCH_ID)
    parser.add_argument("--frontend-base", default="http://localhost:5173")
    parser.add_argument("--evaluator-provider", choices=["anthropic", "ollama"], default="anthropic")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case-study-id", type=int, action="append", dest="case_study_ids")
    args = parser.parse_args()

    targets = case_studies_needing_rerun()
    if args.case_study_ids:
        targets = {cid: targets.get(cid, {"monsoon": True, "lulc": True}) for cid in args.case_study_ids}

    print(f"Case studies to re-run (monsoon/lulc EF3): {sorted(targets.keys())}")
    if args.dry_run:
        for cid, flags in sorted(targets.items()):
            print(f"  cs{cid}: {flags}")
        return 0

    manifest = load_batch(args.batch_id)
    q000 = built_systems_query()
    present_cache: dict[str, dict[str, Any]] = {}

    for cs_entry in manifest.get("case_studies") or []:
        case_study_id = int(cs_entry.get("case_study_id") or 0)
        if case_study_id not in targets:
            continue
        mws_id = str(cs_entry.get("mws_id") or "")
        flags = targets[case_study_id]
        print(f"Re-run server Q000 · case study {case_study_id} · {mws_id} · {flags}")

        started = time.perf_counter()
        diagnosis = _run_server_diagnosis(mws_id, str(q000.get("query") or ""))
        elapsed = round((time.perf_counter() - started) * 1000, 2)

        write_response_artifact(
            args.batch_id,
            response_artifact_name(case_study_id, None, "server"),
            diagnosis,
        )
        cs_entry.setdefault("sessions", {})["server"] = {
            **session_ref(diagnosis, args.frontend_base),
            "elapsed_ms": elapsed,
            "llm_model": None,
            "want_llm_opinion": False,
            "llm_skipped": True,
        }
        print(f"  server session={diagnosis.get('session_id')} ({elapsed}ms)")

        query_run = next((r for r in (cs_entry.get("query_runs") or []) if r.get("query_id") == "Q000"), None)
        if not query_run:
            query_run = {
                "query_id": "Q000",
                "persona": q000.get("persona"),
                "production_system": q000.get("production_system"),
                "query": q000.get("query"),
                "sessions": {},
                "evaluations": {},
                "agreement": {},
            }
            cs_entry["query_runs"] = [query_run] + [r for r in (cs_entry.get("query_runs") or []) if r.get("query_id") != "Q000"]

        mws_summary = _load_mws_variable_summary(mws_id, present_cache)
        case_study_meta = {
            "case_study_id": case_study_id,
            "mws_id": mws_id,
            "tehsil": cs_entry.get("tehsil"),
            "district": cs_entry.get("district"),
            "state": cs_entry.get("state"),
        }
        print("  Evaluating Q000 · server")
        with llm_provider_override(args.evaluator_provider):
            evaluation = evaluate_response(
                query=q000,
                diagnosis=diagnosis,
                mws_variable_summary=mws_summary,
                mode="server",
                evaluator_provider=args.evaluator_provider,
                case_study=case_study_meta,
                server_diagnosis=diagnosis,
            )
        query_run.setdefault("evaluations", {})["server"] = evaluation
        write_evaluation_artifact(
            args.batch_id,
            evaluation_artifact_name(case_study_id, "Q000", "server"),
            evaluation,
        )
        ef3 = [f for f in (evaluation.get("error_flags_triggered") or []) if f.get("flag_id") == "EF3"]
        print(f"  EF3 after re-run: {len(ef3)}")

        save_batch(manifest)
        print(f"  saved manifest ({len(manifest.get('case_studies') or [])} case studies)")

    print(f"Updated batch {args.batch_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
