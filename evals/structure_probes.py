"""Mechanical probes of RSCH-1B's question, at zero cost.

RSCH-1B asks whether the architecture effigy is REQUIRED to preserve is itself
domain-informative. The paid arm answers it with an LLM attacker reading a
canonicalised file. These three probes answer a cheaper version first, with no
model in the loop, and they are worth running BEFORE spending: if a mechanical
classifier can already recover the domain, the expensive arm is confounded and
the canonicaliser needs another look.

  1. counters  — leave-one-out nearest centroid over evals/counters.py's
     structural counters of the ORIGINAL source. This is the same information
     the BLIND arm shows its attacker, so it cross-checks BLIND's permutation
     result by a completely different route.
  2. tokens    — leave-one-out 1-NN over tf-idf of the CANONICALISED artifact's
     surviving word tokens. Tests for a vocabulary channel the gate missed.
  3. concentration — any surviving token that occurs in one domain and
     essentially nowhere else. A literal fragment here is a leak, found for free.

Each probe is reported against its OWN permutation null, for the same reason
arm accuracies are (A4.1): the raw rate of a classifier over unbalanced classes
is not interpretable on its own.

READ THE RESULT CAREFULLY. These probes are dominated by file ROLE — every
domain has a main.go, a server.go, a client.ts — so a nearest-neighbour tends to
match the same role in a DIFFERENT domain and score below chance. Below-chance
therefore means "no detectable domain signal," never "negative signal," and
never "the architecture is actively misleading."

    python3 evals/structure_probes.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

EVALS = Path(__file__).resolve().parent
ROOT = EVALS.parent
sys.path.insert(0, str(EVALS))

import canonicalize  # noqa: E402
import counters  # noqa: E402

WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PLACEHOLDER = re.compile(r"[Ii]dent_\d{4}|str_\d{4}")
DRAWS = 2000
SEED = 20260819


def corpus() -> list[dict]:
    man = json.loads((EVALS / "corpus" / "manifest.json").read_text())
    rows = []
    for a in man["artifacts"]:
        d = man["domains"].get(a["domain_dir"])
        if not isinstance(d, dict) or "true_domain_id" not in d:
            continue
        if not (40 <= a["lines"] <= 400):
            continue
        rows.append(a | {"true_domain_id": d["true_domain_id"]})
    return sorted(rows, key=lambda a: a["path"])


def loo(predict, labels: list[str], n: int) -> float:
    return sum(1 for i in range(n) if predict(i, labels) == labels[i]) / n


def permuted(predict, labels: list[str], n: int, observed: float, rng) -> dict:
    accs = []
    for _ in range(DRAWS):
        p = labels[:]
        rng.shuffle(p)
        accs.append(loo(predict, p, n))
    accs.sort()
    return {
        "observed": observed,
        "permuted_mean": sum(accs) / len(accs),
        "permuted_lo": accs[int(0.025 * DRAWS)],
        "permuted_hi": accs[int(0.975 * DRAWS) - 1],
        "p": sum(1 for a in accs if a >= observed) / DRAWS,
    }


def probe_counters(rows: list[dict], rng) -> dict:
    feats = []
    for a in rows:
        c = counters.count((ROOT / a["path"]).read_text(encoding="utf-8"), a["language"])
        feats.append([c["lines"], c["funcs"], c["structs"], c["interfaces"], c["imports"],
                      c["exports"], c["string_literals"], c["max_brace_depth"],
                      c["bytes"] / max(1, c["lines"])])
    m = len(feats[0])
    mean = [sum(f[j] for f in feats) / len(feats) for j in range(m)]
    sd = [math.sqrt(sum((f[j] - mean[j]) ** 2 for f in feats) / len(feats)) or 1.0 for j in range(m)]
    X = [[(f[j] - mean[j]) / sd[j] for j in range(m)] for f in feats]
    labels = [a["true_domain_id"] for a in rows]
    n = len(X)

    def predict(i, labs):
        cents = defaultdict(lambda: [0.0] * m)
        cnt = Counter()
        for k in range(n):
            if k == i:
                continue
            cnt[labs[k]] += 1
            for j in range(m):
                cents[labs[k]][j] += X[k][j]
        best, bestd = None, float("inf")
        for l, v in cents.items():
            d = sum((X[i][j] - v[j] / cnt[l]) ** 2 for j in range(m))
            if d < bestd:
                bestd, best = d, l
        return best

    return permuted(predict, labels, n, loo(predict, labels, n), rng)


def probe_tokens(rows: list[dict], rng, outdir: Path | None) -> tuple[dict, list]:
    docs, labels, gate_failures = [], [], []
    tmpdir = Path(tempfile.mkdtemp())
    for a in rows:
        p = ROOT / a["path"]
        src = p.read_text(encoding="utf-8")
        try:
            out, census = canonicalize.canonicalize(p, a["language"])
            canonicalize.gate(p, a["language"], src, out, census, tmpdir / p.name)
        except canonicalize.GateFailure as e:
            gate_failures.append(f"{a['path']}: {e}")
            continue
        if outdir:
            (outdir / f"{a['domain_dir']}__{p.name}.txt").write_text(out, encoding="utf-8")
        docs.append(Counter(w for w in WORD.findall(out) if not PLACEHOLDER.fullmatch(w)))
        labels.append(a["true_domain_id"])

    n = len(docs)
    df = Counter()
    for d in docs:
        df.update(d.keys())

    def vec(d):
        v = {w: (1 + math.log(c)) * math.log(n / df[w]) for w, c in d.items() if df[w] < n}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    V = [vec(d) for d in docs]

    def predict(i, labs):
        best, bestsim = None, -1.0
        for j in range(n):
            if i == j:
                continue
            s = sum(V[i][w] * V[j][w] for w in V[i].keys() & V[j].keys())
            if s > bestsim:
                bestsim, best = s, labs[j]
        return best

    res = permuted(predict, labels, n, loo(predict, labels, n), rng)
    res["gate_failures"] = gate_failures
    res["n"] = n

    # concentration: a surviving token that lives in essentially one domain
    per = defaultdict(Counter)
    for d, l in zip(docs, labels):
        per[l].update(set(d.keys()))
    tot = Counter()
    for c in per.values():
        tot.update(c)
    conc = []
    for w, t in tot.items():
        if t < 3:
            continue
        for l, c in per.items():
            if c[w] >= 3 and c[w] / t > 0.70:
                conc.append({"token": w, "domain": l, "files": c[w], "of": t})
    return res, sorted(conc, key=lambda x: -x["files"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="also write canonicalised artifacts here")
    args = ap.parse_args()
    import random

    outdir = Path(args.out) if args.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    rows = corpus()
    k = len({a["true_domain_id"] for a in rows})
    print(f"{len(rows)} artifacts, {k} domains, uniform chance {1/k:.3f}, {DRAWS} permutations\n")

    c = probe_counters(rows, random.Random(SEED))
    print(f"1. structural counters, nearest centroid : {c['observed']:.3f}  "
          f"null {c['permuted_mean']:.3f} [{c['permuted_lo']:.3f}, {c['permuted_hi']:.3f}]  p={c['p']:.4f}")

    t, conc = probe_tokens(rows, random.Random(SEED), outdir)
    print(f"2. canonicalised tokens, 1-NN tf-idf     : {t['observed']:.3f}  "
          f"null {t['permuted_mean']:.3f} [{t['permuted_lo']:.3f}, {t['permuted_hi']:.3f}]  p={t['p']:.4f}"
          f"   (n={t['n']})")
    if t["gate_failures"]:
        print(f"   gate failures ({len(t['gate_failures'])}), excluded:")
        for g in t["gate_failures"]:
            print(f"     {g[:150]}")
    print(f"3. tokens concentrated in one domain     : "
          + (", ".join(f"{x['token']} ({x['domain']} {x['files']}/{x['of']})" for x in conc[:8])
             if conc else "NONE"))
    print("\nBelow chance means no detectable domain signal, not negative signal: these probes are")
    print("dominated by file role, which is shared across all six domains.")

    report = {"n_artifacts": len(rows), "n_domains": k, "draws": DRAWS, "seed": SEED,
              "counters": c, "tokens": t, "concentrated_tokens": conc}
    (EVALS / "structure_probes.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\n-> {EVALS / 'structure_probes.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
