# DISCARDED — this run produced no data

**Recorded 2026-08-19**, per pre-registration §12 rule 3 ("If a run is discarded, the reason is
recorded in the run directory and the discarded raw output stays committed"). There is no raw
output to keep: `raw/` and `artifacts/` are both empty, and **zero API calls were made**.

## What it is

A second launch of the held-out RSCH-1 run, started at `19:22:50Z`, abandoned before a single item
completed. `run_rsch1.py` writes `config.json` immediately after creating the run directory and
before either stage does any work, so a fully-written config beside empty `raw/`/`artifacts/` is
exactly what an invocation that never finished its first item leaves behind.

## Why it was abandoned

Its `config.json` differs from the completed run's in exactly three fields — `run_id`, `started_at`,
and `modes` (`["forced_choice"]` only, omitting `open_ended`). Everything else is byte-identical,
including `manifest_sha256`, `domains_sha256`, `repo_git_commit` and the 30-file `source_files` list.

The chronology: `20260819T182111Z-rsch1-held-out` was created at `18:21:11Z` and halted on
`403 — You have exceeded your monthly spending limit` (see that run's `NOTE.md`). This directory was
created at `19:22:50Z`, between that halt and the resume. The original run was then resumed under its
own `--run-id` at `21:00:01Z` and completed — every already-paid-for call was cached, so resuming was
strictly cheaper than starting fresh. This attempt was dropped in favour of that.

**Nothing here was used in any result.** It is kept, rather than deleted, so the run sequence in
`evals/runs/` has no unexplained gap.
