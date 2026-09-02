# Limitations

**This file is authoritative.** The README's "Status" section is a summary of it and must stay a
strict subset — if the two ever disagree, this file is correct and the README is stale. The same
applies to `docs/working-paper.md` and `docs/draft-1.md`.

Last reviewed: 2026-08-30. (§2.0.2 records RSCH-1B, run 2026-08-20.)

---

## 1. What this is, and what it is not

effigy is a **research artifact and feasibility study**. It is not a security product, and nothing
in this repository is a security guarantee. The running service is a demonstration of a technique,
not a hardened implementation of it. Do not put real proprietary source through it and conclude
anything about your exposure.

## 2. Status of the central privacy claim: **measured once, completely, and it fails**

The pre-registered experiment (`evals/preregistration.md`, RSCH-1) was run on 2026-08-19 against
the six-domain corpus. An account spending cap halted it mid-flight; it was **resumed under the same
run id and completed** — **986 of 998 attacker calls**, all **three** held-out domains, 12 calls
never reaching the model and excluded as missing rather than scored wrong.
`evals/runs/20260819T182111Z-rsch1-held-out/summary.md` is authoritative. (That directory's
`NOTE.md` describes the *partial* state and is marked superseded; an earlier revision of this
section quoted it and reported two domains and 502 calls. Corrected 2026-08-19.)

Panel maximum across the two attackers, exact counts beside every rate:

| arm | menu (recognition) | free text, judge MATCH | leak-term veto |
|---|---|---|---|
| blind (floor) | 10/30 (33.3%) | 0/59 (0.0%) | — |
| **source (control)** | 30/30 (100%) | 60/60 (100%) | — |
| `fpe` | 30/30 (100%) | 60/60 (100%) | 🚫 93.3% |
| `literal-tagging` | 30/30 (100%) | 59/60 (98.3%) | 🚫 96.7% |
| `composed` | 30/30 (100%) | 51/57 (89.5%) | 🚫 |
| **`llm-translation`** | 65/83 (78.3%) | 86/173 (49.7%) | 🚫 50.0% |

**All four solutions FAIL §8**, including `llm-translation` (p_husk 78.3% vs p_blind 33.3% at the
strongest attacker, cluster-bootstrap 95% CI on the difference **[+0.243, +0.640]**), and all four
trip §8's hard leak-term veto.

**But `llm-translation` is the only transform doing any work.** It roughly halves every leakage
measure while `fpe` and `literal-tagging` sit at ceiling on all three endpoints — exactly as §5
predicted in advance. The finding is not "husking does not work"; it is that the LLM rewrite
substantially degrades domain signal and still does not clear the bar this project set itself.

### 2.0 The BLIND floor was response bias, not a floor

Added 2026-08-19 (amendment A4.1). Every accuracy above is confounded by the attacker's answer
distribution: the BLIND attacker answered `ham-radio-logbook` on **26 of 29** and **23 of 30** items
regardless of what it was shown. Holding each attacker's answers fixed and permuting the true labels
10,000 times across source files gives what that bias alone buys:

| arm | observed | permuted null | corrected | p |
|---|---:|---:|---:|---:|
| blind | 0.345 / 0.333 | 0.320 / 0.300 | **+0.025 / +0.033** | 0.41 / 0.39 |
| `llm-translation` | 0.721 / 0.783 | 0.282 / 0.304 | **+0.439 / +0.479** | 0.0000 |
| source, `fpe`, `literal-tagging`, `composed` | 1.000 | 0.332 | **+0.668** | 0.0000 |

**BLIND has no recoverable signal at all.** The 10-number structural stub carries nothing about the
domain. The husk−blind *difference* barely moves, so the FAIL verdicts stand — but "33.3% floor"
should never again be described as weak-but-real structural signal. `permutation.md` beside the
summary carries the analytic cross-check.

### 2.0.2 The architecture itself leaks — RSCH-1B, 2026-08-20

Registered in advance as amendment A4 and run against the held-out split. Each source file was
mechanically canonicalised — every identifier, string literal, comment and JSX text node removed,
control flow / call graph / arity / nesting / coupling left exactly intact — and the same attacker
panel was asked the same 12-option question. Eleven hard gates enforce the transform, and three
model-free probes find nothing left in it (structural counters 0.047 against a 0.165 null;
canonicalised tokens 0.000 against 0.154; no token concentrated in any domain).

| arm | observed | permuted null | corrected | p |
|---|---:|---:|---:|---:|
| `structure-only` | 0.467 / 0.520 | 0.232 / 0.276 | **+0.234 / +0.244** | 0.0014 / 0.0031 |
| `structure-only-nonum` | 0.500 / 0.538 | 0.243 / 0.273 | **+0.257 / +0.265** | 0.0008 / 0.0023 |

Against the anchors — BLIND **+0.03**, `llm-translation` **+0.44 / +0.48**, source **+0.67** —
**shape alone carries roughly half the leak a husk carries.** Numeric literals do not explain it:
canonicalising every numeric value left the score unchanged or slightly higher, so this is not the
"format constants" story of §2 below. It is control flow, call graph, arity, nesting and coupling.

**This is the most consequential limitation in this file.** effigy's premise is that architectural
pathology must be preserved. If preserved architecture is itself domain-informative, then the thing
the technique is *required* to keep is part of what leaks, and no verifier enforcing that invariant
can fix it. The claim that needs re-scoping is `docs/working-paper.md` §4.2's, and the honest form
is a trade-off — structural fidelity against domain privacy — rather than a promise of both.

Caveats, and they are load-bearing. **This run's own §8 validity gate is recorded as FAILED**
(`summary.md` §1): it carried no `source` control arm and no `BLIND` arm, so `p_source` is 0/0 and
the gate cannot be evaluated, and §3 of that summary marks both arms **NOT COMPUTABLE** on §8's
verdict machinery. The +0.234 / +0.257 figures are therefore *not* §8 verdicts — they come from the
permuted response-bias baseline registered as amendment A4.1, which needs no BLIND arm, and they
should be read as that and nothing more. Also: recognition on a 12-option menu, not recall; **the
open-ended endpoint was not run**, so there is no free-text or hard-veto measurement; coverage 111/120,
with nine Kimi records lost to router 504s (transport, split 5/4 across arms); A3.2 still binds, so
contents only, never paths.

### 2.0.1 One leak channel was mechanical, and is now closed

The Go module name — which in this corpus **is** the domain label — survived **22 of 90**
`llm-translation` husks. On those the attacker was right **44/44 (100%)**; on husks where it was
removed, **83/125 (66.4%)**. `llm_translation.py` had always required own-module imports to be
renamed, so this was a shipped defect rather than a property of husking, and it is now enforced by a
fourth trigger in `_husk_check.check` (fires on 14/14 real cases, 0/76 clean ones — development-log
counts; no committed run records them).

**The residual matters more than the fix.** The remaining 8 leaks (2 Go, 6 TS/TSX) arrive as
*content* — `<h1>qsolog</h1>` — with no import to derive the name from. No import-based rule can see
those; that is work for the unbuilt verifier (§5).

**Three qualifications that are load-bearing.**

*Recognition is not recall.* C1 is phrased in terms of a forced choice over twelve options with the
correct one on the menu. `llm-translation` fails that while removing two-thirds of the free-text
signal. Quoting the menu number alone overstates the leak.

*Copying does not explain it.* Mean copied-span share was **0.269 when the attacker was right and
0.276 when it was wrong** — indistinguishable. `composed` leaks at 100% while
copying **0.000**. So the leak survives a genuine rewrite and is not fixable by tightening the
passthrough gate. This is direct support for `docs/working-paper.md` §4.2 and the strongest
argument yet for RSCH-2.

*Nothing here tests identity.* See §2.1.

### 2.1 What RSCH-1 structurally cannot test

The corpus is **synthetic**. No real organization, product, vendor or regulator exists in it, so
identifier-level re-identification — *"the organization, the product line, the proprietary
algorithm, the regulatory domain"*, which is what the threat model actually names — is untestable
here **by construction**, for every arm.

The evidence: the only "specific identifier" ever recovered from any husk was `meterworks`, the
corpus's own invented module name — which was a mechanical defect, now closed (§2.0.1). The one real-world company name that appeared in a guess does
not occur anywhere in the corpus and was fabricated by the attacker. Even the **unhusked SOURCE**
control named a real outside entity on only a minority of items, all guesses about the sector.

So RSCH-1 measures **problem-domain** leakage and nothing narrower. A result in either direction
says nothing about whether a husk protects a real organization's identity. That needs real
proprietary source with real identifiers in it — a different experiment with different consent and
handling requirements, and it is not currently planned.

### 2.2 A concrete defect the run surfaced

`llm-translation` left the source module name `meterworks` in its output, although its system
prompt explicitly requires imports of the input's own modules to be renamed. Directly checkable,
and a ready-made acceptance test for RSCH-2's verifier.

---

*Historical, kept because it is what the file said before the measurement existed:* everything
below was a spot observation, not a measurement of the claim.

**One observation suggesting a leak, not reproduced.** On 2026-08-19 a frontier model, shown a
husked multi-file tree with clean contents and clean paths, correctly named the source domain
("MARC 21 / library catalog", confidence 0.72), reasoning from parsing constants — `tag[1:4]`, the
`$` subfield split, the `tag >= "010"` boundary. One trial, one corpus, one model.

**A follow-up on different real code did not reproduce it.** Six files from a private repo in an
unrelated domain were husked and checked (`evals/runs/20260819-dogfood-sibling/`). Five of six
transformed genuinely and retained **zero to two** domain terms, none verbatim — including three
parsers of public data formats, which scored 0, 1 and 2. So the "format constants carry the domain"
generalisation is **not supported** and must not be published on the strength of the single MARC
observation.

**Withdrawn.** An earlier claim in this file, that third-party dependency names constitute an
unhuskable domain fingerprint, was wrong. It rested on a tree in which 76% of the leak-bearing lines
were byte-identical to the source, i.e. the files had not been transformed at all. Retained here as
a correction rather than deleted.

### The defect that IS measured: silent passthrough

`llm-translation` sometimes returns its input nearly unchanged and reports success. Measured at 1 of
6 files on one repo (ratio 0.97, 118/162 lines byte-identical, the only edit being docstring-to-
comment conversion) and 5 of 7 on another.

There is no post-condition check of any kind: the solution verifies that a response is non-empty and
not truncated, and nothing else. **This is a privacy defect, not a quality one.** A caller receives
what they believe is a husk and it is their source code, with nothing in the response to
distinguish the two. A similarity check against the input would catch it outright and does not
exist.

**Closed in the request path (2026-08-19).** `llm-translation` now compares its output to its
input and refuses to return a husk that is substantially the source
(`husk-api/app/solutions/_husk_check.py`, calibrated in `evals/calibrate_postcondition.py` against
150 file-observations, 3 of 3 known passthroughs caught). A refusal retries once, naming what was
copied, then fails closed with a 500 rather than returning a degraded husk with a warning — a
warning in a field the caller may not read is how this defect survived in the first place. Live
acceptance on a whole tree: 5 of 6 files husked with the first two triggers, 4 of 6 once the third
shipped (`evals/runs/20260819-prompt-fix-32b/POSTCONDITION.md`). Every response now carries
`meta.postcondition` with the measurements and the verdict, because the caller cannot run this
comparison themselves.

**Every leak number in this repository was understated, and the scorer is fixed (2026-08-19).**
`evals/score_husk.py` measured leakage by matching words against an authored term list, which is
blind to a span of source returned verbatim that happens to contain no domain vocabulary. It now
counts copied spans — the share of the source's code lines returned inside runs of 5+ consecutive
byte-identical lines — and shares one implementation with the request-path gate so the two cannot
drift. Re-scored:

| run | domain retention (vocabulary) | **copied span** |
|---|---|---|
| 7B, current prompt | 18% | **15%** |
| 32B, current prompt | 31% | **42%** |
| 32B, old prompt | 41% | **54%** |

The 32B's 31% domain retention reads as a moderate vocabulary leak. The same output returns 42% of
the caller's source verbatim. Both numbers are true; only one of them was being reported.

**And building it found a second form of the defect (2026-08-19).** *Partial* passthrough: a model
translates the top of a file and copies the bottom out verbatim. Measured at **20 of 150
file-observations carrying 20+ consecutive byte-identical code lines**, including 14 of the 126
produced under the current prompt. One instance returned 36 consecutive lines with the real table
and column names while scoring 0.84 similarity and 78% identifier retention; another returned 26
lines — a regex holding a live URL path, a whole dataclass, an entire parse function — while
scoring **0% domain-term retention and zero leak terms**. Every privacy metric in this repository
called that file clean. The earlier statement that no passthrough has been observed since the
prompt fix is true only of *whole-file* passthrough. See
`evals/runs/20260819-prompt-fix-32b/POSTCONDITION.md`.

**Partly mitigated at the prompt, not at the seam (2026-08-19).** The system prompt told the model
"DO NOT: Refactor or improve the code in any way", which a strong instruction-follower reads as
"do not change the text". Rewriting that clause removed every observed passthrough on this corpus:
32B went from 2 of 6 files returned substantially unchanged to 0 of 6, and domain-term retention
fell from 41% to 31% (`evals/runs/20260819-prompt-fix-32b/`). **At that point the defect itself was
unchanged** — the service still returned whatever the model produced without comparing it to the
input. The request-path gate above, closed later the same day, is what changed that: the service
now runs the same copied-span comparison `evals/score_husk.py` uses, so a future model, prompt, or
temperature that reintroduces passthrough is refused rather than returned.

## 3. What each solution actually destroys

The two deterministic solutions destroy exactly the half the other preserves.

| | Identifiers | String literals | Comments | Import paths |
|---|---|---|---|---|
| `fpe` | **destroyed** | preserved verbatim | preserved verbatim | preserved verbatim |
| `literal-tagging` | preserved verbatim | **destroyed** | preserved verbatim | destroyed |
| `llm-translation` | rewritten | rewritten | rewritten | rewritten |

**Instructing a model to remove an identifier is not the same as it being removed (measured
2026-08-19, 18 runs).** Four prompt revisions were ratcheted against each other with replicates
(`evals/runs/20260819-prompt-fix-32b/RATCHET.md`). A document ID inside a URL, and a list of nine
real folder IDs, survived **18 runs out of 18** — twelve of which contained a clause naming exactly
those two things as content that must be replaced. The model rewrites the URL's host and its path
and leaves the ID between them. Restating the rule as a mechanical test did not move it; fixing a
worked example that contradicted the rule did not move it. On aggregate vocabulary leakage, no
revision after the first was distinguishable from it at n=6 — the run-to-run spread of a single
fixed prompt is wider than the differences between prompts.

This is empirical support, on one corpus, for `docs/working-paper.md` §4.2's claim that
prompt-only enforcement of the invariant is a category error, and for the unbuilt verifier (RSCH-2).
**A husk cannot be trusted on the strength of the prompt that produced it.**

**Numeric literals are the least reliably husked content (measured 2026-08-19).** Across five husk
runs at two model scales and three prompt revisions, a URL's query-string ID and a list of nine real
folder IDs survived byte-identical in **every** run that produced those lines — the model rewrote the
host and the path of the URL and left the ID inside it untouched. Real SEC CIK numbers survived in
four runs of five, sitting beside company names the model *did* translate; the 7B under the newest
prompt replaced them. Numeric keys are frequently the strongest re-identification handle in a file —
a CIK names the exact company — and no revision of "rename everything" made replacing them
dependable. `evals/runs/20260819-prompt-fix-32b/`.

Concretely: an `fpe` husk of Go source still contains lines like
`"github.com/<org>/<product>/internal/<domain>"` — the organization, the product line, and the
regulatory domain, in plaintext. The recorded evaluation presents exactly such a husk as a success,
because it was scoring dependency reconstruction, not privacy. Under the threat model in
`docs/draft-1.md` §2, which names *"the organization, the product line, the proprietary algorithm,
the regulatory domain"* as what the adversary wants, that husk is a complete failure of the
primitive.

`literal-tagging` is the mirror image: every type name, function name, and variable name survives.

### File paths and names are not husked at all

**Measured 2026-08-19.** Every solution transforms file *contents*. None of them
touches file *paths*, directory names, or file names — the API takes a string and
returns a string, and the name of the thing it came from never enters the
request.

For single-file use this is invisible. For a repository it is a hole: a tree
whose every file body was faithfully rewritten into an unrelated domain still
announced its source domain through the filesystem. In the measured run the husk
retained `marc21.go` (MARC 21 is a library cataloguing standard), `dublincore.go`
(Dublin Core is library metadata), `holdings.go`, `HoldingDetail.tsx`,
`branches.go`, `cmd/stacksd`, and the root directory name itself — 23 occurrences
of one source-domain term across the paths.

**The source domain was recoverable from `ls -R` alone, without opening a single
file.** Any deployment that husks a repository rather than a snippet has to
rename the tree separately; nothing in this project does that for you.

**RSCH-1 deliberately closes this channel in its harness, and that is flattering
to the husk.** The re-identification experiment shows its attacker the artifact's
bytes and its language and nothing else — no path, no filename, no directory
layout (`evals/preregistration.md` amendment A3.2). The reason is that including
the path would measure a channel the tool never claimed to close and would drive
every arm, including the unhusked SOURCE control, to near-100%, making the
comparison vacuous. But a reviewer in real use usually *does* see filenames. So
**no RSCH-1 result may be reported as "the husk does not leak the source
domain"** — only as "the husk's *contents* do not leak it at this corpus scale,
measured with the path channel held out." The path channel is wide open and is
measured above, not there.

## 4. The solutions do not compose in the shipped service

`POST /husk/{slug}` runs exactly one solution. There is no pipeline, no chaining, and no combined
mode. The design catalog marks the O1×I4 pairing as invalid outright; O1×I3 (`fpe` after
`literal-tagging`) is marked compatible, but you would have to chain the two calls yourself, and no
recorded evaluation covers the composition.

## 5. There is no verifier

The design's own method section calls the verifier **"the load-bearing piece of the design"** and
says that *"without it, the privacy primitive degenerates into a stochastic rewriter with no
diagnostic guarantee,"* and that prompt-only enforcement of the pathology-anchor invariant is
**"a category error."**

No verifier exists. Grepping the entire source for CPG / isomorphism / anti-pattern-density /
speech-act terms returns two hits, both prose: a docstring title, and one sentence *inside a system
prompt string* in `husk-api/app/solutions/llm_translation.py`. That sentence is the entire
enforcement mechanism **for the pathology-anchor invariant**, which is the property the design says
must be certified.

One narrower post-condition does ship, and §2 above describes it: `app/solutions/_husk_check.py`
compares the output against the input and fails closed when a husk is substantially its own source
or still carries the input's own module name. It is a **passthrough floor, not the verifier** —
`algorithmTests.md` classifies it as "a floor, not the property the paper claims." Nothing computes
CPG isomorphism, anti-pattern density, or comment speech acts.

So the design document argues that the shipped configuration is a category error, and the shipped
configuration is that category error. Results run on rewriter goodwill.

## 6. FPE key posture

- The key protects **identifier tokens only**. Comments and string literals are untouched (§3).
- **Set `FPE_KEY`.** Without it a random key is generated per process: husks are internally
  consistent within one run, but pseudonyms change on restart, so a re-identification map from an
  earlier process will not dehusk.
- A malformed `FPE_KEY` raises rather than falling back.
- **All `fpe` outputs measured before 2026-08-19 — since withdrawn from `algorithmTests.md` with
  their fixture — were produced under a key that is baked into this source file** and under the
  pre-2026-08-19 62-character alphabet. They are historical; see
  §12/F7.
- The cipher is `pyffx` 0.3.0 — a pure-Python Feistel construction, **not** NIST SP 800-38G FF1 or
  FF3-1 (HMAC-SHA1 round function, no tweak parameter, unmaintained). The design catalog cites
  SP 800-38G as prior art; the implementation does not deliver it. Deterministic encryption over a
  2-character identifier is a 63² = 3,969-element domain — a codebook, not a cipher.

## 7. Output is not deterministic

`llm-translation` is not byte-stable. Measured on the earlier, since-withdrawn fixture — no committed
run records it; see the banner at the top of `algorithmTests.md` — two runs of the same input at
temperature 0.2 against the 14B model produced **144 and 159 lines, with 15 vs 16 top-level exports**, differing in which entity the
PATCH endpoint operated on. Both were valid translations. At 7B the same test produced 42 and 76
lines with disjoint function sets.

Consequences: caching on an input hash alone is unsafe — the honest key is
`(input_hash, model, temperature, target_domain, seed)`. Nothing caches today, so this is latent
rather than live. But it also means **a husk cannot be reproduced on demand**, which matters for any
audit trail. (Target *selection* is deterministic — a sha256 of the input. Do not confuse that with
deterministic output.)

## 8. Model coverage is thin, uneven, and does not improve with scale

Three scales of one family have been evaluated — `qwen2.5-coder` at **7B, 14B and 32B** — plus a
single `meta-llama/Llama-3.1-8B-Instruct` husk (`evals/runs/20260819-agentic-multifile/`). None is a
repeated measurement.

**Scaling up made the husker worse, not better.** §2.2's re-scored table above is the authoritative
comparison: the 32B returned **42% of the caller's source verbatim** against the 7B's **15%**, and
31% domain retention against 18% (`evals/runs/20260819-prompt-fix-32b/`,
`evals/runs/20260819-husker-scale/`). `algorithmTests.md` states the conclusion plainly — "a bigger
model was the worse husker" — and **the 7B remains the recommendation.**

An earlier 7B→14B "feasibility verdict flips" finding is **superseded** and must not be cited:
`algorithmTests.md` retires it as "a different corpus asking different questions… it should not be
cited as evidence that scaling up improves husking generally."

Nothing has been shown to transfer to another model family at any scale. The web UI offers a
**32-model dropdown**, selectable per request — **none of those 32 has any recorded evaluation.**

## 9. Corpus scale

The `llm-translation` fidelity results that the working paper builds on rest on **three single
files** (one Go, one TS, one TSX); `literal-tagging` used four, `fpe` used eight. Other runs are
wider — `evals/runs/20260819-dogfood-sibling/` and `-husker-scale/` cover six Python files from an
unrelated domain — but none is broad.

**Multi-file translation is unimplemented in the shipped service, not unevaluated.** `POST
/husk/{slug}` takes one string and returns one string. The multi-file results in `algorithmTests.md`
(9 of 9 defects detected across two husked trees) were produced by eval-side harnesses —
`evals/husk_tree.py` and `evals/husk_paths.py` — on one tree, one target domain, one reviewer
family. The 7B cross-file drift suggests scaling this will not be easy.

Those fidelity runs all came from a **single problem domain**, which is why no re-identification
number computed against that corpus would have been interpretable: an attacker who always guessed
that one domain would have scored 100% without reading anything. **That rebuild is done** — the
corpus is now six domains and 72 artifacts (`corpus/DOMAINS.md`, gated by `evals/verify_domains.py`),
and RSCH-1 and RSCH-1B were run against its held-out split. The single-domain caveat applies to the
fidelity results above, not to the re-identification experiments.

### 9.1 The domain corpora parse; they do not build

`corpus/DOMAINS.md` §5 gates the five RSCH-1 domains on **parsing**, not linking — §5.2 requires
only that `gofmt -e -l` is silent, and §5.3 states outright that unresolved-import diagnostics are
"expected — these compile standalone." They are husking *input*, not runnable services.
`evals/verify_domains.py` gates exactly those five, and all five pass; `corpus/stacks` is gated
separately by `evals/run_eval.py --verify`, and passes too. **None of the five ships a `go.sum`**
(only `corpus/stacks` has one), and two of them (`qsolog`, `tremorline`) additionally import an
`internal/store` package that was never generated, so `go build` fails in all five. **That is within
contract, not a defect** — but it will surprise anyone who clones the repo and tries to run a
domain, so it is recorded here.

`corpus/stacks/` is the exception and is genuinely buildable and tested (Go 3/3, vitest 33/33): it
is the pathology corpus that `corpus/PATHOLOGY.md` anchors and `evals/run_eval.py --verify` gates,
not an RSCH-1 domain.

### 9.2 The shipped prompt differs from the evaluated one, in one example

`husk-api/app/solutions/llm_translation.py`'s system prompt is the text evaluated as **v3** in
`evals/runs/20260819-prompt-fix-32b/` with the illustrative few-shot rewritten for publication: the
input half moved off its original domain, and the output half's verb was renamed with it so the
pair stays coherent (`settle_booking` → `issue_booking`). Every *instruction*, the ordering, and the
example's structure — same lines, same FIXME position, same control flow — are unchanged. The
shipped text is **4793 characters against the artifact's 4795** (4807 and 4809 bytes in UTF-8). `evals/runs/20260819-prompt-fix-32b/prompts/v3.txt` remains
the byte-exact text the recorded numbers were produced with and is deliberately not synchronised to
the shipped file. **No recorded number was re-measured after this change.**

That means the original example survives verbatim in the six committed prompt artifacts
(`prompts/v3.txt` through `v8.txt`) while the shipped prompt no longer carries it. This is
deliberate and is the only defensible ordering: those files are the evidence, and editing them to
match a later publication decision would falsify the record of what was actually run. If the two
disagree, the artifact is what produced the numbers and the shipped file is what a caller gets.

## 10. Known correctness defects, open

Found on the earlier, since-withdrawn fixture — their record left `algorithmTests.md` with it (see
its banner) — and unfixed:

- **`literal-tagging` breaks on nested template literals** — TSX backtick interpolation defeats the
  regex and can yield syntactically invalid output.
- **Import paths collapse to `<PATH:n>`/`<MSG:n>`** and become unrecoverable — the single most
  damaging case for dependency-graph reconstruction, which is the primary downstream use.
- **MIME types are misclassified as `PATH`** (`application/json` matches the path regex), a
  documented false-positive class.
- **`fpe` leaks bare JSX text nodes** — there is no parser, so text between JSX tags is not
  recognized as a literal and is enciphered as identifiers.

## 11. Threat-model exclusions

Out of scope by design: an adversary with access to the rewriter's weights or activations, and side
channels generally.

Additionally true of this implementation, and not to be mistaken for design:

- The re-identification map is **client-held and unencrypted**. It travels in a normal JSON response
  body and sits in a browser tab with no expiry. For `fpe` it is a complete identifier dictionary of
  the source; for `literal-tagging` it maps every placeholder back to its literal, including
  anything classified as a key. One leaked map is a total compromise of that husk.
- The service has **no authentication** of any kind.
- The service is **not hardened**: importing the app writes to disk, so it will fail to start on a
  read-only filesystem, and a stub solution (`example`, which simply reverses its input) is
  registered on the public API surface.

## 12. What would falsify this

The central claim, stated precisely enough to test:

> **C1.** For source within the evaluated envelope (Go/TypeScript/TSX, single files of 40–400
> lines), a husk produced by `llm-translation` does not let a frontier-model adversary — one who
> knows the tool, the algorithm, the system prompt, and the target catalog — identify the source's
> problem domain at a rate meaningfully above what the same adversary achieves from structural
> metadata alone.

Every qualifier in that sentence is load-bearing, and each is a limitation stated as a scope.

**Falsifiers:**

- **F1** — husk recovery exceeds the blind-structural-metadata baseline by ≥0.25 with the confidence
  interval excluding zero, **for any attacker in the panel**. C1 false as stated.
- **F2** — an open-ended attacker names a true organization, product, regulation, or proprietary
  system on ≥5% of husks. C1 false in the sense §2 of the threat model actually cares about.
- **F3** — a single frontier model, given one husk and this public repo, reconstructs a
  semantically-equivalent source-domain rendering of the code rather than just a label. This is a
  stronger attack than the planned eval runs, and it is the one a skeptic will try first. Naming it
  costs nothing; being scooped by it costs everything.
- **F4** — recovery rises monotonically with attacker strength across the panel. Even if today's
  best attacker sits at the floor, a monotone trend falsifies C1's *durability*.
- **F5** — *(secondary claim: a diagnosis of the husk is valid for the source)* — a blinded
  comparison of source-diagnosis against husk-diagnosis-mapped-back shows agreement no better than
  diagnosing an unrelated program of similar shape. **Nobody has run this. It is not scheduled.**
- **F6** — *(secondary claim: pathology survives prompt-only enforcement)* — analyzer-computed
  anti-pattern density differs beyond tolerance on ≥10% of husks. Currently **unmeasurable**,
  because no verifier exists (§5). The paper files this claim at *high* confidence on the basis of
  manual inspection of three smells in three files. That confidence is not supported.
- **F7** — *(fpe confidentiality: "unrecoverable without the key")* — **already falsified, on
  2026-08-19.** The default key was a constant baked into `app/solutions/fpe.py`, so any
  default-config husk was decryptable by anyone holding this source:
  `pyffx.String(KEY, alphabet, 18).decrypt("kOkkUJKQ97aMd3lXih")` → `"handleMemberLookup"`. Fixed
  the same day (see `DECISIONS.md`); recorded here rather than quietly removed, because publishing
  your own falsified claim is worth more than never having made it.

**Anti-rationalization rules**, committed in advance:

1. Results are reported at the **strongest** adversary tested, never the mean.
2. An inconclusive result is reported as inconclusive, never as support.
3. If a run is discarded, the reason is recorded and the discarded raw output stays committed.
4. Every result table cites the pre-registration commit SHA.
5. **Standing invitation:** if you break any of F1–F7, open an issue with the husk and the prompt,
   and it will be linked from this file.
