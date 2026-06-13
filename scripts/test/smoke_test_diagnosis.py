#!/usr/bin/env python3
"""Runtime smoke tests for newly inducted NTFP + socio-economic pathways."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_CASES = [
    {
        "name": "forest_degradation",
        "uid": "10_10124",
        "problem": (
            "Forest cover is declining and communities report reduced collection "
            "of mahua, tendu leaves, and other non-timber forest produce."
        ),
        "expect_pathways": ["forest_degradation", "ntfp_decline"],
        "expect_panel_any": ["lulc_tree_forest_ha", "cd_total_deforestation", "deforestation"],
    },
    {
        "name": "encroachment",
        "uid": "10_10124",
        "problem": (
            "Forest land is being encroached for farming and settlement, "
            "reducing tribal access to forest commons and NTFP."
        ),
        "expect_pathways": ["encroachment"],
        "expect_panel_any": ["lulc_tree_forest_ha", "cd_total_deforestation", "deforestation"],
    },
    {
        "name": "multi_sector_vulnerability",
        "uid": "10_10124",
        "problem": (
            "Households face economic hardship from drought crop losses, "
            "limited banking access, and insufficient MGNREGA employment."
        ),
        "expect_pathways": ["multi_sector_vulnerability", "economic_hardship"],
        "expect_panel_any": ["drought_weeks", "nrega"],
    },
    {
        "name": "small_landholding",
        "uid": "10_10124",
        "problem": (
            "Small fragmented landholdings, low cropping intensity, "
            "and long distances to APMC and dairy markets keep farm incomes low."
        ),
        "expect_pathways": ["small_landholding", "low_income"],
        "expect_panel_any": ["cropping_intensity", "dist_"],
    },
]


def post_json(url: str, payload: dict, timeout: int = 300) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pathway_blob(response: dict) -> str:
    parts = []
    for key in ("confirmed_pathways", "uncertain_pathways"):
        for item in response.get(key) or []:
            if isinstance(item, dict):
                parts.append(json.dumps(item))
            else:
                parts.append(str(item))
    return " ".join(parts).lower()


def run_case(base_url: str, case: dict) -> tuple[bool, list[str]]:
    notes: list[str] = []
    try:
        response = post_json(
            f"{base_url.rstrip('/')}/api/query",
            {"uid": case["uid"], "problem_description": case["problem"]},
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return False, [f"HTTP {exc.code}: {body}"]
    except Exception as exc:
        return False, [str(exc)]

    required = ("session_id", "confirmed_pathways", "panel_updates")
    missing = [k for k in required if k not in response]
    if missing:
        return False, [f"Missing keys: {missing}"]

    blob = pathway_blob(response)
    if not any(token.lower() in blob for token in case["expect_pathways"]):
        notes.append(f"Expected pathway tokens not found: {case['expect_pathways']}")
        notes.append(f"Got: {blob[:240]}")

    panel_text = " ".join(response.get("panel_updates") or []).lower()
    if case.get("expect_panel_any") and not any(tok in panel_text for tok in case["expect_panel_any"]):
        notes.append(f"Expected panel update tokens not found: {case['expect_panel_any']}")
        notes.append(f"Got panel_updates: {response.get('panel_updates')}")

    follow_up = response.get("follow_up_question")
    if follow_up:
        var = (follow_up.get("variable") if isinstance(follow_up, dict) else None) or ""
        forbidden = {
            "lulc_tree_forest_ha",
            "cd_total_deforestation_ha",
            "village_sc_percent",
            "dist_bank_km",
            "cropping_intensity",
        }
        if var in forbidden:
            notes.append(f"Follow-up asked for Excel-backed variable: {var}")

    ok = not notes
    if ok:
        notes.append(
            f"session={response['session_id'][:8]}… "
            f"panel={response.get('panel_updates')} "
            f"follow_up={bool(follow_up)}"
        )
    return ok, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--case", action="append", dest="cases", help="Case name filter")
    args = parser.parse_args()

    cases = DEFAULT_CASES
    if args.cases:
        wanted = set(args.cases)
        cases = [c for c in DEFAULT_CASES if c["name"] in wanted]

    print(f"=== Diagnosis smoke tests ({args.base_url}) ===")
    failures = 0
    for case in cases:
        ok, notes = run_case(args.base_url, case)
        status = "PASS" if ok else "FAIL"
        print(f"\n[{status}] {case['name']} (MWS {case['uid']})")
        for note in notes:
            print(f"  {note}")
        if not ok:
            failures += 1

    print(f"\n=== {'ALL PASS' if failures == 0 else f'{failures} FAILED'} ===")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
