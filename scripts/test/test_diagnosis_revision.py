"""Unit tests for follow-up diagnosis revision helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from services.diagnosis_revision import (  # noqa: E402
    apply_follow_up_revision,
    build_retrieval_query,
    compute_diagnosis_revision,
    normalize_qualitative_answer,
)


def test_normalize_yes_worsening():
    out = normalize_qualitative_answer("forest_degradation_observed", "Yes, it has been worsening")
    assert out["present"] is True
    assert out["trend"] == "worsening"
    assert out["raw"] == "Yes, it has been worsening"


def test_normalize_no():
    out = normalize_qualitative_answer("borewell_density", "No, we don't have many borewells")
    assert out["present"] is False
    assert out["trend"] is None


def test_retrieval_query_includes_injected():
    q = build_retrieval_query(
        "wells drying up",
        {"borewell_density": {"raw": "many new borewells", "present": True}},
    )
    assert "wells drying up" in q
    assert "borewell_density" in q
    assert "many new borewells" in q


def test_revision_promotion():
    prior = {
        "confirmed_pathways": [],
        "uncertain_pathways": [{"pathway_id": "forest_degradation", "confidence": "medium"}],
        "solutions": [],
        "panel_updates": [],
    }
    current = {
        "confirmed_pathways": [{"pathway_id": "forest_degradation", "confidence": "high"}],
        "uncertain_pathways": [],
        "solutions": ["contour bunding"],
        "panel_updates": ["drought_weeks stacked_bar"],
        "panel_update_explanation": "Show drought stress.",
    }
    revision = compute_diagnosis_revision(prior, current, answered_variable="forest_degradation_observed")
    assert revision["improved"] is True
    assert any(c["from"] == "uncertain" and c["to"] == "confirmed" for c in revision["pathway_changes"])

    gated = apply_follow_up_revision(current, prior, answered_variable="forest_degradation_observed")
    assert gated["panel_updates"] == current["panel_updates"]


def test_revision_no_change_gates_panel_updates():
    prior = {
        "confirmed_pathways": [{"pathway_id": "groundwater_stress", "confidence": "high"}],
        "uncertain_pathways": [],
        "solutions": ["recharge structures"],
        "panel_updates": ["cropping_intensity + annual_delta_g_mm dual_axis"],
    }
    current = {
        "confirmed_pathways": [{"pathway_id": "groundwater_stress", "confidence": "high"}],
        "uncertain_pathways": [],
        "solutions": ["recharge structures"],
        "panel_updates": ["drought_weeks stacked_bar"],
    }
    revision = compute_diagnosis_revision(prior, current)
    assert revision["improved"] is False

    gated = apply_follow_up_revision(current, prior)
    assert gated["panel_updates"] == []
    assert gated["diagnosis_revision"]["improved"] is False


def main() -> int:
    tests = [
        test_normalize_yes_worsening,
        test_normalize_no,
        test_retrieval_query_includes_injected,
        test_revision_promotion,
        test_revision_no_change_gates_panel_updates,
    ]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
