from __future__ import annotations

from typing import Any

from pymongo.database import Database

from services.aer_lookup import mws_aer_profile
from services.tehsil_refs import normalize_tehsils


def _intersect_village_ids(mws_doc: dict) -> list:
    intersect = mws_doc.get("intersect_villages") or {}
    return list(intersect.get("village_ids") or [])


def village_aggregates_for_mws(db: Database, mws_doc: dict) -> dict[str, float | int]:
    """Aggregate census village indicators for villages intersecting this MWS."""
    ids = _intersect_village_ids(mws_doc)
    if not ids:
        return {}

    rows = list(
        db.village_data.find(
            {"village_id": {"$in": ids}},
            {
                "village_id": 1,
                "population": 1,
                "sc_count": 1,
                "st_count": 1,
                "sc_percent": 1,
                "st_percent": 1,
                "literacy_rate_percent": 1,
            },
        )
    )
    if not rows:
        return {}

    by_id = {row["village_id"]: row for row in rows}
    ordered = [by_id[vid] for vid in ids if vid in by_id]
    if not ordered:
        return {}

    total_pop = 0.0
    total_sc = 0.0
    total_st = 0.0
    literacy_weighted = 0.0
    sc_percent_sum = 0.0
    st_percent_sum = 0.0
    sc_percent_n = 0
    st_percent_n = 0

    for row in ordered:
        pop = row.get("population")
        if pop is not None:
            pop_f = float(pop)
            total_pop += pop_f
            if row.get("sc_count") is not None:
                total_sc += float(row["sc_count"])
            if row.get("st_count") is not None:
                total_st += float(row["st_count"])
            if row.get("literacy_rate_percent") is not None:
                literacy_weighted += float(row["literacy_rate_percent"]) * pop_f

        if row.get("sc_percent") is not None:
            sc_percent_sum += float(row["sc_percent"])
            sc_percent_n += 1
        if row.get("st_percent") is not None:
            st_percent_sum += float(row["st_percent"])
            st_percent_n += 1

    out: dict[str, float | int] = {}

    if total_pop > 0:
        out["village_total_population"] = int(round(total_pop))
        if total_sc > 0 or any(r.get("sc_count") is not None for r in ordered):
            out["village_sc_percent"] = round(total_sc / total_pop * 100, 4)
        if total_st > 0 or any(r.get("st_count") is not None for r in ordered):
            out["village_st_percent"] = round(total_st / total_pop * 100, 4)
        if literacy_weighted > 0 or any(r.get("literacy_rate_percent") is not None for r in ordered):
            out["village_literacy_rate"] = round(literacy_weighted / total_pop, 4)

    if "village_sc_percent" not in out and sc_percent_n:
        out["village_sc_percent"] = round(sc_percent_sum / sc_percent_n, 4)
    if "village_st_percent" not in out and st_percent_n:
        out["village_st_percent"] = round(st_percent_sum / st_percent_n, 4)

    return out


def _min_distance(rows: list[dict], field: str) -> float | None:
    values = []
    for row in rows:
        distances = row.get("facility_distances_km") or {}
        val = distances.get(field)
        if val is not None:
            values.append(float(val))
    return min(values) if values else None


_FACILITY_DISTANCE_SPECS: list[tuple[str, str | tuple[str, ...], str]] = [
    # Education
    ("dist_school_primary_km", "school_primary", "Primary school"),
    ("dist_school_upper_primary_km", "school_upper_primary", "Upper primary school"),
    ("dist_school_secondary_km", "school_secondary", "Secondary school"),
    ("dist_school_higher_secondary_km", "school_higher_secondary", "Higher secondary school"),
    ("dist_college_km", "college", "College"),
    ("dist_university_km", "university", "University"),
    # Health
    ("dist_chc_km", "chc", "Community health centre"),
    ("dist_phc_km", "phc", "Primary health centre"),
    ("dist_sub_centre_km", "sub_centre", "Health sub-centre"),
    ("dist_district_hospital_km", "district_hospital", "District hospital"),
    # Agriculture & allied
    ("dist_cooperative_km", "cooperative", "Agricultural cooperative society"),
    ("dist_markets_trading_km", "markets_trading", "Agricultural market"),
    ("dist_storage_warehousing_km", "storage_warehousing", "Cold storage / warehousing"),
    ("dist_agri_processing_km", "agri_processing", "Agri processing"),
    ("dist_agri_support_km", "agri_support", "Agri support infrastructure"),
    ("dist_apmc_km", "apmc", "APMC"),
    ("dist_dairy_km", "dairy", "Dairy / animal husbandry"),
    # Financial & public services
    ("dist_bank_km", ("bank_branch", "bank_atm", "bank_mitra"), "Bank (nearest)"),
    ("dist_csc_km", "csc", "Common service centre"),
    ("dist_pds_km", "pds", "PDS outlet"),
]


def facility_distances_for_mws(db: Database, mws_doc: dict) -> dict[str, float]:
    """Minimum facility distance (km) across villages intersecting this MWS."""
    ids = _intersect_village_ids(mws_doc)
    if not ids:
        return {}

    rows = list(
        db.village_data.find(
            {"village_id": {"$in": ids}},
            {"village_id": 1, "facility_distances_km": 1},
        )
    )
    if not rows:
        return {}

    out: dict[str, float] = {}
    for out_key, source, _label in _FACILITY_DISTANCE_SPECS:
        if isinstance(source, tuple):
            candidates = []
            for field in source:
                val = _min_distance(rows, field)
                if val is not None:
                    candidates.append(val)
            if candidates:
                out[out_key] = round(min(candidates), 3)
        else:
            val = _min_distance(rows, source)
            if val is not None:
                out[out_key] = round(val, 3)
    return out


def facility_distance_table_for_mws(db: Database, mws_doc: dict) -> list[dict[str, Any]]:
    """Human-readable facility distance rows for the info panel."""
    dist = facility_distances_for_mws(db, mws_doc)
    rows = []
    for out_key, _source, label in _FACILITY_DISTANCE_SPECS:
        km = dist.get(out_key)
        if km is not None:
            rows.append({"facility": label, "distance_km": km})
    return rows


def village_names_for_mws(db: Database, mws_doc: dict) -> list[dict[str, Any]]:
    ids = _intersect_village_ids(mws_doc)
    if not ids:
        return []

    details = (mws_doc.get("intersect_villages") or {}).get("details") or {}
    rows = list(
        db.village_data.find(
            {"village_id": {"$in": ids}},
            {
                "village_id": 1,
                "village_name": 1,
                "population": 1,
                "sc_percent": 1,
                "st_percent": 1,
                "literacy_rate_percent": 1,
            },
        )
    )
    by_id = {row["village_id"]: row for row in rows}
    out = []
    for vid in ids:
        row = by_id.get(vid) or {}
        meta = details.get(str(vid)) or details.get(vid) or {}
        out.append(
            {
                "village_id": vid,
                "name": row.get("village_name"),
                "population": row.get("population"),
                "sc_percent": row.get("sc_percent"),
                "st_percent": row.get("st_percent"),
                "literacy_rate_percent": row.get("literacy_rate_percent"),
                "area_intersect_ha": meta.get("area_intersect"),
                "percent_of_mws": meta.get("percentage_of_area"),
            }
        )
    out.sort(key=lambda item: (-(item.get("percent_of_mws") or 0), str(item.get("name") or "")))
    return out


def enrich_mws_doc(db: Database, doc: dict) -> dict:
    enriched = dict(doc)
    enriched["tehsils"] = normalize_tehsils(doc)
    enriched.update(mws_aer_profile(doc))
    enriched["intersect_village_names"] = village_names_for_mws(db, doc)
    enriched["village_aggregates"] = village_aggregates_for_mws(db, doc)
    enriched["facility_distances"] = facility_distances_for_mws(db, doc)
    enriched["facility_distance_table"] = facility_distance_table_for_mws(db, doc)
    return enriched
