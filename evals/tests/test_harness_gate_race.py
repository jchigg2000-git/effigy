"""HAR-1 / SVC-1: the ungated arm must not switch the gate off for the gated arm.

run_rsch1 used to set GATE_OFF in os.environ from inside its worker threads while
building `llm-translation-ungated`. `_husk_check._thresholds()` reads the process
environment at check time, so gated husks running in other threads were checked
with the gate off (89/90 in run 20260819T182111Z), and overlapping restores left
GATE_OFF set in the process afterwards.

Offline: the model client is replaced by an echo that returns the source verbatim
after a short sleep. That is a passthrough the shipped gate must refuse, so the
arm a husk was really built under is visible in whether it was refused.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import run_rsch1

SRC_PATH = run_rsch1.REPO / "corpus" / "tremorline" / "api" / "cmd" / "tremorlined" / "main.go"

ECHO_STUB = '''
import random
import time
from types import SimpleNamespace

SRC = open({src!r}, encoding="utf-8").read()


class Echo:
    """Stands in for openai.OpenAI: no network, returns the source unchanged."""

    def __init__(self, *args, **kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        time.sleep(random.uniform(0.005, 0.03))
        choice = SimpleNamespace(message=SimpleNamespace(content=SRC), finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=None, model="echo")

    def close(self):
        pass
'''

# The ungated arm is built in a child process, which the in-process monkeypatch
# cannot reach, so the child is started through this launcher instead: same
# stub, then the real child entry point.
LAUNCHER = '''
import sys
sys.path[:0] = [{stub_dir!r}, {evals!r}, {husk_api!r}]
import echo_stub
import app.solutions.llm_translation as L
L.OpenAI = echo_stub.Echo
import run_rsch1
raise SystemExit(run_rsch1.husk_child_main())
'''


def test_gate_state_follows_the_arm_under_six_threads(tmp_path, monkeypatch):
    for k in run_rsch1.GATE_OFF:
        monkeypatch.delenv(k, raising=False)
    # Belt and braces: even if a stub failed to install, nothing leaves the host.
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("LLM_API_KEY", "offline-test")

    (tmp_path / "echo_stub.py").write_text(ECHO_STUB.format(src=str(SRC_PATH)))
    monkeypatch.syspath_prepend(str(tmp_path))
    import echo_stub
    import app.solutions.llm_translation as llm
    from app.solutions._husk_check import PassthroughDetected

    monkeypatch.setattr(llm, "OpenAI", echo_stub.Echo)
    launcher = tmp_path / "launcher.py"
    launcher.write_text(LAUNCHER.format(stub_dir=str(tmp_path), evals=str(run_rsch1.EVALS),
                                        husk_api=str(run_rsch1.REPO / "husk-api")))
    monkeypatch.setattr(run_rsch1, "_husk_child_cmd",
                        lambda: [sys.executable, str(launcher)], raising=False)

    src = SRC_PATH.read_text(encoding="utf-8")
    jobs = [("llm-translation" if i % 2 == 0 else "llm-translation-ungated", i // 2)
            for i in range(12)]

    def build(job):
        arm, rep = job
        try:
            return arm, run_rsch1.build_artifact(arm, src, "go", rep, 1, SRC_PATH)
        except Exception as exc:  # noqa: BLE001
            return arm, exc

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(build, jobs))

    gated = [r for arm, r in results if arm == "llm-translation"]
    ungated = [r for arm, r in results if arm == "llm-translation-ungated"]
    assert all(isinstance(r, PassthroughDetected) for r in gated), \
        [repr(r)[:160] for r in gated]
    for r in ungated:
        assert isinstance(r, tuple), repr(r)[:300]
        thresholds = r[1]["postcondition"]["thresholds"]
        assert thresholds["run_lines"] == 999999 and thresholds["module_names"] is False
        assert thresholds == run_rsch1.expected_gate("llm-translation-ungated")["thresholds"]
    assert not [k for k in os.environ if k.startswith("HUSK_CHECK_")]


def test_gated_arm_accepts_default_values_and_refuses_real_overrides(monkeypatch):
    # husk-api/.env is loaded before the gate is checked, and .env.example lists the
    # HUSK_CHECK_* knobs at their defaults. A default value must not read as a stray
    # override; a value that changes the gate must.
    import pytest

    for k in list(os.environ):
        if k.startswith("HUSK_CHECK_"):
            monkeypatch.delenv(k)
    run_rsch1._gate_cache.clear()
    monkeypatch.setenv("HUSK_CHECK_RETRIES", "1")
    monkeypatch.setenv("HUSK_CHECK_MODULE_NAMES", "1")
    shipped = run_rsch1.expected_gate("llm-translation")
    assert shipped["thresholds"] != run_rsch1.expected_gate("llm-translation-ungated")["thresholds"]
    monkeypatch.setenv("HUSK_CHECK_RUN_LINES", "999999")
    with pytest.raises(run_rsch1.GateStateMismatch):
        run_rsch1.expected_gate("llm-translation")
