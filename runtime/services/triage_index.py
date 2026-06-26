"""Case-study catalog loading and section grouping for triage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import METADATA_DIR
from services.assembler import load_framework
from services.built_pathways import (
    STRESS_ONLY_PATHWAY,
    built_pathways_for_section,
    section_has_built_pathways,
)
from services.tehsil_refs import primary_tehsil

CASE_STUDY_GLOB = "case_study_locations*.json"
USER_CATALOG_DIR = METADATA_DIR / "user-case-studies"
USER_CATALOG_PREFIX = "user-case-studies/"


def list_case_study_catalogs() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(METADATA_DIR.glob(CASE_STUDY_GLOB)):
        if not path.is_file():
            continue
        rows.append(
            {
                "filename": path.name,
                "path": str(path.relative_to(METADATA_DIR.parent)),
                "source": "builtin",
            }
        )
    if USER_CATALOG_DIR.is_dir():
        for path in sorted(USER_CATALOG_DIR.glob("*.json")):
            if not path.is_file():
                continue
            rel = f"{USER_CATALOG_PREFIX}{path.name}"
            rows.append(
                {
                    "filename": rel,
                    "path": str(path.relative_to(METADATA_DIR.parent)),
                    "source": "user",
                }
            )
    return rows


def _catalog_path(filename: str) -> Path:
    normalized = str(filename or "").replace("\\", "/").strip()
    if not normalized or ".." in normalized.split("/"):
        raise FileNotFoundError(f"Case study catalog not found: {filename}")

    if normalized.startswith(USER_CATALOG_PREFIX):
        path = METADATA_DIR / normalized
    else:
        path = METADATA_DIR / Path(normalized).name

    if not path.is_file():
        raise FileNotFoundError(f"Case study catalog not found: {filename}")
    return path


def load_case_study_rows_from_file(
    filename: str,
    *,
    include_stress_only: bool = True,
) -> list[dict[str, Any]]:
    with _catalog_path(filename).open(encoding="utf-8") as handle:
        raw = json.load(handle)

    rows: list[dict[str, Any]] = []

    def walk(
        node: Any,
        production: str | None = None,
        stress: str | None = None,
        pathway: str | None = None,
    ) -> None:
        if isinstance(node, dict):
            if "case_studies" in node and isinstance(node["case_studies"], list):
                is_stress_only = pathway == STRESS_ONLY_PATHWAY
                if is_stress_only and not include_stress_only:
                    return
                for entry in node["case_studies"]:
                    mws_id = str(entry.get("mws_id") or "").strip()
                    if not mws_id:
                        continue
                    rows.append(
                        {
                            "case_study_id": entry.get("case_study_id"),
                            "mws_id": mws_id,
                            "lat": entry.get("lat"),
                            "lng": entry.get("lng"),
                            "production_system": production,
                            "observed_stress": stress,
                            "expected_pathway": None if is_stress_only else pathway,
                            "stress_only": is_stress_only,
                        }
                    )
            for key, value in node.items():
                if key == "production_systems":
                    for prod, pdata in (value or {}).items():
                        for stress_name, sdata in (pdata.get("observed_stresses") or {}).items():
                            for pathway_id, pdata2 in (sdata.get("causal_pathways") or {}).items():
                                walk(pdata2, prod, stress_name, pathway_id)
                elif key not in ("meta", "diagnosis_framework", "normalisation_note", "note"):
                    walk(value, production, stress, pathway)
        elif isinstance(node, list):
            for item in node:
                walk(item, production, stress, pathway)

    walk(raw.get("diagnosis_framework") or raw)
    return rows


def enrich_instances_with_admin(db, instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    uids = sorted({str(row.get("mws_id") or "").strip() for row in instances if row.get("mws_id")})
    admin: dict[str, dict[str, str]] = {}
    if uids:
        for doc in db.mws_data.find(
            {"uid": {"$in": uids}},
            {"uid": 1, "state": 1, "district": 1, "tehsil": 1, "tehsils": 1},
        ):
            uid = str(doc.get("uid") or "").strip()
            ref = primary_tehsil(doc)
            if uid and ref:
                admin[uid] = {
                    "state": ref["state"],
                    "district": ref["district"],
                    "tehsil": ref["tehsil"],
                }
    for row in instances:
        loc = admin.get(str(row.get("mws_id") or ""), {})
        row["state"] = loc.get("state", "")
        row["district"] = loc.get("district", "")
        row["tehsil"] = loc.get("tehsil", "")
    return instances


def framework_actual_pathways(production_system: str, observed_stress: str) -> list[str]:
    framework = load_framework()["diagnosis_framework"]["production_systems"]
    stress_node = (
        framework.get(production_system, {})
        .get("observed_stresses", {})
        .get(observed_stress, {})
    )
    pathways = list((stress_node.get("causal_pathways") or {}).keys())
    if STRESS_ONLY_PATHWAY not in pathways:
        pathways.append(STRESS_ONLY_PATHWAY)
    return pathways


def _actual_pathways_in_instances(instances: list[dict[str, Any]]) -> set[str]:
    actuals: set[str] = set()
    for instance in instances:
        if instance.get("stress_only"):
            actuals.add(STRESS_ONLY_PATHWAY)
            continue
        pathway = str(instance.get("expected_pathway") or "").strip()
        if pathway:
            actuals.add(pathway)
    return actuals


def matrix_columns_for_section(production_system: str, observed_stress: str) -> list[str]:
    """Predicted-axis columns: built pathways with cards for this section tuple."""
    return built_pathways_for_section(production_system, observed_stress)


def matrix_pathways_for_section(
    production_system: str,
    observed_stress: str,
    instances: list[dict[str, Any]],
) -> list[str]:
    """Matrix rows: built pathways for this section plus any actual pathways in case studies."""
    built = set(built_pathways_for_section(production_system, observed_stress))
    rows = built | _actual_pathways_in_instances(instances)
    return sorted(rows, key=lambda pid: (pid == STRESS_ONLY_PATHWAY, pid))


def section_pathways_for_section(production_system: str, observed_stress: str) -> list[str]:
    """Built pathways in this section — used for signal grid grouping."""
    return matrix_columns_for_section(production_system, observed_stress)


def section_key(production_system: str, observed_stress: str) -> str:
    ps = re.sub(r"[^a-z0-9]+", "_", str(production_system or "").strip().lower()).strip("_")
    stress = str(observed_stress or "").strip()
    return f"{ps}__{stress}"


def group_instances_into_sections(instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in instances:
        production = str(row.get("production_system") or "")
        stress = str(row.get("observed_stress") or "")
        if not production or not stress:
            continue
        buckets.setdefault((production, stress), []).append(row)

    sections: list[dict[str, Any]] = []
    for (production, stress), rows in sorted(buckets.items()):
        rows.sort(key=lambda item: (item.get("case_study_id") or 0, item.get("mws_id") or ""))
        sections.append(
            {
                "section_key": section_key(production, stress),
                "production_system": production,
                "observed_stress": stress,
                "actual_pathways": framework_actual_pathways(production, stress),
                "matrix_pathways": matrix_pathways_for_section(production, stress, rows),
                "matrix_columns": matrix_columns_for_section(production, stress),
                "predicted_pathways": section_pathways_for_section(production, stress),
                "instances": rows,
            }
        )
    return sections


def load_catalog_bundle(db, filename: str) -> dict[str, Any]:
    instances = enrich_instances_with_admin(db, load_case_study_rows_from_file(filename))
    sections = [
        section
        for section in group_instances_into_sections(instances)
        if section_has_built_pathways(section["production_system"], section["observed_stress"])
    ]
    return {
        "filename": filename.replace("\\", "/"),
        "instance_count": len(instances),
        "sections": sections,
    }
