"""Regression tests for the 2026-09-26 service audit (SVC-*, HAR-5).

One test per finding, each failing on the code as it was before the fix. The
model is always a stub: nothing here reaches a network.
"""
import difflib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.solutions._husk_check import PassthroughDetected, check, own_module_names
from tests.test_llm_translation import _GO_SOURCE, _GOOD_HUSK, _SOURCE, _mock_completion

client = TestClient(app)
HUSK_API = Path(__file__).resolve().parent.parent


def _post(*completions, input=_SOURCE):
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = list(completions)
        return client.post("/husk/llm-translation", json={"input": input, "crumb_level": 1})


def test_postcondition_records_retry_budget():
    """SVC-1: HUSK_CHECK_RETRIES is not among the gate's thresholds, so a
    harness could not tell from the record which retry budget a husk ran under."""
    r = _post(_mock_completion(_GOOD_HUSK))
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["postcondition"]["retries_allowed"] == 1
    with patch.dict(os.environ, {"HUSK_CHECK_RETRIES": "0"}):
        r = _post(_mock_completion(_GOOD_HUSK))
    assert r.json()["meta"]["postcondition"]["retries_allowed"] == 0


def test_usage_is_summed_across_postcondition_attempts():
    """HAR-5: a refused attempt is billed, but meta.usage reported only the last
    one, and a refusal carried no usage at all."""
    r = _post(_mock_completion(_SOURCE, 100, 50), _mock_completion(_GOOD_HUSK, 120, 60))
    assert r.status_code == 200, r.text
    meta = r.json()["meta"]
    # reasoning_tokens is a MagicMock attribute on the stub: it must come back
    # None, not leak a non-int into the JSON.
    assert meta["usage"] == {"prompt_tokens": 220, "completion_tokens": 110,
                             "total_tokens": 330, "reasoning_tokens": None}
    assert [u["total_tokens"] for u in meta["usage_attempts"]] == [150, 180]

    from app.registry import get
    with patch.dict(os.environ, {"HUSK_CHECK_RETRIES": "0"}), \
            patch("app.solutions.llm_translation.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = [
            _mock_completion(_SOURCE, 100, 50)]
        with pytest.raises(PassthroughDetected) as exc:
            get("llm-translation").fn(_SOURCE, 1, {})
    assert exc.value.report["usage"]["total_tokens"] == 150
    assert exc.value.report["retries_allowed"] == 0


# A types-only Go file: no `func` anywhere, which is what the suffix guess keyed on.
_GO_TYPES_ONLY = """package model

import (
\t"time"

\t"meterworks/internal/units"
)

// Reading is one meter reading, as the ingest path stores it.
type Reading struct {
\tMeterID string
\tTakenAt time.Time
\tVolume  units.Litres
\tFlags   []string
}
"""


def test_types_only_go_file_module_name_is_refused():
    """SVC-3: without options.suffix a Go file with no `func` was read as Python,
    which switched the module-name check off."""
    from app.solutions.llm_translation import _infer_suffix

    assert _infer_suffix(_GO_TYPES_ONLY) == ".go"
    husk = (_GO_TYPES_ONLY.replace("package model", "package stay")
            .replace("Reading", "Booking").replace("MeterID", "RoomID")
            .replace("TakenAt", "BookedAt").replace("Volume", "Nights")
            .replace("Flags", "Tags").replace("meter reading", "room booking")
            .replace("ingest path", "front desk"))
    with patch.dict(os.environ, {"HUSK_CHECK_RETRIES": "0"}):
        r = _post(_mock_completion(husk), input=_GO_TYPES_ONLY)
    assert r.status_code == 500, r.text
    assert "module name 'meterworks'" in r.json()["detail"]


def test_commentary_outside_the_fence_is_not_served():
    """SVC-4: a preamble and a trailing rename note were served as part of the
    husk, and an empty fenced block was served as an empty 200."""
    note = "Note: I renamed `ClaimBatch` to `TrackQueue` and `payer_id` to `artist_id`."
    reply = ("Here is the translated code in the music streaming domain:\n\n"
             f"```python\n{_GOOD_HUSK}\n```\n\n{note}")
    r = _post(_mock_completion(reply))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output"] == _GOOD_HUSK
    assert "ClaimBatch" not in body["output"] and "```" not in body["output"]
    assert body["meta"]["discarded_outside_fence_chars"] > 0

    r = _post(_mock_completion("```python\n```"))
    assert r.status_code == 500
    assert "empty content" in r.json()["detail"].lower()


def test_reordered_passthrough_is_refused():
    """SVC-5: the source's own lines with its functions in reverse order passed
    the gate. Every span measure is in-order, and so is whole-text similarity."""
    funcs = [[f"def settle_{i}(claim_{i}, payer_{i}):",
              f"    total_{i} = claim_{i}.amount + {i}",
              f"    if payer_{i}.blocked_{i}:",
              f"        return None",
              f"    payer_{i}.post_{i}(total_{i})",
              f"    return total_{i}"] for i in range(20)]
    source = "\n".join(ln for f in funcs for ln in f)
    husk = "\n".join(ln for f in reversed(funcs) for ln in f)
    with pytest.raises(PassthroughDetected) as exc:
        check(source, husk, ".py")
    assert exc.value.report["verdict"] == "passthrough"
    assert "in whatever order" in exc.value.report["reasons"][-1]


def test_upstream_5xx_maps_to_502():
    """SVC-6: a provider 503 (after the client's own retries) surfaced as this
    service's 500 solution_failed, although the README reserves 502 for exactly this."""
    from openai import APIStatusError

    response = MagicMock()
    response.status_code = 503
    err = APIStatusError("upstream overloaded", response=response, body=None)
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = err
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    assert r.status_code == 502, r.text
    assert r.json()["error"] == "backend_unavailable"
    assert "503" in r.json()["detail"]


def _run_fresh(code: str, **env_changes) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "HUSK_ENABLE_EXAMPLE"}
    env.update(env_changes, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-c", code], cwd=HUSK_API, env=env,
                          capture_output=True, text=True, timeout=120)


def test_import_does_not_write_to_disk():
    """SVC-7: importing the app created static/ and rewrote the targets JSON, so
    it failed to start on a read-only filesystem whenever either was missing or stale."""
    p = _run_fresh(
        "import pathlib\n"
        "def refuse(*a, **k):\n"
        "    raise PermissionError('import wrote to disk')\n"
        "for name in ('mkdir', 'write_text', 'write_bytes', 'touch'):\n"
        "    setattr(pathlib.Path, name, refuse)\n"
        "import app.main\n")
    assert p.returncode == 0, p.stderr[-2000:]


def test_targets_json_matches_catalog():
    """SVC-7: the drift guard that replaces the import-time rewrite."""
    from app.solutions.llm_translation import _catalog_json

    committed = (HUSK_API / "static" / "llm-translation-targets.json").read_text()
    assert committed == _catalog_json(), (
        "static/llm-translation-targets.json is stale; regenerate it with "
        "_write_catalog_json() (see its docstring)")


def test_example_stub_is_not_registered_by_default():
    """SVC-8: the `example` stub (it reverses its input) was served on the public API."""
    p = _run_fresh(
        "import app.main\n"
        "from app.registry import get\n"
        "assert get('llm-translation') is not None\n"
        "assert get('example') is None, 'example registered without opt-in'\n")
    assert p.returncode == 0, p.stderr[-2000:]


def test_own_module_names_from_host_prefixed_go_module():
    """SVC-M1: real Go modules are host-prefixed (github.com/org/repo), and the
    check skipped every import whose first segment has a dot."""
    source = _GO_SOURCE.replace('"meterworks/internal/', '"github.com/acme/meterworks/internal/')
    assert own_module_names(source, ".go") >= {"meterworks"}
    husk = source.replace("api.NewServer", "svc.Build").replace("EnsureSeeded", "Prepare")
    with pytest.raises(PassthroughDetected) as exc:
        check(source, husk, ".go")
    assert exc.value.report["verdict"] == "module_name_leak"
    assert "meterworks" in exc.value.report["leaked_module_names"]


def test_large_honest_husk_skips_the_exact_ratio():
    """SVC-M2: the exact character ratio ran on every input up to 200k chars and
    cost seconds to minutes per attempt, even when its upper bound showed it
    could not reach the threshold."""
    source = "\n".join(f"def settle_claim_{i}(claim_{i}, payer_{i}):\n"
                       f"    return payer_{i}.remit(claim_{i}, {i})" for i in range(600))
    husk = (source.replace("settle_claim_", "queue_track_").replace("claim_", "song_")
            .replace("payer_", "listener_").replace(".remit(", ".stream("))
    with patch.object(difflib.SequenceMatcher, "ratio",
                      side_effect=AssertionError("exact ratio computed")):
        report = check(source, husk, ".py")
    assert report["verdict"] == "ok"
    assert report["similarity_ratio"] is None
    assert report["similarity_ratio_upper_bound"] < report["thresholds"]["ratio"]
    # Small inputs keep the exact figure.
    assert check(_SOURCE, _GOOD_HUSK, ".py")["similarity_ratio"] is not None
