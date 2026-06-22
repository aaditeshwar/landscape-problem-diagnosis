#!/usr/bin/env python3
"""Run initial diagnoses for case-study MWS locations via the live API.

Creates real sessions and diagnosis.jsonl entries (follow_up_count=0 only) so
feedback URLs and replay_diagnosis_runs.py baselines work like manual UI runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from eval.case_study_index import (  # noqa: E402
    BUILT_PATHWAY_IDS,
    DEFAULT_PROBLEM,
    enrich_case_study_rows,
    load_case_study_rows,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "reports" / "case_study_eval"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _pathway_ids(response: dict[str, Any], bucket: str) -> list[str]:
    ids: list[str] = []
    for item in response.get(bucket) or []:
        if isinstance(item, dict):
            pid = str(item.get("pathway_id") or "").strip()
            if pid:
                ids.append(pid)
    return ids


def _match_status(expected: str | None, confirmed: list[str], uncertain: list[str]) -> str:
    if not expected:
        return "stress_only"
    if expected in confirmed:
        return "confirmed"
    if expected in uncertain:
        return "uncertain"
    return "miss"


def _feedback_url(frontend_base: str, snapshot_id: str) -> str:
    base = frontend_base.rstrip("/")
    return f"{base}/feedback?snapshot_id={quote(snapshot_id, safe='')}"


def _admin_fields(row: dict[str, Any]) -> dict[str, str]:
    return {
        "state": str(row.get("state") or ""),
        "district": str(row.get("district") or ""),
        "tehsil": str(row.get("tehsil") or ""),
    }


def run_batch(
    *,
    api_base: str,
    frontend_base: str,
    problem_description: str,
    want_llm_opinion: bool,
    include_stress_only: bool,
    limit: int | None,
    delay_seconds: float,
    dry_run: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = enrich_case_study_rows(load_case_study_rows(include_stress_only=include_stress_only))
    if limit is not None:
        rows = rows[:limit]

    report_rows: list[dict[str, Any]] = []
    replay_runs: list[dict[str, Any]] = []

    if dry_run:
        for index, row in enumerate(rows, start=1):
            report_rows.append(
                {
                    "run_index": index,
                    "case_study_id": row.get("case_study_id"),
                    **_admin_fields(row),
                    "mws_id": row["mws_id"],
                    "expected_pathway": row.get("expected_pathway") or "",
                    "stress_only": row.get("stress_only"),
                    "status": "dry_run",
                }
            )
        return report_rows, replay_runs

    with httpx.Client(timeout=600.0) as client:
        health = client.get(f"{api_base.rstrip('/')}/api/health")
        health.raise_for_status()

        for index, row in enumerate(rows, start=1):
            body = {
                "uid": row["mws_id"],
                "problem_description": problem_description if want_llm_opinion else "",
                "want_llm_opinion": want_llm_opinion,
            }
            started = time.perf_counter()
            response = client.post(f"{api_base.rstrip('/')}/api/query", json=body)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            response.raise_for_status()
            payload = response.json()

            session_id = str(payload.get("session_id") or "")
            snapshot_id = str(payload.get("diagnosis_snapshot_id") or "")
            confirmed = _pathway_ids(payload, "confirmed_pathways")
            uncertain = _pathway_ids(payload, "uncertain_pathways")
            expected = row.get("expected_pathway")
            match = _match_status(expected, confirmed, uncertain)

            report_rows.append(
                {
                    "run_index": index,
                    "case_study_id": row.get("case_study_id"),
                    **_admin_fields(row),
                    "mws_id": row["mws_id"],
                    "production_system": row.get("production_system") or "",
                    "observed_stress": row.get("observed_stress") or "",
                    "expected_pathway": expected or "",
                    "stress_only": row.get("stress_only"),
                    "confirmed_pathways": ",".join(confirmed),
                    "uncertain_pathways": ",".join(uncertain),
                    "match_status": match,
                    "session_id": session_id,
                    "diagnosis_snapshot_id": snapshot_id,
                    "feedback_url": _feedback_url(frontend_base, snapshot_id) if snapshot_id else "",
                    "want_llm_opinion": want_llm_opinion,
                    "elapsed_ms": elapsed_ms,
                    "skipped_production_systems": json.dumps(
                        payload.get("skipped_production_systems") or [],
                        ensure_ascii=False,
                    ),
                }
            )

            replay_runs.append(
                {
                    "run_index": index,
                    "case_study_id": row.get("case_study_id"),
                    **_admin_fields(row),
                    "expected_pathway": expected,
                    "source_session_id": session_id,
                    "source_timestamp": datetime.now(timezone.utc).isoformat(),
                    "query": {
                        "uid": row["mws_id"],
                        "problem_description": body["problem_description"],
                        "want_llm_opinion": want_llm_opinion,
                    },
                    "diagnosis_snapshot_id": snapshot_id,
                    "feedback_url": _feedback_url(frontend_base, snapshot_id) if snapshot_id else "",
                    "final_response": payload,
                }
            )

            print(
                f"[{index}/{len(rows)}] {row['mws_id']} "
                f"({row.get('tehsil') or '—'}, {row.get('district') or '—'}, {row.get('state') or '—'}) "
                f"expected={expected or '—'} match={match} session={session_id}"
            )

            if delay_seconds > 0 and index < len(rows):
                time.sleep(delay_seconds)

    return report_rows, replay_runs


def write_outputs(
    report_rows: list[dict[str, Any]],
    replay_runs: list[dict[str, Any]],
    *,
    output_dir: Path,
    want_llm_opinion: bool,
    problem_description: str,
    dry_run: bool,
) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = "llm" if want_llm_opinion else "server"
    stamp = _utc_stamp()

    report_json = output_dir / f"case_study_diagnosis_{mode}_{stamp}.json"
    report_csv = output_dir / f"case_study_diagnosis_{mode}_{stamp}.csv"

    built = [r for r in report_rows if r.get("expected_pathway")]
    hits = [r for r in built if r.get("match_status") == "confirmed"]
    partial = [r for r in built if r.get("match_status") == "uncertain"]
    misses = [r for r in built if r.get("match_status") == "miss"]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "want_llm_opinion": want_llm_opinion,
        "problem_description": problem_description,
        "dry_run": dry_run,
        "row_count": len(report_rows),
        "built_pathway_rows": len(built),
        "confirmed_hits": len(hits),
        "uncertain_hits": len(partial),
        "misses": len(misses),
        "rows": report_rows,
    }
    report_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if report_rows:
        fieldnames = list(report_rows[0].keys())
        with report_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(report_rows)

    replay_path: Path | None = None
    if replay_runs and not dry_run:
        replay_path = output_dir / f"replay_baseline_{mode}_{stamp}.json"
        replay_path.write_text(
            json.dumps(
                {
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "source": "scripts/eval/run_case_study_diagnoses.py",
                    "want_llm_opinion": want_llm_opinion,
                    "problem_description": problem_description,
                    "run_count": len(replay_runs),
                    "runs": replay_runs,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return report_json, replay_path


def _load_present_variables(mws_id: str, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if mws_id in cache:
        return cache[mws_id]
    runtime_dir = ROOT / "runtime"
    if str(runtime_dir) not in sys.path:
        sys.path.insert(0, str(runtime_dir))
    from services.signal_evaluator import merge_export_variables  # noqa: E402

    path = ROOT / "data" / "raw_jsons" / f"{mws_id}.json"
    if path.is_file():
        export = json.loads(path.read_text(encoding="utf-8"))
        cache[mws_id] = merge_export_variables(export)
    else:
        cache[mws_id] = {}
    return cache[mws_id]


def _location_label(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("mws_id") or "").strip(),
        str(row.get("tehsil") or "").strip(),
        str(row.get("district") or "").strip(),
        str(row.get("state") or "").strip(),
    ]
    return " · ".join(p for p in parts if p)


def _location_link(row: dict[str, Any]) -> str:
    label = _location_label(row)
    url = str(row.get("feedback_url") or "").strip()
    return f"[{label}]({url})" if url else label


def _pathway_eval(replay_run: dict[str, Any] | None, pathway_id: str) -> dict[str, Any] | None:
    if not replay_run or not pathway_id:
        return None
    signal_eval = (replay_run.get("final_response") or {}).get("signal_evaluation") or {}
    for item in signal_eval.get("pathways") or []:
        if isinstance(item, dict) and str(item.get("pathway_id") or "") == pathway_id:
            return item
    return None


def _format_var_value(name: str, value: Any) -> str:
    if value is None:
        return f"`{name}`=—"
    if isinstance(value, list):
        if not value:
            return f"`{name}`=[]"
        last = value[-1]
        return f"`{name}`[-1]={json.dumps(last, ensure_ascii=False)}"
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False)
        if len(text) > 72:
            text = text[:69] + "…"
        return f"`{name}`={text}"
    return f"`{name}`={json.dumps(value, ensure_ascii=False) if isinstance(value, str) else value}"


def _format_signal_line(signal: dict[str, Any], present: dict[str, Any]) -> str:
    runtime_dir = ROOT / "runtime"
    if str(runtime_dir) not in sys.path:
        sys.path.insert(0, str(runtime_dir))
    from services.signal_evaluator import expression_load_names  # noqa: E402

    expr = str(signal.get("expression") or "").strip()
    result = signal.get("result")
    if result is True:
        result_label = "**TRUE**"
    elif result is False:
        result_label = "**FALSE**"
    else:
        result_label = "**None**"
    sig_id = str(signal.get("signal_id") or "?")
    direction = str(signal.get("direction") or "")
    status = str(signal.get("status") or "ok")

    parts = [f"**{sig_id}** ({direction}) → {result_label}"]
    if status != "ok":
        parts.append(f"status={status}")
    if expr:
        parts.append(f"`{expr}`")
    var_names = sorted(expression_load_names(expr)) if expr else []
    if var_names:
        var_bits = [_format_var_value(name, present.get(name)) for name in var_names]
        parts.append("vars: " + ", ".join(var_bits))
    return " · ".join(parts)


def _expected_pathway_detail(
    row: dict[str, Any],
    replay_run: dict[str, Any] | None,
    present_cache: dict[str, dict[str, Any]],
) -> str:
    expected = str(row.get("expected_pathway") or "").strip()
    if not expected:
        return "—"

    if expected not in BUILT_PATHWAY_IDS:
        return (
            f"**`{expected}`** — pathway **not built** in stack "
            f"(no evidence cards; diagnosis cannot surface this pathway)"
        )

    match = str(row.get("match_status") or "")
    outcome = {
        "confirmed": "confirmed",
        "uncertain": "uncertain",
        "miss": "miss",
    }.get(match, match or "—")

    lines = [f"**`{expected}`** · **{outcome}**"]
    confirmed = str(row.get("confirmed_pathways") or "—")
    uncertain = str(row.get("uncertain_pathways") or "—")
    lines.append(f"Diagnosis lists — confirmed: {confirmed}; uncertain: {uncertain}")

    pathway_eval = _pathway_eval(replay_run, expected)
    if not pathway_eval:
        lines.append("Pathway **not retrieved** (absent from signal evaluation bundle)")
        return "<br>".join(lines)

    summary = pathway_eval.get("summary") or {}
    lines.append(
        "Policy eval — "
        f"confirms_true={summary.get('confirms_true', 0)}, "
        f"rules_out_true={summary.get('rules_out_true', 0)}, "
        f"amplifiers_true={summary.get('amplifies_true', 0)}, "
        f"needs_llm={summary.get('needs_llm', 0)}"
    )

    present = _load_present_variables(str(row.get("mws_id") or ""), present_cache)
    for signal in pathway_eval.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        lines.append(_format_signal_line(signal, present))

    return "<br>".join(lines)


def _render_result_table(
    rows: list[dict[str, Any]],
    replay_by_index: dict[int, dict[str, Any]],
    present_cache: dict[str, dict[str, Any]],
) -> list[str]:
    if not rows:
        return ["_(none)_", ""]
    lines = [
        "| Location | Expected pathway (signals + variables) |",
        "|----------|----------------------------------------|",
    ]
    for row in sorted(
        rows,
        key=lambda r: (
            r.get("state") or "",
            r.get("district") or "",
            r.get("tehsil") or "",
            r.get("mws_id") or "",
        ),
    ):
        run_index = int(row.get("run_index") or 0)
        detail = _expected_pathway_detail(row, replay_by_index.get(run_index), present_cache)
        lines.append(f"| {_location_link(row)} | {detail} |")
    lines.append("")
    return lines


def write_markdown_report(
    summary: dict[str, Any],
    *,
    output_dir: Path,
    mode: str,
    stamp: str,
    replay_path: Path | None,
    replay_runs: list[dict[str, Any]] | None = None,
) -> Path:
    """Write a human-readable triage summary grouped by match_status."""
    md_path = output_dir / f"case_study_diagnosis_{mode}_{stamp}.md"
    rows = summary.get("rows") or []
    replay_by_index = {
        int(item.get("run_index") or 0): item for item in (replay_runs or []) if item.get("run_index")
    }
    present_cache: dict[str, dict[str, Any]] = {}

    by_status: dict[str, list[dict[str, Any]]] = {
        "confirmed": [],
        "uncertain": [],
        "miss": [],
        "stress_only": [],
    }
    for row in rows:
        status = str(row.get("match_status") or "stress_only")
        by_status.setdefault(status, []).append(row)

    misses = by_status.get("miss") or []
    miss_built = [r for r in misses if str(r.get("expected_pathway") or "") in BUILT_PATHWAY_IDS]
    miss_unbuilt = [r for r in misses if str(r.get("expected_pathway") or "") not in BUILT_PATHWAY_IDS]

    built_list = ", ".join(f"`{p}`" for p in sorted(BUILT_PATHWAY_IDS))

    lines = [
        "# Case study diagnosis batch",
        "",
        f"**Generated:** {summary.get('generated_at')}",
        f"**Mode:** {mode} (`want_llm_opinion={summary.get('want_llm_opinion')}`)",
        f"**Problem text:** {summary.get('problem_description') or '*(empty — server-only)*'}",
        "",
        f"**Built pathways ({len(BUILT_PATHWAY_IDS)}):** {built_list}",
        "",
        "## Scorecard",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Total runs | {summary.get('row_count', 0)} |",
        f"| With expected pathway | {summary.get('built_pathway_rows', 0)} |",
        f"| Confirmed hit | {summary.get('confirmed_hits', 0)} |",
        f"| Uncertain (partial) | {summary.get('uncertain_hits', 0)} |",
        f"| Miss (total) | {len(misses)} |",
        f"| Miss — built pathway | {len(miss_built)} |",
        f"| Miss — pathway not built | {len(miss_unbuilt)} |",
        "",
        "## Triage priority",
        "",
        "1. **Miss (built pathways)** — stack should surface these; inspect signal TRUE/FALSE below.",
        "2. **Uncertain** — pathway retrieved but below confirmation threshold.",
        "3. **Miss (not built)** — expected pathway has no cards yet; misses are expected.",
        "",
    ]

    if replay_path:
        lines.extend(
            [
                "## Replay baseline",
                "",
                f"`{replay_path}`",
                "",
                "Compare with Claude/Ollama reviewer:",
                "",
                "```powershell",
                f".\\.venv\\Scripts\\python.exe scripts/replay_diagnosis_runs.py replay --baseline {replay_path}",
                "```",
                "",
            ]
        )

    lines.append(f"## MISS — built pathways ({len(miss_built)})")
    lines.append("")
    lines.extend(_render_result_table(miss_built, replay_by_index, present_cache))

    lines.append(f"## MISS — pathways not built yet ({len(miss_unbuilt)})")
    lines.append("")
    lines.extend(_render_result_table(miss_unbuilt, replay_by_index, present_cache))

    uncertain = by_status.get("uncertain") or []
    lines.append(f"## UNCERTAIN ({len(uncertain)})")
    lines.append("")
    lines.extend(_render_result_table(uncertain, replay_by_index, present_cache))

    confirmed = by_status.get("confirmed") or []
    lines.append(f"## CONFIRMED ({len(confirmed)})")
    lines.append("")
    lines.extend(_render_result_table(confirmed, replay_by_index, present_cache))

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument(
        "--frontend-base",
        default="http://localhost:5173",
        help="Vite frontend base for feedback URLs",
    )
    parser.add_argument(
        "--problem",
        default=DEFAULT_PROBLEM,
        help="Problem text when --want-llm is set (ignored for server-only runs)",
    )
    parser.add_argument(
        "--want-llm",
        action="store_true",
        help="Run with want_llm_opinion=true (reviewer mode). Default is server-only.",
    )
    parser.add_argument(
        "--include-stress-only",
        action="store_true",
        help="Include __stress_only__ rows (no expected pathway)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Run only first N rows")
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true", help="List rows without API calls")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    limit = args.limit or None
    report_rows, replay_runs = run_batch(
        api_base=args.api_base,
        frontend_base=args.frontend_base,
        problem_description=args.problem,
        want_llm_opinion=args.want_llm,
        include_stress_only=args.include_stress_only,
        limit=limit,
        delay_seconds=args.delay_seconds,
        dry_run=args.dry_run,
    )

    report_json, replay_path = write_outputs(
        report_rows,
        replay_runs,
        output_dir=args.output_dir,
        want_llm_opinion=args.want_llm,
        problem_description=args.problem,
        dry_run=args.dry_run,
    )

    md_path: Path | None = None
    if report_rows and not args.dry_run:
        summary = json.loads(report_json.read_text(encoding="utf-8"))
        mode = "llm" if args.want_llm else "server"
        stamp = report_json.stem.rsplit("_", 1)[-1]
        md_path = write_markdown_report(
            summary,
            output_dir=args.output_dir,
            mode=mode,
            stamp=stamp,
            replay_path=replay_path,
            replay_runs=replay_runs,
        )

    print(f"Wrote {report_json}")
    if md_path:
        print(f"Wrote {md_path}")
    if replay_path:
        print(f"Wrote {replay_path}")
        print(
            "Replay with: py scripts/replay_diagnosis_runs.py replay "
            f"--baseline {replay_path} --api-base {args.api_base}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
