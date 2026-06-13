#!/usr/bin/env python3
"""Download NBSS-LUP AER boundaries and validate against reference_standards.

Polygon source (Esri India Living Atlas, ICAR-NBSS&LUP 20-region layer):
  Service: https://livingatlas.esri.in/server1/rest/services/India/Agro_Ecological_Regions/MapServer
  Layer:   https://livingatlas.esri.in/server1/rest/services/India/Agro_Ecological_Regions/MapServer/0
  Query:   https://livingatlas.esri.in/server1/rest/services/India/Agro_Ecological_Regions/MapServer/0/query

Downloaded features are enriched with aer_code / aer_name from
metadata/reference_standards.json and written to data/India_AER_NBSS_LUP.geojson.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

bootstrap()

from lib.aer_lookup import (  # noqa: E402
    AER_GEOJSON_SOURCE,
    DEFAULT_AER_GEOJSON,
    fetch_aer_geojson,
    validate_aer_geojson,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_AER_GEOJSON,
        help=f"Output GeoJSON path (default: {DEFAULT_AER_GEOJSON.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the existing GeoJSON without downloading",
    )
    parser.add_argument(
        "--print-source",
        action="store_true",
        help="Print the Esri Living Atlas layer URLs and exit",
    )
    args = parser.parse_args()

    if args.print_source:
        print(f"Name: {AER_GEOJSON_SOURCE['name']}")
        print(f"Provider: {AER_GEOJSON_SOURCE['provider']}")
        print(f"Service URL: {AER_GEOJSON_SOURCE['service_url']}")
        print(f"Layer URL: {AER_GEOJSON_SOURCE['layer_url']}")
        print(f"Query URL: {AER_GEOJSON_SOURCE['query_url']}")
        return 0

    if not args.validate_only:
        print(f"Downloading from: {AER_GEOJSON_SOURCE['layer_url']}")
        fetch_aer_geojson(args.output)

    report = validate_aer_geojson(args.output)
    for line in report.summary_lines():
        print(line)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
