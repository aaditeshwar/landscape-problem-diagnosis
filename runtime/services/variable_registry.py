"""Canonical variable registry: names, aliases, types, and Mongo normalization helpers."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import METADATA_DIR
from services.derived_variables import IDM_INDICATOR_TRIGGER_SCORE, DROUGHT_DERIVED_VARIABLE_NAMES

STATIC_CD_VARIABLES = frozenset(
    {
        "cd_urbanization_ha",
        "cd_total_urbanization_ha",
        "cd_afforestation_ha",
        "cd_total_afforestation_ha",
        "cd_total_degradation_ha",
        "cd_farm_to_barren_ha",
        "cd_total_deforestation_ha",
        "cd_forest_to_farm_ha",
        "cd_single_to_double_ha",
    }
)

DROUGHT_CAUSALITY_ALIASES = frozenset({"drought_causality", "drought_causality_json"})


@lru_cache
def load_registry() -> dict:
    path = METADATA_DIR / "variable_registry.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)["variable_registry"]


@lru_cache
def load_data_dictionary() -> dict:
    path = METADATA_DIR / "data_dictionary_v2.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)["data_dictionary"]


def registry_variables() -> dict[str, dict]:
    return load_registry().get("variables", {})


def drought_source_key_map() -> dict[str, str]:
    entry = registry_variables().get("drought_causality", {})
    return dict(entry.get("source_key_map", {}))


def drought_invented_expression_keys() -> frozenset[str]:
    entry = registry_variables().get("drought_causality", {})
    return frozenset(entry.get("invented_expression_keys", []))


@lru_cache
def alias_to_canonical() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical, meta in registry_variables().items():
        mapping[canonical] = canonical
        for alias in meta.get("legacy_aliases", []):
            mapping[alias] = canonical
    return mapping


@lru_cache
def canonical_to_resolver_key() -> dict[str, str]:
    """Map canonical registry names to assembler resolver keys (framework names)."""
    mapping: dict[str, str] = {}
    for canonical, meta in registry_variables().items():
        aliases = meta.get("legacy_aliases") or []
        resolver_key = aliases[0] if aliases else canonical
        mapping[canonical] = resolver_key
        for alias in aliases:
            mapping[alias] = resolver_key
        mapping[resolver_key] = resolver_key
    return mapping


def canonical_name(name: str) -> str:
    return alias_to_canonical().get(name, name)


def resolver_key_for(name: str) -> str:
    canonical = canonical_name(name)
    return canonical_to_resolver_key().get(canonical, name)


def variable_type(name: str) -> str | None:
    canonical = canonical_name(name)
    meta = registry_variables().get(canonical)
    if meta:
        return meta.get("type")
    dd = load_data_dictionary().get("variables", {}).get(canonical)
    if dd:
        return dd.get("type")
    return None


def is_static_variable(name: str) -> bool:
    vtype = variable_type(name)
    if vtype == "static":
        return True
    return name in STATIC_CD_VARIABLES


def is_nested_time_series(name: str) -> bool:
    return variable_type(name) == "nested_time_series"


def known_variable_names() -> set[str]:
    names: set[str] = set(load_data_dictionary().get("variables", {}))
    for canonical, meta in registry_variables().items():
        names.add(canonical)
        names.update(meta.get("legacy_aliases", []))
    names.update(DROUGHT_DERIVED_VARIABLE_NAMES)
    return names


def normalize_drought_severity_block(block: dict | None) -> dict:
    if not isinstance(block, dict):
        return {}
    key_map = drought_source_key_map()
    normalized: dict[str, Any] = {}
    for raw_key, value in block.items():
        canonical_key = key_map.get(raw_key, raw_key)
        normalized[canonical_key] = value
    return normalized


def normalize_drought_causality(causality: dict | None) -> dict:
    """Remap Excel/Mongo drought causality keys to dictionary nested schema."""
    if not isinstance(causality, dict):
        return {}
    normalized: dict[str, Any] = {}
    for year, payload in causality.items():
        if not isinstance(payload, dict):
            normalized[str(year)] = payload
            continue
        normalized[str(year)] = {
            "severe_moderate": normalize_drought_severity_block(payload.get("severe_moderate")),
            "mild": normalize_drought_severity_block(payload.get("mild")),
        }
    return normalized


def collect_drought_nested_keys(causality: dict | None) -> set[str]:
    keys: set[str] = set()
    if not isinstance(causality, dict):
        return keys
    for payload in causality.values():
        if not isinstance(payload, dict):
            continue
        for severity in ("severe_moderate", "mild"):
            block = payload.get(severity)
            if isinstance(block, dict):
                keys.update(block.keys())
    return keys


@lru_cache
def list_type_variables() -> frozenset[str]:
    """Variables whose dictionary unit is a list — default to [] when absent from MWS."""
    names: set[str] = set()
    for name, meta in load_data_dictionary().get("variables", {}).items():
        unit = str(meta.get("unit") or "").lower()
        if "list" in unit:
            names.add(name)
    for canonical, meta in registry_variables().items():
        unit = str(meta.get("unit") or "").lower()
        if "list" in unit:
            names.add(canonical)
    return frozenset(names)


PRESENCE_CATEGORICAL_VARIABLES = frozenset(
    {
        "canal_name",
        "river_name",
    }
)


@lru_cache
def presence_categorical_variables() -> frozenset[str]:
    """Static categoricals where None in present means feature absent, not missing data."""
    return PRESENCE_CATEGORICAL_VARIABLES


def extend_resolver_map(resolvers: dict[str, Any]) -> dict[str, Any]:
    """Add canonical and legacy alias keys that point to the same resolver."""
    extended = dict(resolvers)
    for canonical, meta in registry_variables().items():
        aliases = meta.get("legacy_aliases") or []
        if aliases and aliases[0] in extended:
            base_key = aliases[0]
        elif canonical in extended:
            base_key = canonical
        else:
            continue
        resolver = extended[base_key]
        if canonical not in extended:
            extended[canonical] = resolver
        for alias in aliases:
            if alias not in extended:
                extended[alias] = resolver
    return extended


_STATIC_INDEX_RE = re.compile(
    r"\b(" + "|".join(re.escape(v) for v in sorted(STATIC_CD_VARIABLES, key=len, reverse=True)) + r")\s*\[[^\]]+\]"
)


def strip_static_variable_indexing(expression: str) -> str:
    return _STATIC_INDEX_RE.sub(r"\1", expression)


def rewrite_static_cd_trend_expression(expression: str) -> str:
    """Rewrite cumulative static cd_* trend idioms to scalar threshold checks."""
    expr = strip_static_variable_indexing(expression)
    for var in sorted(STATIC_CD_VARIABLES, key=len, reverse=True):
        trend_pattern = re.compile(
            rf"{re.escape(var)}\s*>\s*{re.escape(var)}\s*and\s*\(\s*{re.escape(var)}\s*-\s*{re.escape(var)}\s*\)\s*>\s*(?P<threshold>[\d.]+)",
            re.IGNORECASE,
        )
        expr = trend_pattern.sub(rf"{var} > \g<threshold>", expr)
        diff_only = re.compile(
            rf"\(\s*{re.escape(var)}\s*-\s*{re.escape(var)}\s*\)\s*>\s*(?P<threshold>[\d.]+)"
        )
        expr = diff_only.sub(rf"{var} > \g<threshold>", expr)
    return expr


def rewrite_drought_causality_expression(expression: str) -> str:
    """Rewrite legacy flat drought_causality.get(...) patterns to derived latest-score scalars."""
    score = str(int(IDM_INDICATOR_TRIGGER_SCORE))
    expr = expression
    dc = r"drought_causality"

    spi_trigger = (
        rf"({dc}\.get\(['\"]spi_kharif['\"],\s*[^)]+\)\s*(?:<=|<)\s*-1\.0|"
        rf"{dc}\.get\(['\"]SPI_kharif['\"],\s*[^)]+\)\s*(?:<=|<)\s*-1\.0)"
    )
    expr = re.sub(spi_trigger, f"drought_mild_spi_score_latest >= {score}", expr, flags=re.IGNORECASE)

    expr = re.sub(
        rf"{dc}\.get\(['\"]mai_kharif['\"],\s*[^)]+\)\s*<\s*(?:0\.5|0\.75)",
        f"drought_mild_mai_score_latest >= {score}",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(
        rf"{dc}\.get\(['\"]vci_kharif['\"],\s*[^)]+\)\s*<\s*(?:35|40|0\.35)",
        f"drought_mild_vci_score_latest >= {score}",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(
        rf"{dc}\.get\(['\"]VCI_kharif['\"],\s*[^)]+\)\s*<\s*(?:35|40)",
        f"drought_mild_vci_score_latest >= {score}",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(
        rf"{dc}\.get\(['\"]spi_class['\"]\)\s*in\s*\[[^\]]+\]",
        f"(drought_mild_spi_score_latest >= {score} or drought_severe_moderate_spi_score_latest >= {score})",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(
        rf"{dc}\.get\(['\"]mai_class['\"]\)\s*in\s*\[[^\]]+\]",
        f"(drought_mild_mai_score_latest >= {score} or drought_severe_moderate_path_score_latest >= 2)",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(
        rf"{dc}\.get\(['\"]vci['\"]\)\s*is not None and {dc}\.get\(['\"]vci['\"]\)\s*<\s*(?:35|40)",
        f"drought_mild_vci_score_latest >= {score}",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(
        rf"{dc}\.get\(['\"]vci['\"],\s*[^)]+\)\s*<\s*(?:35|40)",
        f"drought_mild_vci_score_latest >= {score}",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(
        rf"{dc}\.get\(['\"]vci['\"]\)\s*<\s*(?:35|40)",
        f"drought_mild_vci_score_latest >= {score}",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(
        rf"{dc}\.get\(['\"]mai['\"]\)\s*<\s*0\.5",
        f"drought_mild_mai_score_latest >= {score}",
        expr,
        flags=re.IGNORECASE,
    )
    return expr


def registry_excerpt_block() -> str:
    """Human-readable registry excerpt for card-generation prompts."""
    lines = ["Variable registry policy (canonical names and shapes):"]
    policy = load_registry().get("expression_access", {})
    for key, text in policy.items():
        lines.append(f"  {key}: {text}")
    lines.append("  drought derived scalars (latest agricultural year, India Drought Manual trigger scores):")
    for name in sorted(DROUGHT_DERIVED_VARIABLE_NAMES):
        lines.append(f"    {name}: compare directly, e.g. {name} >= 26")
    lines.append("  drought_causality nested access example:")
    lines.append(
        "    drought_causality[sorted(drought_causality.keys())[-1]]['mild']['spi_score']"
    )
    lines.append("  Do NOT use invented flat keys: spi_class, spi_kharif, mai_kharif, vci_kharif.")
    return "\n".join(lines)


def normalize_expression(expression: str) -> tuple[str, list[str]]:
    """Apply deterministic expression rewrites; return patched expression and change notes."""
    notes: list[str] = []
    original = expression
    expr = expression.replace(" AND ", " and ").replace(" OR ", " or ")
    if expr != expression:
        notes.append("normalized boolean operators")
    if "drought_causality_json" in expr:
        expr = re.sub(r"\bdrought_causality_json\b", "drought_causality", expr)
        notes.append("renamed drought_causality_json to drought_causality")
    drought_before = expr
    expr = rewrite_drought_causality_expression(expr)
    if expr != drought_before:
        notes.append("rewrote drought_causality flat .get() keys to derived latest-score scalars")
    expr = rewrite_static_cd_trend_expression(expr)
    if expr != original and not notes:
        notes.append("rewrote static cd_* indexing/threshold pattern")
    return expr, notes
