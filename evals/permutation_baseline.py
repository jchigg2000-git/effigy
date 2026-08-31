"""Permutation baseline — what an arm's accuracy is worth after response bias.

Every accuracy in RSCH-1 is confounded by the attacker's answer distribution.
The BLIND attacker answered `ham-radio-logbook` on 26 of 29 items regardless of
what it was shown; against a held-out split that is one-third ham-radio, that
alone buys ~33% "accuracy" with zero information extracted. Reporting 33.3% as a
floor and 78.3% as a result invites the reader to subtract them, which is only
valid if both carry the same bias, and they do not.

So: hold each attacker's answers FIXED, permute the true labels, and read the
accuracy distribution that response bias alone produces. Report every arm as
observed MINUS permuted.

Permutation is over SOURCE FILES, not items. Prereg §9 resamples source files
for the cluster bootstrap because replicate husks of one source are not
independent observations; the same reasoning binds here. Permuting item labels
would break the clustering §9 exists to protect and would understate the null's
variance. Permuting the label assignment across the 30 files also preserves the
10/10/10 domain marginal exactly, which item-level shuffling does not.

No API calls. Pure computation over committed raw output.

    python3 evals/permutation_baseline.py <run-dir-name>
    python3 evals/permutation_baseline.py --selftest
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
import statistics
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
RUNS = EVALS / "runs"

DRAWS = 10_000
SEED = 20260819  # same seed score_rsch1.cluster_bootstrap_diff uses


# --------------------------------------------------------------------------
# core


def permutation_cell(items: list[dict], draws: int = DRAWS, seed: int = SEED) -> dict:
    """One (arm, attacker) cell.

    `items` are dicts with `source_path`, `true_domain_id`, `answer_id`.
    Returns observed accuracy, the permuted null, and the corrected effect.
    """
    n = len(items)
    if n == 0:
        return {"n": 0}

    observed = sum(1 for it in items if it["answer_id"] == it["true_domain_id"]) / n

    # One label per source file, carried to that file's replicates.
    label_of: dict[str, str] = {}
    for it in items:
        label_of.setdefault(it["source_path"], it["true_domain_id"])
    files = sorted(label_of)
    labels = [label_of[f] for f in files]

    rng = random.Random(seed)
    accs: list[float] = []
    for _ in range(draws):
        shuffled = labels[:]
        rng.shuffle(shuffled)
        m = dict(zip(files, shuffled))
        accs.append(sum(1 for it in items if m[it["source_path"]] == it["answer_id"]) / n)
    accs.sort()

    mean = statistics.fmean(accs)
    # p is one-sided: how often does pure response bias reach the observed value?
    p = sum(1 for a in accs if a >= observed) / draws

    # Analytic cross-check. Under a random label permutation the expected
    # accuracy is sum_d P(answer=d) * P(true=d). If the permutation does not
    # land on this, the permutation is wrong.
    ans_share = collections.Counter(it["answer_id"] for it in items)
    true_share = collections.Counter(it["true_domain_id"] for it in items)
    analytic = sum((ans_share[d] / n) * (true_share[d] / n) for d in set(ans_share) | set(true_share))

    modal_answer, modal_n = collections.Counter(it["answer_id"] for it in items).most_common(1)[0]

    return {
        "n": n,
        "n_files": len(files),
        "observed": observed,
        "permuted_mean": mean,
        "permuted_lo": accs[int(0.025 * draws)],
        "permuted_hi": accs[int(0.975 * draws) - 1],
        "corrected": observed - mean,
        "p": p,
        "analytic": analytic,
        "analytic_gap": abs(mean - analytic),
        "modal_answer": modal_answer,
        "modal_share": modal_n / n,
        "modal_n": modal_n,
    }


# --------------------------------------------------------------------------
# loading


def load_forced_choice(run: Path) -> list[dict]:
    """Forced-choice records with a parsed answer, resolved to a domain id.

    Records whose every attempt transport-failed carry `parsed: null` and have
    no answer to permute. They are dropped as MISSING, matching how
    score_rsch1.py already treats them: a coverage gap, never a wrong answer.
    """
    out, dropped = [], 0
    for p in sorted((run / "raw").glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("mode") != "forced_choice":
            continue
        parsed = rec.get("parsed") or {}
        choice = parsed.get("choice")
        menu = rec.get("menu_order") or []
        if not isinstance(choice, int) or not (1 <= choice <= len(menu)):
            dropped += 1
            continue
        out.append(
            {
                "item_id": rec["item_id"],
                "arm": rec["arm"],
                "attacker": rec["attacker"],
                "source_path": rec["source_path"],
                "domain_dir": rec.get("domain_dir", ""),
                "true_domain_id": rec["true_domain_id"],
                "answer_id": menu[choice - 1],
            }
        )
    if dropped:
        print(f"  (dropped {dropped} records with no parsed choice — missing, not wrong)", file=sys.stderr)
    return out


def module_name_survival(run: Path) -> dict[str, bool]:
    """Did an artifact keep the Go module name it was husked from?

    In this corpus the module name IS the domain (`meterworks`,`qsolog`,
    `tremorline`), and llm_translation.py's own system prompt already requires
    own-module imports to be renamed. So this is a mechanical, already-forbidden
    leak channel, and splitting accuracy by it separates "the rewriter failed"
    from "the architecture leaked".
    """
    out: dict[str, bool] = {}
    for f in sorted((run / "artifacts").glob("*.txt")):
        item_id = f.name[:-4]
        module = item_id.split("__")[0]
        text = f.read_text(encoding="utf-8", errors="ignore")
        out[item_id] = bool(re.search(re.escape(module), text, re.I))
    return out


# --------------------------------------------------------------------------
# report


def build(run: Path) -> dict:
    rows = load_forced_choice(run)
    arms = sorted({r["arm"] for r in rows})
    attackers = sorted({r["attacker"] for r in rows})

    cells = {}
    for arm in arms:
        for atk in attackers:
            items = [r for r in rows if r["arm"] == arm and r["attacker"] == atk]
            if items:
                cells[f"{arm}|{atk}"] = permutation_cell(items)

    # Leak-channel attribution: llm-translation split by module-name survival.
    survival = module_name_survival(run)
    attribution = {}
    for arm in arms:
        split: dict[str, list[dict]] = {"leaked": [], "clean": []}
        for r in rows:
            if r["arm"] != arm:
                continue
            s = survival.get(r["item_id"])
            if s is None:
                continue
            split["leaked" if s else "clean"].append(r)
        if split["leaked"] and split["clean"]:
            attribution[arm] = {
                bucket: {
                    "n": len(v),
                    "correct": sum(1 for it in v if it["answer_id"] == it["true_domain_id"]),
                    "accuracy": sum(1 for it in v if it["answer_id"] == it["true_domain_id"]) / len(v),
                }
                for bucket, v in split.items()
            }
            n_art = sum(1 for k, s in survival.items() if f"__{arm}__" in k)
            n_leak = sum(1 for k, s in survival.items() if f"__{arm}__" in k and s)
            attribution[arm]["artifacts_leaking_module_name"] = f"{n_leak}/{n_art}"

    return {"run": run.name, "draws": DRAWS, "seed": SEED, "cells": cells, "attribution": attribution}


def render(report: dict) -> str:
    L = [
        f"# Permutation baseline — {report['run']}",
        "",
        f"{report['draws']:,} permutations, seed {report['seed']}, labels permuted across SOURCE FILES",
        "(prereg §9 clustering), replicates carried with their file.",
        "",
        "`corrected` = observed − permuted mean. `p` = P(response bias alone reaches observed).",
        "",
        "| arm | attacker | n | observed | permuted | corrected | p | modal answer |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for key, c in sorted(report["cells"].items()):
        if not c.get("n"):
            continue
        arm, atk = key.split("|")
        short = atk.split("/")[-1].split(":")[0]
        L.append(
            f"| `{arm}` | {short} | {c['n']} | {c['observed']:.3f} | "
            f"{c['permuted_mean']:.3f} [{c['permuted_lo']:.3f}, {c['permuted_hi']:.3f}] | "
            f"**{c['corrected']:+.3f}** | {c['p']:.4f} | {c['modal_answer']} {c['modal_n']}/{c['n']} |"
        )

    worst = max((c["analytic_gap"] for c in report["cells"].values() if c.get("n")), default=0.0)
    L += ["", f"Analytic cross-check `Σ_d P(ans=d)·P(true=d)` agrees with the permuted mean "
              f"to within **{worst:.4f}** across every cell."]

    if report["attribution"]:
        L += ["", "## Leak-channel attribution — own-module name survival", "",
              "The Go module name IS the domain in this corpus, and the husker prompt's",
              "\"Imports of the input's OWN modules ARE renamed\" clause already forbids it",
              "surviving. Splitting by whether it did separates a fixable",
              "rewriter defect from anything the architecture itself carries.", "",
              "| arm | artifacts leaking module name | accuracy WHEN leaked | accuracy when removed |",
              "|---|---|---:|---:|"]
        for arm, a in sorted(report["attribution"].items()):
            L.append(
                f"| `{arm}` | {a['artifacts_leaking_module_name']} | "
                f"{a['leaked']['correct']}/{a['leaked']['n']} = {a['leaked']['accuracy']:.3f} | "
                f"{a['clean']['correct']}/{a['clean']['n']} = {a['clean']['accuracy']:.3f} |"
            )
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# self-test — these are the acceptance cases for the method itself


def selftest() -> int:
    files = [f"f{i}" for i in range(30)]
    labels = [d for d in ("A", "B", "C") for _ in range(10)]
    truth = dict(zip(files, labels))

    def cell(answer_of):
        return permutation_cell(
            [{"source_path": f, "true_domain_id": truth[f], "answer_id": answer_of(f)} for f in files]
        )

    ok = True
    c = cell(lambda f: truth[f])
    print(f"always-correct   obs={c['observed']:.3f} perm={c['permuted_mean']:.3f} p={c['p']:.4f}")
    ok &= c["observed"] == 1.0 and c["p"] == 0.0

    c = cell(lambda f: "A")
    print(f"always-answers-A obs={c['observed']:.3f} perm={c['permuted_mean']:.3f} p={c['p']:.4f}")
    # A pure-bias attacker must correct to ~zero. This is the BLIND case.
    ok &= abs(c["corrected"]) < 0.01 and c["p"] > 0.9

    rng = random.Random(7)
    c = cell(lambda f: rng.choice("ABC"))
    print(f"uniform-random   obs={c['observed']:.3f} perm={c['permuted_mean']:.3f} p={c['p']:.4f}")
    ok &= c["p"] > 0.05

    for name, c in (("always-correct", cell(lambda f: truth[f])), ("always-A", cell(lambda f: "A"))):
        assert c["analytic_gap"] < 0.01, f"{name}: permuted mean {c['permuted_mean']} != analytic {c['analytic']}"

    print("OK" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?", help="run directory name under evals/runs/")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.run:
        ap.error("need a run directory or --selftest")

    run = RUNS / args.run
    if not run.is_dir():
        raise SystemExit(f"no such run: {run}")

    report = build(run)
    (run / "permutation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    text = render(report)
    (run / "permutation.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {run / 'permutation.json'} and {run / 'permutation.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
