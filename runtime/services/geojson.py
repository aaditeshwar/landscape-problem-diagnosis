from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid


def dissolve_boundary_geometry(geom: dict[str, Any]) -> dict[str, Any]:
    """Merge internal edges in MultiPolygon tehsil geometry (dissolved MWS footprints)."""
    try:
        dissolved = unary_union(make_valid(shape(geom)))
        if dissolved.is_empty:
            return geom
        return mapping(dissolved)
    except Exception:
        return geom


def boundaries_to_feature_collection(
    docs: list[dict],
    *,
    id_field: str,
    extra_props: tuple[str, ...] = ("state", "district", "tehsil"),
) -> dict[str, Any]:
    features = []
    for doc in docs:
        geom = doc.get("geometry")
        if not geom:
            continue
        props = {id_field: doc.get(id_field)}
        for key in extra_props:
            if key in doc:
                props[key] = doc[key]
        features.append({"type": "Feature", "properties": props, "geometry": geom})
    return {"type": "FeatureCollection", "features": features}


def sanitize_mongo_doc(doc: dict | None) -> dict | None:
    if not doc:
        return None
    out = dict(doc)
    out.pop("_id", None)
    return out
