# Sibling-repo husk test — 2026-08-19

Six files from a private sibling repo (regulated-utility data processing,
source repo withheld), husked
by `Qwen/Qwen2.5-Coder-7B-Instruct` into `music-streaming`.

> **The husk artifacts were deleted on 2026-08-19; only this write-up remains.**
> Every measurement below was taken against them before removal and is unchanged.
> They were removed because the `verbatim` column is what it says: each husk
> carried lines of the private repo's source returned byte-identical — 118 of 162
> in `sources/source_a.py`, which was never transformed at all, and 124, 85, 67 and 47
> in the four others. `source_a.py` additionally carried real regulatory-filing identifiers, live
> live regulatory-filing API URLs and the sibling repo's internal ticket
> vocabulary. Keeping
> them in a repo intended to go public would have published the source this
> project exists to protect.

**Transformation was verified BEFORE leaks were counted.** That check is the
whole point of this run: a previous attempt reported a "leak" that turned out to
be untransformed passthrough.

| file | kind | src | husk | ratio | verbatim | leak terms | of which verbatim |
|---|---|---|---|---|---|---|---|
| `decision/runs.py` | ordinary | 258 | 92 | 0.05 | 13/82 | **0** | 0 |
| `health.py` | ordinary | 163 | 128 | 0.58 | 47/100 | **0** | 0 |
| `parse/format_b.py` | public-source parser | 272 | 261 | 0.74 | 124/223 | 1 | 0 |
| `parse/format_a.py` | public-source parser | 297 | 205 | 0.03 | 67/177 | 2 | 0 |
| `sources/source_b.py` | public-source parser | 267 | 218 | 0.50 | 85/182 | **0** | 0 |
| `sources/source_a.py` | public-source parser | 191 | 190 | **0.97** | 118/162 | 16 | 9 |

## Findings

**1. Where the transform ran, it worked.** Five of six files came back with zero
to two domain terms, none of them verbatim. `format_a.py` at ratio 0.03 became
plausible music-streaming code; its two residual hits are the word "utility"
surviving inside two docstrings, which is vocabulary residue rather than a domain
giveaway.

**2. Public-standard parsers did NOT leak more than ordinary code.** FERC,
Census and SPP parsers scored 2, 1 and 0. This does **not** reproduce the earlier
observation that format constants carry the domain, and that generalisation
should not be published on the strength of one corpus.

**3. The one leaking file was never husked.** `sources/source_a.py` has ratio 0.97
with 118/162 lines byte-identical; its only change is docstring-to-comment
conversion. Its 16 "leaks" are the original text. The service returned success.

## The actual defect: silent passthrough

`llm-translation` sometimes returns its input nearly unchanged and reports
success. Observed at 1/6 here and 5/7 on a previous tree. There is no
post-condition check — the solution verifies liveness (non-empty, not truncated)
and nothing else.

This is a **privacy** defect, not merely a quality one: a user receives what they
believe is a husk, and it is their source code. Nothing in the response
distinguishes the two. A similarity check against the input would catch it
outright and does not exist.
