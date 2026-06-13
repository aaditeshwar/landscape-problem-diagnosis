from typing import Any

from pymongo.database import Database


def locate_point(db: Database, lon: float, lat: float) -> dict[str, Any]:
    """Resolve lon/lat to MWS uid and village_id using boundary polygons."""
    point = {"type": "Point", "coordinates": [lon, lat]}
    geo_query = {"geometry": {"$geoIntersects": {"$geometry": point}}}

    mws = db.mws_boundaries.find_one(geo_query, {"uid": 1, "state": 1, "district": 1, "tehsil": 1})
    village = db.village_boundaries.find_one(
        geo_query,
        {"village_id": 1, "state": 1, "district": 1, "tehsil": 1},
    )

    result: dict[str, Any] = {"lon": lon, "lat": lat, "found": bool(mws or village)}
    if mws:
        result["mws_uid"] = mws.get("uid")
        result["state"] = mws.get("state")
        result["district"] = mws.get("district")
        result["tehsil"] = mws.get("tehsil")
    elif village:
        result["state"] = village.get("state")
        result["district"] = village.get("district")
        result["tehsil"] = village.get("tehsil")

    if village:
        result["village_id"] = village.get("village_id")

    return result
