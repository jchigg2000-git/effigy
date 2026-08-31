# DISCARDED — do not cite these numbers

Retained per `evals/preregistration.md` §12 rule 3: a discarded run keeps its raw
output, and the reason is recorded next to it.

## Why

**1. The corpus was an answer key when this ran.** Eight comments in the corpus
named the defects they sat beside — "every handler can reach every concern",
"every query in this program is written at its call site", "nothing but
convention keeps the SELECT list and the Scan list in step". The evaluator was
reading labels rather than detecting structure, and the husker preserved those
labels in translation, so the husk scored well for the wrong reason. Fixed in
commit `c6bc23f`.

**2. A harness bug corrupted the agreement column.** A failed baseline diagnosis
was stored as "this file has no smells" instead of as a failure. The evaluator
failed on the 376-line `holdings.go`, so the husk diagnosis — which correctly
found all four planted defects there — scored 0.0 agreement against a false
claim that the real file was clean. Fixed in commit `5dbd96c`.

**3. Single-file scope made two of the nine defects unscoreable.**
`layering_violation` is the absence of queries in the persistence package and
their presence in handlers; `duplicated_error_handling` spans four handlers plus
a TypeScript restatement. Neither is visible in one file, so both scored 0
regardless of husker quality. Superseded by the multi-file agentic path.

## What is still true

The two zero-scoring huskers failed on **context window**, not quality:
`Qwen/Qwen2.5-7B-Instruct` returned 422 "Input validation error", and
`google/gemma-3n-E4B-it` returned 400 "Requested token count exceeds". A cheap
local husker needs enough context for the largest file plus the system prompt,
and two of four otherwise-plausible candidates could not take a 376-line file.
That finding does not depend on any of the discarded scoring.
