#!/usr/bin/env python3
"""RSCH-1 — scoring, verdicts, and the summary table.

Implements `evals/preregistration.md` §6, §8, §9 and §12. The thresholds here
were frozen before any data was collected; if you find yourself editing one to
make a result read better, that is the situation the prereg exists to prevent.

Order of operations is itself pre-registered and is not cosmetic:

  1. **Validity gate FIRST** (§8). p_source >= 0.90 and Arm B parse failure <= 5%.
     If it fails, NO verdict is issued for any arm — because an attacker that
     cannot identify the domain from the *unmodified original* tells you the task
     or the labels are broken, and every husk number downstream is then measuring
     the harness rather than the husk.
  2. **Deterministic leak-term pre-check** (§6.2 pass 1), before any judge runs.
     No model, no judgement, fully reproducible. It will miss paraphrases; that is
     accepted and stated rather than patched with a second model.
  3. **Judge** (§6.2 pass 2), a third family, never shown the artifact.
  4. **Verdicts** (§8), reported at the panel MAXIMUM, never the mean (§7, §12.1).

    python3 evals/score_rsch1.py <run-dir>
    python3 evals/score_rsch1.py <run-dir> --no-judge     # deterministic parts only
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import math
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVALS = REPO / "evals"
PROMPTS = EVALS / "prompts"
Z95 = 1.959963984540054
BOOTSTRAP_DRAWS = 10_000


# ------------------------------------------------------------- statistics ----
def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float, float]:
    """Wilson score interval. §9: the normal approximation is wrong at this n."""
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, max(0.0, centre - half), min(1.0, centre + half)


def cluster_bootstrap_diff(husk: dict[str, list[int]], blind: dict[str, list[int]],
                           draws: int = BOOTSTRAP_DRAWS,
                           seed: int = 20260819) -> tuple[float, float]:
    """95% CI on (p_husk - p_blind), resampling SOURCE FILES with replacement.

    §9 is emphatic about this and it is the single thing that would make a PASS
    indefensible if done wrong: replicate husks of the same source are NOT
    independent observations. Resampling items instead of files would shrink the
    interval by roughly sqrt(replicates) and manufacture significance.
    """
    files = sorted(set(husk) | set(blind))
    if not files:
        return (0.0, 0.0)
    rng = random.Random(seed)
    diffs = []
    for _ in range(draws):
        pick = [files[rng.randrange(len(files))] for _ in files]
        hk = sum(sum(husk.get(f, [])) for f in pick)
        hn = sum(len(husk.get(f, [])) for f in pick)
        bk = sum(sum(blind.get(f, [])) for f in pick)
        bn = sum(len(blind.get(f, [])) for f in pick)
        if hn and bn:
            diffs.append(hk / hn - bk / bn)
    if not diffs:
        return (0.0, 0.0)
    diffs.sort()
    lo = diffs[int(0.025 * (len(diffs) - 1))]
    hi = diffs[int(0.975 * (len(diffs) - 1))]
    return lo, hi


def rate(k: int, n: int) -> str:
    """§9: exact counts beside every rate — `4/24`, never just `16.7%`."""
    return f"{k}/{n} ({(k / n * 100 if n else 0):.1f}%)"


# ----------------------------------------------------------------- loading ---
def load_raw(run: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((run / "raw").glob("*.json"))]


def is_missing(rec: dict) -> bool:
    """True when the call never reached the model at all.

    §6.1 says an UNPARSEABLE response is retried once and then scored incorrect.
    That rule is about a model that answered in the wrong shape — a real
    observation of a real capability. A transport failure (403 spend cap, 500,
    timeout) is not that: nothing was asked and nothing was answered, and scoring
    it "incorrect" invents an observation in the direction of the attacker being
    worse than it is. It has to be excluded from the denominator and reported as
    coverage instead.

    Getting this wrong is not cosmetic. When this run hit an account spending cap
    mid-flight, conflating the two put p_source at 46.7% and failed the validity
    gate — which would have read as "the task or the labels are broken" when in
    fact the attacker answered every call it actually received.
    """
    atts = rec.get("attempts") or []
    if not atts:
        return True
    # Missing only if NO attempt produced any text from the model.
    return all(a.get("text") is None for a in atts)


def scored_choice(rec: dict) -> dict:
    """Score one forced-choice record. §6.1: exact match against the ground-truth
    label — no judge, fully objective. Unparseable is scored INCORRECT after one
    retry, and counted separately as a parse failure. A call that never reached the
    model is MISSING, not incorrect — see is_missing()."""
    if is_missing(rec):
        return {"parse_ok": None, "missing": True, "correct": 0,
                "confidence": 0.0, "choice": None, "choice_id": None}
    parsed = rec.get("parsed")
    truth = rec.get("truth_option")
    if not parsed or "choice" not in parsed or truth is None:
        return {"parse_ok": False, "missing": False, "correct": 0,
                "confidence": 0.0, "choice": None, "choice_id": None}
    try:
        choice = int(parsed["choice"])
    except Exception:
        return {"parse_ok": False, "missing": False, "correct": 0,
                "confidence": 0.0, "choice": None, "choice_id": None}
    try:
        conf = float(parsed.get("confidence", 0.0))
    except Exception:
        conf = 0.0
    return {"parse_ok": True, "missing": False, "correct": int(choice == truth),
            "confidence": conf, "choice": choice,
            # What the attacker picked, by id — reveals whether a wrong answer is
            # the llm-translation TARGET, which is the behaviour a working husk
            # should produce and is invisible in a bare accuracy number.
            "choice_id": (rec["menu_order"][choice - 1]
                          if 1 <= choice <= len(rec.get("menu_order", [])) else None)}


# Mirrors run_rsch1.STOCHASTIC_ARMS: the arms stage_attack caps at the configured
# replicate count.
STOCHASTIC_ARMS = ("llm-translation", "llm-translation-ungated")


def effective_config(cfg: dict, recs: list[dict]) -> tuple[dict, list[str]]:
    """The config every section scores against, and the arms config.json omits.

    config.json keeps the FIRST invocation's fields, and each resume is appended to
    its `resumes` list (run_rsch1.write_or_extend_config). Runs from before that
    change kept only the LAST invocation's (20260819T182111Z omits an arm it built
    and attacked). Either way the top-level `arms` can be short, and an arm scored
    only where it is listed silently drops out of §2-§5. So arms, attackers and
    modes are the ordered union of the top level, every resume, and what raw/
    actually holds; the replicate budget is the largest any invocation used.
    """
    invocations = [cfg, *cfg.get("resumes", [])]

    def union(key: str, from_recs: str) -> list[str]:
        seen = [v for inv in invocations for v in inv.get(key) or []]
        return list(dict.fromkeys([*seen, *(r[from_recs] for r in recs)]))

    eff = dict(cfg)
    eff["arms"] = union("arms", "arm")
    eff["attackers"] = union("attackers", "attacker")
    eff["modes"] = union("modes", "mode")
    reps = [inv["replicates_llm_translation"] for inv in invocations
            if inv.get("replicates_llm_translation") is not None]
    if reps:
        eff["replicates_llm_translation"] = max(reps)
    unlisted = [a for a in eff["arms"] if a not in (cfg.get("arms") or [])]
    return eff, unlisted


def expected_coverage(run: Path, cfg: dict, recs: list[dict]) -> dict | None:
    """(arm, attacker, mode) -> {expected, present, missing}, or None without artifacts.

    Records that were never written are invisible to is_missing(): a stopped,
    breaker-tripped or partly resumed attack writes nothing for the jobs it never
    ran. The job set is rebuilt the way run_rsch1.stage_attack builds it, from the
    non-error artifacts. Arms are the config's plus any present in raw, because
    config.json's top level can omit an arm a resume built (see effective_config).
    """
    metas = [json.loads(p.read_text()) for p in sorted((run / "artifacts").glob("*.meta.json"))]
    if not metas:
        return None
    arms = set(cfg.get("arms", [])) | {r["arm"] for r in recs}
    attackers = list(dict.fromkeys([*cfg.get("attackers", []), *(r["attacker"] for r in recs)]))
    modes = list(dict.fromkeys([*cfg.get("modes", []), *(r["mode"] for r in recs)]))
    reps = cfg.get("replicates_llm_translation")
    split = set(cfg.get("source_files") or [])
    keys: dict[str, set] = defaultdict(set)
    for m in metas:
        if m.get("error") or not m.get("key") or m.get("arm") not in arms:
            continue
        if m["arm"] in STOCHASTIC_ARMS and reps is not None and m.get("replicate", 0) >= reps:
            continue
        if split and m.get("source_path") not in split:
            continue
        keys[m["arm"]].add(m["key"])
    cov: dict = {}
    for arm, ks in keys.items():
        for atk in attackers:
            for mode in modes:
                cov[(arm, atk, mode)] = {"expected": len(ks), "present": 0, "missing": 0}
    for r in recs:
        c = cov.get((r["arm"], r["attacker"], r["mode"]))
        if c is None or r["item_id"] not in keys[r["arm"]]:
            continue
        c["present"] += 1
        c["missing"] += is_missing(r)
    return cov


# run_rsch1.GATE_OFF, as _husk_check records it in postcondition.thresholds. No
# real gate runs at these values, so a gated-arm artifact carrying any of them
# was built with the gate (at least partly) off.
GATE_OFF_THRESHOLDS = {"run_lines": 999999, "run_share": 9.0, "copied_share": 9.0,
                       "retention": 9.0, "ratio": 9.0}


def gate_state_mismatches(run: Path) -> dict[str, tuple[int, int]]:
    """arm -> (artifacts whose recorded gate state contradicts the arm, artifacts
    with a recorded gate state), for the two llm-translation arms.

    The ungated arm used to switch the gate off by mutating os.environ from
    inside a thread pool, which let concurrent gated jobs run with it off too.
    The recorded thresholds are the only after-the-fact evidence of which state
    each husk was really built in.
    """
    out: dict[str, list[int]] = {}
    for p in sorted((run / "artifacts").glob("*.meta.json")):
        m = json.loads(p.read_text())
        arm = m.get("arm")
        if m.get("error") or arm not in STOCHASTIC_ARMS:
            continue
        th = ((m.get("solution_meta") or {}).get("postcondition") or {}).get("thresholds")
        if not isinstance(th, dict):
            continue
        at_off = [th.get(k) == v for k, v in GATE_OFF_THRESHOLDS.items()]
        wrong = any(at_off) if arm == "llm-translation" else not all(at_off)
        c = out.setdefault(arm, [0, 0])
        c[0] += wrong
        c[1] += 1
    return {k: (v[0], v[1]) for k, v in out.items()}


def mechanism_buckets(fc: list[dict], copied_share) -> dict:
    """arm -> {"hit": [...], "miss": [...]} copied-span shares for the husk arms.

    A transport failure never reached the model, so it is neither a right nor a
    wrong answer (is_missing); a parse failure stays in "miss", per §6.1.
    """
    buckets: dict = defaultdict(lambda: {"hit": [], "miss": []})
    for r in fc:
        if r["arm"] in ("blind", "source"):
            continue
        sc = scored_choice(r)
        if sc["missing"]:
            continue
        cs = copied_share(r["item_id"], r["source_path"])
        if cs is None:
            continue
        buckets[r["arm"]]["hit" if sc["correct"] else "miss"].append(cs)
    return buckets


def _usage(resp) -> dict | None:
    """Token usage off an OpenAI-style response, every field int-or-None.

    Anything that is not an int (a provider that omits a field, a test double)
    becomes None, so the payload always serialises and absence never reads as 0.
    """
    u = getattr(resp, "usage", None)
    if u is None:
        return None

    def _int(v):
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    details = getattr(u, "completion_tokens_details", None)
    return {"prompt_tokens": _int(getattr(u, "prompt_tokens", None)),
            "completion_tokens": _int(getattr(u, "completion_tokens", None)),
            "total_tokens": _int(getattr(u, "total_tokens", None)),
            "reasoning_tokens": _int(getattr(details, "reasoning_tokens", None))}


USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")


def usage_table(recs: list[dict], judged: dict | None = None,
                judge_model: str | None = None, metas: list[dict] = ()) -> list[str]:
    """Token usage summed per (attacker, arm) from each attempt's `usage`, one judge
    row, and one rewriter row per arm from the artifact metas' solution_meta.usage
    (llm-translation has recorded that since before RSCH-1). Runs recorded before
    attacker/judge usage capture say so instead of printing zeros."""
    rows: dict = defaultdict(lambda: {"calls": 0, "with": 0, **{f: 0 for f in USAGE_FIELDS}})

    def add(key, usage):
        row = rows[key]
        row["calls"] += 1
        if isinstance(usage, dict) and any(isinstance(usage.get(f), int) for f in USAGE_FIELDS):
            row["with"] += 1
            for f in USAGE_FIELDS:
                if isinstance(usage.get(f), int):
                    row[f] += usage[f]

    for r in recs:
        for a in r.get("attempts") or []:
            add((r["attacker"], r["arm"]), a.get("usage"))
    for p in (judged or {}).values():
        add((f"{judge_model} (judge)", "all arms"), p.get("usage"))
    for m in metas:
        sm = m.get("solution_meta") or {}
        if "usage" in sm and not m.get("error"):
            add((f"{sm.get('model') or 'rewriter'} (rewriter)", m.get("arm")), sm.get("usage"))

    L = ["## 7. Token usage (not pre-registered)\n"]
    if not any(row["with"] for row in rows.values()):
        L.append("No usage recorded: this run's attempts, judge records and artifact metas "
                 "predate usage capture, so its cost cannot be read from the run directory.\n")
        return L
    atk_rows = [k for k in rows if not k[0].endswith(("(judge)", "(rewriter)"))]
    if atk_rows and not any(rows[k]["with"] for k in atk_rows):
        L.append("Attacker and judge calls in this run predate usage capture, so only the "
                 "rewriter's share of the cost can be read from the run directory.\n")
    L.append("Summed over every attempt, retries included. A call without a usage record "
             "(transport failure, or a provider that omits it) is counted in the first column "
             "and adds nothing to the sums, so those are lower bounds wherever it is below n.\n")
    L.append("| attacker | arm | calls with usage | prompt | completion | of which reasoning | total |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for (atk, arm), row in sorted(rows.items()):
        L.append(f"| `{atk.split('/')[-1]}` | `{arm}` | {row['with']}/{row['calls']} | "
                 + " | ".join(f"{row[f]:,}" for f in USAGE_FIELDS) + " |")
    L.append("")
    return L


# ------------------------------------------------- deterministic leak check --
def leak_precheck(guess_text: str, terms: list[str]) -> list[str]:
    """§6.2 pass 1. Case-insensitive, word-boundary matched, no model."""
    hits = []
    for t in terms:
        if re.search(r"\b" + re.escape(t) + r"\b", guess_text, re.I):
            hits.append(t)
    return hits


def open_ended_text(rec: dict) -> str:
    p = rec.get("parsed") or {}
    bits = [str(p.get("domain", ""))]
    ids = p.get("specific_identifiers")
    if isinstance(ids, list):
        bits += [str(x) for x in ids]
    bits.append(str(p.get("evidence", "")))
    return " ".join(bits)


# ------------------------------------------------------------------ judge ----
def run_judge(run: Path, recs: list[dict], judge_model: str) -> dict[str, dict]:
    """§6.2 pass 2. Third family, temperature 0, NOT shown the artifact."""
    from dotenv import load_dotenv  # noqa: PLC0415
    load_dotenv(REPO / "husk-api" / ".env")
    from openai import OpenAI  # noqa: PLC0415

    tpl = re.sub(r"^\s*<!--.*?-->\s*", "",
                 (PROMPTS / "judge.md").read_text(), count=1, flags=re.S)
    menu = {o["id"]: o for o in json.loads((EVALS / "domains.json").read_text())["options"]}
    jdir = run / "judge"
    jdir.mkdir(exist_ok=True)
    client = OpenAI(base_url=os.environ["LLM_BASE_URL"],
                    api_key=os.environ["LLM_API_KEY"], timeout=300)
    # Judge prompts are tiny (no artifact — §6.2 blinds the judge deliberately), but
    # there are one per open-ended record and a serial loop over ~660 of them is an
    # hour of wall clock for no reason. Cached per record, so a re-score after a
    # scoring-code change costs nothing.
    JUDGE_SCHEMA = {"type": "json_schema", "json_schema": {
        "name": "judgement", "strict": True, "schema": {
            "type": "object", "additionalProperties": False,
            "required": ["label", "reason"],
            "properties": {"label": {"type": "string",
                                     "enum": ["MATCH", "RELATED", "MISS"]},
                           "reason": {"type": "string"}}}}}

    todo = []
    out: dict[str, dict] = {}
    for rec in recs:
        if rec["mode"] != "open_ended" or not rec.get("parsed"):
            continue
        rid = f"{rec['item_id']}__{re.sub(r'[^A-Za-z0-9.-]+', '-', rec['attacker'])}"
        dest = jdir / f"{rid}.json"
        if dest.exists():
            out[rid] = json.loads(dest.read_text())
            continue
        truth = menu.get(rec["true_domain_id"], {})
        prompt = (tpl.replace("{truth_label}", truth.get("label", rec["true_domain_id"]))
                     .replace("{truth_description}", truth.get("description", ""))
                     .replace("{guess}", open_ended_text(rec)[:1500]))
        todo.append((rid, dest, rec, prompt))

    def judge_one(job):
        rid, dest, rec, prompt = job
        usage = None  # unknown, not zero, when the call fails
        try:
            r = client.chat.completions.create(
                model=judge_model, messages=[{"role": "user", "content": prompt}],
                max_tokens=4096, temperature=0, response_format=JUDGE_SCHEMA)
            usage = _usage(r)
            txt = r.choices[0].message.content or ""
            a, b = txt.find("{"), txt.rfind("}")
            parsed = json.loads(txt[a:b + 1]) if a >= 0 and b > a else None
        except Exception as exc:  # noqa: BLE001
            txt, parsed = f"{type(exc).__name__}: {exc}", None
        payload = {"item_id": rec["item_id"], "attacker": rec["attacker"],
                   "judge": judge_model, "prompt": prompt, "response": txt,
                   "label": (parsed or {}).get("label"), "usage": usage}
        dest.write_text(json.dumps(payload, indent=2) + "\n")
        return rid, payload

    if todo:
        print(f"[judge] {len(todo)} to label ({len(out)} cached)", file=sys.stderr)
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for rid, payload in ex.map(judge_one, todo):
                out[rid] = payload
    return out


# ------------------------------------------------------------------ main -----
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="run directory under evals/runs/")
    ap.add_argument("--no-judge", action="store_true")
    a = ap.parse_args()
    run = Path(a.run)
    if not run.is_absolute():
        run = REPO / run
    recs = load_raw(run)
    if not recs:
        print("no raw records", file=sys.stderr)
        return 2
    cfg, unlisted_arms = effective_config(json.loads((run / "config.json").read_text()), recs)

    attackers = cfg["attackers"]
    fc = [r for r in recs if r["mode"] == "forced_choice"]
    oe = [r for r in recs if r["mode"] == "open_ended"]

    # correct[(attacker, arm)][source_path] -> [0/1, ...]  (clustered by SOURCE FILE)
    correct: dict = defaultdict(lambda: defaultdict(list))
    conf_hi: dict = defaultdict(lambda: defaultdict(list))
    parse_fail: dict = defaultdict(lambda: [0, 0])
    per_domain: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    target_picks: dict = defaultdict(int)

    missing: dict = defaultdict(int)
    for r in fc:
        s = scored_choice(r)
        k = (r["attacker"], r["arm"])
        if s["missing"]:
            # Never reached the model. Excluded from every rate; reported as coverage.
            missing[k] += 1
            continue
        parse_fail[k][1] += 1
        if not s["parse_ok"]:
            parse_fail[k][0] += 1
        correct[k][r["source_path"]].append(s["correct"])
        if s["confidence"] >= 0.7:
            conf_hi[k][r["source_path"]].append(s["correct"])
        d = per_domain[k][r["true_domain_id"]]
        d[0] += s["correct"]
        d[1] += 1
        if s["choice_id"] and s["choice_id"] != r["true_domain_id"]:
            target_picks[(r["arm"], s["choice_id"])] += 1

    def agg(k) -> tuple[int, int]:
        items = correct.get(k, {})
        return sum(sum(v) for v in items.values()), sum(len(v) for v in items.values())

    L: list[str] = []
    W = L.append
    W(f"# RSCH-1 — results\n")
    # A1 is about the data a run actually holds, not the split it was launched on.
    n_src_seen = len({r["source_path"] for r in fc if not is_missing(r)})
    W(f"**Run:** `{cfg['run_id']}`  ·  **split:** `{cfg['split']}`  ·  "
      f"**sources:** {cfg['n_source_files']}"
      + (f" ({n_src_seen} carry an answered forced-choice record)"
         if n_src_seen != cfg["n_source_files"] else ""))
    W(f"**Pre-registration commit:** `{cfg['preregistration_commit']}` (§12 rule 4)")
    W(f"**Repo commit:** `{cfg['repo_git_commit']}`"
      + ("  ⚠️ **working tree dirty**" if cfg.get("repo_dirty") else ""))
    W(f"**Attackers:** {', '.join(attackers)}  ·  **judge:** {cfg['judge']}")
    W(f"**Rewriter:** {cfg.get('rewriter_model')}  ·  endpoint `{cfg.get('endpoint_host')}`\n")
    if unlisted_arms:
        W(f"> ⚠️ **ARMS NOT IN config.json's top level: "
          f"{', '.join(f'`{a}`' for a in unlisted_arms)}.** A resume (or, before "
          f"2026-09-26, an overwritten config) built or attacked them. They are scored in every "
          f"section below like any other arm, not dropped.\n")
    n_missing = sum(1 for r in recs if is_missing(r))
    cov = expected_coverage(run, cfg, recs) or {}
    n_absent = sum(max(0, c["expected"] - c["present"]) for c in cov.values())
    cov_missing = sum(c["missing"] for c in cov.values())
    if n_absent or cov_missing:
        n_expected = sum(c["expected"] for c in cov.values())
        n_answered = sum(c["present"] - c["missing"] for c in cov.values())
        W(f"> ⚠️ **COVERAGE: {n_answered}/{n_expected} expected calls have a model answer.** "
          f"This run's artifacts × attackers × modes imply {n_expected} calls: "
          + " and ".join(x for x in (
              f"{n_absent} were never written (an attack that stops, trips its breaker or is "
              f"resumed on a subset writes nothing for the jobs it never ran)" if n_absent else "",
              f"{cov_missing} never reached the model (transport failure)" if cov_missing else "")
              if x)
          + ". They are excluded from every rate below as missing observations rather than "
          "scored incorrect, because nothing was asked and nothing was answered. **Check the "
          "per-domain table before reading any aggregate: a domain the run never got to will "
          "look absent, not clean.**\n")
        W("| arm | attacker | mode | answered / expected | never written | transport failure |")
        W("|---|---|---|---:|---:|---:|")
        for (arm_, atk_, mode_), c in sorted(cov.items()):
            gap = c["expected"] - c["present"] + c["missing"]
            if gap > 0:
                W(f"| `{arm_}` | `{atk_.split('/')[-1]}` | {mode_} | "
                  f"{c['present'] - c['missing']}/{c['expected']} | "
                  f"{max(0, c['expected'] - c['present'])} | {c['missing']} |")
        W("")
    elif n_missing:
        W(f"> ⚠️ **COVERAGE: {len(recs) - n_missing}/{len(recs)} calls completed; "
          f"{n_missing} never reached the model** (transport failure). Those are excluded from "
          f"every rate below as missing observations rather than scored incorrect, because "
          f"nothing was asked and nothing was answered. **Check the per-domain table before "
          f"reading any aggregate: a domain the run never got to will look absent, not clean.**\n")

    mism = gate_state_mismatches(run)
    g_bad, g_all = mism.get("llm-translation", (0, 0))
    u_bad, u_all = mism.get("llm-translation-ungated", (0, 0))
    if g_bad or u_bad:
        W("> 🚨 **GATE STATE DOES NOT MATCH THE ARM.**"
          + (f" **{g_bad}/{g_all} `llm-translation` artifacts were built with the post-condition "
             "gate OFF**: their recorded thresholds are the neutralised values the "
             "`llm-translation-ungated` arm uses. Every `llm-translation` figure below therefore "
             "describes an effectively ungated rewriter, not what a caller of the service "
             "receives, and husks the gate would have refused are scored as served."
             if g_bad else "")
          + (f" {u_bad}/{u_all} `llm-translation-ungated` artifacts record live gate thresholds "
             "instead, so that arm was partly gated." if u_bad else "")
          + " Scored as recorded so the run stays reproducible; a true gated figure needs a "
          "re-run.\n")

    # ---- 1. VALIDITY GATE, evaluated first -----------------------------------
    W("## 1. Validity gate (§8) — evaluated first\n")
    W("If this fails, **no verdict is issued for any arm**.\n")
    W("| attacker | p_source | parse failure (all arms) | gate |")
    W("|---|---|---|---|")
    gate_ok = True
    gate_failed = False
    for atk in attackers:
        k, n = agg((atk, "source"))
        p, lo, hi = wilson(k, n)
        pf_k = sum(v[0] for (a_, _), v in parse_fail.items() if a_ == atk)
        pf_n = sum(v[1] for (a_, _), v in parse_fail.items() if a_ == atk)
        pf = pf_k / pf_n if pf_n else 0.0
        ok = (p >= 0.90) and (pf <= 0.05)
        gate_ok &= ok
        if n == 0 and pf <= 0.05:
            # No source records is not a failed control, it is an absent one.
            W(f"| `{atk}` | — | {rate(pf_k, pf_n)} | NOT EVALUATED — no source arm in this run |")
            continue
        gate_failed |= not ok
        W(f"| `{atk}` | {rate(k, n)} [{lo:.2f}, {hi:.2f}] | {rate(pf_k, pf_n)} | "
          f"{'✅ pass' if ok else '❌ FAIL'} |")
    W("")
    gate_why = "validity gate failed" if gate_failed else "validity gate not evaluated"
    if gate_failed:
        W("> **GATE FAILED.** Per §8 no verdict is issued for any arm. An attacker that "
          "cannot identify the domain from the unmodified original means the task or the "
          "labels are broken, and every husk number below would be measuring the harness "
          "rather than the husk.\n")
    elif not gate_ok:
        W("> **GATE NOT EVALUATED — no source arm in this run.** Per §8 no verdict is issued "
          "for any arm. This is not a failed gate: the control that checks the task and the "
          "labels was never run, so this run says nothing about them either way.\n")

    # A1: fewer than 3 held-out domains carrying data is INCONCLUSIVE on power
    # grounds, whatever the numbers. Counted per arm on domains where both the
    # source control and the arm have an answered forced-choice record.
    def domains_with_data(arm: str) -> set:
        return {d for (_, a_), row in per_domain.items() if a_ == arm for d in row}

    a1_short: dict[str, int] = {}
    src_doms = domains_with_data("source")
    if src_doms:
        for arm in cfg["arms"]:
            if arm not in ("blind", "source") and domains_with_data(arm):
                nd = len(src_doms & domains_with_data(arm))
                if nd < 3:
                    a1_short[arm] = nd
    if a1_short:
        W("> **A1 — fewer than 3 domains carry data** for "
          + ", ".join(f"`{a_}` ({nd})" for a_, nd in a1_short.items())
          + ". Amendment A1 reports a confirmatory run with fewer than 3 held-out domains as "
          "INCONCLUSIVE on power grounds regardless of its numbers, so no PASS or FAIL is "
          "issued for those arms.\n")

    # ---- 2. Arm B, forced choice --------------------------------------------
    W("## 2. Arm B — forced choice (pre-registered primary endpoint, §6.1)\n")
    W("Chance on a 12-option menu is 0.083. **BLIND, not chance, is the baseline "
      "C1 is measured against** (§3).\n")
    W("> ⚠️ **This table measures RECOGNITION, not recall, and the difference is large enough "
      "to change what the result means.** The attacker is handed twelve options with the correct "
      "one among them. Picking it off a list is far easier than describing the domain cold, and "
      "the two endpoints disagree sharply — on the first domain measured, `llm-translation` "
      "scored **71.7% on the menu but 21.7% in free text**, against a `source` control of 100% "
      "and 93.8%. C1 is phrased in terms of THIS table, so C1 can fail while the husk is still "
      "removing most of the free-text signal — and that is what happened. Read §4 and §5b before "
      "quoting anything from here.\n")
    W("| arm | " + " | ".join(f"`{a_.split('/')[-1]}`" for a_ in attackers)
      + " | **panel max** |")
    W("|---|" + "---|" * (len(attackers) + 1))
    panel_max: dict[str, float] = {}
    for arm in cfg["arms"]:
        cells = []
        best = 0.0
        for atk in attackers:
            k, n = agg((atk, arm))
            if n == 0:
                cells.append("—")
                continue
            p, lo, hi = wilson(k, n)
            best = max(best, p)
            cells.append(f"{rate(k, n)}<br><sub>[{lo:.2f}, {hi:.2f}]</sub>")
        panel_max[arm] = best
        W(f"| `{arm}` | " + " | ".join(cells) + f" | **{best:.3f}** |")
    W("")
    W("§7 and §12.1: the headline is the **maximum** across the panel, never the mean — "
      "averaging a strong attacker against a weak one launders a failure.\n")

    # ---- 2b. Permutation-corrected (amendment A4.1) --------------------------
    # Raw accuracy is confounded by the attacker's answer distribution: an
    # attacker that ignores its input and always names one domain scores that
    # domain's base rate. Holding its answers fixed and permuting the labels
    # says what response bias alone buys, so the arm can be read as a
    # difference from its OWN null rather than from BLIND's.
    try:
        sys.path.insert(0, str(EVALS))
        from permutation_baseline import build as perm_build, render as perm_render

        rep = perm_build(run)
        (run / "permutation.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        (run / "permutation.md").write_text(perm_render(rep), encoding="utf-8")
        W("### 2b. Corrected for attacker response bias (A4.1)\n")
        W("Each attacker's answers are held fixed and the true labels permuted 10,000 times "
          "across **source files** (§9's clustering rule, replicates carried with their file). "
          "`corrected` is observed minus that null; `p` is how often response bias alone reaches "
          "the observed value.\n")
        W("| arm | attacker | n | observed | permuted null | **corrected** | p | modal answer |")
        W("|---|---|---:|---:|---:|---:|---:|---|")
        n_differs = []
        for key, c in sorted(rep["cells"].items()):
            if not c.get("n"):
                continue
            arm_, atk_ = key.split("|")
            short = atk_.split('/')[-1].split(':')[0]
            n2 = agg((atk_, arm_))[1]
            if n2 != c["n"]:
                n_differs.append((arm_, short, n2, c["n"]))
            if c.get("degenerate"):
                W(f"| `{arm_}` | {short} | {c['n']} | {c['observed']:.3f} "
                  f"| not computable | **not computable** | — "
                  f"| {c['modal_answer']} {c['modal_n']}/{c['n']} |")
                continue
            W(f"| `{arm_}` | {short} | {c['n']} | {c['observed']:.3f} "
              f"| {c['permuted_mean']:.3f} [{c['permuted_lo']:.2f}, {c['permuted_hi']:.2f}] "
              f"| **{c['corrected']:+.3f}** | {c['p']:.4f} "
              f"| {c['modal_answer']} {c['modal_n']}/{c['n']} |")
        W("")
        if any(c.get("degenerate") for c in rep["cells"].values()):
            W("*not computable*: every source file in the cell carries one domain, so permuting "
              "labels changes nothing and the null equals the observed value by construction.\n")
        if n_differs:
            # A4.1 as registered drops every record with no parsed choice; §2
            # scores an answered-but-unparseable reply incorrect (§6.1). Until an
            # amendment reconciles them, the two n's are stated side by side.
            W("> **n here is not §2's n** for " + "; ".join(
                f"`{a_}` / {s_}: " + (f"n excludes {n2 - n1} answered-but-unparseable "
                                      f"record{'s' if n2 - n1 != 1 else ''} that §2 scores "
                                      f"incorrect ({n1} here, {n2} in §2)"
                                      if n2 > n1 else f"{n1} here, {n2} in §2")
                for a_, s_, n2, n1 in n_differs)
              + ". A4.1 drops a forced-choice record with no parsed choice as missing; §2 "
              "follows §6.1 and counts it as a wrong answer.\n")
        W("Full detail, including the analytic cross-check and the leak-channel attribution, "
          "is in `permutation.md` beside this file.\n")
    except Exception as exc:  # noqa: BLE001 — never let the correction break the report
        W(f"### 2b. Permutation correction unavailable: {type(exc).__name__}: {exc}\n")

    # accuracy at confidence >= 0.7
    W("### Accuracy at confidence ≥ 0.7 (§6.1)\n")
    W("| arm | " + " | ".join(f"`{a_.split('/')[-1]}`" for a_ in attackers) + " |")
    W("|---|" + "---|" * len(attackers))
    for arm in cfg["arms"]:
        cells = []
        for atk in attackers:
            items = conf_hi.get((atk, arm), {})
            k = sum(sum(v) for v in items.values())
            n = sum(len(v) for v in items.values())
            cells.append(rate(k, n) if n else "—")
        W(f"| `{arm}` | " + " | ".join(cells) + " |")
    W("")

    # ---- 3. Per-domain, always reported -------------------------------------
    W("### Per-domain accuracy (§9 — always reported)\n")
    W("One leaky domain is invisible in an aggregate and is exactly the case that matters.\n")
    doms = sorted({d for k in per_domain for d in per_domain[k]})
    W("| arm | attacker | " + " | ".join(f"`{d}`" for d in doms) + " |")
    W("|---|---|" + "---|" * len(doms))
    for arm in cfg["arms"]:
        for atk in attackers:
            row = per_domain.get((atk, arm), {})
            if not row:
                continue
            cells = [rate(*row[d]) if d in row else "—" for d in doms]
            W(f"| `{arm}` | `{atk.split('/')[-1]}` | " + " | ".join(cells) + " |")
    W("")

    # ---- 4.1 computed ahead of the verdicts ------------------------------------
    # §8's hard veto overrides any Arm B verdict, so it has to be known before the
    # verdict table is written. It is still rendered in §4.1, where it belongs.
    veto: dict[str, bool] = {}
    veto_rows = []
    man = None
    for arm in cfg["arms"]:
        for atk in attackers:
            rs = [r for r in oe if r["arm"] == arm and r["attacker"] == atk
                  and not is_missing(r)]
            if not rs:
                continue
            if man is None:
                man = json.loads((EVALS / "corpus" / "manifest.json").read_text())
            terms_by_dom = {d["true_domain_id"]: d.get("leak_terms", [])
                            for d in man["domains"].values() if isinstance(d, dict)}
            hits = sum(1 for r in rs
                       if leak_precheck(open_ended_text(r),
                                        terms_by_dom.get(r["true_domain_id"], [])))
            frac = hits / len(rs)
            fired = frac >= 0.10 and arm not in ("blind", "source")
            veto[arm] = veto.get(arm, False) or fired
            veto_rows.append((arm, atk, hits, len(rs), fired))

    def veto_issued(arm: str) -> bool:
        # A failed gate issues no verdict for any arm (§8), and A1 none for a
        # short arm; the veto is a verdict like any other.
        return veto.get(arm, False) and gate_ok and arm not in a1_short

    # ---- 4. Verdicts ---------------------------------------------------------
    W("## 3. Verdicts (§8)\n")
    W("| solution | p_husk (strongest attacker) | p_blind (same attacker) | attacker | "
      "95% CI on difference (cluster bootstrap over source files) | verdict |")
    W("|---|---|---|---|---|---|")
    verdicts = {}
    for arm in cfg["arms"]:
        if arm in ("blind", "source"):
            continue
        best_atk = max(attackers, key=lambda at: (agg((at, arm))[0] /
                                                  max(1, agg((at, arm))[1])))
        hk, hn = agg((best_atk, arm))
        if hn == 0:
            continue
        p_h = hk / hn
        # p_blind is THIS attacker's blind, not the panel-max blind. §7 says report
        # the husk rate at the strongest attacker; the difference it is compared
        # against has to come from the same model, because (p_husk of model A) −
        # (p_blind of model B) is not a quantity about either of them. The cluster
        # bootstrap below already pairs them per attacker, so using panel-max here
        # would have put a point estimate and its own confidence interval on
        # different footings.
        bk, bn = agg((best_atk, "blind"))
        if bn == 0:
            # No BLIND arm in this run. Defaulting p_blind to 0.0 would print a
            # confident FAIL computed against a baseline that was never
            # measured, and a committed summary.md is exactly where such a
            # number gets quoted later. Refuse instead, and point at the
            # correction that IS valid for a run like this.
            if veto_issued(arm):
                # The Arm A veto needs no BLIND baseline.
                verdicts[arm] = "**FAIL** (hard veto, Arm A)"
                W(f"| `{arm}` | {rate(hk, hn)} | — | `{best_atk.split('/')[-1]}` | — | "
                  f"{verdicts[arm]} — no BLIND arm, so Arm B issues nothing here. |")
                continue
            verdicts[arm] = "NOT COMPUTABLE"
            W(f"| `{arm}` | {rate(hk, hn)} | — | `{best_atk.split('/')[-1]}` | — | "
              "**NOT COMPUTABLE — no BLIND arm in this run.** Read §2b: these arms are "
              "interpreted against their own permuted baseline (A4.1), not against BLIND. |")
            continue
        p_b = bk / bn if bn else 0.0
        lo, hi = cluster_bootstrap_diff(correct[(best_atk, arm)],
                                        correct[(best_atk, "blind")])
        spread = max(abs(agg((x, arm))[0] / max(1, agg((x, arm))[1]) -
                         agg((y, arm))[0] / max(1, agg((y, arm))[1]))
                     for x in attackers for y in attackers)
        if not gate_ok:
            v = f"INCONCLUSIVE — {gate_why}"
        elif arm in a1_short:
            v = "INCONCLUSIVE — A1: fewer than 3 domains carry data"
        elif spread > 0.20:
            v = "INCONCLUSIVE — attackers differ by > 0.20"
        elif hi <= 0.10 and p_h <= 0.25:
            v = "**PASS**"
        elif (p_h - p_b) >= 0.25 and lo > 0:
            v = "**FAIL**"
        else:
            v = "INCONCLUSIVE"
        if veto_issued(arm) and v != "**FAIL**":
            v = "**FAIL** (hard veto, Arm A)"
        verdicts[arm] = v
        W(f"| `{arm}` | {rate(hk, hn)} | {rate(bk, bn)} | `{best_atk.split('/')[-1]}` | "
          f"[{lo:+.3f}, {hi:+.3f}] | {v} |")
    W("")
    W("> **INCONCLUSIVE is reported as inconclusive** — never as support for C1, never as "
      "\"no evidence of leakage.\" (§8, registered literally so it cannot be softened later.)\n")

    # ---- 5. Arm A, deterministic pre-check ----------------------------------
    W("## 4. Arm A — open ended (§6.2). Can only FALSIFY C1, never support it.\n")
    W("### 4.1 Deterministic leak-term pre-check — no model, fully reproducible\n")
    W("| arm | attacker | guesses containing a source-domain leak term | veto |")
    W("|---|---|---|---|")
    for arm, atk, hits, n_rs, fired in veto_rows:
        if arm in ("blind", "source"):
            cell = "—"
        elif not gate_ok:
            cell = f"not issued ({gate_why.replace('validity ', '')})"
        elif arm in a1_short:
            cell = "not issued (A1: fewer than 3 domains)"
        else:
            cell = "🚫 **FAIL — hard veto**" if fired else "—"
        W(f"| `{arm}` | `{atk.split('/')[-1]}` | {rate(hits, n_rs)} | {cell} |")
    W("")
    if any(veto_issued(k) for k in veto):
        W("> **Hard veto fired (§8).** A solution whose open-ended guesses hit its own "
          "source-domain leak terms on ≥ 10% of items is **FAIL regardless of its "
          "forced-choice result**. Solutions vetoed: "
          + ", ".join(f"`{k}`" for k in veto if veto_issued(k)) + "\n")

    # ---- 6. Judge ------------------------------------------------------------
    if not a.no_judge:
        W("### 4.2 Judge (§6.2 pass 2)\n")
        judged = run_judge(run, oe, cfg["judge"])
        tally: dict = defaultdict(lambda: defaultdict(int))
        for rid, p in judged.items():
            rec = next((r for r in oe if rid.startswith(r["item_id"])), None)
            if rec:
                tally[rec["arm"]][p.get("label") or "UNPARSED"] += 1
        W("| arm | MATCH | RELATED | MISS | unparsed |")
        W("|---|---|---|---|---|")
        for arm in cfg["arms"]:
            t = tally.get(arm, {})
            W(f"| `{arm}` | {t.get('MATCH', 0)} | {t.get('RELATED', 0)} | "
              f"{t.get('MISS', 0)} | {t.get('UNPARSED', 0)} |")
        W("")
        kpath = run / "kappa.json"
        if kpath.exists():
            kd = json.loads(kpath.read_text())
            k = kd.get("kappa")
            W(f"**Cohen's κ = {k}** on {kd['n_pairs']} hand-labelled pairs "
              f"(observed agreement {kd['observed_agreement']}, "
              f"chance {kd['expected_agreement']}).")
            if k is None or k < 0.6:
                W("")
                W("> **κ < 0.6 — the judge table above is DESCRIPTIVE ONLY** (§6.2, registered "
                  "in advance). Only the deterministic leak-term pre-check in §4.1 counts as "
                  "evidence for or against C1.\n")
            else:
                W("")
                W("> κ ≥ 0.6, so these labels may be cited as evidence (§6.2).\n")
        else:
            W("> **κ is OWED and this table is therefore DESCRIPTIVE ONLY.** §6.2 requires a "
              "random 20% of these hand-labelled and Cohen's κ reported, and registers in "
              "advance that **if κ < 0.6 only the deterministic pre-check counts as "
              "evidence**. Until the hand-labelling is done the weaker reading applies, "
              "because an unmeasured κ cannot be assumed to pass.\n")
            W("    python3 evals/kappa_judge.py --sample " + str(run.name))
            W("    # fill in human_label on each row, then:")
            W("    python3 evals/kappa_judge.py --score  " + str(run.name) + "\n")

    # ---- 6b. Mechanism: does copied source explain a successful attack? ------
    # Not required by the pre-registration. Added because a re-identification rate
    # on its own says THAT a husk leaks and never WHY, and this repo already has a
    # measured mechanism to hand: llm-translation returns spans of its input
    # verbatim. Joining the two turns "llm-translation scored X" into "it scored X
    # and the items it lost carried N% more copied source", which is a claim a
    # reader can act on. Every number here is deterministic and needs no API call.
    W("## 5. Mechanism — copied source vs successful re-identification\n")
    W("*Not pre-registered. Descriptive, and reported as such.* Measured with the shipped "
      "`app/solutions/_husk_check.inspect`, the same implementation the request-path gate "
      "uses, so this cannot drift from what the service enforces.\n")
    try:
        # Load by file path, not as a package. `import app.solutions` fires the
        # solutions auto-discovery loop, which imports llm_translation and thus
        # `openai` at module scope — absent under a bare interpreter, where this
        # scorer is meant to run. The broad except below would then silently drop
        # this whole section. Same idiom as score_husk.py and
        # calibrate_postcondition.py, for the same reason.
        _hc_spec = importlib.util.spec_from_file_location(
            "_husk_check", REPO / "husk-api" / "app" / "solutions" / "_husk_check.py")
        _hc_mod = importlib.util.module_from_spec(_hc_spec)
        _hc_spec.loader.exec_module(_hc_mod)
        husk_inspect = _hc_mod.inspect
        art = run / "artifacts"
        cache: dict[str, float] = {}

        def copied_share(item_id: str, src_path: str) -> float | None:
            if item_id in cache:
                return cache[item_id]
            f = art / f"{item_id}.txt"
            sp = REPO / src_path
            if not f.exists() or not sp.exists():
                return None
            try:
                r = husk_inspect(sp.read_text(encoding="utf-8"),
                                 f.read_text(encoding="utf-8"),
                                 "." + src_path.rsplit(".", 1)[-1])
                cache[item_id] = r["copied_span_share"]
            except Exception:  # noqa: BLE001
                return None
            return cache[item_id]

        buckets = mechanism_buckets(fc, copied_share)
        W("| arm | mean copied-span share when attacker was RIGHT | when WRONG | n right / n wrong |")
        W("|---|---|---|---|")
        for arm in cfg["arms"]:
            b = buckets.get(arm)
            if not b or not (b["hit"] or b["miss"]):
                continue
            mh = f"{sum(b['hit']) / len(b['hit']):.3f}" if b["hit"] else "—"
            mm = f"{sum(b['miss']) / len(b['miss']):.3f}" if b["miss"] else "—"
            W(f"| `{arm}` | {mh} | {mm} | {len(b['hit'])} / {len(b['miss'])} |")
        W("")
        W("A higher figure in the first column than the second means the attacker succeeded "
          "disproportionately on husks that had returned more of their own source verbatim — "
          "i.e. the leak is *copying*, which is a fixable defect with a gate already built for "
          "it. Similar figures mean the leak survives a genuine rewrite, which is the harder "
          "and more interesting result and is what `docs/working-paper.md` §4.2 predicts.\n")
    except Exception as exc:  # noqa: BLE001
        W(f"*(mechanism section unavailable: {type(exc).__name__}: {exc})*\n")

    # ---- 7. Registered limitations ------------------------------------------
    W("## 5b. What this corpus cannot test\n")
    W("Every source domain here is **synthetic** — fabricated for this evaluation, modelling no "
      "real institution, product, vendor or system. The threat model the project states it cares "
      "about is *\"the organization, the product line, the proprietary algorithm, the regulatory "
      "domain\"* (§6.2). **None of those exist in this corpus**, so identifier-level "
      "re-identification is not merely unmeasured here — it is untestable by construction.\n")
    W("The check that shows it: on the **unhusked SOURCE** control the attacker named a real "
      "outside entity on only a minority of items, and the names it produced do not appear in the "
      "corpus at all — they were plausible guesses about the sector, not recoveries. The ceiling "
      "for identifier-level recovery on synthetic input is therefore near zero for *every* arm, "
      "husked or not, and no arm can be credited or blamed for it.\n")
    W("Consequence for the writeup: this experiment measures **problem-domain** leakage and "
      "nothing narrower. A result here, in either direction, says nothing about whether a husk "
      "protects a real organization's identity. Testing that needs real proprietary source with "
      "real identifiers in it — a different experiment, with different consent and handling "
      "requirements.\n")
    W("## 6. Power, registered in advance (§10)\n")
    W(f"With {cfg['n_source_files']} clustered source files this design reliably resolves a "
      "difference of ~0.20–0.25 and **cannot resolve differences below ~0.10**. A null "
      "result therefore means *\"no leak detectable at this corpus scale\"* — **not** that "
      "the husk is private.\n")
    art_metas = [json.loads(q.read_text()) for q in sorted((run / "artifacts").glob("*.meta.json"))]
    L.extend(usage_table(recs, None if a.no_judge else judged, cfg["judge"], art_metas))

    out = run / "summary.md"
    out.write_text("\n".join(L) + "\n")

    scored_path = run / "scored.jsonl"
    with scored_path.open("w") as fh:
        for r in fc:
            fh.write(json.dumps({**{k: r[k] for k in
                                    ("item_id", "arm", "replicate", "source_path",
                                     "true_domain_id", "attacker", "menu_seed",
                                     "truth_option")},
                                 **scored_choice(r)}) + "\n")
    print("\n".join(L))
    def _rel(p: Path) -> Path:
        return p.relative_to(REPO) if p.is_relative_to(REPO) else p

    print(f"\n-> {_rel(out)}\n-> {_rel(scored_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
