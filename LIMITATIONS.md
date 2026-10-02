# Limitations

**This file is authoritative.** The README's "Status" section is a summary of it and must stay a
strict subset — if the two ever disagree, this file is correct and the README is stale. The same
applies to `docs/working-paper.md` and `docs/draft-1.md`.

Last reviewed: 2026-09-26 — the audit errata below, and §5, §6, §10 and §11 updated. Previously
2026-08-30. (§2.0.2 records RSCH-1B, run 2026-08-20.)

---

## 1. What this is, and what it is not

effigy is a **research artifact and feasibility study**. It is not a security product, and nothing
in this repository is a security guarantee. The running service is a demonstration of a technique,
not a hardened implementation of it. Do not put real proprietary source through it and conclude
anything about your exposure.

## Errata — 2026-09-26 audit

A four-lane audit (the husking solutions, the service, the statistics, the eval harness) produced
37 findings, all reproduced; each lane's findings were re-checked by an adversarial second
reviewer, who added 5 of the 37. The fixes are in the code
(§10, §11, `DECISIONS.md` 2026-09-26); this section is what they mean for figures already
published. **The committed run artifacts stay as they were run** (the one exception is E13), and
every published figure keeps its value, with a pointer such as *(E1)* beside it here, in
`README.md` and in `ROADMAP.md`. A statement that was simply false is struck through with a dated
correction. Four findings are deferred to the owner (`ROADMAP.md` §0).

**No verdict changes on the recorded data.** RSCH-1's four FAILs and RSCH-1B's "above baseline"
hold under every entry below; E1, E7 and E10 need paid re-runs to confirm, and none is expected to
flip a verdict. What does not survive is the claim that RSCH-1's `llm-translation` row measured a gated
husker (E1).

**E1 — RSCH-1's "gated" `llm-translation` arm was built with the gate off.** `run_rsch1.py`
switched the post-condition gate off for the ungated arm by editing process-wide environment
variables from six worker threads; overlapping jobs saved and restored each other's overrides and
left them set. In `20260819T182111Z`, **89 of 90 "gated" husks record the gate-off thresholds**, so
the gate passed everything and no retry could trigger (the overrides also set
`HUSK_CHECK_RETRIES=0`, which the metas do not record); only `meterworks` `meter.go` r1 carries the defaults,
and the ungated arm has the mirror image. At the thresholds shipped at the time, 39/90 would have
been refused on first attempt (45/90 with the module-name check shipped since). `tremorline`
`main.go` r0 and r1 are the source minus its trailing newline, and all 4 forced-choice answers on
them were scored correct. *Published:* 65/83 (78.3%) and 62/90 (68.9%) forced choice; 86/173
(49.7%) judge MATCH, 86 MATCH / 80 MISS; 43/86 (50.0%) leak-term hits; CI [+0.243, +0.640];
corrected +0.439 / +0.479, and the +0.44 / +0.48 anchor RSCH-1B is compared against; §5's
0.269 / 0.276; §2.0.1's 22 of 90, 44/44 and 83/125. All of them describe an effectively ungated
rewriter. *Corrected value:* needs a re-run. A gated build retries each refusal once and does not
attack what is still refused, so the gated figure cannot be derived from these records.
Descriptively, on the husks the gate would pass the attackers scored Kimi 39/48 (0.81) and
DeepSeek 36/51 (0.71); on those it would refuse, 26/35 and 26/39. *Verdict:* FAIL is not at risk —
the would-pass subset scores higher than the whole arm for both attackers, against blind 10/30.
Void for this run: the A3 gated-vs-ungated comparison, and `ROADMAP.md`'s "the gate refused
nothing, 90/90 ok" (struck).

**E2 — "986 of 998 attacker calls" includes an arm the run's config does not declare.**
`config.json` was rewritten on every invocation, so each committed config describes its run's last
resume. The post-spending-cap resume passed `--arms` without `llm-translation-ungated`, so
`20260819T182111Z`'s config (started_at 21:00Z for an 18:21Z run id) omits an arm that was built
for all 30 files and attacked on `meterworks` only: 38 records, in no §2 or verdict table (they
appear only in §2b and `permutation.md`, as E5's single-domain cell), but counted in the coverage
banner and in the validity gate's parse-failure column (0/242, 5/249). The scorer now takes its arms
from `config.json`, every recorded resume and `raw/` together, so a re-score scores them in every
section, where A1 marks them INCONCLUSIVE (one domain). *Published:*
986 of 998. *Corrected:* right as an on-disk count; against the six declared arms it is **948 of
960**, all 12 gaps transport failures. The same overwrite means neither RSCH-1's nor RSCH-1B's
original commit is recoverable from its config (RSCH-1B's shows the resume's `8d03ae3` and
`max_tokens` 32000; its `summary.md` header says `652976ec…`, dirty). *Verdict:* none changes.

**E3 — A resume never re-asked a transport failure, and a transport error could spend the §6.1
retry.** `20260819T182111Z/NOTE.md` says a resume pays only for the missing calls. In fact a record
whose every attempt failed in transport was treated as final, and three records had their single
parse retry consumed by a transport error; one of them (DeepSeek, `llm-translation`, forced choice:
unparseable, then the 403 spending cap) is scored incorrect on one response. *Published:* Kimi
65/83, DeepSeek 62/90, parse failure 5/249. *Corrected:* a resume with the fixed runner would
re-ask exactly 15 records (12 missing, 3 owed retries). Kimi's forced choice could land anywhere
from 65/90 to 72/90 (72.2%–80.0%); DeepSeek's moves by at most 1. Not re-run. *Verdict:* none
changes.

**E4 — The A4.1 permutation drops answered-but-unparseable replies that §2 scores wrong. Owner
decision pending.** A4.1 registers "records with no parsed choice are dropped as missing"; §6.1 and
§2 score an answered-but-unparseable reply incorrect. So one `summary.md` gives DeepSeek
`llm-translation` 62/90 (0.689) in §2 and 0.721 on n = 86 in §2b, and DeepSeek blind 10/30 in §2
and 0.345 on n = 29 in §2b. The 5 records are DeepSeek replies with empty text and
`finish_reason=length`. *Published:* blind 0.345 / 0.320 / +0.025 / p 0.41; `llm-translation`
0.721 / 0.282 / +0.439 (the +0.44 anchor); "26 of 29"; "83/125 (66.4%)". *Under the §6.1
denominator:* 0.333 / 0.300 / +0.033 / p 0.33; 0.689 / 0.269 / +0.419 (+0.42); 26 of 30; 83/129
(64.3%). The published values follow A4.1 as registered, so they stand until a dated amendment
(A5) says otherwise; a re-scored §2b now states when its n excludes such records. Kimi and RSCH-1B
are unaffected. *Verdict:* none changes; `structure-only` is still about half of `llm-translation`
(+0.234 against +0.419).

**E5 — Permutation p-values had no +1 correction.** p was b/m, which can print 0.0000; a Monte
Carlo permutation p is (b+1)/(m+1). *Published → corrected:* 0.0000 → 0.0001 in every RSCH-1
source and solution cell; RSCH-1B 0.0014 / 0.0031 → 0.0015 / 0.0032 and 0.0008 / 0.0023 →
0.0009 / 0.0024; blind 0.41 / 0.39 and "p≈0.002" unchanged at their rounding. A cell whose files all
carry one domain (`llm-translation-ungated`, 9/9 on `meterworks`) printed "+0.000, p = 1.0000",
which reads as "no signal"; it is now "not computable". `evals/structure_probes.py` now uses
(b+1)/(m+1) too; the committed `structure_probes.json` (not regenerated) keeps its counters p 0.988,
which would read 0.98801. *Verdict:* none changes.

**E6 — §5's mechanism table counted transport failures as wrong answers.** The 7 Kimi
`llm-translation` records that never reached the model sat in the "wrong" bucket. *Published:*
0.269 when right, **0.276** when wrong (127 / 53). *Corrected:* 0.269 / **0.275** (127 / 46). The
table also holds E1's two passthrough husks. The committed `summary.md` still reads 0.276, as does
the reason given for amendment A4 in `evals/preregistration.md`, which is append-only. *Verdict:*
none; copying still does not explain the leak.

**E7 — The committed `fpe`, `literal-tagging` and `composed` husks carry tokenizer defects that are
now fixed (§10).** `literal-tagging` let a single-quoted literal cross line breaks, so an apostrophe
in a comment swallowed code into one placeholder and printed later literals in plain text (8/30
committed husks). `fpe` emitted digit-leading pseudonyms and enciphered Go keywords and number
tails, so **18/18 committed Go `fpe` husks fail `gofmt -e`**, and it left names inside `${...}` in
plain text beside their pseudonyms (27 names in 8 of 12 TS/TSX husks). `literal-tagging` also
classed MIME types as PATH and wrote illegal Go runes. The code as run regenerates every committed
artifact byte for byte; today's code changes 30/30 `fpe`, 30/30 `composed` and 15/30
`literal-tagging` husks in `20260819T182111Z`, and 2/2, 2/2 and 1/2 in `20260819T180024Z`.
*Published:* `fpe` 30/30, 60/60, 93.3%; `literal-tagging` 30/30, 59/60, 96.7%; `composed` 30/30,
51/57; +0.668 for those arms in §2.0. They stand as the record of what the attackers saw.
*Corrected:* needs a paid rebuild and re-attack. *Verdict:* not expected to move — the three arms
sit at ceiling, and each fixed husk still carries the half its solution preserves (§3) — but
unmeasured.

**E8 — The module-name channel was closed only for bare module names.** The gate's fourth trigger
derives names from import paths, and skipped any import whose first segment contains a dot, so for
an ordinary Go module (`github.com/org/repo/...`) it never fired. It fired here because the corpus
uses bare module names (`module meterworks`). With the recorded Go husks' imports rewritten to
`github.com/acme/<name>/...`, 24 of 27 module-name refusals escape it and 8 would be served as `ok`
with the repo name intact. It now also takes the org and repo segments of a host-prefixed path when
an import has an `internal/` segment. Still not covered: a host-prefixed module with no `internal/`
import, and a name that arrives as content. *Published:* "now closed" (§2.0.1 and `ROADMAP.md`,
struck). The 14/14 and 0/76 calibration figures are unaffected. *Verdict:* 0 of 183 recorded gate
verdicts change.

**E9 — `ROADMAP.md` quoted the partial run's recall figures as the finished run's.** Found in this
documentation pass, not by the audit. Its RSCH-1 entry says `llm-translation` "scored 31.4% against
a source control of 96.4%" on free text; those are `NOTE.md`'s partial-state figures (27/86,
27/28). The finished run's are 86/173 (49.7%) against 60/60 (100%), `summary.md` §4.2 — and E1
applies to the first. Struck in place. *Verdict:* none.

**E10 — RSCH-1B: 8 of 60 canonicalised artifacts kept an authored comment, and the gate could not
see it.** The TS canonicaliser collected comments only where an AST node starts, so a comment
whose next token is `)`, `]` or `}`, including a JSX `{/* */}`, was copied through; gate G2
re-lexed the output with the same classifier. In `20260820T021753Z`, `client.ts` in all three
domains × both arms kept one sentence that is identical across domains, and `qsolog`
`ContactDetail.tsx` × both arms kept a comment in ham-radio vocabulary (award progress, station,
"band/mode pair"). **All 4 forced-choice answers on those two items were correct**, at confidence
0.90–0.95; the attackers give no rationale, so causation cannot be shown. *Published:* +0.234 /
+0.244 (p 0.0014 / 0.0031); +0.257 / +0.265 (p 0.0008 / 0.0023); the "+0.24, p≈0.002" headline;
"every … comment … removed" (struck in §2.0.2). *Sensitivity, model-free:* excluding the 4
`ContactDetail` records, +0.220 / +0.224 (p 0.0039 / 0.0051) and +0.245 / +0.252 (p 0.0010 /
0.0047), p by E5's (b+1)/(m+1); excluding all 12 records on the 8 changed artifacts, +0.245 / +0.214 and +0.232 / +0.237,
every p < 0.01. A clean figure needs the re-canonicalised artifacts attacked again under a new run
id, which is paid. *Verdict:* the conclusion holds — shape alone carries roughly half the leak a
husk carries.

**E11 — RSCH-1B's validity gate was not evaluated, rather than failed, and its open-ended endpoint
was started.** The scorer printed "GATE FAILED … the task or the labels are broken" for a run with
no source arm (p_source 0/0); it now prints "NOT EVALUATED — no source arm in this run" and, as
before, issues no verdict. The open-ended endpoint was started and then stopped: **13 of 120
calls** landed, all with 0 leak-term hits, after the committed `summary.md` was generated, so that
file lacks them. Against its full expected job set the run has 124 of 240 answers (forced choice
111/120). *Published:* "recorded FAILED"; "the open-ended endpoint was not run" (struck).
*Verdict:* none; both arms remain NOT COMPUTABLE on §8.

**E12 — `marc21.go` failed canonicaliser gate G8 because the gate was wrong.** `evals/README.md`
said the canonicaliser "loses one level of nesting" on `corpus/stacks/…/marc21.go`. It does not: the
source's raw depth of 7 comes from the string `"{dollar}"`, and `counters.py` counts braces inside
literals. G8 now compares depth on literal-masked code, and `canonicalize.py --all` passes 64/64 in
both arms. The committed `evals/structure_probes.json`, not regenerated, still lists the failure and
ran its tokens probe on 63 files. *Published:* "canonicalised tokens 0.000 against 0.154". *On
regeneration:* 0.000 against 0.156 (n = 64); the counters probe is unchanged. Also struck, in
`evals/README.md` and §9.1: that `corpus/stacks` is "not an RSCH-1 domain". It is
`library-circulation`, one of the six, in the selection split; no held-out run used it.
*Verdict:* none.

**E13 — The κ worksheet showed the wrong attacker's guess on 57 of 98 rows.** `kappa_judge.py`
matched records by file-name prefix, so every Kimi row showed DeepSeek's guess, and `--score`
compared 96 of the 98 rows against Kimi's judge label; a perfect rater would have scored κ ≈
0.83–0.87 instead of 1.0. No κ had been computed.
`evals/runs/20260819T182111Z-rsch1-held-out/kappa_worksheet.jsonl` was **regenerated in place**,
the one committed run file this pass changed, because all 98 `human_label` fields were still empty:
same seed, same 98 rows in the same order, and each row now shows its own attacker's guess.
*Verdict:* none; the judge table stays descriptive until the worksheet is labelled.

**E14 — The CIK "Fisher p ≈ 0.02" does not reproduce.** `ROADMAP.md` and
`evals/runs/20260819-prompt-fix-32b/RATCHET.md` give it for real SEC CIKs kept 5/6 without the
numbers clause against 3/12 with it. Exact: **two-sided p = 0.043**, one-sided 0.032. The
5/6-against-9/18 figure, p = 0.34, reproduces. *Verdict:* none — v4 was reverted on the 0.34 and on
copied span (p = 0.0034).

**E15 — §11's read-only-filesystem claim was only conditionally true.** The committed tree imported
on a read-only filesystem. Import failed only when the targets JSON was stale or `static/` was
missing, or on a non-editable install, which did not package `static/`. Fixed, and struck in §11.

**E16 — The passthrough gate does not refuse every husk that is substantially its source.** It
measures code lines only: a comment or docstring copied word for word is invisible to it, and an
input under 12 code lines is never judged, so a docs-heavy file or a single long line can come back
byte-identical with a 200. 6 of the 93 recorded RSCH-1 husks that pass it today carry a verbatim
prose run of 5+ lines. Qualified in §2 and §5; the fix is deferred to the owner, because it changes
what the gate refuses and can only be calibrated on the Go/TS runs. *Verdict:* none; no recorded
number changes without a re-run.

**E17 — The smoke run `20260819T180024Z` re-scores as A1-INCONCLUSIVE.** Its committed
`summary.md` issues **FAIL** on all four husk arms and a hard-veto banner, from data covering two
domains. The scorer now enforces amendment A1's floor (fewer than 3 domains → INCONCLUSIVE), so a
re-score reads "INCONCLUSIVE — A1", the 8 veto cells read "not issued (A1 …)" and every §2b cell
"not computable". Its committed summary also predates the current scorer and did not reproduce
byte-for-byte before this change. *Verdict:* none that was cited: the run's `NOTE.md` marks it NOT
A RESULT, and no document quotes its numbers.

### Audit finding index

Code comments, tests, `DECISIONS.md` and `ROADMAP.md` cite the audit's findings by id. Each row
says what the finding was and where it is now recorded. *Fixed* means shipped with a regression
test; *part* means the rest is described where the row points; *owner* means deliberately not
implemented (`ROADMAP.md` §0).

| id | finding | status | where |
|---|---|---|---|
| SOL-1 | quoted literals crossed newlines: a comment apostrophe swallowed code (`literal-tagging`) or left identifiers plain (`fpe`) | fixed | E7 |
| SOL-2 | `fpe` Go husks never parsed (digit-leading pseudonyms, unspared keywords, enciphered number tails) | fixed | E7, §6 |
| SOL-3 | `fpe` left names inside `${...}` in plain text beside their pseudonyms | fixed | E7 |
| SOL-4 | nested template literals split into invalid JS | fixed, opt-in | §10 |
| SOL-5 | `fpe` comment rules are language-blind; non-ASCII identifiers passed through | fixed, opt-in *(2026-10-01)* | §10 |
| SOL-6 | `fpe` enciphers JSX text with the code's key | owner | §10 |
| SOL-7 | MIME types (and `and/or`, dates) classified as `PATH` | fixed | §10 |
| SOL-8 | import specifiers become per-call placeholders; the import graph is unrecoverable | owner | §10 |
| SOLV-1 | quadratic tokenizers: one 200 KB request took minutes | fixed | §10 |
| SOLV-2 | `literal-tagging` turned Go/C rune literals into multi-character runes | fixed | E7 |
| SVC-1 | the RSCH-1 gated arm was built with the gate off (service half: retry budget recorded) | fixed | E1 |
| SVC-2 | the gate cannot see copied comments and never judges inputs under 12 code lines | owner | E16, §5 |
| SVC-3 | Go files without `func ` early on were read as Python, switching the module-name check off | fixed | E8, §5 |
| SVC-4 | model commentary around a fenced husk was served as the husk | fixed | §5 |
| SVC-5 | a husk that reordered the source's lines passed the gate | fixed | §5 |
| SVC-6 | provider 429/5xx surfaced as the service's own 500 | fixed | §11 |
| SVC-7 | importing the app wrote to disk; `static/` was not packaged | fixed | E15, §11 |
| SVC-8 | the `example` stub was registered on the public API | fixed | §11 |
| SVC-M1 | the module-name check missed host-prefixed Go module paths | fixed | E8 |
| SVC-M2 | the gate cost minutes of CPU on inputs the contract allows | fixed | §11 |
| STAT-1 | `kappa_judge.py` paired rows with the wrong attacker | fixed | E13 |
| STAT-2 | A4.1's permutation drops answered-but-unparseable replies (same as HAR-8) | part | E4 |
| STAT-3 | §5's mechanism table counted transport failures as wrong answers | fixed | E6 |
| STAT-4 | permutation p had no +1 correction; single-domain cells read as "no signal" | fixed | E5 |
| STAT-5 | the scorer could not see records never written, and misreported a run with no source arm | fixed | E11 |
| STAT-6 | a resume overwrote `config.json` (same as HAR-4) | fixed | E2 |
| STAT-7 | the §8 hard veto never reached the verdict column | fixed | E17 |
| STAT-8 | Wilson intervals on replicated cells ignore clustering | owner | `ROADMAP.md` §0 |
| STATS-M1 | the scorer did not enforce A1's three-domain floor | fixed | E17 |
| HAR-1 | the thread race behind SVC-1 (harness half) | fixed | E1 |
| HAR-2 | the TS canonicaliser kept comments before `)`, `]`, `}`, and the gate shared the blind spot | fixed | E10 |
| HAR-3 | a resume never re-asked transport failures, which could spend the §6.1 retry | fixed | E3 |
| HAR-4 | a resume overwrote `config.json` and artifact error records | fixed | E2 |
| HAR-5 | token usage was not recorded | fixed | `evals/README.md` § Token usage |
| HAR-6 | canonicaliser gate false positives (G2 regex flags, G8 braces in literals) | fixed | E12 |
| HAR-7 | the canonicaliser keeps a shadowed or domain-named import by name | part (TS, G4) | `ROADMAP.md` §0 |
| HAR-8 | the same defect as STAT-2 | part | E4 |

## 2. Status of the central privacy claim: **measured once, completely, and it fails**

The pre-registered experiment (`evals/preregistration.md`, RSCH-1) was run on 2026-08-19 against
the six-domain corpus. An account spending cap halted it mid-flight; it was **resumed under the same
run id and completed** — **986 of 998 attacker calls** *(E2)*, all **three** held-out domains, 12 calls
never reaching the model and excluded as missing rather than scored wrong.
`evals/runs/20260819T182111Z-rsch1-held-out/summary.md` is authoritative. (That directory's
`NOTE.md` describes the *partial* state and is marked superseded; an earlier revision of this
section quoted it and reported two domains and 502 calls. Corrected 2026-08-19.)

Panel maximum across the two attackers, exact counts beside every rate:

| arm | menu (recognition) | free text, judge MATCH | leak-term veto |
|---|---|---|---|
| blind (floor) | 10/30 (33.3%) | 0/59 (0.0%) | — |
| **source (control)** | 30/30 (100%) | 60/60 (100%) | — |
| `fpe` *(E7)* | 30/30 (100%) | 60/60 (100%) | 🚫 93.3% |
| `literal-tagging` *(E7)* | 30/30 (100%) | 59/60 (98.3%) | 🚫 96.7% |
| `composed` *(E7)* | 30/30 (100%) | 51/57 (89.5%) | 🚫 |
| **`llm-translation`** *(E1)* | 65/83 (78.3%) *(E3)* | 86/173 (49.7%) | 🚫 50.0% |

**All four solutions FAIL §8**, including `llm-translation` (p_husk 78.3% vs p_blind 33.3% at the
strongest attacker, cluster-bootstrap 95% CI on the difference **[+0.243, +0.640]** *(E1)*), and all
four trip §8's hard leak-term veto.

**But `llm-translation` is the only transform doing any work.** It roughly halves every leakage
measure *(E1)* while `fpe` and `literal-tagging` sit at ceiling on all three endpoints *(E7)* — exactly as §5
predicted in advance. The finding is not "husking does not work"; it is that the LLM rewrite
substantially degrades domain signal and still does not clear the bar this project set itself.

### 2.0 The BLIND floor was response bias, not a floor

Added 2026-08-19 (amendment A4.1). Every accuracy above is confounded by the attacker's answer
distribution: the BLIND attacker answered `ham-radio-logbook` on **26 of 29** *(E4)* and **23 of 30**
items regardless of what it was shown. Holding each attacker's answers fixed and permuting the true
labels 10,000 times across source files gives what that bias alone buys (DeepSeek / Kimi):

| arm | observed | permuted null | corrected | p |
|---|---:|---:|---:|---:|
| blind *(E4)* | 0.345 / 0.333 | 0.320 / 0.300 | **+0.025 / +0.033** | 0.41 / 0.39 |
| `llm-translation` *(E1, E4)* | 0.721 / 0.783 | 0.282 / 0.304 | **+0.439 / +0.479** | 0.0000 *(E5)* |
| source, `fpe`, `literal-tagging`, `composed` *(E7)* | 1.000 | 0.332 | **+0.668** | 0.0000 *(E5)* |

**BLIND has no recoverable signal at all.** The 10-number structural stub carries nothing about the
domain. The husk−blind *difference* barely moves, so the FAIL verdicts stand — but "33.3% floor"
should never again be described as weak-but-real structural signal. `permutation.md` beside the
summary carries the analytic cross-check.

### 2.0.2 The architecture itself leaks — RSCH-1B, 2026-08-20

Registered in advance as amendment A4 and run against the held-out split. Each source file was
mechanically canonicalised — ~~every identifier, string literal, comment and JSX text node removed~~
*[2026-09-26: not every comment — 8 of the 60 artifacts kept one authored comment verbatim, two of
them in ham-radio vocabulary; erratum E10]* —
control flow / call graph / arity / nesting / coupling left exactly intact — and the same attacker
panel was asked the same 12-option question. Eleven hard gates enforce the transform *(gate G2 could
not see a comment before `)`, `]` or `}`; E10)*, and three
model-free probes find nothing left in it (structural counters 0.047 against a 0.165 null;
canonicalised tokens 0.000 against 0.154 *(E12)*; no token concentrated in any domain).

| arm | observed | permuted null | corrected | p |
|---|---:|---:|---:|---:|
| `structure-only` | 0.467 / 0.520 | 0.232 / 0.276 | **+0.234 / +0.244** *(E10)* | 0.0014 / 0.0031 *(E5, E10)* |
| `structure-only-nonum` | 0.500 / 0.538 | 0.243 / 0.273 | **+0.257 / +0.265** *(E10)* | 0.0008 / 0.0023 *(E5, E10)* |

Against the anchors — BLIND **+0.03**, `llm-translation` **+0.44 / +0.48** *(E1, E4)*, source
**+0.67** — **shape alone carries roughly half the leak a husk carries.** Numeric literals do not explain it:
canonicalising every numeric value left the score unchanged or slightly higher, so this is not the
"format constants" story of §2 below. It is control flow, call graph, arity, nesting and coupling.

**This is the most consequential limitation in this file.** effigy's premise is that architectural
pathology must be preserved. If preserved architecture is itself domain-informative, then the thing
the technique is *required* to keep is part of what leaks, and no verifier enforcing that invariant
can fix it. The claim that needs re-scoping is `docs/working-paper.md` §4.2's, and the honest form
is a trade-off — structural fidelity against domain privacy — rather than a promise of both.

Caveats, and they are load-bearing. **This run's own §8 validity gate is recorded as FAILED**
*(E11)* (`summary.md` §1): it carried no `source` control arm and no `BLIND` arm, so `p_source` is
0/0 and the gate cannot be evaluated, and §3 of that summary marks both arms **NOT COMPUTABLE** on
§8's verdict machinery. The +0.234 / +0.257 figures *(E10)* are therefore *not* §8 verdicts — they
come from the permuted response-bias baseline registered as amendment A4.1, which needs no BLIND
arm, and they should be read as that and nothing more. Also: recognition on a 12-option menu, not
recall; ~~**the open-ended endpoint was not run**~~ *[2026-09-26: it was started and stopped after
13 of 120 calls, all with 0 leak-term hits — too few to measure anything; erratum E11]*, so there is
no free-text or hard-veto measurement; forced-choice coverage 111/120,
with nine Kimi records lost to router 504s (transport, split 5/4 across arms); A3.2 still binds, so
contents only, never paths.

### 2.0.1 One leak channel was mechanical, ~~and is now closed~~

*[2026-09-26: closed only for bare module names such as `meterworks`, which this corpus uses; see
the last paragraph of this section and erratum E8.]*

The Go module name — which in this corpus **is** the domain label — survived **22 of 90** *(E1)*
`llm-translation` husks. On those the attacker was right **44/44 (100%)**; on husks where it was
removed, **83/125 (66.4%)** *(E4)*. `llm_translation.py` had always required own-module imports to be
renamed, so this was a shipped defect rather than a property of husking, and it is now enforced by a
fourth trigger in `_husk_check.check` (fires on 14/14 real cases, 0/76 clean ones — development-log
counts; no committed run records them).

*Scope, 2026-09-26 (E8):* the trigger derives names from import paths only. Until this date it
skipped any import whose first segment contains a dot, so for an ordinary Go module
(`github.com/org/repo/...`) it never fired. It now also takes the org and repo segments of a
host-prefixed path when an import has an `internal/` segment, which Go's own `internal/` rule
guarantees is the importer's own tree. A host-prefixed module with no `internal/` import is still
not covered.

**The residual matters more than the fix.** The remaining 8 leaks (2 Go, 6 TS/TSX) arrive as
*content* — `<h1>qsolog</h1>` — with no import to derive the name from. No import-based rule can see
those; that is work for the unbuilt verifier (§5).

**Three qualifications that are load-bearing.**

*Recognition is not recall.* C1 is phrased in terms of a forced choice over twelve options with the
correct one on the menu. `llm-translation` fails that while removing two-thirds of the free-text
signal *(E1)*. Quoting the menu number alone overstates the leak.

*Copying does not explain it.* Mean copied-span share was **0.269 when the attacker was right and
0.276 when it was wrong** *(E1, E6)* — indistinguishable. `composed` leaks at 100% while
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
corpus's own invented module name — which was a mechanical defect, now closed (§2.0.1; for bare module names only, E8). The one real-world company name that appeared in a guess does
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

*Qualified 2026-09-26 (E16):* "refuses to return a husk that is substantially the source" holds
for the code lines the gate measures. It does not see a comment or docstring copied word for word,
and it never judges an input with fewer than 12 code lines, so such a file can come back
byte-identical with a 200 (§5).

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

**What the floor cannot see (open; owner decision, E16).** Every line-level measure runs on code
with comments and docstrings stripped, so prose copied word for word is invisible to it, and an
input with fewer than 12 code lines is reported and never failed. A docs-heavy file or a single long
line can therefore come back byte-identical with a 200. 6 of the 93 recorded RSCH-1 husks that pass
the gate today carry a verbatim prose run of 5+ lines; one keeps a source path and function name.
Since 2026-09-26 the gate also refuses a copy whose code lines are reordered but otherwise
identical, detects Go from the `package` clause (a types-only Go file used to be read as Python,
which switched the module-name check off), and records its retry budget. The service strips
commentary around a single fenced husk and fails closed on an ambiguous fence layout; a preamble or
trailing note with no fence at all is still served.

So the design document argues that the shipped configuration is a category error, and the shipped
configuration is that category error. Results run on rewriter goodwill.

## 6. FPE key posture

- The key protects **identifier tokens only**. Comments and string literals are untouched (§3).
- **Set `FPE_KEY`.** Without it a random key is generated per process: husks are internally
  consistent within one run, but pseudonyms change on restart, so a re-identification map from an
  earlier process will not dehusk.
- A malformed `FPE_KEY` raises rather than falling back.
- **Some pseudonyms changed on 2026-09-26** (§10). A map saved before then under the same `FPE_KEY`
  will not dehusk tokens whose pseudonym was walked to a usable one, the Go and Python keywords now
  spared, number tails, or non-ASCII identifiers. A token whose first ciphertext was already usable
  keeps its pseudonym.
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
~~not an RSCH-1 domain~~ *[2026-09-26: it is one — `library-circulation`, in the selection split;
no held-out run used it. Erratum E12]*.

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

## 10. Known correctness defects

Found on the earlier, since-withdrawn fixture — their record left `algorithmTests.md` with it (see
its banner) — unfixed as of 2026-08-30 (status after the 2026-09-26 audit beside each):

- **`literal-tagging` breaks on nested template literals** — TSX backtick interpolation defeats the
  regex and can yield syntactically invalid output. *[2026-09-26: fixed only when the request sets
  `options.language` — see below.]*
- **Import paths collapse to `<PATH:n>`/`<MSG:n>`** and become unrecoverable — the single most
  damaging case for dependency-graph reconstruction, which is the primary downstream use.
  *[2026-09-26: still open — see below.]*
- **MIME types are misclassified as `PATH`** (`application/json` matches the path regex), a
  documented false-positive class. *[2026-09-26: fixed for MIME types — see below.]*
- **`fpe` leaks bare JSX text nodes** — there is no parser, so text between JSX tags is not
  recognized as a literal and is enciphered as identifiers. *[2026-09-26: still open, and worse
  than stated — see below.]*

**Status after the 2026-09-26 audit**, which re-checked those four on the current code and found
more. What the fixed defects did to committed husks is erratum E7.

*Fixed:*

- **A single-quoted literal no longer crosses a line break**, in either solution. An apostrophe
  used to pair with a quote hundreds of lines later: after one in a comment (`search's`),
  `literal-tagging` swallowed the code in between into one placeholder and printed later literals
  in plain text (16 of 80 corpus files); after one in JSX text, `fpe` left the identifiers in
  between unenciphered. Double-quoted, triple-quoted and backtick literals may still span lines.
- **`fpe` husks parse.** A pseudonym is re-enciphered until it starts with a letter or `_` and is
  not a word spared at that crumb level; Go (`go`, `defer`, `map`, `chan`, `select`, `goto`,
  `fallthrough`, `range`, `type`) and Python (`assert`, `del`, `global`, `nonlocal`) keywords are
  spared; numbers (`0o755`, `0x1F`, `1_000`) pass through. Corpus Go husks failing `gofmt -e`: 166 of
  172 → 0 (43 files × crumbs 0–3). `husk-api` and `evals` Python files that parse after husking:
  2 of 38 → 34.
- **`fpe` enciphers the code inside `${...}`** in backtick template literals; the literal text
  stays verbatim.
- **Both tokenizers are linear.** An unterminated quote in a 200,000-character request, the
  contract's limit, took about 170 s in `literal-tagging` and held the whole process; it now takes
  under 0.1 s in either solution.
- **`literal-tagging` leaves Go and C rune literals** (`'S'`, `'\n'`) as they are instead of writing
  an illegal multi-character rune. With the line-break fix, corpus Go `literal-tagging` husks
  failing `gofmt -e`: 11 of 43 → 0.
- **MIME types** (`application/json`, `text/plain; charset=utf-8`) **are now MSG**, not PATH.
- **Nested template literals are one literal — only when the request sets `options.language`** to
  js, jsx, ts, tsx, javascript or typescript. Without it the old first-backtick rule applies,
  because a Go raw string containing `${` would otherwise swallow the code after it. Neither the UI
  nor the evals harness sends `options.language`. *[2026-10-01: the UI now does, from its Language
  menu; the harness still does not.]*
- **`fpe` enciphers non-ASCII identifiers** (through the keyed HMAC fallback, counted in
  `meta.non_ascii_identifiers`), and `this.#field` no longer hides the rest of its line.

*Behaviour a caller should know about:*

- `fpe` now enciphers `${NAME}` inside any backtick literal, including a Go raw string or a shell
  backtick; the husk still parses and dehusks, but that string is no longer verbatim.
- A one-character single-quoted string passes through verbatim, in every language.
- A multi-line single-quoted string (Ruby, PHP, shell) is left untagged by `literal-tagging`, and
  `fpe` no longer treats it as one token, so identifier-shaped words inside it are enciphered.
- `fpe`'s `pseudonym_collisions` also counts a crumb-3 pseudonym equal to a token left in plain text;
  under `emit_map` that is refused.
- Some `fpe` pseudonyms changed (§6).

*Still open:*

- **Import paths collapse** (the second item above). Placeholder counters restart per request, so
  `<PATH:0>` in one file has nothing to do with `<PATH:0>` in another, relative paths cannot be
  resolved, and standard-library and internal packages look alike. A fix is a design choice with an
  API cost (the API carries no file path) — owner decision, `ROADMAP.md` §0.
- **`fpe` enciphers JSX text as if it were identifiers** (the fourth item above), with the same key
  as the code. The English word *event* and the prop `event` get the same pseudonym, so guessing one
  word of prose unmasks an identifier throughout the file (committed `tremorline`
  `EventDetail.tsx` husk). `literal-tagging` leaves the same prose verbatim. No regex-only fix is
  safe; the owner has to choose between passing JSX text through and enciphering it under a
  separate key (`ROADMAP.md` §0).
- `literal-tagging` now classes digit-only slash literals (`09/26/2026`, `1/2`) and a short
  fixed list of everyday pairs (`and/or`, `N/A`, `km/h`, `yes/no`, `on/off`, `true/false`,
  `w/o`, `he/she`, `mi/h`) as MSG, not PATH. Any other two-word slash literal is still PATH, and
  an extensionless two-segment path whose first segment is a MIME top-level word (`model/user`)
  is MSG. No committed corpus or eval literal changes class.
- An apostrophe can still pair with a quote later on the same line (`// Don't use 'x'`); the corpus
  has none.
- `fpe`'s comment syntax is language-blind **unless the request sets `options.language`**
  *[2026-10-01]*. Without it, Python `//` floor division and a TS `#private` declaration hide the
  rest of the line from encipherment (37 of 4,059 code names in this repo's own Python). With
  `python`/`py`, `//` is code; with a JS/TS name (as `literal-tagging` takes it), `#` is code apart
  from a leading `#!` line, and a nested template literal is one literal; with `go`/`golang`, `#` is
  code and a backtick raw string passes through verbatim, `${...}` included. `meta.lexer` says
  which rules ran. *[2026-10-01: `c`/`h` and `cpp`/`c++`/`cc`/`cxx`/`hpp`/`hh`/`hxx` make a
  preprocessor line code: the directive name, an `#include <...>` path and a whole `#pragma` line
  stay verbatim, and a `#define`d name gets the same pseudonym as its uses (unset, the line is a
  `#` comment, so the macro's name stays in plain text beside its enciphered uses). `rs`/`rust`
  makes `#[attr]`/`#![attr]` code apart from the attribute's name, passes raw strings
  (`r#"..."#`) through verbatim, and pairs a single quote only as a char literal, so a lifetime
  (`<'a>`, `&'a str`) or loop label no longer pairs with the next quote on its line and leaves
  the names between in plain text. Each adds its language's keywords (spared at every level) and
  its predeclared types and standard names (from crumb 1). Not handled: C++ raw strings
  (`R"(...)"`), nested Rust block comments, and a Rust attribute name that is itself a domain
  word (`#[claims_audit]`).]* Without one of these settings, C `#define`/`#include` and Rust
  `#[attr]` lines still pass through verbatim as `#` comments. The UI sends `options.language` from its Language menu (since
  2026-10-01; unset by default); the evals harness does not.
- `fpe` now leaves two-letter string prefixes (`rf"..."`, `Rb'...'`) and the TS contextual keywords
  `keyof`, `readonly`, `declare` and `satisfies` as they are; each used to be enciphered and break
  the parse. *[2026-10-01: from crumb 1 it also spares Go's predeclared types and builtins
  (`string`, `error`, `int64`, `byte`, `make`, `append`, ...) and TS's primitive types (`number`,
  `boolean`, `undefined`, ...), as L1 specifies; they had been enciphered at every level — 1,398 of
  18,659 enciphered corpus tokens. Crumb 0 still enciphers them.]* Without a JS/TS
  `options.language` it splits a nested template at the inner backtick, and it does not encipher
  interpolation inside
  double-quoted strings (Ruby `#{}`, Kotlin/shell `${}`, C# `$"{}"`).
- *[2026-10-01]* **`fpe` enciphers the expressions in Python f- and t-string replacement fields**
  (`f"{invoice.amount_due!r:>{width}}"`, any prefix case, `'''`/`"""` included); the literal
  text, `{{`/`}}`, `\N{...}`, the conversion and the format-spec text stay verbatim. Every such
  name used to pass through in plain text: 378 of 378 in `husk-api`'s and `evals`' own Python,
  0 after. Those 30 husks still all parse, Go/TS husks are byte-identical, and husk → dehusk
  exactness is unchanged.
- A short `fpe` pseudonym can equal an ordinary word (`id`, `OR`) inside a literal, comment or
  diagnosis, and `/dehusk` then rewrites that word. Husk → dehusk of the husk text is exact in 1869
  of 1920 cases (8 keys × 80 files × crumbs 0–2), up from 1644.

## 11. Threat-model exclusions

Out of scope by design: an adversary with access to the rewriter's weights or activations, and side
channels generally.

Additionally true of this implementation, and not to be mistaken for design:

- The re-identification map is **client-held and unencrypted**. It travels in a normal JSON response
  body and sits in a browser tab with no expiry. For `fpe` it is a complete identifier dictionary of
  the source; for `literal-tagging` it maps every placeholder back to its literal, including
  anything classified as a key. One leaked map is a total compromise of that husk.
- The service has **no authentication** of any kind.
- ~~The service is **not hardened**: importing the app writes to disk, so it will fail to start on a
  read-only filesystem, and a stub solution (`example`, which simply reverses its input) is
  registered on the public API surface.~~ *[2026-09-26: the read-only claim held only when the
  targets JSON was stale, `static/` was missing, or on a non-editable install (erratum E15); both
  defects are fixed — next item.]*
- **Hardened on 2026-09-26.** Importing the app writes nothing: the committed targets JSON is
  regenerated by hand, and a test fails if it drifts from the catalog. `/ui` is mounted only when
  the static files exist, and a built wheel carries them as `app/static`. `example` is registered
  only when `HUSK_ENABLE_EXAMPLE=1` is in the process environment. After the OpenAI client's own two
  retries, an upstream 429 returns 503 `backend_rate_limited` and an upstream 408 or 5xx returns 502
  `backend_unavailable`, instead of the service's own 500; a hung backend costs up to 3 ×
  `LLM_TIMEOUT_SECONDS` (540 s at the default) before the 502. The gate on a 196,044-character
  honest husk dropped from 23 s to 0.3 s.
- **Still not hardened:** beyond the missing authentication, an upstream status other than 408,
  429 or 5xx (such as a 403 spending cap) is still a 500 `solution_failed`, and a near-identical or
  highly repetitive pair near the 200,000-character limit can still hold the gate for 10 s or more
  per attempt.

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
