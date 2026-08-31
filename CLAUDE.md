**`ROADMAP.md` is the SINGLE SOURCE OF TRUTH for execution** — what's left, what's next, and
every phase / acceptance criterion / decision, across all workstreams. On any handoff, **read it
first and follow only it as the plan.** There is deliberately **no other `*_PLAN` or status
doc** — `rerun-llm-test.md` was folded into it (2026-08-07); never recreate a doc like it. Put
new plan or status content in `ROADMAP.md`. If any doc's status conflicts with ROADMAP, ROADMAP
wins.

`docs/handoffs/01-06` are kept as build history (README indexes them directly) — not rival plan
docs, do not fold or delete them.

**Backlog items are not blockers.** No item under a `BACKLOG` / `PARKED` status gates any other
work unless it carries a `⛔ BLOCKS:` line quoting the owner's instruction from when it was
parked. Absent that line, it is non-blocking. Do not infer blocking from urgency or dependency
order.

`DECISIONS.md` is append-only; supersede rather than rewrite.

Read order for a fresh session: this file → `ROADMAP.md`, then `docs/working-paper.md` /
`husk-algorithms.md` / `docs/handoffs/*` on demand.
