"""HAR-4 / STAT-6: a resume must not overwrite what an earlier invocation recorded.

config.json used to be rewritten by every invocation, so a resumed run's commit,
start time and arms described the last resume rather than the records on disk. And
an errored artifact was retried with its error record overwritten, which erased
gated refusals, a §12 rule-3 datum.
"""
import json

import pytest

import run_rsch1


def _config(commit: str, started: str, **over) -> dict:
    return {"run_id": "r", "experiment": "RSCH-1", "started_at": started, "split": "held-out",
            "arms": ["blind", "llm-translation"], "attackers": ["a", "b"],
            "attacker_max_tokens": 16000, "modes": ["forced_choice"],
            "repo_git_commit": commit, "repo_dirty": False, **over}


def test_resume_keeps_the_first_config_and_appends_the_resume(tmp_path, capsys):
    run_rsch1.write_or_extend_config(tmp_path, _config("aaa", "t0"))
    run_rsch1.write_or_extend_config(
        tmp_path, _config("bbb", "t1", arms=["llm-translation-ungated"], attacker_max_tokens=32000))
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert (cfg["repo_git_commit"], cfg["started_at"], cfg["arms"]) == \
        ("aaa", "t0", ["blind", "llm-translation"])
    assert [r["repo_git_commit"] for r in cfg["resumes"]] == ["bbb"]
    assert cfg["resumes"][0]["drift"] == ["arms", "attacker_max_tokens"]
    assert "WARNING" in capsys.readouterr().err

    # A different attacker panel is a different experiment: refused, and nothing
    # is appended unless the drift is explicitly allowed.
    with pytest.raises(SystemExit):
        run_rsch1.write_or_extend_config(tmp_path, _config("ccc", "t2", attackers=["z"]))
    assert len(json.loads((tmp_path / "config.json").read_text())["resumes"]) == 1


def test_resume_keeps_refusals_and_preserves_retried_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("LLM_API_KEY", "offline-test")
    for k in run_rsch1.GATE_OFF:
        monkeypatch.delenv(k, raising=False)
    import app.solutions.llm_translation as llm

    class NoModel:
        def __init__(self, *a, **kw):
            raise AssertionError("a kept refusal must not be husked again")

    monkeypatch.setattr(llm, "OpenAI", NoModel)

    path = "corpus/tremorline/api/cmd/tremorlined/main.go"
    row = {"path": path, "language": "go", "sha256": "0", "domain_dir": "tremorline",
           "true_domain_id": "x"}
    art = tmp_path / "artifacts"
    art.mkdir()
    refusal = {"key": "tremorline__main.go__llm-translation__r0", "arm": "llm-translation",
               "replicate": 0, "source_path": path,
               "error": "PassthroughDetected: husk rejected: 14 consecutive code lines"}
    transport = {"key": "tremorline__main.go__source__r0", "arm": "source", "replicate": 0,
                 "source_path": path, "error": "APIConnectionError: connection reset"}
    for rec in (refusal, transport):
        (art / f"{rec['key']}.meta.json").write_text(json.dumps(rec))

    run_rsch1.stage_artifacts(tmp_path, [row], 1, 1, ("source", "llm-translation"),
                              workers=2, dry=False)

    assert json.loads((art / f"{refusal['key']}.meta.json").read_text()) == refusal
    rebuilt = json.loads((art / f"{transport['key']}.meta.json").read_text())
    assert "error" not in rebuilt
    assert rebuilt["prior_errors"] == [f"{transport['key']}.attempt1.error.json"]
    assert json.loads((art / rebuilt["prior_errors"][0]).read_text()) == transport
