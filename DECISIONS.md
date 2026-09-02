# effigy — Decisions

Append-only. One entry per ship or per decision that changes direction. **Supersede, never
silently rewrite** — a decision that is later reversed gets a new entry that names and supersedes
the old one; the old entry stays. Roadmap items cite entries by date + title.

## 2026-04-30 (approx.) — Retire `crumb_level` as `llm-translation`'s target-selection knob

The four-level "crumb" gradient did not produce a meaningful privacy/utility gradient on capable
models — the levels collapsed into "which target the deterministic picker happens to land on,"
and a privacy-leak inversion was found where levels designed for closer translation leaked more
source-domain structure. Replaced with a flat, explicit target-domain catalog
(`options.target_id` / `options.target_domain`). `crumb_level` is still accepted on the
`llm-translation` endpoint for contract uniformity but is unused. Source: `docs/handoffs/
06-llm-translation-target-catalog.md`, `docs/draft-1.md` §6.3, `algorithmTests.md`
"Re-evaluation: qwen2.5-coder:14b".

## 2026-08-07 — Install ROADMAP.md/DECISIONS.md triad; keep build-history handoffs in place

`docs/handoffs/01-06` are actively indexed by `README.md` as "the build history," not orphaned
session-status docs — kept in place rather than folded/staged, unlike the sweep's default
handling of `HANDOFF*`-named files. Only `rerun-llm-test.md` (an orphaned, zero-inbound-ref
completed eval task whose result duplicates into `algorithmTests.md`) was staged.

## 2026-08-19 — `fpe` stops shipping its own decryption key; alphabet gains `_`

`_load_key()` returned a constant baked into `app/solutions/fpe.py` whenever `FPE_KEY` was unset
— the documented default. Because pyffx's Feistel is invertible and the alphabet is fixed, that
made every default-config husk decryptable by anyone holding the source, falsifying `README.md`'s
"unrecoverable without the key" for the path everyone actually ran. Demonstrated by round-tripping
`handleMemberLookup` from the published constant. Now: a malformed `FPE_KEY` raises instead of
falling back; production fails closed; the default is a random per-process key; the old constant
survives only behind `FPE_DEMO_KEY=1` so recorded outputs stay reproducible.

Separately, `_ALPHABET_MIXED` excluded `_` while `_IDENT_RE` admitted it, so the sanitizer folded
`_` onto `H` (`ord("_") % 62 == 33`) and `foo_bar`/`fooHbar` enciphered identically to `k9pHwWF`.
The re-identification map was built by a dict comprehension, so one original was dropped silently
and `/dehusk` rewrote diagnoses with the wrong identifier. The alphabet now includes `_`, and a
reverse index raises on collision when a map is requested. Pseudonyms changed once, in this
commit. Source: `LIMITATIONS.md`, `husk-api/tests/test_fpe.py`.

## 2026-08-19 — Drop the vendored fixtures; the results file dies with its corpus

`membership/` and `testCode/` were third-party-derived fixtures carried as translation test
inputs. They are not this project's code to publish, so they were removed rather than carried
into a public repository, along with every path, identifier and vocabulary that described them.

Two things went with them that were not in the original scope, on the same reasoning.

**The dogfood husk tree** (`evals/runs/20260819-dogfood-sibling/husk/`). It was committed on the
strength of its measurements, and the measurements are what condemned it: every file returned
lines of a *private sibling repo* byte-identical — 118 of 162 in `sources/source_a.py`, which the
service reported as a success and never transformed at all, plus 124, 85, 67 and 47 in the
others. `source_a.py` also carried real regulatory-filing identifiers. Its `RESULT.md` keeps every number; the
husks added no evidence the write-up lacked.

**`algorithmTests.md`'s verdicts.** Every input path in them pointed into the superseded tree, so they
could not be reproduced or located. Rewritten from committed `evals/runs/` records rather than
migrated — rewriting evidence to survive a change in the thing it measured is the failure mode
its own editor's note existed to prevent. The cost is stated in the file: **`fpe` and
`literal-tagging` held `viable-with-caveats` verdicts that have not been re-earned, and are now
unmeasured rather than previously-passing.**

`docs/handoffs/02,03,04` were **annotated, not rewritten** — root `CLAUDE.md` keeps `01-06` as
the per-component build record.

## 2026-08-19 — Build the corpus to six domains rather than weaken RSCH-1's design

**Context.** `evals/preregistration.md` was committed frozen and unrun. Its §2 requires **K ≥ 6
distinct source domains** and calls that "a precondition for this pre-registration being meaningful
at all," because against a single-domain corpus an attacker that ignores its input and always
answers that one domain scores 100%. The corpus was `corpus/stacks/` alone — one domain, 22
artifacts. `evals/domains.json` already named the six intended source domains; five had no
artifacts. Amendment A1's selection/held-out split could not be drawn either.

**Decision.** Build the five missing domains rather than relax §2. `corpus/DOMAINS.md` is the build
contract; `evals/verify_domains.py` is the mechanical gate. Result: **72 artifacts, 64 inside the
40–400-line envelope** against a target of 48, three domains per split.

**Three sub-decisions worth not relitigating.**

1. **Each domain gets its own architecture, not `stacks` with the vocabulary swapped.** The BLIND
   arm hands the attacker a structure-only stub. If all six shared one architecture, BLIND would sit
   at chance *by construction*, every point of husk accuracy above it would be attributed to
   vocabulary, and the husk would get credit for closing a channel the corpus never opened. Measured
   after the fact: relative spread across the six domain means is 0.17–0.53 per counter — similar in
   kind, no giveaway.

2. **The five new domains are syntactically valid but not buildable, and that is a stated limit.**
   No `go.sum`, no lockfiles, no tests, no seed data. Sound *for this experiment specifically*
   because the attacker sees one file's contents and nothing else (amendment A3.2), so buildability
   is invisible at the item level. **Not** sound for the defect-detection evaluation, which stays on
   `stacks`. Recorded in `corpus/README.md` so it is not filed as a gap later.

3. **The five implement invented local interchange formats, never real published standards.**
   `stacks` implements a real one (MARC 21) and that is already the corpus's single known worst case
   for re-identification — `LIMITATIONS.md` §2 records a frontier model recovering "MARC 21 /
   library catalog" from parsing constants alone. Five more real standards would bake the worst case
   into the aggregate and make the headline a statement about public-standard parsers rather than
   about husking.

Superseded by nothing. See `evals/preregistration.md` amendment A3, appended before the first run.

## 2026-08-30 — Drop `docs/Effigy_Technical_Abstract.pdf` rather than annotate it

The abstract was written before the evidence and five of its claims are now contradicted by this
repository's own code and results:

1. *"The output is unrecoverable: no inversion exists, no re-identification path is preserved."*
   `POST /dehusk` (`husk-api/app/main.py:93`) reverses a husk's identifiers from a caller-supplied
   pseudonym map obtained via `options.emit_map` — a re-identification path the product
   deliberately offers. `fpe` is key-invertible besides; `LIMITATIONS.md` F7 records a worked decrypt.
2. *"a two-layer transformation … k-anonymity, differential privacy noise injection."* Neither is
   implemented. `husk-api/` contains no k-anonymity, differential-privacy, Laplace or epsilon
   machinery of any kind.
3. *"The format supports configurable crumb levels."* `llm-translation` ignores the parameter —
   `husk-api/app/solutions/llm_translation.py`'s `husk()` reads `crumb_level is unused` and
   `del crumb_level`. Target selection is from a flat catalog.
4. *"conformance testing verifies [the crumb-level bounds]."* The verifier is specified and unbuilt.
5. *"The husk does not leak organizational identity."* RSCH-1B measured architecture alone
   recovering the source domain at +0.24 over a permuted null (p≈0.002).

**Decision: remove the file, do not ship an erratum.** It is a ReportLab binary with no source in
the tree, so it cannot be corrected in place; an erratum covering five claims would be longer than
the abstract and would leave a document whose headline privacy guarantee is false in the
repository anyway. `docs/working-paper.md` and `LIMITATIONS.md` are the accurate, maintained
statements of the same material, and the abstract was an orphan — nothing linked it but one
incidental line in a historical ROADMAP handoff block.

## 2026-08-31 — Regenerate the one drifted manifest entry, having established it is bookkeeping

`evals/run_eval.py --verify` failed on `corpus/tailwatch/api/internal/ingest/localdirective.go`:
the manifest recorded 11391B/347L, the file on disk is 11635B/349L. Regenerating a digest to make
a failing check pass is normally the exact failure mode this repo names — "rewriting evidence to
survive a change in the thing it measured" — so it was refused once and investigated instead.

It is not that, and the deciding fact is the recorded `git_blob_oid`:

- The manifest's recorded blob `041b4980…` **does not exist in this repository at any commit.**
  The version it describes was never committed. The file and the manifest were written in the
  *same* commit that built the six-domain corpus, and the file was never modified after, so `--refresh-manifest`
  simply ran before the last edit to that one file. A build-order slip, not drift.
- Therefore the committed file is what every consumer has ever read. No measurement was taken
  against the version the manifest describes, because that version was never available to take one.
- Exactly **1 of 72** artifacts was affected — not systemic.
- No run record pins the **per-artifact** digest, and `corpus/PATHOLOGY.md` anchors its nine
  defects in `corpus/stacks/` only, so no anchor could be erased by the refresh.
- **Correction, found in review:** eight run `config.json` files — including both headline runs,
  `20260819T182111Z-rsch1-held-out` (RSCH-1) and `20260820T021753Z-rsch1-held-out` (RSCH-1B) — do
  pin the **whole-manifest** digest, and this refresh moves it:
  `20b5e3d622635f4fd25787c0089dbd2852156ab2d62fe7bc14fe4025ff7c6fa0` →
  `ed6f3ef1bc97bbd021769d08617693b2a3ad413e4200a687939c30cd3b5a5531`. Both are recorded here so an
  old config still maps to the manifest document that was current when it ran. What this costs is
  the ability to confirm "this run's manifest == the manifest in the tree" by hash; it does not
  change what those runs measured, because they read the files on disk and the disk files are
  unchanged — the refreshed entry describes a version that was never in the tree. An older pin,
  `fc7c27d08c79e5b6fe5547b6920e6fee0a79d408c45a3da213e17c366d87ab4e`, shows this digest had already
  drifted across manifest revisions before now.
- The file parses clean and is `gofmt`-clean.

**Decision: regenerate via the documented path** (`evals/run_eval.py --refresh-manifest`, which
`corpus/DOMAINS.md` §7 already prescribes after generation, and which deliberately preserves the
authored `domains` block so a refresh cannot reset the privacy eval's ground truth). The resulting
diff is four derived fields on one entry; artifact count, ordering, paths and `domains` are
byte-identical. `--verify` now reports OK on all 72.

## 2026-09-01 — Publication addendum: references that do not resolve in the published tree

Written for the public flip. Entries above are left exactly as written, per this file's rule; this
entry records what a reader of the published tree cannot follow, and what they can check instead.

- **The 2026-04-30 entry** cites an `algorithmTests.md` section, "Re-evaluation:
  qwen2.5-coder:14b". That section was deleted in the 2026-08-19 rewrite (see "Drop the vendored
  fixtures" above and the banner at the top of `algorithmTests.md`). The 14B verdict now survives
  only as a disclaimed aside at the end of that file's "`llm-translation` — model scale, and a
  reversal" section.
- **The 2026-08-31 entry** reasons from commit and blob history ("does not exist in this repository
  at any commit", "written in the same commit that built the six-domain corpus"). Those claims were
  made against the full development history; the published tree is a single root commit, so they
  cannot be re-derived from it. What a reader can still check: `git cat-file -e 041b4980` fails
  here too, and `python3 evals/run_eval.py --verify` reports OK on all 72 artifacts.
- **Every commit SHA** cited in this file, in `ROADMAP.md`, in `algorithmTests.md` and under
  `evals/runs/` identifies the pre-publication history and will not resolve. `evals/README.md`
  § "Commit references under `evals/runs/` do not resolve" is the standing disclosure.
