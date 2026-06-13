"""Re-export runtime AER lookup helpers for maintenance and ingest scripts."""

from __future__ import annotations

import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[2] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from services.aer_lookup import (  # noqa: E402,F401
    AERIndex,
    AERMatch,
    AERValidationReport,
    AER_GEOJSON_SOURCE,
    DEFAULT_AER_GEOJSON,
    LIVING_ATLAS_AER_URL,
    attach_aer_to_mws,
    fetch_aer_geojson,
    get_aer_index,
    load_reference_regions,
    validate_aer_geojson,
)
