# DISCARDED — artifacts built, attack stage never ran

**Recorded 2026-09-01, reconstructed from the directory contents before publication** — not a
contemporaneous note. Pre-registration §12 rule 3 asks for the reason to be recorded in the run
directory; what follows is what the files themselves show, and nothing more is claimed.

## What it is

The second launch of the RSCH-1B structure-only attack stage, created at `01:25:02Z` on 2026-08-20.
The directory holds `config.json` and a complete `artifacts/` (120 files). There is no `raw/`: the
attack stage was never run against it, so no attacker call is recorded here.

## How it relates to the analysed run

Every artifact file is byte-identical to its counterpart in
`20260820T021753Z-rsch1-held-out/artifacts/` — the canonicaliser is deterministic — and 15 of the
`.meta.json` sidecars differ only in `latency_s`. `config.json` differs from the analysed run's in
the same five fields as `20260820T012441Z`'s: `run_id`, `started_at`, `attacker_max_tokens`
(`16000` vs `32000`), `repo_dirty` and `repo_git_commit`.

`20260820T012544Z-rsch1-held-out/DISCARDED.md` records why the 16000-token budget was abandoned for
this arm.
