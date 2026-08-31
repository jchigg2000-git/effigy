import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_registered():
    r = client.get("/solutions")
    slugs = [s["slug"] for s in r.json()["solutions"]]
    assert "llm-translation" in slugs


def _mock_completion(text: str, prompt_tokens=10, completion_tokens=20):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def test_happy_path_returns_translated_code():
    fake = _mock_completion("class Pawn:\n    pass\n")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "class Customer:\n    pass\n",
            "crumb_level": 1,
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Pawn" in body["output"]
    assert body["meta"]["target_domain"]
    assert body["meta"]["model"]


def test_strips_code_fences():
    fake = _mock_completion("```python\nclass Pawn:\n    pass\n```")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    out = r.json()["output"]
    assert not out.startswith("```")
    assert "class Pawn" in out


def test_backend_unavailable_returns_502():
    from openai import APIConnectionError
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    assert r.status_code == 502
    assert r.json()["error"] == "backend_unavailable"


def test_target_domain_override():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {"target_domain": "a coffee-shop ordering system"},
        })
    assert r.status_code == 200
    assert r.json()["meta"]["target_domain"] == "a coffee-shop ordering system"


def test_target_id_selects_from_catalog():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {"target_id": "chess-engine"},
        })
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["target_id"] == "chess-engine"
    assert "chess" in body["meta"]["target_domain"].lower()


def test_unknown_target_id_returns_500():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {"target_id": "no-such-target"},
        })
    # The host wraps ValueError into a 500 solution_failed; see handoff 06
    # "Step 2 — Selection function" notes for why this is acceptable.
    assert r.status_code == 500
    assert r.json()["error"] == "solution_failed"
    assert "no-such-target" in r.json()["detail"]


def test_deterministic_default_is_stable_across_runs():
    fake = _mock_completion("output")
    targets = []
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        for _ in range(3):
            r = client.post("/husk/llm-translation", json={
                "input": "the same input twice",
                "crumb_level": 1,
            })
            targets.append((r.json()["meta"]["target_id"], r.json()["meta"]["target_domain"]))
    assert len(set(targets)) == 1
    assert targets[0][0] is not None  # default selection populates target_id


def test_free_text_override_clears_target_id():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {"target_domain": "a coffee-shop ordering system"},
        })
    body = r.json()
    assert body["meta"]["target_domain"] == "a coffee-shop ordering system"
    assert body["meta"]["target_id"] is None


def test_free_text_overrides_target_id_when_both_supplied():
    fake = _mock_completion("output")
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={
            "input": "x = 1",
            "crumb_level": 1,
            "options": {
                "target_id": "chess-engine",
                "target_domain": "a coffee-shop ordering system",
            },
        })
    body = r.json()
    assert body["meta"]["target_domain"] == "a coffee-shop ordering system"
    assert body["meta"]["target_id"] is None


def test_crumb_level_is_ignored_by_llm_translation():
    fake = _mock_completion("output")
    targets = []
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        for lvl in (0, 1, 2, 3):
            r = client.post("/husk/llm-translation", json={
                "input": "identical input",
                "crumb_level": lvl,
            })
            targets.append(r.json()["meta"]["target_id"])
    assert len(set(targets)) == 1  # all four levels produce the same default


def test_truncation_at_max_tokens_returns_500():
    # finish_reason == "length" means the response hit max_tokens. A bare
    # MagicMock attribute is truthy but != "length", so the production check
    # only fires when we set it explicitly here.
    fake = _mock_completion("class Pawn:\n    pass\n")
    fake.choices[0].finish_reason = "length"
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    assert r.status_code == 500
    assert r.json()["error"] == "solution_failed"
    detail = r.json()["detail"].lower()
    assert "truncat" in detail
    assert "llm_max_tokens" in detail


def test_empty_content_returns_500():
    fake = _mock_completion("")
    fake.choices[0].finish_reason = "stop"
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    assert r.status_code == 500
    assert r.json()["error"] == "solution_failed"
    assert "empty content" in r.json()["detail"].lower()


def test_none_content_returns_500():
    fake = _mock_completion(None)
    fake.choices[0].finish_reason = "stop"
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    assert r.status_code == 500
    assert r.json()["error"] == "solution_failed"
    assert "empty content" in r.json()["detail"].lower()


def test_whitespace_only_content_returns_500():
    fake = _mock_completion("   \n\t  ")
    fake.choices[0].finish_reason = "stop"
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = fake
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    assert r.status_code == 500
    assert r.json()["error"] == "solution_failed"
    assert "empty content" in r.json()["detail"].lower()


def test_api_status_error_includes_status_in_message():
    # APIStatusError subclasses APIError and carries .status_code; the
    # production code surfaces that status in the RuntimeError message.
    from openai import APIStatusError
    fake_response = MagicMock()
    fake_response.status_code = 429
    err = APIStatusError("rate limited by upstream", response=fake_response, body=None)
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.side_effect = err
        r = client.post("/husk/llm-translation", json={"input": "x = 1", "crumb_level": 1})
    assert r.status_code == 500
    assert r.json()["error"] == "solution_failed"
    detail = r.json()["detail"]
    assert "429" in detail
    assert "LLM API error" in detail


# --- post-condition: the service must not return the caller their own source ---
#
# Pins the fix for the silent-passthrough defect (LIMITATIONS.md §2). Thresholds
# are calibrated in evals/calibrate_postcondition.py; these assertions pin the
# BEHAVIOUR — refuse, retry, report — not the numbers.

_SOURCE = "\n".join(
    ["import json", "", "class ClaimBatch:", "    def __init__(self, payer_id: str):",
     "        self.payer_id = payer_id", "        self.rows = []", "",
     "    def add(self, row):", "        if not row:", "            return None",
     "        self.rows.append(row)", "        return len(self.rows)", "",
     "    def total(self):", "        n = 0", "        for r in self.rows:",
     "            n += r.get('amount', 0)", "        return n", "",
     "    def flush(self, sink):", "        for r in self.rows:", "            sink.write(json.dumps(r))",
     "        self.rows = []", "        return True"]
)
_GOOD_HUSK = _SOURCE.replace("ClaimBatch", "TrackQueue").replace("payer_id", "artist_id") \
    .replace("rows", "tracks").replace("amount", "duration").replace("sink", "player") \
    .replace("add", "enqueue").replace("total", "runtime").replace("flush", "drain")


def _post(*completions):
    """Drive /husk with a scripted sequence of model responses."""
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.side_effect = [
            _mock_completion(c) for c in completions]
        return client.post("/husk/llm-translation",
                           json={"input": _SOURCE, "crumb_level": 1})


def test_passthrough_is_refused_not_returned():
    """The defect itself: the model echoes the input and the service says 200 OK."""
    with patch.dict("os.environ", {"HUSK_CHECK_RETRIES": "0"}):
        r = _post(_SOURCE)
    assert r.status_code == 500, r.text
    detail = r.json()["detail"]
    assert "substantially its own input" in detail
    assert "consecutive code lines" in detail


def test_partial_passthrough_is_refused():
    """Half translated, half copied. Every whole-file measure calls this fine —
    it was found in real output scoring 0% domain-vocabulary retention."""
    half = _GOOD_HUSK.split("\n")[:10] + _SOURCE.split("\n")[10:]
    with patch.dict("os.environ", {"HUSK_CHECK_RETRIES": "0"}):
        r = _post("\n".join(half))
    assert r.status_code == 500, r.text
    assert "substantially its own input" in r.json()["detail"]


def test_genuine_husk_passes_and_reports_its_evidence():
    r = _post(_GOOD_HUSK)
    assert r.status_code == 200, r.text
    pc = r.json()["meta"]["postcondition"]
    assert pc["verdict"] == "ok"
    # The caller cannot run this comparison themselves — they do not have the
    # husker's view of both texts — so it travels with the response.
    assert pc["longest_identical_run"] >= 0
    assert "ident_retention" in pc and "similarity_ratio" in pc


def test_retry_recovers_a_passthrough():
    """A refusal should not become an outage when the transform is stochastic."""
    r = _post(_SOURCE, _GOOD_HUSK)
    assert r.status_code == 200, r.text
    meta = r.json()["meta"]
    assert meta["postcondition"]["verdict"] == "ok"
    assert len(meta["postcondition_retries"]) == 1
    assert "consecutive code lines" in meta["postcondition_retries"][0]["rejected"]


def test_tiny_input_is_never_refused():
    """Below a dozen lines, an honest husk and its input are similar for reasons
    that have nothing to do with passthrough. Refusing there breaks real use."""
    with patch("app.solutions.llm_translation.OpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create.return_value = _mock_completion("x = 1\ny = 2\n")
        r = client.post("/husk/llm-translation",
                        json={"input": "x = 1\ny = 2\n", "crumb_level": 1})
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["postcondition"]["verdict"] == "too_small_to_judge"


def test_distributed_copying_is_refused():
    """Copying does not have to be contiguous. A husk that returns a third of the
    input in many small spans evades a longest-run trigger — one real husk
    returned 66% of its source in spans of 5 to 14 lines and passed the gate as
    originally shipped."""
    src_lines = _SOURCE.split("\n")
    husk_lines = _GOOD_HUSK.split("\n")
    # Alternate 6 copied lines / 2 translated: no run long enough to trip the
    # run trigger, most of the file returned verbatim.
    mixed = []
    for i in range(0, len(src_lines), 8):
        mixed += src_lines[i:i + 6] + husk_lines[i + 6:i + 8]
    with patch.dict("os.environ", {"HUSK_CHECK_RETRIES": "0"}):
        r = _post("\n".join(mixed))
    assert r.status_code == 500, r.text
    assert "returned unchanged" in r.json()["detail"]


# --- own-module name survival (RSCH-1B) -----------------------------------
# Measured defect, not a hypothetical: in the RSCH-1 held-out run the Go module
# name survived 22 of 90 husks, and on those the adversary re-identified the
# source domain 44/44 = 100%. The system prompt already forbids it
# ("Imports of the input's OWN modules ARE renamed"), which is why the fix is a
# post-condition check rather than more prompt text.

_GO_SOURCE = """package main

import (
\t"context"
\t"net/http"

\t"meterworks/internal/api"
\t"meterworks/internal/ingest"
)

func run(ctx context.Context) error {
\tsrv := api.NewServer()
\tif err := ingest.EnsureSeeded(ctx); err != nil {
\t\treturn err
\t}
\treturn http.ListenAndServe(":8320", srv)
}
"""


def test_own_module_names_are_detected_from_go_imports():
    from app.solutions._husk_check import own_module_names

    assert own_module_names(_GO_SOURCE, ".go") == {"meterworks"}
    # Third-party and stdlib are never own-module.
    assert own_module_names('import (\n\t"net/http"\n\t"github.com/go-chi/chi/v5"\n)', ".go") == set()
    # Only Go: no other language exposes the module name in an import path.
    assert own_module_names(_GO_SOURCE, ".ts") == set()


def test_surviving_module_name_is_refused():
    from app.solutions._husk_check import PassthroughDetected, check

    husk = _GO_SOURCE.replace("api.NewServer", "svc.Build").replace("EnsureSeeded", "Prepare")
    with pytest.raises(PassthroughDetected) as exc:
        check(_GO_SOURCE, husk, ".go")
    assert exc.value.report["verdict"] == "module_name_leak"
    assert exc.value.report["leaked_module_names"] == ["meterworks"]


def test_renamed_module_passes():
    """Must not fire when the rewriter did its job. The similarity triggers are
    neutralised so this asserts the module rule alone — otherwise a
    near-identical pair trips passthrough first and proves nothing about it."""
    from app.solutions._husk_check import check

    husk = _GO_SOURCE.replace("meterworks", "widgets")
    with patch.dict("os.environ", {"HUSK_CHECK_RUN_LINES": "999999", "HUSK_CHECK_RUN_SHARE": "9",
                                   "HUSK_CHECK_COPIED_SHARE": "9", "HUSK_CHECK_RETENTION": "9"}):
        assert check(_GO_SOURCE, husk, ".go")["leaked_module_names"] == []


def test_module_name_check_is_disablable():
    """Symmetry with the other triggers: an operator can turn it off knowingly."""
    from app.solutions._husk_check import check

    husk = _GO_SOURCE.replace("api.NewServer", "svc.Build")
    with patch.dict("os.environ", {"HUSK_CHECK_MODULE_NAMES": "0",
                                   "HUSK_CHECK_RUN_LINES": "999999",
                                   "HUSK_CHECK_RUN_SHARE": "9",
                                   "HUSK_CHECK_COPIED_SHARE": "9",
                                   "HUSK_CHECK_RETENTION": "9"}):
        assert check(_GO_SOURCE, husk, ".go")["leaked_module_names"] == []
