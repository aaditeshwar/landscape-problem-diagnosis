"""Quick verification of Phase 0.6 + Phase 1 ingest results."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import ROOT, bootstrap  # noqa: E402

from dotenv import load_dotenv
from pymongo import MongoClient

bootstrap(runtime=True)
load_dotenv(ROOT / ".env")

from services.tehsil_refs import make_tehsil_ref, tehsil_membership_query  # noqa: E402
from services.variable_registry import collect_drought_nested_keys, drought_source_key_map  # noqa: E402

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000)
db = client["diagnosis_db"]

manifest = db.ingest_manifest.find_one({"_id": "Maharashtra__Yavatmal__Darwha"})
darwha_ref = make_tehsil_ref("Maharashtra", "Yavatmal", "Darwha")
mws_count = db.mws_data.count_documents(tehsil_membership_query(darwha_ref))
village_count = db.village_data.count_documents({"tehsil": "Darwha"})
banayat = db.village_data.find_one({"village_id": 0})
framework = db.diagnosis_framework.find_one({"_id": "diagnosis_framework_v1"}, {"_id": 1, "loaded_at": 1})
dictionary = db.data_dictionary.find_one({"_id": "data_dictionary_v2"}, {"_id": 1, "loaded_at": 1})

sample = db.mws_data.find_one(
    {"uid": "4_100672"},
    {
        "uid": 1,
        "tehsil": 1,
        "tehsils": 1,
        "aquifer": 1,
        "soge": 1,
        "hydrological_annual.2023": 1,
        "hydrological_annual.2017": 1,
        "intersect_villages.village_ids": 1,
    },
)

print("=== Phase 0.6: Metadata ===")
print(f"  diagnosis_framework loaded: {framework is not None}")
print(f"  data_dictionary loaded:     {dictionary is not None}")

print("\n=== Phase 1: Ingest Manifest ===")
if manifest:
    for k in ["status", "mws_count", "village_count", "geometries_fetched", "excel_file"]:
        print(f"  {k}: {manifest.get(k)}")

print("\n=== Phase 1: Collection Counts ===")
print(f"  mws_data (Darwha):     {mws_count}")
print(f"  village_data (Darwha): {village_count}")
print(f"  BANAYAT (village_id=0): {'EXCLUDED' if banayat is None else 'PRESENT (unexpected)'}")

print("\n=== Sample MWS 4_100672 ===")
if sample:
    hydro_2017 = (sample.get("hydrological_annual") or {}).get("2017", {})
    hydro_2023 = (sample.get("hydrological_annual") or {}).get("2023", {})
    print(f"  uid: {sample.get('uid')}")
    print(f"  tehsils: {len(sample.get('tehsils') or [])} membership(s)")
    print(f"  legacy tehsil: {sample.get('tehsil')}")
    print(f"  aquifer (ACWADAM): {(sample.get('aquifer') or {}).get('acwadam_class')}")
    print(f"  SOGE dev %: {(sample.get('soge') or {}).get('dev_percent')}")
    if hydro_2017:
        print(f"  2017 delta_g_mm (computed): {hydro_2017.get('delta_g_mm')}")
        print(f"  2017 has well_depth_m:      {'well_depth_m' in hydro_2017}")
        print(f"  2017 has cumulative_g_mm:   {'cumulative_g_mm' in hydro_2017}")
    if hydro_2023:
        print(f"  2023 delta_g_mm (computed): {hydro_2023.get('delta_g_mm')}")
    village_ids = (sample.get("intersect_villages") or {}).get("village_ids") or []
    print(f"  intersecting villages: {len(village_ids)} villages")
else:
    print("  NOT FOUND")

drought_sample = db.mws_data.find_one(
    {"drought_causality": {"$exists": True}, "uid": "1_34623"},
    {"uid": 1, "drought_causality.2024": 1},
)
print("\n=== Registry: drought causality normalization ===")
if drought_sample:
    keys = collect_drought_nested_keys(drought_sample.get("drought_causality"))
    raw_keys = set(drought_source_key_map().keys())
    stale = sorted(keys & raw_keys)
    print(f"  sample uid: {drought_sample.get('uid')}")
    print(f"  raw Excel nested keys still present: {len(stale)}")
    if stale:
        print(f"    examples: {stale[:5]}")
else:
    print("  drought sample NOT FOUND")

client.close()
