"""Sample cluster raster values at a lat/lon (local GeoTIFF or remote proxy)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from config import CLUSTER_COG_URL, CLUSTER_COG_VIEWER_URL
from services.cluster_palette import suffix_for_raster_value
from services.context_clusters import cluster_by_suffix

ROOT = Path(__file__).resolve().parents[2]
LOCAL_COG_PATH = ROOT / "data" / "clusters.tif"


def remote_raster_query_base() -> str | None:
    for url in (CLUSTER_COG_VIEWER_URL, CLUSTER_COG_URL):
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


@lru_cache(maxsize=1)
def _open_local_dataset():
    import rasterio

    return rasterio.open(LOCAL_COG_PATH)


def _sample_local_raster_value(lat: float, lon: float) -> int:
    dataset = _open_local_dataset()
    samples = list(dataset.sample([(lon, lat)]))
    if not samples:
        return 0
    raw = samples[0][0]
    if raw is None:
        return 0
    return int(round(float(raw)))


def _build_query_result(lat: float, lon: float, raster_value: int) -> dict[str, Any]:
    suffix = suffix_for_raster_value(raster_value)
    cluster = cluster_by_suffix().get(suffix) if suffix else None
    return {
        "lat": lat,
        "lon": lon,
        "raster_value": raster_value,
        "cluster_suffix": suffix,
        "cluster_label": cluster.get("label") if cluster else None,
        "cluster": cluster,
    }


def query_cluster_at_point(lat: float, lon: float) -> dict[str, Any]:
    if LOCAL_COG_PATH.is_file():
        raster_value = _sample_local_raster_value(lat, lon)
        if raster_value > 0:
            return _build_query_result(lat, lon, raster_value)

    base = remote_raster_query_base()
    if base:
        try:
            return _query_remote(base, lat, lon)
        except httpx.HTTPError as error:
            raise ValueError("No cluster at this location") from error

    if LOCAL_COG_PATH.is_file():
        raise ValueError("No cluster at this location")

    raise RuntimeError("Cluster raster is not configured")


def _query_remote(base: str, lat: float, lon: float) -> dict[str, Any]:
    url = f"{base.rstrip('/')}/raster-query"
    with httpx.Client(timeout=20.0) as client:
        response = client.get(url, params={"lat": lat, "lon": lon})
        response.raise_for_status()
        payload = response.json()

    if isinstance(payload, dict) and payload.get("cluster_suffix"):
        return payload

    raster_value = payload.get("raster_value") if isinstance(payload, dict) else None
    if isinstance(raster_value, (int, float)) and raster_value > 0:
        return _build_query_result(lat, lon, int(round(raster_value)))

    raise ValueError("No cluster at this location")
