#!/usr/bin/env python3
"""Unit tests for LLM diagnosis JSON parsing and repair."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime"))

from services.reasoner import DiagnosisLLMParseError, parse_json_response  # noqa: E402


def test_parse_valid_json():
    parsed = parse_json_response('{"confirmed_pathways": [], "follow_up_question": null}')
    assert parsed["confirmed_pathways"] == []


def test_parse_strips_markdown_fence():
    text = '```json\n{"confirmed_pathways": [], "solutions": []}\n```'
    parsed = parse_json_response(text)
    assert parsed["solutions"] == []


def test_repair_trailing_comma_and_python_literals():
    text = '{"confirmed_pathways": [], "follow_up_question": None,}'
    parsed = parse_json_response(text)
    assert parsed["follow_up_question"] is None


def test_repair_unescaped_quotes_in_reasoning():
    text = """{
  "confirmed_pathways": [{"pathway_id": "multi_sector_vulnerability", "confidence": "medium", "reasoning": "MWS 12_201240 shows sig_01 TRUE for "high SC/ST" proportion but only one confirming signal."}],
  "uncertain_pathways": [],
  "solutions": [],
  "panel_update_explanation": null,
  "follow_up_question": null
}"""
    parsed = parse_json_response(text)
    assert parsed["confirmed_pathways"][0]["pathway_id"] == "multi_sector_vulnerability"
    assert "high SC/ST" in parsed["confirmed_pathways"][0]["reasoning"]


def test_parse_error_includes_raw_and_position():
    text = '{"broken": "value'
    try:
        parse_json_response(text)
    except DiagnosisLLMParseError as exc:
        assert exc.raw.startswith('{"broken"')
        assert exc.pos is not None
    else:
        raise AssertionError("expected DiagnosisLLMParseError")


def test_repair_truncated_diagnosis_json():
    # Mimics Ollama stopping after the solutions key (missing ] and value tail).
    text = (
        '{\n  "confirmed_pathways": [{"pathway_id": "groundwater_stress", "confidence": "high", "reasoning": "ok"}],\n'
        '  "uncertain_pathways": [{"pathway_id": "encroachment", "confidence": "low", "reasoning": "maybe", '
        '"missing_variable_questions": [{"variable": "forest_patch_connectivity", '
        '"question": "Have forest patches become isolated?"}]},\n'
        '  "solutions"'
    )
    parsed = parse_json_response(text)
    assert parsed["confirmed_pathways"][0]["pathway_id"] == "groundwater_stress"
    assert parsed["uncertain_pathways"][0]["pathway_id"] == "encroachment"
    assert parsed["solutions"] == []
    assert parsed["follow_up_question"] is None


def test_repair_does_not_break_closing_quote_at_eof():
    text = '{"confirmed_pathways": [], "solutions"'
    try:
        parse_json_response(text)
    except DiagnosisLLMParseError as exc:
        assert "solutions\\" not in exc.raw


if __name__ == "__main__":
    test_parse_valid_json()
    test_parse_strips_markdown_fence()
    test_repair_trailing_comma_and_python_literals()
    test_repair_unescaped_quotes_in_reasoning()
    test_repair_truncated_diagnosis_json()
    test_repair_does_not_break_closing_quote_at_eof()
    test_parse_error_includes_raw_and_position()
    print("All parse_json_response tests passed.")
