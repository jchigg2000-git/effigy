"""HAR-3: transport failures in the attack stage.

Two defects, one mechanism. A transport failure used to spend §6.1's single parse
retry (an unusable answer after a 504 was scored a miss although the retry never
reached the model), and a resume treated any raw file on disk as done, so a call
that never reached the model stayed missing forever.

Offline: call_model_resilient is replaced by a per-item script of outcomes.
"""
import json
import threading

import run_rsch1

FC = '{"choice": 1, "confidence": 0.5}'


def _setup(tmp_path):
    truth = json.loads(run_rsch1.DOMAINS.read_text())["options"][0]["id"]
    art = tmp_path / "artifacts"
    art.mkdir()
    rows = []
    for item in ("A", "B"):
        key = f"dom__{item}.go__fpe__r0"
        (art / f"{key}.txt").write_text(f"package main // ITEM_{item}\n")
        (art / f"{key}.meta.json").write_text(json.dumps({
            "key": key, "arm": "fpe", "replicate": 0, "source_path": f"corpus/dom/{item}.go",
            "source_sha256": "0", "true_domain_id": truth, "language": "go"}))
        rows.append({"path": f"corpus/dom/{item}.go", "domain_dir": "dom"})
    return rows


def _scripted(monkeypatch, scripts):
    calls = {k: 0 for k in scripts}
    lock = threading.Lock()

    def fake(client, model, prompt, max_tokens, mode, transport_tries=5):
        item = "A" if "ITEM_A" in prompt else "B"
        with lock:
            calls[item] += 1
            outcome = scripts[item].pop(0)
        if outcome == "E":
            raise RuntimeError("InternalServerError: 504 gateway timeout")
        text = FC if outcome == "P" else "I think it is probably finance."
        return {"text": text, "finish_reason": "stop", "served_model": model,
                "latency_s": 0.0, "usage": None}

    monkeypatch.setattr(run_rsch1, "call_model_resilient", fake)
    return calls


def _raw(tmp_path):
    return {p.name.split("__")[1][0]: json.loads(p.read_text())
            for p in sorted((tmp_path / "raw").glob("*.json"))}


def test_transport_failures_neither_spend_the_retry_nor_stay_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("LLM_API_KEY", "offline-test")
    rows = _setup(tmp_path)

    def attack():
        run_rsch1.stage_attack(tmp_path, rows, ["atk/model"], "judge", ("fpe",), 1,
                               workers=2, dry=False, modes=("forced_choice",))

    # Pass 1. A: 504, then an unusable answer, and the §6.1 retry must still be
    # asked. B: an outage, nothing reaches the model.
    calls = _scripted(monkeypatch, {"A": ["E", "U", "P"], "B": ["E", "E"]})
    attack()
    raw = _raw(tmp_path)
    assert calls == {"A": 3, "B": 2}
    assert run_rsch1.responses(raw["A"]["attempts"]) == 2 and raw["A"]["parsed"]["choice"] == 1
    assert run_rsch1.responses(raw["B"]["attempts"]) == 0
    assert all(a["usage"] is None for a in raw["B"]["attempts"])

    # Pass 2, a healthy resume: B is asked again, A is final and left alone, and
    # the superseded record survives outside the raw/*.json glob.
    calls = _scripted(monkeypatch, {"A": [], "B": ["P"]})
    attack()
    raw = _raw(tmp_path)
    assert calls == {"A": 0, "B": 1}
    assert len(list((tmp_path / "raw").glob("*.json"))) == 2
    assert raw["B"]["parsed"]["choice"] == 1
    superseded = list((tmp_path / "raw_superseded").glob("*.json"))
    assert len(superseded) == 1
    assert raw["B"]["superseded"] == [f"raw_superseded/{superseded[0].name}"]
