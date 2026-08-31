#!/usr/bin/env python3
"""Committed evaluation harness for the husking solutions.

Replaces husk-api/scripts/fpe_corpus_eval.py, which was fpe-only, printed to
stdout, saved nothing, and hardcoded corpus paths. Every number that ends up in
a doc must come from a file this wrote.

Subcommands
-----------
  --verify              re-hash the corpus against the manifest and check that
                        every PATHOLOGY.md symbol anchor still resolves
  --refresh-manifest    regenerate the manifest from the corpus tree
  --run SOLUTION        run one solution over the corpus, saving every artifact

Design notes
------------
* Results are self-describing: each record embeds the input's own sha256 plus
  the corpus commit, so you can always tell which bytes produced a number. This
  is what makes silent corpus drift detectable rather than invisible.
* Raw husk output is written to a sibling .output.txt verbatim, never embedded
  in JSON, so two runs can be diffed with ordinary tools.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVALS = REPO / "evals"
CORPUS = REPO / "corpus"
RUNS = EVALS / "runs"
MANIFEST = EVALS / "corpus" / "manifest.json"

sys.path.insert(0, str(REPO / "husk-api"))
sys.path.insert(0, str(EVALS))

import counters  # noqa: E402

_LANG_BY_SUFFIX = {".go": "go", ".ts": "ts", ".tsx": "tsx"}


# --------------------------------------------------------------------------
# The landmine. Read app/contract.py: the re-identification map "re-identifies
# the source, so it is sensitive: it is never logged or persisted." But fpe and
# literal_tagging both put it INTO meta when options.emit_map is set, and this
# harness calls husk() directly. A naive json.dump(meta) would commit a full
# pseudonym -> original map of the corpus into a repo intended to be public.
#
# Three guards, of which this is the one that cannot be forgotten.
# --------------------------------------------------------------------------
def assert_no_map(meta: dict, where: str) -> None:
    if "reidentify_map" in meta:
        raise SystemExit(
            f"REFUSING TO WRITE {where}: meta contains 'reidentify_map'. "
            "The harness must never persist a re-identification map. "
            "Do not set options.emit_map in cases.json."
        )


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def git(*args: str, cwd: Path = REPO) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def corpus_files() -> list[Path]:
    if not CORPUS.exists():
        return []
    return sorted(
        p
        for p in CORPUS.rglob("*")
        if p.is_file()
        and p.suffix in _LANG_BY_SUFFIX
        and "node_modules" not in p.parts
        and not p.name.endswith("_test.go")
        and ".test." not in p.name
    )


# ---------------------------------------------------------------- manifest --
def refresh_manifest() -> int:
    files = corpus_files()
    if not files:
        print("no corpus files found under corpus/ — nothing to record", file=sys.stderr)
        return 1
    entries = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        rel = p.relative_to(REPO).as_posix()
        entries.append(
            {
                "path": rel,
                "domain_dir": p.relative_to(CORPUS).parts[0],
                "language": _LANG_BY_SUFFIX[p.suffix],
                "sha256": sha256_text(text),
                "bytes": len(text.encode("utf-8")),
                "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
                "git_blob_oid": git("hash-object", str(p)),
            }
        )
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    prior = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    doc = {
        "generated_by": "evals/run_eval.py --refresh-manifest",
        # Domain labels and leak terms are AUTHORED, not derived. They are
        # preserved across refreshes so a regeneration cannot quietly reset the
        # ground truth the privacy eval scores against.
        "domains": prior.get("domains", {}),
        "artifacts": entries,
    }
    MANIFEST.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"manifest: {len(entries)} artifacts -> {MANIFEST.relative_to(REPO)}")
    if not doc["domains"]:
        print("WARNING: manifest has no 'domains' block. The privacy eval needs")
        print("         true_domain_id and leak_terms[] per domain before it can run.")
    return 0


def load_manifest() -> dict:
    if not MANIFEST.exists():
        raise SystemExit(f"no manifest at {MANIFEST.relative_to(REPO)}; run --refresh-manifest")
    return json.loads(MANIFEST.read_text())


# ------------------------------------------------------------------ verify --
_ANCHOR_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.M)


def verify() -> int:
    failures: list[str] = []
    man = load_manifest()

    for e in man["artifacts"]:
        p = REPO / e["path"]
        if not p.exists():
            failures.append(f"missing: {e['path']}")
            continue
        text = p.read_text(encoding="utf-8")
        if sha256_text(text) != e["sha256"]:
            failures.append(
                f"drift: {e['path']} sha256 changed since the manifest was written "
                f"(recorded {e['bytes']}B/{e['lines']}L)"
            )

    # Pathology anchors are SYMBOLS, never line numbers: line numbers drift the
    # first time anyone touches a file, which is how the superseded corpus rotted.
    pathology = CORPUS / "PATHOLOGY.md"
    if pathology.exists():
        body = pathology.read_text()
        haystack = "\n".join((REPO / e["path"]).read_text(encoding="utf-8")
                             for e in man["artifacts"] if (REPO / e["path"]).exists())
        for sym in _ANCHOR_RE.findall(body):
            if sym not in haystack:
                failures.append(f"pathology anchor vanished: {sym!r}")

    for f in failures:
        print(f"FAIL  {f}", file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} verification failure(s)", file=sys.stderr)
        return 1
    print(f"verify: OK — {len(man['artifacts'])} artifacts match the manifest")
    return 0


# --------------------------------------------------------------------- run --
def run_solution(slug: str, crumb_level: int, backend_slug: str | None) -> int:
    from app.registry import get  # noqa: PLC0415
    import app.solutions  # noqa: F401,PLC0415  (registers the plugins)

    man = load_manifest()
    entry = get(slug)
    if entry is None:
        raise SystemExit(f"unknown solution: {slug}")
    husk = entry.fn

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backend = backend_slug or os.environ.get("LLM_MODEL", "local")
    run_id = f"{stamp}-{slug}-{re.sub(r'[^A-Za-z0-9.-]+', '-', backend)}"
    outdir = RUNS / run_id
    (outdir / "husks").mkdir(parents=True, exist_ok=True)

    prereg_sha = git("log", "-1", "--format=%H", "--", "evals/preregistration.md")
    config = {
        "run_id": run_id,
        "solution": slug,
        "crumb_level": crumb_level,
        "started_at": stamp,
        "repo_git_commit": git("rev-parse", "HEAD"),
        "repo_dirty": bool(git("status", "--porcelain")),
        "preregistration_commit": prereg_sha,
        "manifest_sha256": sha256_text(MANIFEST.read_text()),
        "backend": {
            # base-URL HOST only, and never the API key.
            "base_url": os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
            "model": os.environ.get("LLM_MODEL", "qwen2.5-coder:14b"),
            "temperature": os.environ.get("LLM_TEMPERATURE", "0.2"),
        },
    }
    (outdir / "config.json").write_text(json.dumps(config, indent=2) + "\n")

    ok = failed = 0
    for e in man["artifacts"]:
        src = (REPO / e["path"]).read_text(encoding="utf-8")
        case_id = f"{slug}-L{crumb_level}-{Path(e['path']).name}"
        rec: dict = {
            "case_id": case_id,
            "run_id": run_id,
            "solution": slug,
            "crumb_level": crumb_level,
            "input": {k: e[k] for k in ("path", "language", "sha256", "bytes", "lines")},
            "corpus": {"git_commit": config["repo_git_commit"],
                       "manifest_sha256": config["manifest_sha256"]},
        }
        t0 = time.time()
        try:
            # options is empty by design: emit_map is never set here.
            out, meta = husk(src, crumb_level, {})
            assert_no_map(meta, f"{case_id}.json")
            outfile = outdir / "husks" / f"{case_id}.output.txt"
            outfile.write_text(out, encoding="utf-8")
            ci = counters.count(src, e["language"])
            co = counters.count(out, e["language"])
            rec |= {
                "output": {"path": outfile.relative_to(REPO).as_posix(),
                           "sha256": sha256_text(out), "bytes": len(out.encode()),
                           "lines": co["lines"]},
                "meta": meta,
                "counters": {"input": ci, "output": co, "delta": counters.delta(ci, co)},
                "error": None,
            }
            ok += 1
        except Exception as exc:  # noqa: BLE001 — a failing case is data, not a crash
            rec |= {"output": None, "meta": {}, "counters": {},
                    "error": f"{type(exc).__name__}: {exc}"}
            failed += 1
        rec["timing_ms"] = int((time.time() - t0) * 1000)
        assert_no_map(rec.get("meta", {}), f"{case_id}.json")
        (outdir / f"{case_id}.json").write_text(json.dumps(rec, indent=2) + "\n")
        print(f"  {'ok  ' if rec['error'] is None else 'FAIL'} {case_id}"
              f"{'' if rec['error'] is None else '  ' + rec['error']}")

    print(f"\n{run_id}: {ok} ok, {failed} failed -> {outdir.relative_to(REPO)}")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--refresh-manifest", action="store_true")
    ap.add_argument("--run", metavar="SOLUTION")
    ap.add_argument("--crumb-level", type=int, default=1)
    ap.add_argument("--backend", default=None, help="slug for the run id")
    a = ap.parse_args()

    if a.refresh_manifest:
        return refresh_manifest()
    if a.verify:
        return verify()
    if a.run:
        return run_solution(a.run, a.crumb_level, a.backend)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
