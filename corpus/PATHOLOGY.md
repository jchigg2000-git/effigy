# Deliberate defects in the evaluation corpus

This is the machine-readable index of the architectural defects planted in
`corpus/stacks/`. The rationale for each lives in `corpus/stacks/SPEC.md` §5; this
file is what the harness reads.

**These defects are the measurement instrument, not a backlog.** A husking
transform is scored on whether they survive rewriting. Refactoring, linting away,
extracting, parameterising or otherwise "cleaning up" any row below destroys the
measurement it exists to take. Any tool or agent that proposes fixing one has
misread the purpose — point it back here.

**Anchors are symbols, never line numbers.** Line numbers drift the first time
anyone touches a file, which is how the superseded corpus rotted. Every anchor is
a string that appears verbatim in the corpus source, so it can be relocated with
`grep` after any amount of reformatting. `evals/run_eval.py --verify` re-resolves
every anchor in the index table below against the corpus on every run and fails if
one has vanished.

IDs are stable forever. Retire an ID rather than reuse it.

**Comments in the corpus must never name the defect they sit next to.** A
comment saying "every handler can reach every concern" or "nothing but
convention keeps these in step" turns the corpus into an answer key: a reviewing
model scores full marks by reading the prose instead of the structure, and a
husk is then scored on whether it preserved *comments* rather than whether it
preserved *architecture*. This was found on 2026-08-19 when a multi-file
reviewer recovered 9/9 defects and cited a self-describing comment as its
evidence for four of them; eight comment lines were rewritten as ordinary
developer prose. Corpus comments should read like something a working engineer
wrote — describing what the code does, never that it is deliberately bad.

## Catalogue

| ID | Name | Anchor | Shape | Why it exists | Consumed by |
| --- | --- | --- | --- | --- | --- |
| P1 | God-struct holding every concern | `api/internal/api/server.go` → `Server` | One struct, built once at boot, holds a raw database handle alongside a structured logger, two scalar configuration strings and the assembled HTTP handler; every request handler is a method on it, so every handler has ambient access to every concern. Five fields, three responsibilities. | It is the root cause the other transport-layer defects hang off. If the handle were an interface or a repository type, P2 and P3 could not exist and the layering evidence would disappear from the call graph as well as from the type. | fpe → structural preservation; literal-tagging → code-smell detection; llm-translation → code-smell detection |
| P2 | Inline SQL in readiness handler | `api/internal/api/server.go` → `(*Server).handleReady` | A raw `SELECT count(*)` aggregate is executed against a struct-owned `*sql.DB` inside an HTTP handler body, with no persistence-layer call between transport and query, and its result is branched on to choose between two error responses and a success response. | Gives every transform exactly one guaranteed SQL-class string literal in the smallest file in the package, so literal classification can be verified without parsing the 375-line handler file. Extracting it into a repository method would delete both the layering evidence and the single-literal control. | literal-tagging → code-smell detection; llm-translation → code-smell detection |
| P3 | Persistence layer present but unused | `api/internal/store/store.go` → `Open` | A package that is nominally the persistence layer exposes exactly one function: it applies pragmas, executes an embedded schema and hands back the raw handle. It contains no queries. Every query in the program is written inline in an HTTP handler or an ingest function. The layer exists in the directory structure and is absent from the call graph. | Layering violations that a husk can still expose are the highest-value finding in the whole evaluation, because they are invisible to identifier substitution — the evidence is in where code lives, not in what it is called. Moving one query into `store` would make the package look load-bearing and destroy the contrast. | fpe → structural preservation; llm-translation → code-smell detection |
| P4 | Domain-leaking literals across layers | `api/internal/api/server.go` → `corsAllowList` | Configuration keys, route paths, error prose and protocol constants are inline literals at their use sites rather than named constants, in four sub-classes, spread across the daemon, the router, the handlers, the export builder and the typed client. The program's subject matter is reconstructible from the strings alone. | This is the surface the privacy argument is actually tested against, and the misclassification cases are deliberate: `application/json` matches a path-shaped pattern and gets tagged as a path, and a bare `method: "PATCH"` is indistinguishable from prose. Naming these as constants would remove documented findings. | literal-tagging → literal classification; llm-translation → literal classification; privacy → source-domain identification |
| P5 | SQL concatenated over optional filters | `api/internal/api/holdings.go` → `(*Server).handleSearchHoldings` | One handler file materially larger than every other file in its package. Its bulk is a search handler that appends `WHERE` fragments to a string slice and bind arguments to an `any` slice across six independent optional-filter branches, then joins the fragments into a query, plus a patch handler doing the same for a `SET` clause through `fmt.Sprintf`. | The file-size and literal-density findings are keyed to this file, and the six raw SQL literals in it are the hard target the literal histogram is checked against. Parameterising the builder or moving it behind a query object collapses both the size signal and the SQL-class count. | fpe → structural preservation; literal-tagging → code-smell detection; llm-translation → code-smell detection |
| P6 | Nested switch on magic-string discriminants | `api/internal/ingest/marc21.go` → `Parse` | A line-oriented record parser whose main loop is a large switch on a tag token, where individual arms open a guard and then a second switch on a sub-discriminant, with bare string constants as case labels and length-guarded positional indexing into a slice of parsed fragments. Maximum brace depth six. Subfield access is deliberately inconsistent: some arms use a keyed helper, others index positionally. | Nesting depth and switch arity are the structural counters most likely to be flattened by a rewriter, and the magic-string discriminants are the ones a translation is most tempted to rename into an enum. Both moves are detectable only if the input carries them. | fpe → structural preservation; llm-translation → structural preservation |
| P7 | Zero-arg closures over mutable outer state | `api/internal/ingest/marc21.go` → `flushRecord` | The parse function declares record-accumulator pointers in its own scope, then defines zero-argument closures that read and write those pointers. Both the closures and the raw pointers are touched from inside multiple case arms of the loop, and the closures are called once more after it terminates. Nothing is passed as an argument; all coupling runs through captured variables. | This is the defect a prior evaluation reported as still legible after identifier substitution — the zero-argument calls plus the repeated non-local variable are the signature, and they survive renaming. It is the strongest evidence the corpus has that structure outlives vocabulary. | fpe → structural preservation; literal-tagging → code-smell detection; llm-translation → structural preservation |
| P8 | Wide positional Scan across a join | `api/internal/api/holdings.go` → `(*Server).loadHolding` | A loader issues a two-table join and binds nineteen columns positionally into a single `Scan` spread over four physical lines, with a coalesce wrapping every nullable column. Column order in the query and argument order in the bind are coupled by nothing but convention, so a column added to either table silently shifts every binding after it. | Corroborating evidence for P1 and P3, and a sharp test of whether a transform preserves argument arity. The fifteen-plus-four column split is pinned by the schema; adding a column to either table breaks this row and requires editing it here first. | fpe → structural preservation; llm-translation → structural preservation |
| P9 | Copy-pasted not-found ladder | `api/internal/api/holdings.go` → `errors.Is` | An identical four-line error-handling block — test for the no-rows sentinel, write a 404 envelope, return; test for any other error, delegate to the server-error helper, return — repeated verbatim across four handlers with no extracted helper, plus a branch-scoped variant in a fifth. The client-side arm is a TypeScript validator that restates the Go validator's rules and messages by hand. | Duplication that spans two languages is the only defect here a single-file transform cannot see, which makes it the control for cross-file findings. Extracting a helper on either side would remove the repetition the counters measure. | literal-tagging → code-smell detection; llm-translation → code-smell detection |

## Anchor index

The harness parses the first cell of each row below and greps the corpus for it.
Every entry is a literal substring of a `.go`, `.ts` or `.tsx` file under
`corpus/stacks/` that is not a test file.

| Anchor symbol | ID | File | What it pins |
| --- | --- | --- | --- |
| `type Server struct` | P1 | `api/internal/api/server.go` | the god-struct declaration itself |
| `NewServer` | P1 | `api/internal/api/server.go` | the single construction site that wires every concern together |
| `handleReady` | P2 | `api/internal/api/server.go` | the readiness handler carrying inline SQL |
| `SELECT count(*) FROM holdings` | P2 | `api/internal/api/server.go` | the one raw aggregate literal in the smallest file |
| `store.Open` | P3 | `api/cmd/stacksd/main.go` | the only call into the nominal persistence layer |
| `SetMaxOpenConns` | P3 | `api/internal/store/store.go` | the body of that layer — pragmas and a handle, no queries |
| `STACKS_CORS_ORIGINS` | P4 | `api/internal/api/server.go` | an environment key read inline at its use site |
| `application/dc+json; charset=utf-8` | P4 | `api/internal/api/holdings.go` | a protocol literal written where it is used |
| `const BASE = "/api"` | P4 | `app/src/api/client.ts` | the client's one named constant, against which everything else is inline |
| `method: "PATCH"` | P4 | `app/src/api/client.ts` | the bare HTTP-method literal, a documented misclassification case |
| `DEV_PASS` | P4 | `app/src/auth.ts` | a credential literal kept inline on purpose, with its scanner-bait comment |
| `handleSearchHoldings` | P5 | `api/internal/api/holdings.go` | the concatenating search handler |
| `strings.Join(conds, " AND ")` | P5 | `api/internal/api/holdings.go` | the join that assembles the WHERE clause from fragments |
| `validateAndBuild` | P5 | `api/internal/api/holdings.go` | the SET-clause builder and its closure over two slices |
| `LOANSTART` | P6 | `api/internal/ingest/marc21.go` | a magic-string discriminant inside the deep nested switch |
| `sub(sfs, 'b') == "D8"` | P6 | `api/internal/ingest/marc21.go` | the guard the second switch opens inside |
| `sub(sfs, 'a')` | P6 | `api/internal/ingest/marc21.go` | the keyed subfield idiom, half of the deliberate inconsistency |
| `sfs[1].Value` | P6 | `api/internal/ingest/marc21.go` | the positional subfield idiom, the other half |
| `flushRecord` | P7 | `api/internal/ingest/marc21.go` | the zero-argument closure called from two arms and after the loop |
| `flushLoan` | P7 | `api/internal/ingest/marc21.go` | the inner closure the outer one calls |
| `curLoan` | P7 | `api/internal/ingest/marc21.go` | the captured pointer touched from three separate paths |
| `loadHolding` | P8 | `api/internal/api/holdings.go` | the loader with the nineteen-column bind |
| `&br.RegistrySymbol, &br.SystemID` | P8 | `api/internal/api/holdings.go` | the tail of the positional Scan, where drift would first show |
| `errors.Is(err, sql.ErrNoRows)` | P9 | `api/internal/api/holdings.go` | the duplicated sentinel test |
| `holding not found` | P9 | `api/internal/api/holdings.go` | the message repeated verbatim by each copy |
| `branch not found` | P9 | `api/internal/api/branches.go` | the branch-scoped variant of the same ladder |
| `deskPhone must be digits only` | P9 | `api/internal/api/holdings.go` | a validator message the TypeScript arm restates by hand |

## Relocation recipes

If an anchor stops resolving, these find where it moved. Run them from the
repository root.

    grep -rn 'type Server struct'            corpus/stacks/api/internal/api/
    grep -rn 'func (s \*Server) handleReady' corpus/stacks/api/internal/api/server.go
    grep -rn 'func Open('                    corpus/stacks/api/internal/store/store.go
    grep -rn 'STACKS_'                       corpus/stacks/api/
    grep -rn 'strings.Join(conds'            corpus/stacks/api/internal/api/holdings.go
    grep -rn 'flushRecord\|flushLoan'        corpus/stacks/api/internal/ingest/marc21.go
    grep -rn 'func (s \*Server) loadHolding' corpus/stacks/api/internal/api/holdings.go
    grep -rn 'sql.ErrNoRows'                 corpus/stacks/api/internal/api/

## Consistency gate

Every ID in the catalogue appears in the *Pathologies* column of `SPEC.md` §4, and
every ID referenced there exists here. That bidirectional check is the only
consistency requirement between the two files.
