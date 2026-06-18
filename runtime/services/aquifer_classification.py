"""Infer ACWADAM aquifer class from lithology percentages and optional MWS AER."""

from __future__ import annotations

from typing import Any

LITHOLOGY_COLUMNS = [
    "Alluvium",
    "Banded Gneissic Complex",
    "Basalt",
    "Charnockite",
    "Gneiss",
    "Granite",
    "Intrusive",
    "Khondalite",
    "Laterite",
    "Limestone",
    "Quartzite",
    "Sandstone",
    "Schist",
    "Shale",
    "None",
]

ACWADAM_CLASSES = (
    "alluvium",
    "himalayan_and_sub_himalayan",
    "volcanic",
    "sedimentary_soft_rock",
    "sedimentary_hard_rock",
    "crystalline_basement",
)

CARD_AQUIFER_TAGS = ("hard_rock", "alluvium", "semi-consolidated", "coastal")

LITHOLOGY_TO_ACWADAM: dict[str, str] = {
    "Alluvium": "alluvium",
    "Basalt": "volcanic",
    "Sandstone": "sedimentary_soft_rock",
    "Shale": "sedimentary_soft_rock",
    "Limestone": "sedimentary_soft_rock",
    "Quartzite": "sedimentary_hard_rock",
    "Granite": "crystalline_basement",
    "Gneiss": "crystalline_basement",
    "Banded Gneissic Complex": "crystalline_basement",
    "Charnockite": "crystalline_basement",
    "Khondalite": "crystalline_basement",
    "Schist": "crystalline_basement",
    "Intrusive": "crystalline_basement",
}

HIMALAYAN_AERS = frozenset({"AER-1", "AER-14", "AER-16"})
HIMALAYAN_OVERRIDE_LITHOLOGIES = frozenset({"Sandstone", "Shale", "Schist"})

DECCAN_VOLCANIC_AERS = frozenset({"AER-5", "AER-6"})
PENINSULAR_AERS = frozenset({"AER-3", "AER-7", "AER-8", "AER-11", "AER-12"})
COASTAL_ALLUVIAL_AERS = frozenset({"AER-18", "AER-19", "AER-20"})

AER_FALLBACK_ACWADAM: dict[str, str] = {
    "AER-1": "himalayan_and_sub_himalayan",
    "AER-14": "himalayan_and_sub_himalayan",
    "AER-16": "himalayan_and_sub_himalayan",
    "AER-5": "volcanic",
    "AER-6": "volcanic",
    "AER-2": "alluvium",
    "AER-4": "alluvium",
    "AER-9": "alluvium",
    "AER-13": "alluvium",
    "AER-15": "alluvium",
    "AER-18": "alluvium",
    "AER-19": "alluvium",
    "AER-20": "alluvium",
    "AER-10": "sedimentary_soft_rock",
    "AER-17": "sedimentary_soft_rock",
    "AER-3": "crystalline_basement",
    "AER-7": "crystalline_basement",
    "AER-8": "crystalline_basement",
    "AER-11": "crystalline_basement",
    "AER-12": "crystalline_basement",
}

ACWADAM_TO_CARD_AQUIFER: dict[str, str] = {
    "alluvium": "alluvium",
    "sedimentary_soft_rock": "semi-consolidated",
    "volcanic": "hard_rock",
    "crystalline_basement": "hard_rock",
    "sedimentary_hard_rock": "hard_rock",
    "himalayan_and_sub_himalayan": "hard_rock",
}

TIE_THRESHOLD_PP = 5.0


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dominant_lithology(lithology_percent: dict[str, Any] | None) -> tuple[str | None, float | None]:
    """Return dominant lithology name and percent, excluding the None bucket."""
    if not lithology_percent:
        return None, None
    ranked: list[tuple[str, float]] = []
    for name, raw in lithology_percent.items():
        if name == "None":
            continue
        pct = _as_float(raw)
        if pct is not None and pct > 0:
            ranked.append((name, pct))
    if not ranked:
        return None, None
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked[0]


def _is_ambiguous_lithology(lithology_percent: dict[str, Any] | None) -> bool:
    dominant, top_pct = dominant_lithology(lithology_percent)
    if dominant is None or top_pct is None:
        return True
    if dominant == "Laterite":
        return True
    ranked = []
    for name, raw in (lithology_percent or {}).items():
        if name == "None":
            continue
        pct = _as_float(raw)
        if pct is not None and pct > 0:
            ranked.append((name, pct))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    if len(ranked) < 2:
        return False
    second_pct = ranked[1][1]
    return (top_pct - second_pct) <= TIE_THRESHOLD_PP


def _laterite_acwadam(aer_code: str | None) -> str:
    if aer_code in DECCAN_VOLCANIC_AERS:
        return "volcanic"
    if aer_code in HIMALAYAN_AERS:
        return "himalayan_and_sub_himalayan"
    if aer_code in COASTAL_ALLUVIAL_AERS:
        return "alluvium"
    if aer_code in PENINSULAR_AERS:
        return "crystalline_basement"
    return "crystalline_basement"


def _aer_fallback(aer_code: str | None) -> str | None:
    if not aer_code:
        return None
    return AER_FALLBACK_ACWADAM.get(aer_code)


def _apply_himalayan_override(
    acwadam_class: str,
    dominant: str | None,
    aer_code: str | None,
) -> str:
    if (
        aer_code in HIMALAYAN_AERS
        and dominant in HIMALAYAN_OVERRIDE_LITHOLOGIES
    ):
        return "himalayan_and_sub_himalayan"
    if aer_code in HIMALAYAN_AERS and dominant in {
        "Granite",
        "Gneiss",
        "Banded Gneissic Complex",
        "Charnockite",
        "Khondalite",
        "Intrusive",
    }:
        return "himalayan_and_sub_himalayan"
    return acwadam_class


def infer_acwadam_class(
    lithology_percent: dict[str, Any] | None,
    aer_code: str | None = None,
) -> dict[str, Any]:
    """
    Infer ACWADAM class from dominant aquifer lithology, with AER disambiguation.

    Returns dict with acwadam_class, dominant_lithology, acwadam_source.
    """
    dominant, _ = dominant_lithology(lithology_percent)
    ambiguous = _is_ambiguous_lithology(lithology_percent)

    if dominant is None:
        fallback = _aer_fallback(aer_code) or "crystalline_basement"
        return {
            "acwadam_class": fallback,
            "dominant_lithology": None,
            "acwadam_source": "aer_fallback" if aer_code else "default",
        }

    if dominant == "Laterite":
        acwadam = _laterite_acwadam(aer_code)
        return {
            "acwadam_class": acwadam,
            "dominant_lithology": dominant,
            "acwadam_source": "lithology+aer",
        }

    if ambiguous and aer_code:
        if aer_code in HIMALAYAN_AERS and dominant in HIMALAYAN_OVERRIDE_LITHOLOGIES:
            return {
                "acwadam_class": "himalayan_and_sub_himalayan",
                "dominant_lithology": dominant,
                "acwadam_source": "lithology+aer",
            }
        fallback = _aer_fallback(aer_code)
        if fallback:
            return {
                "acwadam_class": fallback,
                "dominant_lithology": dominant,
                "acwadam_source": "lithology+aer",
            }

    acwadam = LITHOLOGY_TO_ACWADAM.get(dominant, "crystalline_basement")
    acwadam = _apply_himalayan_override(acwadam, dominant, aer_code)
    return {
        "acwadam_class": acwadam,
        "dominant_lithology": dominant,
        "acwadam_source": "lithology+aer" if aer_code else "lithology",
    }


def card_aquifer_tags(acwadam_class: str | None, aer_code: str | None = None) -> list[str]:
    """Map ACWADAM class (+ optional AER) to evidence-card aquifer_tags filter values."""
    acwadam = acwadam_class or ""
    base = ACWADAM_TO_CARD_AQUIFER.get(acwadam, "hard_rock")
    if aer_code == "AER-20":
        return ["coastal"]
    if aer_code == "AER-18" and acwadam == "alluvium":
        return ["coastal", "alluvium"]
    return [base]


def card_aquifer_tags_for_mws(mws_doc: dict) -> list[str]:
    aquifer = mws_doc.get("aquifer") or {}
    return card_aquifer_tags(
        aquifer.get("acwadam_class"),
        mws_doc.get("nbss_lup_aer_code"),
    )


def build_aquifer_payload(
    raw_class: str,
    lithology_percent: dict[str, Any],
    aer_code: str | None = None,
) -> dict[str, Any]:
    """Build the aquifer sub-document stored on mws_data."""
    inferred = infer_acwadam_class(lithology_percent, aer_code)
    return {
        "raw_class": raw_class,
        "lithology_percent": lithology_percent,
        "dominant_lithology": inferred["dominant_lithology"],
        "acwadam_class": inferred["acwadam_class"],
        "acwadam_source": inferred["acwadam_source"],
    }
