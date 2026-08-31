# Ratcheting the husker prompt — 2026-08-19

Six prompt revisions, 42 husk runs, `Qwen2.5-Coder-7B-Instruct`, the same six
files and the same pinned target throughout. Records: `replicates-*.json`,
`ratchet-pooled.json`, prompt texts under `prompts/`.

**The result is a null one, and it is the most useful thing measured today: the
ratchet hit its noise floor immediately.** No prompt revision after v3 is
distinguishable from v3 at this sample size. What *is* measurable is discrete
per-identifier behaviour, and there the picture is sharp.

**Re-scored the same day with copied-span accounting** (added after a partial
passthrough turned up that every vocabulary metric had scored as clean). It does
not rescue the ratchet, but it points the other way: copied-span share rises
**monotonically across all four arms in the order the prompt grew** — v3 0.139,
v4 0.169, v5 0.188, v6 0.233. A monotonic ordering over four arms is more
suggestive than any single pairwise p-value here, and the suggestion is that
piling on instructions made the model copy more, not less.

## The acceptance rule, fixed before the first challenger ran

A challenger replaces the champion only if, over 3 replicates:

- mean domain retention **below** the champion's mean, **and** its worst
  replicate no worse than the champion's mean;
- mean shape fidelity ≥ 0.98 (the guard: every other metric rewards a husk for
  looking less like its input, and emitting less code is the cheapest way to
  score well on all of them);
- zero passthrough files in every replicate.

## Why replicates at all

The first measurement of the session ran the same prompt, model, corpus and
target twice and got **8 and 14 leak lines**. `llm-translation` is not
byte-stable and the run-to-run spread swamps the differences that had been
reported between revisions. Every single-run comparison in this repository
before today is therefore *unadjudicated* — not wrong, just unable to separate
an effect from a resample. `evals/run_replicates.py` exists to stop that
recurring.

## The measurement was biased by the thing being measured

v7 and v8 were first run **after the post-condition gate went live in
`husk()`**, and the gate changes what gets measured. `husk_tree.py` records a
FAIL for every refused file and writes nothing, so those arms were scored only on
the husks that *passed the gate* — the worst output silently dropped out of the
sample, and the retry improved what remained.

The result looked spectacular: v7 at copied span **0.116** against v4's 0.169,
permutation p = 0.009, the strongest effect of the session. It was an artifact.
The tell was in the record: 6, 5, 5, 6, 5, 6 files per replicate for v7 and 5, 5,
5, 4, 5, 5 for v8, against a clean 6, 6, 6 for every arm measured before the gate
existed. Re-run with the gate neutralised, v7 is **0.188** — worse than v3, and
no better than v4.

`run_replicates.py` now disables the gate by default (`--with-gate` to opt back
in) and warns when replicates score unequal numbers of files, so a measurement
harness cannot quietly grade its own subject again.

## What each revision changed

| | change from the previous revision |
|---|---|
| **v3** | the champion coming in: rewrite-not-edit framing, "do not improve" scoped to structure, rename-everything list, length preservation, worked example, acronym / data-literal / column-name call-outs |
| **v4** | numbers that identify are content; compound dotted string keys are identifiers segment by segment; a two-pass self-review (prose, then literals) |
| **v5** | v4 + the acronym rule restated as a mechanical test ("any token of 2–6 characters that is not an ordinary word") |
| **v6** | v4 + one fix: the worked example kept its identifying number (`0042`) unchanged while the prose told the model to replace such numbers. The example now moves it |
| **v7** | v3 + the numbers clause ONLY — v4's compound-dotted-keys bullet and two-pass tail removed, to isolate which addition carried v4's CIK advantage |
| **v8** | v7 + v4's two-pass self-review tail (i.e. v4 minus the compound-keys bullet) |

## Pooled result

| arm | prompt chars | runs | domain retention | **copied span share** | copied lines |
|---|---|---|---|---|---|
| **v3 (shipped)** | 4795 | 6 | 0.166 | **0.139** (0.119–0.176) | 124 |
| v4 | 6030 | 6 | 0.148 | 0.169 (0.139–0.218) | 155 |
| v5 | 6527 | 3 | 0.139 | 0.188 (0.170–0.199) | 172 |
| v6 | 6128 | 3 | 0.196 | 0.233 (0.193–0.306) | 212 |
| v7 = v3 + numbers clause only | 5474 | 6 | 0.207 | 0.188 (0.146–0.243) | 161 |
| v8 = v7 + two-pass review | 5852 | 6 | 0.254 | 0.201 (0.145–0.252) | 179 |

**Re-scored 2026-08-19 with copied-span accounting, and the ordering reverses.**
On domain retention v4 is nominally ahead of v3 (0.148 vs 0.166, permutation test
p = 0.52 — nothing). On copied span v3 is ahead of every other arm. Copied span is
also the less noisy of the two — pooled CV 0.26 against 0.35 — which makes it the
better objective, and means the ratchet above was optimising the noisier signal.

### v7 and v8: the isolation experiment, and the answer

v7 is v3 plus the numbers clause and *nothing else*; v8 is v7 plus v4's two-pass
self-review. Both were run at n=6 to settle which of v4's additions was carrying
its CIK advantage.

**Neither helped. Every arm built on v3 copies more than v3 does.** Pooling all
24 runs of v3-plus-additions against v3's 6:

| | runs | copied span share |
|---|---|---|
| v3 alone | 6 | **0.139** (0.119–0.176) |
| every v3 + additions arm | 24 | 0.192 (0.139–0.306) |

**permutation p = 0.0034** — the strongest result of the session, and it says the
additions were the problem. Pairwise: v3 vs v7 p = 0.018, v3 vs v8 p = 0.009,
v3 vs v4 p = 0.083.

Prompt length only partly explains it (Spearman rho = 0.60 across the six arms,
n=6, not significant): v7 is shorter than v4 and copies more. So this is not
simply "longer prompts dilute" — an earlier draft of this file claimed a
monotonic length ordering, and v7/v8 break it.

**And v4's CIK advantage did not survive the extra data.** On the runs available
before v7/v8, CIKs were kept 5/6 without the numbers clause and 3/12 with it,
Fisher p ≈ 0.02. With all 18 clause-bearing runs the split is 5/6 versus 9/18 and
**p = 0.34**. There is no established CIK effect.

### So v3 ships, and this is a reversal

`prompts/v3.txt` is live in `husk-api/app/solutions/llm_translation.py`. v4 held
that slot for part of the day on the strength of a CIK effect that more data
dissolved, while costing measurable extra copying. Every clause added after v3 —
numbers, compound keys, mechanical acronym test, two-pass review, and the fixed
example — made the husker copy more source, or made no difference.

Every arm's range overlaps every other arm's range on domain retention. The
metrics disagree about the ordering, which is what noise domination looks like —
and the copied-span column added later disagrees with both, in the one direction
that tracks how much prose each revision added.

**v4 won its first three replicates cleanly and then failed to reproduce.** Its
first triple was 0.111 (0.087–0.137), whose worst run beat the champion's best;
by the rule above that is an accept. A confirmation triple of the identical
prompt returned 0.185 (0.128–0.218). Pooled, the "win" is 0.018 against ranges
0.13 wide. Had the ratchet stopped at the accept, this file would have reported
a prompt improvement that does not exist.

## Where prompt effects ARE visible: individual identifiers

Averaging hides this. Three specific identifiers, tracked per run — each is
present-or-absent, no averaging:

| arm | runs | real SEC CIKs kept | URL query ID kept | folder-ID list kept |
|---|---|---|---|---|
| v3 (no numbers clause) | 6 | 5/6 | 6/6 | 6/6 |
| v4 | 6 | 2/6 | 6/6 | 6/6 |
| v5 | 3 | 0/3 | 3/3 | 3/3 |
| v6 | 3 | 1/3 | 3/3 | 3/3 |
| **all** | **18** | **8/18** | **18/18** | **18/18** |

**The numbers clause works on one class of identifier.** Real SEC CIK numbers
inside a fixture list survived 5 of 6 runs without the clause and 3 of 12 with
it. That is the only prompt effect in this session that the measurement can see
at all.

**And it does not touch the other two, ever.** A document ID inside a URL and a
list of nine real folder IDs survived **18 runs out of 18**, across four
revisions — twelve of which contain a clause naming *"a folder or document ID, a
query-string value inside a URL"* as something that must be replaced. The model
rewrites the URL's host and its path and leaves the ID sitting between them.
Restating the rule as a mechanical test (v5) did not move it. Fixing the worked
example that contradicted the rule (v6) did not move it.

## What this says about the technique

Instructing a model to remove a class of identifier is not the same as the
identifier being removed, and the gap is not closed by better instructions. Two
of the three tracked identifiers were named explicitly in the prompt and
survived every single run.

That is empirical support — on one corpus, one model, one target domain — for
the claim in `docs/working-paper.md` §4.2 that prompt-only enforcement of the
husking invariant is a category error, and for RSCH-2's verifier. It is support,
not proof: 18 runs at 7B on six Python files.

The practical reading: **a husk cannot be trusted on the strength of the prompt
that produced it.** Something has to check the output. As of the same day
something does: `husk-api/app/solutions/_husk_check.py` runs in the request path
and refuses output that is substantially its input (`POSTCONDITION.md`).

## Shipped

**v3 is the shipped prompt** (`prompts/v3.txt`, live in
`husk-api/app/solutions/llm_translation.py`). v4 held the slot for part of
2026-08-19 and was reverted when its only supporting evidence dissolved. v4–v8
are kept here as the record; all five are worse than v3 or indistinguishable
from it on copied span, and none has a surviving advantage on anything else.

## Caveats

- One corpus, one target domain, one model, one language. 7B only — the 32B was
  not re-measured under the ratchet.
- n=6 for v3, v4, v7 and v8; n=3 for v5 and v6. n=3 was demonstrably too small;
  n=6 is not obviously enough, since v4's two triples disagreed.
- v7 and v8 were each measured in a single batch of 6, where v3 and v4 pooled two
  separate triples. A single batch may be more correlated (same provider routing
  window) than two.
- One v7 replicate scored 4 files rather than 6 after two husk calls failed at the
  API. Excluding it moves v7's mean from 0.188 to 0.176 — still worse than v3.
- The multiplicity is real: v7 and v8 were added after seeing v3–v6, and each new
  arm is another chance for noise to look like signal. The pooled v3-vs-additions
  test (p = 0.0034) is the one that does not depend on picking an arm.
- Leak terms are authored (`evals/leak_terms.json`). A term nobody thought of
  leaks silently, and the three tracked identifiers were chosen because earlier
  runs surfaced them — they are not a random sample of what can leak.
- The acceptance rule was written against domain retention, before copied-span
  accounting existed. Every accept/reject decision recorded above was therefore
  made on the noisier of the two metrics. The decisions are not re-litigated
  here; the pooled table simply reports both.
- The husk trees are under `/tmp/ratchet/` and are not committed: they are husks
  of private source that demonstrably still contain real identifiers.
