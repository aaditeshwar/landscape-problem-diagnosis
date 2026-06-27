"""Write tuning results to triage patch catalog and human-readable reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "reports" / "signal_tuning"
DEFAULT_PATCH_CATALOG = "case_study_locations_signal_tuning.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_report(pathway_id: str, payload: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"{pathway_id}_tuning_report.json"
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return out_path


def write_markdown_report(pathway_id: str, payload: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"{pathway_id}_tuning_report.md"
    lines = [
        f"# Signal tuning report — `{pathway_id}`",
        "",
        f"- Production system: **{payload.get('production_system')}**",
        f"- Observed stress: **{payload.get('observed_stress')}**",
        f"- Positives: **{payload.get('n_positives')}** · Negatives: **{payload.get('n_negatives')}**",
        f"- Cards tuned: **{payload.get('cards_considered')}**",
        "",
    ]
    for row in payload.get("signal_results") or []:
        lines.extend(
            [
                f"## {row.get('card_id')} · {row.get('signal_id')}",
                "",
                f"- Template: `{row.get('template')}`",
                f"- Recommendation: **{row.get('recommendation')}**",
                f"- Original: `{row.get('original_expression')}`",
                f"- Proposed: `{row.get('proposed_expression')}`",
                "",
            ]
        )
        baseline = row.get("baseline") or {}
        cm = baseline.get("confusion_matrix") or {}
        lines.append(
            f"- Baseline pathway outcome: TPR={baseline.get('tpr')} FPR={baseline.get('fpr')} "
            f"(TP={cm.get('TP')} FP={cm.get('FP')} TN={cm.get('TN')} FN={cm.get('FN')})"
        )
        best = row.get("best_candidate") or {}
        if best:
            cm2 = best.get("confusion_matrix") or {}
            lines.append(
                f"- Best candidate: TPR={best.get('tpr')} FPR={best.get('fpr')} "
                f"(TP={cm2.get('TP')} FP={cm2.get('FP')} TN={cm2.get('TN')} FN={cm2.get('FN')})"
            )
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def append_summary_csv(rows: list[dict[str, Any]]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "summary.csv"
    header = (
        "pathway_id,n_pos,n_neg,card_id,signal_id,recommendation,"
        "original_expression,proposed_expression,baseline_tpr,baseline_fpr,best_tpr,best_fpr\n"
    )
    if not out_path.is_file():
        out_path.write_text(header, encoding="utf-8")
    with out_path.open("a", encoding="utf-8") as handle:
        for row in rows:
            baseline = row.get("baseline") or {}
            best = row.get("best_candidate") or {}
            handle.write(
                ",".join(
                    [
                        _csv(row.get("pathway_id")),
                        str(row.get("n_positives") or ""),
                        str(row.get("n_negatives") or ""),
                        _csv(row.get("card_id")),
                        _csv(row.get("signal_id")),
                        _csv(row.get("recommendation")),
                        _csv(row.get("original_expression")),
                        _csv(row.get("proposed_expression")),
                        _csv(baseline.get("tpr")),
                        _csv(baseline.get("fpr")),
                        _csv(best.get("tpr")),
                        _csv(best.get("fpr")),
                    ]
                )
                + "\n"
            )
    return out_path


def _csv(value: Any) -> str:
    text = "" if value is None else str(value)
    if any(ch in text for ch in [",", '"', "\n"]):
        return '"' + text.replace('"', '""') + '"'
    return text


def build_patch_doc(
    *,
    catalog_filename: str,
    reviewer: str,
    card_patches: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "catalog_filename": catalog_filename,
        "batch_id": f"triage__{Path(catalog_filename).stem}",
        "updated_at": utc_now(),
        "reviewer": reviewer,
        "source": "signal_tuning_phase3",
        "cards": card_patches,
    }


def write_patch_catalog(catalog_filename: str, doc: dict[str, Any]) -> Path:
    out_path = ROOT / "metadata" / "triage_patches" / catalog_filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    tmp.replace(out_path)
    return out_path
