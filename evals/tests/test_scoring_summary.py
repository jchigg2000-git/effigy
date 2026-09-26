"""score_rsch1 regression tests on small synthetic runs: no network, no committed run touched.

Each test builds a run directory in tmp_path with the fields score_rsch1 reads, scores it with
--no-judge (or calls one helper directly), and checks the one figure its finding is about.
"""
import json
import sys
from types import SimpleNamespace

import score_rsch1

DOMS = ("ham-radio-logbook", "seismic-monitoring", "water-utility-metering")
# One real leak term per domain (evals/corpus/manifest.json), for the §4.1 veto.
LEAK = {"ham-radio-logbook": "ham radio", "seismic-monitoring": "seismic",
        "water-utility-metering": "water meter"}
MENU = [*DOMS, "recipe-manager", "hotel-booking"]


def _files(doms=DOMS, per=10):
    return [(f"corpus/{d}/f{i}.go", d) for d in doms for i in range(per)]


def fc(arm, src, dom, outcome, atk="a/A"):
    """One forced-choice record; outcome is right | wrong | unparseable | missing."""
    truth = MENU.index(dom) + 1
    wrong = next(i + 1 for i, d in enumerate(MENU) if d != dom)
    if outcome == "missing":
        attempts, parsed = [{"attempt": 0, "error": "403"}], None
    elif outcome == "unparseable":
        attempts, parsed = [{"attempt": 0, "text": "", "finish_reason": "length"}], None
    else:
        choice = truth if outcome == "right" else wrong
        attempts = [{"attempt": 0, "text": "{}", "finish_reason": "stop"}]
        parsed = {"choice": choice, "confidence": 0.9}
    return {"item_id": f"{src.replace('/', '_')}__{arm}__r0", "arm": arm, "replicate": 0,
            "source_path": src, "true_domain_id": dom, "attacker": atk, "mode": "forced_choice",
            "menu_seed": 0, "menu_order": MENU, "truth_option": truth, "attempts": attempts,
            "parsed": parsed}


def oe(arm, src, dom, guess, atk="a/A"):
    return {"item_id": f"{src.replace('/', '_')}__{arm}__r0", "arm": arm, "replicate": 0,
            "source_path": src, "true_domain_id": dom, "attacker": atk, "mode": "open_ended",
            "attempts": [{"attempt": 0, "text": "{}"}],
            "parsed": {"domain": guess, "specific_identifiers": [], "evidence": ""}}


def score(tmp_path, monkeypatch, recs, arms, metas=(), attackers=("a/A",)):
    (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(recs):
        (tmp_path / "raw" / f"{i:04d}__{r['mode']}.json").write_text(json.dumps(r))
    for m in metas:
        (tmp_path / "artifacts").mkdir(exist_ok=True)
        (tmp_path / "artifacts" / f"{m['key']}.meta.json").write_text(json.dumps(m))
    (tmp_path / "config.json").write_text(json.dumps({
        "run_id": "synthetic", "split": "held-out", "n_source_files": 30,
        "preregistration_commit": "x", "repo_git_commit": "x", "attackers": list(attackers),
        "judge": "j/J", "arms": list(arms), "modes": ["forced_choice", "open_ended"]}))
    monkeypatch.setattr(sys, "argv", ["score_rsch1.py", str(tmp_path), "--no-judge"])
    assert score_rsch1.main() == 0
    return (tmp_path / "summary.md").read_text()


def row(summary, section, arm):
    body = summary.split(section, 1)[1]
    return next(line for line in body.splitlines() if line.startswith(f"| `{arm}` |"))


def arm_b(src_right=30, blind_right=9, fpe_right=15, doms=DOMS):
    """source / blind / fpe forced-choice records with the given number right per arm."""
    recs = []
    for arm, k in (("source", src_right), ("blind", blind_right), ("fpe", fpe_right)):
        recs += [fc(arm, s, d, "right" if i < k else "wrong")
                 for i, (s, d) in enumerate(_files(doms))]
    return recs


def test_2b_states_when_its_n_excludes_unparseable_records(tmp_path, monkeypatch):
    # STAT-2 / HAR-8: A4.1 drops answered-but-unparseable records, §2 scores them incorrect.
    recs = arm_b()
    recs[30 + 1] = fc("blind", *_files()[1], "unparseable")
    recs[30 + 2] = fc("blind", *_files()[2], "missing")
    summary = score(tmp_path, monkeypatch, recs, ["source", "blind", "fpe"])
    cell = json.loads((tmp_path / "permutation.json").read_text())["cells"]["blind|a/A"]
    assert cell["n"] == 28  # the registered drop rule is unchanged
    assert "n excludes 1 answered-but-unparseable record that §2 scores incorrect " \
           "(28 here, 29 in §2)" in summary


def test_mechanism_buckets_skip_transport_failures():
    # STAT-3: a call that never reached the model is neither a right nor a wrong answer.
    src, dom = _files()[0]
    recs = [fc("fpe", src, dom, o) for o in ("right", "unparseable", "missing")]
    b = score_rsch1.mechanism_buckets(recs, lambda item_id, path: 0.5)
    assert (len(b["fpe"]["hit"]), len(b["fpe"]["miss"])) == (1, 1)


def test_coverage_counts_unwritten_jobs_and_absent_source_is_not_evaluated(tmp_path, monkeypatch):
    # STAT-5: 2 files x {source, fpe} artifacts, only the fpe calls written.
    files = _files(per=1)[:2]
    metas = [{"key": f"{s.replace('/', '_')}__{arm}__r0", "arm": arm, "replicate": 0,
              "source_path": s} for s, _ in files for arm in ("source", "fpe")]
    recs = [fc("fpe", s, d, "right") for s, d in files]
    summary = score(tmp_path, monkeypatch, recs, ["source", "fpe"], metas=metas)
    # forced choice and open ended are both configured: 2 arms x 2 files x 2 modes = 8
    assert "COVERAGE: 2/8 expected calls have a model answer" in summary
    assert "| `source` | `A` | forced_choice | 0/2 | 2 | 0 |" in summary
    gate = summary.split("## 1.", 1)[1].split("## 2.", 1)[0]
    assert "NOT EVALUATED" in gate and "GATE FAILED" not in gate


def test_hard_veto_reaches_verdict_only_when_gate_passes(tmp_path, monkeypatch):
    # STAT-7: Arm B alone is INCONCLUSIVE (15/30 vs blind 9/30); 30% of guesses hit a leak term.
    guesses = [oe("fpe", s, d, LEAK[d] if i % 10 < 3 else "a recipe app")
               for i, (s, d) in enumerate(_files())]
    summary = score(tmp_path / "pass", monkeypatch, arm_b() + guesses, ["source", "blind", "fpe"])
    assert row(summary, "## 3. Verdicts", "fpe").endswith("| **FAIL** (hard veto, Arm A) |")

    summary = score(tmp_path / "fail", monkeypatch, arm_b(src_right=15) + guesses,
                    ["source", "blind", "fpe"])
    assert row(summary, "## 3. Verdicts", "fpe").endswith("| INCONCLUSIVE — validity gate failed |")
    assert row(summary, "### 4.1", "fpe").endswith("| not issued (gate failed) |")
    assert "Hard veto fired" not in summary


def test_a1_fewer_than_three_domains_is_inconclusive(tmp_path, monkeypatch):
    # STATS-M1: a clear Arm B FAIL on 2 domains is INCONCLUSIVE under A1; 3 domains still FAIL.
    summary = score(tmp_path / "two", monkeypatch,
                    arm_b(src_right=20, blind_right=6, fpe_right=20, doms=DOMS[:2]),
                    ["source", "blind", "fpe"])
    verdict = row(summary, "## 3. Verdicts", "fpe")
    assert "INCONCLUSIVE — A1" in verdict and "**FAIL**" not in verdict

    summary = score(tmp_path / "three", monkeypatch, arm_b(fpe_right=30),
                    ["source", "blind", "fpe"])
    assert row(summary, "## 3. Verdicts", "fpe").endswith("| **FAIL** |")


def test_gated_arm_built_with_gate_off_is_flagged(tmp_path, monkeypatch):
    # SVC-1 item 3: the gated arm's recorded thresholds show whether the gate really ran.
    # As recorded in 20260819T182111Z: run_rsch1.GATE_OFF, read back by _husk_check.
    off = {"run_lines": 999999, "run_share": 9.0, "copied_share": 9.0, "retention": 9.0,
           "ratio": 9.0, "min_code_lines": 12}
    live = {"run_lines": 20, "run_share": 0.15, "copied_share": 0.35, "retention": 0.92,
            "ratio": 0.95, "min_code_lines": 12}
    metas = [{"key": f"f{i}__llm-translation__r0", "arm": "llm-translation", "replicate": 0,
              "source_path": s,
              "solution_meta": {"postcondition": {"thresholds": off if i < 3 else live}}}
             for i, (s, _) in enumerate(_files(per=2)[:4])]
    summary = score(tmp_path, monkeypatch, arm_b(), ["source", "blind", "fpe", "llm-translation"],
                    metas=metas)
    assert "GATE STATE DOES NOT MATCH THE ARM" in summary
    assert "3/4 `llm-translation` artifacts were built with the post-condition gate OFF" in summary


def test_judge_records_usage_and_cost_table_degrades(tmp_path, monkeypatch):
    # HAR-5: judge payloads carry int-or-None usage; runs without usage say so.
    import dotenv
    import openai

    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15,
                            completion_tokens_details=SimpleNamespace(reasoning_tokens=object()))

    class Client:
        def __init__(self, **kw):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, messages, **kw):
            if "BOOM" in messages[0]["content"]:
                raise RuntimeError("503")
            msg = SimpleNamespace(content='{"label": "MATCH", "reason": "r"}')
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=usage)

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(openai, "OpenAI", Client)
    monkeypatch.setenv("LLM_BASE_URL", "http://stub.invalid")
    monkeypatch.setenv("LLM_API_KEY", "stub")
    src, dom = _files()[0]
    recs = [oe("fpe", src, dom, "a guess", atk="a/A"), oe("fpe", src, dom, "BOOM", atk="b/B")]

    judged = score_rsch1.run_judge(tmp_path, recs, "j/J")
    by_atk = {p["attacker"]: p for p in judged.values()}
    assert by_atk["a/A"]["usage"] == {"prompt_tokens": 10, "completion_tokens": 5,
                                      "total_tokens": 15, "reasoning_tokens": None}
    assert by_atk["b/B"]["usage"] is None
    for f in (tmp_path / "judge").glob("*.json"):
        json.loads(f.read_text())  # serialisable, nothing but ints and None

    assert "| `J (judge)` | `all arms` | 1/2 | 10 | 5 | 0 | 15 |" in \
        "\n".join(score_rsch1.usage_table(recs, judged, "j/J"))
    assert "No usage recorded" in "\n".join(score_rsch1.usage_table(recs))


def test_arm_listed_only_in_a_resume_is_still_scored(tmp_path, monkeypatch):
    # write_or_extend_config keeps the first invocation's `arms` and appends a resume that
    # added `fpe` to `resumes`. The arm must reach §2 and §3, not only the coverage banner.
    summary = score(tmp_path, monkeypatch, arm_b(), arms=("source", "blind"))
    cfg = json.loads((tmp_path / "config.json").read_text())
    cfg["resumes"] = [{"arms": ["source", "blind", "fpe"], "drift": ["arms"]}]
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    monkeypatch.setattr(sys, "argv", ["score_rsch1.py", str(tmp_path), "--no-judge"])
    assert score_rsch1.main() == 0
    summary = (tmp_path / "summary.md").read_text()
    assert "ARMS NOT IN config.json's top level: `fpe`" in summary
    assert row(summary, "## 2.", "fpe")
    assert row(summary, "## 3.", "fpe")
