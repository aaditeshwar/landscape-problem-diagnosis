#!/usr/bin/env python3
"""Unit tests for tehsil_refs helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.tehsil_refs import (  # noqa: E402
    doc_in_tehsil,
    format_tehsil_list,
    make_tehsil_ref,
    merge_tehsil_refs,
    normalize_tehsils,
    resolve_active_tehsil,
    tehsil_key,
    tehsil_membership_query,
)


def test_normalize_legacy_scalar():
    doc = {"uid": "1_1", "state": "S", "district": "D", "tehsil": "T"}
    refs = normalize_tehsils(doc)
    assert len(refs) == 1
    assert refs[0]["tehsil"] == "T"


def test_normalize_tehsils_list():
    doc = {
        "uid": "1_1",
        "tehsils": [
            make_tehsil_ref("S", "D", "A"),
            make_tehsil_ref("S", "D", "B"),
        ],
    }
    assert len(normalize_tehsils(doc)) == 2


def test_doc_in_tehsil():
    doc = {"tehsils": [make_tehsil_ref("S", "D", "A"), make_tehsil_ref("S", "D", "B")]}
    assert doc_in_tehsil(doc, make_tehsil_ref("S", "D", "B"))
    assert not doc_in_tehsil(doc, make_tehsil_ref("S", "D", "C"))


def test_resolve_active_tehsil():
    doc = {"tehsils": [make_tehsil_ref("S", "D", "A"), make_tehsil_ref("S", "D", "B")]}
    active = make_tehsil_ref("S", "D", "B")
    assert resolve_active_tehsil(doc, active)["tehsil"] == "B"


def test_format_tehsil_list_with_active():
    doc = {"tehsils": [make_tehsil_ref("S", "D", "A"), make_tehsil_ref("S", "D", "B")]}
    text = format_tehsil_list(doc, make_tehsil_ref("S", "D", "A"))
    assert "also in B" in text


def test_merge_tehsil_refs():
    existing = [make_tehsil_ref("S", "D", "A")]
    merged = merge_tehsil_refs(existing, make_tehsil_ref("S", "D", "B"))
    assert len(merged) == 2
    merged_again = merge_tehsil_refs(merged, make_tehsil_ref("S", "D", "B"))
    assert len(merged_again) == 2


def test_tehsil_membership_query():
    q = tehsil_membership_query(make_tehsil_ref("S", "D", "T"))
    assert q["tehsils"]["$elemMatch"]["tehsil"] == "T"


def test_tehsil_key():
    assert tehsil_key(make_tehsil_ref("Maharashtra", "Yavatmal", "Darwha")) == "Maharashtra__Yavatmal__Darwha"


if __name__ == "__main__":
    tests = [
        test_normalize_legacy_scalar,
        test_normalize_tehsils_list,
        test_doc_in_tehsil,
        test_resolve_active_tehsil,
        test_format_tehsil_list_with_active,
        test_merge_tehsil_refs,
        test_tehsil_membership_query,
        test_tehsil_key,
    ]
    for fn in tests:
        fn()
    print(f"All {len(tests)} tehsil_refs tests passed.")
