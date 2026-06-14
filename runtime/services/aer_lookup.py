"""NBSS-LUP Agro-Ecological Region (AER) spatial lookup for MWS boundaries."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests
from pymongo.database import Database
from pymongo.operations import UpdateOne
from shapely.geometry import Point, shape
from shapely.prepared import prep

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AER_GEOJSON = ROOT / "data" / "India_AER_NBSS_LUP.geojson"
REFERENCE_STANDARDS_PATH = ROOT / "metadata" / "reference_standards.json"

# Official NBSS-LUP AER polygon layer (Esri India Living Atlas).
# Layer browser: .../Agro_Ecological_Regions/MapServer/0
# Alternate NWIC host (often unreachable): gis.nwic.in/.../Agro_Regions/MapServer/1
AER_GEOJSON_SOURCE = {
    "name": "India Agro-Ecological Regions (NBSS-LUP, 20 regions)",
    "provider": "Esri India Living Atlas (ICAR-NBSS&LUP)",
    "service_url": (
        "https://livingatlas.esri.in/server1/rest/services/India/"
        "Agro_Ecological_Regions/MapServer"
    ),
    "layer_url": (
        "https://livingatlas.esri.in/server1/rest/services/India/"
        "Agro_Ecological_Regions/MapServer/0"
    ),
    "query_url": (
        "https://livingatlas.esri.in/server1/rest/services/India/"
        "Agro_Ecological_Regions/MapServer/0/query"
    ),
}
LIVING_ATLAS_AER_URL = AER_GEOJSON_SOURCE["query_url"]

# NBSS-LUP physio_reg labels (same order as ae_regcode 1..20 in official layers).
_PHYSIO_REG_TO_AER: dict[str, str] = {
    "WESTERN HIMALAYAS  COLD ARID ECO-REGION": "AER-1",
    "WESTERN PLAIN  KACHCHH AND PART OF KATHIAWAR PENINSULA HOT ARID ECO-REGION": "AER-2",
    "KARNATAKA PLATEAU (RAYALSEEMA AS INCLUSION)": "AER-3",
    "NORTHERN PLAIN (AND CENTRAL HIGHLANDS) INCLUDING ARAVALLIS  HOT SEMI-ARID EGO-REGION": "AER-4",
    "NORTHERN PLAIN (AND CENTRAL HIGHLANDS) INCLUDING ARAVALLIS  HOT SEMI-ARID ECO-REGION": "AER-4",
    "CENTRAL HIGHLANDS ( MALWA )  GUJARAT PLAIN AND KATHIAWAR PENINSULA  SEMI-ARID ECO-REGION": "AER-5",
    "DECCAN PLATU  HOT SEMI-ARID ECO-REGION": "AER-6",
    "DECCAN PLATEAU  (TELANGANA) AND EASTERN GHATS  HOT SEMI ARID ECO-REGION": "AER-7",
    "EASTERN GHATS AND TAMIL NADU UPLANDS AND DECCAN (K ARNATAKA) PLATEAU  HOT SEMI-ARID TO ARID ECO-REGION": "AER-8",
    "NORTHERN PLAIN  HOT SUBHUMID (DRY) ECO-REGION": "AER-9",
    "CENTRAL HIGHLANDS (MALWA AND BUNDELKHAND)  HOT SUBHUMID (DRY) ECO-REGION": "AER-10",
    "EASTERN PLATEAU (CHHATTISGARH REGION)": "AER-11",
    "EASTERN PLATEAU (CHHATTISGARH) AND EASTERN GHATS  HOT SUBHUMID ECO-REGION": "AER-11",
    "EASTERN PLATEAU (CHHOTANAGPUR) AND EASTERN GHATS  HOT SUBHUMID ECO-REGION": "AER-12",
    "EASTERN PLAIN  HOT SUBAUMID (MOIST) ECO-REGION": "AER-13",
    "WESTERN HIMALAYA  WARM SUBHUMID (TO HUMID WITH INCLUSION OF PERHUMID) ECO-REGION": "AER-14",
    "ASSAM AND BENGAL PLAIN  HOT SUBHUMID  TO HUMID  (INCLUSION  OF PERHUMID) ECO-REGION": "AER-15",
    "EASTERN HIMALAYAS  WARM PERHUMID ECO-REGION": "AER-16",
    "NORTH EASTERN HILLS (PURVACHAL)  WARM PERHUMID ECO-REGION": "AER-17",
    "EASTERN COASTAL PLAIN  HOT SUBHUMID TO SEMI-ARID EGO-REGION": "AER-18",
    "WESTERN GHATS AND COASTAL PLAIN  HOT HUMID-PERHUMID ECO-REGION": "AER-19",
    "ISLANDS  OF ANDAMAN-NICOBAR  AND LAKSHADWEEP  HOT  HUMID  TO PERHUMID ISLAND ECO-REGION": "AER-20",
}


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").upper().strip())


@lru_cache(maxsize=1)
def load_reference_regions() -> dict[str, dict[str, Any]]:
    data = json.loads(REFERENCE_STANDARDS_PATH.read_text(encoding="utf-8"))
    return data["nbss_lup_agro_ecological_regions"]["regions"]


def ae_regcode_to_aer_code(code: int | str | None) -> str | None:
    if code is None:
        return None
    if isinstance(code, str):
        text = code.strip().upper()
        if text.startswith("AER-"):
            return text
        if text == "UNKNOWN":
            return None
    try:
        number = int(code)
    except (TypeError, ValueError):
        return None
    if 1 <= number <= 20:
        return f"AER-{number}"
    return None


def resolve_aer_code(props: dict[str, Any], ref_regions: dict[str, dict[str, Any]] | None = None) -> str | None:
    """Resolve canonical AER code from feature properties."""
    ref_regions = ref_regions or load_reference_regions()
    existing = props.get("aer_code")
    if existing and existing != "UNKNOWN" and existing in ref_regions:
        return existing

    mapped = ae_regcode_to_aer_code(props.get("ae_regcode"))
    if mapped:
        return mapped

    for key in ("physio_reg", "physio_reg_original", "aer_name"):
        label = _normalize_name(str(props.get(key) or ""))
        if not label:
            continue
        if label in _PHYSIO_REG_TO_AER:
            return _PHYSIO_REG_TO_AER[label]
        for physio_label, aer_code in _PHYSIO_REG_TO_AER.items():
            if physio_label in label or label in physio_label:
                return aer_code

    return None


def rainfall_regime_from_aer_name(name: str | None) -> str | None:
    if not name:
        return None
    lower = name.lower()
    if "perhumid" in lower or "per humid" in lower:
        return "perhumid"
    if "sub-humid" in lower or "subhumid" in lower:
        return "sub-humid"
    if "humid" in lower:
        return "humid"
    if "semi-arid" in lower or "semi arid" in lower:
        return "semi-arid"
    if "arid" in lower:
        return "arid"
    return None


def mws_aer_profile(mws_doc: dict) -> dict[str, Any]:
    """NBSS-LUP AER context for an MWS, including rainfall regime label."""
    code = mws_doc.get("nbss_lup_aer_code")
    ref = load_reference_regions().get(str(code or ""), {})
    name = mws_doc.get("nbss_lup_aer_name") or ref.get("name")
    regime = rainfall_regime_from_aer_name(name)
    return {
        "nbss_lup_aer_code": code,
        "nbss_lup_aer_name": name,
        "nbss_lup_aer_physio_reg": mws_doc.get("nbss_lup_aer_physio_reg"),
        "agro_ecological_zone": name,
        "rainfall_mm_band": ref.get("rainfall_mm"),
        "rainfall_regime": regime,
    }


def enrich_feature_properties(
    props: dict[str, Any],
    ref_regions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ref_regions = ref_regions or load_reference_regions()
    out = dict(props)
    aer_code = resolve_aer_code(out, ref_regions)
    if aer_code:
        out["aer_code"] = aer_code
        out["aer_name"] = ref_regions[aer_code]["name"]
    return out


@dataclass
class AERValidationReport:
    geojson_path: str
    feature_count: int = 0
    with_geometry: int = 0
    without_geometry: int = 0
    resolved_codes: list[str] = field(default_factory=list)
    unknown_codes: list[str] = field(default_factory=list)
    missing_reference: list[str] = field(default_factory=list)
    extra_reference: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        ref = load_reference_regions()
        expected = set(ref.keys())
        resolved = set(self.resolved_codes)
        return (
            not self.errors
            and self.with_geometry > 0
            and not self.unknown_codes
            and not self.missing_reference
            and resolved == expected
        )

    def summary_lines(self) -> list[str]:
        ref = load_reference_regions()
        lines = [
            f"AER GeoJSON: {self.geojson_path}",
            f"Features: {self.feature_count} ({self.with_geometry} with geometry, {self.without_geometry} without)",
            f"Resolved AER codes ({len(self.resolved_codes)}): {', '.join(sorted(self.resolved_codes))}",
        ]
        if self.unknown_codes:
            lines.append(f"Unknown aer_code values: {', '.join(sorted(set(self.unknown_codes)))}")
        if self.missing_reference:
            lines.append(f"In reference_standards but missing from geojson: {', '.join(sorted(self.missing_reference))}")
        if self.extra_reference:
            lines.append(f"In geojson but not in reference_standards: {', '.join(sorted(self.extra_reference))}")
        for err in self.errors:
            lines.append(f"ERROR: {err}")
        lines.append("Validation: PASS" if self.ok else "Validation: FAIL")
        return lines


def validate_aer_geojson(path: Path | str | None = None) -> AERValidationReport:
    geojson_path = Path(path or DEFAULT_AER_GEOJSON)
    report = AERValidationReport(geojson_path=str(geojson_path))
    ref_regions = load_reference_regions()

    if not geojson_path.exists():
        report.errors.append(f"File not found: {geojson_path}")
        return report

    try:
        data = json.loads(geojson_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.errors.append(f"Invalid JSON: {exc}")
        return report

    features = data.get("features") or []
    report.feature_count = len(features)
    seen_codes: set[str] = set()

    for feature in features:
        props = feature.get("properties") or {}
        if feature.get("geometry"):
            report.with_geometry += 1
        else:
            report.without_geometry += 1

        aer_code = resolve_aer_code(props, ref_regions)
        raw_code = props.get("aer_code")
        if raw_code and raw_code != "UNKNOWN" and aer_code is None:
            report.unknown_codes.append(str(raw_code))
        elif aer_code:
            seen_codes.add(aer_code)
        else:
            report.unknown_codes.append(str(raw_code or props.get("physio_reg") or "UNKNOWN"))

    report.resolved_codes = sorted(seen_codes)
    report.missing_reference = sorted(set(ref_regions.keys()) - seen_codes)
    report.extra_reference = sorted(seen_codes - set(ref_regions.keys()))
    if report.with_geometry == 0:
        report.errors.append("No feature geometries found; point-in-polygon lookup will not work")
    return report


def fetch_aer_geojson(dest: Path | str | None = None, *, timeout: int = 120) -> Path:
    """Download NBSS-LUP AER polygons and write an enriched local GeoJSON."""
    dest_path = Path(dest or DEFAULT_AER_GEOJSON)
    ref_regions = load_reference_regions()
    params = {
        "where": "1=1",
        "outFields": "ae_regcode,physio_reg,area_sqkm",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": 25,
    }
    response = requests.get(LIVING_ATLAS_AER_URL, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    features = data.get("features") or []
    if len(features) != 20:
        raise RuntimeError(f"Expected 20 AER features, got {len(features)}")

    enriched_features = []
    for feature in features:
        props = enrich_feature_properties(feature.get("properties") or {}, ref_regions)
        aer_code = props.get("aer_code")
        if not aer_code or aer_code not in ref_regions:
            raise RuntimeError(f"Could not resolve AER code for feature: {props}")
        enriched_features.append(
            {
                "type": "Feature",
                "geometry": feature.get("geometry"),
                "properties": {
                    "aer_code": aer_code,
                    "aer_name": ref_regions[aer_code]["name"],
                    "physio_reg_original": props.get("physio_reg") or props.get("physio_reg_original"),
                    "ae_regcode": props.get("ae_regcode"),
                    "area_sqkm": props.get("area_sqkm"),
                },
            }
        )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type": "FeatureCollection", "features": enriched_features}
    dest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    log.info(
        "Wrote %s AER features to %s (source: %s)",
        len(enriched_features),
        dest_path,
        AER_GEOJSON_SOURCE["layer_url"],
    )
    return dest_path


@dataclass(frozen=True)
class AERMatch:
    aer_code: str
    aer_name: str
    physio_reg_original: str | None = None


class AERIndex:
    """In-memory point-in-polygon index over NBSS-LUP AER boundaries."""

    def __init__(self, geojson_path: Path | str | None = None):
        self.geojson_path = Path(geojson_path or DEFAULT_AER_GEOJSON)
        self._prepared: list[Any] = []
        self._meta: list[AERMatch] = []
        self._load()

    def _load(self) -> None:
        if not self.geojson_path.exists():
            raise FileNotFoundError(f"AER GeoJSON not found: {self.geojson_path}")

        data = json.loads(self.geojson_path.read_text(encoding="utf-8"))
        ref_regions = load_reference_regions()
        loaded = 0

        for feature in data.get("features") or []:
            geom = feature.get("geometry")
            if not geom:
                continue
            props = enrich_feature_properties(feature.get("properties") or {}, ref_regions)
            aer_code = props.get("aer_code")
            if not aer_code or aer_code not in ref_regions:
                continue
            try:
                polygon = shape(geom)
            except Exception as exc:
                log.warning("Skipping invalid AER geometry for %s: %s", aer_code, exc)
                continue
            if polygon.is_empty:
                continue
            self._prepared.append(prep(polygon))
            self._meta.append(
                AERMatch(
                    aer_code=aer_code,
                    aer_name=ref_regions[aer_code]["name"],
                    physio_reg_original=props.get("physio_reg_original") or props.get("physio_reg"),
                )
            )
            loaded += 1

        if loaded == 0:
            raise RuntimeError(
                f"No usable AER geometries in {self.geojson_path}. "
                "Run scripts/maintenance/fetch_aer_geojson.py to download boundaries."
            )
        log.debug("Loaded %s AER polygons from %s", loaded, self.geojson_path)

    def lookup_lonlat(self, lon: float, lat: float) -> AERMatch | None:
        point = Point(lon, lat)
        for prepared, meta in zip(self._prepared, self._meta):
            if prepared.contains(point):
                return meta
        return None

    def lookup_geometry(self, geometry: dict[str, Any] | None) -> AERMatch | None:
        if not geometry:
            return None
        try:
            geom = shape(geometry)
        except Exception:
            return None
        if geom.is_empty:
            return None
        centroid = geom.centroid
        return self.lookup_lonlat(centroid.x, centroid.y)


_INDEX: AERIndex | None = None


def get_aer_index(geojson_path: Path | str | None = None, *, reload: bool = False) -> AERIndex:
    global _INDEX
    path = Path(geojson_path) if geojson_path else DEFAULT_AER_GEOJSON
    if reload or _INDEX is None or _INDEX.geojson_path != path:
        _INDEX = AERIndex(path)
    return _INDEX


def attach_aer_to_mws(
    db: Database,
    uids: list[str],
    *,
    geojson_path: Path | str | None = None,
) -> dict[str, int]:
    """Look up AER for each MWS boundary and persist nbss_lup_aer_* on mws_data."""
    if not uids:
        return {"requested": 0, "updated": 0, "missing_boundary": 0, "lookup_failed": 0}

    index = get_aer_index(geojson_path)
    stats = {"requested": len(uids), "updated": 0, "missing_boundary": 0, "lookup_failed": 0}
    mws_ops: list[UpdateOne] = []

    for uid in uids:
        boundary = db.mws_boundaries.find_one({"uid": uid}, {"geometry": 1})
        if not boundary or not boundary.get("geometry"):
            stats["missing_boundary"] += 1
            continue

        match = index.lookup_geometry(boundary["geometry"])
        if not match:
            stats["lookup_failed"] += 1
            log.warning("AER lookup failed for MWS %s", uid)
            continue

        mws_ops.append(
            UpdateOne(
                {"uid": uid},
                {
                    "$set": {
                        "nbss_lup_aer_code": match.aer_code,
                        "nbss_lup_aer_name": match.aer_name,
                        "nbss_lup_aer_physio_reg": match.physio_reg_original,
                    }
                },
            )
        )
        stats["updated"] += 1

    if mws_ops:
        db.mws_data.bulk_write(mws_ops)
    return stats
