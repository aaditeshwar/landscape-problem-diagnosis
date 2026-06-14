#!/usr/bin/env python3
"""Unit tests for expression audit helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from lib.expression_audit import audit_card, blocking_findings, validate_card_expressions  # noqa: E402
from services.variable_registry import normalize_expression  # noqa: E402


def test_normalize_drought_expression_passes_audit():
    raw = (
        "drought_causality_json.get('spi_kharif', 0) <= -1.0 "
        "and drought_causality_json.get('vci_kharif', 100) < 40"
    )
    patched, _ = normalize_expression(raw)
    card = {
        "card_id": "agriculture__water_scarcity__drought__001",
        "diagnostic_signals": [
            {"signal_id": "sig_03", "condition": {"expression": patched, "variables": []}}
        ],
    }
    assert blocking_findings(audit_card(card)) == []
    assert validate_card_expressions(card) == []


def test_static_cd_shape_is_blocked():
    card = {
        "card_id": "ntfp_forest_biodiversity__ntfp_decline__encroachment__001",
        "diagnostic_signals": [
            {
                "signal_id": "sig_02",
                "condition": {
                    "expression": "cd_total_urbanization_ha[-1] > cd_total_urbanization_ha[0]",
                    "variables": ["cd_total_urbanization_ha"],
                },
            }
        ],
    }
    findings = blocking_findings(audit_card(card))
    assert any(f["severity"] == "SHAPE" for f in findings)


def test_invented_drought_key_is_nested():
    card = {
        "card_id": "agriculture__water_scarcity__drought__011",
        "diagnostic_signals": [
            {
                "signal_id": "sig_03",
                "condition": {
                    "expression": "drought_causality.get('spi_class') in ['moderate_drought']",
                    "variables": ["drought_causality"],
                },
            }
        ],
    }
    findings = blocking_findings(audit_card(card))
    assert any(f["severity"] == "NESTED" for f in findings)
