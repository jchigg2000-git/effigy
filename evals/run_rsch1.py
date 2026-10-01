#!/usr/bin/env python3
"""RSCH-1 — adversarial source-domain re-identification. The runner.

Implements `evals/preregistration.md`. Read that first; this file is the
mechanism, the prereg is the contract, and where they disagree the prereg wins
and this is the bug.

Two stages, deliberately separable, because they fail differently and cost
differently:

    --stage artifacts   build every arm's artifact for every source file and
                        cache it under the run directory. The husk arm calls a
                        rewriter model 3x per source (§10) and is the slow,
                        flaky, expensive half.
    --stage attack      run the attacker panel over the cached artifacts. Pure
                        reads of the cache, so it can be re-run after a scoring
                        bug without paying for the husks again.
    --stage all         both.

Both stages are resumable: an artifact or a raw response already on disk is not
recomputed. That is not a convenience — §12 rule 3 requires a discarded run's
raw output to stay committed, so runs are append-only by construction. What a
resume does attempt again is what was never observed: an artifact that failed
for any reason other than a gate refusal, and an attacker call that never
reached the model or is still owed its §6.1 retry. The earlier record is moved
aside (`*.attemptN.error.json`, `raw_superseded/`), never overwritten, and
config.json keeps the first invocation's settings with later ones appended.

    python3 evals/run_rsch1.py --stage artifacts --split held-out
    python3 evals/run_rsch1.py --stage attack    --split held-out
    python3 evals/run_rsch1.py --stage all --split held-out --limit 2 --dry-run

API keys are never recorded: config.json stores the base-URL host and model id
only (§11).
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVALS = REPO / "evals"
MANIFEST = EVALS / "corpus" / "manifest.json"
DOMAINS = EVALS / "domains.json"
PROMPTS = EVALS / "prompts"
RUNS = EVALS / "runs"

sys.path.insert(0, str(EVALS))
sys.path.insert(0, str(REPO / "husk-api"))

import blind_stub  # noqa: E402

# Arms, in the order §3 tables them. "composed" is fpe(literal_tagging(src)),
# chained here rather than by the service — it is not a registered solution.
# `structure-only` / `structure-only-nonum` are RSCH-1B (amendment A4): the
# source with all AUTHORED vocabulary mechanically removed and the shape left
# exactly intact. They are not husk solutions and never touch the service — they
# answer whether the architecture the technique is REQUIRED to preserve is
# itself domain-informative. `-nonum` additionally indexes numeric literals.
DETERMINISTIC_ARMS = ("fpe", "literal-tagging", "composed",
                      "structure-only", "structure-only-nonum")
# `llm-translation-ungated` is the same rewriter with the shipped post-condition
# gate neutralised. It exists because the gate REFUSES passthrough husks, and a
# refusal removes that source file from the husk arm entirely — so p_husk would be
# measured only on the files the model happens to husk well. That is a selection
# effect running in the flattering direction, and this repo has already been burned
# by it once (evals/run_replicates.py disables the gate by default for exactly this
# reason). Running both arms turns the confound into a measurement: the gated arm is
# what a caller actually receives, the ungated arm says whether the refused files
# were the leaky ones.
STOCHASTIC_ARMS = ("llm-translation", "llm-translation-ungated")
ALL_ARMS = ("blind", "source", *DETERMINISTIC_ARMS, *STOCHASTIC_ARMS)

# Neutralises every threshold in app/solutions/_husk_check.py, same values
# evals/run_replicates.py uses so the two harnesses cannot drift apart.
#
# Never applied to this process's os.environ. _thresholds() reads the process
# environment at check time, so setting these from one worker thread switched the
# gate off for gated husks running in the others: 89 of 90 "gated" husks in run
# 20260819T182111Z were checked with the gate off. The ungated arm is built in a
# child process that gets these in its own environment instead, the way
# run_replicates.py already did it.
GATE_OFF = {"HUSK_CHECK_RUN_LINES": "999999", "HUSK_CHECK_RUN_SHARE": "9",
            "HUSK_CHECK_COPIED_SHARE": "9", "HUSK_CHECK_RETENTION": "9",
            "HUSK_CHECK_RATIO": "9", "HUSK_CHECK_RETRIES": "0",
            "HUSK_CHECK_MODULE_NAMES": "0"}


class GateStateMismatch(RuntimeError):
    """An llm-translation husk was not built under the gate its arm defines.

    A harness error, never a datum: the husk says nothing about the service under
    test, so it is recorded as an error, kept away from the attackers, and built
    again on resume.
    """

    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report or {}


class HuskChildError(RuntimeError):
    """A failure inside the ungated-arm child, carrying the child's exception type
    name so the error record reads the same as an in-process failure."""

    def __init__(self, type_name: str, message: str, report: dict | None = None):
        super().__init__(message)
        self.type_name = type_name
        self.report = report or {}


# ------------------------------------------------------------------ helpers --
def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=REPO, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def assert_no_map(meta: dict, where: str) -> None:
    """The landmine, restated from run_eval.py because this runner also calls
    husk() directly. fpe and literal_tagging put a pseudonym -> original map into
    meta when options.emit_map is set; persisting one would publish a full
    re-identification key for the corpus in a repo meant to be public."""
    if "reidentify_map" in meta:
        raise SystemExit(f"REFUSING TO WRITE {where}: meta contains 'reidentify_map'.")


def load_prompt(name: str) -> str:
    """Read a prompt file, dropping its leading HTML-comment design note.

    The notes exist so the next reader knows WHY each prompt is shaped the way it
    is, and they must never reach a model — a design note explaining that the
    menu is permuted to kill position bias is a hint.
    """
    text = (PROMPTS / name).read_text(encoding="utf-8")
    return re.sub(r"^\s*<!--.*?-->\s*", "", text, count=1, flags=re.S)


def solution_block(arm: str) -> str:
    """The per-arm disclosure from solution_blocks.md (§4, Kerckhoffs)."""
    body = load_prompt("solution_blocks.md")
    blocks = {}
    for chunk in re.split(r"^## ", body, flags=re.M)[1:]:
        head, _, rest = chunk.partition("\n")
        blocks[head.strip()] = rest.strip()
    # The ungated variant is the same algorithm to the attacker's eyes — it differs
    # only in a post-condition check the caller never sees — so it gets the same
    # disclosure. Telling the attacker which variant it holds would leak the answer
    # to a question the experiment is asking.
    key = "llm-translation" if arm == "llm-translation-ungated" else arm
    if key not in blocks:
        raise SystemExit(f"no solution block for arm '{arm}' in solution_blocks.md")
    return blocks[key]


# ----------------------------------------------------------------- corpus ----
def domain_split(man: dict) -> dict[str, str]:
    """Amendment A1: partition BY SOURCE DOMAIN, deterministically — sorted domain
    ids, alternating — so the partition cannot be quietly re-drawn to favour a
    result. By domain rather than by file because files within one domain are not
    independent observations, and a file-level split would leak the selection set
    into the held-out set."""
    ids = sorted({d["true_domain_id"] for d in man["domains"].values()
                  if isinstance(d, dict) and "true_domain_id" in d})
    return {d: ("selection" if i % 2 == 0 else "held-out") for i, d in enumerate(ids)}


def corpus_items(man: dict, split: str, limit: int | None) -> list[dict]:
    """One row per SOURCE FILE in the requested split, carrying its ground truth.

    Files outside the prereg §1 envelope (40-400 lines) are dropped here and the
    count is reported, because a silent drop reads as full coverage.
    """
    assign = domain_split(man)
    rows, out_of_envelope = [], 0
    for a in man["artifacts"]:
        dom = man["domains"][a["domain_dir"]]
        did = dom["true_domain_id"]
        if split != "all" and assign.get(did) != split:
            continue
        if not (40 <= a["lines"] <= 400):
            out_of_envelope += 1
            continue
        rows.append({
            "path": a["path"], "language": a["language"], "lines": a["lines"],
            "sha256": a["sha256"], "domain_dir": a["domain_dir"],
            "true_domain_id": did, "leak_terms": dom.get("leak_terms", []),
        })
    rows.sort(key=lambda r: r["path"])
    if out_of_envelope:
        print(f"  note: {out_of_envelope} artifact(s) dropped, outside the "
              f"40-400 line envelope (prereg §1)")
    return rows[:limit] if limit else rows


# -------------------------------------------------------------- artifacts ----
def call_model_resilient(client, model: str, prompt: str, max_tokens: int,
                        mode: str, transport_tries: int = 5) -> dict:
    """call_model, with backoff on TRANSPORT failures only.

    The distinction is methodological, not cosmetic. §6.1's "retry once, then
    score incorrect" governs an UNPARSEABLE MODEL RESPONSE — the model answered
    and the answer was unusable. A 429 or a 504 means the model was never asked
    at all, which this design already treats as a coverage gap rather than a
    wrong answer. So retrying transport errors changes coverage, never scoring,
    and it does not consume the §6.1 parse budget.

    Needed because the structure-only arms are slow: with no vocabulary to
    reason from, these models deliberate for 100-240s per call, and several
    concurrent requests at a 32000-token budget trip both the account's
    tokens-per-minute limit (429) and the router's gateway timeout (504).
    Retrying immediately, as the bare loop did, simply hit the same wall twice.
    """
    delay = 20.0
    last = None
    retries: list[str] = []
    waited = 0.0
    for i in range(transport_tries):
        try:
            resp = call_model(client, model, prompt, max_tokens, mode)
            # Record what it took to get here. Without this the retries are
            # invisible: a call that waited five minutes on 429 backoff looks
            # identical in the record to one that answered immediately, and the
            # run's own throughput becomes undiagnosable from its output.
            if retries:
                resp["transport_retries"] = retries
                resp["transport_wait_s"] = round(waited, 1)
            return resp
        except Exception as exc:  # noqa: BLE001
            name = type(exc).__name__
            transient = ("RateLimit" in name or "InternalServer" in name
                         or "APITimeout" in name or "APIConnection" in name
                         or "504" in str(exc) or "429" in str(exc))
            last = exc
            if not transient or i == transport_tries - 1:
                if retries:
                    raise RuntimeError(
                        f"{name} after {len(retries)} transport retries "
                        f"({waited:.0f}s waiting): {str(exc)[:200]}") from exc
                raise
            retries.append(f"{name}: {str(exc)[:60]}")
            print(f"[transport] {model.split('/')[-1]} {name}, backoff {delay:.0f}s "
                  f"(retry {i + 1}/{transport_tries - 1})", file=sys.stderr, flush=True)
            nap = delay + random.random() * 5
            time.sleep(nap)
            waited += nap
            delay = min(delay * 2, 180)
    raise last  # unreachable


class ParseFailureBreaker:
    """Abort a run that is failing to produce answers, before it spends the lot.

    Written after RSCH-1B's first attack stage burned 64 calls at a 48%
    unresolved rate against §8's 5% ceiling — an INCONCLUSIVE bought at full
    price. The cause (an attacker token budget too small for a vocabulary-free
    artifact) was diagnosable from the first dozen records; nothing about
    continuing to 240 made it clearer.

    Deliberately NOT set at §8's 5%. This is a runaway detector, not a verdict:
    the threshold is loose enough that an ordinary run never trips it, and a
    run that does trip it was never going to produce a usable result. A run that
    lands between the two is reported by score_rsch1.py as failing the validity
    gate, which is where that judgement belongs.

    Counts only calls this process actually made — cached records from a resumed
    run say nothing about current conditions.
    """

    def __init__(self, min_sample: int = 12, max_fail: float = 0.25):
        self._lock = threading.Lock()
        self.n = self.bad = 0
        self.min_sample, self.max_fail = min_sample, max_fail
        self.tripped = threading.Event()

    def record(self, ok: bool) -> None:
        with self._lock:
            self.n += 1
            self.bad += 0 if ok else 1
            if self.n >= self.min_sample and self.bad / self.n > self.max_fail:
                if not self.tripped.is_set():
                    print(f"\n[ABORT] {self.bad}/{self.n} calls produced no answer "
                          f"({self.bad / self.n:.0%} > {self.max_fail:.0%}). Stopping before this "
                          f"spends the full budget.\n"
                          f"        Check evals/runs/<run>/raw/*.json for the failure mode. If the "
                          f"attempts show finish_reason=length with empty text, the attacker's "
                          f"--max-tokens is too small for this arm; if they show 429/504, lower "
                          f"--workers.", file=sys.stderr, flush=True)
                self.tripped.set()


def build_artifact(arm: str, src: str, language: str, rep: int,
                   crumb_level: int, path: Path | None = None) -> tuple[str, dict]:
    """The bytes the attacker will see for one (source file, arm, replicate)."""
    if arm.startswith("structure-only"):
        # Deliberately BEFORE the app.registry import: this arm has no
        # dependency on the husk service at all.
        import canonicalize  # noqa: PLC0415

        if path is None:
            raise SystemExit("structure-only needs the source path")
        keep = arm != "structure-only-nonum"
        out, census = canonicalize.canonicalize(path, language, keep_numbers=keep)
        import tempfile  # noqa: PLC0415

        tmp = Path(tempfile.mkdtemp()) / path.name
        warn = canonicalize.gate(path, language, src, out, census, tmp, keep_numbers=keep)
        # The gate raises on any failure, so reaching here means the artifact is
        # leak-free and structurally identical. The census is published so
        # "what did you leave in?" is a table rather than an argument.
        return out, {"generated_by": "evals/canonicalize.py", **census, **warn}
    if arm == "blind":
        s = blind_stub.render(src, language)
        blind_stub.assert_content_free(s)   # a BLIND item that is not blind
        return s, {"generated_by": "evals/blind_stub.py"}                # invalidates everything
    if arm == "source":
        return src, {}

    from app.registry import get       # noqa: PLC0415
    import app.solutions               # noqa: F401,PLC0415  (registers the plugins)

    if arm == "composed":
        mid, m1 = get("literal-tagging").fn(src, crumb_level, {})
        assert_no_map(m1, "composed:literal-tagging")
        out, m2 = get("fpe").fn(mid, crumb_level, {})
        assert_no_map(m2, "composed:fpe")
        return out, {"chain": ["literal-tagging", "fpe"]}

    slug = "llm-translation" if arm == "llm-translation-ungated" else arm
    entry = get(slug)
    if entry is None:
        raise SystemExit(f"unknown solution: {slug}")
    if arm in STOCHASTIC_ARMS:
        out, meta = husk_under_gate(arm, entry, src, crumb_level)
    else:
        out, meta = entry.fn(src, crumb_level, {})
    assert_no_map(meta, f"{arm} rep{rep}")
    # meta carries the postcondition measurements and the chosen target; both are
    # wanted in the record, neither is sensitive.
    return out, {k: v for k, v in meta.items() if k != "reidentify_map"}


# ------------------------------------------------------------ gate state ----
# Run in a fresh interpreter, so the answer comes from the environment it is
# given rather than from whatever this process's environment holds. `retries`
# restates llm_translation.husk()'s own reading of HUSK_CHECK_RETRIES.
_GATE_PROBE = ("import json, os\n"
               "from app.solutions._husk_check import _thresholds\n"
               "print(json.dumps({'thresholds': _thresholds(), 'retries': "
               "max(0, int(os.environ.get('HUSK_CHECK_RETRIES', '1')))}))")
_gate_cache: dict[tuple, dict] = {}
_gate_lock = threading.Lock()


def gate_env(arm: str) -> dict[str, str]:
    """The environment an llm-translation arm's husks are built under."""
    env = dict(os.environ)
    if arm == "llm-translation-ungated":
        env.update(GATE_OFF)
    return env


def expected_gate(arm: str) -> dict:
    """The gate an llm-translation arm is defined by: the thresholds dict
    _husk_check._thresholds() returns under the arm's environment, and the
    post-condition retries llm_translation allows under it.

    The gated arm is the shipped gate. A HUSK_CHECK_* value in this process's
    environment (husk-api/.env is loaded first) that makes the gate differ from
    the shipped defaults would quietly make it something else, so that is refused
    rather than taken as the expectation. A value equal to its default is fine.
    """
    env = gate_env(arm)
    got = _probe_gate(env)
    if arm == "llm-translation":
        shipped = _probe_gate({k: v for k, v in os.environ.items()
                               if not k.startswith("HUSK_CHECK_")})
        if got != shipped:
            stray = sorted(k for k in os.environ if k.startswith("HUSK_CHECK_"))
            raise GateStateMismatch(
                f"{', '.join(stray)} set in this process's environment make the gate "
                f"{got}, not the shipped {shipped}: the gated arm would not be the "
                f"shipped gate. Unset them and re-run.")
    return got


def _probe_gate(env: dict[str, str]) -> dict:
    sig = tuple(sorted((k, v) for k, v in env.items() if k.startswith("HUSK_CHECK_")))
    with _gate_lock:
        if sig not in _gate_cache:
            p = subprocess.run([sys.executable, "-c", _GATE_PROBE], env=env,
                               cwd=REPO / "husk-api", capture_output=True, text=True)
            if p.returncode != 0:
                raise RuntimeError(f"gate probe failed: {p.stderr.strip()[-300:]}")
            _gate_cache[sig] = json.loads(p.stdout.strip().splitlines()[-1])
        return _gate_cache[sig]


def check_gate(arm: str, report: dict | None, expected: dict) -> None:
    """Fail closed unless the recorded post-condition matches the arm's gate.

    The whole thresholds dict is compared, not just run_lines: a key-by-key
    restore of the environment can leave a reader with half of each.
    """
    report = report if isinstance(report, dict) else {}
    got = report.get("thresholds")
    if got != expected["thresholds"]:
        raise GateStateMismatch(
            f"{arm} husk was checked under thresholds {got}, expected "
            f"{expected['thresholds']}", report)
    retries = report.get("retries_allowed")
    if retries is not None and retries != expected["retries"]:
        raise GateStateMismatch(
            f"{arm} husk allowed {retries} post-condition retries, expected "
            f"{expected['retries']}", report)


def husk_under_gate(arm: str, entry, src: str, crumb_level: int) -> tuple[str, dict]:
    """One llm-translation husk, built under its arm's gate and checked against it
    afterwards. Gated husks run in this process, whose environment nothing
    mutates; ungated husks run in a child process that has GATE_OFF in its own."""
    from app.solutions._husk_check import PassthroughDetected  # noqa: PLC0415

    expected = expected_gate(arm)
    try:
        if arm == "llm-translation-ungated":
            out, meta = _husk_in_child(src, crumb_level, gate_env(arm))
        else:
            out, meta = entry.fn(src, crumb_level, {})
    except PassthroughDetected as exc:
        # A refusal is itself evidence the gate was on; its thresholds, when the
        # report carries them, must still be the arm's.
        if isinstance(exc.report, dict) and "thresholds" in exc.report:
            check_gate(arm, exc.report, expected)
        raise
    check_gate(arm, meta.get("postcondition"), expected)
    return out, meta


def _husk_child_cmd() -> list[str]:
    """argv of the ungated-arm child. A function so the offline tests can start it
    through a launcher that stubs the model client first."""
    return [sys.executable, str(Path(__file__).resolve()), "--husk-child"]


def _husk_in_child(src: str, crumb_level: int, env: dict[str, str]) -> tuple[str, dict]:
    p = subprocess.run(_husk_child_cmd(), env=env, cwd=REPO, capture_output=True, text=True,
                       input=json.dumps({"src": src, "crumb_level": crumb_level}))
    lines = p.stdout.strip().splitlines()
    if p.returncode != 0 or not lines:
        raise RuntimeError(f"husk child exited {p.returncode}: {p.stderr.strip()[-300:]}")
    reply = json.loads(lines[-1])
    if reply["ok"]:
        return reply["out"], reply["meta"]
    if reply["type"] == "PassthroughDetected":
        # The ungated arm has no gate to refuse with. A refusal here means the
        # child was not running the arm it was asked for.
        raise GateStateMismatch(
            f"the ungated arm refused a husk: {reply['message'][:200]}", reply.get("report"))
    raise HuskChildError(reply["type"], reply["message"], reply.get("report"))


def husk_child_main() -> int:
    """Child side of _husk_in_child: one llm-translation husk under whatever
    environment the parent passed, reply as one JSON line on stdout."""
    job = json.loads(sys.stdin.read())
    real_stdout, sys.stdout = sys.stdout, sys.stderr  # nothing else may reach stdout
    try:
        from app.registry import get       # noqa: PLC0415
        import app.solutions               # noqa: F401,PLC0415

        out, meta = get("llm-translation").fn(job["src"], job["crumb_level"], {})
        reply = {"ok": True, "out": out, "meta": meta}
    except Exception as exc:  # noqa: BLE001 — the parent decides what it means
        reply = {"ok": False, "type": type(exc).__name__, "message": str(exc)[:2000],
                 "report": getattr(exc, "report", None)}
    finally:
        sys.stdout = real_stdout
    print(json.dumps(reply, default=str))
    return 0


def is_gate_refusal(meta: dict) -> bool:
    """An error record that is the gated arm refusing a husk: a §12 rule-3 datum
    about the service, kept as it is and not retried until it passes. Retrying
    refusals until they pass is the selection effect the ungated arm exists to
    expose. Records written before `error_type` existed carry the type as the
    prefix of `error`."""
    kind = meta.get("error_type") or str(meta.get("error", "")).split(":", 1)[0]
    return meta.get("arm") == "llm-translation" and kind == "PassthroughDetected"


def preserve_error_meta(art_dir: Path, k: str) -> str:
    """Move an error record aside before its artifact is attempted again.

    The new name does not match `*.meta.json`, which is the only artifact glob
    any reader uses, so the earlier attempt stays on disk without being read as
    the current one."""
    n = 1
    while (art_dir / f"{k}.attempt{n}.error.json").exists():
        n += 1
    name = f"{k}.attempt{n}.error.json"
    (art_dir / f"{k}.meta.json").rename(art_dir / name)
    return name


def stage_artifacts(outdir: Path, rows: list[dict], reps: int, crumb_level: int,
                    arms: tuple[str, ...], workers: int, dry: bool,
                    retry_refused: bool = False) -> None:
    art_dir = outdir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for r in rows:
        for arm in arms:
            n = reps if arm in STOCHASTIC_ARMS else 1
            for rep in range(n):
                jobs.append((r, arm, rep))

    # Before any husk is paid for: a gated arm that would not be the shipped
    # gate refuses the whole stage here, rather than failing one husk at a time.
    if not dry:
        for arm in (a for a in arms if a in STOCHASTIC_ARMS):
            try:
                expected_gate(arm)
            except GateStateMismatch as exc:
                raise SystemExit(f"REFUSING TO BUILD {arm}: {exc}") from exc

    def key(r: dict, arm: str, rep: int) -> str:
        stem = Path(r["path"]).name
        return f"{r['domain_dir']}__{stem}__{arm}__r{rep}"

    def work(job) -> dict:
        r, arm, rep = job
        k = key(r, arm, rep)
        dest = art_dir / f"{k}.txt"
        meta_dest = art_dir / f"{k}.meta.json"
        if dest.exists() and meta_dest.exists():
            return {"key": k, "ok": True, "cached": True}
        prior = json.loads(meta_dest.read_text()) if meta_dest.exists() else None
        if prior is not None and is_gate_refusal(prior) and not retry_refused:
            return {"key": k, "ok": False, "cached": True, "refused": True}
        if dry:
            return {"key": k, "ok": True, "cached": False, "dry": True}
        # Any other earlier failure (transport, harness, a gate-state mismatch) is
        # not an observation, so it is attempted again, with the record kept.
        prior_errors = ([preserve_error_meta(art_dir, k)]
                        if prior is not None and prior.get("error") else [])
        src = (REPO / r["path"]).read_text(encoding="utf-8")
        t0 = time.time()
        try:
            out, meta = build_artifact(arm, src, r["language"], rep, crumb_level,
                                       REPO / r["path"])
            dest.write_text(out, encoding="utf-8")
            meta_dest.write_text(json.dumps({
                "key": k, "arm": arm, "replicate": rep, "source_path": r["path"],
                "source_sha256": r["sha256"], "true_domain_id": r["true_domain_id"],
                "language": r["language"], "artifact_sha256": sha256_text(out),
                "artifact_lines": out.count("\n") + 1,
                "latency_s": round(time.time() - t0, 1), "solution_meta": meta,
                **({"prior_errors": prior_errors} if prior_errors else {}),
            }, indent=2) + "\n")
            return {"key": k, "ok": True, "cached": False}
        except Exception as exc:  # noqa: BLE001 — a failure is the datum
            # Recorded, not raised: §12 rule 3. A husk the rewriter refused is a
            # real observation about the service and must survive in the record.
            kind = getattr(exc, "type_name", type(exc).__name__)
            report = getattr(exc, "report", None)
            rec = {
                "key": k, "arm": arm, "replicate": rep, "source_path": r["path"],
                "error": f"{kind}: {str(exc)[:300]}", "error_type": kind,
                "latency_s": round(time.time() - t0, 1),
            }
            # A refused husk was still paid for. None when the service did not say.
            if isinstance(report, dict) and "usage" in report:
                rec["usage"] = report.get("usage")
            if prior_errors:
                rec["prior_errors"] = prior_errors
            meta_dest.write_text(json.dumps(rec, indent=2, default=str) + "\n")
            return {"key": k, "ok": False, "error": kind}

    print(f"[artifacts] {len(jobs)} to build ({len(rows)} sources x {len(arms)} arms, "
          f"stochastic arms x{reps})")
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(work, jobs))
    ok = sum(1 for r in res if r["ok"])
    cached = sum(1 for r in res if r.get("cached"))
    refused = sum(1 for r in res if r.get("refused"))
    print(f"[artifacts] {ok}/{len(res)} ok ({cached} already on disk, of which {refused} "
          f"kept gate refusals; {len(res) - ok} not built)")


# ----------------------------------------------------------------- attack ----
def build_menu(seed: int) -> tuple[str, list[dict]]:
    """12 options, permuted per item by a recorded seed (§6.1) to kill position
    bias. The seed is derived from the item id, so the permutation is a pure
    function of the item and any reader can regenerate it."""
    opts = json.loads(DOMAINS.read_text())["options"]
    perm = list(opts)
    random.Random(seed).shuffle(perm)
    text = "\n".join(f"{i + 1}. {o['label']} — {o['description']}"
                     for i, o in enumerate(perm))
    return text, perm


def parse_json_reply(text: str) -> dict | None:
    t = (text or "").strip()
    if t.startswith("```"):
        parts = t.split("```")
        t = parts[1] if len(parts) > 1 else t
        t = t.removeprefix("json").strip()
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        obj = json.loads(t[a:b + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


# Forced structured output. Every panel model supports it on the pinned provider,
# and `strict` keeps reasoning out of the content channel so what comes back is the
# object and nothing else.
SCHEMAS = {
    "forced_choice": {"type": "json_schema", "json_schema": {
        "name": "forced_choice", "strict": True, "schema": {
            "type": "object", "additionalProperties": False,
            "required": ["choice", "confidence"],
            "properties": {"choice": {"type": "integer"},
                           "confidence": {"type": "number"}}}}},
    "open_ended": {"type": "json_schema", "json_schema": {
        "name": "open_ended", "strict": True, "schema": {
            "type": "object", "additionalProperties": False,
            "required": ["domain", "specific_identifiers", "confidence", "evidence"],
            "properties": {"domain": {"type": "string"},
                           "specific_identifiers": {"type": "array",
                                                    "items": {"type": "string"}},
                           "confidence": {"type": "number"},
                           "evidence": {"type": "string"}}}}},
}


# §6.1's retry is decided on the schema's required keys, not on "any JSON
# object". Strict json_schema makes a keyless object near-impossible, but one
# would otherwise skip the retry and still be scored a parse failure.
REQUIRED_KEYS = {m: set(s["json_schema"]["schema"]["required"]) for m, s in SCHEMAS.items()}


def answered(parsed: dict | None, mode: str | None) -> bool:
    return parsed is not None and REQUIRED_KEYS.get(mode, set()) <= parsed.keys()


def responses(attempts: list[dict]) -> int:
    """Attempts the model actually answered. A transport failure carries no
    `text` (the same rule as score_rsch1.is_missing)."""
    return sum(1 for a in attempts if a.get("text") is not None)


def attack_done(rec: dict) -> bool:
    """Whether a raw record on disk is final, so a resume leaves it alone.

    Not final: a record the model never answered, where every attempt was a
    transport failure, and a record still owed its §6.1 retry, where the one
    answer was unusable and the retry never reached the model. Both are
    coverage the run has not yet bought, not observations.
    """
    return (answered(rec.get("parsed"), rec.get("mode"))
            or responses(rec.get("attempts") or []) >= 2)


def call_model(client, model: str, prompt: str, max_tokens: int,
               mode: str | None = None) -> dict:
    """One attacker call.

    `max_tokens` has to be generous and the reason is not obvious: on this router
    a reasoning model's INTERNAL deliberation is billed against max_tokens even
    when it never reaches the content channel. Measured on a BLIND item, which is
    the hardest case because the attacker has almost nothing to reason from: at
    3072 both panel attackers returned an EMPTY string with finish_reason=length,
    having spent the entire budget thinking. At 16000 the same call returns
    `{"choice": 1, "confidence": 0.2}` — a correct, appropriately unconfident
    answer. A tight budget here would not have produced a wrong answer; it would
    have produced a 29% parse-failure rate and tripped §8's validity gate, which
    would have read as an attacker-capability finding rather than a harness
    setting.
    """
    t0 = time.time()
    kw = {"response_format": SCHEMAS[mode]} if mode in SCHEMAS else {}
    r = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens, temperature=0, **kw,
    )
    return {
        "text": r.choices[0].message.content or "",
        "finish_reason": r.choices[0].finish_reason,
        "served_model": getattr(r, "model", None),
        "latency_s": round(time.time() - t0, 2),
        "usage": usage_fields(r),
    }


def usage_fields(resp) -> dict | None:
    """Token usage off one chat-completions response, as plain ints.

    None when the response carries no usage block, and a call that raised
    records None too: absence is not zero, since whether a failed request was
    billed is unknown. Every field is int-or-None, so an odd provider object
    (or a test double) can never make a record unserialisable. Shared by the
    other harness scripts that call a model directly.
    """
    u = getattr(resp, "usage", None)
    if u is None:
        return None

    def as_int(v):
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    details = getattr(u, "completion_tokens_details", None)
    return {"prompt_tokens": as_int(getattr(u, "prompt_tokens", None)),
            "completion_tokens": as_int(getattr(u, "completion_tokens", None)),
            "total_tokens": as_int(getattr(u, "total_tokens", None)),
            "reasoning_tokens": as_int(getattr(details, "reasoning_tokens", None))}


def refusal_usage(exc: BaseException) -> dict | None:
    """Tokens a refused husk was billed for, off the service's refusal report.

    None when the exception carries no report or the report carries no usage:
    absence is not zero. Shared by the scripts that call the rewriter directly.
    """
    report = getattr(exc, "report", None)
    return report.get("usage") if isinstance(report, dict) else None


def stage_attack(outdir: Path, rows: list[dict], attackers: list[str], judge: str,
                 arms: tuple[str, ...], reps: int, workers: int, dry: bool,
                 max_tokens: int = 16000,
                 modes: tuple[str, ...] = ("forced_choice", "open_ended"),
                 breaker: "ParseFailureBreaker | None" = None) -> None:
    from openai import OpenAI  # noqa: PLC0415

    base = os.environ["LLM_BASE_URL"]
    key = os.environ["LLM_API_KEY"]
    art_dir = outdir / "artifacts"
    raw_dir = outdir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    briefing_tpl = load_prompt("kerckhoffs.md")
    fc_tpl = load_prompt("forced_choice.md")
    oe_tpl = load_prompt("open_ended.md")

    by_id = {r["path"]: r for r in rows}
    items = []
    for meta_path in sorted(art_dir.glob("*.meta.json")):
        m = json.loads(meta_path.read_text())
        if m.get("error") or m["arm"] not in arms:
            continue
        if m["arm"] in STOCHASTIC_ARMS and m["replicate"] >= reps:
            continue
        src_row = by_id.get(m["source_path"])
        if src_row is None:
            continue
        items.append((m, src_row))

    jobs = [(m, r, atk, mode) for (m, r) in items for atk in attackers
            for mode in modes]
    print(f"[attack] {len(items)} items x {len(attackers)} attackers x "
          f"{len(modes)} mode(s) {modes} = {len(jobs)} calls")
    if dry:
        return

    def work(job) -> dict:
        m, row, attacker, mode = job
        item_id = f"{m['key']}"
        safe_atk = re.sub(r"[^A-Za-z0-9.-]+", "-", attacker)
        dest = raw_dir / f"{item_id}__{safe_atk}__{mode}.json"
        old = json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else None
        if old is not None and attack_done(old):
            return {"ok": True, "cached": True}
        if breaker is not None and breaker.tripped.is_set():
            return {"ok": False, "skipped": True}

        artifact = (art_dir / f"{m['key']}.txt").read_text(encoding="utf-8")
        briefing = briefing_tpl.replace("{solution_block}", solution_block(m["arm"]))
        label = ("A structural profile computed from the original file. No content."
                 if m["arm"] == "blind" else "One source file.")
        lang = "text" if m["arm"] == "blind" else m["language"]

        # Seed is a pure function of the item id — reproducible, and not choosable.
        seed = int(hashlib.sha256(item_id.encode()).hexdigest()[:8], 16)
        menu_text, perm = build_menu(seed)

        if mode == "forced_choice":
            prompt = (fc_tpl.replace("{briefing}", briefing)
                            .replace("{menu}", menu_text)
                            .replace("{artifact_label}", label)
                            .replace("{language}", lang)
                            .replace("{artifact}", artifact))
        else:
            prompt = (oe_tpl.replace("{briefing}", briefing)
                            .replace("{artifact_label}", label)
                            .replace("{language}", lang)
                            .replace("{artifact}", artifact))

        client = OpenAI(base_url=base, api_key=key, timeout=420)
        # A resumed record carries its earlier attempts forward, so an answer the
        # model already gave still counts against the single §6.1 retry.
        carried = old is not None and old.get("prompt") == prompt
        attempts = list(old.get("attempts") or []) if carried else []
        parsed = old.get("parsed") if carried else None
        # §6.1: unparseable responses are retried ONCE, then scored incorrect,
        # with the parse-failure rate reported separately. Only model RESPONSES
        # count against that; a transport failure (after call_model_resilient's
        # own backoff) has a budget of its own, so it can neither use up the
        # parse retry nor turn an unasked retry into a scored miss.
        n_resp, n_fail = responses(attempts), 0
        while n_resp < 2 and n_fail < 2:
            try:
                resp = call_model_resilient(client, attacker, prompt, max_tokens, mode)
            except Exception as exc:  # noqa: BLE001
                attempts.append({"attempt": len(attempts), "error":
                                 f"{type(exc).__name__}: {str(exc)[:300]}",
                                 "parsed_ok": False, "usage": None,
                                 "max_tokens": max_tokens})
                n_fail += 1
                continue
            n_resp += 1
            parsed = parse_json_reply(resp["text"])
            # max_tokens per attempt, because a resume can carry an earlier
            # invocation's attempts forward under a different budget.
            attempts.append({"attempt": len(attempts), **resp, "max_tokens": max_tokens,
                             "parsed_ok": answered(parsed, mode)})
            if answered(parsed, mode):
                break

        # Superseded, never overwritten: the earlier record moves outside the
        # raw/*.json glob every reader uses, and the new one points at it.
        superseded = []
        if old is not None:
            sup_dir = outdir / "raw_superseded"
            sup_dir.mkdir(exist_ok=True)
            n = 1
            while (sup_dir / f"{dest.stem}.{n}.json").exists():
                n += 1
            dest.rename(sup_dir / f"{dest.stem}.{n}.json")
            superseded = [*old.get("superseded", []), f"raw_superseded/{dest.stem}.{n}.json"]

        dest.write_text(json.dumps({
            "item_id": item_id, "arm": m["arm"], "replicate": m["replicate"],
            "source_path": m["source_path"], "source_sha256": m["source_sha256"],
            "true_domain_id": m["true_domain_id"], "domain_dir": row["domain_dir"],
            "attacker": attacker, "mode": mode,
            "menu_seed": seed,
            "menu_order": [o["id"] for o in perm],
            "truth_option": next((i + 1 for i, o in enumerate(perm)
                                  if o["id"] == m["true_domain_id"]), None),
            "prompt": prompt,          # §11: the FULL request, committed
            "attempts": attempts,      # §11: the FULL response, every attempt
            "parsed": parsed,
            # One unusable answer whose retry never reached the model. A resume
            # asks again; until then it scores as a parse failure.
            **({"retry_owed": True} if n_resp == 1 and not answered(parsed, mode) else {}),
            **({"superseded": superseded} if superseded else {}),
        }, indent=2) + "\n", encoding="utf-8")
        if breaker is not None:
            breaker.record(answered(parsed, mode))
        return {"ok": answered(parsed, mode), "cached": False}

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(work, jobs))
    cached = sum(1 for r in res if r.get("cached"))
    skipped = sum(1 for r in res if r.get("skipped"))
    asked = [r for r in res if not r.get("cached") and not r.get("skipped")]
    ok = sum(1 for r in asked if r["ok"])
    print(f"[attack] {ok}/{len(asked)} asked this run parsed ({cached} already final "
          f"on disk)")
    if skipped:
        print(f"[attack] ABORTED — {skipped} jobs skipped by the parse-failure breaker. "
              f"Fix the cause and resume with --run-id; completed records are cached.")
    print(f"[attack] judge stage is score_rsch1.py's job (judge={judge})")


# ------------------------------------------------------------------- main ----
# A resume that changes these would mix two experiments in one directory.
RESUME_REFUSES = ("split", "attackers")
# These legitimately change between invocations (a resume after a spend cap
# with fewer arms, a larger attacker budget, an added mode), so a change is
# warned about and recorded, not refused.
RESUME_WARNS = ("arms", "modes", "attacker_max_tokens", "replicates_llm_translation",
                "crumb_level", "judge", "source_files", "preregistration_commit",
                "manifest_sha256", "domains_sha256", "endpoint_host", "rewriter_model",
                "rewriter_temperature")


def write_or_extend_config(outdir: Path, config: dict, allow_drift: bool = False,
                           record: bool = True) -> dict:
    """Write config.json for a new run; on a resume, keep it and append.

    config.json used to be rewritten by every invocation, so a resumed run's
    started_at, commit, arms and attacker budget described the LAST resume
    rather than the records on disk (20260819T182111Z's config omits an arm it
    built and attacked). Now the first invocation's config is never changed, and
    each later invocation is appended to its `resumes` list with the fields that
    drifted. `record=False` (a dry run) checks a resume without appending it.
    """
    path = outdir / "config.json"
    if not path.exists():
        path.write_text(json.dumps(config, indent=2) + "\n")
        return config
    stored = json.loads(path.read_text())
    refused = [k for k in RESUME_REFUSES
               if stored.get(k) is not None and stored.get(k) != config.get(k)]
    if refused and not allow_drift:
        raise SystemExit(
            f"REFUSING TO RESUME {outdir.name}: {', '.join(refused)} differ from its "
            f"config.json ({', '.join(f'{k}={stored.get(k)!r}' for k in refused)}). "
            f"Start a new run, or pass --allow-config-drift to record the change.")
    drift = [k for k in (*RESUME_REFUSES, *RESUME_WARNS) if stored.get(k) != config.get(k)]
    if drift:
        print(f"WARNING: resuming {outdir.name} with {', '.join(drift)} different from the "
              f"first invocation; recorded in config.json 'resumes'", file=sys.stderr)
    entry = {k: v for k, v in config.items()
             if k not in ("run_id", "experiment", "domain_split", "source_files")}
    entry["drift"] = drift
    if refused:
        entry["drift_allowed"] = True
    if record:
        stored.setdefault("resumes", []).append(entry)
        path.write_text(json.dumps(stored, indent=2) + "\n")
    return stored


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("artifacts", "attack", "all"), default="all")
    ap.add_argument("--split", choices=("held-out", "selection", "all"),
                    default="held-out",
                    help="A1: the CONFIRMATORY run uses held-out only")
    ap.add_argument("--arms", default=",".join(ALL_ARMS))
    ap.add_argument("--replicates", type=int, default=3,
                    help="§10: llm-translation is not byte-stable, so 3 husks per source")
    ap.add_argument("--crumb-level", type=int, default=1)
    # Providers are PINNED with the `:provider` suffix. The router otherwise
    # load-balances one model id across 4-8 providers, and only some of them
    # support forced structured output. Pinning also stops a slow provider from
    # 504-ing a long generation midway through a run.
    ap.add_argument("--attackers",
                    default="moonshotai/Kimi-K3:baseten,"
                            "deepseek-ai/DeepSeek-V4-Pro-0813:baseten")
    ap.add_argument("--judge", default="zai-org/GLM-5.2:baseten")
    ap.add_argument("--modes", default="forced_choice,open_ended",
                    help="§6.1 forced_choice is the PRE-REGISTERED PRIMARY ENDPOINT; "
                         "§6.2 open_ended can only falsify C1, never support it, so it is "
                         "the half to drop first once C1 has already failed")
    ap.add_argument("--max-tokens", type=int, default=16000,
                    help="must cover INTERNAL reasoning tokens, not just the answer")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--breaker-min", type=int, default=12,
                    help="calls before the parse-failure breaker can trip")
    ap.add_argument("--breaker-max-fail", type=float, default=0.25,
                    help="unresolved fraction that aborts the run (§8's ceiling is 0.05; this is a "
                         "runaway detector, not a verdict)")
    ap.add_argument("--no-breaker", action="store_true",
                    help="disable the parse-failure breaker")
    ap.add_argument("--run-id", help="resume an existing run directory")
    ap.add_argument("--allow-config-drift", action="store_true",
                    help="resume even though --split or --attackers differ from the run's "
                         "config.json; the change is recorded in its 'resumes' list")
    ap.add_argument("--retry-refused", action="store_true",
                    help="build again the gated husks an earlier invocation saw refused. Off "
                         "by default: a refusal is a §12 datum, and retrying until a husk "
                         "passes is a selection effect. The refusal record is kept either way")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    from dotenv import load_dotenv  # noqa: PLC0415
    load_dotenv(REPO / "husk-api" / ".env")

    man = json.loads(MANIFEST.read_text())
    assign = domain_split(man)
    n_holdout = sum(1 for v in assign.values() if v == "held-out")
    print(f"domains: {len(assign)}  split: "
          + ", ".join(f"{d}={s}" for d, s in sorted(assign.items())))

    # §2 precondition and A1's power floor, checked BEFORE any money is spent.
    if len({d["true_domain_id"] for d in man["domains"].values()
            if isinstance(d, dict) and "true_domain_id" in d}) < 6:
        print("\nREFUSING TO RUN: prereg §2 requires K >= 6 source domains. Against a "
              "single-domain corpus an attacker that ignores its input and always "
              "answers that domain scores 100%, so no recovery rate measured here "
              "would be a property of the husk. Build the corpus first "
              "(corpus/DOMAINS.md).", file=sys.stderr)
        return 2
    if a.split == "held-out" and n_holdout < 3:
        print(f"\nWARNING: held-out split has {n_holdout} domains. A1: fewer than 3 "
              f"means the confirmatory run is reported INCONCLUSIVE on power "
              f"grounds regardless of its numbers.", file=sys.stderr)

    rows = corpus_items(man, a.split, a.limit)
    if not rows:
        print("no artifacts in split", file=sys.stderr)
        return 2
    arms = tuple(x.strip() for x in a.arms.split(",") if x.strip())
    attackers = [x.strip() for x in a.attackers.split(",") if x.strip()]

    if a.run_id:
        outdir = RUNS / a.run_id
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        outdir = RUNS / f"{stamp}-rsch1-{a.split}"
    outdir.mkdir(parents=True, exist_ok=True)

    config = {
        "run_id": outdir.name,
        "experiment": "RSCH-1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "split": a.split,
        "domain_split": assign,
        "arms": list(arms),
        "replicates_llm_translation": a.replicates,
        "crumb_level": a.crumb_level,
        "n_source_files": len(rows),
        "source_files": [r["path"] for r in rows],
        "attackers": attackers,
        "judge": a.judge,
        "attacker_temperature": 0,
        "attacker_max_tokens": a.max_tokens,
        "modes": [x.strip() for x in a.modes.split(",") if x.strip()],
        "response_format": "json_schema (strict)",
        "repo_git_commit": git("rev-parse", "HEAD"),
        "repo_dirty": bool(git("status", "--porcelain")),
        # §12 rule 4: every result table cites the prereg's commit SHA.
        "preregistration_commit": git("log", "-1", "--format=%H", "--",
                                      "evals/preregistration.md"),
        "manifest_sha256": sha256_text(MANIFEST.read_text()),
        "domains_sha256": sha256_text(DOMAINS.read_text()),
        # HOST only. Never the key. (§11)
        "endpoint_host": re.sub(r"^https?://", "",
                                os.environ.get("LLM_BASE_URL", "")).split("/")[0],
        "rewriter_model": os.environ.get("LLM_MODEL"),
        "rewriter_temperature": os.environ.get("LLM_TEMPERATURE"),
        "stage": a.stage,
    }
    write_or_extend_config(outdir, config, allow_drift=a.allow_config_drift,
                           record=not a.dry_run)
    print(f"run: {outdir.relative_to(REPO)}  sources={len(rows)}  arms={list(arms)}")

    if a.stage in ("artifacts", "all"):
        stage_artifacts(outdir, rows, a.replicates, a.crumb_level, arms,
                        a.workers, a.dry_run, a.retry_refused)
    if a.stage in ("attack", "all"):
        breaker = None if a.no_breaker else ParseFailureBreaker(a.breaker_min, a.breaker_max_fail)
        stage_attack(outdir, rows, attackers, a.judge, arms, a.replicates,
                     a.workers, a.dry_run, a.max_tokens,
                     tuple(x.strip() for x in a.modes.split(",") if x.strip()),
                     breaker)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--husk-child"]:
        raise SystemExit(husk_child_main())
    raise SystemExit(main())
