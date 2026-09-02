# Corpus domain expansion — generation contract

**Status:** build contract. Normative. **Scope:** the five domains added alongside `stacks/` to
make `evals/preregistration.md` runnable.

## 1. Why these exist

RSCH-1 measures whether an attacker can recover a source file's **problem domain** from its husk.
Prereg §2: against a **single-domain** corpus an attacker that ignores its input and always answers
that one domain scores 100%, so any recovery rate measured that way is an artifact of the corpus
rather than a property of the husk. §2 therefore requires **K ≥ 6 distinct source domains**, and
calls that "a precondition for this pre-registration being meaningful at all."

`corpus/stacks/` is one domain. `evals/domains.json` declares the six intended source domains;
when this contract was written, five of them had zero artifacts. **This document is the contract
for those five** — they have since been built to it, and `evals/verify_domains.py` gates them.

## 2. Each domain gets its OWN architecture

The tempting shortcut is to clone `stacks`'s architecture five times and swap the vocabulary. **Do
not.** The BLIND arm hands the attacker a structural stub — language, line count,
struct/handler/interface/import counts, max brace depth — and measures what *structure alone*
reveals. If all six domains share one architecture, BLIND lands exactly at chance by construction,
every point of HUSK accuracy above it is attributed to vocabulary, and the husk gets credit for
closing a channel the corpus never opened. That is a flattering floor, and prereg §3 exists
specifically to stop the floor being tuned.

So each domain has its own entity model, its own endpoint shapes, its own parser format, and its
own component decomposition. What they share is **kind, stack, and size envelope** — enough that
domain identity is the variable under study and language/scale is not.

## 3. Shared skeleton

Same stack as `stacks/`: **Go 1.22 HTTP service** (`chi` router, `database/sql` over SQLite) plus a
**React 18 / TypeScript / Vite SPA**. Same house style — read
`corpus/stacks/api/internal/api/branches.go` and
`corpus/stacks/app/src/components/ResultsTable.tsx` before writing a line.

Concretely that means: tab-indented Go; raw SQL as backtick string literals inline in handlers;
`writeJSON` / `writeError` helpers; `chi.URLParam`; `COALESCE(col,'')` on nullable reads;
`errors.Is(err, sql.ErrNoRows)` → 404; a `*Server` struct carrying `db`; TS with two-space
indentation, `interface` over `type` for object shapes, named function exports (not default),
`className` strings rather than any CSS-in-JS.

### 3.1 Exactly ten artifacts per domain, every one in the 40–400-line envelope

Prereg §1 fixes the envelope as Go / TypeScript / TSX, 40–400 lines, HTTP-service and
SPA-component code. **A file outside 40–400 lines is not a corpus artifact** — it is excluded from
the manifest and wasted work.

| # | Path (under `corpus/<domain-dir>/`) | Lines | What it is |
|---|---|---|---|
| 1 | `api/cmd/<svc>d/main.go` | 80–120 | wiring, flags, `envOr`, listen address literal |
| 2 | `api/internal/api/server.go` | 90–140 | `Server`, `NewServer`, `Handler()`, route table, CORS, health |
| 3 | `api/internal/api/<primary>.go` | 240–380 | the domain's main read/search/patch handlers |
| 4 | `api/internal/api/<secondary>.go` | 70–120 | a second, smaller resource |
| 5 | `api/internal/ingest/<format>.go` | 200–350 | a text-format parser for this domain's interchange format |
| 6 | `api/internal/model/<entity>.go` | 40–70 | the struct set with JSON tags |
| 7 | `app/src/api/client.ts` | 130–190 | interfaces, `ApiError`, fetch wrappers, URL builder |
| 8 | `app/src/App.tsx` | 110–180 | page shell, state, wiring |
| 9 | `app/src/components/<Detail>.tsx` | 90–140 | read-only detail view |
| 10 | `app/src/components/<Form>.tsx` | 130–190 | a form with client-side validation |

### 3.2 What is deliberately NOT required

**No planted pathologies.** `PATHOLOGY.md` and its symbol anchors belong to the defect-detection
evaluation, which runs against `stacks` only. RSCH-1 measures domain recovery and does not read
them. Write naturally; do not engineer defects, and do not engineer them out.

**Not buildable, and that is a stated scope limit rather than a shortcut.** No `go.sum`, no
lockfiles, no `node_modules`, no tests, no seed data, no `schema.sql`, no `Makefile`. The gate is
**syntactic validity** (§5), not a green build. This is sound because the attacker is shown one
file's *contents* and nothing else: buildability is invisible at the item level, so it cannot bias
a comparison between domains. It does mean these trees are attack inputs and not runnable apps,
and `corpus/README.md` must say so.

## 4. Fabrication rules

Every rule in `corpus/README.md` §"Fake-data conventions" carries over in spirit: **all data is
invented**, models no real institution, product, vendor, standard body or system, and must never be
documented as resembling one. Per domain:

- **Identifiers** are sequential fictions with a domain-flavoured prefix, never a real registry
  value, and never structurally valid where a real check digit or checksum exists.
- **People**: opaque ids only. No names, addresses, dates of birth, or contact data anywhere.
- **Phone literals**: only the reserved `+1-555-01xx` block. **Email**: only `@example.org`.
- **Credentials**: `dev` / `dev`, each carrying an inline `// dev-only, not a secret` comment.
- **Interchange formats are invented local profiles.** Give the parser a plausible line-oriented or
  fixed-width format of your own design and say in the package doc that it is a local profile. Do
  **not** implement a real published standard — `stacks` implements a real one (MARC 21) and that is
  already the corpus's one known worst case for re-identification (`LIMITATIONS.md` §2). Five more
  of them would bake that worst case into the result.

## 5. Acceptance gates

Every gate is mechanical. A domain that fails one is not done.

1. **Ten files, all 40–400 lines.** `awk 'END{print FNR}'` per file.
2. **Go parses.** `gofmt -e -l <dir>` prints nothing and exits 0.
3. **TS/TSX parses.** `tsc --noEmit --jsx react-jsx` reports **no TS1xxx** diagnostic. TS2xxx
   (unresolved import, missing React types) is expected — these compile standalone.
4. **Self-contained.** `grep -rn '\.\./\.\.'` over the tree returns nothing.
5. **No cross-domain bleed.** No file may contain any other domain's `leak_terms`, and no file
   anywhere may carry `stacks` vocabulary — no `isbn`, `marc`, `dewey`, `oclc`, `lccn`,
   `bibliographic`, `patron`, `borrower`, `circulation`, `holding`, `shelfmark`, `interlibrary`.
6. **`leak_terms` authored and disjoint.** 15–25 terms per domain, the discriminative vocabulary a
   husk would have to destroy. Pairwise disjoint across all six domains, and excluding ordinary
   programming vocabulary — `record`, `index`, `branch`, `state`, `zone`, `region`, `catalog`,
   `entry`, `report` are all forbidden because they fire constantly on unrelated code.

## 6. The five domains

Ids are fixed by `evals/domains.json` and must match it exactly.

### 6.1 `ham-radio-logbook` → `corpus/qsolog/`
Amateur radio contact logging. Entities: operator station, contact (QSO), band/mode pair,
confirmation, award credit. Service shape: contact search filtered by band, mode and date window; a
confirmation-matching handler that pairs a logged contact against an inbound confirmation; an
award-progress rollup that counts distinct worked entities. Parser: a tag-delimited log-interchange
format of your own invention (`<field:len>value` runs terminated by an end-of-record tag).
Module `qsolog`. Listen `:8310`. Vite `5310`.

### 6.2 `water-utility-metering` → `corpus/meterworks/`
Municipal water metering. Entities: service point, meter, read, consumption interval, rate tier,
billing cycle. Service shape: reads listed by route with a paging window; a consumption calculation
that walks tiered rates and accumulates; a re-read/exception handler for reads flagged out of
tolerance. Parser: a **fixed-width** meter-read import file — column offsets, a header line, a
trailer with a record count that is verified. Module `meterworks`. Listen `:8320`. Vite `5320`.

### 6.3 `seismic-monitoring` → `corpus/tremorline/`
Seismic event monitoring. Entities: station, channel, waveform segment, detection, event, magnitude
estimate. Service shape: event catalog query bounded by time window, magnitude range and a
lat/long box; a station-channel inventory listing; a detection-to-event association handler.
Parser: a channel-metadata text format of your own invention, with an epoch-ranged validity block
per channel. Module `tremorline`. Listen `:8330`. Vite `5330`.

### 6.4 `textile-mill-production` → `corpus/loomshed/`
Textile mill production. Entities: loom, yarn lot, shift, production run, defect entry, order.
Service shape: run detail with per-shift output; a loom-utilisation rollup across a date range; a
defect-entry patch handler with validation. Parser: a shift-report ingest, one block per loom per
shift, with a continuation-line convention. Module `loomshed`. Listen `:8340`. Vite `5340`.

### 6.5 `avionics-airworthiness` → `corpus/tailwatch/`
Aircraft airworthiness tracking. Entities: airframe, component position, part serial, life limit,
maintenance interval, directive, compliance record. Service shape: component drill-down by
airframe; a remaining-life computation over hours/cycles/calendar with whichever-comes-first
selection; a directive-compliance listing. Parser: a directive-applicability import, one directive
per block with applicability predicates. Module `tailwatch`. Listen `:8350`. Vite `5350`.

## 7. After generation

    python3 evals/run_eval.py --refresh-manifest   # fingerprint all six domains
    python3 evals/run_eval.py --verify             # re-hash; stacks anchors must still resolve

The manifest's `domains` block gains one entry per new domain carrying `true_domain_id` (matching
`evals/domains.json`) and the authored `leak_terms[]`. Those terms are **authored ground truth**:
never derive them from a husk, because a list built from the output cannot measure the output.
