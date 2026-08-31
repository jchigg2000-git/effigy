#!/usr/bin/env python3
"""Does a husk still smell the same? — the diagnostic-validity loop.

    cheap model husks it  ->  better model diagnoses the husk
                          ->  better model diagnoses the real code
                          ->  do the two diagnoses agree?

This measures the claim the project actually rests on: *a consumer LLM's
diagnosis of the husk stays valid for the source*. Every other metric in this
repo is a proxy for it. Structural counters ask whether the shape survived;
this asks whether the FINDINGS survived, which is what a user is buying.

ROLE ASSIGNMENT, AND WHY IT MATTERS
-----------------------------------
* **Husker — cheap, and in production LOCAL.** The husker sees the real source.
  Sending it to a hosted endpoint would leak the exact thing the technique
  protects. A hosted cheap model is used here as a *stand-in* so the rig does not
  require a local server; the finding transfers by model class, not by hosting.
  Any recommendation drawn from this must say "a model of this class, run
  locally."
* **Evaluator — strong, hosted.** This is the frontier model the product exists
  to let you safely use. It sees the husk. That is the whole point.

The evaluator also diagnoses the raw source, to produce the comparison baseline.
That is safe HERE only because the corpus is synthetic. Never do it to real
proprietary code — it is precisely the disclosure the tool prevents.

TWO SCORES PER CASE
-------------------
* **agreement** — F1 between the smell set found in the husk and the smell set
  the same evaluator found in the source. Measures "same diagnosis."
* **ground-truth recall** — of the defects PATHOLOGY.md says are planted in that
  file, how many the husk diagnosis found. Measures "right diagnosis," and does
  not depend on the evaluator being correct about the source.

Both are reported. Agreement alone would be satisfied by an evaluator that is
consistently wrong; recall alone ignores false positives the husk invents.

    python3 evals/run_smell_loop.py --huskers a,b --evaluator c
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
EVALS = REPO / "evals"
RUNS = EVALS / "runs"
MANIFEST = EVALS / "corpus" / "manifest.json"
PATHOLOGY = REPO / "corpus" / "PATHOLOGY.md"

sys.path.insert(0, str(REPO / "husk-api"))

# Domain-neutral smell taxonomy, one entry per planted defect class. Deliberately
# phrased without library or catalog vocabulary: the evaluator sees a husk that
# has been rewritten into some other domain, and a taxonomy carrying source-domain
# nouns would hand it the answer.
SMELLS = {
    "god_object": "One type holds several unrelated concerns at once (for example a raw "
                  "database handle plus logging plus configuration plus request routing), "
                  "and most functions are methods on it.",
    "inline_sql_in_handler": "A raw database query is executed directly inside a request "
                             "handler, with no persistence-layer call between them.",
    "layering_violation": "A persistence or data-access layer exists in the structure but is "
                          "bypassed — queries live in handlers or parsers instead.",
    "inline_magic_literals": "Configuration keys, route paths, protocol constants and error "
                             "prose appear as inline literals at their use sites rather than "
                             "named constants.",
    "concatenated_sql": "A query is assembled by appending string fragments across several "
                        "optional-filter branches, then joining them.",
    "deep_nested_switch": "A large switch on a string discriminant, where individual arms open "
                          "a further nested switch, with bare string constants as case labels.",
    "closure_over_mutable_state": "Zero-argument closures read and write variables captured "
                                  "from an enclosing scope, called from several branches; "
                                  "coupling runs through captured state rather than arguments.",
    "wide_positional_bind": "Many columns are bound positionally in a single call, coupled to "
                            "query column order by convention alone.",
    "duplicated_error_handling": "An identical error-handling block is repeated verbatim across "
                                 "several functions with no extracted helper.",
}

# PATHOLOGY.md id -> taxonomy key. The catalogue is the ground truth; this only
# renames it into the vocabulary the evaluator is shown.
P_TO_SMELL = {
    "P1": "god_object",
    "P2": "inline_sql_in_handler",
    "P3": "layering_violation",
    "P4": "inline_magic_literals",
    "P5": "concatenated_sql",
    "P6": "deep_nested_switch",
    "P7": "closure_over_mutable_state",
    "P8": "wide_positional_bind",
    "P9": "duplicated_error_handling",
}

EVAL_PROMPT = """You are reviewing one source file for architectural code smells.

The file may have been mechanically rewritten into an unfamiliar problem domain.
Ignore the subject matter entirely. Judge only the STRUCTURE.

For each smell below, decide whether this file exhibits it.

{catalogue}

Reply with ONLY a JSON object, no prose and no code fence:
{{"findings": [{{"smell": "<key>", "present": true|false, "evidence": "<=20 words, quoting a symbol or line from the file>"}}]}}

Include every key exactly once.

--- FILE ({language}) ---
{code}
--- END FILE ---"""


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def ground_truth() -> dict[str, set[str]]:
    """file -> set(smell keys), parsed from PATHOLOGY.md's anchor index."""
    gt: dict[str, set[str]] = {}
    for line in PATHOLOGY.read_text().splitlines():
        m = re.match(r"^\|\s*`[^`]+`\s*\|\s*(P\d)\s*\|\s*`([^`]+)`\s*\|", line)
        if m and m.group(1) in P_TO_SMELL:
            gt.setdefault(f"corpus/stacks/{m.group(2)}", set()).add(P_TO_SMELL[m.group(1)])
    return gt


def client():
    from openai import OpenAI  # noqa: PLC0415
    return OpenAI(base_url=os.environ["LLM_BASE_URL"],
                  api_key=os.environ["LLM_API_KEY"], timeout=300)


def diagnose(model: str, code: str, language: str) -> tuple[set[str], str | None]:
    """Ask the evaluator which smells are present. Returns (present_set, error)."""
    catalogue = "\n".join(f"- {k}: {v}" for k, v in SMELLS.items())
    try:
        r = client().chat.completions.create(
            model=model, temperature=0, max_tokens=2000,
            messages=[{"role": "user", "content": EVAL_PROMPT.format(
                catalogue=catalogue, language=language, code=code)}],
        )
        raw = (r.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        return set(), f"{type(exc).__name__}: {str(exc)[:140]}"

    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return set(), f"unparseable: {raw[:100]!r}"
    try:
        doc = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return set(), f"bad json: {e}"
    found = {f["smell"] for f in doc.get("findings", [])
             if f.get("present") and f.get("smell") in SMELLS}
    return found, None


def f1(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    tp = len(a & b)
    if not tp:
        return 0.0
    prec, rec = tp / len(a), tp / len(b)
    return round(2 * prec * rec / (prec + rec), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--huskers", required=True, help="comma-separated cheap model ids")
    ap.add_argument("--evaluator", required=True, help="strong model id")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()

    from dotenv import load_dotenv  # noqa: PLC0415
    load_dotenv(REPO / "husk-api" / ".env")
    import app.solutions.llm_translation as llm  # noqa: PLC0415

    gt = ground_truth()
    man = json.loads(MANIFEST.read_text())
    arts = [x for x in man["artifacts"] if x["path"] in gt]
    if not arts:
        raise SystemExit("no corpus artifact carries a pathology anchor")
    huskers = [m.strip() for m in a.huskers.split(",") if m.strip()]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = RUNS / f"{stamp}-smell-loop"
    (outdir / "husks").mkdir(parents=True, exist_ok=True)

    print(f"evaluator: {a.evaluator}")
    print(f"huskers  : {', '.join(huskers)}")
    print(f"files    : {len(arts)} pathology-bearing artifacts\n")

    # Baseline: the evaluator's diagnosis of the REAL code. One call per file,
    # reused across every husker, so adding a husker costs husk+diagnose only.
    print("baseline — diagnosing the real source")
    baseline: dict[str, set[str]] = {}
    for art in arts:
        src = (REPO / art["path"]).read_text(encoding="utf-8")
        found, err = diagnose(a.evaluator, src, art["language"])
        planted = gt[art["path"]]
        if err:
            # A failed baseline is NOT "this file has no smells". Storing an
            # empty set here would silently score every husk of this file against
            # a claim that the real file is clean, which reads as total
            # disagreement when the husk is in fact correct. Drop the file.
            print(f"  {Path(art['path']).name:24s} BASELINE FAILED — excluding: {err[:70]}")
            continue
        baseline[art["path"]] = found
        print(f"  {Path(art['path']).name:24s} found={len(found)} "
              f"planted={len(planted)} recall={len(found & planted)}/{len(planted)}")
    dropped = [x["path"] for x in arts if x["path"] not in baseline]
    if dropped:
        print(f"  NOTE: {len(dropped)} file(s) excluded for baseline failure: "
              f"{[Path(d).name for d in dropped]}")
    arts = [x for x in arts if x["path"] in baseline]
    if not arts:
        raise SystemExit("every baseline diagnosis failed; nothing to compare against")

    rows = []

    def work(job):
        model, art = job
        src = (REPO / art["path"]).read_text(encoding="utf-8")
        rec = {"husker": model, "path": art["path"], "language": art["language"],
               "planted": sorted(gt[art["path"]]),
               "baseline_source": sorted(baseline[art["path"]])}
        t0 = time.time()
        prev = os.environ.get("LLM_MODEL")
        os.environ["LLM_MODEL"] = model
        try:
            husk, _ = llm.husk(src, 1, {})
        except Exception as exc:  # noqa: BLE001
            os.environ["LLM_MODEL"] = prev or ""
            return rec | {"status": "husk_failed",
                          "error": f"{type(exc).__name__}: {str(exc)[:140]}",
                          "latency_s": round(time.time() - t0, 1)}
        finally:
            if prev is None:
                os.environ.pop("LLM_MODEL", None)
            else:
                os.environ["LLM_MODEL"] = prev
        rec["husk_latency_s"] = round(time.time() - t0, 1)

        name = f"{model.split('/')[-1]}--{Path(art['path']).name}.txt"
        (outdir / "husks" / name).write_text(husk, encoding="utf-8")
        rec["husk_sha256"] = sha256_text(husk)
        rec["husk_lines"] = husk.count("\n") + 1

        found, err = diagnose(a.evaluator, husk, art["language"])
        if err:
            return rec | {"status": "diagnose_failed", "error": err}
        planted = gt[art["path"]]
        rec |= {
            "status": "ok",
            "husk_findings": sorted(found),
            "agreement_f1": f1(found, baseline[art["path"]]),
            "gt_recall": round(len(found & planted) / len(planted), 3),
            "gt_recall_n": f"{len(found & planted)}/{len(planted)}",
        }
        print(f"  {model.split('/')[-1][:26]:26s} {Path(art['path']).name:24s} "
              f"agree={rec['agreement_f1']:<5} recall={rec['gt_recall_n']}")
        return rec

    print("\nloop — husk with the cheap model, diagnose the husk")
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(work, [(m, art) for m in huskers for art in arts]))

    (outdir / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    print(f"\n{'husker':34s} {'ok':>3s} {'agreement':>10s} {'gt recall':>10s} {'p50 husk s':>11s}")
    summary = []
    for m in huskers:
        rs = [r for r in rows if r["husker"] == m]
        ok = [r for r in rs if r["status"] == "ok"]
        lat = sorted(r.get("husk_latency_s", 0) for r in rs)
        s = {"husker": m, "cases": len(rs), "ok": len(ok),
             "mean_agreement_f1": round(sum(r["agreement_f1"] for r in ok) / len(ok), 3) if ok else None,
             "mean_gt_recall": round(sum(r["gt_recall"] for r in ok) / len(ok), 3) if ok else None,
             "p50_husk_latency_s": lat[len(lat) // 2] if lat else None}
        summary.append(s)
        print(f"{m[:34]:34s} {s['ok']:>3d} "
              f"{(s['mean_agreement_f1'] if s['mean_agreement_f1'] is not None else '-'):>10} "
              f"{(s['mean_gt_recall'] if s['mean_gt_recall'] is not None else '-'):>10} "
              f"{(s['p50_husk_latency_s'] if s['p50_husk_latency_s'] is not None else '-'):>11}")

    eligible = [s for s in summary if s["cases"] and s["ok"] == s["cases"]]
    ranked = sorted(eligible, key=lambda s: (-s["mean_gt_recall"], -s["mean_agreement_f1"]))
    (outdir / "config.json").write_text(json.dumps({
        "run_id": outdir.name, "evaluator": a.evaluator, "huskers": huskers,
        "endpoint_host": urlparse(os.environ.get("LLM_BASE_URL", "")).netloc,
        "files": [x["path"] for x in arts],
        "manifest_sha256": sha256_text(MANIFEST.read_text()),
        "baseline_source_findings": {k: sorted(v) for k, v in baseline.items()},
        "note": ("Huskers are hosted here as a STAND-IN for cheap LOCAL models. "
                 "In production the husker must run in-tenant; a hosted husker "
                 "leaks the source it exists to protect."),
    }, indent=2) + "\n")
    (outdir / "summary.json").write_text(json.dumps({"summary": summary, "ranked": ranked}, indent=2) + "\n")

    print()
    if ranked:
        w = ranked[0]
        print(f"best cheap husker: {w['husker']}  "
              f"(ground-truth recall {w['mean_gt_recall']}, agreement {w['mean_agreement_f1']})")
    else:
        print("no husker completed every case — nothing ranked")
    print(f"-> {outdir.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
