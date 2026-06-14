#!/usr/bin/env python3
"""Matrix evaluation: all case-study MWS exports x all evidence-card signals."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _bootstrap import bootstrap  # noqa: E402

bootstrap(runtime=True)

from verify.evaluate_signal_matrix import evaluate_matrix  # noqa: E402


def test_signal_matrix_no_hard_eval_errors():
    report = evaluate_matrix()
    assert report["summary"]["hard_runtime_errors"] == 0, report["hard_failures_sample"][:3]
