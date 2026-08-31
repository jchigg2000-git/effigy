#!/usr/bin/env python3
"""Model selection sweep for `llm-translation`: which backend preserves code structure?

Effigy husks SOURCE CODE so an LLM can review its architecture. The whole
technique is worthless if the rewrite destroys the architecture on the way, so
the one question that decides which backend to recommend is:

    does the husk still contain the same program shape as the source?

That is measured deterministically here — no attacker, no judge, no model in the
scoring loop. Whether a husk leaks its source DOMAIN is a different question
about the technique rather than the backend, and it belongs to RSCH-1
(`preregistration.md`). Ranking backends by domain-vocabulary leakage would be a
data-masking metric applied to a code-masking problem, and it is trivially won
by a model that emits nothing.

THREE GATES, THEN A SCORE
-------------------------
1. RETURNED CODE  — non-empty, and free of reasoning-block text. The shipped
   solution strips code fences and nothing else, so a `<think>` block lands in
   the husk verbatim. Measured, not silently cleaned: cleaning it would hide a
   real defect in the service.
2. STILL PARSES   — Go via `gofmt -e`; TS/TSX via `tsc`, counting only TS1xxx
   syntax diagnostics (TS2xxx type errors are expected, since the husk is
   compiled with no imports resolvable). A husk that does not parse is useless
   no matter how similar its token counts are, and this is the signal that
   counter-matching alone misses.
3. STRUCTURE SCORE — per-key relative error between input and output structural
   counters, averaged and inverted. 1.0 is perfect preservation.

Selection runs on the SELECTION split only; RSCH-1 confirms on the held-out
split (see preregistration.md amendment A1).

    python3 evals/run_models.py --models a,b,c
    python3 evals/run_models.py --list-splits
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
EVALS = REPO / "evals"
RUNS = EVALS / "runs"
MANIFEST = EVALS / "corpus" / "manifest.json"

sys.path.insert(0, str(REPO / "husk-api"))
sys.path.insert(0, str(EVALS))

import counters  # noqa: E402

REASONING_MARKERS = ("<think>", "</think>", "<PAD>", "<|")

# The counters that describe program SHAPE. Deliberately excludes string_literals
# and bytes: llm-translation is supposed to rewrite those, and scoring a model
# down for doing its job would invert the metric.
SHAPE_KEYS = ("funcs", "structs", "interfaces", "imports", "exports", "max_brace_depth")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def load_manifest() -> dict:
    if not MANIFEST.exists():
        raise SystemExit("no corpus manifest; run: evals/run_eval.py --refresh-manifest")
    return json.loads(MANIFEST.read_text())


def split_domains(man: dict) -> tuple[list[str], list[str]]:
    """Deterministic selection/held-out split BY DOMAIN, from the manifest alone."""
    domains = sorted({a["domain_dir"] for a in man["artifacts"]})
    return domains[0::2], domains[1::2]


# ------------------------------------------------------------------- parsing --
def parses(text: str, language: str) -> tuple[bool, str]:
    """Syntax-only check. Returns (ok, detail)."""
    suffix = {"go": ".go", "ts": ".ts", "tsx": ".tsx"}[language]
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as fh:
        fh.write(text)
        path = fh.name
    try:
        if language == "go":
            p = subprocess.run(["gofmt", "-e", path], capture_output=True, text=True, timeout=30)
            return (p.returncode == 0, p.stderr.strip().splitlines()[0][:120] if p.stderr else "")
        # tsc reports syntax errors as TS1xxx and type errors as TS2xxx. Only the
        # former matter: the husk is compiled standalone, so every import is
        # unresolvable and TS2xxx is guaranteed noise.
        p = subprocess.run(
            ["tsc", "--noEmit", "--skipLibCheck", "--allowJs", "--jsx", "react-jsx",
             "--target", "esnext", "--moduleResolution", "bundler", path],
            capture_output=True, text=True, timeout=90,
        )
        syntax = [ln for ln in p.stdout.splitlines() if ": error TS1" in ln]
        return (not syntax, syntax[0][:120] if syntax else "")
    except subprocess.TimeoutExpired:
        return (False, "parse check timed out")
    except FileNotFoundError as e:
        return (True, f"parser unavailable ({e.filename}); parse gate skipped")
    finally:
        os.unlink(path)


def structure_score(ci: dict, co: dict) -> tuple[float, dict]:
    """Mean per-key relative error, inverted. 1.0 = perfectly preserved shape."""
    per = {}
    for k in SHAPE_KEYS:
        a, b = ci.get(k, 0), co.get(k, 0)
        if a == 0 and b == 0:
            continue
        per[k] = round(1.0 - min(1.0, abs(b - a) / max(a, 1)), 3)
    return (round(sum(per.values()) / len(per), 3) if per else 0.0, per)


# ---------------------------------------------------------------- one case --
def evaluate_case(model: str, art: dict) -> dict:
    import app.solutions.llm_translation as llm  # noqa: PLC0415

    src = (REPO / art["path"]).read_text(encoding="utf-8")
    rec: dict = {
        "model": model, "path": art["path"], "domain": art["domain_dir"],
        "language": art["language"], "input_sha256": art["sha256"],
        "input_lines": art["lines"],
    }
    t0 = time.time()
    prev = os.environ.get("LLM_MODEL")
    os.environ["LLM_MODEL"] = model
    try:
        out, _meta = llm.husk(src, 1, {})
    except Exception as exc:  # noqa: BLE001
        rec |= {"gate": "returned_code", "failure": f"{type(exc).__name__}: {str(exc)[:150]}",
                "latency_s": round(time.time() - t0, 1)}
        return rec
    finally:
        if prev is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = prev

    rec["latency_s"] = round(time.time() - t0, 1)
    rec["output_sha256"] = sha256_text(out)
    rec["output_lines"] = out.count("\n") + 1

    if not out.strip():
        return rec | {"gate": "returned_code", "failure": "empty output"}
    marker = next((m for m in REASONING_MARKERS if m in out), None)
    if marker:
        return rec | {"gate": "returned_code",
                      "failure": f"reasoning block in output ({marker!r})"}

    ok, detail = parses(out, art["language"])
    rec["parse_detail"] = detail
    if not ok:
        return rec | {"gate": "parses", "failure": f"does not parse: {detail}"}

    ci = counters.count(src, art["language"])
    co = counters.count(out, art["language"])
    score, per = structure_score(ci, co)
    return rec | {"gate": "passed", "failure": None, "structure_score": score,
                  "per_key": per, "counters": {"input": ci, "output": co}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", help="comma-separated model ids")
    ap.add_argument("--split", choices=["selection", "heldout"], default="selection")
    ap.add_argument("--list-splits", action="store_true")
    ap.add_argument("--limit", type=int, help="max artifacts per model (screening runs)")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()

    man = load_manifest()
    sel, held = split_domains(man)
    if a.list_splits:
        print(f"selection domains: {sel}\nheld-out domains : {held}")
        return 0
    if not a.models:
        ap.error("--models is required")

    from dotenv import load_dotenv  # noqa: PLC0415
    load_dotenv(REPO / "husk-api" / ".env")

    wanted = set(sel if a.split == "selection" else held)
    arts = [x for x in man["artifacts"] if x["domain_dir"] in wanted]
    if not arts:
        raise SystemExit(f"no artifacts in the {a.split} split ({sorted(wanted)})")
    dropped = 0
    if a.limit and len(arts) > a.limit:
        dropped = len(arts) - a.limit
        arts = arts[: a.limit]

    models = [m.strip() for m in a.models.split(",") if m.strip()]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = RUNS / f"{stamp}-model-sweep-{a.split}"
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"{len(models)} models x {len(arts)} artifacts = {len(models)*len(arts)} calls "
          f"[{a.split}: {', '.join(sorted(wanted))}]")
    if dropped:
        # Never let a bounded run read as full coverage.
        print(f"NOTE: --limit dropped {dropped} artifact(s); this is a screening run, "
              f"not full coverage")
    print()

    def work(job):
        m, art = job
        r = evaluate_case(m, art)
        tag = {"passed": "ok ", "parses": "PARSE", "returned_code": "CODE"}[r["gate"]]
        detail = (f"struct={r['structure_score']}" if r["gate"] == "passed"
                  else r["failure"][:50])
        print(f"  {tag:5s} {r['latency_s']:6.1f}s {m.split('/')[-1][:30]:30s} "
              f"{Path(art['path']).name:24s} {detail}")
        return r

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(work, [(m, art) for m in models for art in arts]))
    (outdir / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    summary = []
    for m in models:
        rs = [r for r in rows if r["model"] == m]
        ok = [r for r in rs if r["gate"] == "passed"]
        lat = sorted(r["latency_s"] for r in rs)
        summary.append({
            "model": m, "cases": len(rs), "passed": len(ok),
            "no_code": sum(1 for r in rs if r["gate"] == "returned_code"),
            "parse_fail": sum(1 for r in rs if r["gate"] == "parses"),
            "mean_structure_score": round(sum(r["structure_score"] for r in ok) / len(ok), 3)
            if ok else None,
            "p50_latency_s": lat[len(lat) // 2] if lat else None,
        })

    print(f"\n{'model':46s} {'pass':>5s} {'nocode':>7s} {'parsefail':>10s} "
          f"{'structure':>10s} {'p50 s':>7s}")
    for s in summary:
        print(f"{s['model'][:46]:46s} {s['passed']:>5d} {s['no_code']:>7d} "
              f"{s['parse_fail']:>10d} "
              f"{(s['mean_structure_score'] if s['mean_structure_score'] is not None else '-'):>10} "
              f"{(s['p50_latency_s'] if s['p50_latency_s'] is not None else '-'):>7}")

    eligible = [s for s in summary if s["cases"] and s["passed"] == s["cases"]]
    ranked = sorted(eligible, key=lambda s: (-s["mean_structure_score"], s["p50_latency_s"]))
    (outdir / "config.json").write_text(json.dumps({
        "run_id": outdir.name, "split": a.split, "split_domains": sorted(wanted),
        "artifacts_evaluated": len(arts), "artifacts_dropped_by_limit": dropped,
        "endpoint_host": urlparse(os.environ.get("LLM_BASE_URL", "")).netloc,
        "models": models, "manifest_sha256": sha256_text(MANIFEST.read_text()),
        "criterion": "code structure preservation; see module docstring",
        "note": "SELECTION result. Never cited as support for C1 (preregistration.md A1).",
    }, indent=2) + "\n")
    (outdir / "summary.json").write_text(json.dumps(
        {"summary": summary, "ranked": ranked,
         "gate_rule": "must return code AND parse on every case to be ranked"}, indent=2) + "\n")

    print()
    if ranked:
        w = ranked[0]
        print(f"best structure preservation: {w['model']} "
              f"(score {w['mean_structure_score']}, p50 {w['p50_latency_s']}s)")
    else:
        print("no model cleared both gates on every case — nothing ranked")
    print(f"-> {outdir.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
