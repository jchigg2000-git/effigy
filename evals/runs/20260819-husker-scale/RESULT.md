# Husker scale: 7B vs 32B — 2026-08-19

Same six files from a private sibling repo (regulated-utility data processing,
source repo withheld),
same target (`music-streaming`), `LLM_MAX_TOKENS=8192`. Transformation was
verified before leaks were counted.

"Code verbatim" excludes comments and docstrings, so it measures whether the
CODE was translated rather than whether the prose was.

| model | file | whole-file ratio | code verbatim | leak lines |
|---|---|---|---|---|
| 7B | `decision/runs.py` | 0.05 | 16% | 0 |
| 7B | `health.py` | 0.58 | 45% | 0 |
| 7B | `parse/format_b.py` | 0.74 | 61% | 1 |
| 7B | `parse/format_a.py` | 0.03 | 35% | 2 |
| 7B | `sources/source_a.py` | **0.97** | 78% | 16 |
| 7B | `sources/source_b.py` | 0.50 | 52% | 0 |
| 32B | `decision/runs.py` | 0.90 | 65% | 17 |
| 32B | `health.py` | **1.00** | **99%** | 1 |
| 32B | `parse/format_b.py` | 0.89 | 80% | 5 |
| 32B | `sources/source_a.py` | 0.73 | 55% | 0 |
| 32B | `sources/source_b.py` | 0.96 | 87% | 0 |

**7B — mean code verbatim 48%, 19 leak lines, n=6**
**32B — mean code verbatim 77%, 23 leak lines, n=5** (`format_a.py` did not complete)

## A bigger model is a WORSE husker here

The 32B leaves more than three quarters of code lines byte-identical. Its failure
mode is distinctive: it translates docstrings and comments while leaving the code
alone. `health.py` came back identical to its input except for a single word
(one source-domain noun → its target-domain counterpart). `decision/runs.py` has a fully translated docstring —
"track playback sessions", "listener" — sitting on top of unchanged code, which is
why 17 source-domain terms survive in its identifiers.

The likely mechanism is the system prompt's "DO NOT refactor" clause. A stronger
instruction-follower honours it more literally, and minimal editing is the
result. That is the opposite of what husking needs.

**This contradicts the repo's existing scale finding**, which recorded the verdict
flipping from "viable-with-caveats" at 7B to "viable" at 14B. That was measured on
a different corpus with different questions; it should not be cited as evidence
that scaling up improves husking generally.

**Not uniformly worse.** The 32B husked `sources/source_a.py` cleanly (0 leaks) — the
one file the 7B passed through entirely (ratio 0.97, 16 leaks). The two models
fail on different files, which points at run-to-run instability rather than a
clean quality ordering. `llm-translation` is not byte-stable, and neither of these
is a repeated measurement.

---

**Followed up 2026-08-19 — the mechanism proposed above was tested.** The
"DO NOT refactor" clause was rewritten and the 32B re-run on the same six files:
`../20260819-prompt-fix-32b/RESULT.md`. The clause was part of the cause —
outright passthroughs disappear and domain-term retention drops 41% → 31% — but
the 32B remains the worse husker and the ordering here stands. The table above
was measured by hand; `evals/score_husk.py` now reproduces its `ratio` and
`code verbatim` columns exactly, and every number in the follow-up comes from
that script.
