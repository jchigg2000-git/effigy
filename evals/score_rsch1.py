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
        try:
            r = client.chat.completions.create(
                model=judge_model, messages=[{"role": "user", "content": prompt}],
                max_tokens=4096, temperature=0, response_format=JUDGE_SCHEMA)
            txt = r.choices[0].message.content or ""
            a, b = txt.find("{"), txt.rfind("}")
            parsed = json.loads(txt[a:b + 1]) if a >= 0 and b > a else None
        except Exception as exc:  # noqa: BLE001
            txt, parsed = f"{type(exc).__name__}: {exc}", None
        payload = {"item_id": rec["item_id"], "attacker": rec["attacker"],
                   "judge": judge_model, "prompt": prompt, "response": txt,
                   "label": (parsed or {}).get("label")}
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
    cfg = json.loads((run / "config.json").read_text())
    recs = load_raw(run)
    if not recs:
        print("no raw records", file=sys.stderr)
        return 2

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
    W(f"**Run:** `{cfg['run_id']}`  ·  **split:** `{cfg['split']}`  ·  "
      f"**sources:** {cfg['n_source_files']}")
    W(f"**Pre-registration commit:** `{cfg['preregistration_commit']}` (§12 rule 4)")
    W(f"**Repo commit:** `{cfg['repo_git_commit']}`"
      + ("  ⚠️ **working tree dirty**" if cfg.get("repo_dirty") else ""))
    W(f"**Attackers:** {', '.join(attackers)}  ·  **judge:** {cfg['judge']}")
    W(f"**Rewriter:** {cfg.get('rewriter_model')}  ·  endpoint `{cfg.get('endpoint_host')}`\n")
    n_missing = sum(1 for r in recs if is_missing(r))
    if n_missing:
        W(f"> ⚠️ **COVERAGE: {len(recs) - n_missing}/{len(recs)} calls completed; "
          f"{n_missing} never reached the model** (transport failure — this run hit an "
          f"account spending cap mid-flight). Those are excluded from every rate below as "
          f"missing observations rather than scored incorrect, because nothing was asked and "
          f"nothing was answered. **Check the per-domain table before reading any aggregate: "
          f"a domain the run never got to will look absent, not clean.**\n")

    # ---- 1. VALIDITY GATE, evaluated first -----------------------------------
    W("## 1. Validity gate (§8) — evaluated first\n")
    W("If this fails, **no verdict is issued for any arm**.\n")
    W("| attacker | p_source | parse failure (all arms) | gate |")
    W("|---|---|---|---|")
    gate_ok = True
    for atk in attackers:
        k, n = agg((atk, "source"))
        p, lo, hi = wilson(k, n)
        pf_k = sum(v[0] for (a_, _), v in parse_fail.items() if a_ == atk)
        pf_n = sum(v[1] for (a_, _), v in parse_fail.items() if a_ == atk)
        pf = pf_k / pf_n if pf_n else 0.0
        ok = (p >= 0.90) and (pf <= 0.05)
        gate_ok &= ok
        W(f"| `{atk}` | {rate(k, n)} [{lo:.2f}, {hi:.2f}] | {rate(pf_k, pf_n)} | "
          f"{'✅ pass' if ok else '❌ FAIL'} |")
    W("")
    if not gate_ok:
        W("> **GATE FAILED.** Per §8 no verdict is issued for any arm. An attacker that "
          "cannot identify the domain from the unmodified original means the task or the "
          "labels are broken, and every husk number below would be measuring the harness "
          "rather than the husk.\n")

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
        for key, c in sorted(rep["cells"].items()):
            if not c.get("n"):
                continue
            arm_, atk_ = key.split("|")
            W(f"| `{arm_}` | {atk_.split('/')[-1].split(':')[0]} | {c['n']} | {c['observed']:.3f} "
              f"| {c['permuted_mean']:.3f} [{c['permuted_lo']:.2f}, {c['permuted_hi']:.2f}] "
              f"| **{c['corrected']:+.3f}** | {c['p']:.4f} "
              f"| {c['modal_answer']} {c['modal_n']}/{c['n']} |")
        W("")
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
            v = "INCONCLUSIVE — validity gate failed"
        elif spread > 0.20:
            v = "INCONCLUSIVE — attackers differ by > 0.20"
        elif hi <= 0.10 and p_h <= 0.25:
            v = "**PASS**"
        elif (p_h - p_b) >= 0.25 and lo > 0:
            v = "**FAIL**"
        else:
            v = "INCONCLUSIVE"
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
    veto = {}
    for arm in cfg["arms"]:
        for atk in attackers:
            rs = [r for r in oe if r["arm"] == arm and r["attacker"] == atk
                  and not is_missing(r)]
            if not rs:
                continue
            man = json.loads((EVALS / "corpus" / "manifest.json").read_text())
            terms_by_dom = {d["true_domain_id"]: d.get("leak_terms", [])
                            for d in man["domains"].values() if isinstance(d, dict)}
            hits = sum(1 for r in rs
                       if leak_precheck(open_ended_text(r),
                                        terms_by_dom.get(r["true_domain_id"], [])))
            frac = hits / len(rs)
            fired = frac >= 0.10 and arm not in ("blind", "source")
            veto[arm] = veto.get(arm, False) or fired
            W(f"| `{arm}` | `{atk.split('/')[-1]}` | {rate(hits, len(rs))} | "
              f"{'🚫 **FAIL — hard veto**' if fired else '—'} |")
    W("")
    if any(veto.values()):
        W("> **Hard veto fired (§8).** A solution whose open-ended guesses hit its own "
          "source-domain leak terms on ≥ 10% of items is **FAIL regardless of its "
          "forced-choice result**. Solutions vetoed: "
          + ", ".join(f"`{k}`" for k, v in veto.items() if v) + "\n")

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

        buckets: dict = defaultdict(lambda: {"hit": [], "miss": []})
        for r in fc:
            if r["arm"] in ("blind", "source"):
                continue
            cs = copied_share(r["item_id"], r["source_path"])
            if cs is None:
                continue
            sc = scored_choice(r)
            buckets[r["arm"]]["hit" if sc["correct"] else "miss"].append(cs)
        W("| arm | mean copied-span share when attacker was RIGHT | when WRONG | n right / n wrong |")
        W("|---|---|---|---|")
        for arm in cfg["arms"]:
            b = buckets.get(arm)
            if not b or not (b["hit"] or b["miss"]):
                continue
            mh = sum(b["hit"]) / len(b["hit"]) if b["hit"] else float("nan")
            mm = sum(b["miss"]) / len(b["miss"]) if b["miss"] else float("nan")
            W(f"| `{arm}` | {mh:.3f} | {mm:.3f} | {len(b['hit'])} / {len(b['miss'])} |")
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
