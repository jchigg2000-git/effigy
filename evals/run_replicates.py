#!/usr/bin/env python3
"""Husk a tree N times with the same settings, score every run, report the spread.

Why this exists: on 2026-08-19 the same prompt, model, corpus and target were run
twice and returned 8 and 14 leak lines. `llm-translation` is not byte-stable, and
the run-to-run spread is larger than most of the differences that had been
reported between prompt revisions up to that point. Every single-run comparison in
this repository before that date is therefore unadjudicated, not wrong — the
measurement simply cannot separate a real effect from a resample.

So: no prompt revision is accepted on one run. This script is the acceptance
gate. It reports mean and full range across replicates, and the ratchet rule is
that a challenger must beat the champion's mean by more than the champion's own
observed range, without losing shape fidelity.

    python3 evals/run_replicates.py --model Qwen/Qwen2.5-Coder-7B-Instruct \
        --target music-streaming --src /tmp/sibling-src --runs 3 \
        --label prompt-v4 --out evals/runs/<run>/replicates-v4.json

The husk trees land under --workdir (default /tmp/ratchet) and are NOT committed:
they are husks of private source and carry identifiers that survive husking
(see runs/20260819-prompt-fix-32b/RESULT.md).
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from score_husk import score_file, build_pattern  # noqa: E402

TRACKED = ("domain_retention", "leak_lines", "code_verbatim", "ident_retention",
           "shape_fidelity", "copied_span_share")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--terms", default="electric-transmission")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", required=True, help="identifies the prompt revision under test")
    ap.add_argument("--workdir", default="/tmp/ratchet")
    ap.add_argument("--max-tokens", default="8192")
    ap.add_argument("--out")
    ap.add_argument("--with-gate", action="store_true",
                    help="leave the request-path passthrough gate ENABLED during husking. "
                         "Off by default, and the default is the important part: with the gate "
                         "live, husk_tree records a FAIL for every refused file and writes "
                         "nothing, so the arm gets scored only on the husks that passed — the "
                         "worst ones are silently dropped and the arm's mean flatters itself. "
                         "That bias produced a 0.116-vs-0.169 'decisive win' on 2026-08-19 that "
                         "evaporated to 0.188 on re-run. Retries have the same effect.")
    ap.add_argument("--rescore", action="store_true",
                    help="score the trees already under --workdir instead of husking again. "
                         "Those trees ARE the measured artifacts; re-husking would measure "
                         "different ones, since llm-translation is not byte-stable.")
    a = ap.parse_args()

    pattern = build_pattern(a.terms)
    src_root = Path(a.src).resolve()
    work = Path(a.workdir)
    work.mkdir(parents=True, exist_ok=True)

    runs = []
    for i in range(1, a.runs + 1):
        out = work / f"{a.label}-run{i}"
        print(f"\n--- {a.label} replicate {i}/{a.runs}")
        if a.rescore:
            if not out.is_dir():
                print(f"  no tree at {out}; skipping")
                continue
        else:
            subprocess.run(["rm", "-rf", str(out)], check=True)
        gate_off = {} if a.with_gate else {
            "HUSK_CHECK_RUN_LINES": "999999", "HUSK_CHECK_RUN_SHARE": "9",
            "HUSK_CHECK_COPIED_SHARE": "9", "HUSK_CHECK_RETENTION": "9",
            "HUSK_CHECK_RATIO": "9", "HUSK_CHECK_RETRIES": "0",
            "HUSK_CHECK_MODULE_NAMES": "0"}
        env_cmd = None if a.rescore else ["env", *(f"{k}={v}" for k, v in gate_off.items()), f"LLM_MAX_TOKENS={a.max_tokens}",
                   str(HERE.parent / "husk-api" / ".venv" / "bin" / "python"),
                   str(HERE / "husk_tree.py"), "--model", a.model,
                   "--target", a.target, "--src", str(src_root),
                   "--out", str(out), "--workers", "3"]
        if env_cmd is not None:
            proc = subprocess.run(env_cmd, capture_output=True, text=True)
            sys.stdout.write(proc.stdout[-800:])
            if proc.returncode != 0:
                print(f"  husk run {i} returned {proc.returncode}; scoring what landed")

        files = {}
        for hp in sorted(out.rglob("*")):
            if not hp.is_file() or hp.name.startswith("_"):
                continue
            rel = hp.relative_to(out)
            sp = src_root / rel
            if sp.is_file():
                full = score_file(sp.read_text(encoding="utf-8"),
                                  hp.read_text(encoding="utf-8"),
                                  hp.suffix, pattern)
                # Compact: the full per-file record is available from
                # score_husk.py directly. Three replicates x several revisions
                # of the whole record makes an unreadable file.
                files[str(rel)] = {k: full[k] for k in (
                    "whole_file_ratio", "code_verbatim", "ident_retention",
                    "domain_retention", "shape_fidelity", "leak_lines",
                    "leak_lines_verbatim", "copied_span_share",
                    "copied_span_lines", "longest_span", "copied_spans",
                    "passthrough", "leak_terms")}
        rows = list(files.values())
        n = len(rows) or 1
        runs.append({
            "replicate": i,
            "files": len(rows),
            "passthrough_files": sum(1 for r in rows if r["passthrough"]),
            "leak_lines": sum(r["leak_lines"] for r in rows),
            "copied_span_lines": sum(r["copied_span_lines"] for r in rows),
            "files_with_span_20plus": sum(1 for r in rows if r["longest_span"] >= 20),
            **{k: round(sum(r[k] for r in rows) / n, 3)
               for k in TRACKED if k != "leak_lines"},
            "per_file": files,
        })
        print(f"  -> domain_retention {runs[-1]['domain_retention']:.2f}  "
              f"copied_span {runs[-1]['copied_span_share']:.1%} "
              f"({runs[-1]['copied_span_lines']}L, {runs[-1]['files_with_span_20plus']} files >=20) "
              f"leak_lines {runs[-1]['leak_lines']}  "
              f"shape {runs[-1]['shape_fidelity']:.2f}  "
              f"passthrough {runs[-1]['passthrough_files']}")

    def agg(key: str) -> dict:
        vals = [r[key] for r in runs]
        return {"mean": round(statistics.fmean(vals), 3), "min": min(vals),
                "max": max(vals), "range": round(max(vals) - min(vals), 3),
                "values": vals}

    summary = {"label": a.label, "model": a.model, "target": a.target,
               "replicates": a.runs, "term_set": a.terms,
               **{k: agg(k) for k in ("domain_retention", "leak_lines",
                                      "code_verbatim", "ident_retention",
                                      "shape_fidelity", "passthrough_files",
                                      "copied_span_share", "copied_span_lines",
                                      "files_with_span_20plus")}}

    print(f"\n=== {a.label}, {a.runs} replicates, {a.model}"
          f"{'' if a.rescore else (' [gate ON — sample is biased]' if a.with_gate else ' [gate off]')}")
    short = [r["replicate"] for r in runs if r["files"] != max(x["files"] for x in runs)]
    if short:
        print(f"  WARNING: replicates {short} scored fewer files than their peers — "
              f"an unequal sample across replicates, check for husk failures")
    for k in ("domain_retention", "copied_span_share", "copied_span_lines",
              "files_with_span_20plus", "leak_lines", "shape_fidelity", "passthrough_files"):
        s = summary[k]
        print(f"  {k:<20} mean {s['mean']:<8} range {s['min']}–{s['max']}")

    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"summary": summary, "runs": runs}, indent=2) + "\n")
        print(f"\nwrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
