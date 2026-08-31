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
raw output to stay committed, so runs are append-only by construction.

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
GATE_OFF = {"HUSK_CHECK_RUN_LINES": "999999", "HUSK_CHECK_RUN_SHARE": "9",
            "HUSK_CHECK_COPIED_SHARE": "9", "HUSK_CHECK_RETENTION": "9",
            "HUSK_CHECK_RATIO": "9", "HUSK_CHECK_RETRIES": "0",
            "HUSK_CHECK_MODULE_NAMES": "0"}


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
    if arm == "llm-translation-ungated":
        prev = {k: os.environ.get(k) for k in GATE_OFF}
        os.environ.update(GATE_OFF)
        try:
            out, meta = entry.fn(src, crumb_level, {})
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    else:
        out, meta = entry.fn(src, crumb_level, {})
    assert_no_map(meta, f"{arm} rep{rep}")
    # meta carries the postcondition measurements and the chosen target; both are
    # wanted in the record, neither is sensitive.
    return out, {k: v for k, v in meta.items() if k != "reidentify_map"}


def stage_artifacts(outdir: Path, rows: list[dict], reps: int, crumb_level: int,
                    arms: tuple[str, ...], workers: int, dry: bool) -> None:
    art_dir = outdir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for r in rows:
        for arm in arms:
            n = reps if arm in STOCHASTIC_ARMS else 1
            for rep in range(n):
                jobs.append((r, arm, rep))

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
        if dry:
            return {"key": k, "ok": True, "cached": False, "dry": True}
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
            }, indent=2) + "\n")
            return {"key": k, "ok": True, "cached": False}
        except Exception as exc:  # noqa: BLE001 — a failure is the datum
            # Recorded, not raised: §12 rule 3. A husk the rewriter refused is a
            # real observation about the service and must survive in the record.
            meta_dest.write_text(json.dumps({
                "key": k, "arm": arm, "replicate": rep, "source_path": r["path"],
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "latency_s": round(time.time() - t0, 1),
            }, indent=2) + "\n")
            return {"key": k, "ok": False, "error": f"{type(exc).__name__}"}

    print(f"[artifacts] {len(jobs)} to build ({len(rows)} sources x {len(arms)} arms, "
          f"stochastic arms x{reps})")
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(work, jobs))
    ok = sum(1 for r in res if r["ok"])
    cached = sum(1 for r in res if r.get("cached"))
    print(f"[artifacts] {ok}/{len(res)} ok ({cached} already cached, "
          f"{len(res) - ok} failed)")


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
    }


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
        if dest.exists():
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
        attempts = []
        parsed = None
        # §6.1: unparseable responses are retried ONCE, then scored incorrect,
        # with the parse-failure rate reported separately.
        for attempt in range(2):
            try:
                resp = call_model_resilient(client, attacker, prompt, max_tokens, mode)
                parsed = parse_json_reply(resp["text"])
                attempts.append({"attempt": attempt, **resp,
                                 "parsed_ok": parsed is not None})
                if parsed is not None:
                    break
            except Exception as exc:  # noqa: BLE001
                attempts.append({"attempt": attempt, "error":
                                 f"{type(exc).__name__}: {str(exc)[:300]}",
                                 "parsed_ok": False})

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
        }, indent=2) + "\n", encoding="utf-8")
        if breaker is not None:
            breaker.record(parsed is not None)
        return {"ok": parsed is not None, "cached": False}

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(work, jobs))
    ok = sum(1 for r in res if r["ok"])
    cached = sum(1 for r in res if r.get("cached"))
    skipped = sum(1 for r in res if r.get("skipped"))
    print(f"[attack] {ok}/{len(res)} parsed ({cached} cached)")
    if skipped:
        print(f"[attack] ABORTED — {skipped} jobs skipped by the parse-failure breaker. "
              f"Fix the cause and resume with --run-id; completed records are cached.")
    print(f"[attack] judge stage is score_rsch1.py's job (judge={judge})")


# ------------------------------------------------------------------- main ----
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
    }
    (outdir / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    print(f"run: {outdir.relative_to(REPO)}  sources={len(rows)}  arms={list(arms)}")

    if a.stage in ("artifacts", "all"):
        stage_artifacts(outdir, rows, a.replicates, a.crumb_level, arms,
                        a.workers, a.dry_run)
    if a.stage in ("attack", "all"):
        breaker = None if a.no_breaker else ParseFailureBreaker(a.breaker_min, a.breaker_max_fail)
        stage_attack(outdir, rows, attackers, a.judge, arms, a.replicates,
                     a.workers, a.dry_run, a.max_tokens,
                     tuple(x.strip() for x in a.modes.split(",") if x.strip()),
                     breaker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
