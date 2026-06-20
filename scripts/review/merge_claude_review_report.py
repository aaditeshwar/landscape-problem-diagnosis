#!/usr/bin/env python3
"""Merge per-card Claude review results into human and machine reports."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "reports" / "claude_review" / "results"
OUT_DIR = ROOT / "reports" / "claude_review"

CSV_FIELDS = [
    "card_id",
    "overall_score",
    "dimension",
    "issue_id",
    "severity",
    "field_path",
    "current_snippet",
    "suggested_snippet",
    "reviewer_confidence",
    "explanation",
]


def snippet(value) -> str:
    if value is None:
        return ""
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return text[:400].replace("\n", " ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    result_paths = sorted(args.results_dir.glob("*.json"))
    if not result_paths:
        print(f"No results in {args.results_dir}", file=sys.stderr)
        return 1

    rows: list[dict[str, str]] = []
    patches: dict[str, list[dict]] = {}
    overall_scores: Counter[str] = Counter()
    dimension_scores: Counter[str] = Counter()
    policy_findings: list[dict] = []

    for path in result_paths:
        with path.open(encoding="utf-8") as handle:
            doc = json.load(handle)
        card_id = str(doc.get("card_id") or path.stem)
        overall = str(doc.get("overall_score") or "unknown")
        overall_scores[overall] += 1

        for dim_key, dim_val in (doc.get("dimensions") or {}).items():
            if isinstance(dim_val, dict):
                dimension_scores[f"{dim_key}:{dim_val.get('score', '?')}"] += 1

        for finding in doc.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            issue_id = str(finding.get("issue_id") or "")
            field_path = str(finding.get("field_path") or "")
            suggested = finding.get("suggested_patch")
            row = {
                "card_id": card_id,
                "overall_score": overall,
                "dimension": str(finding.get("dimension") or ""),
                "issue_id": issue_id,
                "severity": str(finding.get("severity") or ""),
                "field_path": field_path,
                "current_snippet": snippet(finding.get("current_value")),
                "suggested_snippet": snippet(suggested),
                "reviewer_confidence": str(finding.get("reviewer_confidence") or ""),
                "explanation": str(finding.get("explanation") or "")[:500],
            }
            rows.append(row)

            if suggested:
                patches.setdefault(card_id, []).append(
                    {
                        "issue_id": issue_id,
                        "field_path": field_path,
                        "suggested_patch": suggested,
                        "severity": finding.get("severity"),
                        "dimension": finding.get("dimension"),
                    }
                )

            if finding.get("dimension") == "D3_confirmation_policy":
                policy_findings.append({**finding, "card_id": card_id})

    args.out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = args.out_dir / "card_review_issues.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    patches_path = args.out_dir / "suggested_patches.json"
    patches_path.write_text(json.dumps(patches, indent=2, ensure_ascii=False), encoding="utf-8")

    summary_lines = [
        "# Claude evidence card review summary",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Result files: {len(result_paths)}",
        "",
        "## Overall scores",
        "",
    ]
    for score, count in sorted(overall_scores.items()):
        summary_lines.append(f"- **{score}**: {count}")

    summary_lines.extend(["", "## Dimension scores", ""])
    for key, count in sorted(dimension_scores.items()):
        summary_lines.append(f"- `{key}`: {count}")

    error_rows = [r for r in rows if r["severity"] == "error"]
    warn_rows = [r for r in rows if r["severity"] == "warn"]
    summary_lines.extend(
        [
            "",
            "## Findings",
            "",
            f"- Errors: {len(error_rows)}",
            f"- Warnings: {len(warn_rows)}",
            f"- Total findings: {len(rows)}",
            "",
            "## Outputs",
            "",
            f"- `{csv_path.relative_to(ROOT)}`",
            f"- `{patches_path.relative_to(ROOT)}`",
            "",
        ]
    )

    summary_path = args.out_dir / "CARD_REVIEW_SUMMARY.md"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    policy_md_lines = [
        "# Policy fixes for review (v2 — Claude review)",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Policy-related findings: {len(policy_findings)}",
        "",
    ]
    for item in policy_findings[:200]:
        policy_md_lines.append(f"## {item.get('card_id')} — {item.get('issue_id')}")
        policy_md_lines.append("")
        policy_md_lines.append(str(item.get("explanation") or ""))
        policy_md_lines.append("")
        if item.get("suggested_patch"):
            policy_md_lines.append("```json")
            policy_md_lines.append(json.dumps(item["suggested_patch"], indent=2))
            policy_md_lines.append("```")
        policy_md_lines.append("")

    policy_path = args.out_dir / "POLICY_FIXES_FOR_REVIEW_v2.md"
    policy_path.write_text("\n".join(policy_md_lines), encoding="utf-8")

    print(f"Wrote {summary_path}")
    print(f"Wrote {csv_path} ({len(rows)} rows)")
    print(f"Wrote {patches_path} ({len(patches)} cards with patches)")
    print(f"Wrote {policy_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
