#!/usr/bin/env python3
"""Cross-check variable registry against framework, assembler, cards, and case-study exports."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap(runtime=True)

from dotenv import load_dotenv  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from services.assembler import NOT_AVAILABLE, VARIABLE_RESOLVERS, find_pathway, load_framework, resolve_variable  # noqa: E402
from services.derived_variables import resolve_derived  # noqa: E402
from services.variable_registry import (  # noqa: E402
    DROUGHT_CAUSALITY_ALIASES,
    STATIC_CD_VARIABLES,
    alias_to_canonical,
    canonical_name,
    collect_drought_nested_keys,
    drought_invented_expression_keys,
    drought_source_key_map,
    is_static_variable,
    known_variable_names,
    load_data_dictionary,
    load_registry,
    registry_variables,
    variable_type,
)

RAW_CARD_DIR = ROOT / "data" / "evidence_cards" / "raw"
CASE_STUDY_DIR = ROOT / "data" / "raw_jsons"
AUDIT_DIR = ROOT / "data" / "audits"

STATIC_INDEX_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[[^\]]+\]"
)
GET_CALL_RE = re.compile(
    r"\b(drought_causality(?:_json)?)\.get\s*\(\s*['\"]([^'\"]+)['\"]"
)


def framework_variables() -> dict[str, str]:
    root = load_framework()["diagnosis_framework"]["production_systems"]
    out: dict[str, str] = {}
    for _prod, pdata in root.items():
        for _stress, sdata in pdata.get("observed_stresses", {}).items():
            for pathway_id, cfg in sdata.get("causal_pathways", {}).items():
                for var_def in cfg.get("diagnostic_variables", []):
                    name = var_def["variable"]
                    out[name] = var_def.get("availability", "available")
    return out


def derived_variable_names() -> set[str]:
    return {
        "mean_annual_precipitation_mm",
        "trend_annual_precipitation_mm",
        "mean_annual_et_mm",
        "trend_annual_et_mm",
        "mean_annual_runoff_mm",
        "trend_annual_runoff_mm",
        "mean_annual_delta_g_mm",
        "trend_annual_delta_g_mm",
        "mean_cropping_intensity",
        "trend_cropping_intensity",
        "mean_kharif_cropped_area_ha",
        "trend_kharif_cropped_area_ha",
        "mean_double_crop_area_ha",
        "trend_double_crop_area_ha",
        "drought_moderate_return_period",
        "drought_severe_return_period",
        "mean_swb_total_area_ha",
        "trend_swb_total_area_ha",
        "mean_swb_rabi_kharif_ratio",
        "trend_swb_rabi_kharif_ratio",
    }


def all_known_names() -> set[str]:
    names = known_variable_names()
    names.update(VARIABLE_RESOLVERS)
    names.update(NOT_AVAILABLE)
    names.update(derived_variable_names())
    names.update(framework_variables())
    names.add("True")
    names.add("False")
    names.add("None")
    return names


def extract_ast_names(expression: str) -> set[str]:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()
    allowed_builtins = {
        "abs", "min", "max", "len", "sum", "sorted", "round", "float", "int", "str",
        "list", "dict", "any", "all", "set", "tuple", "range", "enumerate", "zip",
    }
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    bound.add(sub.id)
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id not in allowed_builtins
        and node.id not in bound
    }


def audit_cards(known: set[str]) -> dict:
    findings: list[dict] = []
    invented = drought_invented_expression_keys()
    cards_scanned = 0

    for card_path in sorted(RAW_CARD_DIR.glob("*.json")):
        cards_scanned += 1
        card = json.loads(card_path.read_text(encoding="utf-8"))
        card_id = card.get("card_id") or card_path.stem
        for sig in card.get("diagnostic_signals", []):
            sig_id = sig.get("signal_id", "?")
            expression = (sig.get("condition") or {}).get("expression") or sig.get("expression") or ""
            if not expression.strip():
                continue

            for match in GET_CALL_RE.finditer(expression):
                key = match.group(2)
                if key in invented:
                    findings.append(
                        {
                            "severity": "NESTED",
                            "category": "invented_drought_key",
                            "card_id": card_id,
                            "signal_id": sig_id,
                            "detail": f".get('{key}') on drought causality is not in nested schema",
                            "expression": expression,
                        }
                    )

            for match in STATIC_INDEX_RE.finditer(expression):
                var = match.group(1)
                if is_static_variable(var):
                    findings.append(
                        {
                            "severity": "SHAPE",
                            "category": "static_indexed_as_series",
                            "card_id": card_id,
                            "signal_id": sig_id,
                            "detail": f"{var} is static but indexed as {match.group(0)}",
                            "expression": expression,
                        }
                    )

            for name in extract_ast_names(expression):
                if name in known:
                    canonical = canonical_name(name)
                    if name != canonical and name in alias_to_canonical():
                        findings.append(
                            {
                                "severity": "ALIAS",
                                "category": "legacy_name_in_expression",
                                "card_id": card_id,
                                "signal_id": sig_id,
                                "detail": f"{name} should migrate to {canonical}",
                                "expression": expression,
                            }
                        )
                    continue
                findings.append(
                    {
                        "severity": "BLOCKER",
                        "category": "unknown_identifier",
                        "card_id": card_id,
                        "signal_id": sig_id,
                        "detail": f"unknown identifier '{name}'",
                        "expression": expression,
                    }
                )

            try:
                ast.parse(expression, mode="eval")
            except SyntaxError as exc:
                findings.append(
                    {
                        "severity": "BLOCKER",
                        "category": "invalid_python",
                        "card_id": card_id,
                        "signal_id": sig_id,
                        "detail": str(exc),
                        "expression": expression,
                    }
                )

    by_severity: dict[str, list] = {"BLOCKER": [], "SHAPE": [], "NESTED": [], "ALIAS": []}
    for item in findings:
        by_severity[item["severity"]].append(item)

    return {
        "cards_scanned": cards_scanned,
        "findings": findings,
        "counts": {k: len(v) for k, v in by_severity.items()},
        "by_severity": by_severity,
    }


def audit_framework_registry() -> dict:
    fw = framework_variables()
    registry = registry_variables()
    dd = load_data_dictionary().get("variables", {})
    missing_registry: list[str] = []
    missing_resolver: list[str] = []

    for name, availability in sorted(fw.items()):
        canonical = canonical_name(name)
        if availability == "not_available":
            continue
        if canonical not in registry and name not in dd and name not in VARIABLE_RESOLVERS and name not in derived_variable_names():
            missing_registry.append(name)
        if name not in VARIABLE_RESOLVERS and name not in derived_variable_names() and name not in NOT_AVAILABLE:
            missing_resolver.append(name)

    return {
        "framework_variables": len(fw),
        "missing_registry_entry": missing_registry,
        "missing_resolver": missing_resolver,
    }


def audit_case_study_exports() -> dict:
    raw_keys: set[str] = set()
    unmapped_drought_keys: set[str] = set()
    files_scanned = 0
    key_map = drought_source_key_map()
    canonical_drought = set()
    for meta in registry_variables().get("drought_causality", {}).get("nested_schema", {}).values():
        canonical_drought.update(meta)

    for path in sorted(CASE_STUDY_DIR.glob("*.json")):
        files_scanned += 1
        doc = json.loads(path.read_text(encoding="utf-8"))
        present = doc.get("present_variables") or {}
        raw_keys.update(present.keys())
        drought_blob = None
        for alias in DROUGHT_CAUSALITY_ALIASES:
            if alias in present:
                drought_blob = present[alias]
                break
        for key in collect_drought_nested_keys(drought_blob):
            if key not in canonical_drought and key not in key_map:
                unmapped_drought_keys.add(key)
            elif key in key_map and key_map[key] not in canonical_drought:
                unmapped_drought_keys.add(key)

    legacy_present = sorted(k for k in raw_keys if k in alias_to_canonical() and k != canonical_name(k))
    return {
        "files_scanned": files_scanned,
        "present_variable_keys": sorted(raw_keys),
        "legacy_present_variable_keys": legacy_present,
        "unmapped_drought_nested_keys": sorted(unmapped_drought_keys),
    }


def audit_mongo_drought_keys(db) -> dict:
    if db is None:
        return {"skipped": True, "reason": "no Mongo connection"}
    keys: set[str] = set()
    sample = 0
    for doc in db.mws_data.find({"drought_causality": {"$exists": True}}, {"drought_causality": 1}).limit(500):
        sample += 1
        keys.update(collect_drought_nested_keys(doc.get("drought_causality")))
    key_map = drought_source_key_map()
    canonical = set()
    for meta in registry_variables().get("drought_causality", {}).get("nested_schema", {}).values():
        canonical.update(meta)
    raw_only = sorted(k for k in keys if k in key_map)
    unmapped = sorted(k for k in keys if k not in canonical and k not in key_map)
    return {
        "sample_docs": sample,
        "nested_keys_seen": sorted(keys),
        "raw_excel_keys_still_present": raw_only,
        "unmapped_keys": unmapped,
    }


def audit_resolver_shapes(db, uids: list[str]) -> dict:
    if db is None:
        return {"skipped": True}
    mismatches: list[dict] = []
    for uid in uids:
        doc = db.mws_data.find_one({"uid": uid})
        if not doc:
            continue
        for var in sorted(STATIC_CD_VARIABLES):
            value = resolve_variable(doc, var)
            expected = "static"
            actual = type(value).__name__
            if value is not None and not isinstance(value, (int, float)):
                mismatches.append({"uid": uid, "variable": var, "expected": expected, "actual": actual})
        for var in DROUGHT_CAUSALITY_ALIASES:
            value = resolve_variable(doc, var)
            if value is not None and not isinstance(value, dict):
                mismatches.append({"uid": uid, "variable": var, "expected": "nested_time_series", "actual": type(value).__name__})
    return {"uids_checked": uids, "shape_mismatches": mismatches}


def run_audit(*, use_mongo: bool = True) -> dict:
    known = all_known_names()
    report = {
        "audited_at": date.today().isoformat(),
        "registry_version": load_registry().get("version"),
        "framework": audit_framework_registry(),
        "cards": audit_cards(known),
        "case_study_exports": audit_case_study_exports(),
    }

    db = None
    if use_mongo:
        load_dotenv(ROOT / ".env")
        try:
            client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000)
            db = client["diagnosis_db"]
            client.admin.command("ping")
            report["mongo_drought_keys"] = audit_mongo_drought_keys(db)
            uids = [p.stem for p in CASE_STUDY_DIR.glob("*.json")][:8]
            report["resolver_shapes"] = audit_resolver_shapes(db, uids)
            client.close()
        except Exception as exc:  # noqa: BLE001
            report["mongo"] = {"skipped": True, "error": str(exc)}

    counts = report["cards"]["counts"]
    report["summary"] = {
        "blockers": counts.get("BLOCKER", 0),
        "shape_issues": counts.get("SHAPE", 0),
        "nested_issues": counts.get("NESTED", 0),
        "alias_usages": counts.get("ALIAS", 0),
        "exit_ok": counts.get("BLOCKER", 0) == 0 and counts.get("SHAPE", 0) == 0 and counts.get("NESTED", 0) == 0,
        "aliases_clean": counts.get("ALIAS", 0) == 0,
    }
    return report


def print_report(report: dict) -> None:
    summary = report["summary"]
    cards = report["cards"]["counts"]
    print("=== Variable naming audit ===")
    print(f"  Registry version: {report.get('registry_version')}")
    print(f"  Cards scanned:    {report['cards']['cards_scanned']}")
    print(f"  BLOCKER:          {cards.get('BLOCKER', 0)}")
    print(f"  SHAPE:            {cards.get('SHAPE', 0)}")
    print(f"  NESTED:           {cards.get('NESTED', 0)}")
    print(f"  ALIAS:            {cards.get('ALIAS', 0)}")
    fw = report["framework"]
    print(f"  Framework vars missing registry: {len(fw.get('missing_registry_entry', []))}")
    print(f"  Framework vars missing resolver: {len(fw.get('missing_resolver', []))}")
    cs = report["case_study_exports"]
    print(f"  Case-study exports: {cs.get('files_scanned', 0)}")
    print(f"  Unmapped drought nested keys in exports: {len(cs.get('unmapped_drought_nested_keys', []))}")
    if report.get("mongo_drought_keys"):
        md = report["mongo_drought_keys"]
        if not md.get("skipped"):
            print(f"  Mongo drought raw keys (sample): {len(md.get('raw_excel_keys_still_present', []))}")
    if summary.get("alias_usages", 0):
        print(f"  WARNING: {summary['alias_usages']} legacy alias usages remain in card expressions")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-mongo", action="store_true", help="Skip Mongo checks")
    parser.add_argument(
        "--strict-aliases",
        action="store_true",
        help="Exit non-zero when legacy alias names remain in card expressions",
    )
    parser.add_argument("--write-report", type=Path, help="Write JSON report path")
    args = parser.parse_args()

    report = run_audit(use_mongo=not args.no_mongo)
    print_report(report)

    out_path = args.write_report
    if out_path is None:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = AUDIT_DIR / f"variable_naming_{date.today().isoformat()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written: {out_path}")

    summary = report["summary"]
    if not summary["exit_ok"]:
        return 1
    if args.strict_aliases and not summary.get("aliases_clean", True):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
