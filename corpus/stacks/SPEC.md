# `stacks` — Corpus Generation Specification

**Status:** build contract. Normative. Everything below is required unless marked *soft*.
**Scope:** this file plus its sibling `PATHOLOGY.md` are the complete institutional memory for
this corpus. The tree it describes is generated from this document alone — there is no other
source to consult.

---

## 1. Purpose

`stacks` is a **synthetic** two-tier application — a Go HTTP service plus a React/TypeScript
single-page client — built for one job: to be **evaluation input for husking transforms.**

A husking transform rewrites source code so that identifiers, literals, or the whole domain are
replaced, while the *architectural shape* of the program is expected to survive. The evaluation
measures whether specific, deliberately-planted structural defects are still diagnosable in the
husked output. That measurement is only meaningful if the input carries those defects in known
places, at known sizes.

Therefore:

- **This corpus is fabricated.** Every title, identifier, phone number, address, and credential in
  it is invented for this purpose. It models no real institution, product, vendor, or system, and
  must never be described as resembling one.
- **The defects in it are intentional.** They are the measurement instrument. See §9.
- **The line counts in §4 are part of the contract**, because prior evaluation findings are keyed
  to file size ("a 375-line handler file", "the 166-line client"). A rebuild that drifts on size
  invalidates comparison against those findings.

### 1.1 What it replaces

This corpus supersedes an earlier vendored fixture (hereafter **"the superseded corpus"**). That
fixture was measured, and its measurements are transcribed into §3–§7 of this document as *shape*
— structure, arity, nesting, symbol inventory — never as its subject matter. The superseded corpus
is being removed from history; **after removal, nothing in it is recoverable, and this file is the
only record of what has to be reproduced.**

The replacement is written in the public-library catalog and circulation domain from its first
line. No vocabulary, identifier, comment, path segment, module name, or fixture datum from the
superseded corpus's subject matter may appear anywhere in the generated tree.

---

## 2. Domain model

A regional library system operates several branches. Each branch shelves **holdings**
(bibliographic records for physical items). Holdings circulate to **borrowers** under **loans**,
and borrowers can queue for an item via **reservations**. Everything is inter-branch: a loan
records the branch a borrower will collect from, which need not be the branch that shelves the
item.

### 2.1 Entities

| Entity | Grain | Notes |
|---|---|---|
| `system` | one per install | The consortium that owns the branches. Exactly one row in the seed. |
| `branch` | one per physical location | Three in the seed. Owns holdings. |
| `holding` | one per shelved item | The central record. 24 in the seed. |
| `loan` | many per holding | Circulation events with an effective period. |
| `borrower` | referenced by loans/reservations | **Opaque ID only** — see §7.4. |
| `reservation` | many per holding | Queued requests. Never joined into the holding read path. |

Cardinality: `system 1—N branch 1—N holding 1—N loan`, plus `borrower 1—N loan` and
`borrower 1—N reservation`.

### 2.2 SQLite schema — `api/internal/store/schema.sql`

Verbatim contract. Column names, order, and nullability are load-bearing (see P8 in §5).

```sql
CREATE TABLE IF NOT EXISTS systems (
  system_id TEXT PRIMARY KEY,
  name      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS branches (
  branch_id       TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  registry_symbol TEXT,
  system_id       TEXT REFERENCES systems(system_id)
);

CREATE TABLE IF NOT EXISTS holdings (
  holding_id      TEXT PRIMARY KEY,
  branch_id       TEXT NOT NULL REFERENCES branches(branch_id),
  author          TEXT NOT NULL,
  title           TEXT NOT NULL,
  published       TEXT NOT NULL,
  language        TEXT,
  material_code   TEXT,
  circ_status     TEXT,
  collection_code TEXT,
  isbn            TEXT,
  desk_phone      TEXT,
  call_number     TEXT,
  room            TEXT,
  wing            TEXT,
  bin             TEXT
);
CREATE INDEX IF NOT EXISTS holdings_branch_idx    ON holdings(branch_id);
CREATE INDEX IF NOT EXISTS holdings_title_pub_idx ON holdings(title, published);

CREATE TABLE IF NOT EXISTS loans (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  holding_id      TEXT NOT NULL REFERENCES holdings(holding_id),
  borrower_id     TEXT REFERENCES borrowers(borrower_id),
  loan_type       TEXT NOT NULL,
  loan_level      TEXT,
  policy_code     TEXT,
  pickup_branch   TEXT,
  effective_start TEXT NOT NULL,
  effective_end   TEXT
);
CREATE INDEX IF NOT EXISTS loans_holding_idx ON loans(holding_id);

CREATE TABLE IF NOT EXISTS borrowers (
  borrower_id    TEXT PRIMARY KEY,
  home_branch_id TEXT REFERENCES branches(branch_id)
);

CREATE TABLE IF NOT EXISTS reservations (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  holding_id     TEXT NOT NULL REFERENCES holdings(holding_id),
  borrower_id    TEXT NOT NULL REFERENCES borrowers(borrower_id),
  pickup_branch  TEXT,
  placed_on      TEXT NOT NULL,
  queue_position INTEGER NOT NULL DEFAULT 1,
  status         TEXT
);
CREATE INDEX IF NOT EXISTS reservations_holding_idx ON reservations(holding_id);
```

**Hard invariant:** the `holdings` table has **exactly 15 columns** and `branches` has **exactly
4**. Their join drives a **19-column positional `Scan`** (P8). Adding a column to either table
breaks a catalogued defect and is forbidden without a matching `PATHOLOGY.md` edit.

`borrowers` and `reservations` are additive: they are seeded and counted, but **must not** be
joined into the holding read path.

### 2.3 Go model types — `api/internal/model/holding.go`

Exactly four exported types. This file is 41 lines including the package comment.

```go
type Shelf struct {                   // CallNumber, Room, Wing, Bin — all omitempty
type Branch struct {                  // BranchID, Name, RegistrySymbol(omit), SystemID(omit)
type Loan struct {                    // Type, Level(omit), PolicyCode(omit),
                                      // EffectiveStart, EffectiveEnd(omit)
type Holding struct {                 // 14 fields; ends Shelf Shelf, Branch *Branch, Loans []Loan
```

`Holding` field order mirrors the `holdings` column order, then `Shelf`, then `*Branch`, then
`[]Loan`. JSON tags are lowerCamelCase; every optional scalar carries `,omitempty`; `shelf` and
`loans` do **not**.

`Loan` deliberately omits `BorrowerID` and `PickupBranch` from its JSON projection — borrower
identity is not exposed on the holding read path.

### 2.4 HTTP surface

| Method | Path | Handler | File |
|---|---|---|---|
| GET | `/healthz` | `handleHealth` | `server.go` |
| GET | `/readyz` | `handleReady` | `server.go` |
| GET | `/holdings/search` | `handleSearchHoldings` | `holdings.go` |
| GET | `/holdings/{holdingId}` | `handleGetHolding` | `holdings.go` |
| PATCH | `/holdings/{holdingId}` | `handlePatchHolding` | `holdings.go` |
| GET | `/holdings/{holdingId}/loans` | `handleGetLoans` | `holdings.go` |
| GET | `/holdings/{holdingId}/export/dc` | `handleExportDC` | `holdings.go` |
| GET | `/branches/{branchId}` | `handleGetBranch` | `branches.go` |
| GET | `/branches/{branchId}/holdings` | `handleBranchShelflist` | `branches.go` |
| POST | `/admin/ingest` | `handleAdminIngest` | `admin.go` |

**Search filters** — exactly six, three substring and three exact, at least one required:

| Query param | Match | Column |
|---|---|---|
| `title` | substring, case-insensitive (`LIKE '%…%'` on the uppercased needle) | `title` |
| `author` | substring, case-insensitive | `author` |
| `holdingId` | substring, case-insensitive (`UPPER(holding_id) LIKE ?`) | `holding_id` |
| `published` | exact | `published` |
| `branchId` | exact | `branch_id` |
| `shelfBin` | exact | `bin` |

Plus `limit` (default 50, max 200). `/branches/{id}/holdings` takes `limit` (default 50, max 500)
and `offset`.

**PATCH** accepts only `author`, `title`, `language`, `deskPhone`, and a nested `shelf` object
(`callNumber`, `room`, `wing`, `bin`). Every field is a pointer so "absent" is distinguishable
from "set to empty". Ingest-derived fields (`holdingId`, `branchId`, `published`, `materialCode`,
`circStatus`, `collectionCode`, `isbn`, `loans`) are read-only.

Validation rules — these regexes are themselves catalogued literals (P4):

| Field | Rule |
|---|---|
| `author`, `title` | trimmed, must be non-empty, stored uppercased |
| `language` | one of `EN`, `ES`, `FR`, `UND`, or empty |
| `deskPhone` | `^\d*$` (digits only; see §7.5) |
| `shelf.wing` | `^[A-Za-z]{2}$` or empty, stored uppercased |
| `shelf.bin` | `^\d{5}$` or empty |

Error envelope: `{"error":{"code":"…","message":"…"}}`. Codes in use: `not_found`, `bad_request`,
`unauthorized`, `db_error`, `not_seeded`, `internal`.

---

## 3. Reference measurements from the superseded corpus

Transcribed as shape. These are the numbers the file plan in §4 is derived from. Line counts were
taken with `wc -l`; brace depth is maximum unmatched `{` depth over the whole file.

| Shape | Lines | Depth | Types | Funcs | Exported symbols |
|---|---|---|---|---|---|
| daemon entrypoint | 97 | 3 | 0 | 3 | — (package `main`) |
| router + god-struct + health/ready | 115 | 5 | 1 | 7 | 3 |
| large multi-handler file | 375 | 4 | 3 | 8 | 0 (all methods on the struct) |
| secondary handler file | 92 | 3 | 0 | 2 | 0 |
| admin handler | 27 | 2 | 1 | 1 | 0 |
| error envelope helpers | 25 | 3 | 2 | 2 | 0 |
| interchange/export builder | 263 | 7 | 15 | 4 | 16 |
| record-ingest parser | 353 | 6 | 4 | 6 | 4 |
| JSON model types | 41 | 1 | 4 | 0 | 4 |
| store opener | 31 | 2 | 0 | 1 | 1 |
| embedded schema | 42 | — | 4 tables | — | — |
| handler test suite | 404 | 5 | 0 | 21 | 18 test funcs |
| interchange test suite | 167 | 4 | 0 | 4 | 3 test funcs |
| parser test suite | 74 | 2 | 0 | 2 | 2 test funcs |
| typed API client (TS) | 166 | 4 | 9 ifaces | 7 | 16 |
| dev auth curtain (TS) | 32 | 2 | 0 | 3 | 7 |
| root component (TSX) | 164 | 6 | 0 | 1 | 1 |
| detail component (TSX) | 110 | 5 | 1 | 1 | 1 |
| search form (TSX) | 118 | 3 | 1 | 1 | 1 |
| edit form (TSX) | 171 | 3 | 2 | 4 | 1 |
| results table (TSX) | 44 | 4 | 1 | 1 | 1 |
| auth gate (TSX) | 23 | 3 | 1 | 1 | 1 |
| login page (TSX) | 59 | 3 | 1 | 1 | 1 |
| gate test | 63 | 3 | — | — | — |
| client test | 197 | 6 | — | — | — |
| edit-form test | 101 | 4 | — | — | — |
| results-table test | 63 | 4 | — | — | — |
| search-form test | 56 | 3 | — | — | — |
| root component entry | 10 | 1 | — | — | — |
| test setup shim | 1 | 0 | — | — | — |
| stylesheet | 370 | — | — | — | — |
| SPA HTML shell | 12 | — | — | — | — |
| Vite config | 21 | 2 | — | — | — |
| SPA manifest | 28 | — | — | — | — |
| root manifest | 12 | — | — | — | — |
| Makefile | 53 | — | — | — | — |
| Go module file | 24 | — | 2 direct + 12 indirect | — | — |
| Go checksum file | 51 | — | — | — | — |
| README | 103 | — | — | — | — |

**Literal-count reference (soft targets).** A prior evaluation run recorded literal density on
four files: router 49 literals; large handler file 136 literals with a class histogram of
`{SQL: 6, MSG: 102, PATH: 7, EMPTY: 21}`; typed client 18; detail component 19. Reproduce these
approximately. The **`SQL: 6` count is a hard target** — see P5/P2 in §5.

---

## 4. File-by-file build plan

Paths are relative to this directory (`corpus/stacks/`). **Line counts marked ✱ are gated at
±5.** Others are derived and should land within ±10.

### 4.1 Go service

| Path | Lines | Required exported symbols | Pathologies |
|---|---|---|---|
| `api/go.mod` | 24 | `module stacks` | — |
| `api/go.sum` | ~51 | — | committed (§7.3) |
| `api/cmd/stacksd/main.go` | ✱105 | `main` | P4 |
| `api/internal/api/server.go` | ✱115 | `Server`, `NewServer`, `(*Server).Handler` | **P1, P2, P4** |
| `api/internal/api/holdings.go` | ✱375 | none (all methods on `*Server`) | **P3, P4, P5, P8, P9** |
| `api/internal/api/branches.go` | 98 | none | P3, P9 |
| `api/internal/api/admin.go` | 27 | none | P3, P4 |
| `api/internal/api/errors.go` | 25 | none | — |
| `api/internal/api/api_test.go` | 404 | 18 `Test…` funcs | — |
| `api/internal/ingest/marc21.go` | ✱353 | `Counts`, `Parse`, `EnsureSeeded`, `FromFile` | **P6, P7** |
| `api/internal/ingest/marc21_test.go` | 74 | 2 `Test…` funcs | — |
| `api/internal/interchange/dublincore.go` | ✱263 | 15 types + `BuildRecordSet` | P4 |
| `api/internal/interchange/dublincore_test.go` | 167 | 3 `Test…` funcs | — |
| `api/internal/model/holding.go` | ✱41 | `Shelf`, `Branch`, `Loan`, `Holding` | — |
| `api/internal/store/store.go` | 31 | `Open` | **P3** (by omission) |
| `api/internal/store/schema.sql` | 62 | 6 tables, 4 indexes | — |
| `api/testdata/catalog_seed.mrk` | ~295 (soft) | — | §6 |

`api/internal/api/server.go` symbol inventory, in order: `Server` struct (5 fields), `corsAllowList()`,
`corsMiddleware()`, `NewServer()`, `(*Server).Handler()`, `(*Server).handleHealth`,
`(*Server).handleReady`, `(*Server).serverError`.

`api/internal/api/holdings.go` symbol inventory, in order: `(*Server).loadHolding`,
`(*Server).loadLoans`, `(*Server).handleGetHolding`, `(*Server).handleGetLoans`,
`holdingSummary` struct, `(*Server).handleSearchHoldings`, `holdingPatch` struct, `shelfPatch`
struct, the three compiled regexes, `(*holdingPatch).validateAndBuild`,
`(*Server).handlePatchHolding`, `(*Server).handleExportDC`. Eight functions, three types.

`api/internal/interchange/dublincore.go` type inventory (15, in order): `RecordSet`, `SetEntry`,
`Resource` (an `any` alias with a comment explaining the tagged-union-ish approach), `Identifier`,
`TitleStatement`, `ContactPoint`, `ShelfLocation`, `Reference`, `Record`, `Collection`, `Period`,
`Coding`, `CodedTerm`, `AvailabilityClass`, `Availability`. Four functions: `BuildRecordSet`,
`mapLanguage`, `idOrIndex`, `itoa` (a hand-rolled integer formatter — deliberately reimplemented
rather than importing `strconv`; that reimplementation is itself part of the corpus's texture).

### 4.2 SPA

| Path | Lines | Required exports | Pathologies |
|---|---|---|---|
| `app/package.json` | 28 | — | — |
| `app/package-lock.json` | generated | — | committed (§7.3) |
| `app/tsconfig.json` | 25 | — | **standalone — §7.3** |
| `app/vite.config.ts` | 21 | — | P4 |
| `app/index.html` | 12 | — | — |
| `app/src/main.tsx` | 10 | — | — |
| `app/src/App.tsx` | 164 | `App` | P4 |
| `app/src/api/client.ts` | ✱166 | 9 interfaces, `ApiError`, `buildSearchUrl`, `searchHoldings`, `getHolding`, `patchHolding`, `dcExportUrl`, `hasAnyFilter` | **P4** |
| `app/src/auth.ts` | ✱32 | `DEV_USER`, `DEV_PASS`, `AUTH_KEY`, `AUTH_EVENT`, `isAuthenticated`, `login`, `logout` | P4, §7.6 |
| `app/src/styles.css` | 370 | — | — |
| `app/src/test-setup.ts` | 1 | — | — |
| `app/src/components/HoldingDetail.tsx` | ✱110 | `HoldingDetail` | P4 |
| `app/src/components/SearchForm.tsx` | ✱118 | `SearchForm` | P4 |
| `app/src/components/HoldingEditForm.tsx` | 171 | `HoldingEditForm` | P4, P9 |
| `app/src/components/ResultsTable.tsx` | 44 | `ResultsTable` | — |
| `app/src/components/AuthGate.tsx` | 23 | `AuthGate` | — |
| `app/src/components/LoginPage.tsx` | 59 | `LoginPage` | §7.6 |
| `app/src/__tests__/AuthGate.test.tsx` | 63 | — | — |
| `app/src/__tests__/client.test.ts` | 197 | — | — |
| `app/src/__tests__/HoldingEditForm.test.tsx` | 101 | — | — |
| `app/src/__tests__/ResultsTable.test.tsx` | 63 | — | — |
| `app/src/__tests__/SearchForm.test.tsx` | 56 | — | — |

`client.ts` interface inventory (9, in order): `Shelf`, `Branch`, `Loan`, `Holding`,
`HoldingSummary`, `SearchFilters`, `SearchResponse`, `ShelfPatch`, `HoldingPatch`. Plus the
`ApiError` class and six exported functions. `const BASE = "/api"`.

`HoldingEditForm.tsx` carries an internal `FormState` interface with 8 flat string fields, plus
`initialState`, `validate`, `buildPatch` module-level helpers — `validate` restates the Go
validator's rules in TypeScript, with a comment naming the Go file it mirrors. That duplication is
P9's client-side arm.

### 4.3 Root

| Path | Lines | Notes |
|---|---|---|
| `Makefile` | 53 | targets `run build test tidy clean smoke ui ui-test dev`; no path escapes the tree |
| `package.json` | 12 | root workspace runner; `concurrently` only |
| `package-lock.json` | generated | committed (§7.3) |
| `README.md` | ~103 | must not list any external prerequisite (§7.2) |
| `PATHOLOGY.md` | see §8 | the defect catalogue |
| `.gitignore` | ~10 | ignores `api/data/`, `api/bin/`, `node_modules/`, `dist/`, `*.tsbuildinfo`. **Never** ignores `api/testdata/`, `go.sum`, or lockfiles. |

---

## 5. Pathology inventory

Seven required (P1–P7) plus two corroborating (P8–P9). Every entry states the **shape** and the
**required manifestation** in this domain. `PATHOLOGY.md` (§8) is the machine-facing index; this
section is the rationale.

### P1 — God-struct: transport, persistence, config, and logging in one type

**Shape.** A single struct, constructed once at boot, holds a raw database handle
(`*sql.DB`) alongside a structured logger, two scalar config strings, and the assembled
`http.Handler`. Every request handler is a method on it, so every handler has ambient access to
every concern. Five fields, three distinct responsibilities.

**Manifestation.** `api/internal/api/server.go`:

```go
type Server struct {
	db         *sql.DB
	logger     *slog.Logger
	seedPath   string
	adminToken string
	router     http.Handler
}
```

`NewServer(db *sql.DB, logger *slog.Logger, seedPath, adminToken string) *Server` builds the chi
router inside the constructor and assigns it to `s.router`. `(*Server).Handler()` returns it.
**The `db` field must be the raw `*sql.DB`, not an interface and not a repository type** — that is
the whole defect.

### P2 — Inline SQL inside a readiness handler

**Shape.** A liveness/readiness endpoint that runs a raw aggregate query against the struct-owned
database handle in the handler body, with no repository call between HTTP and SQL. It is the
smallest possible demonstration of P1's consequence, and it lives in the *smallest* file, which is
why it is catalogued separately.

**Manifestation.** `(*Server).handleReady` in `server.go`:

```go
var n int
if err := s.db.QueryRowContext(r.Context(), `SELECT count(*) FROM holdings`).Scan(&n); err != nil {
	writeError(w, http.StatusServiceUnavailable, "db_error", err.Error())
	return
}
if n == 0 {
	writeError(w, http.StatusServiceUnavailable, "not_seeded", "no holdings loaded")
	return
}
writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "holdings": n})
```

The query **must** be a raw backtick string literal containing `SELECT count(*)`. Exactly one such
literal in `server.go`.

### P3 — Layering violation: handlers reach past the store package to the DB

**Shape.** A `store` package exists and is the nominal persistence layer, but it exposes exactly
one function — `Open(path string) (*sql.DB, error)` — which applies pragmas and executes an
embedded schema, then hands the caller the raw handle. There are no queries in `store`. Every
query in the program is written inline in an HTTP handler or an ingest function. The layer is
present in the directory structure and absent in the call graph.

**Manifestation.** `api/internal/store/store.go` is 31 lines, has exactly one exported symbol
(`Open`), embeds `schema.sql` via `//go:embed`, sets `db.SetMaxOpenConns(1)`, and contains **zero
`SELECT`/`INSERT`/`UPDATE` statements outside the embedded schema**. All queries live in
`holdings.go`, `branches.go`, `server.go`, and `ingest/marc21.go`.

### P4 — Domain-leaking string literals scattered across layers

**Shape.** Configuration, routing, error text, and protocol constants are inline literals at their
use sites rather than named constants, so the program's subject matter is reconstructible from the
strings alone. Four sub-classes, all required:

| Class | Required instances |
|---|---|
| **Env-var names** | `STACKS_CORS_ORIGINS` (read via `os.Getenv` inside `corsAllowList()`, comma-split, empty means the middleware is a no-op); `STACKS_ADDR`, `STACKS_DB_PATH`, `STACKS_SEED_PATH`, `STACKS_ADMIN_TOKEN` (read in `main.go` through an `envOr(key, fallback string) string` helper) |
| **URL path constants** | `/healthz`, `/readyz`, `/holdings`, `/search`, `/{holdingId}`, `/loans`, `/export/dc`, `/branches`, `/{branchId}`, `/admin/ingest` in `NewServer`; `const BASE = "/api"` and the template-built paths in `client.ts` |
| **Error messages** | `"holding not found"`, `"branch not found"`, `"no holdings loaded"`, `"missing or invalid admin token"`, `"internal server error"`, `"Content-Type must be application/json"`, `"request body had no updatable fields"`, `"at least one filter required (title, author, holdingId, published, branchId, shelfBin)"`, `"wing must be a 2-letter code or empty"`, `"bin must be 5 digits or empty"`, `"deskPhone must be digits only"`, `"language must be one of EN, ES, FR, UND, or empty"` |
| **Protocol/MIME magic strings** | `"application/json"`, `"application/dc+json; charset=utf-8"`, the six CORS header names, `"GET, POST, PATCH, OPTIONS"`, `"Accept, Content-Type, X-Admin-Token"`, `"X-Request-Id"`, `"300"`, and the bare `method: "PATCH"` in `client.ts` |

The MIME strings and the HTTP-method literal are specifically required because the evaluation
recorded them as a **misclassification** case: `application/json` matches a path-shaped pattern
and gets tagged as a path, and bare method names are indistinguishable from prose. Removing them
removes a documented finding.

### P5 — The large file: SQL assembled by string concatenation across optional filters

**Shape.** One handler file materially larger than every other file in its package, whose bulk
comes from a search handler that appends `WHERE` fragments to a `[]string` and arguments to a
`[]any` across N independent optional-filter branches, then joins the fragments into a query
string, and from a patch handler that does the same thing for a `SET` clause via `fmt.Sprintf`.

**Manifestation.** `api/internal/api/holdings.go`, 375 lines.

- `handleSearchHoldings` builds `conds []string` / `args []any` across **six** `if v :=
  strings.TrimSpace(q.Get("…")); v != ""` blocks, errors with `bad_request` when `len(conds) == 0`,
  clamps `limit` to `0 < n <= 200`, then:
  ```go
  sqlStr := `SELECT holding_id, branch_id, author, title, published,
                    COALESCE(room,''), COALESCE(wing,''), COALESCE(bin,'')
             FROM holdings WHERE ` + strings.Join(conds, " AND ") +
      ` ORDER BY title, author LIMIT ?`
  ```
- `(*holdingPatch).validateAndBuild` returns `(setParts []string, args []any, badReq string)` and
  uses a local `set := func(col string, val any) { … }` closure to append to both slices.
- `handlePatchHolding` then does
  `fmt.Sprintf("UPDATE holdings SET %s WHERE holding_id = ?", strings.Join(setParts, ", "))`.

**Hard target: exactly six raw-SQL string literals in this file**, matching the recorded histogram.
They are: the `loadHolding` join query, the `loadLoans` query, the existence probe in
`handleGetLoans`, the search query, the existence probe in `handlePatchHolding`, and the
`fmt.Sprintf` UPDATE template. Both the search `WHERE` fragment and the `ORDER BY`/`LIMIT` tail
belong to the same literal via `+` concatenation.

Note the search handler also carries a three-line comment explaining that stored text is
uppercased on ingest so `LIKE` is effectively case-insensitive, and that at ~24 rows a scan is
fine but FTS5 would be the move at 10k+. That comment is part of the corpus's texture; keep it.

### P6 — Deep nesting with a switch inside an if, on magic-string discriminants

**Shape.** A line-oriented record parser whose main loop is a large `switch` on a tag token, where
individual arms open an `if` guard and then open a **second `switch`** on a sub-discriminant, with
bare string constants as the case labels and length-guarded positional indexing into a slice of
parsed fragments. Maximum brace depth ≥ 6.

**Manifestation.** `api/internal/ingest/marc21.go`. Three arms must carry a nested switch:

1. The `"110"` arm switches on the relator subfield to decide whether the line names the system or
   a branch.
2. The `"852"` arm switches on subfield code to fan out into branch id / room / wing / call number
   / bin.
3. The `"583"` arm — the required deep one:
   ```go
   case "583":
       if curLoan != nil && len(sfs) >= 3 && sub(sfs, 'b') == "D8" {
           switch sub(sfs, 'a') {
           case "LOANSTART":
               curLoan.EffectiveStart = isoDate(sub(sfs, 'c'))
           case "LOANEND":
               curLoan.EffectiveEnd = isoDate(sub(sfs, 'c'))
           }
       }
   ```
   `"D8"`, `"LOANSTART"`, `"LOANEND"` are the magic-string discriminants. Do not replace them with
   named constants.

Additionally required, as part of P6's texture: **mixed subfield-access idiom.** Some arms use the
keyed helper `sub(sfs, 'a')`; others index positionally with a length guard
(`if len(sfs) > 1 { cur.DeskPhone = sfs[1].Value }` in the `"270"` arm, and `sfs[0]` / `sfs[1]` in
the `"245"` arm). The inconsistency is deliberate.

### P7 — Closures over mutable outer state, flushed across switch arms

**Shape.** The parse function declares record-accumulator pointers in its own scope, then defines
zero-argument `flush…()` closures that read and write those pointers. Both the closures and the
raw pointers are then touched from inside multiple `case` arms of the loop, and the closures are
also called once more after the loop terminates. Nothing is passed as an argument; all coupling is
through captured variables.

**Manifestation.** In `parseBytes` (or equivalently the line-loop function) of `marc21.go`:

```go
pf := &parsedFile{}
var cur *parsedHolding
var curLoan *parsedLoan

flushLoan := func() {
	if cur != nil && curLoan != nil {
		cur.Loans = append(cur.Loans, *curLoan)
		curLoan = nil
	}
}
flushRecord := func() {
	flushLoan()
	if cur != nil {
		pf.Holdings = append(pf.Holdings, *cur)
		cur = nil
	}
}
```

Required call sites: `flushRecord()` from the `"LDR"` arm and from the blank-line branch;
`flushLoan()` from the `"876"` arm; `flushRecord()` once after the loop. `curLoan` must be read or
written from at least three different `case` arms (`"876"`, `"583"`, and the policy-code path).
This is the defect the evaluation reported as still legible after identifier substitution — the
zero-argument calls plus the repeated non-local variable are the signature.

### P8 — Wide positional `Scan` (corroborating)

**Shape.** A loader function issues a two-table join and binds **19 columns positionally** into a
single `Scan` call across four physical lines, with `COALESCE(col,'')` wrapping every nullable
column. Column order in the query and argument order in the `Scan` are coupled by nothing but
convention.

**Manifestation.** `(*Server).loadHolding` in `holdings.go`. 15 `holdings` columns + 4 `branches`
columns. The query is built with an optional ` AND h.branch_id = ?` appended when the caller
passes a non-empty branch id, and `args := []any{holdingID}` grown accordingly.

### P9 — Copy-pasted `sql.ErrNoRows` ladder (corroborating)

**Shape.** The identical four-line error-handling block

```go
if errors.Is(err, sql.ErrNoRows) {
	writeError(w, http.StatusNotFound, "not_found", "holding not found")
	return
}
if err != nil {
	s.serverError(w, err)
	return
}
```

repeated verbatim across four handlers, with no extracted helper.

**Manifestation.** `handleGetHolding`, `handleGetLoans`, `handlePatchHolding`, `handleExportDC` in
`holdings.go`; the branch-scoped variant (`"branch not found"`) once in `handleGetBranch`. The
client-side arm is `HoldingEditForm.tsx`'s `validate()` restating the Go validator.

---

## 6. Ingest format: MARCMaker (`.mrk`)

The record-ingest parser consumes **MARCMaker**, a real, documented, line-oriented serialization of
MARC 21 records. This replaces the superseded corpus's segment-delimited interchange format with
one that is public, self-describing, and native to this domain.

### 6.1 Grammar the parser handles

```
file        := record ( BLANK record )* BLANK?
record      := leader-line field-line+
leader-line := "=LDR" SP SP leader-data NL
field-line  := "=" tag SP SP field-body NL
tag         := DIGIT DIGIT DIGIT | "LDR"
field-body  := control-data                      ; tags 001–009
             | ind ind subfield+                 ; tags 010–999
ind         := "\" | DIGIT | LETTER              ; "\" denotes a blank indicator
subfield    := "$" code data
code        := lowercase-letter | digit
```

Rules the parser must implement, and no more:

1. Every line begins with `=`. Any line not beginning with `=` that is non-blank is skipped.
2. A **blank line terminates the current record** — this is the analogue of an explicit end-of-record
   marker, and it calls `flushRecord()`.
3. `=LDR` also calls `flushRecord()` and starts a new one. Belt and braces; both paths are exercised.
4. Tags `001`–`009` are **control fields**: no indicators, no subfields — the body after the two
   spaces is the value verbatim.
5. For data fields, the **first two characters after the two spaces are the indicators.**
   `\` means blank. The parser reads them but only the `110` arm uses one.
6. Subfields are introduced by `$` followed by exactly one code character. The value runs to the
   next `$` or end of line.
7. A literal dollar sign in data is escaped `{dollar}`; the parser un-escapes it. At least one seed
   record must exercise this.
8. Dates arrive as `YYYYMMDD` and are converted by `isoDate(d8 string) string`, which returns its
   input unchanged if `len(d8) != 8`.

The parser's doc comment must state plainly that it is **a deliberately minimal reader scoped to
the shape our own seed generator emits — not a general-purpose MARC implementation** — and list
the simplifications: one system record, one branch per file, and a local profile for `=583`
and `=876` subfield use.

### 6.2 Tag arms — required `switch` cases

| Tag | Role | Notes |
|---|---|---|
| `LDR` | `flushRecord()`; `cur = &parsedHolding{}`; read the record-status and material byte from the leader into `cur.MaterialCode` | record boundary |
| `001` | control field → `cur.HoldingID` | no subfields |
| `010` | `$a` → `pf.CollectionControlNumber`, first non-empty wins | LCCN source |
| `020` | `$a` → `cur.ISBN` | |
| `035` | `$a` → `pf.RegistrySymbol`, first non-empty wins | OCLC source |
| `100` | `$a` → `cur.Author` (uppercased on insert) | length-guarded |
| `245` | positional `sfs[0]` → `cur.Title`, `sfs[1]` → `cur.Statement` | positional idiom |
| `260`, `264` | shared arm; `$c` → `cur.Published` via `isoDate`; `$b` → `cur.Imprint` | two labels, one body |
| `270` | positional `sfs[1]` → `cur.DeskPhone` | positional idiom |
| `590` | `$a` → `cur.CircStatus` | |
| `650` | `$a` → `cur.CollectionCode` | |
| `852` | **nested switch on subfield code** → `$a` branch id (first wins → `pf.BranchID`), `$b` room, `$c` wing, `$h`+`$i` call number, `$j` bin | **P6** |
| `876` | `flushLoan()`; new `curLoan`; `$h` type, `$j` level, `$x` policy code, `$3` borrower id | **P7** |
| `583` | **switch inside if** on `$a` with `$b == "D8"` guard; also handles `$a == "HOLDPLACED"` → reservation | **P6** |
| `110` | **nested switch on `$4` relator**: `sys` → system, `brn` → branch | **P6** |

### 6.3 Seed file — `api/testdata/catalog_seed.mrk`

The block below is the **normative head of the seed file.** It is copied verbatim into
`api/testdata/catalog_seed.mrk` and then extended, following the same pattern, to **24
bibliographic records** distributed across the three branches. All works are pre-1929 and all
listed authors died more than 95 years ago (§7.4).

```
=LDR  00512cai a2200157 a 4500
=001  stk00000000
=010  \\$alcc00000001
=035  \\$a(OCoLC)ocm00000001
=110  2\$aOakhurst County Library System$4sys$0STK-SYS-001
=110  2\$aCentral Branch$4brn$0BR-CENTRAL
=852  \\$aBR-CENTRAL$bMain Reading Room$cNW

=LDR  00714nam a2200205 a 4500
=001  stk00000001
=010  \\$alcc00000002
=020  \\$a978-0-00-000001-9
=035  \\$a(OCoLC)ocm00000002
=100  1\$aDickens, Charles,$d1812-1870.
=245  14$aA tale of two cities /$cCharles Dickens.
=260  \\$aLondon :$bChapman & Hall,$c18590101.
=590  \\$aON-SHELF
=650  \0$aHistorical fiction.
=852  \\$aBR-CENTRAL$bMain Reading Room$cNW$hPR4571$i.A1 1859$j01420
=270  \\$aCirculation desk$k+1-555-0101
=876  \\$aitem-1$hLOAN$jSTD$xCIRC-21D$3BRW-0000001
=583  \\$aLOANSTART$bD8$c20260104
=583  \\$aLOANEND$bD8$c20260125

=LDR  00698nam a2200193 a 4500
=001  stk00000002
=020  \\$a978-0-00-000002-9
=035  \\$a(OCoLC)ocm00000003
=100  1\$aAusten, Jane,$d1775-1817.
=245  10$aPride and prejudice /$cJane Austen.
=260  \\$aLondon :$bT. Egerton,$c18130128.
=590  \\$aON-LOAN
=650  \0$aDomestic fiction.
=852  \\$aBR-EASTSIDE$bFiction Alcove$cSE$hPR4034$i.P7 1813$j02310
=270  \\$aCirculation desk$k+1-555-0102
=876  \\$aitem-2$hLOAN$jEXT$xCIRC-42D$3BRW-0000002
=583  \\$aLOANSTART$bD8$c20260110
=583  \\$aHOLDPLACED$bD8$c20260114$3BRW-0000005

=LDR  00731nam a2200201 a 4500
=001  stk00000003
=010  \\$alcc00000004
=020  \\$a978-0-00-000003-9
=035  \\$a(OCoLC)ocm00000004
=100  1\$aMelville, Herman,$d1819-1891.
=245  10$aMoby-Dick ; or, The whale /$cHerman Melville.
=264  \1$aNew York :$bHarper & Brothers,$c18511114.
=590  \\$aON-SHELF
=650  \0$aSea stories.
=852  \\$aBR-NORTHGATE$bAmerican Literature$cNE$hPS2384$i.M6 1851$j03105
=876  \\$aitem-3$hLOAN$jSTD$xCIRC-21D$3BRW-0000003
=583  \\$aLOANSTART$bD8$c20251201
=583  \\$aLOANEND$bD8$c20251222

=LDR  00688nam a2200189 a 4500
=001  stk00000004
=020  \\$a978-0-00-000004-9
=035  \\$a(OCoLC)ocm00000005
=100  1\$aShelley, Mary Wollstonecraft,$d1797-1851.
=245  10$aFrankenstein ; or, The modern Prometheus /$cMary Wollstonecraft Shelley.
=260  \\$aLondon :$bLackington, Hughes, Harding, Mavor {dollar}amp; Jones,$c18180101.
=590  \\$aIN-REPAIR
=650  \0$aGothic fiction.
=852  \\$aBR-CENTRAL$bSpecial Collections$cSW$hPR5397$i.F7 1818$j01455
=270  \\$aCirculation desk$k+1-555-0103
=876  \\$aitem-4$hREF$jSHORT$xREF-00D$3BRW-0000004

=LDR  00705nam a2200197 a 4500
=001  stk00000005
=010  \\$alcc00000006
=020  \\$a978-0-00-000005-9
=035  \\$a(OCoLC)ocm00000006
=100  1\$aStoker, Bram,$d1847-1912.
=245  10$aDracula /$cBram Stoker.
=264  \1$aWestminster :$bArchibald Constable and Company,$c18970526.
=590  \\$aON-LOAN
=650  \0$aHorror tales.
=852  \\$aBR-EASTSIDE$bFiction Alcove$cSE$hPR6037$i.T617 1897$j02388
=876  \\$aitem-5$hILL$jSTD$xILL-14D$3BRW-0000006
=583  \\$aLOANSTART$bD8$c20260118
=583  \\$aLOANEND$bD8$c20260201

=LDR  00742nam a2200209 a 4500
=001  stk00000006
=020  \\$a978-0-00-000006-9
=035  \\$a(OCoLC)ocm00000007
=100  1\$aVerne, Jules,$d1828-1905.
=245  10$aTwenty thousand leagues under the seas /$cJules Verne.
=260  \\$aParis :$bPierre-Jules Hetzel,$c18700620.
=590  \\$aON-SHELF
=650  \0$aScience fiction.
=852  \\$aBR-NORTHGATE$bWorld Literature$cNE$hPQ2469$i.V5 1870$j03212
=270  \\$aCirculation desk$k+1-555-0104
=876  \\$aitem-6$hLOAN$jSTD$xCIRC-21D$3BRW-0000007
=583  \\$aLOANSTART$bD8$c20260105
=583  \\$aLOANEND$bD8$c20260126
```

Records 7–24 continue the pattern with (at minimum) Brontë, *Wuthering Heights*, 1847;
Hawthorne, *The scarlet letter*, 1850; Carroll, *Alice's adventures in wonderland*, 1865;
Swift, *Gulliver's travels*, 1726; Shakespeare, *Hamlet*, 1603; Homer (trans. pre-1929),
*The odyssey*; Cervantes, *Don Quixote*, 1605; Poe, *Tales of mystery and imagination*, 1908;
Wollstonecraft, *A vindication of the rights of woman*, 1792; Thoreau, *Walden*, 1854; Twain,
*The adventures of Tom Sawyer*, 1876; Doyle, *A study in scarlet*, 1887 (author d. 1930).
Each gets the next sequential control number, OCLC number, and ISBN.

### 6.4 What the parser writes

`FromFile(ctx, db, path)` opens a transaction, `DELETE`s all six tables in dependency order
(`reservations`, `loans`, `borrowers`, `holdings`, `branches`, `systems`), inserts the system row
(if `pf.SystemID != ""`), the branch row, then loops holdings — **skipping any parsed record whose
`HoldingID` is empty**, which is how the leading collection-level record is discarded — inserting
each holding, its loans (skipping any loan with an empty `Type` or empty `EffectiveStart`), its
borrowers (`INSERT OR IGNORE`), and its reservations.

`Counts` is a six-field struct with JSON tags: `systems`, `branches`, `holdings`, `loans`,
`borrowers`, `reservations`.

`EnsureSeeded(ctx, db, path) (bool, Counts, error)` runs `SELECT count(*) FROM holdings` first and
returns `(false, Counts{}, nil)` when the count is non-zero.

A `nullStr(s string) any` helper returns `nil` for empty strings so `NULL` reaches the column.

---

## 7. Hard requirements

### 7.1 Identifier systems — exactly five

`dublincore.go` emits URN-namespaced identifiers. There are **exactly five systems**, no more:

| URN | Carried on | Presence |
|---|---|---|
| `urn:stacks:holding-id` | `Record` | **always** — the first entry in `Record.Identifier` |
| `urn:isbn:` | `Record` | conditional on `h.ISBN != ""` |
| `urn:oclc:` | `Collection` | conditional on `b.RegistrySymbol != ""` |
| `urn:lccn:` | `Collection` | conditional on `b.SystemID != ""` |
| `urn:stacks:branch-id` | `Availability.Kind.Coding[0].System` | always, code = the loan's pickup branch |

Struct shape:

```go
type Identifier struct {
	System string `json:"system,omitempty"`
	Value  string `json:"value,omitempty"`
}
```

**The omit-if-empty ladder** in `BuildRecordSet(h model.Holding) RecordSet`, in this order — this
sequence of conditional appends is itself a measured shape and must be reproduced structurally:

1. Build `rec := Record{RecordType: "Record", ID: h.HoldingID, Identifier: []Identifier{{System:
   "urn:stacks:holding-id", Value: h.HoldingID}}, Title: …, Creator: …, Language:
   mapLanguage(h.Language), Date: h.Published}`.
2. `if h.ISBN != ""` → append `Identifier{System: "urn:isbn:", Value: h.ISBN}`.
3. `if h.DeskPhone != ""` → append `ContactPoint{System: "phone", Value: h.DeskPhone}`.
4. Assemble `loc := ShelfLocation{Room:…, Wing:…, Bin:…}`; `if h.Shelf.CallNumber != ""` → set
   `loc.Line = []string{h.Shelf.CallNumber}`; then
   `if loc.Line != nil || loc.Room != "" || loc.Wing != "" || loc.Bin != ""` → set
   `rec.Location = []ShelfLocation{loc}`.
5. `entries := []SetEntry{{FullURL: "Record/" + h.HoldingID, Resource: rec}}`.
6. `if h.Branch != nil` → build `Collection`; `if RegistrySymbol != ""` → append `urn:oclc:`;
   `if SystemID != ""` → append `urn:lccn:`; append the entry.
7. `for i, l := range h.Loans` → build `Availability` with
   `Kind: CodedTerm{Coding: []Coding{{System: "urn:stacks:branch-id", Code: l.PickupBranch}},
   Text: l.Type}`; `if l.Level != ""` → append `AvailabilityClass`; `if l.PolicyCode != ""` →
   append another; `if h.Branch != nil` → set `Custodian`; append the entry.
8. Return `RecordSet{RecordType: "RecordSet", Type: "collection", Entry: entries}`.

Every field on every type in this file carries `,omitempty` except `RecordType`, `Type`, `ID`,
`Status`, and `Holder`. `mapLanguage` maps `EN`/`en`→`eng`, `ES`/`es`→`spa`, `FR`/`fr`→`fre`,
`UND`/`und`→`und`, `""`→`""`, default→`mul`.

The package doc comment states that this is a **one-way export** intended for download, not for
posting back to any metadata registry.

### 7.2 Self-containment — the anti-pattern this corpus exists to not repeat

The superseded corpus was **not clonable**. Grepping it for `\.\./\.\./`, `TestData`, and
`portRegistry` produced six escapes above its own root plus one registry dependency. Recorded here
as the anti-pattern, described by shape and location only:

| # | Site | What it did |
|---|---|---|
| 1 | root `Makefile`, line 3 | seed-path variable defaulted to `../../TestData/<seed file>` |
| 2 | daemon `main.go`, line 34 | `envOr` fallback for the seed path was `../TestData/<seed file>` |
| 3 | ingest test, line 10 | `const seedPath = "../../../../TestData/<seed file>"` |
| 4 | handler test, line 36 | same constant, same four-level escape |
| 5 | `README.md`, line 16 | listed "`TestData/<seed file>` at the repo parent" as a **prerequisite** |
| 6 | SPA `tsconfig.json`, line 2 | `"extends": "../../tsconfig.base.json"` — the whole file was 4 lines and none of the compiler options were local |
| 7 | sibling fixture `README.md`, line 106 | a "Ports" section stating its two ports were reserved in `../portRegistry.txt` — the allocation table lived outside the tree |

Consequence: a public clone had no seed data, no TypeScript compiler options, and no way to know
which ports were safe. **Every one of these is forbidden in the replacement.** Required instead:

| Requirement | Detail |
|---|---|
| Seed lives inside the tree | `api/testdata/catalog_seed.mrk`, committed. `main.go` default is `./testdata/catalog_seed.mrk`; Go tests use `const seedPath = "../../testdata/catalog_seed.mrk"` — at most two levels, never leaving `api/`. |
| Listen address is hardcoded | Default `":8300"`, written as a literal in `main.go`'s `envOr("STACKS_ADDR", ":8300")`. **No registry file, no lookup, no external allocation table.** SPA dev server: Vite on `5300` with `strictPort: true`, proxying `/api` → `http://localhost:8300`. |
| Standalone `tsconfig.json` | `app/tsconfig.json` has **no `extends` key**. All compiler options are inline: `target: ES2020`, `useDefineForClassFields`, `lib: [ES2020, DOM, DOM.Iterable]`, `module: ESNext`, `skipLibCheck`, `moduleResolution: bundler`, `allowImportingTsExtensions`, `resolveJsonModule`, `isolatedModules`, `moduleDetection: force`, `noEmit`, `jsx: react-jsx`, `strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, plus `"include": ["src"]`. 25 lines. |
| Zero parent references | `grep -rn '\.\./\.\.' .` over the generated tree must return **nothing** outside `node_modules/`. |
| README lists no external prerequisite | Only Go 1.22+ and Node 20+. |

### 7.3 Dependencies and lockfiles

Go module path is the bare **`stacks`** — no hosting-provider prefix, no organisation segment.
Imports read `stacks/internal/api`, `stacks/internal/ingest`, `stacks/internal/store`,
`stacks/internal/model`, `stacks/internal/interchange`. This is deliberate: an org-prefixed module
path is itself a vocabulary leak.

Pinned direct dependencies, exact versions:

```
github.com/go-chi/chi/v5 v5.1.0
modernc.org/sqlite       v1.34.1
```

`modernc.org/sqlite` is the **pure-Go** driver — no cgo, so `CGO_ENABLED=0` builds work and no C
toolchain is needed. Import it for side effects: `_ "modernc.org/sqlite"`, opened with driver name
`"sqlite"`.

SPA dependencies: `react` ^18.3.1, `react-dom` ^18.3.1; dev: `@testing-library/react` ^16.0.1,
`@testing-library/user-event` ^14.5.2, `@types/react` ^18.3.12, `@types/react-dom` ^18.3.1,
`@vitejs/plugin-react` ^4.3.3, `happy-dom` ^15.7.4, `typescript` ^5.6.3, `vite` ^5.4.10,
`vitest` ^2.1.4. Root dev dependency: `concurrently` ^9.1.0.

**Committed, never gitignored:** `api/go.sum`, `package-lock.json` (root), `app/package-lock.json`,
`api/testdata/catalog_seed.mrk`.

### 7.4 Fabricated-data conventions

| Datum | Rule |
|---|---|
| Works | Public domain, **published pre-1929**, by authors dead **more than 95 years**. Verify both before adding a title. |
| ISBNs | Drawn from the `978-0-00-0000NN-x` block with **deliberately invalid check digits** — the final digit is fixed at `9` regardless of the mod-10 result, so no generated string can collide with an assigned ISBN. Never compute a valid check digit. |
| OCLC numbers | Sequential fictitious `ocm00000001`, `ocm00000002`, … carried in `035 $a` as `(OCoLC)ocm……`. |
| Control numbers | Sequential fictitious `stk00000001`, `stk00000002`, … in `001`. The collection-level record uses `stk00000000`. |
| LCCN values | Sequential fictitious `lcc00000001`, … Structurally **not** a valid LCCN. |
| Borrowers | Opaque `BRW-0000001` … `BRW-0000012` only. **No names, no addresses, no dates of birth, no contact data, anywhere in the tree** — not in the seed, not in tests, not in fixtures, not in the SPA. The `borrowers` table has exactly two columns for this reason. |
| Branches | Exactly three: `BR-CENTRAL`, `BR-EASTSIDE`, `BR-NORTHGATE`. System: `STK-SYS-001`, "Oakhurst County Library System" (invented). |
| Call numbers | Dewey- or LC-style, e.g. `823.8 D548d`, `PR4571 .A1 1859`. Plausible, not authoritative. |
| Phone literals | Only from the reserved `+1-555-01xx` block. The `.mrk` carries `+1-555-0101`; ingest normalises to digits (`15550101`); the API, DB, and UI carry the digits-only form, which is what the `^\d*$` validator sees. |
| Email literals | Only `<local>@example.org`. |
| Shelf bins | Five-digit codes, e.g. `01420`. |
| Wings | Two-letter codes: `NW`, `NE`, `SW`, `SE`. |

### 7.5 Text normalisation

`title` and `author` are **stored uppercased** by both ingest and PATCH. The search handler
uppercases the needle before `LIKE`, which is what makes substring matching effectively
case-insensitive. `HoldingEditForm.tsx`'s `buildPatch` compares its trimmed-uppercased form value
against the stored value to decide whether to include a field in the patch — the same asymmetry the
superseded corpus had, and one the evaluation exercised.

### 7.6 Development credentials

The SPA has a **dev-only login curtain**, not authentication: hardcoded `dev` / `dev`, a
`sessionStorage` flag, a `window` event to broadcast changes, and **no server middleware** — the Go
API is unauthenticated and anything talking directly to `:8300` bypasses the gate. `auth.ts` must
open with a comment saying exactly that.

The admin ingest endpoint is gated by a constant-token compare against `X-Admin-Token`, default
`localdev`.

Each of the three credential literals — `DEV_USER = "dev"`, `DEV_PASS = "dev"`, and the
`"localdev"` admin-token default in `main.go` — carries an inline `// dev-only, not a secret`
comment on the same line or the line above. These are scanner bait by design; the comment is what
stops a downstream secret scan from being a false positive.

---

## 8. `PATHOLOGY.md` contract

A sibling `PATHOLOGY.md` is required. It is the machine-readable index of the defects; §5 of this
file is the rationale. It contains one table with exactly these columns:

| Column | Content |
|---|---|
| `ID` | `P1`–`P9`. Stable forever. Never renumber; retire an ID rather than reuse it. |
| `Name` | Short defect name, ≤ 8 words. |
| `Anchor` | **`<path>` → `<symbol>`. Never a line number.** Line numbers drift on every regeneration and every reformat; symbols do not. Where a defect is a whole file, the anchor is `<path> → (file)`. Where it is a struct field, `<path> → <Type>.<Field>`. |
| `Shape` | One sentence, domain-neutral, describing the structure — what a husking transform has to preserve. |
| `Why it exists` | What the defect is measuring and what would be lost if it were "fixed". |
| `Consumed by` | The evaluation section(s) that read this defect, by heading name. |

A `grep` recipe column is optional but encouraged: a single command that relocates the anchor after
drift.

One fully worked row:

| ID | Name | Anchor | Shape | Why it exists | Consumed by |
|---|---|---|---|---|---|
| P2 | Inline SQL in readiness handler | `api/internal/api/server.go` → `(*Server).handleReady` | A raw `SELECT count(*)` aggregate is executed against a struct-owned `*sql.DB` inside an HTTP handler body, with no persistence-layer call between transport and query, and its result is branched on to choose between two error responses and a success response. | Gives every transform exactly one guaranteed SQL-class string literal in the smallest file in the package, so literal classification can be verified without parsing the 375-line handler file. Extracting it into a repository method would delete both the layering evidence and the single-literal control. | "literal-tagging → code-smell detection" §1; "translation → code-smell detection" §1 |

Relocation recipe for that row: `grep -n 'func (s \*Server) handleReady' api/internal/api/server.go`.

Every ID in the table must appear in at least one row of §4's *Pathologies* column, and every ID
referenced in §4 must exist in the table. That bidirectional check is the only consistency gate
between the two files.

---

## 9. Non-goals

1. **This is not production code.** It is not hardened, not authenticated, not deployed, and not
   intended to be. It binds localhost. There is no CI pipeline and none is wanted.
2. **The defects are the product.** P1–P9 must not be refactored, linted away, extracted,
   parameterised, or "cleaned up." A change that improves the architecture destroys the
   measurement. Any tool or agent that proposes fixing them has misread the purpose — point it at
   `PATHOLOGY.md`.
3. **It models nothing real.** No institution, catalogue, consortium, vendor, product, or system.
   Never present it, document it, or introduce it as resembling one. Every identifier, title
   selection, phone number, and credential is fabricated for this document.
4. **It is not a reference implementation of any metadata standard.** The `.mrk` reader handles a
   documented subset plus a stated local profile; the Dublin Core exporter emits a one-way,
   download-only projection. Neither should be cited as conformant.
5. **It is not a test suite for itself.** The Go and TypeScript tests exist to make the corpus a
   plausibly-complete application with realistic test-file shapes for a transform to chew on. They
   are not a quality gate and must not be expanded into one.
6. **Nothing here needs to be portable beyond a developer machine.** Pure-Go SQLite and a
   hardcoded port are the point, not a limitation to be engineered around.
