# The post-condition gate — 2026-08-19

`llm-translation` now checks its own output against its input and refuses to
return a husk that is substantially the source. Code:
`husk-api/app/solutions/_husk_check.py`. Calibration:
`evals/calibrate_postcondition.py`, record in `postcondition-calibration.json`.

Until today the solution verified that a response was non-empty and untruncated
and nothing else, which is why a file that came back byte-identical except for
one word was served as a successful husk. **The caller cannot detect that
failure** — they have the output, not the comparison.

## Building it found a failure mode nothing else here had seen

The gate was built to catch whole-file passthrough. Calibrating it against every
husk this project has produced — 150 file-observations across 25 trees — turned
up something else:

**Partial passthrough. A model translates the top of a file and copies the
bottom out verbatim.** One instance: `decision/runs.py` under prompt v6 returned
36 consecutive code lines byte-identical to the source, including the real table
name and column names, inside a file that scored **0.84 similarity, 78%
identifier retention** — both unremarkable. Another, in `sources/source_b.py`, copied
26 lines including a regex constant holding a live URL path, a whole dataclass,
and an entire parse function. That file scored **0% domain-term retention and
zero leak lines**: the copied region contains no words from the leak-term list,
so every privacy metric used in this repository called it clean.

Distribution across all 150 observations, by longest run of consecutive
byte-identical code lines:

| prompt | observations | ≥30 lines | ≥20 lines | ≥10 lines | worst |
|---|---|---|---|---|---|
| v1 (32B) | 6 | 2 | 3 | 4 | 100 |
| v1 (7B) | 12 | 0 | 2 | 4 | 27 |
| v2 (32B) | 6 | 1 | 1 | 4 | 31 |
| v3 | 54 | 1 | 2 | 15 | 31 |
| v4 (shipped) | 36 | 0 | 4 | 9 | 26 |
| v5 | 18 | 0 | 3 | 3 | 26 |
| v6 | 18 | 1 | 5 | 6 | 36 |
| **all** | **150** | **5** | **20** | **45** | **100** |

**This corrects a claim made earlier today.** "Zero passthrough in 132
file-observations since the prompt fix" was true of *whole-file* passthrough and
remains true. It is not true that no source survives verbatim: 14 of the 126
observations under the new prompts carry a run of 20+ identical code lines. The
prompt rewrite fixed the catastrophic version of this failure and left a
section-level version that no metric in this repository was looking for.

## What the gate checks

Three independent triggers, any of which refuses the husk:

1. **A run of identical code lines** — 20 of them, or 15% of the input. Direct
   evidence that a span was copied rather than rewritten.
2. **35% of the source returned across ALL spans of 5+ lines.** Added hours after
   the first two, when copied-span accounting in `score_husk.py` showed the
   longest-run trigger was under-powered: **copying distributes.** One husk
   returned **66% of its source — 72 lines — in spans of 5 to 14**, and shipped
   past a gate watching only for a run of 20. Across the 130 husks the first two
   triggers passed, 23 had returned ≥25% of the source and 3 had returned ≥50%.
   Threshold set at the 95th percentile of that distribution (median 9%, p90 30%).
3. **Identifier retention ≥ 92% together with whole-text similarity ≥ 95%** —
   the diffuse version, for output reordered rather than copied wholesale.

Files under 12 code lines are reported and never refused: at that size an input
and an honest husk of it are similar for reasons unrelated to passthrough.

Triggers 1 and 2 are the ones that earn the module, and they have a property the
vocabulary metrics lack: **its evidence is self-certifying.** "36 consecutive lines are
byte-identical to the input" is a fact about the output, not a classification of
it. There is no threshold at which returning that is correct.

All thresholds are env-overridable (`HUSK_CHECK_RUN_LINES`,
`HUSK_CHECK_RUN_SHARE`, `HUSK_CHECK_COPIED_SHARE`, `HUSK_CHECK_RETENTION`,
`HUSK_CHECK_RATIO`, `HUSK_CHECK_MIN_LINES`, `HUSK_CHECK_RETRIES`).

## Calibration

Fitted against all 150 observations, with the three whole-file passthroughs
labelled from the eyeball verification recorded in `RESULT.md` and
`../20260819-dogfood-sibling/RESULT.md`. The calibration script calls the
shipped gate rather than reimplementing its rule, so it cannot pass while
production fails.

- **3 of 3 labelled whole-file passthroughs caught.**
- **25 further husks refused** — 17 on the run triggers, 8 more once the
  total-share trigger was added. These are not false positives: each returns
  either 20+ consecutive or 35%+ total byte-identical source lines. The four
  largest distinct ones were read against their source. What the count bounds is
  how often a caller is refused.
- 11 of the 25 are the same file, `sources/source_b.py`, whose regex-constant and
  dataclass block models copy rather than translate on almost every run at every
  prompt revision. That is a property of the file, not of the gate.

## Behaviour on failure: retry once, then fail closed

A refusal triggers one retry at temperature +0.3, with the rejected attempt and
a message naming what was copied appended to the conversation — "try again" on a
stochastic transform is a coin flip, whereas a model can act on "you copied 36
consecutive lines." If the retry is also refused, the solution raises and the
host returns 500. It does not return a degraded husk with a warning: a warning
in a field the caller may not read is how this defect existed in the first place.

**Live acceptance runs**, whole tree, shipped thresholds, 1 retry,
`Qwen2.5-Coder-7B-Instruct`:

- with two triggers: **5 of 6 husked, 1 refused** (`sources/source_b.py`, both
  attempts copied 26+ lines);
- with three: **4 of 6 husked, 2 refused** (`source_b.py` again and `decision/runs.py`
  at 37 consecutive lines). Both refusals cite the run trigger as well as the new
  one, so on this draw the extra trigger did not change the outcome — the
  difference is run-to-run variance, which on this corpus is large.

Against the 150-observation archive the measured refusal rate is **28 of 150,
19%**. Every refusal carries either 20+ consecutive or 35%+ total verbatim
source lines. Without the gate, each would have been returned to a caller as an
anonymised husk.

Every response now carries `meta.postcondition` — the measurements, the
thresholds, and the verdict — because the caller cannot run this comparison
themselves.

## Limits

- One corpus, one language for the calibration (Python), one model for the live
  acceptance run. The comment/docstring stripping is a documented heuristic, not
  a parser; on Go/TS it uses slash-comment rules inferred from the source, and
  that inference is a guess when the caller does not pass `options.suffix`.
- The thresholds are fitted to 150 observations from one project's husks. A
  codebase with long stretches of genuinely generic code — a big enum, a
  vendored constants table — will be refused more often, and the escape hatch is
  an env var rather than anything cleverer.
- **This is not the verifier.** RSCH-2 specifies a CPG-isomorphism +
  anti-pattern-density + comment-speech-act checker that certifies a husk
  *preserved the pathology*. This checks one much narrower thing: that the output
  is not the input. It is a floor, not the property the paper claims.
