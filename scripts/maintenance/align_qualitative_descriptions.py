#!/usr/bin/env python3
"""Apply template-based qualitative_description alignments (prose only)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap()

RAW = ROOT / "data" / "evidence_cards" / "raw"
EDITS_PATH = ROOT / "metadata" / "claude_review_user_card_edits.json"
DROUGHT_GLOB = "agriculture__water_scarcity__drought__*.json"
GROUNDWATER_GLOB = "agriculture__water_scarcity__groundwater_stress__*.json"
IRRIGATION_GLOB = "agriculture__water_scarcity__irrigation_challenges__*.json"

IRRIGATION_SIG01_EXPR = "trend_swb_total_area_ha < 1 and swb_count <= 15"
IRRIGATION_SIG01_OPENING = (
    "Surface water body total area trend is below 1 ha/year and "
    "15 or fewer distinct SWBs are present in the MWS"
)

IRRIGATION_SIG03_EXPR = "nrega_swc_count <= 20"
IRRIGATION_SIG03_OPENING_BASE = (
    "20 or fewer cumulative soil and water conservation or irrigation works "
    "recorded under MGNREGA"
)
NREGA_SWC_OLD_OPENING_RE = re.compile(
    r"Fewer than \d+ cumulative soil and water conservation or irrigation works "
    r"(?:completed )?(?:recorded )?under MGNREGA"
    r"(?P<geo>(?: for the (?:MWS|micro-watershed)| in the MWS))?"
    r",?\s*"
    r"(?P<tail>(?:indicating|indicates?|indicate)\s+.+)$",
    re.IGNORECASE | re.DOTALL,
)

RAINFED_GLOB = "agriculture__water_scarcity__rainfed_risk__*.json"
RAINFED_NREGA_IRRIGATION_EXPRS = frozenset(
    {
        "canal_name is None and nrega_irrigation_count <= 35",
        "nrega_irrigation_count <= 35 and canal_name is None",
        "nrega_irrigation_count <= 35",
    }
)
NREGA_IRRIGATION_COUNT_OLD_RE = re.compile(
    r"fewer than \d+ MGNREGA irrigation works",
    re.IGNORECASE,
)
NREGA_IRRIGATION_COUNT_NEW = "35 or fewer MGNREGA irrigation works"

ENCROACHMENT_GLOB = "ntfp_forest_biodiversity__ntfp_decline__encroachment__*.json"
# Expression threshold -> prose ha (expr > 29 means "more than 30 ha" in qual text).
ENCROACHMENT_SIG01_FOREST_FARM_PROSE_HA: dict[str, int] = {
    "cd_forest_to_farm_ha > 29": 30,
    "cd_forest_to_farm_ha > 20": 20,
}
WRONG_FOREST_FARM_50_HA_RE = re.compile(
    r"\b(?:more than |over )?50\s*ha\b",
    re.IGNORECASE,
)
ANY_MORE_THAN_HA_RE = re.compile(
    r"\bmore than \d+\s*ha\b",
    re.IGNORECASE,
)
VAGUE_FOREST_FARM_INCREASE_RE = re.compile(
    r"^(?:Cumulative )?[Ff]orest-to-farm conversion(?: area)? has increased"
    r"( over the (?:available |observation )?(?:period|record))?,?\s*",
    re.IGNORECASE,
)

FOREST_DEGRADATION_GLOB = (
    "ntfp_forest_biodiversity__ntfp_decline__forest_degradation__*.json"
)
DEFORESTATION_TOTAL_HA_THRESHOLD_RE = re.compile(
    r"(?:^|[(&\s])cd_total_deforestation_ha\s*>\s*(\d+)"
)
WRONG_DEFORESTATION_HA_NUM_RE = re.compile(
    r"\b(?P<lead>(?:[Mm]ore than |[Ee]xceeds |"
    r"[Cc]umulative deforestation exceeds |"
    r"[Cc]umulative deforested area exceeds |"
    r"[Tt]otal deforested area(?: in the micro-watershed)? exceeds ))"
    r"(?P<num>50|100)\s*(?P<unit>ha|hectares)\b",
    re.IGNORECASE,
)

MULTI_SECTOR_GLOB = (
    "socio_economic__economic_hardship__multi_sector_vulnerability__*.json"
)
MULTI_SECTOR_SIG01_LITERACY_OPENINGS: dict[str, str] = {
    "(village_sc_percent + village_st_percent) > 40 and village_literacy_rate < 55": (
        "Combined SC and ST population exceeds 40% of village population AND "
        "literacy rate is below 55%"
    ),
    "(village_sc_percent + village_st_percent) > 40 or village_literacy_rate < 55": (
        "Combined SC and ST population exceeds 40% of village population OR "
        "literacy rate is below 55%"
    ),
    "((village_st_percent > 40) or (village_sc_percent + village_st_percent > 50)) and village_literacy_rate < 60": (
        "Village has ST population above 40%, or combined SC+ST share exceeds 50%, AND "
        "literacy rate is below 60%"
    ),
    "(village_st_percent > 50 or (village_st_percent + village_sc_percent) > 60) and village_literacy_rate < 60": (
        "Villages where ST population exceeds 50%, or combined SC+ST exceeds 60%, AND "
        "literacy rate is below 60%"
    ),
    "(village_sc_percent + village_st_percent) > 35 and village_literacy_rate < 65": (
        "Combined SC and ST population exceeds 35% of village population AND "
        "literacy rate is below 65%"
    ),
    "(village_st_percent + village_sc_percent) > 40 and village_literacy_rate < 60": (
        "Combined SC and ST population exceeds 40% of village population AND "
        "literacy rate is below 60%"
    ),
}
MULTI_SECTOR_SIG03_BANK_NREGA_OPENINGS: dict[str, str] = {
    "dist_bank_km > 10 or nrega_swc_count < 5": (
        "Nearest bank branch is more than 10 km away, or fewer than 5 cumulative "
        "MGNREGA soil and water conservation works have been recorded in the "
        "micro-watershed"
    ),
    "dist_bank_km > 5 or nrega_swc_count < 5": (
        "Distance to nearest bank branch exceeds 5 km, or fewer than 5 cumulative "
        "MGNREGA soil and water conservation works have been recorded in the "
        "micro-watershed"
    ),
}

MEAN_DELTA_G_EXPR = "mean_annual_delta_g_mm < 0"
MEAN_DELTA_G_OPENING_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"The linear trend in annual groundwater balance \(P - ET - Runoff\) "
            r"is declining at more than 2 mm/year and the multi-year mean is negative,\s*",
            re.IGNORECASE,
        ),
        "The multi-year mean annual groundwater balance (P - ET - Runoff) is negative, ",
    ),
    (
        re.compile(
            r"The linear trend in annual groundwater recharge \(P - ET - Runoff\) "
            r"is negative and the multi-year mean is also negative,\s*",
            re.IGNORECASE,
        ),
        "The multi-year mean annual groundwater recharge (P - ET - Runoff) is negative, ",
    ),
    (
        re.compile(
            r"The linear trend in annual groundwater balance \(P - ET - Runoff\) "
            r"is negative and the multi-year mean is also negative,\s*",
            re.IGNORECASE,
        ),
        "The multi-year mean annual groundwater balance (P - ET - Runoff) is negative, ",
    ),
    (
        re.compile(
            r"Both the linear trend slope of annual groundwater balance \(P - ET - Runoff\) "
            r"is negative and the multi-year mean is negative,\s*",
            re.IGNORECASE,
        ),
        "The multi-year mean annual groundwater balance (P - ET - Runoff) is negative, ",
    ),
    (
        re.compile(
            r"Both the linear trend and the multi-year mean of annual groundwater balance "
            r"\(P - ET - Runoff\) are negative,\s*",
            re.IGNORECASE,
        ),
        "The multi-year mean annual groundwater balance (P - ET - Runoff) is negative, ",
    ),
    (
        re.compile(
            r"Both the linear trend and the multi-year mean of annual groundwater recharge "
            r"\(P - ET - Runoff\) are negative,\s*",
            re.IGNORECASE,
        ),
        "The multi-year mean annual groundwater recharge (P - ET - Runoff) is negative, ",
    ),
    (
        re.compile(
            r"Mean annual groundwater balance \(P - ET - Runoff\) is negative across "
            r"the multi-year record and the trend is declining,\s*",
            re.IGNORECASE,
        ),
        "Mean annual groundwater balance (P - ET - Runoff) is negative across the multi-year record, ",
    ),
    (
        re.compile(
            r"Declining trend in annual groundwater recharge balance \(P - ET - Runoff\) "
            r"with a low mean recharge value,\s*",
            re.IGNORECASE,
        ),
        "The multi-year mean annual groundwater balance (P - ET - Runoff) is negative, ",
    ),
]

RETURN_PERIOD_EXPR = (
    "drought_severe_return_period <= 4 or drought_moderate_return_period <= 4"
)
RETURN_PERIOD_OPENING = (
    "Severe drought return period is 4 years or less, "
    "or moderate drought return period is 4 years or less"
)

MEAN_DRY_SPELL_EXPR = "mean(dry_spell_weeks) >= 3"
MEAN_DRY_SPELL_OPENING_PREFIX = "Mean dry-spell weeks across the record is 3 or more"
DEFAULT_DRY_SPELL_PAREN = "(4-week moving window with less than 50% historical rainfall)"

TAIL_PATTERNS = [
    re.compile(r",\s*((?:indicates?|indicate)\s+.+)$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\s+season\s+((?:indicates?|indicate)\s+.+)$", re.IGNORECASE | re.DOTALL),
]
DRY_SPELL_PAREN_RE = re.compile(r"\((4-week moving window with [^)]+)\)", re.IGNORECASE)


def extract_tail_clause(old: str, card_id: str) -> str | None:
    for pattern in TAIL_PATTERNS:
        match = pattern.search(old)
        if match:
            return match.group(1).strip()
    return None


def align_drought_sig_01_return_period(card: dict) -> list[tuple[str, str, str | None, str]]:
    """Return list of (signal_id, expression, new_qual, status)."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        if sig.get("signal_id") != "sig_01":
            continue
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        if expr != RETURN_PERIOD_EXPR:
            continue
        signal_id = str(sig.get("signal_id"))
        old = str(cond.get("qualitative_description") or "").strip()
        if not old:
            out.append(
                (
                    signal_id,
                    expr,
                    f"{RETURN_PERIOD_OPENING}, indicating recurrent drought episodes "
                    "sufficient to cause significant crop water stress and yield loss.",
                    "filled_empty",
                )
            )
            continue
        if old.startswith(RETURN_PERIOD_OPENING):
            out.append((signal_id, expr, old, "already_aligned"))
            continue
        tail_clause = extract_tail_clause(old, card_id)
        if not tail_clause:
            out.append((signal_id, expr, None, f"no_tail_match:{card_id}"))
            continue
        out.append((signal_id, expr, f"{RETURN_PERIOD_OPENING}, {tail_clause}", "updated"))
    return out


def align_drought_mean_dry_spell(card: dict) -> list[tuple[str, str, str | None, str]]:
    """Return list of (signal_id, expression, new_qual, status) for mean dry spell."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        if expr != MEAN_DRY_SPELL_EXPR:
            continue
        signal_id = str(sig.get("signal_id") or "?")
        old = str(cond.get("qualitative_description") or "").strip()
        paren_match = DRY_SPELL_PAREN_RE.search(old) if old else None
        paren = (
            f"({paren_match.group(1)})"
            if paren_match
            else DEFAULT_DRY_SPELL_PAREN
        )
        opening = f"{MEAN_DRY_SPELL_OPENING_PREFIX} {paren}"
        if not old:
            out.append(
                (
                    signal_id,
                    expr,
                    f"{opening}, indicating prolonged moisture deficit disrupting "
                    "critical crop growth stages.",
                    "filled_empty",
                )
            )
            continue
        if old.startswith(MEAN_DRY_SPELL_OPENING_PREFIX):
            out.append((signal_id, expr, old, "already_aligned"))
            continue
        tail_clause = extract_tail_clause(old, card_id)
        if not tail_clause:
            out.append((signal_id, expr, None, f"no_tail_match:{card_id}:{signal_id}"))
            continue
        out.append((signal_id, expr, f"{opening}, {tail_clause}", "updated"))
    return out


def extract_irrigation_sig01_tail(old: str) -> str | None:
    if re.search(r"Very few and small surface water bodies", old, re.IGNORECASE):
        match = re.search(r"indicate\s+(.+)$", old, re.IGNORECASE | re.DOTALL)
        if match:
            return f"indicating {match.group(1).strip()}"
    tail = extract_tail_clause(old, "")
    if tail:
        return tail
    match = re.search(
        r"(?:,\s*)?((?:indicating?|indicate)\s+.+)$",
        old,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else None


def align_irrigation_sig_01_swb_trend(card: dict) -> list[tuple[str, str, str | None, str]]:
    """Align prose for trend_swb_total_area_ha < 1 and swb_count <= 15."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        if expr != IRRIGATION_SIG01_EXPR:
            continue
        signal_id = str(sig.get("signal_id") or "?")
        old = str(cond.get("qualitative_description") or "").strip()
        if not old:
            out.append((signal_id, expr, None, f"empty_qual:{card_id}:{signal_id}"))
            continue
        if old.startswith(IRRIGATION_SIG01_OPENING):
            out.append((signal_id, expr, old, "already_aligned"))
            continue
        tail_clause = extract_irrigation_sig01_tail(old)
        if not tail_clause:
            out.append((signal_id, expr, None, f"no_tail_match:{card_id}:{signal_id}"))
            continue
        out.append(
            (signal_id, expr, f"{IRRIGATION_SIG01_OPENING}, {tail_clause}", "updated")
        )
    return out


def align_irrigation_sig_03_nrega_swc(card: dict) -> list[tuple[str, str, str | None, str]]:
    """Align prose for nrega_swc_count <= 20."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        if expr != IRRIGATION_SIG03_EXPR:
            continue
        signal_id = str(sig.get("signal_id") or "?")
        old = str(cond.get("qualitative_description") or "").strip()
        if not old:
            out.append((signal_id, expr, None, f"empty_qual:{card_id}:{signal_id}"))
            continue
        if old.startswith(IRRIGATION_SIG03_OPENING_BASE):
            out.append((signal_id, expr, old, "already_aligned"))
            continue
        match = NREGA_SWC_OLD_OPENING_RE.search(old)
        if not match:
            out.append((signal_id, expr, None, f"no_opening_match:{card_id}:{signal_id}"))
            continue
        geo = match.group("geo") or ""
        tail = match.group("tail").strip()
        if tail.lower().startswith("indicates "):
            tail = f"indicating {tail[10:].lstrip()}"
        out.append(
            (
                signal_id,
                expr,
                f"{IRRIGATION_SIG03_OPENING_BASE}{geo}, {tail}",
                "updated",
            )
        )
    return out


def align_rainfed_nrega_irrigation_count(card: dict) -> list[tuple[str, str, str | None, str]]:
    """Align prose for nrega_irrigation_count <= 35 (with or without canal_name is None)."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        if expr not in RAINFED_NREGA_IRRIGATION_EXPRS:
            continue
        signal_id = str(sig.get("signal_id") or "?")
        old = str(cond.get("qualitative_description") or "").strip()
        if not old:
            out.append((signal_id, expr, None, f"empty_qual:{card_id}:{signal_id}"))
            continue
        if not NREGA_IRRIGATION_COUNT_OLD_RE.search(old):
            if NREGA_IRRIGATION_COUNT_NEW.lower() in old.lower():
                out.append((signal_id, expr, old, "already_aligned"))
            else:
                out.append(
                    (signal_id, expr, None, f"no_count_phrase_match:{card_id}:{signal_id}")
                )
            continue
        new_qual = NREGA_IRRIGATION_COUNT_OLD_RE.sub(
            NREGA_IRRIGATION_COUNT_NEW, old, count=1
        )
        out.append((signal_id, expr, new_qual, "updated"))
    return out


def _ha_phrase(prose_ha: int, *, capitalize: bool = False) -> str:
    if capitalize:
        return f"More than {prose_ha} ha"
    return f"more than {prose_ha} ha"


def align_encroachment_forest_farm_ha_prose(
    old: str, prose_ha: int
) -> tuple[str | None, str]:
    if re.search(rf"\bmore than {prose_ha}\s*ha\b", old, re.IGNORECASE):
        return old, "already_aligned"

    def replace_ha_match(match: re.Match[str]) -> str:
        return _ha_phrase(prose_ha, capitalize=match.group(0)[0].isupper())

    if WRONG_FOREST_FARM_50_HA_RE.search(old):
        return WRONG_FOREST_FARM_50_HA_RE.sub(replace_ha_match, old, count=1), "updated"

    if ANY_MORE_THAN_HA_RE.search(old):
        return ANY_MORE_THAN_HA_RE.sub(replace_ha_match, old, count=1), "updated"

    if VAGUE_FOREST_FARM_INCREASE_RE.search(old):
        period_match = re.search(
            r" over the (?:available |observation )?(?:period|record)",
            old,
            re.IGNORECASE,
        )
        period = period_match.group(0) if period_match else " over the available record"
        tail_clause = extract_tail_clause(old, "")
        if not tail_clause:
            tail_match = re.search(
                r",\s*((?:indicating|indicates?|indicate)\s+.+)$",
                old,
                re.IGNORECASE | re.DOTALL,
            )
            tail_clause = tail_match.group(1).strip() if tail_match else None
        if not tail_clause:
            return None, "no_tail_match"
        return (
            f"Cumulative forest-to-farm conversion has increased by "
            f"{_ha_phrase(prose_ha)}{period}, {tail_clause}",
            "updated",
        )

    return None, "unhandled_wording"


def align_encroachment_sig01_forest_farm_ha(
    card: dict,
) -> list[tuple[str, str, str | None, str]]:
    """Align encroachment sig_01 forest-to-farm ha prose to expression thresholds."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        if sig.get("signal_id") != "sig_01":
            continue
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        prose_ha = ENCROACHMENT_SIG01_FOREST_FARM_PROSE_HA.get(expr)
        if prose_ha is None:
            continue
        signal_id = str(sig.get("signal_id") or "?")
        old = str(cond.get("qualitative_description") or "").strip()
        if not old:
            out.append((signal_id, expr, None, f"empty_qual:{card_id}:{signal_id}"))
            continue
        new_qual, status = align_encroachment_forest_farm_ha_prose(old, prose_ha)
        if new_qual is None:
            out.append((signal_id, expr, None, f"{status}:{card_id}:{signal_id}"))
        else:
            out.append((signal_id, expr, new_qual, status))
    return out


def prose_ha_from_expr_threshold(threshold: int) -> int:
    """Map expression literal to human-readable ha (expr > 29 => prose 30)."""
    return 30 if threshold == 29 else threshold


def align_forest_degradation_deforestation_ha_prose(
    old: str, prose_ha: int
) -> tuple[str | None, str]:
    if re.search(
        rf"(?:more than|exceeds)\s+{prose_ha}\s*(?:ha|hectares)",
        old,
        re.IGNORECASE,
    ):
        return old, "already_aligned"
    if not WRONG_DEFORESTATION_HA_NUM_RE.search(old):
        return None, "no_wrong_ha_match"

    def repl(match: re.Match[str]) -> str:
        wrong = int(match.group("num"))
        if wrong <= prose_ha:
            return match.group(0)
        return f"{match.group('lead')}{prose_ha} {match.group('unit')}"

    new = WRONG_DEFORESTATION_HA_NUM_RE.sub(repl, old)
    if new == old:
        return None, "unhandled_wording"
    return new, "updated"


def align_forest_degradation_deforestation_ha(
    card: dict,
) -> list[tuple[str, str, str | None, str]]:
    """Align sig_02/sig_03 deforestation ha prose to cd_total_deforestation_ha thresholds."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        signal_id = str(sig.get("signal_id") or "?")
        if signal_id not in {"sig_02", "sig_03"}:
            continue
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        threshold_match = DEFORESTATION_TOTAL_HA_THRESHOLD_RE.search(expr)
        if not threshold_match:
            continue
        threshold = int(threshold_match.group(1))
        if threshold == 0:
            continue
        prose_ha = prose_ha_from_expr_threshold(threshold)
        old = str(cond.get("qualitative_description") or "").strip()
        if not old:
            out.append((signal_id, expr, None, f"empty_qual:{card_id}:{signal_id}"))
            continue
        new_qual, status = align_forest_degradation_deforestation_ha_prose(old, prose_ha)
        if new_qual is None:
            out.append((signal_id, expr, None, f"{status}:{card_id}:{signal_id}"))
        else:
            out.append((signal_id, expr, new_qual, status))
    return out


def align_multi_sector_sig01_literacy(card: dict) -> list[tuple[str, str, str | None, str]]:
    """Add literacy clause to sig_01 prose where expression includes village_literacy_rate."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        if sig.get("signal_id") != "sig_01":
            continue
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        opening = MULTI_SECTOR_SIG01_LITERACY_OPENINGS.get(expr)
        if not opening:
            continue
        signal_id = str(sig.get("signal_id") or "?")
        old = str(cond.get("qualitative_description") or "").strip()
        if not old:
            out.append((signal_id, expr, None, f"empty_qual:{card_id}:{signal_id}"))
            continue
        if re.search(r"literacy rate is below", old, re.IGNORECASE):
            out.append((signal_id, expr, old, "already_aligned"))
            continue
        tail_clause = None
        for pattern in (
            re.compile(
                r",\s*((?:indicating|indicates?|indicate)\s+.+)$",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(r"\s+(face\s+.+)$", re.IGNORECASE | re.DOTALL),
        ):
            match = pattern.search(old)
            if match:
                tail_clause = match.group(1).strip()
                break
        if not tail_clause:
            out.append((signal_id, expr, None, f"no_tail_match:{card_id}:{signal_id}"))
            continue
        out.append((signal_id, expr, f"{opening}, {tail_clause}", "updated"))
    return out


def align_multi_sector_sig03_bank_or_nrega(
    card: dict,
) -> list[tuple[str, str, str | None, str]]:
    """Align sig_03 prose for dist_bank_km OR nrega_swc_count compound expressions."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        if sig.get("signal_id") != "sig_03":
            continue
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        opening = MULTI_SECTOR_SIG03_BANK_NREGA_OPENINGS.get(expr)
        if not opening:
            continue
        signal_id = str(sig.get("signal_id") or "?")
        old = str(cond.get("qualitative_description") or "").strip()
        if not old:
            out.append((signal_id, expr, None, f"empty_qual:{card_id}:{signal_id}"))
            continue
        if re.search(r"mgnrega|nrega|soil and water conservation", old, re.IGNORECASE):
            out.append((signal_id, expr, old, "already_aligned"))
            continue
        tail_clause = None
        for pattern in (
            re.compile(
                r",\s*((?:forcing|indicating|indicates?|indicate)\s+.+)$",
                re.IGNORECASE | re.DOTALL,
            ),
        ):
            match = pattern.search(old)
            if match:
                tail_clause = match.group(1).strip()
                break
        if not tail_clause:
            out.append((signal_id, expr, None, f"no_tail_match:{card_id}:{signal_id}"))
            continue
        out.append((signal_id, expr, f"{opening}, {tail_clause}", "updated"))
    return out


def strip_trend_from_mean_delta_g_prose(old: str) -> tuple[str | None, str]:
    text = old.strip()
    if not text:
        return None, "empty_qual"
    for pattern, replacement in MEAN_DELTA_G_OPENING_REPLACEMENTS:
        updated = pattern.sub(replacement, text, count=1)
        if updated != text:
            return updated.strip(), "updated"
    if re.search(r"\blinear trend\b", text, re.IGNORECASE):
        return None, "unhandled_trend_wording"
    if re.search(r"\bDeclining trend in annual groundwater\b", text, re.IGNORECASE):
        return None, "unhandled_trend_wording"
    if re.search(r"\band the trend is declining\b", text, re.IGNORECASE):
        return None, "unhandled_trend_wording"
    return text, "already_aligned"


def align_groundwater_mean_delta_g_only(card: dict) -> list[tuple[str, str, str | None, str]]:
    """Align prose for signals using mean_annual_delta_g_mm < 0 without trend in expression."""
    card_id = card.get("card_id", "?")
    out: list[tuple[str, str, str | None, str]] = []
    for sig in card.get("diagnostic_signals") or []:
        cond = sig.get("condition") or {}
        expr = (cond.get("expression") or sig.get("expression") or "").strip()
        if expr != MEAN_DELTA_G_EXPR:
            continue
        signal_id = str(sig.get("signal_id") or "?")
        old = str(cond.get("qualitative_description") or "").strip()
        new_qual, status = strip_trend_from_mean_delta_g_prose(old)
        if new_qual is None:
            out.append((signal_id, expr, None, f"{status}:{card_id}:{signal_id}"))
        else:
            out.append((signal_id, expr, new_qual, status))
    return out


CATEGORY_HANDLERS: dict[str, tuple[str, Callable[[dict], list[tuple[str, str, str | None, str]]]]] = {
    "drought_sig_01_return_period": (DROUGHT_GLOB, align_drought_sig_01_return_period),
    "drought_mean_dry_spell": (DROUGHT_GLOB, align_drought_mean_dry_spell),
    "groundwater_mean_delta_g_only": (GROUNDWATER_GLOB, align_groundwater_mean_delta_g_only),
    "irrigation_sig_01_swb_trend": (IRRIGATION_GLOB, align_irrigation_sig_01_swb_trend),
    "irrigation_sig_03_nrega_swc": (IRRIGATION_GLOB, align_irrigation_sig_03_nrega_swc),
    "rainfed_nrega_irrigation_count": (RAINFED_GLOB, align_rainfed_nrega_irrigation_count),
    "encroachment_sig01_forest_farm_ha": (
        ENCROACHMENT_GLOB,
        align_encroachment_sig01_forest_farm_ha,
    ),
    "forest_degradation_deforestation_ha": (
        FOREST_DEGRADATION_GLOB,
        align_forest_degradation_deforestation_ha,
    ),
    "multi_sector_sig01_literacy": (
        MULTI_SECTOR_GLOB,
        align_multi_sector_sig01_literacy,
    ),
    "multi_sector_sig03_bank_or_nrega": (
        MULTI_SECTOR_GLOB,
        align_multi_sector_sig03_bank_or_nrega,
    ),
}


def sync_user_edit_patches(updates: list[tuple[str, str, str, str]]) -> list[str]:
    """Mirror qualitative_description into user_card_edits patches. Returns card_ids synced."""
    if not updates or not EDITS_PATH.exists():
        return []
    doc = json.loads(EDITS_PATH.read_text(encoding="utf-8"))
    synced: list[str] = []
    batches = doc.get("batches") if isinstance(doc.get("batches"), dict) else {}
    for card_id, signal_id, expression, new_qual in updates:
        for batch in batches.values():
            if not isinstance(batch, dict):
                continue
            edits = batch.get("edits") or {}
            entry = edits.get(card_id)
            if not isinstance(entry, dict):
                continue
            patch = entry.get("patch")
            if not isinstance(patch, dict):
                continue
            for sig in patch.get("diagnostic_signals") or []:
                if not isinstance(sig, dict) or sig.get("signal_id") != signal_id:
                    continue
                cond = sig.get("condition")
                if not isinstance(cond, dict):
                    continue
                if (cond.get("expression") or "").strip() != expression:
                    continue
                if cond.get("qualitative_description") == new_qual:
                    break
                cond["qualitative_description"] = new_qual
                if card_id not in synced:
                    synced.append(card_id)
                break
    if synced:
        EDITS_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return synced


def apply_category(
    category: str,
    *,
    dry_run: bool = False,
    sync_edits: bool = True,
) -> dict:
    config = CATEGORY_HANDLERS.get(category)
    if config is None:
        raise ValueError(f"Unknown category: {category}")
    glob_pattern, handler = config

    results: dict = {
        "updated": [],
        "patch_synced": [],
        "exceptions": [],
        "skipped": [],
    }
    pending_patch_sync: list[tuple[str, str, str, str]] = []

    for path in sorted(RAW.glob(glob_pattern)):
        card = json.loads(path.read_text(encoding="utf-8"))
        card_id = path.stem
        alignments = handler(card)
        if not alignments:
            results["skipped"].append({"card_id": card_id, "reason": "no_matching_signals"})
            continue

        card_changed = False
        for signal_id, expression, new_qual, status in alignments:
            if new_qual is None:
                results["exceptions"].append({"card_id": card_id, "reason": status})
                continue

            for sig in card.get("diagnostic_signals") or []:
                if str(sig.get("signal_id")) != signal_id:
                    continue
                cond = sig.setdefault("condition", {})
                if (cond.get("expression") or sig.get("expression") or "").strip() != expression:
                    continue
                old = cond.get("qualitative_description", "")
                if status == "already_aligned" and old == new_qual:
                    results["skipped"].append(
                        {
                            "card_id": card_id,
                            "signal_id": signal_id,
                            "reason": status,
                        }
                    )
                else:
                    cond["qualitative_description"] = new_qual
                    results["updated"].append(
                        {
                            "card_id": card_id,
                            "signal_id": signal_id,
                            "status": status,
                            "before": old,
                            "after": new_qual,
                        }
                    )
                    card_changed = True
                pending_patch_sync.append((card_id, signal_id, expression, new_qual))
                break

        if card_changed and not dry_run:
            path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if sync_edits and not dry_run and pending_patch_sync:
        results["patch_synced"] = sync_user_edit_patches(pending_patch_sync)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "category",
        choices=sorted(CATEGORY_HANDLERS),
        help="Alignment category to apply",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-sync-edits", action="store_true")
    args = parser.parse_args()

    report = apply_category(
        args.category,
        dry_run=args.dry_run,
        sync_edits=not args.no_sync_edits,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
