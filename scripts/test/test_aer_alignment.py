#!/usr/bin/env python3
"""Unit tests for AER alignment classification."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.aer_alignment import classify_aer_alignment, overlapping_retrieval_aer_tags  # noqa: E402


def test_exact_match():
    assert classify_aer_alignment(["AER-11"], "AER-11", ["AER-11", "AER-12"]) == "exact"


def test_neighbor_proxy():
    assert (
        classify_aer_alignment(["AER-3", "AER-7", "AER-8"], "AER-11", ["AER-11", "AER-12", "AER-10", "AER-7", "AER-8"])
        == "neighbor"
    )


def test_true_mismatch():
    assert classify_aer_alignment(["AER-9"], "AER-11", ["AER-11", "AER-12", "AER-10", "AER-7", "AER-8"]) == "mismatch"


def test_overlap_tags():
    overlap = overlapping_retrieval_aer_tags(
        ["AER-3", "AER-7", "AER-8"],
        ["AER-11", "AER-12", "AER-10", "AER-7", "AER-8"],
    )
    assert overlap == ["AER-7", "AER-8"]


def main() -> int:
    test_exact_match()
    test_neighbor_proxy()
    test_true_mismatch()
    test_overlap_tags()
    print("All AER alignment tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
