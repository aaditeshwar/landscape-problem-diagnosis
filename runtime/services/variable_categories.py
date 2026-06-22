"""Shared variable category labels for catalog and dashboard."""

from __future__ import annotations

import re

CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("LULC & land cover", re.compile(r"^lulc_|tree_cover|terrain_lulc", re.I)),
    ("Terrain & topography", re.compile(r"^terrain_|^elevation_|^dem_|drainage_density|flow_direction|stream_order", re.I)),
    ("Climate & hydrology", re.compile(
        r"^(annual_|seasonal_|drought_|monsoon_|dry_spell|precipitation|et_|runoff|delta_g)", re.I
    )),
    ("Groundwater & aquifer", re.compile(r"^(aquifer_|soge_|borewell|well_|groundwater)", re.I)),
    ("Cropping & agriculture", re.compile(
        r"^(cropping_|kharif_|swb_|irrigation|crop_|lulc_double|lulc_single|lulc_cropland)", re.I
    )),
    ("Forest & NTFP", re.compile(r"forest|ntfp|shrub|encroach", re.I)),
    ("NREGA & rural works", re.compile(r"^nrega_", re.I)),
    ("Socio-economic & census", re.compile(
        r"population|literacy|landholding|income|sc_|st_|village|facility_", re.I
    )),
    ("Derived & trends", re.compile(r"^(mean_|trend_)|_return_period$|tree_cover_percent", re.I)),
    ("Connectivity & admin", re.compile(r"^(uid|mws_|watershed|basin|tehsil|state|district|nbss_lup|aer)", re.I)),
]


def categorize_variable(name: str) -> str:
    for label, pattern in CATEGORY_RULES:
        if pattern.search(name):
            return label
    return "Other"


def category_sort_key(label: str) -> tuple:
    return (label == "Other", label)
