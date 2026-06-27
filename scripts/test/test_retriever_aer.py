#!/usr/bin/env python3
"""Unit tests for AER-aware evidence card retrieval filters."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.retriever import (  # noqa: E402
    AER_RETRIEVAL_NEIGHBORS,
    DIRECT_AER_MATCH_WEIGHT,
    _aer_tags_for_retrieval,
    _apply_direct_aer_bonus,
    _card_query,
    _fetch_candidates,
)


class FakeCollection:
    def __init__(self, docs: list[dict]):
        self.docs = docs

    def find(self, query: dict, projection: dict | None = None):
        def matches(doc: dict) -> bool:
            for key, expected in query.items():
                value = doc.get(key)
                if isinstance(expected, dict) and "$in" in expected:
                    tags = value if isinstance(value, list) else [value]
                    if not any(tag in expected["$in"] for tag in tags):
                        return False
                elif isinstance(value, list):
                    if expected not in value:
                        return False
                elif value != expected:
                    return False
            return True

        return [doc for doc in self.docs if matches(doc)]


class FakeDB:
    def __init__(self, docs: list[dict]):
        self.evidence_cards = FakeCollection(docs)


SAMPLE_CARDS = [
    {
        "_id": "enc_001",
        "card_id": "enc_001",
        "aer_tags": ["AER-6"],
        "aquifer_tags": ["hard_rock"],
        "embedding": [1.0, 0.0],
    },
    {
        "_id": "enc_003",
        "card_id": "enc_003",
        "aer_tags": ["AER-9"],
        "aquifer_tags": ["alluvium"],
        "embedding": [0.9, 0.1],
    },
    {
        "_id": "sl_006",
        "card_id": "sl_006",
        "aer_tags": ["AER-18"],
        "aquifer_tags": ["coastal", "alluvium"],
        "embedding": [0.8, 0.2],
    },
]


def test_aer_neighbors_for_aer3():
    tags = _aer_tags_for_retrieval({"nbss_lup_aer_code": "AER-3"})
    assert tags == ["AER-3", "AER-6", "AER-7", "AER-8"]


def test_fetch_candidates_excludes_wrong_aer():
    db = FakeDB(SAMPLE_CARDS)
    aer_tags = AER_RETRIEVAL_NEIGHBORS["AER-3"]
    candidates = _fetch_candidates(db, ["hard_rock"], aer_tags)
    ids = {c["card_id"] for c in candidates}
    assert "enc_001" in ids
    assert "enc_003" not in ids
    assert "sl_006" not in ids


def test_card_query_uses_in_for_multiple_aers():
    query = _card_query(["hard_rock"], ["AER-3", "AER-6"])
    assert query == {"aquifer_tags": "hard_rock", "aer_tags": {"$in": ["AER-3", "AER-6"]}}


def test_card_query_coastal_alluvium_pair():
    query = _card_query(["coastal", "alluvium"], ["AER-18"])
    assert query == {
        "aquifer_tags": {"$in": ["coastal", "alluvium"]},
        "aer_tags": "AER-18",
    }


def test_aer_neighbors_for_aer11():
    tags = _aer_tags_for_retrieval({"nbss_lup_aer_code": "AER-11"})
    assert tags == ["AER-11", "AER-12", "AER-7", "AER-8", "AER-10"]


def test_fetch_similar_aquifer_prefers_direct_aer():
    db = FakeDB(
        [
            {
                "_id": "gw_008",
                "card_id": "gw_008",
                "causal_pathway": "groundwater_stress",
                "aer_tags": ["AER-11"],
                "aquifer_tags": ["hard_rock"],
            },
            {
                "_id": "gw_005",
                "card_id": "gw_005",
                "causal_pathway": "groundwater_stress",
                "aer_tags": ["AER-10"],
                "aquifer_tags": ["semi-consolidated"],
            },
        ]
    )
    aer_tags = ["AER-11", "AER-12", "AER-7", "AER-8", "AER-10"]
    candidates = _fetch_candidates(
        db,
        ["semi-consolidated"],
        aer_tags,
        mws_aer="AER-11",
    )
    ids = {c["card_id"] for c in candidates}
    assert ids == {"gw_008"}


def test_direct_aer_bonus_prefers_mws_aer_card():
    proxy = {"card_id": "proxy", "aer_tags": ["AER-7", "AER-8"], "embedding": [1.0, 0.0]}
    direct = {"card_id": "direct", "aer_tags": ["AER-11"], "embedding": [0.95, 0.05]}
    scored = [(0.90, proxy), (0.88, direct)]
    boosted = _apply_direct_aer_bonus(scored, "AER-11")
    assert boosted[0][1]["card_id"] == "direct"
    assert boosted[0][0] >= 0.88 + DIRECT_AER_MATCH_WEIGHT


def main() -> int:
    test_aer_neighbors_for_aer3()
    test_aer_neighbors_for_aer11()
    test_fetch_similar_aquifer_prefers_direct_aer()
    test_fetch_candidates_excludes_wrong_aer()
    test_card_query_uses_in_for_multiple_aers()
    test_card_query_coastal_alluvium_pair()
    test_direct_aer_bonus_prefers_mws_aer_card()
    print("All retriever AER tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
