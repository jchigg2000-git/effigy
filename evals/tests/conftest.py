"""Shared pytest setup for the evals harness tests.

The harness scripts are run as `python evals/<script>.py` and import each other as top-level
modules, so the tests put `evals/` on the path the same way rather than packaging it.
Run from the repo root: `husk-api/.venv/bin/python -m pytest -q evals/tests`.
"""
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent.parent
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))
