#!/usr/bin/env python3
"""Score a husked tree against its source: did the transform run, and did it leak?

Written because the 7B/32B comparison in runs/20260819-husker-scale was measured
by hand in a terminal, and this repository's own rule is that every number in a
document comes from a file the harness wrote.

Two questions, in this order — the order is the method:

  1. DID IT RUN?  `llm-translation` sometimes returns its input nearly unchanged
     and reports success (LIMITATIONS.md, "silent passthrough"). Counting leaks
     in an untransformed file measures nothing but the input, which is exactly
     the error that produced the withdrawn dependency-leak claim.
  2. DID IT LEAK?  Only meaningful for files that answered (1).

Metrics
-------
whole_file_ratio    difflib similarity of husk to source over the whole text.
ident_retention     share of the source's own content identifiers (length >= 4,
                    excluding the keywords, builtins and library names the
                    husker is TOLD to keep) that survive into the husk. This is
                    the transformation signal. Line-level verbatim is not: a
                    faithful husk still repeats `@dataclass` and `))`, so it
                    reads as unchanged where nothing was left unchanged.
code_verbatim       share of the husk's CODE lines (comments and docstrings
                    removed) that appear byte-identically in the source. This is
                    the headline number: it measures whether the CODE was
                    rewritten, not whether the prose was. Trivial lines (`)`,
                    `else:`) are included, matching the earlier hand
                    measurement; code_verbatim_substantive repeats it over lines
                    of 8+ characters for a less flattering read.
domain_retention    of the distinct domain terms present in the SOURCE, the
                    share still present in the husk. The privacy-relevant
                    number, and the one that separates "kept generic names"
                    from "never translated".
shape_fidelity      1.0 when the husk has exactly the def / class / branch /
                    loop / handler / return counts of its input. The ratchet
                    guard: every other metric rewards looking less like the
                    input, and emitting less code is the cheapest way to do
                    that. A prompt revision that improves leaks while this falls
                    has not improved anything.
copied_span_share   share of the SOURCE's code lines returned inside a run of 5+
                    consecutive byte-identical lines. Every other leak metric
                    here matches words against an authored list and is therefore
                    blind to a copied span containing no domain vocabulary: one
                    real husk returned 26 consecutive source lines — a regex
                    holding a live URL, a whole dataclass, an entire parse
                    function — and scored 0% domain retention with zero leak
                    terms. Added 2026-08-19; every leak number recorded here
                    before that date was computed without it.
leak_lines          husk lines containing >=1 authored leak term.
leak_lines_verbatim of those, the ones byte-identical to a source line — i.e.
                    leaks that are simply untransformed input.

Comment/docstring removal is a documented heuristic, not a parser (same stance
as counters.py): husks routinely fail to parse, and a scorer that crashes on the
worst outputs is a scorer that only sees the good ones.

    python3 evals/score_husk.py --src /tmp/sibling-src --husk /tmp/sibling-husk32 \
        --terms electric-transmission --label "32B old prompt" \
        --out evals/runs/<run>/score-32b-old.json
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TERMS_FILE = HERE / "leak_terms.json"

# strip_prose / content_idents / span detection are imported from the module the
# SERVICE runs, not reimplemented here. An offline scorer that disagrees with the
# request-path gate is worse than no scorer: it certifies husks the service would
# refuse, and vice versa. Loaded by file path so this stays runnable under a bare
# interpreter (importing app.solutions pulls in openai and writes files).
_spec = importlib.util.spec_from_file_location(
    "_husk_check", HERE.parent / "husk-api" / "app" / "solutions" / "_husk_check.py")
_hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hc)
strip_prose = _hc.strip_prose
content_idents = _hc.content_idents




# The ratchet guard. Every metric above rewards a husk for looking less like its
# input, and the cheapest way to score well on all of them is to emit less code.
# Pathology preservation is the entire premise of the technique, so a revision
# that improves the leak numbers by dropping functions has not improved anything.
_SHAPE = {
    "def": re.compile(r"^\s*(?:async\s+)?def\s|^\s*func\s"),
    "class": re.compile(r"^\s*(?:class|type)\s"),
    "branch": re.compile(r"^\s*(?:if|elif|else|switch|case)\b"),
    "loop": re.compile(r"^\s*(?:for|while)\b"),
    "except": re.compile(r"^\s*(?:try|except|catch|finally|rescue)\b"),
    "return": re.compile(r"^\s*(?:return|yield)\b"),
}


def shape(code_lines: list[str]) -> dict[str, int]:
    """Structural census of a file. Not a parser — a reproducible proxy, in the
    same spirit as counters.py."""
    return {k: sum(1 for ln in code_lines if rx.match(ln)) for k, rx in _SHAPE.items()}


def score_file(src_text: str, husk_text: str, suffix: str, pattern: re.Pattern) -> dict:
    src_code = strip_prose(src_text, suffix)
    husk_code = strip_prose(husk_text, suffix)
    src_code_set = set(src_code)
    src_all_set = {ln.strip() for ln in src_text.splitlines() if ln.strip()}

    verbatim = [ln for ln in husk_code if ln in src_code_set]
    subst = [ln for ln in husk_code if len(ln) >= 8]
    subst_verbatim = [ln for ln in subst if ln in src_code_set]

    src_terms = {m.group(0).lower() for m in pattern.finditer(src_text)}

    leak_lines, leak_verbatim, hits = 0, 0, {}
    for raw in husk_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        found = {m.group(0).lower() for m in pattern.finditer(line)}
        if not found:
            continue
        leak_lines += 1
        if line in src_all_set:
            leak_verbatim += 1
        for t in found:
            hits[t] = hits.get(t, 0) + 1

    ratio = difflib.SequenceMatcher(None, src_text, husk_text).ratio()
    code_verbatim = len(verbatim) / len(husk_code) if husk_code else 1.0

    # Copied spans: runs of consecutive code lines the husk carries over from
    # the source unchanged. Every leak number above this line is computed by
    # matching words from an authored list, which is blind to a copied span that
    # happens to contain no domain vocabulary — one real husk returned 26
    # consecutive lines of source, including a live URL inside a regex, and
    # scored zero on every one of them.
    spans = _hc.copied_spans(src_code, husk_code)
    copied_lines = sum(spans)

    # Line-level verbatim conflates "kept a generic name" with "never
    # translated": a faithful husk still repeats `@dataclass`, `continue` and
    # `))` byte for byte. Identifier retention separates the two — it asks how
    # much of the input's OWN vocabulary the husker carried across.
    src_idents = content_idents(src_code)
    kept = src_idents & content_idents(husk_code)
    retention = len(kept) / len(src_idents) if src_idents else 0.0

    src_shape, husk_shape = shape(src_code), shape(husk_code)
    shape_loss = {k: src_shape[k] - husk_shape[k] for k in src_shape
                  if src_shape[k] != husk_shape[k]}
    total_shape = sum(src_shape.values())
    shape_fidelity = (1 - sum(abs(v) for v in shape_loss.values()) / total_shape
                      if total_shape else 1.0)
    return {
        "src_lines": src_text.count("\n") + 1,
        "husk_lines": husk_text.count("\n") + 1,
        "whole_file_ratio": round(ratio, 2),
        "code_lines_src": len(src_code),
        "code_lines_husk": len(husk_code),
        "code_verbatim": round(code_verbatim, 2),
        "code_verbatim_n": len(verbatim),
        "code_verbatim_substantive": round(
            len(subst_verbatim) / len(subst), 2) if subst else 1.0,
        "ident_retention": round(retention, 2),
        # 1.0 = the husk has exactly as many defs, classes, branches, loops,
        # handlers and returns as its input. Anything a ratchet accepts must
        # hold this near 1.0, or the leak numbers improved by deletion.
        "shape_fidelity": round(shape_fidelity, 2),
        "shape_loss": shape_loss,
        "idents_src": len(src_idents),
        # Count only. The list would put the source's own identifier
        # vocabulary into a committed file, which is the exact leak this
        # repository exists to study.
        "idents_kept": len(kept),
        # The privacy-relevant one: of the distinct domain terms the SOURCE
        # contains, how many are still there? Unlike ident_retention it does
        # not punish a husker for keeping `body_sha256`.
        "domain_retention": round(len(src_terms & set(hits)) / len(src_terms), 2) if src_terms else 0.0,
        "domain_terms_src": len(src_terms),
        # A file this close to its input was not husked at all; its leak counts
        # are counts of the ORIGINAL text and must not be read as a property of
        # husking. Both halves are needed and the thresholds are high on
        # purpose: a genuine husk sits at ratio 0.96 / retention 0.90 when the
        # file is mostly structure, so anything looser mislabels good output.
        # Calibrated by eye against 24 file-observations (7B/32B x prompt
        # revisions); the band just under it is genuinely ambiguous and the
        # per-file numbers, not this flag, are what a reader should trust.
        "passthrough": retention >= 0.92 and ratio >= 0.95,
        # How much of the SOURCE came back as contiguous unrewritten text. The
        # honest "how much of the input did the caller get returned" number.
        "copied_spans": len(spans),
        "copied_span_lines": copied_lines,
        "copied_span_share": round(copied_lines / len(src_code), 3) if src_code else 0.0,
        "longest_span": max(spans) if spans else 0,
        "leak_lines": leak_lines,
        "leak_lines_verbatim": leak_verbatim,
        "leak_terms": dict(sorted(hits.items(), key=lambda kv: -kv[1])),
    }


def build_pattern(terms_key: str) -> re.Pattern:
    """Compile the authored leak-term list for one source domain."""
    catalog = json.loads(TERMS_FILE.read_text())
    if terms_key not in catalog:
        raise SystemExit(f"unknown term set {terms_key!r}; have: "
                         f"{[k for k in catalog if not k.startswith('_')]}")
    terms = catalog[terms_key]["terms"]
    # Some term sets redact source-identifying names from the committed list and
    # keep them in a gitignored overlay (see leak_terms.json's _terms_private_note).
    # Merge it when present; say so loudly when it is not, because its absence
    # makes leak_lines and domain_retention lower bounds rather than exact.
    priv_name = catalog[terms_key].get("terms_private_file")
    if priv_name:
        priv = TERMS_FILE.parent / priv_name
        if priv.is_file():
            terms = terms + json.loads(priv.read_text())[terms_key]["terms"]
        else:
            print(f"note: {priv_name} absent -- {terms_key!r} scored on the public "
                  f"term list only; leak_lines and domain_retention are LOWER BOUNDS",
                  file=sys.stderr)
    return re.compile(
        r"\b(" + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r")\b",
        re.IGNORECASE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="source tree the husk was made from")
    ap.add_argument("--husk", required=True, help="husked tree to score")
    ap.add_argument("--terms", required=True, help="key in evals/leak_terms.json")
    ap.add_argument("--label", default="", help="free-text label for the run")
    ap.add_argument("--out", help="write the JSON record here")
    a = ap.parse_args()

    pattern = build_pattern(a.terms)

    src_root, husk_root = Path(a.src).resolve(), Path(a.husk).resolve()
    rows = {}
    for hp in sorted(husk_root.rglob("*")):
        if not hp.is_file() or hp.name.startswith("_"):
            continue
        rel = hp.relative_to(husk_root)
        sp = src_root / rel
        if not sp.is_file():
            print(f"  skip {rel} — no source counterpart")
            continue
        rows[str(rel)] = score_file(sp.read_text(encoding="utf-8"),
                                    hp.read_text(encoding="utf-8"),
                                    hp.suffix, pattern)

    scored = list(rows.values())
    n = len(scored)
    clean = [r for r in scored if not r["passthrough"]]
    summary = {
        "label": a.label,
        "term_set": a.terms,
        "files": n,
        "passthrough_files": n - len(clean),
        "mean_code_verbatim": round(sum(r["code_verbatim"] for r in scored) / n, 2) if n else None,
        "mean_ident_retention": round(sum(r["ident_retention"] for r in scored) / n, 2) if n else None,
        "mean_domain_retention": round(sum(r["domain_retention"] for r in scored) / n, 2) if n else None,
        "mean_copied_span_share": round(sum(r["copied_span_share"] for r in scored) / n, 3) if n else None,
        "copied_span_lines_total": sum(r["copied_span_lines"] for r in scored),
        "longest_span_max": max((r["longest_span"] for r in scored), default=0),
        "files_with_span_20plus": sum(1 for r in scored if r["longest_span"] >= 20),
        "mean_shape_fidelity": round(sum(r["shape_fidelity"] for r in scored) / n, 2) if n else None,
        "mean_code_verbatim_transformed_only": round(
            sum(r["code_verbatim"] for r in clean) / len(clean), 2) if clean else None,
        "leak_lines_total": sum(r["leak_lines"] for r in scored),
        "leak_lines_total_transformed_only": sum(r["leak_lines"] for r in clean),
        "leak_lines_verbatim_total": sum(r["leak_lines_verbatim"] for r in scored),
    }

    print(f"\n{a.label or a.husk}")
    print("| file | ratio | code verbatim | ident retention | domain retention | **copied span** | longest | leak lines | shape | passthrough |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for rel, r in rows.items():
        print(f"| `{rel}` | {r['whole_file_ratio']:.2f} | {r['code_verbatim']:.0%} "
              f"| {r['ident_retention']:.0%} | {r['domain_retention']:.0%} "
              f"| **{r['copied_span_share']:.0%}** ({r['copied_span_lines']}L) "
              f"| {r['longest_span']} "
              f"| {r['leak_lines']} "
              f"| {r['shape_fidelity']:.0%} "
              f"| {'**YES**' if r['passthrough'] else 'no'} |")
    print(f"\n{json.dumps(summary, indent=2)}")

    if a.out:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"summary": summary, "files": rows}, indent=2) + "\n")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
