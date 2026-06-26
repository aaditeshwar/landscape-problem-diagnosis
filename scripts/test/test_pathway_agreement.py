"""Tests for pathway agreement level pairing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.pathway_agreement import (  # noqa: E402
    agreement_between,
    independent_pathway_level,
    server_pathway_level,
)


def test_server_confirmed_high():
    diagnosis = {
        "confirmed_pathways": [{"pathway_id": "drought", "confidence": "high"}],
        "uncertain_pathways": [],
    }
    assert server_pathway_level(diagnosis, "drought") == "confirmed_high"


def test_server_confirmed_medium_low():
    diagnosis = {
        "confirmed_pathways": [{"pathway_id": "drought", "confidence": "medium"}],
        "uncertain_pathways": [],
    }
    assert server_pathway_level(diagnosis, "drought") == "confirmed_medium_low"


def test_server_uncertain():
    diagnosis = {
        "confirmed_pathways": [],
        "uncertain_pathways": [{"pathway_id": "drought", "confidence": "low"}],
    }
    assert server_pathway_level(diagnosis, "drought") == "uncertain"


def test_server_unconfirmed():
    diagnosis = {"confirmed_pathways": [], "uncertain_pathways": []}
    assert server_pathway_level(diagnosis, "drought") == "unconfirmed"


def test_llm_pairings():
    diagnosis = {
        "independent_pathway_review": [
            {"pathway_id": "a", "pathway_present": "yes", "confidence": "high"},
            {"pathway_id": "b", "pathway_present": "yes", "confidence": "low"},
            {"pathway_id": "c", "pathway_present": "uncertain"},
            {"pathway_id": "d", "pathway_present": "no"},
        ]
    }
    assert independent_pathway_level(diagnosis, "a") == "confirmed_high"
    assert independent_pathway_level(diagnosis, "b") == "confirmed_medium_low"
    assert independent_pathway_level(diagnosis, "c") == "uncertain"
    assert independent_pathway_level(diagnosis, "d") == "unconfirmed"
    assert independent_pathway_level(diagnosis, "missing") == "unconfirmed"


def test_unconfirmed_pairs_with_missing_or_no():
    server = {
        "confirmed_pathways": [],
        "uncertain_pathways": [],
        "signal_evaluation": {"drought": {}},
    }
    llm_missing = {"signal_evaluation": {"drought": {}}, "independent_pathway_review": []}
    llm_no = {
        "signal_evaluation": {"drought": {}},
        "independent_pathway_review": [{"pathway_id": "drought", "pathway_present": "no"}],
    }
    missing = agreement_between(server, llm_missing, left_source="server", right_source="independent")
    explicit_no = agreement_between(server, llm_no, left_source="server", right_source="independent")
    assert missing["pathways"][0]["agree"] is True
    assert explicit_no["pathways"][0]["agree"] is True


if __name__ == "__main__":
    test_server_confirmed_high()
    test_server_confirmed_medium_low()
    test_server_uncertain()
    test_server_unconfirmed()
    test_llm_pairings()
    test_unconfirmed_pairs_with_missing_or_no()
    print("ok")
