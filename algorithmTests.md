# Husk Algorithm Tests — Verdicts

Empirical record for the three registered solutions. **Every number below is
sourced from a committed run under `evals/runs/`** — the linked `RESULT.md` in
each section is the primary record and carries the caveats in full. Nothing here
was transcribed from a terminal.

> **Rewritten 2026-08-19. What this file used to be, and why it is gone.**
>
> Until then this file held verdicts measured against the `membership/` fixture —
> a third-party-derived codebase that is not part of this repository. Every input
> path in those verdicts pointed into a tree that is not published here, so they
> could not be reproduced, checked, or even located.
>
> The old results are **not** rewritten to fit the new corpus. They are deleted,
> because their corpus is deleted. Rewriting evidence to survive a change in the
> thing it measured is the failure mode the previous editor's note existed to
> prevent; the honest move when the subject goes is to say so and start again.
>
> **What that costs, stated plainly:** `fpe` and `literal-tagging` carried
> `viable-with-caveats` verdicts that have **not** been re-earned against the
> replacement corpus. Neither has been evaluated since. Treat both as unmeasured,
> not as previously-passing. See "What is not measured" at the end.

## The corpus

Two bodies of code, used for different questions.

**`corpus/stacks/`** — a synthetic public-library inter-branch catalog and
circulation app (Go + SQLite API, React/TS SPA), generated from
`corpus/stacks/SPEC.md`. It carries **nine deliberate architectural defects**
catalogued in `corpus/PATHOLOGY.md` by *symbol anchor, never line number*, so the
inventory cannot rot as the code moves. This is the fidelity corpus: it answers
"does a diagnosis of the husk still hold for the source?"

One rule earned the hard way and now written into `PATHOLOGY.md`: **the corpus
must not be an answer key.** Its first version carried eight comments naming the
defects they sat beside ("every query in this program is written at its call
site"). Reviewers cited the prose instead of the code, and the husker faithfully
translated the prose, so the husk scored well for entirely the wrong reason.
Removed in `c6bc23f`.

**A private sibling repo** (six Python files, regulated-utility data processing)
— used for the husker-scale and prompt work, because privacy questions need
source whose domain is genuinely sensitive. Its source is not in this repository
and never was. Husks of it are not committed either, for the reason recorded in
`runs/20260819-prompt-fix-32b/RESULT.md`: they are not private enough to publish.

## Husker selection — context window is the first filter

`runs/20260819T124154Z-smell-loop/` — **scoring DISCARDED**, see that run's
`DISCARDED.md` for the three reasons (answer-key corpus, a harness bug that
corrupted the agreement column, and single-file scope making two of nine defects
unscoreable). One finding does not depend on the discarded scoring and stands:

**Two of four otherwise-plausible cheap huskers could not read the corpus at
all.** `Qwen/Qwen2.5-7B-Instruct` returned 422 and `google/gemma-3n-E4B-it`
returned 400 on a 376-line file — input validation and token-count limits, not
quality. A cheap local husker needs context for the largest file *plus* the
system prompt, and that eliminates candidates before any evaluation of output.

Survivors: `Qwen/Qwen2.5-Coder-7B-Instruct` (p50 5.8 s) and
`meta-llama/Llama-3.1-8B-Instruct` (p50 55.0 s).

## `llm-translation` — fidelity, multi-file and agentic

`runs/20260819-agentic-multifile/`. A Sonnet reviewer agent, scoped per tree,
required to cite code rather than comments. Both huskers pinned to one target
domain (`logistics-dispatch`) via `evals/husk_tree.py --target`.

| tree | defects detected | agrees w/ baseline | mean confidence | p50 husk |
|---|---|---|---|---|
| real (baseline) | 9/9 | — | 0.867 | — |
| `Qwen2.5-Coder-7B` husk | 9/9 | 9/9 | 0.811 | 5.8 s |
| `Llama-3.1-8B` husk | 9/9 | 9/9 | 0.794 | 55.0 s |

**Verdict: the pathology survives translation on this corpus.** Every planted
defect is recoverable from the husk, and the diagnoses agree with the baseline
on all nine. The reviewer found the god-object in a struct renamed `DispatchSystem`,
the layering violation in a `store` package renamed to a dispatch concern, and
inline SQL in handlers whose tables had become `routes` and `carriers`.

**Recommended cheap husker: `Qwen2.5-Coder-7B-Instruct`.** Equal detection,
higher confidence, 9.5× faster, and unlike Llama it does not corrupt standard-library
symbols — Llama emitted `logger *log.Truck`.

**A prerequisite that is easy to miss:** `llm-translation` selects its target
domain by hashing each input, so a husked *tree* scatters across unrelated
domains and reads as incoherent. `husk_tree.py --target` pins one. Any multi-file
result measured without it is measuring the wrong thing.

**Caveats:** one run, one target domain, one reviewer family, and
`llm-translation` is not byte-stable.

## `llm-translation` — model scale, and a reversal

`runs/20260819-husker-scale/RESULT.md`, then
`runs/20260819-prompt-fix-32b/RESULT.md`.

**A bigger model was the worse husker.** `Qwen2.5-Coder-32B-Instruct` left more
than three quarters of code lines byte-identical, with a distinctive failure
mode: it translated docstrings and comments and left the code alone. One file
came back identical to its input except for a single word.

The proposed mechanism — the system prompt's *"DO NOT: Refactor or improve the
code in any way"*, honoured more literally by a stronger instruction-follower —
**was tested, and it was part of the cause but not all of it.**

| same six files, same target | code verbatim | domain retention | copied span | leak lines | passthrough files |
|---|---|---|---|---|---|
| 32B, prompt v1 | 74% | 41% | 54% | 53 | 2 of 6 |
| 32B, prompt v3 | 69% | 31% | 42% | 42 | 0 of 6 |
| 7B, prompt v1 | 49% | 21% | 20% | 37 | 1 of 6 |
| **7B, prompt v3** | **49%** | **18%** | **15%** | 8 | 0 of 6 |

Rewriting the clause removed every whole-file passthrough at both scales, stopped
husks collapsing (v1 turned a 258-line file into 92), and got own-module imports
renamed. **On equal footing the 7B wins by more than it had across prompts** — and
the 7B remains the recommendation.

**This contradicts the repo's older scale finding** (verdict flipping from
`viable-with-caveats` at 7B to `viable` at 14B). That was a different corpus
asking different questions, and it should not be cited as evidence that scaling
up improves husking generally.

## The prompt ratchet — a null result, and where the effect actually lives

`runs/20260819-prompt-fix-32b/RATCHET.md`. Six revisions, 42 husk runs, 7B,
`evals/run_replicates.py` as the gate.

**No revision after v3 is distinguishable from v3 at this sample size.** Pooled
domain retention: v3 0.166, v4 0.148, v5 0.139, v6 0.196 — every range overlaps
every other, and the two metrics disagree about the ordering. v4 won its first
three replicates cleanly under a pre-registered rule and then failed to reproduce
on a confirmation triple of the *identical* prompt (0.111 → 0.185).

**On copied span the additions are actively worse.** Pooling all 24 runs of
v3-plus-additions against v3's 6: **0.192 vs 0.139, permutation p = 0.0034** — the
strongest result of the session, and it says every clause added after v3 made the
husker copy more source. v4 was reverted; **v3 ships** (`prompts/v3.txt`, live in
`husk-api/app/solutions/llm_translation.py`).

**A single run cannot adjudicate a prompt revision here.** The first measurement
of the session ran the same prompt, model, corpus and target twice and got 8 and
14 leak lines. Every single-run comparison in this repository predating 2026-08-19
is therefore *unadjudicated* — not wrong, unable to separate an effect from a
resample.

**A measurement caught grading its own subject.** v7 and v8 were first scored with
the post-condition gate live, which drops refused files from the sample: v7 looked
like a decisive win at 0.116 (p = 0.009) and re-ran at 0.188 once the gate was
neutralised. `run_replicates.py` now disables the gate by default and warns on
unequal file counts.

### Where prompt effects ARE visible: individual identifiers

Averaging hides this. Three specific identifiers, present-or-absent per run:

| arm | runs | real SEC CIKs kept | URL query ID kept | folder-ID list kept |
|---|---|---|---|---|
| v3 (no numbers clause) | 6 | 5/6 | 6/6 | 6/6 |
| v4 | 6 | 2/6 | 6/6 | 6/6 |
| v5 | 3 | 0/3 | 3/3 | 3/3 |
| v6 | 3 | 1/3 | 3/3 | 3/3 |
| **all** | **18** | **8/18** | **18/18** | **18/18** |

**A document ID inside a URL and a list of nine real folder IDs survived 18 runs
of 18**, across four revisions — twelve of which explicitly name those two things
as content that must be replaced. The model rewrites the URL's host, rewrites its
path, and leaves the ID sitting between them. Restating the rule as a mechanical
test did not move it; fixing a worked example that contradicted the rule did not
move it.

**The reading: `llm-translation` husks numbers unreliably, and better
instructions do not fix it.** A numeric key is often the strongest
re-identification handle in a file — a CIK names the exact company. This is
empirical support, on one corpus and one model, for `docs/working-paper.md` §4.2's
claim that prompt-only enforcement of the husking invariant is a category error,
and it is the case for RSCH-2's verifier as well as its acceptance test.

## The leak metric was wrong, and every earlier number understated

`evals/score_husk.py` originally measured leakage by matching an authored word
list, which is **blind to a span of source returned verbatim that happens to
contain no domain vocabulary.** It now counts copied spans, and shares one
implementation with the request-path gate.

Re-scored, the 32B under the current prompt reads **31% domain retention and 42%
copied span**. The first sounds like a moderate vocabulary leak; the second says
nearly half the caller's code came back unrewritten. 7B: 18% and 15%.

## The post-condition gate

`runs/20260819-prompt-fix-32b/POSTCONDITION.md`;
`husk-api/app/solutions/_husk_check.py`; calibration by
`evals/calibrate_postcondition.py`.

The service now compares its output to its input, retries once naming what was
copied, then **fails closed**. Three independent triggers: a run of 20 identical
code lines (or 15% of the input); 35% of the source returned across all spans of
5+ lines; or identifier retention ≥92% together with whole-text similarity ≥95%.

Calibrated on **150 file-observations across 25 trees**. Live acceptance: 4 of 6
files husked, 2 refused. Archive refusal rate **28 of 150 (19%)** — every refusal
carrying either 20+ consecutive or 35%+ total byte-identical source lines.

**Building it found a second form of the defect and corrected an earlier claim.**
*Partial* passthrough — top of the file translated, bottom copied verbatim —
occurs in **20 of 150 observations**, 14 of them under the current prompt. One
case returned 26 verbatim lines including a regex constant holding a live URL
path, while scoring **0% domain-term retention and zero leak terms**, so every
privacy metric in this repository called it clean. "Zero passthrough since the
prompt fix" is true only of *whole-file* passthrough.

The third trigger was added after the copied-span rescore showed the first two
were under-powered: **copying distributes.** One husk returned 66% of its source
in spans of 5–14 lines and passed a gate watching only for a run of 20.

**This is not the verifier.** RSCH-2 specifies a CPG-isomorphism +
anti-pattern-density + comment-speech-act checker that certifies a husk *preserved
the pathology*. This checks one much narrower thing — that the output is not the
input. A floor, not the property the paper claims.

## Source-domain recovery — one probe, contested framing

`runs/20260819-agentic-multifile/opus_pathfixed_qwen.json`. An Opus reviewer,
given a husked tree with clean contents **and** husked paths, recovered
"MARC 21 / library catalog" at confidence 0.72 — from parsing constants alone
(`tag[1:4]`, `$` subfield splitting, the `010` control/data-field boundary),
while detecting 9/9 defects at mean confidence 0.861.

**This is one probe, not RSCH-1, and its framing is disputed.** The corpus
implements a *public standard*, which is close to a worst case and unrepresentative
of proprietary code — an argument recorded in `LIMITATIONS.md` §2. It is a reason
to run the pre-registered experiment, not a substitute for it.

## What is not measured

- **RSCH-1 — identifier-level re-identification.** The pre-registered experiment
  **has run** (2026-08-19), and all four solutions FAIL its §8 criterion — see
  `LIMITATIONS.md` §2, which is authoritative. What remains unmeasured is
  narrower: the corpus is synthetic, so re-identification of *a real
  organization, product line or proprietary algorithm* is untestable here by
  construction. RSCH-1 measures problem-domain leakage and nothing narrower.
  Cohen's κ on the judge pass is also still owed, so that endpoint's table is
  descriptive only.
- **`fpe` and `literal-tagging` against the current corpus.** Both carried
  `viable-with-caveats` verdicts against the superseded fixture. Neither has been
  re-evaluated. `fpe`'s cipher configuration also changed on 2026-08-19 (the
  alphabet gained `_`, which had been silently colliding onto `H`, and the
  source-baked default key became a random per-process key), so the old
  pseudonyms were not reproducible even before the corpus was replaced.
- **Any language but Go, TypeScript and Python.** The post-condition gate's
  comment-stripping is a documented heuristic, not a parser.
- **Byte-stability.** `llm-translation` returns valid-but-different husks for the
  same input, so an input-hash cache key is unsafe and every single-run comparison
  needs replicates.
- **Multi-file husking as a product path.** Each file is husked in isolation, so
  husked trees do not compile — imports name packages that do not exist. Real, but
  a limit of one-file-at-a-time husking rather than a bug in it.

Full gap record: `LIMITATIONS.md`.
