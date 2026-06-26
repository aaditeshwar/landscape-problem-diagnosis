"""Validate and store user-uploaded case study catalog JSON files."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import METADATA_DIR
from services.built_pathways import STRESS_ONLY_PATHWAY
from services.triage_index import load_case_study_rows_from_file

USER_CATALOG_DIR = METADATA_DIR / "user-case-studies"
EXAMPLE_CATALOG_PATH = METADATA_DIR / "examples" / "case_study_catalog_example.json"
_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.json$")


def _walk_case_study_rows(
    node: Any,
    *,
    production: str | None = None,
    stress: str | None = None,
    pathway: str | None = None,
    errors: list[str],
    rows: list[dict[str, Any]],
) -> None:
    if isinstance(node, dict):
        if "case_studies" in node and isinstance(node["case_studies"], list):
            if not production or not stress:
                errors.append("case_studies block is missing production_system or observed_stress context")
            for index, entry in enumerate(node["case_studies"]):
                if not isinstance(entry, dict):
                    errors.append(f"case_studies[{index}] must be an object")
                    continue
                mws_id = str(entry.get("mws_id") or "").strip()
                if not mws_id:
                    errors.append(f"case_studies[{index}].mws_id is required")
                    continue
                case_study_id = entry.get("case_study_id")
                if case_study_id is not None and not isinstance(case_study_id, int):
                    errors.append(f"case_studies[{index}].case_study_id must be an integer when provided")
                for coord in ("lat", "lng"):
                    value = entry.get(coord)
                    if value is not None and not isinstance(value, (int, float)):
                        errors.append(f"case_studies[{index}].{coord} must be a number when provided")
                rows.append(
                    {
                        "case_study_id": case_study_id,
                        "mws_id": mws_id,
                        "production_system": production,
                        "observed_stress": stress,
                        "expected_pathway": None if pathway == STRESS_ONLY_PATHWAY else pathway,
                        "stress_only": pathway == STRESS_ONLY_PATHWAY,
                    }
                )
            return
        for key, value in node.items():
            if key == "production_systems" and isinstance(value, dict):
                for prod, pdata in value.items():
                    if not isinstance(pdata, dict):
                        errors.append(f"production_systems.{prod} must be an object")
                        continue
                    stresses = pdata.get("observed_stresses")
                    if not isinstance(stresses, dict):
                        errors.append(f"production_systems.{prod}.observed_stresses must be an object")
                        continue
                    for stress_name, sdata in stresses.items():
                        if not isinstance(sdata, dict):
                            errors.append(
                                f"production_systems.{prod}.observed_stresses.{stress_name} must be an object"
                            )
                            continue
                        pathways = sdata.get("causal_pathways")
                        if not isinstance(pathways, dict):
                            errors.append(
                                f"production_systems.{prod}.observed_stresses.{stress_name}.causal_pathways must be an object"
                            )
                            continue
                        for pathway_id, pdata2 in pathways.items():
                            _walk_case_study_rows(
                                pdata2,
                                production=str(prod),
                                stress=str(stress_name),
                                pathway=str(pathway_id),
                                errors=errors,
                                rows=rows,
                            )
            elif key not in ("meta", "diagnosis_framework", "normalisation_note", "note"):
                _walk_case_study_rows(value, production=production, stress=stress, pathway=pathway, errors=errors, rows=rows)
    elif isinstance(node, list):
        for item in node:
            _walk_case_study_rows(item, production=production, stress=stress, pathway=pathway, errors=errors, rows=rows)


def validate_case_study_catalog(payload: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """Return validation errors and parsed case-study rows."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Catalog must be a JSON object"], []

    framework = payload.get("diagnosis_framework")
    if not isinstance(framework, dict):
        errors.append("Missing required object: diagnosis_framework")
        return errors, []

    rows: list[dict[str, Any]] = []
    _walk_case_study_rows(framework, errors=errors, rows=rows)
    if not rows and not errors:
        errors.append("No case studies found under diagnosis_framework.production_systems")
    if rows:
        seen: set[tuple[Any, str]] = set()
        for row in rows:
            key = (row.get("case_study_id"), row["mws_id"])
            if key in seen:
                errors.append(f"Duplicate case study entry: case_study_id={key[0]!r}, mws_id={key[1]!r}")
            seen.add(key)
    return errors, rows


def parse_catalog_bytes(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Catalog must be UTF-8 encoded JSON") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc.msg}") from exc


def sanitize_catalog_filename(name: str) -> str:
    base = Path(name).name.strip()
    if not base.lower().endswith(".json"):
        base = f"{base}.json"
    safe = re.sub(r"[^\w.\-]+", "_", base)
    safe = safe.strip("._") or "case_study_catalog.json"
    if not _FILENAME_RE.match(safe):
        raise ValueError(
            "Filename must be 1–80 characters, start with a letter or digit, and end with .json "
            "(letters, digits, dot, underscore, hyphen only)"
        )
    return safe


def save_user_catalog(payload: dict[str, Any], *, filename: str | None = None) -> Path:
    errors, rows = validate_case_study_catalog(payload)
    if errors:
        raise ValueError("; ".join(errors))
    if not rows:
        raise ValueError("Catalog contains no case studies")

    USER_CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    if filename:
        out_name = sanitize_catalog_filename(filename)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_name = f"user_case_studies_{stamp}.json"
    out_path = USER_CATALOG_DIR / out_name
    if out_path.exists():
        raise ValueError(f"A catalog named {out_name} already exists — choose a different filename")
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def verify_saved_catalog(path: Path) -> None:
    """Round-trip check using the same loader the triage API uses."""
    rel = path.name
    if path.parent == USER_CATALOG_DIR:
        rel = f"user-case-studies/{path.name}"
    rows = load_case_study_rows_from_file(rel)
    if not rows:
        raise ValueError("Catalog saved but no case studies could be loaded")
