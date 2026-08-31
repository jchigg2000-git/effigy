#!/usr/bin/env python3
"""Calibrate the request-path passthrough gate against every husk on disk.

The gate in `husk-api/app/solutions/_husk_check.py` refuses to return a husk
that is substantially its input. Two things can go wrong with it and only one is
visible in production:

  * a MISS returns the caller their own source code labelled as anonymised —
    the failure the gate exists for;
  * a REFUSAL of output the caller would rather have had — which looks to them
    like the service is broken, and is the cost side of the trade.

Neither is acceptable on a threshold somebody picked by eye, so the thresholds
are fitted here against every husk tree this project has produced, with the
known passthroughs labelled from the eyeball verification recorded in
runs/20260819-prompt-fix-32b/RESULT.md and runs/20260819-dogfood-sibling/RESULT.md.

    python3 evals/calibrate_postcondition.py --src /tmp/sibling-src

Prints the separation between labelled passthroughs and everything else, the
margin at the shipped thresholds, and the nearest non-passthrough to each
trigger — which is the number that matters, because it is how much room the gate
has before it starts refusing good husks.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Import the production module by path: going through `app.solutions` would pull
# in openai/dotenv and write the target-catalog JSON as a side effect, and this
# script must run under a bare interpreter.
_spec = importlib.util.spec_from_file_location(
    "_husk_check", REPO / "husk-api" / "app" / "solutions" / "_husk_check.py")
hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hc)

# Labelled by inspection, not by the metric being fitted — each was read against
# its source and confirmed to be untransformed output the service reported as
# success.
KNOWN_PASSTHROUGH = {
    ("dogfood-sibling", "pkg_a/sources/source_a.py"),
    ("sibling-husk32", "pkg_a/health.py"),
    ("sibling-husk32", "pkg_a/sources/source_b.py"),
}


def trees() -> list[tuple[str, Path]]:
    found = []
    # Removed 2026-08-19 -- it carried verbatim private source (see that run's
    # RESULT.md). The guard stays so the script still runs; the recorded
    # calibration is not reproducible from the repo alone, and never was: the
    # /tmp trees below were ephemeral too.
    committed = REPO / "evals" / "runs" / "20260819-dogfood-sibling" / "husk"
    if committed.is_dir():
        found.append(("dogfood-sibling", committed))
    for p in sorted(Path("/tmp").glob("sibling-husk*")):
        if p.is_dir():
            found.append((p.name, p))
    for p in sorted(Path("/tmp/ratchet").glob("*-run*")) if Path("/tmp/ratchet").is_dir() else []:
        if p.is_dir():
            found.append((p.name, p))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    src_root = Path(a.src).resolve()

    obs = []
    for tree_name, root in trees():
        for hp in sorted(root.rglob("*")):
            if not hp.is_file() or hp.name.startswith("_"):
                continue
            sp = src_root / hp.relative_to(root)
            if not sp.is_file():
                continue
            rep = hc.inspect(sp.read_text(encoding="utf-8"),
                             hp.read_text(encoding="utf-8"), hp.suffix)
            rep["tree"] = tree_name
            rep["file"] = str(hp.relative_to(root))
            rep["labelled_passthrough"] = (tree_name, rep["file"]) in KNOWN_PASSTHROUGH
            rep["_husk_path"] = str(hp)
            obs.append(rep)

    if not obs:
        print("no husk trees found — regenerate with evals/husk_tree.py")
        return 2

    pos = [o for o in obs if o["labelled_passthrough"]]
    neg = [o for o in obs if not o["labelled_passthrough"]]
    print(f"{len(obs)} file-observations across {len({o['tree'] for o in obs})} trees: "
          f"{len(pos)} labelled passthrough, {len(neg)} not\n")

    def spread(rows, key):
        vals = sorted(r[key] for r in rows if r[key] is not None)
        return (min(vals), max(vals)) if vals else (None, None)

    print(f"{'signal':<30}{'labelled passthrough':<26}{'everything else':<26}")
    for key in ("longest_identical_run_share", "ident_retention", "similarity_ratio",
                "code_verbatim"):
        pl, ph = spread(pos, key)
        nl, nh = spread(neg, key)
        print(f"{key:<30}{f'{pl} – {ph}':<26}{f'{nl} – {nh}':<26}")

    t = hc._thresholds()
    print(f"\nshipped thresholds: {t}")

    # The number that decides whether the gate is safe: the closest a correct
    # husk ever came to being refused.
    worst_neg_run = max(neg, key=lambda o: o["longest_identical_run_share"])
    print(f"\nnearest miss on the run trigger (a husk that was NOT passthrough):"
          f"\n  {worst_neg_run['tree']}/{worst_neg_run['file']} at "
          f"{worst_neg_run['longest_identical_run_share']:.0%} vs threshold {t['run_share']:.0%}"
          f"  ({worst_neg_run['longest_identical_run']} consecutive lines)")
    worst_pos_run = min(pos, key=lambda o: o["longest_identical_run_share"])
    print(f"weakest labelled passthrough on the same trigger:"
          f"\n  {worst_pos_run['tree']}/{worst_pos_run['file']} at "
          f"{worst_pos_run['longest_identical_run_share']:.0%}")

    # Ask the shipped gate itself rather than reimplementing its rule here — a
    # calibration that scores a copy of the logic can pass while the deployed
    # logic fails.
    def fails(o) -> bool:
        sp = src_root / o["file"]
        hp = Path(o["_husk_path"])
        try:
            hc.check(sp.read_text(encoding="utf-8"), hp.read_text(encoding="utf-8"), hp.suffix)
            return False
        except hc.PassthroughDetected:
            return True

    tp = [o for o in pos if fails(o)]
    fn = [o for o in pos if not fails(o)]
    extra = [o for o in neg if fails(o)]
    print(f"\nat the shipped thresholds: caught {len(tp)}/{len(pos)} whole-file passthroughs, "
          f"and refused {len(extra)} further husks out of {len(neg)}")
    for o in fn:
        print(f"  MISSED  {o['tree']}/{o['file']}  run={o['longest_identical_run']} lines "
              f"ret={o['ident_retention']:.0%} ratio={o['similarity_ratio']}")
    # NOT "false positives". The run trigger's evidence is self-certifying: N
    # consecutive lines being byte-identical to the input is a fact about the
    # output, not a classification of it. Every refusal below carries >= the
    # threshold in verbatim source lines, and the four largest distinct ones
    # were read against their source (a regex constant holding a live URL path,
    # a whole dataclass, an entire parse function, a constants block). Whether
    # returning them is acceptable is a policy question, and the answer here is
    # no. What the count DOES bound is how often a caller gets refused.
    for o in sorted(extra, key=lambda o: -o["longest_identical_run"]):
        print(f"  REFUSED {o['tree']}/{o['file']}  "
              f"{o['longest_identical_run']} verbatim consecutive lines "
              f"({o['longest_identical_run_share']:.0%})")

    if a.out:
        Path(a.out).write_text(json.dumps({
            "thresholds": t,
            "observations": len(obs),
            "labelled_passthrough": len(pos),
            "caught": len(tp), "missed": len(fn), "further_refusals": len(extra),
            "nearest_miss_run_share": worst_neg_run["longest_identical_run_share"],
            "weakest_passthrough_run_share": worst_pos_run["longest_identical_run_share"],
            "rows": obs,
        }, indent=2) + "\n")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
