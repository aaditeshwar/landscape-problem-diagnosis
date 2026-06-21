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


def write_markdown_report(
    summary: dict[str, Any],
    *,
    output_dir: Path,
    mode: str,
    stamp: str,
    replay_path: Path | None,
) -> Path:
    """Write a human-readable triage summary grouped by match_status."""
    md_path = output_dir / f"case_study_diagnosis_{mode}_{stamp}.md"
    rows = summary.get("rows") or []
    built = [r for r in rows if r.get("expected_pathway")]
    by_status: dict[str, list[dict[str, Any]]] = {
        "confirmed": [],
        "uncertain": [],
        "miss": [],
        "stress_only": [],
    }
    for row in rows:
        status = str(row.get("match_status") or "stress_only")
        by_status.setdefault(status, []).append(row)

    lines = [
        "# Case study diagnosis batch",
        "",
        f"**Generated:** {summary.get('generated_at')}",
        f"**Mode:** {mode} (`want_llm_opinion={summary.get('want_llm_opinion')}`)",
        f"**Problem text:** {summary.get('problem_description') or '*(empty — server-only)*'}",
        "",
        "## Scorecard",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Total runs | {summary.get('row_count', 0)} |",
        f"| With expected pathway | {summary.get('built_pathway_rows', 0)} |",
        f"| Confirmed hit | {summary.get('confirmed_hits', 0)} |",
        f"| Uncertain (partial) | {summary.get('uncertain_hits', 0)} |",
        f"| Miss | {summary.get('misses', 0)} |",
        "",
        "## Triage priority",
        "",
        "1. **`miss`** — expected pathway not in confirmed or uncertain; inspect feedback URL first.",
        "2. **`uncertain`** — pathway surfaced but not confirmed; check signal eval + confirmation policy.",
        "3. **`confirmed`** — spot-check only.",
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

    for status in ("miss", "uncertain", "confirmed"):
        group = by_status.get(status) or []
        if not group:
            continue
        lines.append(f"## {status.upper()} ({len(group)})")
        lines.append("")
        lines.append(
            "| State | District | Tehsil | MWS | Expected | Confirmed | Uncertain | Feedback |"
        )
        lines.append("|-------|----------|--------|-----|----------|-----------|-----------|----------|")
        for row in sorted(
            group,
            key=lambda r: (
                r.get("state") or "",
                r.get("district") or "",
                r.get("tehsil") or "",
                r.get("mws_id") or "",
            ),
        ):
            fb = row.get("feedback_url") or ""
            fb_cell = f"[open]({fb})" if fb else "—"
            lines.append(
                f"| {row.get('state') or '—'} | {row.get('district') or '—'} | "
                f"{row.get('tehsil') or '—'} | `{row.get('mws_id')}` | "
                f"`{row.get('expected_pathway')}` | "
                f"`{row.get('confirmed_pathways') or '—'}` | "
                f"`{row.get('uncertain_pathways') or '—'}` | {fb_cell} |"
            )
        lines.append("")

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
