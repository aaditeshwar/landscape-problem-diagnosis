"""Shared path bootstrap for repository scripts."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent


def bootstrap(*, runtime: bool = False) -> Path:
    """Add scripts/ and optionally runtime/ to sys.path; return repo ROOT."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    if runtime:
        runtime_dir = ROOT / "runtime"
        if str(runtime_dir) not in sys.path:
            sys.path.insert(0, str(runtime_dir))
    return ROOT
