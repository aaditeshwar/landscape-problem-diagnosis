"""Resolve CoRE Stack active locations to stats Excel files and standard ingest paths."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
STATS_ROOT = ROOT / "data" / "raw_excel" / "stats_excel_files"
RAW_EXCEL_DIR = ROOT / "data" / "raw_excel"
CORE_STACK_BASE = "https://geoserver.core-stack.org/api/v1"


@dataclass(frozen=True)
class TehsilLocation:
    state: str
    district: str
    tehsil: str
    state_id: str | None = None
    district_id: str | None = None
    tehsil_id: str | None = None

    @property
    def manifest_id(self) -> str:
        return f"{self.state}__{self.district}__{self.tehsil}"

    @property
    def standard_filename(self) -> str:
        return f"{self.manifest_id}_data.xlsx"

    @property
    def standard_path(self) -> Path:
        return RAW_EXCEL_DIR / self.standard_filename


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def state_folder_name(state_label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", state_label.lower()).strip("_").upper()


def is_auxiliary_excel(filename: str) -> bool:
    name = filename.lower()
    return (
        "_kyl_" in name
        or name.endswith("_kyl_village_data.xlsx")
        or name.endswith("_kyl_filter_data.xlsx")
    )


def fetch_active_locations(api_key: str | None = None, timeout: int = 90) -> list[TehsilLocation]:
    load_dotenv(ROOT / ".env")
    key = (api_key or os.getenv("CORE_STACK_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("CORE_STACK_API_KEY not set")

    response = requests.get(
        f"{CORE_STACK_BASE}/get_active_locations/",
        headers={"X-API-Key": key},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()

    locations: list[TehsilLocation] = []
    for state_entry in payload:
        state_label = state_entry["label"]
        for district_entry in state_entry.get("district", []):
            district_label = district_entry["label"]
            for block in district_entry.get("blocks", []):
                locations.append(
                    TehsilLocation(
                        state=state_label,
                        district=district_label,
                        tehsil=block["label"],
                        state_id=state_entry.get("state_id"),
                        district_id=district_entry.get("district_id"),
                        tehsil_id=block.get("tehsil_id") or block.get("block_id"),
                    )
                )
    return locations


def iter_locations(
    locations: list[TehsilLocation],
    *,
    state: str | None = None,
    district: str | None = None,
    tehsil: str | None = None,
) -> Iterator[TehsilLocation]:
    state_key = normalize_key(state) if state else None
    district_key = normalize_key(district) if district else None
    tehsil_key = normalize_key(tehsil) if tehsil else None

    for loc in locations:
        if state_key and normalize_key(loc.state) != state_key:
            continue
        if district_key and normalize_key(loc.district) != district_key:
            continue
        if tehsil_key and normalize_key(loc.tehsil) != tehsil_key:
            continue
        yield loc


def district_dirs(state_dir: Path, district_label: str) -> list[Path]:
    key = normalize_key(district_label)
    return sorted(
        path
        for path in state_dir.iterdir()
        if path.is_dir() and normalize_key(path.name) == key
    )


def find_stats_excel(
    location: TehsilLocation,
    stats_root: Path = STATS_ROOT,
) -> Path | None:
    state_dir = stats_root / state_folder_name(location.state)
    if not state_dir.is_dir():
        return None

    expected_key = normalize_key(f"{location.district}_{location.tehsil}")
    for district_dir in district_dirs(state_dir, location.district):
        for path in district_dir.glob("*.xlsx"):
            if is_auxiliary_excel(path.name):
                continue
            if normalize_key(path.stem) == expected_key:
                return path
    return None


def resolve_catalog(
    *,
    state: str | None = None,
    district: str | None = None,
    tehsil: str | None = None,
    stats_root: Path = STATS_ROOT,
    api_key: str | None = None,
) -> tuple[list[tuple[TehsilLocation, Path]], list[TehsilLocation]]:
    locations = fetch_active_locations(api_key=api_key)
    found: list[tuple[TehsilLocation, Path]] = []
    missing: list[TehsilLocation] = []

    for location in iter_locations(locations, state=state, district=district, tehsil=tehsil):
        source = find_stats_excel(location, stats_root=stats_root)
        if source is None:
            missing.append(location)
        else:
            found.append((location, source))
    return found, missing
