"""
build_spatial_index.py
======================
Export tehsil boundary polygons to runtime/static/tehsil_list.geojson
for fast frontend initial map load.

Default: for each tehsil marked complete in ingest_manifest, look up its admin
boundary in the pan-India SOI GeoJSON (data/soi_tehsil.geojson or
data/soi_tehsils.geojson). MongoDB tehsil_boundaries geometry is not required —
ingest can succeed even when dissolved MWS boundaries fail (e.g. Mainpur).

Optional legacy source: MongoDB tehsil_boundaries (--from-mongodb).

Usage:
    python scripts/build_spatial_index.py
    python scripts/build_spatial_index.py --input data/soi_tehsil.geojson
    python scripts/build_spatial_index.py --from-mongodb
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from shapely.geometry import mapping, shape
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runtime" / "static" / "tehsil_list.geojson"
DB_NAME = "diagnosis_db"
SOI_CANDIDATES = (
    ROOT / "data" / "soi_tehsils.geojson",
    ROOT / "data" / "soi_tehsil.geojson",
)

load_dotenv(ROOT / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


STATE_ALIASES = {
    "chhattisgarh": "chhatisgarh",
    "chhatisgarh": "chhatisgarh",
}

# CoRE Stack / ingest label -> SOI TEHSIL spelling (alphanumeric keys)
TEHSIL_ALIASES = {
    "kaprada": "kaparada",
}


def _part_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _canon_state(state: str) -> str:
    key = _part_key(state)
    return STATE_ALIASES.get(key, key)


def _canon_tehsil(tehsil: str) -> str:
    key = _part_key(tehsil)
    return TEHSIL_ALIASES.get(key, key)


def normalize_key(state: str, district: str, tehsil: str) -> str:
    return "|".join([_canon_state(state), _part_key(district), _canon_tehsil(tehsil)])



def round_coords(value, precision: int):
    if isinstance(value, list):
        if value and isinstance(value[0], (int, float)):
            return [round(v, precision) for v in value]
        return [round_coords(item, precision) for item in value]
    return value


def round_geometry(geom: dict, precision: int) -> dict:
    out = dict(geom)
    geom_type = out.get("type")
    if geom_type == "GeometryCollection":
        out["geometries"] = [round_geometry(g, precision) for g in out.get("geometries", [])]
    elif "coordinates" in out:
        out["coordinates"] = round_coords(out["coordinates"], precision)
    return out


def simplify_geometry(geom: dict, tolerance: float) -> dict:
    shp = make_valid(shape(geom))
    simplified = shp.simplify(tolerance, preserve_topology=True)
    if simplified.is_empty:
        return geom
    return mapping(simplified)


def find_soi_path(explicit: Path | None) -> Path:
    if explicit:
        if not explicit.exists():
            raise FileNotFoundError(f"Input GeoJSON not found: {explicit}")
        return explicit
    for candidate in SOI_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No SOI tehsil GeoJSON found. Expected one of: "
        + ", ".join(str(p) for p in SOI_CANDIDATES)
    )


def load_ingested_tehsils(client: MongoClient) -> dict[str, dict]:
    """Map normalized state|district|tehsil -> canonical names and mws_count.

    Uses ingest_manifest (status=complete), not tehsil_boundaries, so tehsils
    whose dissolved boundary failed during ingest are still included for SOI lookup.
    """
    manifest_col = client[DB_NAME]["ingest_manifest"]
    lookup: dict[str, dict] = {}
    for doc in manifest_col.find(
        {"status": "complete"},
        {"state": 1, "district": 1, "tehsil": 1, "mws_count": 1},
    ):
        state = doc.get("state")
        district = doc.get("district")
        tehsil = doc.get("tehsil")
        if not state or not district or not tehsil:
            continue
        lookup[normalize_key(state, district, tehsil)] = {
            "state": state,
            "district": district,
            "tehsil": tehsil,
            "mws_count": doc.get("mws_count"),
        }
    return lookup


def soi_feature_key(props: dict) -> str | None:
    raw_state = props.get("STATE") or props.get("state")
    raw_district = props.get("District") or props.get("district")
    raw_tehsil = props.get("TEHSIL") or props.get("tehsil")
    if not raw_state or not raw_district or not raw_tehsil:
        return None
    return normalize_key(str(raw_state), str(raw_district), str(raw_tehsil))


def export_from_soi(
    input_path: Path,
    *,
    simplify: float | None,
    precision: int,
    ingested: dict[str, dict],
) -> list[dict]:
    if not ingested:
        raise ValueError(
            "No complete tehsils found in ingest_manifest — "
            "run ingest_excel.py before building tehsil_list.geojson"
        )

    log.info(
        f"Reading SOI tehsil boundaries from {input_path} "
        f"(filtering to {len(ingested)} ingested tehsil(s))"
    )
    data = json.loads(input_path.read_text(encoding="utf-8"))
    raw_features = data.get("features") or []
    if not raw_features:
        raise ValueError(f"No features found in {input_path}")

    features: list[dict] = []
    found_keys: set[str] = set()

    for idx, feat in enumerate(raw_features, start=1):
        key = soi_feature_key(feat.get("properties") or {})
        if not key or key not in ingested:
            continue

        geom = feat.get("geometry")
        if not geom:
            log.warning(f"Skipping ingested tehsil {key} — no geometry in SOI feature")
            continue

        found_keys.add(key)
        props = dict(ingested[key])

        if simplify is not None:
            geom = simplify_geometry(geom, simplify)
        geom = round_geometry(geom, precision)

        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": geom,
            }
        )

        if len(found_keys) == len(ingested):
            log.info(f"  All {len(ingested)} ingested tehsils matched in SOI — stopping scan early")
            break

        if idx % 500 == 0:
            log.info(f"  Scanned {idx}/{len(raw_features)} SOI features…")

    missing = set(ingested.keys()) - found_keys
    if missing:
        missing_labels = [
            f"{ingested[k]['tehsil']}, {ingested[k]['district']}, {ingested[k]['state']}"
            for k in sorted(missing)
        ]
        raise ValueError(
            f"SOI GeoJSON missing {len(missing)} ingested tehsil(s): {missing_labels}"
        )

    log.info(f"SOI export: wrote {len(features)} ingested tehsil boundary feature(s)")
    return features


def export_from_mongodb(client: MongoClient) -> list[dict]:
    col = client[DB_NAME]["tehsil_boundaries"]
    features: list[dict] = []
    for doc in col.find({}, {"state": 1, "district": 1, "tehsil": 1, "geometry": 1, "mws_count": 1}):
        geom = doc.get("geometry")
        if not geom:
            log.warning(f"Skipping {doc.get('tehsil')} — no geometry")
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "state": doc.get("state"),
                    "district": doc.get("district"),
                    "tehsil": doc.get("tehsil"),
                    "mws_count": doc.get("mws_count"),
                },
                "geometry": geom,
            }
        )
    return features


def write_geojson(features: list[dict], output: Path) -> None:
    if not features:
        raise ValueError("No tehsil features to export")

    geojson = {"type": "FeatureCollection", "features": features}
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(geojson, separators=(",", ":"))
    output.write_text(text, encoding="utf-8")
    size_mb = len(text.encode("utf-8")) / (1024 * 1024)
    log.info(f"Wrote {len(features)} tehsil feature(s) to {output} ({size_mb:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export tehsil_list.geojson for map load")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to pan-India SOI tehsil GeoJSON (default: data/soi_tehsil*.geojson)",
    )
    parser.add_argument(
        "--from-mongodb",
        action="store_true",
        help="Use dissolved tehsil_boundaries from MongoDB instead of SOI GeoJSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help=f"Output GeoJSON path (default: {OUTPUT})",
    )
    parser.add_argument(
        "--simplify",
        type=float,
        default=0.002,
        help="Shapely simplify tolerance in degrees (~220 m at equator); use 0 to disable",
    )
    parser.add_argument(
        "--precision",
        type=int,
        default=5,
        help="Coordinate decimal precision when exporting SOI boundaries",
    )
    args = parser.parse_args()

    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    ingested = load_ingested_tehsils(client)
    log.info(f"Loaded {len(ingested)} complete tehsil(s) from ingest_manifest")

    try:
        if args.from_mongodb:
            log.info("Exporting tehsil boundaries from MongoDB (dissolved MWS)")
            features = export_from_mongodb(client)
        else:
            input_path = find_soi_path(args.input)
            simplify = None if args.simplify <= 0 else args.simplify
            features = export_from_soi(
                input_path,
                simplify=simplify,
                precision=args.precision,
                ingested=ingested,
            )

        write_geojson(features, args.output)
        return 0
    except Exception as exc:
        log.error(str(exc))
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
