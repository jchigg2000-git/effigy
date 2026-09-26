"""Keep the test suite hermetic.

Importing ``app.solutions`` runs ``load_dotenv`` on ``husk-api/.env`` (see
``app/solutions/llm_translation.py``), so a contributor's local ``.env`` would
otherwise decide which key mode, gate thresholds and LLM defaults the tests
exercise. Import the app first so that load has already happened, then drop
every effigy variable so tests run against the documented defaults. Tests that
need a specific value set it themselves with ``patch.dict``.

The ``example`` stub is registered only on opt-in (``app/solutions/_example.py``),
and the contract tests drive the registry through it, so opt in before the import.
"""
import os

import pytest

os.environ["HUSK_ENABLE_EXAMPLE"] = "1"

import app.main  # noqa: E402,F401  -- triggers solution discovery and the .env load

_PREFIXES = ("HUSK_CHECK_", "LLM_")
_NAMES = frozenset({"FPE_KEY", "FPE_DEMO_KEY", "FPE_ALLOW_EPHEMERAL_KEY", "EFFIGY_ENV"})


@pytest.fixture(autouse=True, scope="session")
def _hermetic_env():
    saved = {}
    for name in list(os.environ):
        if name in _NAMES or name.startswith(_PREFIXES):
            saved[name] = os.environ.pop(name)
    yield
    os.environ.update(saved)
