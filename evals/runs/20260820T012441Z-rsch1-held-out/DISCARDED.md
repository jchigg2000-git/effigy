# DISCARDED — this run produced no data

**Recorded 2026-09-01, reconstructed from the directory contents before publication** — not a
contemporaneous note. Pre-registration §12 rule 3 asks for the reason to be recorded in the run
directory; what follows is what the files themselves show, and nothing more is claimed.

## What it is

The first launch of the RSCH-1B structure-only attack stage, created at `01:24:41Z` on 2026-08-20.
The directory holds `config.json` and nothing else: no `artifacts/`, no `raw/`, no scores.
`run_rsch1.py` writes `config.json` immediately after creating the run directory, so this is what
an invocation stopped before its first item leaves behind. No API call is recorded.

## How it differs from the analysed run

Against `20260820T021753Z-rsch1-held-out` (the run reported in `ROADMAP.md` and `LIMITATIONS.md`),
`config.json` differs in exactly five fields: `run_id`, `started_at`, `attacker_max_tokens`
(`16000` here, `32000` there), `repo_dirty` (`true` here) and `repo_git_commit`. Arms, split,
domain assignment, source-file list and manifest digests are identical.

`20260820T012544Z-rsch1-held-out/DISCARDED.md` records why the 16000-token budget was abandoned for
this arm; this directory and `20260820T012502Z-rsch1-held-out/` are the two earlier launches under
that same budget.
