from typing import Any


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
