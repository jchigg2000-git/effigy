# stacks — inter-branch catalog and circulation

A small two-tier application: a Go HTTP service over SQLite, and a React/TypeScript
single-page client. A regional library system shelves **holdings** at three
**branches**; holdings circulate to **borrowers** under **loans**, and borrowers
queue for an item through **reservations**. A loan records the branch a borrower
will collect from, which need not be the branch that shelves the item.

**This tree is synthetic.** Every title, identifier, phone number, call number and
credential in it is invented. It models no real institution, consortium, vendor or
product, and it must never be described as resembling one. See `../README.md` and
`../PATHOLOGY.md` for what it is actually for.

## Prerequisites

Go 1.22+ and Node 20+. That is the whole list. There is no external data file, no
port allocation table, no shared TypeScript base config, and nothing to fetch by
hand — clone the tree and it runs.

## Run it

    make run      # API on :8300, seeded from api/testdata/catalog_seed.mrk
    make ui       # Vite dev server on :5300, proxying /api -> :8300
    make dev      # both at once
    make test     # Go tests
    make ui-test  # SPA tests

The database is created at `api/data/stacks.db` on first boot and seeded from the
MARCMaker file in `api/testdata/`. Delete the directory to start over; `make clean`
does that and leaves `testdata/` alone.

The SPA has a login curtain with the credentials `dev` / `dev`. It is a curtain,
not authentication: the Go API has no auth middleware, and anything talking to
`:8300` directly bypasses it entirely.

## Configuration

Five environment variables, each read at its use site rather than through a config
struct:

| Variable | Default |
| --- | --- |
| `STACKS_ADDR` | `:8300` |
| `STACKS_DB_PATH` | `./data/stacks.db` |
| `STACKS_SEED_PATH` | `./testdata/catalog_seed.mrk` |
| `STACKS_ADMIN_TOKEN` | `localdev` |
| `STACKS_CORS_ORIGINS` | unset — the middleware is a no-op |

## HTTP surface

| Method | Path |
| --- | --- |
| GET | `/healthz` |
| GET | `/readyz` |
| GET | `/holdings/search` |
| GET | `/holdings/{holdingId}` |
| PATCH | `/holdings/{holdingId}` |
| GET | `/holdings/{holdingId}/loans` |
| GET | `/holdings/{holdingId}/export/dc` |
| GET | `/branches/{branchId}` |
| GET | `/branches/{branchId}/holdings` |
| POST | `/admin/ingest` |

Search takes six filters — `title`, `author`, `holdingId` (substring, case
insensitive) and `published`, `branchId`, `shelfBin` (exact) — plus `limit`
(default 50, max 200). At least one filter is required. `title` and `author` are
stored uppercased, and the search handler uppercases the needle, which is what
makes substring matching case-insensitive.

PATCH accepts `author`, `title`, `language`, `deskPhone` and a nested `shelf`
object. Everything derived from ingest is read-only. Errors come back as
`{"error":{"code":"…","message":"…"}}`.

`POST /admin/ingest` reloads the catalog from the seed file and is gated by a
constant-token compare against `X-Admin-Token`.

## Ingest format

`api/testdata/catalog_seed.mrk` is MARCMaker: one `=TAG  body` line per field,
blank line between records, `$` introducing subfields, `{dollar}` escaping a
literal dollar sign. The reader in `api/internal/ingest` handles a documented
subset plus a stated local profile for `=583` and `=876`; it is not a
general-purpose MARC 21 implementation and should not be cited as one.

`GET /holdings/{id}/export/dc` emits a one-way Dublin Core-flavoured projection
intended for download. Nothing reads it back and it is not a conformant
implementation of any metadata standard.

## Layout

    api/cmd/stacksd        daemon entrypoint
    api/internal/api       router, god-struct, handlers
    api/internal/ingest    MARCMaker reader and loader
    api/internal/interchange  Dublin Core export builder
    api/internal/model     JSON projection types
    api/internal/store     database opener and embedded schema
    api/testdata           the seed file
    app/src                SPA source, components, typed client

## Data conventions

Works are public domain, published pre-1929, by authors dead more than 95 years.
ISBNs come from a `978-0-00-` block with deliberately invalid check digits.
Control, OCLC and LCCN numbers are sequential fictions. Borrowers are opaque
`BRW-0000001` identifiers and carry no personal data of any kind. Phone numbers
come only from the reserved `+1-555-01xx` block.
