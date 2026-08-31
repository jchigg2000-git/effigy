#!/usr/bin/env python3
"""Husk the FILE PATHS of an already-husked tree, and make its imports resolve.

Husking file contents is not husking a repository. Measured 2026-08-19: a tree
whose every file body had been faithfully translated into an unrelated domain
still read

    stacks/api/internal/ingest/marc21.go
    stacks/api/internal/interchange/dublincore.go
    stacks/api/internal/api/holdings.go

MARC 21 is a library cataloguing standard and Dublin Core is library metadata, so
the source domain was recoverable from `ls -R` without opening a file. The
service takes a string and returns a string; the name of the file it came from
never enters the request, so no amount of content husking can fix this.

A second problem shows up only at tree scale: each file is husked independently,
so each one invents its own module name. One file imported
`logistics/internal/api` while another imported `stacks/internal/carriers`, and
the directories on disk were neither. The husk did not resolve against itself.

This pass fixes both:

  1. One model call proposes a path mapping for the WHOLE tree at once, plus a
     single module name. Doing it in one call is what makes the result
     self-consistent -- per-file naming is the defect being repaired, so
     repairing it per-file would reintroduce it.
  2. The mapping is applied to the filesystem.
  3. Import strings are rewritten to match, and the module name is normalised
     across every file, so the husk references its own layout.

The mapping is written to `_path_map.json` beside the tree. It is a
re-identification aid of the same class as the fpe pseudonym map -- it maps husked
paths back to source paths -- so it is written to the tree being reviewed ONLY
because that tree is disposable eval output. Never ship it alongside a husk you
are sending anywhere.

    python3 evals/husk_paths.py --tree /tmp/x/ --target logistics-dispatch
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "husk-api"))

SOURCE_EXT = {".py", ".go", ".ts", ".tsx", ".js", ".mod", ".sum", ".json",
               ".html", ".css", ".sql", ".mrk"}

PROMPT = """You are renaming the files of a codebase so that its file and directory names
match the domain its code has already been rewritten into.

The code in this repository is about: **{target}**

Below are the current paths. They still carry names from the ORIGINAL problem
domain, which must not survive. Propose a new path for each one.

Rules:
- Keep the directory DEPTH and the file EXTENSION of every path exactly as-is.
- Keep structural directory names that carry no domain meaning: api, app, src,
  cmd, internal, components, testdata, store, model.
- Rename any segment that carries meaning from the original domain, including
  the repository root directory and the binary name under cmd/.
- Use names a working engineer in the {target} domain would choose.
- Be consistent: the same concept renamed the same way everywhere.
- Do not invent new files or drop any.

Also propose ONE Go module name for the whole repository, lowercase, no slashes.

Current paths:
{paths}

Reply with ONLY a JSON object, no prose, no code fence:
{{"module": "<name>", "paths": {{"<old path>": "<new path>", ...}}}}
Every path above must appear exactly once as a key."""


def collect(tree: Path) -> list[str]:
    return sorted(
        str(p.relative_to(tree))
        for p in tree.rglob("*")
        if p.is_file() and not p.name.startswith("_") and p.suffix in SOURCE_EXT
    )


def propose(target: str, paths: list[str], model: str) -> dict:
    from openai import OpenAI  # noqa: PLC0415

    c = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"], timeout=300)
    r = c.chat.completions.create(
        model=model, temperature=0, max_tokens=4000,
        messages=[{"role": "user", "content": PROMPT.format(
            target=target, paths="\n".join(paths))}])
    raw = (r.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise SystemExit(f"unparseable mapping: {raw[:200]!r}")
    return json.loads(m.group(0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--model", default="Qwen/Qwen2.5-Coder-32B-Instruct",
                    help="model that proposes the mapping; a naming task, not a husking task")
    a = ap.parse_args()

    from dotenv import load_dotenv  # noqa: PLC0415
    load_dotenv(REPO / "husk-api" / ".env")

    tree = Path(a.tree).resolve()
    paths = collect(tree)
    print(f"{len(paths)} paths in {tree}")
    if not paths:
        raise SystemExit(f"no source files found under {tree} — check SOURCE_EXT")

    doc = propose(a.target, paths, a.model)
    mapping: dict[str, str] = doc["paths"]
    module = re.sub(r"[^a-z0-9]", "", doc.get("module", "app").lower()) or "app"

    missing = [p for p in paths if p not in mapping]
    if missing:
        print(f"WARNING: model omitted {len(missing)} path(s); left unrenamed: {missing[:4]}")
    for p in missing:
        mapping[p] = p

    # Old package dir -> new package dir, for rewriting Go import strings. Longest
    # first so nested dirs are replaced before their parents.
    dir_map: dict[str, str] = {}
    for old, new in mapping.items():
        od, nd = str(Path(old).parent), str(Path(new).parent)
        if od != "." and od != nd:
            dir_map[od] = nd
    dir_pairs = sorted(dir_map.items(), key=lambda kv: -len(kv[0]))

    staged = tree.parent / (tree.name + ".renamed")
    if staged.exists():
        shutil.rmtree(staged)

    renamed = skipped = 0
    for old, new in mapping.items():
        src, dst = tree / old, staged / new
        if not src.is_file():
            # The model can hallucinate a key that was never in the input. Skip
            # it rather than dying halfway through and leaving a half-copied
            # tree behind -- the original is deleted at the end, so a crash mid
            # -copy destroys the input.
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        renamed += old != new
    if skipped:
        print(f"WARNING: model proposed {skipped} path(s) that do not exist; skipped")

    # Rewrite import strings and normalise the module name so the husk resolves
    # against its own layout.
    rewrites = 0
    for p in staged.rglob("*"):
        if not p.is_file() or p.suffix not in {".py", ".go", ".ts", ".tsx", ".js", ".mod", ".json"}:
            continue
        text = before = p.read_text(encoding="utf-8", errors="replace")
        for od, nd in dir_pairs:
            # Only inside quoted import-ish strings, so prose is untouched.
            text = re.sub(rf'"([a-z0-9_-]+/)?{re.escape(od)}(/|")',
                          lambda m: f'"{m.group(1) or ""}{nd}{m.group(2)}', text)
        # Any leading module segment in a quoted path -> the one module name.
        text = re.sub(r'"([a-z][a-z0-9_-]*)/(internal|cmd|app)/',
                      rf'"{module}/\2/', text)
        text = re.sub(r"^module\s+\S+", f"module {module}", text, flags=re.M)
        if text != before:
            p.write_text(text, encoding="utf-8")
            rewrites += 1

    (staged / "_path_map.json").write_text(json.dumps(
        {"target": a.target, "module": module, "mapping_model": a.model,
         "renamed": renamed, "files_rewritten": rewrites,
         "WARNING": "maps husked paths back to source paths; never ship beside a husk",
         "paths": mapping}, indent=2) + "\n")

    shutil.rmtree(tree)
    staged.rename(tree)
    print(f"renamed {renamed}/{len(paths)} paths, rewrote imports in {rewrites} files")
    print(f"module -> {module}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
