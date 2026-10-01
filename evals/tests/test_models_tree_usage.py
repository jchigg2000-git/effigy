"""run_models.py and husk_tree.py persist the rewriter's token usage.

Both called the service and threw its meta away, so a sweep's cost was unrecoverable from its
own records. A refusal was billed too: its usage rides on the exception's report.
"""
import json
import sys

import app.solutions.llm_translation as llm
import husk_tree
import run_models

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "reasoning_tokens": None}


def _refusal(usage):
    exc = RuntimeError("passthrough")
    exc.report = {"usage": usage}
    return exc


def _art(tmp_path):
    src = tmp_path / "a.go"
    src.write_text("package a\n")
    return {"path": str(src), "domain_dir": "d", "language": "go", "sha256": "x", "lines": 1}


def test_run_models_records_usage_on_success_and_refusal(tmp_path, monkeypatch):
    art = _art(tmp_path)
    monkeypatch.setattr(llm, "husk", lambda *a, **k: ("", {"usage": USAGE}))
    assert run_models.evaluate_case("m", art)["usage"] == USAGE

    def refuse(*a, **k):
        raise _refusal(USAGE)
    monkeypatch.setattr(llm, "husk", refuse)
    assert run_models.evaluate_case("m", art)["usage"] == USAGE

    monkeypatch.setattr(llm, "husk", lambda *a, **k: ("", {}))
    assert run_models.evaluate_case("m", art)["usage"] is None

    def boom(*a, **k):
        raise ValueError("no report")
    monkeypatch.setattr(llm, "husk", boom)
    assert run_models.evaluate_case("m", art)["usage"] is None


def test_husk_tree_records_usage_per_file(tmp_path, monkeypatch):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    (src / "ok.go").write_text("package a\n")
    (src / "bad.go").write_text("package b\n")

    def fake(text, _n, _opts):
        if "package b" in text:
            raise _refusal(USAGE)
        return "package x\n", {"usage": USAGE}
    monkeypatch.setattr(llm, "husk", fake)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["husk_tree.py", "--model", "m", "--target", "t",
                                      "--src", str(src), "--out", str(out), "--workers", "1"])
    assert husk_tree.main() == 1
    files = {r["dest"]: r for r in json.loads((out / "_husk_manifest.json").read_text())["files"]}
    assert files["ok.go"]["usage"] == USAGE and files["ok.go"]["ok"]
    assert files["bad.go"]["usage"] == USAGE and not files["bad.go"]["ok"]
