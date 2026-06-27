"""Tier-2 short note labels for overall_reasoning_note (expression detail stays in tooltip)."""

from __future__ import annotations

import re

# Exact expression → compact note label.
EXPRESSION_NOTE_LABELS: dict[str, str] = {
    # --- drought ---
    "drought_severe_return_period <= 4 or drought_moderate_return_period <= 4": (
        "Severe/moderate drought return period ≤ 4 years"
    ),
    "mean(dry_spell_weeks) >= 3": "Mean dry-spell weeks ≥ 3",
    # --- groundwater_stress ---
    "mean_annual_delta_g_mm < 0": "Negative mean annual groundwater balance (P−ET−runoff)",
    "soge_dev_percent > 70 or soge_class_name in ['Semi-critical', 'Critical', 'Over-exploited']": (
        "SOGE > 70% or semi-critical+ block classification"
    ),
    "soge_dev_percent > 90 or soge_class_name in ['Critical', 'Over-exploited']": (
        "SOGE > 90% or critical/over-exploited block"
    ),
    "aquifer_class in ['alluvium'] and acwadam_class_percent.get('alluvium', 0) > 40": (
        "Dominant alluvial aquifer (>40% of MWS)"
    ),
    "aquifer_class in ['alluvium'] and acwadam_class_percent.get('alluvium', 0) > 50": (
        "Dominant alluvial aquifer (>50% of MWS)"
    ),
    "aquifer_class in ['alluvium'] and acwadam_class_percent.get('alluvium', 0) > 60": (
        "Dominant alluvial aquifer (>60% of MWS)"
    ),
    "aquifer_class in ['crystalline_basement'] and acwadam_class_percent.get('alluvium', 0) < 20": (
        "Dominant hard-rock aquifer (crystalline basement)"
    ),
    "(aquifer_class in ['volcanic', 'crystalline_basement', 'sedimentary_hard_rock']) and (acwadam_class_percent.get('alluvium', 0) < 20 or acwadam_class_percent.get('alluvium', 0) is None)": (
        "Dominant hard-rock aquifer (volcanic/crystalline/sedimentary)"
    ),
    "nrega_swc_count < 10": "Fewer than 10 cumulative MGNREGA SWC works",
    "nrega_swc_count <= 10": "10 or fewer cumulative MGNREGA SWC works",
    # --- irrigation_challenges ---
    "trend_swb_total_area_ha < 1 and swb_count <= 15": (
        "SWB area trend < 1 ha/year and ≤ 15 water bodies"
    ),
    "trend_swb_total_area_ha < -5 and swb_count < 3": (
        "SWB area loss > 5 ha/year and fewer than 3 water bodies"
    ),
    "mean_swb_rabi_kharif_ratio < 0.35": "Rabi-to-kharif SWB area ratio below 0.35",
    "mean_swb_rabi_kharif_ratio < 0.4": "Rabi-to-kharif SWB area ratio below 0.4",
    "nrega_swc_count <= 20": "20 or fewer cumulative MGNREGA SWC/irrigation works",
    "river_name is None": "No named river through or adjacent to the MWS",
    "river_name is None and dist_cooperative_km > 10": (
        "No river in MWS and cooperative > 10 km away"
    ),
    "river_name is None and dist_cooperative_km > 15": (
        "No river in MWS and cooperative > 15 km away"
    ),
    "dist_cooperative_km > 15": "Nearest agricultural cooperative > 15 km away",
    "dist_cooperative_km > 15 and river_name is None": (
        "No river in MWS and cooperative > 15 km away"
    ),
    "(swb_count <= 15) and (dist_cooperative_km > 15)": (
        "Few SWBs and distant agricultural cooperative"
    ),
    "cd_urbanization_ha > 20": "Settlement footprint expanded > 20 ha",
    "cd_urbanization_ha > 30": "Settlement footprint expanded > 30 ha",
    "cd_urbanization_ha > 50": "Settlement footprint expanded > 50 ha",
    "cd_urbanization_ha > 5": "Settlement footprint expanded > 5 ha",
    "dist_dairy_km > 20": "Nearest dairy infrastructure > 20 km away",
    "dist_dairy_km > 30": "Nearest dairy infrastructure > 30 km away",
    "drought_weeks_severe[-1] > 4": "Severe drought > 4 weeks in latest kharif",
    "drought_weeks_severe[-1] > 4 or drought_severe_return_period < 4": (
        "Severe recent kharif drought or frequent severe drought return"
    ),
    "nrega_swc_count < 5": "Fewer than 5 cumulative MGNREGA SWC works",
    # --- rainfed_risk ---
    "canal_name is None and nrega_irrigation_count <= 35": (
        "No canal in MWS and ≤ 35 MGNREGA irrigation works"
    ),
    "mean_cropping_intensity <= 1.15": "Mean cropping intensity ≤ 1.15",
    "net_irrigated_area_ha < 0.05 * lulc_cropland_ha[-1]": (
        "Irrigated share of cultivated land negligible (<5–10%)"
    ),
    # --- encroachment ---
    "cd_forest_to_farm_ha > 29": "Forest-to-farm conversion > 30 ha cumulative",
    "cd_forest_to_farm_ha > 20": "Forest-to-farm conversion > 20 ha cumulative",
    "cd_forest_to_farm_ha > 10": "Forest-to-farm conversion > 10 ha cumulative",
    "cd_total_urbanization_ha > 29": "Settlement footprint expanded > 30 ha",
    "cd_total_urbanization_ha > 20": "Settlement footprint expanded > 20 ha",
    "village_st_percent > 25": "Scheduled Tribe population > 25%",
    # --- forest_degradation ---
    "cd_total_deforestation_ha > 29": "Cumulative deforestation > 30 ha",
    "cd_total_deforestation_ha > 20": "Cumulative deforestation > 20 ha",
    # --- multi_sector_vulnerability ---
    "(village_sc_percent + village_st_percent) > 40 and village_literacy_rate < 55": (
        "SC+ST > 40% and literacy below 55%"
    ),
    "(village_sc_percent + village_st_percent) > 40 or village_literacy_rate < 55": (
        "SC+ST > 40% or literacy below 55%"
    ),
    "(village_sc_percent + village_st_percent) > 40": "Combined SC+ST population > 40%",
    "dist_bank_km > 10": "Nearest bank branch > 10 km away",
    "dist_bank_km > 5": "Nearest bank branch > 5 km away",
    "dist_bank_km > 10 or nrega_swc_count < 5": (
        "Bank branch > 10 km or < 5 MGNREGA SWC works"
    ),
    "dist_bank_km > 5 or nrega_swc_count < 5": (
        "Bank branch > 5 km or < 5 MGNREGA SWC works"
    ),
    # --- small_landholding ---
    "(lulc_cropland_ha[-1] / (village_total_population + 1e-9)) < 0.2": (
        "Per-capita cropland below 0.2 ha/person"
    ),
    "(lulc_cropland_ha[-1] / (village_total_population + 1e-9)) < 0.4": (
        "Per-capita cropland below 0.4 ha/person"
    ),
    "dist_apmc_km > 30": "Nearest APMC market > 30 km away",
    "mean_cropping_intensity <= 1.15 and trend_cropping_intensity <= 0": (
        "Cropping intensity ≤ 1.15 with flat or declining trend"
    ),
}

# Regex patterns checked in order (first match wins).
EXPRESSION_NOTE_LABEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # drought
    (
        re.compile(r"mean_kharif_precipitation\s*<\s*0\.75", re.I),
        "Kharif seasonal rainfall below 75% of long-run mean",
    ),
    (
        re.compile(r"mean_annual_precipitation_mm\s*<\s*\d+", re.I),
        "Mean annual precipitation below zone threshold",
    ),
    (
        re.compile(r"trend_annual_precipitation_mm\s*<\s*-?\d+", re.I),
        "Declining multi-year precipitation trend",
    ),
    (
        re.compile(r"monsoon_onset_delay_first_year_days\s*>\s*7", re.I),
        "Monsoon onset delayed > 7 days vs earliest year",
    ),
    (
        re.compile(r"monsoon_onset_delay_first_year_days\s*>\s*10", re.I),
        "Monsoon onset delayed > 10 days vs earliest year",
    ),
    (
        re.compile(r"monsoon_onset_delay_lag3_days\s*>\s*7", re.I),
        "Monsoon onset delayed > 7 days vs three years ago",
    ),
    (
        re.compile(r"\(monsoon_onset_date\[.*\]\s*-\s*monsoon_onset_date\[.*\]\)\s*>\s*7", re.I),
        "Monsoon onset delayed > 7 days vs earliest year",
    ),
    (
        re.compile(r"\(monsoon_onset_date\[.*\]\s*-\s*monsoon_onset_date\[.*\]\).*>\s*10", re.I),
        "Monsoon onset delayed > 10 days vs earliest year",
    ),
    (
        re.compile(r"drought_mild_spi_score_latest|drought_severe_moderate_spi_score", re.I),
        "SPI/VCI/MAI drought composite threshold met",
    ),
    # groundwater
    (
        re.compile(r"trend_annual_delta_g_mm\s*<\s*0.*mean_annual_delta_g_mm\s*<\s*0", re.I),
        "Negative groundwater balance trend and multi-year mean",
    ),
    (
        re.compile(r"soge_dev_percent\s*>\s*\d+", re.I),
        "Elevated block SOGE or semi-critical+ classification",
    ),
    (
        re.compile(r"aquifer_class\s+in\s+\[.*alluvium", re.I),
        "Dominant alluvial aquifer lithology",
    ),
    (
        re.compile(r"aquifer_class\s+in\s+\[.*crystalline|volcanic|hard_rock", re.I),
        "Hard-rock or volcanic aquifer context",
    ),
    # irrigation
    (
        re.compile(r"trend_swb_total_area_ha\s*<\s*", re.I),
        "Declining surface water body area",
    ),
    (
        re.compile(r"river_name\s+is\s+None", re.I),
        "No named river through or adjacent to the MWS",
    ),
    (
        re.compile(r"dist_cooperative_km\s*>\s*\d+", re.I),
        "Distant agricultural cooperative society",
    ),
    (
        re.compile(r"cd_urbanization_ha\s*>\s*\d+", re.I),
        "Settlement or urban footprint expansion",
    ),
    (
        re.compile(r"cd_forest_to_farm_ha.*cd_urbanization_ha|cd_urbanization_ha.*cd_forest_to_farm_ha", re.I),
        "Forest-to-farm and settlement expansion co-occur",
    ),
    (
        re.compile(r"dist_dairy_km\s*>\s*\d+", re.I),
        "Remote dairy or livestock market infrastructure",
    ),
    (
        re.compile(r"drought_weeks_severe", re.I),
        "Severe drought weeks in recent kharif season",
    ),
    (
        re.compile(r"swb_count\s*<=?\s*\d+", re.I),
        "Few surface water bodies in the MWS",
    ),
    # rainfed
    (
        re.compile(r"mean_kharif_cropped_area_ha\s*/", re.I),
        "Single-kharif dominance on cropped area",
    ),
    (
        re.compile(r"mean_swb_rabi_kharif_ratio\s*<\s*0\.\d+", re.I),
        "Low rabi-to-kharif surface water body ratio",
    ),
    (
        re.compile(r"terrain_cluster_id\s*==\s*3.*runoff", re.I),
        "High runoff on broad plains/slopes terrain",
    ),
    (
        re.compile(r"canal_name\s+is\s+None", re.I),
        "No irrigation canal in the micro-watershed",
    ),
    # encroachment / forest
    (
        re.compile(r"cd_forest_to_farm_ha\s*>\s*\d+", re.I),
        "Measurable forest-to-farm conversion",
    ),
    (
        re.compile(r"cd_total_urbanization_ha\s*>\s*\d+", re.I),
        "Settlement or urban footprint expansion",
    ),
    (
        re.compile(r"cd_total_deforestation_ha\s*>\s*\d+", re.I),
        "Measurable cumulative deforestation",
    ),
    (
        re.compile(r"village_st_percent\s*>\s*\d+", re.I),
        "High Scheduled Tribe population share",
    ),
    # multi_sector
    (
        re.compile(r"village_sc_percent.*village_st_percent", re.I),
        "High combined SC/ST population share",
    ),
    (
        re.compile(r"village_literacy_rate\s*<\s*\d+", re.I),
        "Village literacy below threshold",
    ),
    (
        re.compile(r"dist_bank_km\s*>\s*\d+", re.I),
        "Poor banking access (distance to branch)",
    ),
    (
        re.compile(r"drought_severe_return_period|drought_weeks_severe", re.I),
        "Recurring severe drought in recent kharif",
    ),
    (
        re.compile(r"migrant_household_percent\s*>\s*\d+", re.I),
        "High seasonal or permanent out-migration",
    ),
    (
        re.compile(r"household_income|farm_income", re.I),
        "Low mean household or farm income",
    ),
    # small_landholding
    (
        re.compile(r"lulc_cropland_ha.*village_total_population", re.I),
        "Low per-capita cropland availability",
    ),
    (
        re.compile(r"dist_apmc_km\s*>\s*\d+", re.I),
        "Remote APMC / regulated market access",
    ),
    (
        re.compile(r"msp|farm_gate_price|sub-MSP|sub_MSP", re.I),
        "Farm-gate price below MSP",
    ),
    (
        re.compile(r"nrega.*<=?\s*\d+", re.I),
        "Low cumulative MGNREGA community works",
    ),
]

# Fallback when expression is empty (qualitative) or no expression match.
PATHWAY_SIG_NOTE_LABELS: dict[tuple[str, str], str] = {
    # drought
    ("drought", "sig_05"): "Delayed monsoon onset vs earliest year in record",
    # groundwater_stress
    ("groundwater_stress", "sig_05"): "Farmer-reported well deepening or dry-season failure",
    ("groundwater_stress", "sig_06"): "Farmer-reported high borewell/tubewell density",
    ("groundwater_stress", "sig_07"): "Farmer-reported saline or brackish well water",
    # irrigation_challenges
    ("irrigation_challenges", "sig_05"): "Farmer-reported well shallowing or unreliable irrigation water",
    # rainfed_risk
    ("rainfed_risk", "sig_05"): "Low rabi surface-water retention or irrigated-area proxy",
    # encroachment
    ("encroachment", "sig_05"): "Pending or rejected FRA claims with NTFP decline",
    ("encroachment", "sig_06"): "Absent or disputed forest boundary demarcation",
    # forest_degradation
    ("forest_degradation", "sig_06"): "Collector-reported NTFP decline from habitat loss",
    # multi_sector_vulnerability
    ("multi_sector_vulnerability", "sig_02"): "Village literacy below threshold",
    ("multi_sector_vulnerability", "sig_06"): "High household out-migration reported",
    ("multi_sector_vulnerability", "sig_07"): "Low mean household income",
    # small_landholding
    ("small_landholding", "sig_04"): "Weak dairy or livelihood diversification infrastructure",
    ("small_landholding", "sig_05"): "Remote dairy infrastructure or weak livestock market access",
    ("small_landholding", "sig_06"): "Farm-gate price persistently below MSP",
    ("small_landholding", "sig_07"): "Majority of households own under 1 ha",
    ("small_landholding", "sig_08"): "Low livestock holding per household",
}


def _normalize_expr(expr: str) -> str:
    return re.sub(r"\s+", " ", str(expr or "").strip())


def template_note_label(pathway: str, sig_id: str, expression: str) -> str | None:
    """Return Tier-2 template label if one applies."""
    pathway = str(pathway or "").strip()
    sig_id = str(sig_id or "").strip()
    expr = _normalize_expr(expression)

    if expr:
        if expr in EXPRESSION_NOTE_LABELS:
            return EXPRESSION_NOTE_LABELS[expr]
        for pattern, label in EXPRESSION_NOTE_LABEL_PATTERNS:
            if pattern.search(expr):
                return label

    return PATHWAY_SIG_NOTE_LABELS.get((pathway, sig_id))
