#!/usr/bin/env python3
"""Husk the whole corpus tree with one model, preserving directory structure.

The service husks ONE FILE per request, but several of the planted defects are
properties of the repository rather than of any file:

  * layering_violation      — a persistence package exists and every query lives
                              somewhere else. Invisible in `store.go` alone; the
                              evidence is the ABSENCE of queries there and their
                              presence in handlers.
  * duplicated_error_handling — an identical block repeated across four handlers
                              plus a hand-restated TypeScript validator.

A single-file evaluator cannot see either, so scoring a husker on them per-file
measures the harness, not the model. This produces a husked TREE so a multi-file
reviewer can see what a single-file reviewer structurally cannot.

Structure is preserved deliberately: path layout is itself part of the evidence
a reviewer uses, and flattening it would destroy the layering finding before the
evaluator ever sees it.

    python3 evals/husk_tree.py --model Qwen/Qwen2.5-Coder-7B-Instruct --target <target_id> --out /tmp/x
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "evals" / "corpus" / "manifest.json"
sys.path.insert(0, str(REPO / "husk-api"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True, help="destination root for the husked tree")
    ap.add_argument("--target", required=True,
                    help="catalog target_id, PINNED for the whole tree (see below)")
    ap.add_argument("--src", help="husk an arbitrary directory instead of the corpus "
                                  "(dogfooding: real code, no manifest)")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    from dotenv import load_dotenv  # noqa: PLC0415
    load_dotenv(REPO / "husk-api" / ".env")
    import app.solutions.llm_translation as llm  # noqa: PLC0415

    if a.src:
        root = Path(a.src).resolve()
        exts = {".py", ".go", ".ts", ".tsx", ".js"}
        arts = [{"path": str(p), "rel": str(p.relative_to(root)),
                 "lines": p.read_text().count("\n") + 1,
                 "language": p.suffix.lstrip(".")}
                for p in sorted(root.rglob("*"))
                if p.is_file() and p.suffix in exts
                and not any(x in p.parts for x in
                            (".venv", "node_modules", "__pycache__", "tests"))]
    else:
        man = json.loads(MANIFEST.read_text())
        arts = man["artifacts"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"husking {len(arts)} artifacts with {a.model} "
          f"[target={a.target}] -> {out}")

    def work(art: dict) -> dict:
        src_path = Path(art["path"])
        if not src_path.is_absolute():
            src_path = REPO / art["path"]
        src = src_path.read_text(encoding="utf-8")
        # Strip the leading "corpus/" so the husked tree is rooted at the app,
        # not at this repo's layout.
        rel = Path(art["rel"]) if "rel" in art else \
            Path(art["path"]).relative_to("corpus")
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        prev = os.environ.get("LLM_MODEL")
        os.environ["LLM_MODEL"] = a.model
        try:
            # Target is PINNED across the tree. The solution otherwise selects a
            # target by hashing each input, so a multi-file husk scatters across
            # unrelated domains -- one file becomes a recipe manager, the next
            # hotel rooms. Invisible when husking one file; fatal for a tree,
            # because no reviewer can read it as a single system and no
            # cross-file reference survives.
            husk, _meta = llm.husk(src, 1, {"target_id": a.target})
            dest.write_text(husk, encoding="utf-8")
            r = {"path": art["path"], "dest": str(rel), "ok": True,
                 "in_lines": art["lines"], "out_lines": husk.count("\n") + 1,
                 "latency_s": round(time.time() - t0, 1), "error": None}
        except Exception as exc:  # noqa: BLE001
            r = {"path": art["path"], "dest": str(rel), "ok": False,
                 "in_lines": art["lines"], "out_lines": 0,
                 "latency_s": round(time.time() - t0, 1),
                 "error": f"{type(exc).__name__}: {str(exc)[:140]}"}
        finally:
            if prev is None:
                os.environ.pop("LLM_MODEL", None)
            else:
                os.environ["LLM_MODEL"] = prev
        print(f"  {'ok  ' if r['ok'] else 'FAIL'} {r['latency_s']:6.1f}s "
              f"{r['in_lines']:>4}->{r['out_lines']:<4} {rel}"
              f"{'  ' + r['error'] if r['error'] else ''}")
        return r

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(work, arts))

    ok = sum(1 for r in rows if r["ok"])
    (out / "_husk_manifest.json").write_text(json.dumps(
        {"model": a.model, "target_id": a.target, "artifacts": len(arts),
         "ok": ok, "files": rows}, indent=2) + "\n")
    print(f"\n{ok}/{len(arts)} husked -> {out}")
    return 0 if ok == len(arts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
