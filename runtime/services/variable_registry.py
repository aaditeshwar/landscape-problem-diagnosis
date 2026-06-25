"""Canonical variable registry: names, aliases, types, and Mongo normalization helpers."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import METADATA_DIR
from services.derived_variables import (
    ASSEMBLER_DERIVED_VARIABLE_NAMES,
    DROUGHT_DERIVED_VARIABLE_NAMES,
    IDM_INDICATOR_TRIGGER_SCORE,
)

STATIC_CD_VARIABLES = frozenset(
    {
        "cd_farm_to_barren_ha",
        "cd_farm_to_built_up_ha",
        "cd_farm_to_farm_ha",
        "cd_farm_to_scrubland_ha",
        "cd_total_degradation_ha",
        "cd_forest_to_barren_ha",
        "cd_forest_to_built_up_ha",
        "cd_forest_to_farm_ha",
        "cd_deforestation_forest_to_forest_ha",
        "cd_forest_to_scrubland_ha",
        "cd_total_deforestation_ha",
        "cd_barren_shrub_to_built_up_ha",
        "cd_built_up_to_built_up_ha",
        "cd_tree_farm_to_built_up_ha",
        "cd_water_to_built_up_ha",
        "cd_urbanization_ha",
        "cd_total_urbanization_ha",
        "cd_barren_to_forest_ha",
        "cd_built_up_to_forest_ha",
        "cd_farm_to_forest_ha",
        "cd_afforestation_forest_to_forest_ha",
        "cd_scrubland_to_forest_ha",
        "cd_afforestation_ha",
        "cd_total_afforestation_ha",
        "cd_single_to_single_ha",
        "cd_single_to_double_ha",
        "cd_single_to_triple_ha",
        "cd_double_to_single_ha",
        "cd_double_to_double_ha",
        "cd_double_to_triple_ha",
        "cd_triple_to_single_ha",
        "cd_triple_to_double_ha",
        "cd_triple_to_triple_ha",
        "cd_crop_intensity_total_change_ha",
    }
)

DROUGHT_CAUSALITY_ALIASES = frozenset({"drought_causality", "drought_causality_json"})

# Entire drought_causality sheet (SPI/MAI/VCI, drought paths, cropping_area_sown_score, etc.)
# is omitted from diagnosis LLM prompts — use drought_weeks, dry_spell_weeks, precipitation, etc.
DROUGHT_LLM_EXCLUDED_DERIVED_VARIABLES = DROUGHT_DERIVED_VARIABLE_NAMES

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


@lru_cache
def framework_variable_availability() -> dict[str, str]:
    path = METADATA_DIR / "diagnosis_framework.json"
    with path.open(encoding="utf-8") as fh:
        root = json.load(fh)["diagnosis_framework"]["production_systems"]
    out: dict[str, str] = {}
    for pdata in root.values():
        for sdata in pdata.get("observed_stresses", {}).values():
            for cfg in sdata.get("causal_pathways", {}).values():
                for var_def in cfg.get("diagnostic_variables", []):
                    name = var_def["variable"]
                    out[name] = var_def.get("availability", "available")
    return out


_EXTRA_NOT_AVAILABLE = frozenset({"well_depth_m", "canal_command_coverage"})


@lru_cache
def not_available_variables() -> frozenset[str]:
    """Variables with no landscape resolver unless user injects an answer."""
    names: set[str] = set(_EXTRA_NOT_AVAILABLE)
    for name, availability in framework_variable_availability().items():
        if availability == "not_available":
            names.add(name)
    for canonical, meta in registry_variables().items():
        if meta.get("type") in {"not_available", "user_elicited"}:
            names.add(canonical)
            names.update(meta.get("legacy_aliases", []))
    return frozenset(names)


_DEFAULT_STATIC_THRESHOLDS: dict[str, str] = {
    "cd_forest_to_farm_ha": "30",
    "cd_urbanization_ha": "20",
    "cd_total_urbanization_ha": "20",
    "cd_afforestation_ha": "10",
    "cd_total_afforestation_ha": "10",
}

_TAUTOLOGY_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*>\s*\1\b")
_SUM_SELF_GROWTH_RE = re.compile(
    r"\(\s*(?P<a>[A-Za-z_][A-Za-z0-9_]*)\s*\+\s*(?P<b>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*>\s*"
    r"\(\s*(?P=a)\s*\+\s*(?P=b)\s*\)\s*\*\s*[\d.]+"
)
_THRESHOLD_FROM_EXPR_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\s*>\s*([\d.]+)\b"
)


def card_variable_thresholds(card: dict) -> dict[str, str]:
    """Collect scalar thresholds already used for each variable on a card."""
    thresholds: dict[str, str] = {}
    alias_map = alias_to_canonical()
    for sig in card.get("diagnostic_signals") or []:
        condition = sig.get("condition") or {}
        expression = condition.get("expression") or sig.get("expression") or ""
        if not expression or _TAUTOLOGY_RE.search(expression):
            continue
        for var, value in _THRESHOLD_FROM_EXPR_RE.findall(expression):
            if _TAUTOLOGY_RE.search(f"{var} > {value}"):
                continue
            canonical = alias_map.get(var, var)
            thresholds[canonical] = value
            thresholds[var] = value
    return thresholds


def rewrite_self_comparison_tautologies(expression: str, thresholds: dict[str, str] | None = None) -> str:
    """Replace var > var patterns on static cd_* variables with scalar thresholds."""
    thresholds = thresholds or {}
    alias_map = alias_to_canonical()

    def _threshold_for(var: str) -> str:
        canonical = alias_map.get(var, var)
        return (
            thresholds.get(canonical)
            or thresholds.get(var)
            or _DEFAULT_STATIC_THRESHOLDS.get(canonical)
            or _DEFAULT_STATIC_THRESHOLDS.get(var)
            or "0"
        )

    expr = _SUM_SELF_GROWTH_RE.sub(
        lambda m: f"({m.group('a')} + {m.group('b')}) > "
        f"{float(_threshold_for(m.group('a'))) + float(_threshold_for(m.group('b')))}",
        expression,
    )

    def _replace(match: re.Match[str]) -> str:
        var = match.group(1)
        return f"{var} > {_threshold_for(var)}"

    return _TAUTOLOGY_RE.sub(_replace, expr)


def apply_legacy_aliases_to_expression(expression: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    expr = expression
    alias_map = alias_to_canonical()
    for alias in sorted(alias_map, key=len, reverse=True):
        canonical = alias_map[alias]
        if alias == canonical or alias not in expr:
            continue
        patched = re.sub(rf"\b{re.escape(alias)}\b", canonical, expr)
        if patched != expr:
            notes.append(f"renamed {alias} to {canonical}")
            expr = patched
    return expr, notes


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


def sanitize_drought_causality_for_llm(causality: dict | None) -> dict[str, Any]:
    """drought_causality is not passed to diagnosis LLM prompts (sheet data is unreliable)."""
    return {}


def sanitize_present_variables_for_llm(present: dict[str, Any] | None) -> dict[str, Any]:
    """Remove drought_causality sheet variables from diagnosis prompt payloads."""
    if not present:
        return {}
    out: dict[str, Any] = {}
    for name, value in present.items():
        if name in DROUGHT_CAUSALITY_ALIASES:
            continue
        if name in DROUGHT_LLM_EXCLUDED_DERIVED_VARIABLES:
            continue
        out[name] = value
    return out


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
        expr = _TAUTOLOGY_RE.sub(
            lambda m, v=var: f"{v} > {_DEFAULT_STATIC_THRESHOLDS.get(v, '0')}"
            if m.group(1) == v
            else m.group(0),
            expr,
        )
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


def registry_excerpt_block(*, for_diagnosis: bool = False) -> str:
    """Human-readable registry excerpt for card-generation prompts."""
    lines = ["Variable registry policy (canonical names and shapes):"]
    policy = load_registry().get("expression_access", {})
    for key, text in policy.items():
        lines.append(f"  {key}: {text}")
    drought_derived = sorted(DROUGHT_DERIVED_VARIABLE_NAMES)
    if for_diagnosis:
        lines.append(
            "  drought_causality and drought_causality-derived scalars are omitted from diagnosis prompts "
            "(unreliable sheet data). Use drought_weeks, dry_spell_weeks, kharif_drought_total_weeks, "
            "precipitation_mm, kharif_cropped_area_percent, and drought_severe_return_period instead."
        )
    else:
        lines.append("  drought derived scalars (latest agricultural year, India Drought Manual trigger scores):")
        for name in drought_derived:
            lines.append(f"    {name}: compare directly, e.g. {name} >= 26")
        lines.append("  drought_causality nested access example:")
        lines.append(
            "    drought_causality[sorted(drought_causality.keys())[-1]]['mild']['spi_score']"
        )
    lines.append("  Do NOT use invented flat keys: spi_class, spi_kharif, mai_kharif, vci_kharif.")
    return "\n".join(lines)


def all_expression_allowed_names() -> set[str]:
    """Names valid in signal condition.expression (dictionary + assembler + derived)."""
    from services.assembler import NOT_AVAILABLE, VARIABLE_RESOLVERS

    names = known_variable_names()
    names.update(VARIABLE_RESOLVERS)
    names.update(NOT_AVAILABLE)
    names.update(ASSEMBLER_DERIVED_VARIABLE_NAMES)
    names.update(DROUGHT_DERIVED_VARIABLE_NAMES)
    names.update({"True", "False", "None"})
    return names


TIME_SERIES_EXPRESSION_VARIABLES: frozenset[str] = frozenset(
    {
        "annual_delta_g_mm",
        "annual_precipitation_mm",
        "annual_et_mm",
        "annual_runoff_mm",
        "seasonal_precipitation_mm",
        "seasonal_et_mm",
        "seasonal_runoff_mm",
        "seasonal_delta_g_mm",
        "drought_weeks_severe",
        "drought_weeks_moderate",
        "dry_spell_weeks",
        "monsoon_onset_date",
        "kharif_cropped_area_percent",
        "cropping_intensity",
        "lulc_single_kharif_ha",
        "lulc_double_crop_ha",
        "lulc_cropland_ha",
        "lulc_shrub_scrub_ha",
        "lulc_barrenland_ha",
        "lulc_tree_forest_ha",
        "lulc_krz_water_ha",
        "swb_total_area_ha",
        "swb_kharif_area_ha",
        "swb_rabi_area_ha",
        "swb_zaid_area_ha",
        "drought_causality",
        "drought_causality_json",
    }
)

SEASONAL_TIME_SERIES_VARIABLES: frozenset[str] = frozenset(
    {
        "seasonal_precipitation_mm",
        "seasonal_et_mm",
        "seasonal_runoff_mm",
        "seasonal_delta_g_mm",
    }
)

CATEGORICAL_SCALAR_VARIABLES: frozenset[str] = frozenset(
    {
        "aquifer_class",
        "aquifer_raw_class",
        "aquifer_dominant_lithology",
        "soge_class_name",
        "terrain_cluster_id",
        "river_name",
        "canal_name",
    }
)

STATIC_SNAPSHOT_VARIABLES: frozenset[str] = frozenset(
    {
        "soge_dev_percent",
        "soge_class_name",
        "aquifer_class",
        "aquifer_raw_class",
        "aquifer_dominant_lithology",
        "terrain_cluster_id",
        "terrain_description",
        "nbss_lup_aer_code",
        "river_name",
        "canal_name",
        "swb_count",
        "nrega_swc_count",
        "nrega_irrigation_count",
        "nrega_land_restoration_count",
        "dist_apmc_km",
        "dist_cooperative_km",
        "dist_milk_chilling_km",
        "village_population",
        "village_sc_percent",
        "village_st_percent",
        "village_literacy_rate",
    }
)


def full_review_registry_block() -> str:
    """Complete allowed-identifier list for Claude card review (Plan 15 / D1e)."""
    lines = [
        registry_excerpt_block(),
        "",
        "Complete allowed expression identifiers (data_dictionary_v2 + variable_registry + assembler resolvers + derived scalars):",
        "  Only flag D1e unregistered variables if the identifier is NOT listed below.",
        "  Do NOT flag .get() on dict-typed variables listed under 'Keyed dict variables' below.",
        "",
        "  Assembler-derived scalars (mean_*, trend_*, drought_*_return_period):",
    ]
    derived = sorted(ASSEMBLER_DERIVED_VARIABLE_NAMES | DROUGHT_DERIVED_VARIABLE_NAMES)
    for name in derived:
        lines.append(f"    {name}")
    skip = set(derived) | {"True", "False", "None"}
    framework = sorted(all_expression_allowed_names() - skip - TIME_SERIES_EXPRESSION_VARIABLES)
    lines.append(f"  Static / point-in-time framework variables ({len(framework)} names, alphabetical):")
    lines.append("    " + ", ".join(framework))
    lines.extend(
        [
            "",
            "Static block-level / point-in-time variables (one value per MWS — NOT time series):",
            "  CGWB SOGE is published annually in the real world, but this framework stores only the",
            "  current block-level snapshot on each MWS — not a year-keyed series.",
            "  Do NOT treat soge_dev_percent or soge_class_name as time series.",
            "  Do NOT suggest [-1], mean_soge, trend_soge, or multi-year persistence guards on SOGE.",
            "  Using soge_dev_percent > 70 in an expression is valid as a static threshold check.",
        ]
    )
    for name in sorted(STATIC_SNAPSHOT_VARIABLES):
        if name in TIME_SERIES_EXPRESSION_VARIABLES:
            continue
        lines.append(f"    {name}")
    lines.extend(
        [
            "",
            "Time-series variables (YearIndexedMapping at evaluation — NOT scalars):",
            "  Integer indexing is valid: var[-1] = latest agricultural year, var[0] = earliest.",
            "  Do NOT flag [-1] or [0] on these names as invalid scalar indexing.",
            "  For persistence across years prefer mean_*, trend_*, drought_*_return_period, or max(var).",
        ]
    )
    for name in sorted(TIME_SERIES_EXPRESSION_VARIABLES):
        if name in SEASONAL_TIME_SERIES_VARIABLES:
            lines.append(
                f"    {name}: yearly series; latest year block supports .get('kharif'|'rabi'|'zaid')"
            )
        else:
            lines.append(f"    {name}: yearly scalar per agricultural year")
    lines.extend(
        [
            "",
            "Categorical string scalars (dominant class / name — use == or in [...], NOT .get()):",
            "    aquifer_class — dominant ACWADAM class string from aquifer.acwadam_class "
            "(values: alluvium, volcanic, crystalline_basement, …)",
            "    soge_class_name, terrain_cluster_id, river_name, canal_name, aquifer_raw_class",
            "",
            "Keyed dict / object variables (use .get('Key', default) with exact keys):",
        ]
    )
    for name, meta in sorted(variable_type_catalog().items()):
        keys = meta.get("dict_keys")
        if not keys:
            continue
        key_preview = ", ".join(keys[:8])
        if len(keys) > 8:
            key_preview += f", … ({len(keys)} total)"
        lines.append(f"    {name} ({meta.get('type', '?')}): keys = {key_preview}")
    lines.append("")
    lines.append(
        "  Review focus: semantic alignment (prose ↔ expressions ↔ policy). "
        "Deterministic preflight already checks syntax, schema, and registry names — "
        "do not re-flag type/indexing issues covered above unless prose contradicts the expression."
    )
    return "\n".join(lines)


def _resolve_data_dictionary_ref(ref: str, dd: dict) -> Any:
    cur: Any = dd
    for part in str(ref or "").split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


@lru_cache
def variable_type_catalog() -> dict[str, dict[str, Any]]:
    """Per-variable type metadata from data_dictionary_v2 for review UI and Claude prompts."""
    dd = load_data_dictionary()
    variables = dd.get("variables") or {}
    catalog: dict[str, dict[str, Any]] = {}
    for name, meta in variables.items():
        if not isinstance(meta, dict):
            continue
        entry: dict[str, Any] = {
            "type": meta.get("type"),
            "unit": meta.get("unit"),
            "description": meta.get("description"),
            "availability": meta.get("availability"),
        }
        desc = str(meta.get("description") or "").lower()
        unit = str(meta.get("unit") or "").lower()
        var_type = str(meta.get("type") or "").lower()
        if "object keyed" in desc or "keyed by" in desc:
            entry["shape"] = "dict"
        elif any(token in unit for token in ("percent per", "hectares per", "km per", "count per", "list per")):
            entry["shape"] = "dict"
        elif var_type == "time_series":
            if "sub-keyed by season" in desc or "{kharif" in desc:
                entry["shape"] = "time_series_seasonal"
            else:
                entry["shape"] = "time_series_yearly"
        elif "categorical" in unit and name in CATEGORICAL_SCALAR_VARIABLES:
            entry["shape"] = "scalar_categorical"
        ref = meta.get("allowed_values_ref")
        if ref:
            resolved = _resolve_data_dictionary_ref(str(ref), dd)
            if isinstance(resolved, list):
                if entry.get("shape") == "dict":
                    entry["dict_keys"] = resolved
                elif entry.get("shape") == "scalar_categorical" or "categorical" in unit:
                    entry["allowed_values"] = resolved
                    entry["shape"] = "scalar_categorical"
                else:
                    entry["dict_keys"] = resolved
                    entry["shape"] = entry.get("shape") or "dict"
            elif isinstance(resolved, dict):
                entry["allowed_values"] = resolved
        catalog[str(name)] = entry
    return catalog


def audit_dict_access_keys(expression: str) -> list[dict[str, str]]:
    """Return dict .get('key') usages where key is missing or wrong case vs catalog."""
    if not expression:
        return []
    catalog = variable_type_catalog()
    issues: list[dict[str, str]] = []
    for match in re.finditer(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.get\s*\(\s*['\"]([^'\"]+)['\"]",
        expression,
    ):
        var_name = match.group(1)
        key = match.group(2)
        meta = catalog.get(var_name) or {}
        dict_keys = meta.get("dict_keys")
        if not dict_keys:
            continue
        allowed = [str(k) for k in dict_keys]
        if key in allowed:
            continue
        case_map = {k.lower(): k for k in allowed}
        canonical = case_map.get(key.lower())
        if canonical:
            issues.append(
                {
                    "variable": var_name,
                    "key_used": key,
                    "issue": "wrong_case",
                    "canonical_key": canonical,
                    "message": f"Use .get('{canonical}', …) — keys are Title Case per data dictionary, not '{key}'.",
                }
            )
        else:
            issues.append(
                {
                    "variable": var_name,
                    "key_used": key,
                    "issue": "unknown_key",
                    "message": f"Key '{key}' is not in {var_name} keys ({', '.join(allowed[:5])}…).",
                }
            )
    return issues


def normalize_expression(expression: str, *, card_thresholds: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """Apply deterministic expression rewrites; return patched expression and change notes."""
    notes: list[str] = []
    original = expression
    expr = expression.replace(" AND ", " and ").replace(" OR ", " or ")
    if expr != expression:
        notes.append("normalized boolean operators")
    expr, alias_notes = apply_legacy_aliases_to_expression(expr)
    notes.extend(alias_notes)
    if "drought_causality_json" in expr:
        expr = re.sub(r"\bdrought_causality_json\b", "drought_causality", expr)
        if "renamed drought_causality_json to drought_causality" not in notes:
            notes.append("renamed drought_causality_json to drought_causality")
    drought_before = expr
    expr = rewrite_drought_causality_expression(expr)
    if expr != drought_before:
        notes.append("rewrote drought_causality flat .get() keys to derived latest-score scalars")
    before_tautology = expr
    expr = rewrite_self_comparison_tautologies(expr, card_thresholds)
    if expr != before_tautology:
        notes.append("rewrote self-comparison tautologies to scalar thresholds")
    expr = rewrite_static_cd_trend_expression(expr)
    if expr != original and not notes:
        notes.append("rewrote static cd_* indexing/threshold pattern")
    return expr, notes
