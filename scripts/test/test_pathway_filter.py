from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from services.reasoner import normalize_diagnosis_response  # noqa: E402


def test_solutions_is_not_a_pathway():
    bundle = {
        "groundwater_stress": {"missing_variables": [], "missing_variable_questions": [], "present_variables": {}},
        "encroachment": {"missing_variables": [], "missing_variable_questions": [], "present_variables": {}},
    }
    raw = {
        "confirmed_pathways": [{"pathway_id": "groundwater_stress", "confidence": "medium", "reasoning": "x"}],
        "uncertain_pathways": [
            {"pathway_id": "encroachment", "confidence": "low", "missing_variable_questions": []},
            {"pathway_id": "solutions", "confidence": "medium", "missing_variable_questions": []},
        ],
        "solutions": ["Check dam construction"],
    }
    out = normalize_diagnosis_response(raw, bundle=bundle)
    uncertain_ids = [p["pathway_id"] for p in out["uncertain_pathways"]]
    assert "solutions" not in uncertain_ids
    assert uncertain_ids == ["encroachment"]
    assert out["solutions"] == ["Check dam construction"]
