#!/usr/bin/env python3
"""Cohen's κ for the RSCH-1 judge. `evals/preregistration.md` §6.2.

§6.2 requires a random 20% of the judge's labels to be hand-labelled and Cohen's κ
reported, and it registers the consequence in advance: **if κ < 0.6 the judge
numbers are reported as descriptive only**, and only the deterministic leak-term
pre-check counts as evidence. This is the tool that makes that checkable instead
of aspirational.

Two steps, deliberately separated so the human never sees the judge's answer
before writing their own:

    python3 evals/kappa_judge.py --sample <run-dir>    # writes kappa_worksheet.jsonl
    # fill in "human_label" on every row: MATCH | RELATED | MISS
    python3 evals/kappa_judge.py --score  <run-dir>    # computes κ, writes kappa.json

The worksheet carries the ground-truth label and the guess and **nothing else** —
the same blinding the judge itself works under (§6.2: "not shown the husk so it
cannot be swayed by it"). It also withholds the judge's own label, because a
human who can see it is measuring their agreement with a suggestion rather than
their independent read, and κ computed that way is worthless in the flattering
direction.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LABELS = ("MATCH", "RELATED", "MISS")
SAMPLE_FRACTION = 0.20
SEED = 20260819


def load_judged(run: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((run / "judge").glob("*.json"))]


def cmd_sample(run: Path) -> int:
    judged = load_judged(run)
    if not judged:
        print("no judge records — run score_rsch1.py first", file=sys.stderr)
        return 2
    menu = {o["id"]: o for o in json.loads(
        (REPO / "evals" / "domains.json").read_text())["options"]}
    raw = {p.stem: json.loads(p.read_text())
           for p in sorted((run / "raw").glob("*open_ended*.json"))}

    n = max(1, round(len(judged) * SAMPLE_FRACTION))
    rng = random.Random(SEED)
    picked = rng.sample(sorted(judged, key=lambda d: d["item_id"]), n)

    out = run / "kappa_worksheet.jsonl"
    with out.open("w") as fh:
        for rec in picked:
            src = next((v for k, v in raw.items() if k.startswith(rec["item_id"])), {})
            truth_id = src.get("true_domain_id", "?")
            truth = menu.get(truth_id, {})
            parsed = src.get("parsed") or {}
            fh.write(json.dumps({
                "item_id": rec["item_id"],
                "attacker": rec["attacker"],
                "truth_label": truth.get("label", truth_id),
                "truth_description": truth.get("description", ""),
                "guess_domain": parsed.get("domain", ""),
                "guess_identifiers": parsed.get("specific_identifiers", []),
                # judge_label is DELIBERATELY ABSENT — see module docstring.
                "human_label": "",
            }) + "\n")
    print(f"sampled {n}/{len(judged)} judge records ({SAMPLE_FRACTION:.0%}, seed {SEED})")
    print(f"-> {out.relative_to(REPO)}")
    print(f"\nFill in \"human_label\" on every row with one of: {' | '.join(LABELS)}")
    print("Then: python3 evals/kappa_judge.py --score", run.relative_to(REPO))
    return 0


def cohens_kappa(a: list[str], b: list[str]) -> tuple[float, float, float]:
    """κ = (po - pe) / (1 - pe). Returns (kappa, observed, expected)."""
    n = len(a)
    if n == 0:
        return 0.0, 0.0, 0.0
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in set(a) | set(b))
    if pe >= 1.0:
        # Both raters used exactly one label for everything. κ is undefined here,
        # not 1.0 — perfect agreement by unanimity carries no information about
        # whether they agree for the same reason.
        return float("nan"), po, pe
    return (po - pe) / (1 - pe), po, pe


def cmd_score(run: Path) -> int:
    ws = run / "kappa_worksheet.jsonl"
    if not ws.exists():
        print(f"no worksheet at {ws}; run --sample first", file=sys.stderr)
        return 2
    rows = [json.loads(l) for l in ws.read_text().splitlines() if l.strip()]
    judged = {r["item_id"]: r for r in load_judged(run)}

    pairs, unlabelled, bad = [], 0, []
    for r in rows:
        h = (r.get("human_label") or "").strip().upper()
        if not h:
            unlabelled += 1
            continue
        if h not in LABELS:
            bad.append((r["item_id"], h))
            continue
        j = judged.get(r["item_id"], {}).get("label")
        if j in LABELS:
            pairs.append((h, j))

    if bad:
        print(f"invalid labels (must be one of {LABELS}): {bad}", file=sys.stderr)
        return 2
    if unlabelled:
        print(f"{unlabelled}/{len(rows)} rows still have an empty human_label — "
              f"fill them in first", file=sys.stderr)
        return 2
    if not pairs:
        print("no comparable pairs", file=sys.stderr)
        return 2

    human = [p[0] for p in pairs]
    judge = [p[1] for p in pairs]
    k, po, pe = cohens_kappa(human, judge)
    verdict = ("DESCRIPTIVE ONLY — κ < 0.6, so per §6.2 only the deterministic "
               "leak-term pre-check counts as evidence"
               if not (k >= 0.6) else "judge labels may be cited as evidence")

    doc = {"n_pairs": len(pairs), "kappa": None if k != k else round(k, 4),
           "observed_agreement": round(po, 4), "expected_agreement": round(pe, 4),
           "threshold": 0.6, "verdict": verdict,
           "human_distribution": dict(Counter(human)),
           "judge_distribution": dict(Counter(judge)),
           "confusion": {f"human={h}|judge={j}": c
                         for (h, j), c in Counter(pairs).items()}}
    (run / "kappa.json").write_text(json.dumps(doc, indent=2) + "\n")
    print(json.dumps(doc, indent=2))
    print(f"\n-> {(run / 'kappa.json').relative_to(REPO)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", action="store_true")
    g.add_argument("--score", action="store_true")
    a = ap.parse_args()
    run = Path(a.run)
    if not run.is_absolute():
        run = REPO / run
    return cmd_sample(run) if a.sample else cmd_score(run)


if __name__ == "__main__":
    raise SystemExit(main())
