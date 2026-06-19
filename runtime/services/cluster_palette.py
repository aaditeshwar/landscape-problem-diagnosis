"""Parse cluster palette from data/clusters.qml."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
QML_PATH = ROOT / "data" / "clusters.qml"


@lru_cache(maxsize=1)
def load_cluster_palette() -> list[dict[str, Any]]:
    if not QML_PATH.is_file():
        return []

    tree = ET.parse(QML_PATH)
    entries: list[dict[str, Any]] = []
    for node in tree.iter("paletteEntry"):
        value_raw = node.attrib.get("value")
        if value_raw is None:
            continue
        try:
            value = int(value_raw)
        except ValueError:
            continue
        label = node.attrib.get("label") or ""
        color = node.attrib.get("color") or "#000000"
        suffix = f"{value:03d}" if value > 0 else None
        entries.append(
            {
                "value": value,
                "suffix": suffix,
                "label": label,
                "color": color,
                "alpha": int(node.attrib.get("alpha", "255")),
            }
        )
    entries.sort(key=lambda item: item["value"])
    return entries


def suffix_for_raster_value(value: int) -> str | None:
    if value <= 0:
        return None
    return f"{value:03d}"
