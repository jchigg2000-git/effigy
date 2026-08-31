#!/usr/bin/env python3
"""Mechanical acceptance gate for the corpus domains. `corpus/DOMAINS.md` §5.

Every check here is a gate the generated domains have to pass before RSCH-1 can
use them, and every one of them is mechanical on purpose — a generator that
reports its own work as passing is not evidence, and five generators reporting
in parallel is five times as much not-evidence.

    python3 evals/verify_domains.py                # all domains
    python3 evals/verify_domains.py qsolog         # one
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
MANIFEST = REPO / "evals" / "corpus" / "manifest.json"
TSC = REPO / "corpus" / "stacks" / "app" / "node_modules" / ".bin" / "tsc"

# A check that could not RUN is not a check that FAILED. Skips are tracked apart
# from failures so a fresh clone (no node_modules, hence no tsc) does not report
# the TS parse check as five broken domains -- but they are printed loudly,
# because a partial run must never be mistaken for a full pass.
SKIPS: list[str] = []

# §5.5 — `stacks` owns these; no other domain may contain any of them.
#
# Each is a FULL regex, not a bare prefix. An earlier version matched `\bmarc`,
# which flags every file containing the word "march" — a directive effective date
# in an unrelated domain read as library-cataloguing vocabulary. A gate whose
# false positives look exactly like real findings is worse than no gate, so the
# suffixes each term is allowed to take are now spelled out.
STACKS_VOCAB = [
    r"\bisbns?\b", r"\bmarc(?:21)?\b", r"\bdewey\b", r"\boclc\b", r"\blccns?\b",
    r"\bbibliographic(?:ally)?\b", r"\bpatrons?\b", r"\bborrowers?\b",
    r"\bcirculation\b", r"\bholdings?\b", r"\bshelfmarks?\b", r"\binterlibrary\b",
    r"\bshelflists?\b", r"\bcall numbers?\b",
]
# §5.6 — ordinary programming vocabulary, forbidden in any leak_terms list because
# it fires constantly on code that has nothing to do with the domain.
FORBIDDEN_TERMS = {"record", "index", "branch", "state", "zone", "region", "catalog",
                   "entry", "report", "item", "type", "name", "id", "code", "value",
                   "status", "data", "file", "line", "count", "list", "table"}
NEW_DOMAINS = ["qsolog", "meterworks", "tremorline", "loomshed", "tailwatch"]


def code_files(d: Path) -> list[Path]:
    return sorted(p for p in d.rglob("*")
                  if p.is_file() and p.suffix in (".go", ".ts", ".tsx")
                  and "node_modules" not in p.parts
                  and not p.name.endswith("_test.go") and ".test." not in p.name)


def nlines(p: Path) -> int:
    t = p.read_text(encoding="utf-8", errors="replace")
    return t.count("\n") + (1 if t and not t.endswith("\n") else 0)


def check(domain: str) -> list[str]:
    d = CORPUS / domain
    fails: list[str] = []
    if not d.exists():
        return [f"{domain}: directory does not exist"]

    files = code_files(d)

    # §5.1 — ten artifacts, every one inside the 40-400 line envelope.
    if len(files) != 10:
        fails.append(f"{domain}: expected 10 code files, found {len(files)}")
    for f in files:
        n = nlines(f)
        if not (40 <= n <= 400):
            fails.append(f"{domain}: {f.relative_to(CORPUS)} is {n} lines, "
                         f"outside the 40-400 envelope (prereg §1)")

    # §5.2 — Go parses.
    gos = [f for f in files if f.suffix == ".go"]
    if gos:
        r = subprocess.run(["gofmt", "-e", "-l", *[str(f) for f in gos]],
                           capture_output=True, text=True)
        if r.returncode != 0 or r.stdout.strip():
            fails.append(f"{domain}: gofmt -e failed: "
                         f"{(r.stdout + r.stderr).strip()[:400]}")

    # §5.3 — TS/TSX parses. Only TS1xxx counts: these compile standalone, so every
    # unresolved import raises TS2xxx noise that says nothing about syntax.
    tss = [f for f in files if f.suffix in (".ts", ".tsx")]
    if tss and TSC.exists():
        r = subprocess.run([str(TSC), "--noEmit", "--jsx", "react-jsx",
                            "--target", "ES2020", "--module", "ESNext",
                            "--moduleResolution", "bundler", "--skipLibCheck",
                            *[str(f) for f in tss]],
                           capture_output=True, text=True, cwd=REPO)
        syntax = [ln for ln in (r.stdout + r.stderr).splitlines()
                  if re.search(r"error TS1\d{3}:", ln)]
        if syntax:
            fails.append(f"{domain}: {len(syntax)} TS1xxx syntax error(s): "
                         + " | ".join(syntax[:3]))
    elif tss:
        SKIPS.append(f"{domain}: TS parse check (§5.3) — tsc not found")

    # §5.4 — self-contained.
    r = subprocess.run(["grep", "-rn", r"\.\./\.\.", str(d)],
                       capture_output=True, text=True)
    if r.stdout.strip():
        fails.append(f"{domain}: path escape(s): {r.stdout.strip()[:200]}")

    # §5.5 — no stacks vocabulary.
    for f in files:
        body = f.read_text(encoding="utf-8", errors="replace").lower()
        hits = [w for w in STACKS_VOCAB if re.search(w, body)]
        if hits:
            fails.append(f"{domain}: {f.relative_to(CORPUS)} carries stacks "
                         f"vocabulary: {sorted(set(hits))}")
    return fails


def check_leak_terms() -> list[str]:
    """§5.6 — authored, sized, pairwise disjoint, free of generic vocabulary."""
    fails: list[str] = []
    if not MANIFEST.exists():
        return ["manifest missing — run: python3 evals/run_eval.py --refresh-manifest"]
    doms = json.loads(MANIFEST.read_text()).get("domains", {})
    real = {k: v for k, v in doms.items() if isinstance(v, dict) and "true_domain_id" in v}
    if len(real) < 6:
        fails.append(f"manifest declares {len(real)} domains; prereg §2 requires >= 6")

    menu_ids = {o["id"] for o in
                json.loads((REPO / "evals" / "domains.json").read_text())["options"]}
    seen: Counter = Counter()
    for name, d in real.items():
        terms = [t.lower().strip() for t in d.get("leak_terms", [])]
        if d["true_domain_id"] not in menu_ids:
            fails.append(f"{name}: true_domain_id '{d['true_domain_id']}' is not in "
                         f"evals/domains.json")
        if not (15 <= len(terms) <= 25):
            fails.append(f"{name}: {len(terms)} leak_terms, §5.6 wants 15-25")
        bad = sorted(set(terms) & FORBIDDEN_TERMS)
        if bad:
            fails.append(f"{name}: leak_terms contain generic vocabulary {bad} — "
                         f"these fire on unrelated code and inflate the veto")
        seen.update(set(terms))
    dupes = sorted(t for t, n in seen.items() if n > 1)
    if dupes:
        fails.append(f"leak_terms are NOT pairwise disjoint across domains: {dupes} — "
                     f"a shared term makes the §8 hard veto ambiguous about which "
                     f"domain leaked")
    return fails


def main() -> int:
    targets = sys.argv[1:] or NEW_DOMAINS
    all_fails: list[str] = []
    for d in targets:
        f = check(d)
        all_fails += f
        print(f"{'PASS' if not f else 'FAIL'}  {d}"
              + (f"  ({len(f)} issue(s))" if f else ""))
    lt = check_leak_terms()
    all_fails += lt
    print(f"{'PASS' if not lt else 'FAIL'}  leak_terms"
          + (f"  ({len(lt)} issue(s))" if lt else ""))
    if SKIPS:
        print("\n--- SKIPPED (not run, not failed) ---")
        for s in SKIPS:
            print(f"  {s}")
        print(f"\n  {len(SKIPS)} check(s) could not run. To enable the TypeScript")
        print("  parse gate:  (cd corpus/stacks/app && npm install)")
    if all_fails:
        print("\n--- failures ---")
        for f in all_fails:
            print(f"  {f}")
        print(f"\n{len(all_fails)} failure(s)")
        return 1
    if SKIPS:
        print("\nall domain gates that could run pass "
              "(corpus/DOMAINS.md §5) — see SKIPPED above")
        return 0
    print("\nall domain gates pass (corpus/DOMAINS.md §5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
