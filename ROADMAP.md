# effigy — ROADMAP

> ⭐ **SINGLE SOURCE OF TRUTH.** On any handoff or fresh session, **read this first and follow
> only this** for what's left, what's next, phases, acceptance criteria, and decisions. There are
> **no other `*_PLAN` / status docs** — they were consolidated into this file. If another doc's
> status ever conflicts with this one, **this wins.**
>
> - **Strategy / research narrative** (a different layer, not an execution plan):
>   `docs/working-paper.md`, `docs/draft-1.md`, `husk-algorithms.md`
> - **Reference / spec** (opened on demand, never as "the plan"): `algorithmTests.md`,
>   `docs/handoffs/01-06` (build history, kept — see Appendix), `docs/architecture/diagrams/*.mmd`
> - **Decisions**: `DECISIONS.md` (append-only log; roadmap items cite it by date + title)

**Legend:** ✅ done · 🔶 shipped but UNVERIFIED · ⏳ in progress · ⬜ not started · 🔬 verification
owed · 🔁 superseded (kept for its evidence, not as work) · ⛔ **BLOCKS** — the only marker that
gates anything

**Backlog items are not blockers.** No item under a `BACKLOG` / `PARKED` status may be cited as
gating, blocking, or holding up any other work unless it carries a `⛔ BLOCKS:` line with the
owner's verbatim instruction. Absent that line, treat it as non-blocking. An agent that reports
a parked item as a blocker is misreading this file.

**Contents:** §0 Do next · §1 Research track (unbuilt) · §2 Open-decisions index · Appendix

## §0 Do next

> ### ▶ RESUME HERE — 2026-08-20: **RSCH-1B is ANSWERED, and the answer changes the project.**
> The architecture is itself domain-informative (+0.24 corrected, p≈0.002), so the invariant the
> technique must preserve is part of what leaks. **Next action is not RSCH-2 as specified — it is
> re-scoping `docs/working-paper.md` §4.2 before any verifier is built.**
>
> #### Corpus provenance
> The evaluation corpus is synthetic and spec-first: `corpus/stacks/` and the five other domains
> under `corpus/` were generated from `corpus/stacks/SPEC.md` and `corpus/DOMAINS.md`, and
> `evals/run_eval.py --verify` gates that they still satisfy them. An earlier vendored fixture pair
> was third-party-derived and is not part of this repository; results measured against it are not
> carried forward — see the note at the top of `algorithmTests.md`.
>
> #### Known and accepted — the withheld source's *shape* is still here
> The `20260819-prompt-fix-32b` records describe the withheld source repository structurally:
> anonymized path strings (`pkg_a/sources/source_a.py`, `parse/format_a.py`) across
> `evals/runs/20260819-prompt-fix-32b/*.json`, `leak_terms.json`'s domain label, and
> `/tmp/sibling-src` in four docstrings. No source code, and the write-ups describe the source's
> identifiers rather than quoting them. Removing this would gut the prompt-ratchet record, which is this repository's strongest
> result, so it is retained deliberately. RSCH-1B below is the measurement of how much a
> structural description of that kind actually leaks, which is the honest framing for keeping it.
>
> ## ✅ RSCH-1B ANSWERED — **yes, the architecture is itself domain-informative.**
>
> Run `evals/runs/20260820T021753Z-rsch1-held-out`, forced choice, 111 resolved records, **parse
> failure 0%**. Registered as amendment **A4**, committed before any call was made.
>
> | arm | observed | permuted null | **corrected** | p |
> |---|---:|---:|---:|---:|
> | `structure-only` | 0.467 / 0.520 | 0.232 / 0.276 | **+0.234 / +0.244** | 0.0014 / 0.0031 |
> | `structure-only-nonum` | 0.500 / 0.538 | 0.243 / 0.273 | **+0.257 / +0.265** | 0.0008 / 0.0023 |
>
> Against the anchors: **BLIND +0.03** (no signal) · **structure-only +0.24** · `llm-translation`
> **+0.44 / +0.48** · **source +0.67**. **Architecture alone carries roughly half the leak a husk
> carries.**
>
> The artifact has no identifiers, no string literals, no comments and no JSX text — eleven hard
> gates enforce it, and three model-free probes find nothing in it (`evals/structure_probes.py`:
> counters 0.047 vs null 0.165, canonicalised tokens 0.000 vs null 0.154, zero domain-concentrated
> tokens). A reasoning model still recovers the source domain at about twice its own response-bias
> baseline. **The signal is only reachable by a model that reasons about shape; it is not a
> vocabulary channel a bag-of-tokens classifier can find.**
>
> ### What this decides
>
> A4.4's interpretation, pre-committed before the numbers existed:
> *"Well above baseline → preserving pathology necessarily leaks domain. The verifier cannot fix a
> leak inside the invariant it enforces, and `docs/working-paper.md`'s central claim must be
> **re-scoped before RSCH-2 is built**."*
>
> That is the branch we are on. **RSCH-2 is not "build the verifier as specified" any more.** A
> CPG-isomorphism + anti-pattern-density checker enforces preservation of exactly the thing this
> result says leaks. Before building it, §4.2's claim needs re-scoping to say what the technique
> can and cannot promise — the honest form is probably "structural fidelity and domain privacy
> trade off against each other," not "the husk preserves pathology and hides the domain."
>
> ### Reported, not explained away
>
> A4.3 registered a monotonicity check: `nonum` must not exceed `structure-only`. **It does, by
> ~0.02** — inside noise at n≈25–30, but the amendment says report it, so it is reported. Its
> substantive content is that **numeric literals do not explain the signal**: stripping every
> numeric value changed nothing, so this is not the "parsing constants" story from `LIMITATIONS.md`
> §2. It is control flow, call graph, arity, nesting and coupling.
>
> ### Caveats that travel with the number
> - **Recognition, not recall.** Twelve options with the right one on the menu. RSCH-1 already
>   showed the two endpoints disagree sharply. **The open-ended endpoint was NOT run** — the owner
>   stopped further spend (2026-08-20). So there is no free-text or hard-veto measurement for these
>   arms, and no §8 verdict is issued for them.
> - **A3.2 still binds**: contents only, never paths. Flattering to every arm including these.
> - **Coverage 111/120.** Nine Kimi records were lost to router 504s and not refilled; Kimi is
>   n=25/26 per arm rather than 30. All nine were transport failures, split 5/4 across the two arms,
>   so they are missing coverage rather than a biased exclusion.
> - Synthetic corpus, so identifier-level re-identification stays untestable by construction.
>
> ### Also settled this session
> - **The BLIND floor was response bias.** It corrects to **+0.025 / +0.033 at p ≈ 0.40** — no
>   recoverable signal. `evals/permutation_baseline.py`, folded into `score_rsch1.py` as §2b and
>   applied retroactively to the RSCH-1 run. RSCH-1's FAIL verdicts stand.
> - **A mechanical leak channel found, quantified, closed.** The Go module name (which here IS the
>   domain) survived 22 of 90 husks; on those the attacker was right **44/44**, vs 83/125 without.
>   Now a fourth trigger in `_husk_check.check` — fires 14/14 on real cases, 0/76 clean. 69 tests
>   green. **The residual 8 leaks arrive as content (`<h1>qsolog</h1>`) with no import to derive the
>   name from — a ready-made acceptance test for whatever RSCH-2 becomes.**
> - **Harness hardening earned the hard way:** a parse-failure circuit breaker (replayed against
>   this session's 48%-failure run it aborts at 12 calls instead of 64), transport backoff that
>   records its own retries, and a scorer that refuses a verdict when the run has no BLIND arm
>   instead of inventing `p_blind = 0`.
>
> #### Open, cheap, not blocking
> - **κ worksheet is generated and awaiting the owner** —
>   `evals/runs/20260819T182111Z-rsch1-held-out/kappa_worksheet.jsonl`, 98 rows. Hand-label
>   `human_label`, then `kappa_judge.py --score`. **Deliberately not self-labelled.** Until scored,
>   §6.2 keeps the judge column descriptive only.
> - **The harness records latency but not token usage**, so run cost can only be estimated from
>   wall time. Worth capturing `usage` from the API response.
> - **`llm-translation` is bimodal** (judge 86 MATCH / 80 MISS) — a reliability problem, which is
>   what a fail-closed verifier is actually good at.
> ---
>
> #### ✅ DONE: **RSCH-1** — run to a verdict 2026-08-19
> `evals/runs/20260819T182111Z-rsch1-held-out/summary.md`. Validity gate **passed** (p_source
> 100%, parse failure 0–2%). **All four solutions FAIL §8.** `llm-translation` 78.3% vs a 33.3%
> BLIND floor, cluster-bootstrap CI on the difference **[+0.243, +0.640]**. It is nonetheless the
> only transform doing any work — it roughly halves every leakage measure while `fpe` and
> `literal-tagging` sit at ceiling on all three endpoints, exactly as §5 predicted in advance.
> ~$43, 986 attacker calls + 489 judge calls, all raw request/response committed per §11.
> **Caveats that travel with the number:** the corpus is synthetic, so identifier-level
> re-identification — what the threat model actually names — is untestable by construction; and the
> forced-choice endpoint measures *recognition* (12 options, answer on the menu) not recall, where
> `llm-translation` scored 31.4% against a source control of 96.4%.
>
> #### Historical — how RSCH-1 got unblocked
> `evals/preregistration.md` is committed **unrun** and is the repo's #1 owed item. Four arms
> (BLIND / SOURCE with a ≥0.90 validity gate / HUSK / COMPOSED), forced choice over 12 permuted
> domains with no judge, a Kerckhoffs attacker given the algorithm and target catalog, a two-family
> panel reported at its **maximum**, Wilson intervals with a cluster bootstrap over *source files*,
> 3 husks per source. Commit the raw JSONL. ~$20–60.
>
> **✅ Phase A DONE — the corpus is six domains (2026-08-19).** `corpus/DOMAINS.md` is the build
> contract; `evals/verify_domains.py` is the mechanical gate and all six pass it. **72 artifacts,
> 64 inside the 40–400-line envelope** against the prereg's target of 48. The A1 selection/held-out
> split draws **3 domains each** — exactly A1's power floor, not below it. `run_eval.py --verify`
> green on all 72. New domains: `qsolog`, `meterworks`, `tremorline`, `loomshed`, `tailwatch`, each
> a Go-service + React/TS-SPA tree with its **own** entity model, endpoints and parser format.
> Structural profiles across the six show relative spread 0.17–0.53 per counter — similar in kind,
> no giveaway, so BLIND has weak-but-nonzero signal rather than a manufactured floor.
>
> **`leak_terms` in the manifest are MINE, not the generators'.** They proposed identifier-shaped
> lists (`channelCode`, `sampleRateHz`) which is right for `score_husk.py` but wrong here: prereg
> §6.2 matches these against the attacker's **free-text guess**, where a camelCase identifier can
> never appear. An identifier list is dead weight that can only make the §8 hard veto fire LESS —
> flattering. Rewritten as natural-language vocabulary; reasoning is in the manifest's
> `_provenance`.
>
> #### ✅ Phase B DONE — the harness is built, unit-tested and pre-flighted
> `evals/blind_stub.py` (code-generated stubs + a content-free assertion), `evals/run_rsch1.py`
> (two resumable stages), `evals/score_rsch1.py`, `evals/kappa_judge.py`, `evals/prompts/*`,
> `evals/verify_domains.py`. Wilson matches published values exactly; the cluster bootstrap
> demonstrably widens the CI by 47% vs flattening replicates into items, which is the §9 error it
> exists to prevent. κ verified including the unanimity edge case (undefined, not 1.0).
>
> **Four defects caught before they could corrupt a result** — all found by pre-flight or smoke
> test, all recorded in `evals/runs/20260819T180024Z-rsch1-held-out/NOTE.md`:
> 1. Prompt templates used format-style `{{...}}` but the runner substitutes with `.replace()`, so
>    every attacker would have seen literal `{{"choice": ...}}`.
> 2. **`.env` pointed `LLM_MODEL` at `Qwen/Qwen2.5-7B-Instruct`** — a model this repo's own
>    evaluation *excluded on context window*. The husk arm would have measured the wrong rewriter.
>    Now `Qwen/Qwen2.5-Coder-7B-Instruct`, the recommended husker.
> 3. `LLM_MAX_TOKENS=32768` exceeded the provider's combined input+output budget; every husk 422'd.
> 4. Attacker parse failure **29%** vs §8's 5% ceiling. Cause: on this router a reasoning model's
>    *internal* deliberation bills against `max_tokens` even when it never reaches the content
>    channel — at 3072 both attackers returned empty with `finish_reason=length`. Fixed by pinning
>    providers that support forced structured output and raising to 16000. Re-ran **52/52, 0%**.
>
> **New arm, registered in A3: `llm-translation-ungated`.** The shipped post-condition gate refuses
> passthrough husks, which silently drops the hardest files from the husk arm and flatters
> `p_husk` — the exact trap this repo already hit once. Running both arms makes the selection
> effect measurable. (In the held-out build the gate refused **nothing**, 90/90 ok, so the two arms
> double as a consistency check.)
>
> **The former blocker, kept for the record:**
> **⛔ WAS BLOCKING RSCH-1: the corpus was one domain and the design needs six.** Prereg §2 requires
> **K ≥ 6 distinct source domains** and calls that "a precondition for this pre-registration being
> meaningful at all" — against a single-domain corpus an attacker that ignores its input and always
> answers that domain scores 100%. `evals/corpus/manifest.json` holds **22 artifacts, all
> `library-circulation`**, 14 of them inside the 40–400-line envelope. `evals/domains.json` already
> *names* the six intended source domains; **five have zero artifacts**. Amendment A1's
> selection/held-out domain split cannot be drawn either. **Phase A is building those five
> domains** (`ham-radio-logbook`, `water-utility-metering`, `seismic-monitoring`,
> `textile-mill-production`, `avionics-airworthiness`) as Go-service + React/TS-SPA trees in the
> same envelope and house style as `corpus/stacks/`, each with its **own** entity model and
> architecture — vocabulary-swapped clones of one architecture would zero out the BLIND arm and
> manufacture a flattering floor.
>
> **The attacker panel is chosen and the model question is CLOSED — no frontier API key needed.**
> `evals/runs/20260819T173746Z-model-probe/PANEL.md`. The shipped model catalog was **stale by 98
> models**: it names 32, the HF router serves **130**, and every prior probe in this repo sourced
> its ids from that file. Re-probed from the endpoint: **116/130 usable**. `probe_models.py` gained
> `--from-endpoint`, which is now the preferred mode. Panel, three families, none of them the
> rewriter's (Qwen): **A1 `moonshotai/Kimi-K3`**, **A2 `deepseek-ai/DeepSeek-V4-Pro-0813`**,
> **judge `zai-org/GLM-5.2`**. Not frontier in the Claude/GPT sense — no such key exists here — so a
> null result means "not recovered by the strongest attacker reachable on this token," and the
> writeup must say exactly that.
>
> **§10's determinism escalation does NOT fire.** First measured against a domain-free stub it
> looked broken (`Kimi-K3` → `[4,4,2]`), which read as router provider-fanout (every candidate is
> served by 4–8 providers). Wrong: re-measured on a real corpus artifact with the real permuted
> menu, all three panel models return the identical correct answer 5/5, pinned or unpinned. The
> scatter was signal strength, not sampling. Run stays at **one attacker call per item**; the 20%
> determinism subsample is still owed, and should be sized off the **HUSK** arm, not SOURCE.
>
> **RSCH-2 (the verifier) is not next.** The ratified plan lists building it under *explicitly not
> doing* — a stub that checks line counts invites trust in a mechanism that isn't there — and §1
> puts it behind RSCH-1. What today's work bought it is evidence: the 18/18 identifier survival is
> both the case for it and its acceptance test.
>
> #### What landed
> - **`fpe` stopped publishing its own key.** The default was a constant baked into
>   `app/solutions/fpe.py`; a husk was decrypted from it to prove the point. Malformed `FPE_KEY` now
>   raises instead of silently falling back, production fails closed, default is a random per-process
>   key, old constant survives only behind `FPE_DEMO_KEY=1`. Also fixed a `_`→`H` alphabet collision
>   that made `/dehusk` rewrite diagnoses with the *wrong* identifier. 59 tests green.
> - **Docs corrected** where the repo's own evidence contradicted them (blanket "without ever seeing
>   the secrets", the `testCode` evaluation that never happened, NIST FF1/FF3-1 attribution for
>   `pyffx` which is neither). `LIMITATIONS.md` added as the authoritative gaps record.
> - **`evals/preregistration.md` committed unrun**, with amendments A1 (selection vs held-out split)
>   and A2 (rank on code structure, not domain vocabulary).
> - **New corpus** `corpus/stacks/` — synthetic library-circulation Go+TS app built from
>   `corpus/stacks/SPEC.md`, with `corpus/PATHOLOGY.md` cataloguing 9 deliberate defects by symbol
>   anchor. Go + vitest green. Superseded fixtures still present at that point; since removed.
> - **Eval harness** `evals/` — `run_eval.py` (drift-proof, refuses to persist a re-identification
>   map), `probe_models.py`, `run_models.py`, `run_smell_loop.py`, `husk_tree.py`, `husk_paths.py`.
>
> #### Measured, and trustworthy
> Multi-file agentic eval, Sonnet reviewer scoped per tree, citing code not comments:
>
> | tree | defects detected | agrees w/ baseline | mean conf | p50 husk |
> |---|---|---|---|---|
> | real (baseline) | 9/9 | — | 0.867 | — |
> | Qwen2.5-Coder-7B husk | 9/9 | 9/9 | 0.811 | 5.8s |
> | Llama-3.1-8B husk | 9/9 | 9/9 | 0.794 | 55.0s |
>
> **Recommended cheap husker: `Qwen2.5-Coder-7B-Instruct`** (= Ollama `qwen2.5-coder:7b`). Equal
> detection, higher confidence, 9.5× faster, and unlike Llama it does not corrupt stdlib symbols —
> Llama emitted `logger *log.Truck`. Caveats: one run, one target domain, one reviewer, and
> `llm-translation` is not byte-stable. `Qwen2.5-7B-Instruct` and `gemma-3n-E4B` were excluded on
> **context window** (422 / 400 on a 376-line file), not quality.
>
> Also fixed and worth not re-discovering: the corpus was an **answer key** — 8 comments named the
> defects beside them and reviewers cited the prose instead of the code. Rewritten; rule now in
> `PATHOLOGY.md`. And `llm-translation` picks its target by hashing each input, so a husked *tree*
> scattered across unrelated domains; `husk_tree.py --target` pins one.
>
> #### The husker prompt was rewritten, and 32B re-run against it (2026-08-19)
> `evals/runs/20260819-prompt-fix-32b/RESULT.md`. The previous run guessed that the system
> prompt's *"DO NOT: Refactor or improve the code in any way"* clause was making the stronger
> model translate the docstrings and leave the code alone. Tested: **the clause was part of the
> cause, and fixing it is not enough.**
>
> | same six files, same target | code verbatim | domain retention | leak lines | passthrough files |
> |---|---|---|---|---|
> | 32B, prompt v1 (old) | 74% | 41% | 53 | 2 of 6 |
> | 32B, prompt v3 (now) | 69% | 31% | 42 | **0 of 6** |
> | 7B, prompt v1 (old) | 49% | 21% | 37 | 1 of 6 |
> | **7B, prompt v3 (now)** | **49%** | **18%** | **8** | **0 of 6** |
>
> Outright passthroughs are gone at both scales, husk length now tracks the input instead of
> collapsing (7B v1 turned 258 lines into 92), and own-module imports are renamed. **Both models
> are now measured on the same prompt, and the 7B wins by more than before** — 18% vs 31% domain
> retention, 8 leak lines vs 42. `Qwen2.5-Coder-7B-Instruct` remains the recommended husker.
> n=1 per cell; `llm-translation` is not byte-stable.
>
> New in `evals/`: `score_husk.py` + `leak_terms.json`. The husker-scale table had been measured
> by hand in a terminal; the scorer reproduces it exactly and every number since comes from it.
>
> **The prompt was then ratcheted — four revisions, 18 runs, and the answer is a null result.**
> `evals/runs/20260819-prompt-fix-32b/RATCHET.md`. Pooled domain retention: v3 0.166, v4 0.148,
> v5 0.139, v6 0.196 — **every range overlaps every other range**, and the two metrics disagree
> about the ordering. v4 won its first three replicates cleanly by a pre-registered rule and then
> failed to reproduce on a confirmation triple of the identical prompt (0.111 → 0.185). **A single
> run cannot adjudicate a prompt revision here**; `evals/run_replicates.py` is the gate that stops
> that recurring, and every single-run comparison in this repo predating today is unadjudicated.
>
> **Where prompt effects ARE visible is individual identifiers, and the news is bad.** A document
> ID inside a URL and a list of nine real folder IDs survived **18 runs of 18**, across four
> revisions — twelve of which explicitly name those two things as content to replace. The model
> rewrites the URL's host and path and leaves the ID between them. Real SEC CIKs are the one thing
> a prompt clause moved: kept 5/6 without it, 3/12 with it. **v4 ships** on the strength of that
> column alone; on aggregate leakage it is indistinguishable from v3.
>
> **This is the strongest evidence the repo now has for RSCH-2 (the unbuilt verifier)** and for
> `docs/working-paper.md` §4.2's "prompt-only enforcement is a category error." Support, not
> proof — one corpus, one model, one target domain.
>
> **The finding the prompt work turned up:** `llm-translation` **husks numbers unreliably.** A URL's
> query-string ID and a list of nine real folder IDs survived byte-identical in every one of five
> runs that produced those lines — host and path rewritten, the ID inside untouched. Real SEC CIK
> numbers survived four runs of five, next to company names the model *did* translate; only the 7B
> on the new prompt replaced them. A numeric key is often the strongest re-identification handle in
> a file. Consequence: the husk trees from this run are **deliberately not committed** (they also
> carry the private repo's package name in every path, since paths are not husked). The already-
> committed `evals/runs/20260819-dogfood-sibling/husk/` has the same properties **plus one file
> that was never transformed at all** — ~118 lines of untransformed source from the withheld
> sibling repository, including real regulatory-filing identifiers. That tree has since been
> removed; its `RESULT.md` keeps every measurement.
>
> **SETTLED: v3 is the shipped prompt, and every clause added after it made the husker copy MORE
> source (2026-08-19).** v7 (v3 + the numbers clause alone) and v8 (v7 + the two-pass review) were
> run at n=6 to isolate which of v4's additions was working. Neither helped. Pooling all 24 runs of
> v3-plus-additions against v3's 6: copied span **0.192 vs 0.139, permutation p = 0.0034** — the
> strongest result of the session. v4's CIK advantage, its only justification, weakened from
> Fisher p ≈ 0.02 to **p = 0.34** once the extra runs were in. v4 was reverted; v3 ships.
>
> **A measurement caught grading its own subject.** v7/v8 were first measured with the
> post-condition gate live, which drops refused files from the sample — v7 looked like a decisive
> win at 0.116 (p = 0.009) and re-ran at 0.188 once the gate was neutralised. `run_replicates.py`
> now disables the gate by default and warns on unequal file counts.
>
> **The scorer was counting the wrong thing, and every leak number in the repo was understated
> (2026-08-19).** `score_husk.py` measured leakage by matching an authored word list, which is
> blind to a span of source returned verbatim containing no domain vocabulary. It now counts
> copied spans and shares one implementation with the request-path gate. Re-scored: the 32B under
> the current prompt reads **31% domain retention and 42% copied span** — the vocabulary number
> sounds like a moderate leak, the other says nearly half the caller's code came back unrewritten.
> 7B: 18% and 15%.
>
> **The post-condition check is built and wired (2026-08-19).**
> `husk-api/app/solutions/_husk_check.py` + `evals/calibrate_postcondition.py`, written up in
> `evals/runs/20260819-prompt-fix-32b/POSTCONDITION.md`. The service compares output to input,
> retries once naming what was copied, then fails closed. Calibrated on 150 file-observations;
> live acceptance 4 of 6 files husked, 2 refused; archive refusal rate 28 of 150 (19%). 65 tests
> green. **A third trigger was added after the copied-span rescore showed the first two were
> under-powered**: copying distributes, and one husk returned 66% of its source in spans of 5–14
> lines while passing a gate that only watched for a run of 20.
>
> **Building it found a second form of the defect, and corrects a claim made earlier the same
> day.** *Partial* passthrough — top of the file translated, bottom copied verbatim — occurs in
> **20 of 150 file-observations**, 14 of them under the current prompt. One case returned 26
> verbatim lines while scoring **0% domain-term retention and zero leak terms**, so every privacy
> metric in this repo called it clean. "Zero passthrough since the prompt fix" is true only of
> *whole-file* passthrough.
>
> #### ⚠️ Disputed / UNVERIFIED — do not cite without checking
> **Items 1 and 2 were settled in commit `ad4b31f` (2026-08-19)** — §2 now reads "still
> unmeasured", the dependency-leak claim is withdrawn, and the dogfood tree was diffed: the files
> had never been transformed. Kept below as the record of what was disputed and why; do not
> re-open them as work.
>
> 1. ~~**`LIMITATIONS.md` §2 currently reads "first measurement is a FAILURE."**~~ *(settled)* That is based on one
>    Opus run recovering "MARC 21 / library catalog" (conf 0.72) from a husked tree with clean
>    contents and clean paths, via parsing constants (`tag[1:4]`, `$` subfields, the `010` boundary).
>    **The owner disputes the framing**: the corpus implements a public standard, which is close to a
>    worst case and unrepresentative of proprietary code. That objection is reasonable and §2 is
>    probably over-broad as written. **Re-scope it before publishing anything.**
> 2. ~~**The dogfood result is UNVERIFIED and probably wrong.**~~ *(settled — it was a false
>    positive, exactly as the owner said: the files were passthrough, not leaks.)* Husking `husk-api/app` itself appeared
>    to leave `openai`, `pyffx`, `fastapi`, `husk`, `dehusk`, `fpe`, `pseudonym` in the output, and I
>    reported that as a structural "dependency names are unhuskable" finding. **The owner's response
>    was that it has to be a false positive, and I had not finished checking when the session ended.**
>    The specific unrun check: several files came back near-identity (`registry.py` 40→46,
>    `dehusk.py` 71→69, `main.py` 121→113), which matches the **known L3 passthrough failure mode** —
>    i.e. those files may never have been husked at all, making the "leak" an artifact of a failed
>    transform rather than a property of it. **Diff the husked output against source before treating
>    any of it as a finding.** Related: `fpe.py` collapsed 311→74 lines, a large unexplained loss.
> 3. Husked trees do not compile — imports name packages that do not exist, because each file is
>    husked in isolation. Real, but it is a limit of one-file-at-a-time husking, not a bug.
>
> *(The NEXT ACTIONS list that stood here is done or superseded — step 10 landed, steps 11–14 ran
> and verified, and the current next action is at the top of this block. The prompt track is closed:
> nothing further is expected from prompt work on this corpus.)*
>
> ---
>
> ### ▶ PREVIOUS — session handoff 2026-08-07.
>
> *(Kept as written. Its `membership/` / `testCode/` fixtures are not part of this repository
> and were replaced by `corpus/stacks/`; the evaluation rounds it cites
> are superseded — see `algorithmTests.md`. Nothing below is current state.)*
>
> **State:** `git status` clean except one untracked marketing-abstract PDF
> (pre-existing, in-flight, left untouched). Repo last committed 2026-07-29. `husk-api` is a
> working, stateless FastAPI service with 3 registered solutions (`fpe`, `literal-tagging`,
> `llm-translation`) — all 6 numbered build handoffs shipped, verified against source
> (`husk-api/app/solutions/*.py`).
>
> **▶ NEXT ACTION: RSCH-1** (README's own "Status — honest" section names this the next research
> priority) **— empirically test whether a consumer LLM can recover the source domain from a
> husk.** Currently untested; this is the paper's core privacy claim.
>
> #### What shipped
> `husk-api` product (3 solutions + `/dehusk` round-trip), test-UI frontend, target-domain
> catalog replacing the old `crumb_level` gradient for `llm-translation` (handoff 06 — verified
> live in `llm_translation.py:37-94`). Two evaluation rounds against the `membership`/`testCode`
> fixtures, incl. a 14B-model re-evaluation (`algorithmTests.md` "Re-evaluation:
> qwen2.5-coder:14b").
>
> #### What I found by reading that nobody reported
> No **verifier** (the CPG-isomorphism + anti-pattern-density + comment-speech-act checker
> `docs/working-paper.md` §4.2 describes as load-bearing — "prompt-only enforcement of the
> invariant is a category error") exists anywhere in `husk-api/app` — `grep` for
> verifier/CPG/"code property graph" in the Python source returned nothing. The paper's method
> section describes a mechanism the running service does not implement; the service is
> prompt-only today, which is exactly the category error §4.2 warns against.
>
> #### What I deliberately did NOT do, and why
> Did not stage `docs/handoffs/01-06` — unlike a typical dead session handoff, README's own
> "Where to read next" section actively indexes them as **"the build history"**; staging them
> would break a live canonical reference and lose the only per-component build record. Did not
> touch `membership/CLAUDE.md` / `testCode/CLAUDE.md` — these are per-fixture CLAUDE.md files
> inside vendored test-corpus apps, not this repo's root SSOT.

## §1 Research track (unbuilt)

*From `docs/working-paper.md` §4.2 ("A few open choices to make before v1 ships") and README's
"Status — honest" section.*

- ✅ **RSCH-1 DONE (2026-08-19)** — the core privacy claim was measured and **fails**.
  All four solutions FAIL §8; `llm-translation` 78.3% vs a 33.3% BLIND floor, CI [+0.243, +0.640].
  Run + raw outputs: `evals/runs/20260819T182111Z-rsch1-held-out/`. It measures **problem-domain**
  leakage only — the corpus is synthetic, so identifier-level re-identification is untestable by
  construction.
- ✅ **RSCH-1B DONE (2026-08-20) — the architecture IS domain-informative.** Registered as
  amendment A4, committed before any call. Canonicalised source (no identifiers, strings, comments
  or JSX text; 11 hard gates; 3 model-free probes find nothing) is still re-identified at
  **+0.234 / +0.244 corrected, p = 0.0014 / 0.0031** — about **half** the leak `llm-translation`
  carries, against a BLIND arm with **no** signal (+0.03, p≈0.40). Numerics do not explain it: the
  `-nonum` arm scores the same or higher. Run `evals/runs/20260820T021753Z-rsch1-held-out`; full
  detail and caveats in §0. Open-ended endpoint not run (spend stopped), so no §8 verdict.
- ⬜ **RSCH-2 — NOT "build the verifier as specified". Re-scope §4.2 first.** RSCH-1B changed what
  this item is. `docs/working-paper.md` §4.2 specifies a CPG-isomorphism + anti-pattern-density +
  comment-speech-act checker as the mechanism that enforces the pathology-anchor invariant. That
  verifier would enforce preservation of **exactly the thing RSCH-1B shows leaks the domain**, so
  building it first means enforcing the wrong thing well. The honest re-scope is probably
  *"structural fidelity and domain privacy trade off against each other"*, not *"the husk preserves
  pathology and hides the domain"* — and the paper needs to say which side of that trade a caller
  is buying. Still true and still the case FOR a fail-closed mechanism of some kind: `grep` confirms
  nothing in `husk-api/app` implements one, the service is prompt-only, and `llm-translation` is
  bimodal (judge 86 MATCH / 80 MISS), which is a reliability problem a fail-closed gate is good at.
  Ready-made acceptance tests: the 18/18 identifier survival from the prompt ratchet, and the 8
  residual module-name leaks that arrive as content (`<h1>qsolog</h1>`) with no import to derive
  them from.
- ⬜ **RSCH-3** CPG dialect underspecified — pick a concrete weighting scheme or adopt Joern's
  defaults (paper's own recommendation: "the latter is faster and more defensible for v1").
  `docs/working-paper.md` §4.2 tail.
- ⬜ **RSCH-4** Comment speech-act taxonomy (§4.2's third preservation condition) has no
  citation — either find one or punt to v2 with an explicit "future work" placeholder, per the
  paper's own note.
- ⬜ **RSCH-5** §4.2's "fail closed" language needs a verifier-budget concept defined in §2
  first, so the mechanism isn't introduced mid-method. `docs/working-paper.md` §4.2 tail.

## §2 Open-decisions index

(none yet — first roadmap pass, no prior decisions on record)

## Appendix — consolidation history

- `rerun-llm-test.md` (95 lines) — folded into §0 "What shipped" (its result is already fully
  recorded in `algorithmTests.md` "Re-evaluation: qwen2.5-coder:14b", zero inbound references
  anywhere in the repo) — staged, recoverable via `git show HEAD:rerun-llm-test.md`.

**Stays separate, deliberately not folded:**
- `docs/handoffs/01-06` — README's own "Where to read next" section indexes these as canonical
  build history; a live inbound reference, not an orphaned status doc. Kept in place.
- `docs/working-paper.md`, `docs/draft-1.md`, `husk-algorithms.md`, `algorithmTests.md` —
  research narrative and evaluation records, not plans.

This roadmap was installed by the `doc-consolidation` sweep (2026-08-07).
