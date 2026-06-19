"""Load CONTEXT_CLUSTERS metadata for API and tooling."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTEXT_CLUSTERS_PATH = ROOT / "metadata" / "context_clusters.json"


@lru_cache(maxsize=1)
def load_context_clusters() -> list[dict[str, Any]]:
    if not CONTEXT_CLUSTERS_PATH.is_file():
        return []
    data = json.loads(CONTEXT_CLUSTERS_PATH.read_text(encoding="utf-8"))
    clusters = data.get("clusters")
    if isinstance(clusters, list):
        return clusters
    return []


def cluster_by_suffix() -> dict[str, dict[str, Any]]:
    return {str(c["suffix"]): c for c in load_context_clusters() if c.get("suffix")}
