"""On-the-fly derived statistics from MWS time series (not stored in Mongo)."""

from __future__ import annotations

from typing import Any

# India Drought Manual indicator trigger score on the stored 0–100 causality scale.
IDM_INDICATOR_TRIGGER_SCORE = 26.0

DROUGHT_DERIVED_VARIABLE_NAMES = frozenset(
    {
        "drought_mild_spi_score_latest",
        "drought_mild_mai_score_latest",
        "drought_mild_vci_score_latest",
        "drought_severe_moderate_spi_score_latest",
        "drought_severe_moderate_mai_score_latest",
        "drought_severe_moderate_vci_score_latest",
        "drought_severe_moderate_path_score_latest",
    }
)

# Computed by assembler / signal_evaluator from MWS time series (also in data_dictionary_v2).
ASSEMBLER_DERIVED_VARIABLE_NAMES = frozenset(
    {
        "mean_annual_precipitation_mm",
        "trend_annual_precipitation_mm",
        "mean_kharif_precipitation",
        "mean_rabi_precipitation",
        "mean_zaid_precipitation",
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
        "tree_cover_percent_mws",
    }
)


def _sorted_numeric_series(series: dict | None) -> list[tuple[int, float]]:
    if not series:
        return []
    out: list[tuple[int, float]] = []
    for key, value in series.items():
        if value is None:
            continue
        try:
            out.append((int(key), float(value)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda pair: pair[0])
    return out


def mean(series: dict | None) -> float | None:
    pairs = _sorted_numeric_series(series)
    if not pairs:
        return None
    return round(sum(v for _, v in pairs) / len(pairs), 4)


def trend(series: dict | None) -> float | None:
    """Linear slope over agricultural years (units per year)."""
    pairs = _sorted_numeric_series(series)
    if len(pairs) < 2:
        if len(pairs) == 1:
            return 0.0
        return None
    years = [float(y) for y, _ in pairs]
    values = [v for _, v in pairs]
    n = len(years)
    mean_y = sum(years) / n
    mean_v = sum(values) / n
    num = sum((y - mean_y) * (v - mean_v) for y, v in zip(years, values))
    den = sum((y - mean_y) ** 2 for y in years)
    if den == 0:
        return None
    return round(num / den, 4)


def delta_g_series(mws_doc: dict) -> dict[str, float] | None:
    hydro = mws_doc.get("hydrological_annual") or {}
    if not hydro:
        return None
    out: dict[str, float] = {}
    for year, row in hydro.items():
        if not isinstance(row, dict):
            continue
        delta = row.get("delta_g_mm")
        if delta is not None:
            out[str(year)] = float(delta)
            continue
        precip = row.get("precipitation_mm")
        et = row.get("et_mm")
        runoff = row.get("runoff_mm")
        if precip is not None and et is not None and runoff is not None:
            out[str(year)] = round(float(precip) - float(et) - float(runoff), 3)
    return out or None


def precipitation_series(mws_doc: dict) -> dict[str, float] | None:
    return _annual_field_series(mws_doc, "precipitation_mm")


def seasonal_precipitation_series(mws_doc: dict, season: str) -> dict[str, float] | None:
    """Per-agricultural-year precipitation_mm for one season (kharif, rabi, zaid)."""
    seasonal = mws_doc.get("hydrological_seasonal") or {}
    out: dict[str, float] = {}
    for year, row in seasonal.items():
        if not isinstance(row, dict):
            continue
        block = row.get(season)
        if isinstance(block, dict) and block.get("precipitation_mm") is not None:
            out[str(year)] = float(block["precipitation_mm"])
    return out or None


def et_series(mws_doc: dict) -> dict[str, float] | None:
    return _annual_field_series(mws_doc, "et_mm")


def runoff_series(mws_doc: dict) -> dict[str, float] | None:
    return _annual_field_series(mws_doc, "runoff_mm")


def _annual_field_series(mws_doc: dict, field: str) -> dict[str, float] | None:
    hydro = mws_doc.get("hydrological_annual") or {}
    out: dict[str, float] = {}
    for year, row in hydro.items():
        if isinstance(row, dict) and row.get(field) is not None:
            out[str(year)] = float(row[field])
    return out or None


def cropping_intensity_series(mws_doc: dict) -> dict[str, float] | None:
    ci = mws_doc.get("cropping_intensity") or {}
    out: dict[str, float] = {}
    for year, row in ci.items():
        if isinstance(row, dict) and row.get("cropping_intensity") is not None:
            out[str(year)] = float(row["cropping_intensity"])
    return out or None


def kharif_cropped_area_ha_series(mws_doc: dict) -> dict[str, float] | None:
    drought = mws_doc.get("drought_kharif") or {}
    out: dict[str, float] = {}
    for year, row in drought.items():
        if isinstance(row, dict) and row.get("kharif_cropped_ha") is not None:
            out[str(year)] = float(row["kharif_cropped_ha"])
    return out or None


def double_crop_area_ha_series(mws_doc: dict) -> dict[str, float] | None:
    ci = mws_doc.get("cropping_intensity") or {}
    out: dict[str, float] = {}
    for year, row in ci.items():
        if isinstance(row, dict) and row.get("double_crop_ha") is not None:
            out[str(year)] = float(row["double_crop_ha"])
    return out or None


def swb_total_area_ha_series(mws_doc: dict) -> dict[str, float] | None:
    swb = mws_doc.get("swb_annual") or {}
    out: dict[str, float] = {}
    for year, row in swb.items():
        if isinstance(row, dict) and row.get("total_ha") is not None:
            out[str(year)] = float(row["total_ha"])
    return out or None


def swb_rabi_kharif_ratio_series(mws_doc: dict) -> dict[str, float] | None:
    swb = mws_doc.get("swb_annual") or {}
    if not swb:
        return None
    out: dict[str, float] = {}
    for year, row in swb.items():
        if not isinstance(row, dict):
            continue
        kharif = row.get("kharif_ha")
        rabi = row.get("rabi_ha")
        if kharif is None and rabi is None:
            continue
        try:
            kharif_val = float(kharif or 0)
        except (TypeError, ValueError):
            continue
        if kharif_val == 0:
            out[str(year)] = 0.0
            continue
        if rabi is None:
            continue
        try:
            out[str(year)] = round(float(rabi) / kharif_val, 4)
        except (TypeError, ValueError):
            continue
    return out or None


def drought_weeks_series(mws_doc: dict, field: str) -> dict[str, float] | None:
    drought = mws_doc.get("drought_kharif") or {}
    out: dict[str, float] = {}
    for year, row in drought.items():
        if isinstance(row, dict) and row.get(field) is not None:
            out[str(year)] = float(row[field])
    return out or None


def _drought_causality(mws_doc: dict) -> dict:
    from services.variable_registry import normalize_drought_causality

    return normalize_drought_causality(mws_doc.get("drought_causality"))


def latest_drought_year_payload(mws_doc: dict) -> dict | None:
    causality = _drought_causality(mws_doc)
    if not causality:
        return None
    years = sorted(str(y) for y in causality.keys())
    if not years:
        return None
    payload = causality.get(years[-1])
    return payload if isinstance(payload, dict) else None


def latest_drought_metric(mws_doc: dict, severity: str, metric: str) -> float | None:
    payload = latest_drought_year_payload(mws_doc)
    if not payload:
        return None
    block = payload.get(severity) or {}
    if not isinstance(block, dict):
        return 0.0
    value = block.get(metric)
    if value is None:
        return 0.0
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def latest_drought_path_score(mws_doc: dict, severity: str = "severe_moderate") -> float | None:
    payload = latest_drought_year_payload(mws_doc)
    if not payload:
        return None
    block = payload.get(severity) or {}
    if not isinstance(block, dict):
        return None
    total = 0.0
    found = False
    for key, value in block.items():
        if not str(key).startswith("drought_path") or value is None:
            continue
        try:
            total += float(value)
            found = True
        except (TypeError, ValueError):
            continue
    return round(total, 4) if found else 0.0


def drought_return_period(weeks_series: dict | None, *, min_weeks: float = 1.0) -> float | None:
    """Average years between drought events (years with weeks >= min_weeks).

    When the series spans N years with zero qualifying events, returns N (a lower bound
    on return period) so expressions like ``drought_severe_return_period <= 4`` evaluate
    as FALSE rather than leaving the variable unresolved.
    """
    pairs = _sorted_numeric_series(weeks_series)
    if not pairs:
        return None
    event_years = sum(1 for _, weeks in pairs if weeks >= min_weeks)
    if event_years == 0:
        return float(len(pairs))
    return round(len(pairs) / event_years, 2)


def latest_lulc_field_ha(mws_doc: dict, field: str) -> float | None:
    """Return the latest agricultural year value for one lulc_ha class field."""
    lulc = mws_doc.get("lulc_ha") or {}
    latest_year: int | None = None
    latest_val: float | None = None
    for year, row in lulc.items():
        if not isinstance(row, dict) or row.get(field) is None:
            continue
        try:
            year_i = int(year)
            value = float(row[field])
        except (TypeError, ValueError):
            continue
        if latest_year is None or year_i > latest_year:
            latest_year = year_i
            latest_val = value
    return latest_val


def tree_cover_percent_mws(mws_doc: dict) -> float | None:
    """Latest tree/forest LULC hectares as percent of total MWS area."""
    area = mws_doc.get("area_ha")
    tree_ha = latest_lulc_field_ha(mws_doc, "tree_forest")
    if area is None or tree_ha is None:
        return None
    try:
        area_f = float(area)
        if area_f <= 0:
            return None
        return round(tree_ha / area_f * 100.0, 2)
    except (TypeError, ValueError):
        return None


def resolve_derived(mws_doc: dict, variable: str) -> Any:
    """Resolve a derived diagnostic variable name to a scalar or series."""
    if variable == "mean_annual_precipitation_mm":
        return mean(precipitation_series(mws_doc))
    if variable == "trend_annual_precipitation_mm":
        return trend(precipitation_series(mws_doc))
    if variable == "mean_kharif_precipitation":
        return mean(seasonal_precipitation_series(mws_doc, "kharif"))
    if variable == "mean_rabi_precipitation":
        return mean(seasonal_precipitation_series(mws_doc, "rabi"))
    if variable == "mean_zaid_precipitation":
        return mean(seasonal_precipitation_series(mws_doc, "zaid"))
    if variable == "mean_annual_et_mm":
        return mean(et_series(mws_doc))
    if variable == "trend_annual_et_mm":
        return trend(et_series(mws_doc))
    if variable == "mean_annual_runoff_mm":
        return mean(runoff_series(mws_doc))
    if variable == "trend_annual_runoff_mm":
        return trend(runoff_series(mws_doc))
    if variable == "mean_annual_delta_g_mm":
        return mean(delta_g_series(mws_doc))
    if variable == "trend_annual_delta_g_mm":
        return trend(delta_g_series(mws_doc))
    if variable == "mean_cropping_intensity":
        return mean(cropping_intensity_series(mws_doc))
    if variable == "trend_cropping_intensity":
        return trend(cropping_intensity_series(mws_doc))
    if variable == "mean_kharif_cropped_area_ha":
        return mean(kharif_cropped_area_ha_series(mws_doc))
    if variable == "trend_kharif_cropped_area_ha":
        return trend(kharif_cropped_area_ha_series(mws_doc))
    if variable == "mean_double_crop_area_ha":
        return mean(double_crop_area_ha_series(mws_doc))
    if variable == "trend_double_crop_area_ha":
        return trend(double_crop_area_ha_series(mws_doc))
    if variable == "drought_moderate_return_period":
        return drought_return_period(drought_weeks_series(mws_doc, "moderate_weeks"))
    if variable == "drought_severe_return_period":
        return drought_return_period(drought_weeks_series(mws_doc, "severe_weeks"))
    if variable == "mean_swb_total_area_ha":
        return mean(swb_total_area_ha_series(mws_doc))
    if variable == "trend_swb_total_area_ha":
        return trend(swb_total_area_ha_series(mws_doc))
    if variable == "mean_swb_rabi_kharif_ratio":
        return mean(swb_rabi_kharif_ratio_series(mws_doc))
    if variable == "trend_swb_rabi_kharif_ratio":
        return trend(swb_rabi_kharif_ratio_series(mws_doc))
    if variable == "drought_mild_spi_score_latest":
        return latest_drought_metric(mws_doc, "mild", "spi_score")
    if variable == "drought_mild_mai_score_latest":
        return latest_drought_metric(mws_doc, "mild", "mai_score")
    if variable == "drought_mild_vci_score_latest":
        return latest_drought_metric(mws_doc, "mild", "vci_score")
    if variable == "drought_severe_moderate_spi_score_latest":
        return latest_drought_metric(mws_doc, "severe_moderate", "spi_score")
    if variable == "drought_severe_moderate_mai_score_latest":
        return latest_drought_metric(mws_doc, "severe_moderate", "mai_score")
    if variable == "drought_severe_moderate_vci_score_latest":
        return latest_drought_metric(mws_doc, "severe_moderate", "vci_score")
    if variable == "drought_severe_moderate_path_score_latest":
        return latest_drought_path_score(mws_doc)
    if variable == "tree_cover_percent_mws":
        return tree_cover_percent_mws(mws_doc)
    return None
