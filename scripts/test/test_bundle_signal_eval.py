from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from services.signal_evaluator import evaluate_bundle_signals  # noqa: E402

SAMPLE_BUNDLE = {
    "groundwater_stress": {
        "present_variables": {"soge_dev_percent": 56.86},
        "evidence_card": {
            "overall_reasoning_note": "Confirm with at least two primary signals.",
            "diagnostic_signals": [
                {
                    "signal_id": "sig_01",
                    "direction": "confirms",
                    "condition": {"expression": "soge_dev_percent > 70"},
                },
                {
                    "signal_id": "sig_02",
                    "direction": "confirms",
                    "condition": {"expression": "soge_dev_percent > 50"},
                },
            ],
        },
    }
}


def test_evaluate_bundle_signals_returns_ok_results():
    results = evaluate_bundle_signals(SAMPLE_BUNDLE)
    pathway = results["groundwater_stress"]
    assert pathway["summary"]["ok"] == 2
    assert pathway["summary"]["needs_llm"] == 0
    assert pathway["signals"][0]["status"] == "ok"
    assert pathway["signals"][0]["result"] is False
    assert pathway["signals"][1]["result"] is True
