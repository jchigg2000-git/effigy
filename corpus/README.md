# corpus

Reference evaluation input for the husking transforms. Everything under this
directory exists to be rewritten by a transform and then measured; nothing here is
a product, a library, or a thing anyone should run in anger.

| Path | Domain | What it is |
| --- | --- | --- |
| `stacks/` | `library-circulation` | A synthetic inter-branch library catalog and circulation system — a Go HTTP service plus a React/TypeScript SPA. |
| `qsolog/` | `ham-radio-logbook` | Amateur radio contact logging. |
| `meterworks/` | `water-utility-metering` | Municipal water metering and consumption billing. |
| `tremorline/` | `seismic-monitoring` | Seismograph station networks and event cataloguing. |
| `loomshed/` | `textile-mill-production` | Loom scheduling and shift production reporting. |
| `tailwatch/` | `avionics-airworthiness` | Component life limits and directive compliance. |
| `DOMAINS.md` | — | The build contract for the five domains added alongside `stacks`. Normative. |
| `stacks/SPEC.md` | — | The build contract `stacks` is generated from. Normative. |
| `PATHOLOGY.md` | — | The deliberate-defects manifest, **for `stacks` only**. `evals/run_eval.py --verify` reads it. |

## Why there are six domains and not one

`evals/preregistration.md` §2: against a **single-domain** corpus, an attacker that ignores its
input and always answers with that one domain scores 100%, so any re-identification rate measured
against it is an artifact of the corpus rather than a property of the husk. The pre-registration
therefore requires **K ≥ 6 distinct source domains**, and calls that a precondition for being
meaningful at all. `stacks` is one; the other five exist to make RSCH-1 runnable.

Each of the five has its **own** entity model, endpoint shapes, parser format and component
decomposition. That is deliberate and is explained in `DOMAINS.md` §2: if all six shared one
architecture, the BLIND arm — which hands the attacker a structure-only stub — would sit at chance
by construction, and the husk would get credit for closing a channel the corpus never opened.

## `stacks` is the only runnable tree

`stacks` builds and its tests pass. **The other five do not, by design.** They carry no `go.sum`, no
lockfiles, no `node_modules`, no tests, no seed data and no schema; the gate they are held to is
syntactic validity (`gofmt -e` clean, no TS1xxx diagnostics), not a green build. See `DOMAINS.md`
§3.2 for why that is sound: the RSCH-1 attacker is shown one file's *contents* and nothing else, so
buildability is invisible at the item level and cannot bias a comparison between domains.

They are **attack inputs, not applications.** Do not try to run them, and do not file their missing
build files as a gap.

The deliberate-defects rules below apply to **`stacks` only** — the other five carry no planted
pathologies, because `PATHOLOGY.md` serves the defect-detection evaluation and RSCH-1 does not read
it.

## Three things to know before touching anything here

**1. It is synthetic.** `stacks` is fabricated end to end. Every title, author,
identifier, call number, phone number, branch, borrower and credential in it was
invented for this purpose. It models no real institution, consortium, catalogue,
vendor, product or system, and it must never be described, documented or
introduced as resembling one. It is also not a reference implementation of any
metadata standard: the MARCMaker reader handles a documented subset plus a stated
local profile, and the Dublin Core exporter emits a one-way, download-only
projection.

**2. The defects are deliberate and must not be fixed.** `stacks` contains a
god-struct, raw SQL inside HTTP handlers, a persistence package with no queries in
it, SQL assembled by string concatenation, a parser nested six braces deep,
closures mutating captured state across switch arms, a nineteen-column positional
scan, and an error-handling block copy-pasted across five handlers. All of it is
on purpose. The evaluation measures whether these structures survive a husking
transform, so they have to be present, in known places, at known sizes.

Refactoring, linting away, extracting, parameterising or "cleaning up" any of them
destroys the measurement. So does reformatting that changes file lengths: prior
findings are keyed to file size, and the line counts in `stacks/SPEC.md` §4 are
part of the contract. Every defect is catalogued in `PATHOLOGY.md` with a symbol
anchor; if a tool or an agent proposes a fix, point it there.

**3. All data is fabricated.** Deliberately so, and to a fixed set of rules.

## Fake-data conventions

| Datum | Rule |
| --- | --- |
| Works | Public domain, published before 1929, by authors dead more than 95 years. Both are checked before a title is added. |
| ISBNs | Drawn from a `978-0-00-0000NN-9` block with **deliberately invalid check digits** — the final digit is fixed at `9` regardless of the mod-10 result, so no string here can collide with an assigned ISBN. Never compute a valid check digit. |
| Control numbers | Sequential fictions: `stk00000001`, `stk00000002`, … The collection-level record uses `stk00000000`. |
| OCLC numbers | Sequential fictions: `(OCoLC)ocm00000001`, … |
| LCCN values | Sequential fictions: `lcc00000001`, … Structurally not valid LCCNs. |
| Borrowers | Opaque identifiers only — `BRW-0000001` through `BRW-0000012`. **No names, no addresses, no dates of birth, no contact data, anywhere**: not in the seed, not in the tests, not in the fixtures, not in the SPA. The borrower table has two columns for exactly this reason, and the JSON projection of a loan omits borrower identity entirely. |
| Branches | Exactly three: `BR-CENTRAL`, `BR-EASTSIDE`, `BR-NORTHGATE`, under the invented system `STK-SYS-001`, "Oakhurst County Library System". |
| Call numbers | Dewey- or LC-flavoured and plausible, e.g. `PR4571 .A1 1859`. Not authoritative. |
| Phone literals | Only from the reserved `+1-555-01xx` block. The seed carries the dashed form; ingest normalises to digits, and the API, database and UI carry the digits. |
| Email literals | Only `<local>@example.org`. |
| Shelf bins | Five digits, e.g. `01420`. Wings are two letters: `NW`, `NE`, `SW`, `SE`. |
| Credentials | `dev` / `dev` for the SPA login curtain and `localdev` for the admin ingest token. Each carries an inline `// dev-only, not a secret` comment: they are scanner bait by design, and the comment is what keeps a secret scan from being a false positive. There is no real credential in this tree. |

## Self-containment

Nothing under `corpus/stacks/` may reference a path above it. The seed file lives
at `stacks/api/testdata/catalog_seed.mrk`, the listen address is the literal
`:8300` in `main.go`, the SPA's TypeScript config is standalone with no `extends`,
and `go.sum` and both lockfiles are committed. `grep -rn '\.\./\.\.'` over the tree
returns nothing outside `node_modules/`. The previous fixture failed all of this
and was not clonable; that is the anti-pattern this one exists to not repeat.

## Verifying it

    python3 evals/run_eval.py --refresh-manifest   # fingerprint the corpus
    python3 evals/run_eval.py --verify             # re-hash it, re-resolve every anchor

`--verify` fails if any artifact's bytes changed without the manifest being
refreshed, or if any `PATHOLOGY.md` anchor no longer resolves to corpus source.
