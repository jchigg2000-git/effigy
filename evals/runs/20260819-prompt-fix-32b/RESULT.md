# Fixing the "DO NOT refactor" clause, and re-running 32B — 2026-08-19

`runs/20260819-husker-scale/RESULT.md` proposed a mechanism for why
`Qwen2.5-Coder-32B-Instruct` husked worse than the 7B: the system prompt said
**"DO NOT: Refactor or improve the code in any way"**, and a stronger
instruction-follower honours that literally — it translates the docstrings and
leaves the code alone. This run tests that by rewriting the prompt and husking
the same six files again.

**The mechanism is real but partial.** The prompt revision removed every
outright passthrough and cut domain-term retention by a quarter. It did not make
the 32B a good husker, and it did not overturn the 7B/32B ordering.

**The 7B was re-run against the same prompt (added below).** It is the best cell
measured — 18% domain retention, 8 leak lines, no passthrough, no file collapse —
and the ordering now holds on equal footing rather than across prompts.

## Method

Same six files from the private sibling repo (regulated-utility data
contracting), same pinned target (`music-streaming`), same model, same
`LLM_MAX_TOKENS=8192`, `temperature=0.2`. Three prompt revisions:

| | prompt |
|---|---|
| **v1** | as committed before this run — "DO NOT: Refactor or improve the code in any way" |
| **v2** | rewrite-not-edit framing; "do not improve" restated as a constraint on STRUCTURE only; explicit rename-everything list; length preservation; a worked before/after example |
| **v3** | v2 plus three call-outs for what v2 still missed: acronyms, data literals, and database/JSON/enum key names |

Scored by `evals/score_husk.py` (new in this commit — the husker-scale table was
measured by hand in a terminal, which this repository's own rules forbid). The
scorer reproduces that hand-measured table's `ratio` and `code verbatim` columns
exactly on all five files it recorded, so v1 here and v1 there are the same
measurement.

Leak terms come from `evals/leak_terms.json`, authored, never derived from a
husk. `iso` was removed from the list after it matched only `UTC ISO` timestamp
comments.

## Result

All figures are means over the six files. Records: `score-*.json`.

| run | prompt | code verbatim | ident retention | domain retention | **copied span** | longest span | leak lines |
|---|---|---|---|---|---|---|---|
| 7B | v1 | 49% | 51% | 21% | **20%** (171L) | 27 | 37 |
| 7B | v3 | 49% | 57% | 18% | **15%** (138L) | 16 | 8 † |
| 32B | v1 | 74% | 81% | 41% | **54%** (470L) | 100 | 53 |
| 32B | v2 | 66% | 75% | 40% | **40%** (340L) | 31 | 45 |
| 32B | v3 | 69% | 77% | 31% | **42%** (368L) | 31 | 42 |

**Re-scored 2026-08-19 with copied-span accounting** (`copied span` = share of the
source's code lines returned inside a run of 5+ consecutive byte-identical
lines). It changes how the rest of this table reads. The 32B under the current
prompt scores 31% domain retention, which sounds like a moderate vocabulary
leak; the same output returns **42% of the caller's source verbatim**. The
vocabulary metrics were never measuring that, and every leak figure recorded in
this repository before today was computed without it.

† **Corrected — every cell in this table is one run, and one run cannot carry
this weight.** Replicating the 7B/v3 cell six times (`RATCHET.md`) gave leak
lines ranging **3 to 21** and domain retention 0.122–0.223. The single run
recorded here landed near the good end. The 32B/v3 cell, at 42 leak lines, still
sits above the 7B's observed maximum, so the model ordering below survives — but
the *size* of every gap in this table is unadjudicated, and the leak-line column
in particular should not be read as a measurement.

**On equal footing, the 7B wins by a wide margin**: 18% domain retention against
31%, and 8 leak lines against 42. The previous run's ordering was measured across
two different prompts; it survives the correction, larger than it looked.

The 7B's leak-line collapse (37 → 8) is mostly one file. Under v1, `sources/source_a.py`
was a passthrough that contributed 32 leak lines of untransformed input; under v3
it husks cleanly and contributes zero. Comparing only the files that transformed
under both prompts, the honest figure is 5 → 8 leak lines, i.e. slightly worse,
against a much larger gain: nothing passed through and nothing collapsed
(v1 turned `decision/runs.py`'s 258 lines into 92; v3 returns 252).

`domain retention` is the privacy-relevant number: of the distinct domain terms
the *source* file contains, how many are still in the husk. `code verbatim` and
`ident retention` are transformation signals, not leak signals — a faithful husk
still repeats `@dataclass` and keeps `body_sha256`, so neither can be read
directly as exposure.

### What the fix bought

**The passthroughs are gone.** Under v1 the 32B returned `health.py` at ratio
1.00 / 99% code verbatim — its input, changed by one word — and `source_b.py` at 0.96
/ 87%. Under v2 and v3, no file trips the flag. `health.py` under v3 is a real
translation: `source` → `artist`, `snapshot` → `track_update`, `scraper` →
`track updater`.

**Length is preserved.** v1 husks collapsed (the 7B turned 258 lines into 92).
v2/v3 land within four lines of the input on all six files, which is what the
explicit length clause was for.

**Own-module imports are renamed now.** v1 left an own-module import
(`from pkg_a.<sub>.<mod> import <Class>`) verbatim in a file whose prose had been
fully translated; v2/v3 rename the package root to the target domain's.

**Company names in data literals came back — but so did v1's.** v2 left three
real company names verbatim inside a constant; v3 replaced them. v1 had replaced
them too, so this is the clause *recovering* behaviour v2 lost, not the clause
buying anything. Read it as run-to-run variance.

### What it did not buy

**The 32B is still the worse husker.** 31% domain retention against the 7B's
18% on the same prompt, and 42 leak lines against 8. The ordering the previous
run reported survives the fix and widens under it.

**Column names and acronyms survive as identifiers.** v3 translated the *values*
two source-domain enum values into `'STR' | 'RDS'` but kept a three-letter
domain column name in 12
places, across the schema, the SQL statements and the function signatures. The
acronym clause reached string content and missed the identifier.

**One string literal never moves.** A dotted config key naming a source-domain
document type survives in `health.py` in every 32B run, v1 through v3. It is a
source-domain identifier sitting in a call argument.

**Numeric literals are the least reliably husked content in the corpus.** No
metric here catches them — the scorer counts words. Across the five husk runs:

| numeric literal | 32B v1 | 32B v2 | 32B v3 | 7B v1 | 7B v3 |
|---|---|---|---|---|---|
| the document-index ID inside a URL | survives | survives | survives | *line dropped* | survives |
| a nine-element constant of real folder IDs | survives | survives | survives | *line dropped* | survives |
| two real regulatory-filing identifiers | survives | survives | survives | survives | **replaced** |

The URL case is the sharp one. In every run that produced the line, the model
rewrote the host and rewrote the path and left the query string `?id=<real id>`
exactly as it was. The nine folder IDs come through as a verbatim list of real
values. Both survive at 7B and at 32B, under all three prompt revisions.

The CIKs are the counter-example, and they matter because a CIK is a public
regulatory key that names the exact company — the strongest single
re-identification handle in the tree. Four runs left them verbatim beside company
names the model *did* translate: the prose gone, the primary key intact. The 7B
on v3 replaced all three with invented `U00000N` IDs. So this is not "models never
husk numbers"; it is that **whether a number gets husked is unpredictable, and
three revisions of "rename everything" did not make it dependable.** An adversary
who knows the target's identifier formats does not need any of the vocabulary
this harness measures.

*(Corrected 2026-08-19: the first version of this section, committed in `7fb5595`,
said numbers were never husked in any run. That was written before the 7B was
re-run, and the 7B's v3 output refutes it.)*

**v3 is not uniformly better than v2.** Code verbatim went *up* (66% → 69%) and
leak lines fell (45 → 42). `format_a.py` got worse on leaks in both revisions (7 →
11 → 14) while `source_a.py` and `format_b.py` improved. One run per revision, and
`llm-translation` is not byte-stable, so the v2↔v3 difference is inside the
noise this harness cannot yet measure.

## Caveats that bound all of the above

- **n=1 per cell.** Four husk runs, no repeats. `llm-translation` is not
  byte-stable, so a difference of a few points between v2 and v3 is not
  evidence of anything.
- **One corpus, one target domain, one model family.** Six Python files from one
  private repo, all husked into `music-streaming`.
- **The 7B was re-run on v3, not on v2.** Both 7B cells are single runs, like
  every other cell here.
- **The leak-term list is authored and incomplete.** It counts terms someone
  thought of. A term not on the list leaks silently.
- **`passthrough` is a calibrated flag, not a measurement.** Thresholds
  (`ident_retention >= 0.92 and ratio >= 0.95`) were set by eye against these 24
  file-observations. The band just below is genuinely ambiguous; read the
  per-file numbers, not the flag.

## What is committed here — and what is NOT

The score records (`score-*.json`) and this file. **The husk trees are not
committed**, which breaks this harness's own "raw outputs are committed on
purpose" rule, deliberately and for the reason that rule exists to expose:

*the husks are not private enough to publish.* They carry two real SEC CIK
numbers, nine real folder IDs, and — because file paths are not husked at all
(LIMITATIONS.md §3) — the private repo's own package name and directory layout
in every path. Committing them into a repository being prepared to go public,
while its owner still works in the domain the source code serves, would publish
exactly what this project claims to prevent.

That is a finding, not an inconvenience. A husk that cannot be published has not
done its job.

The trees are at `/tmp/sibling-husk32{,-v2,-v3}` and are ephemeral. Regenerate with
`evals/husk_tree.py --model Qwen/Qwen2.5-Coder-32B-Instruct --target
music-streaming --src /tmp/sibling-src`; `llm-translation` is not byte-stable, so a
regenerated tree will differ.

**Resolved 2026-08-19:** `runs/20260819-dogfood-sibling/husk/` was committed and
had the same properties — plus one file (`sources/source_a.py`) that was never
transformed at all, i.e. ~118 lines of the private source in this repository,
with its CIKs and company names. Reviewing it showed the problem was not confined
to that file: every husk in the tree carried verbatim source (124, 85, 67 and 47
lines in the others). The tree was deleted; its `RESULT.md` keeps every
measurement.

Source is not included, here or anywhere in this repository.

## Still open

The defect that made all of this hard to see is untouched: **`llm-translation`
has no post-condition check.** It verifies that a response is non-empty and
untruncated, and returns whatever came back. A prompt revision cannot close
that — the service should compare its output to its input and refuse to return a
husk that is substantially the source. `score_husk.py` now contains a working
implementation of that comparison; the service does not call it.
See `LIMITATIONS.md` §2.
