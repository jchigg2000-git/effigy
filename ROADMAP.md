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

> **Closed work is not in this file.** An item is deleted at the edit that closes it — there is
> no ✅ status. What shipped is recorded by the closing commit. To resurrect or cite a deleted
> item: `git log -S'<ID>' -- ROADMAP.md`, then `git show <sha>:ROADMAP.md`.

**Legend:** 🔶 shipped but UNVERIFIED · ⏳ in progress · ⬜ not started · 🔬 verification owed ·
⛔ **BLOCKS** — the only marker that gates anything

**Backlog items are not blockers.** No item under a `BACKLOG` / `PARKED` status may be cited as
gating, blocking, or holding up any other work unless it carries a `⛔ BLOCKS:` line with the
owner's verbatim instruction. Absent that line, treat it as non-blocking. An agent that reports
a parked item as a blocker is misreading this file.

**Contents:** §0 Do next · §1 Research track (unbuilt) · §2 Open-decisions index · Appendix

## §0 Do next

> ### ▶ RESUME HERE — 2026-09-26: **Audit. RSCH-1's "gated" `llm-translation` arm ran ungated.**
> A four-lane audit (solutions, service, statistics, harness) verified 37 findings, each lane
> re-checked by a second reviewer. 33 shipped, 6 of them in part; 4 are owner decisions. **No cited
> verdict changes** (E1, E7 and E10 need paid re-runs to confirm). Published figures keep their values, with pointers to `LIMITATIONS.md` errata E1–E17;
> false statements are struck through with a dated correction. `DECISIONS.md` 2026-09-26.
>
> #### What it found — headline first
> - **E1.** A thread race in `run_rsch1.py` left the gate-off overrides set, so **89/90 "gated"
>   husks in `20260819T182111Z` were built with the gate's thresholds switched off**, so nothing
>   could be refused or retried. 39/90 would have been
>   refused (45/90 with today's module-name check); 2 are the source minus a newline. Every RSCH-1
>   `llm-translation` figure (65/83, [+0.243, +0.640], +0.439 / +0.479) describes an ungated
>   rewriter. FAIL stands: on would-pass husks, Kimi 39/48 and DeepSeek 36/51 against blind 10/30.
> - **E10.** RSCH-1B: 8/60 canonicalised artifacts kept an authored comment; 2 carried ham-radio
>   vocabulary, and all 4 answers on them were correct. Without those records: +0.220 / +0.224 and
>   +0.245 / +0.252, all p < 0.01. The conclusion holds.
> - **E7.** Committed `fpe` Go husks never parsed (18/18 fail `gofmt -e`); `literal-tagging`
>   swallowed code after a comment apostrophe (8/30); `fpe` left `${...}` names in plain text.
> - **E13.** The κ worksheet showed the wrong attacker's guess on 57/98 rows; `kappa_judge.py` now
>   keys on (item, attacker). Smaller: the rest of E1–E17.
>
> #### What was fixed
> - Harness: ungated arm husked in a child process; every husk's gate state checked fail-closed.
> - Resume re-asks transport failures and owed §6.1 retries; `config.json` is written once with
>   later invocations appended; gate refusals are kept; superseded records are moved aside.
> - Token usage recorded on attacker, judge, probe, smell-loop and path-husking calls, and per
>   rewriter attempt (the rewriter's final-attempt usage was already in artifact metas), and since
>   2026-10-01 on `run_models.py` cases and `husk_tree.py` files.
> - Scorer: arms missing from `config.json` are scored, not dropped; coverage against expected
>   jobs; a no-source gate reads NOT EVALUATED; the hard veto
>   reaches §3; A1 floor; gate-state banner; §5 skips transport failures; p = (b+1)/(m+1).
> - Canonicaliser blanks every comment; G2 adds a text-level closed-world scan; G2/G8/G11 false
>   positives fixed (`--all` 64/64); G4 searches preserved import paths.
> - `fpe`: husks parse; `${...}` enciphered; linear tokenizer; non-ASCII identifiers enciphered.
> - `literal-tagging`: no cross-line quotes; linear; runes kept; MIME → MSG; nested templates only
>   with `options.language`.
> - Service: 429 → 503, 408/5xx → 502; fenced-husk extraction; reorder trigger; Go detected from
>   `package`; host-prefixed module names; fast gate on large inputs; no import-time writes;
>   `example` opt-in. Tests: `husk-api` 69 → 93; new `evals/tests`, 20.
>
> #### ⬜ OWNER DECISIONS queued — none blocks another item
> 1. **Re-run the gated `llm-translation` arm (E1).** The only route to a gated RSCH-1 figure and to
>    A3's comparison. Calls: 90 husks (+ up to 90 retries), 360 attacker, up to 180 judge. Cost:
>    the rewriter share is recorded and small (215k prompt + 108k completion tokens on the 7B for
>    the 90 husks); attacker and judge usage was not recorded, so at RSCH-1's average (~$43 over
>    1,475 calls) the re-run is **roughly $15**, an estimate rather than a quote. RSCH-1B's
>    equivalent (E10) is 4 forced-choice calls minimum, 16 for all 8 changed artifacts, under a new
>    run id.
> 2. **Re-attack the rebuilt `fpe`, `literal-tagging` and `composed` arms (E7).** Rebuilding needs
>    no model calls (30 + 30 + 15 artifacts change); the re-attack is 300 attacker calls + up to 150
>    judge, roughly $13 at the same rate. All three sit at ceiling, so no verdict is expected to
>    move: worth it only if those arms' committed husks are to be cited as the shipped behaviour.
> 3. **Amendment A5, the STAT-2 denominator (E4).** DeepSeek `llm-translation` +0.439 → +0.419,
>    blind p 0.41 → 0.33, 83/125 → 83/129; no verdict. Cost: an amendment and a re-score, no calls.
> 4. **Gate calibration for copied comments (SVC-2, E16).** About 6 of 93 recorded passing husks
>    would be refused. Cost: small, but it can only be calibrated on the Go/TS runs.
> 5. **`literal-tagging` import-graph design (SOL-8).** Keyed import segments, opt-in. Cost: medium;
>    relative imports need the file path, which the API does not carry.
> 6. **Cluster-aware intervals (STAT-8).** Replicated-cell Wilson brackets are ~30% too narrow
>    (Kimi [0.68, 0.86] vs [0.65, 0.91]); §9 registers Wilson, so a descriptive column or a note.
> 7. **JSX text in `fpe` (SOL-6):** pass it through, or encipher it under a separate key.
> - Smaller: prereg notes where A4/A4.1 quote E4/E6 figures; regenerating
>   `structure_probes.json`; resuming 182111Z (15 calls);
>   the Go half of HAR-7 (a shadowed import survives `canon_go.go`, which needs its gitignored
>   binary rebuilt; the TS/G4 half shipped).
>
> #### κ worksheet — regenerated, still awaiting hand labels
> `evals/runs/20260819T182111Z-rsch1-held-out/kappa_worksheet.jsonl`, same 98 rows. Label
> `human_label`, then `kappa_judge.py --score`; `--sample` now refuses to overwrite labels.
>
> #### Next research action — unchanged
> **Re-scope `docs/working-paper.md` §4.2 before RSCH-2.** E10 moves RSCH-1B's figures, not its answer.

## §1 Research track (unbuilt)

*From `docs/working-paper.md` §4.2 ("A few open choices to make before v1 ships") and README's
"Status — honest" section.*

- ⬜ **RSCH-2 — NOT "build the verifier as specified". Re-scope §4.2 first.** RSCH-1B changed what
  this item is. `docs/working-paper.md` §4.2 specifies a CPG-isomorphism + anti-pattern-density +
  comment-speech-act checker as the mechanism that enforces the pathology-anchor invariant. That
  verifier would enforce preservation of **exactly the thing RSCH-1B shows leaks the domain**, so
  building it first means enforcing the wrong thing well. The honest re-scope is probably
  *"structural fidelity and domain privacy trade off against each other"*, not *"the husk preserves
  pathology and hides the domain"* — and the paper needs to say which side of that trade a caller
  is buying. Still true and still the case FOR a fail-closed mechanism of some kind: `grep` confirms
  nothing in `husk-api/app` implements one, the service is prompt-only, and `llm-translation` is
  bimodal (judge 86 MATCH / 80 MISS *(E1)*), which is a reliability problem a fail-closed gate is good at.
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
- 🔬 **RSCH-1 determinism subsample owed** (prereg §10: a 20% subsample with 3 calls each; if
  determinism does not hold, escalate to 3 attacker trials everywhere). The probe did not fire the
  escalation, so the run stays at one attacker call per item, but the subsample is still owed on
  the real corpus, sized off the **HUSK** arm, not SOURCE.
  `evals/runs/20260819T173746Z-model-probe/PANEL.md`.

## §2 Open-decisions index

**Open, owner (2026-09-26):** the six items in §0's 2026-09-26 block — re-run the gated
`llm-translation` arm; amendment A5 for the permutation denominator; gate calibration for copied
comments; a `literal-tagging` import-graph design; cluster-aware intervals; JSX text in `fpe`. None
blocks another item.

Ratified decisions live in `DECISIONS.md` (append-only; cited by date + title):

- 2026-04-30 (approx.) — Retire `crumb_level` as `llm-translation`'s target-selection knob
- 2026-08-07 — Install ROADMAP.md/DECISIONS.md triad; keep build-history handoffs in place
- 2026-08-19 — `fpe` stops shipping its own decryption key; alphabet gains `_`
- 2026-08-19 — Drop the vendored fixtures; the results file dies with its corpus
- 2026-08-19 — Build the corpus to six domains rather than weaken RSCH-1's design
- 2026-08-30 — Drop `docs/Effigy_Technical_Abstract.pdf` rather than annotate it
- 2026-08-31 — Regenerate the one drifted manifest entry, having established it is bookkeeping
- 2026-09-01 — Publication addendum: references that do not resolve in the published tree
- 2026-09-26 — Audit fixes ship; affected published figures get errata, not rewrites

## Appendix — consolidation history

- `rerun-llm-test.md` (95 lines) — folded into §0 and removed by the 2026-08-07 consolidation
  sweep (DECISIONS 2026-08-07). The `algorithmTests.md` "Re-evaluation: qwen2.5-coder:14b" section
  that recorded its result was deleted with the vendored fixtures (DECISIONS 2026-08-19); the 14B
  result is not carried forward — see the banner at the top of `algorithmTests.md`. Not
  recoverable from this repository: history was reset to a single root commit at publication.
- 2026-10-12 trim (`cleanup-roadmap --roadmap-only`): deleted the two older §0 resume blocks
  (▶ PREVIOUS 2026-08-20, with its four DONE sections, settled disputes and the resolved
  ⛔ WAS BLOCKING record; ▶ PREVIOUS 2026-08-07) and the two DONE items in §1 (RSCH-1, RSCH-1B);
  moved one owed loose end (the §10 determinism subsample) to §1. Full pre-trim file:
  `git show 2cce136:ROADMAP.md`.

**Stays separate, deliberately not folded:**
- `docs/handoffs/01-06` — README's own "Where to read next" section indexes these as canonical
  build history; a live inbound reference, not an orphaned status doc. Kept in place.
- `docs/working-paper.md`, `docs/draft-1.md`, `husk-algorithms.md`, `algorithmTests.md` —
  research narrative and evaluation records, not plans.

This roadmap was installed by the `doc-consolidation` sweep (2026-08-07).
