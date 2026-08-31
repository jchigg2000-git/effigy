> **⚠️ SUPERSEDED — point-in-time record, added 2026-08-19.** This note was written while the run
> was still partial and was never regenerated after it was resumed under the same `--run-id` and
> **completed**. Every number below (498 of 960 calls, blind 9/30, `llm-translation` 54/79) describes
> that partial state and contradicts `summary.md` in this same directory, which describes the
> finished run (986 of 998 calls; blind 10/30; `llm-translation` 65/83 = 78.3%).
>
> **`summary.md` is the result. This file is kept for the four pre-flight defects it records** — they
> were caught before they could corrupt a result and are worth not re-discovering — and as the record
> of the spending-cap halt. Nothing below is current state.

# RSCH-1 confirmatory run — INCOMPLETE. Stopped by an account spending cap.

**Status: partial. 498 of 960 attacker calls landed. Do not cite as the completed
pre-registered result.**

The run halted on `403 — "You have exceeded your monthly spending limit for
Inference Providers."` That is an account-level monthly cap on the HuggingFace
router, not a per-run budget, and it also means **`husk-api`'s `llm-translation`
solution is non-functional until the cap resets or is raised** — the eval is not
the only thing affected.

Rejected calls are billed nothing, so actual spend was **$21.46**.

## Coverage — two of three held-out domains

| domain | forced choice | open ended | complete? |
|---|---|---|---|
| `water-utility-metering` | 174 | 176 | yes |
| `ham-radio-logbook` | 71 | 75 | ~half |
| `seismic-monitoring` | 1 | 1 | **no — 1 call** |

Amendment A1 reports a confirmatory run as INCONCLUSIVE on power grounds if the
held-out split carries fewer than 3 domains. **Two domains carry real data here,
so this run does not meet A1's floor** regardless of how clean its numbers look.

## What it nonetheless shows, on two domains

| arm | menu (recognition) | free text (recall) |
|---|---|---|
| blind | 9/30 (30.0%) | 0/29 (0.0%) |
| source | 28/28 (100%) | 27/28 (96.4%) |
| fpe | 30/30 (100%) | 25/30 (83.3%) |
| literal-tagging | 30/30 (100%) | 26/30 (86.7%) |
| composed | 30/30 (100%) | 20/28 (71.4%) |
| **llm-translation** | 54/79 (68.4%) | 27/86 (31.4%) |

llm-translation vs blind, paired over 15 source files: diff **+0.384**, 95% CI
[+0.121, +0.623]. §8's FAIL condition (diff ≥ 0.25 and CI lower > 0) is met.

**Read the two columns together or not at all.** The menu hands the attacker
twelve options with the right one among them — a recognition task. Free text asks
it to describe the domain cold. `llm-translation` is the only arm that separates
them, and it is the only arm doing any work: it cuts recall from 96.4% to 31.4%
while the other three leak at ceiling on both. C1 is phrased in terms of the menu
column, which is why C1 fails while the mechanism is visibly working.

## What this run cannot say

The corpus is **synthetic**. There is no real organization, product, vendor or
regulator in it, so identifier-level re-identification — the thing the threat
model actually names — is untestable here by construction. The only "specific
identifier" ever recovered was `meterworks`, our own invented module name; the one
real-world name that appeared in a guess (a utility software vendor) does not
occur anywhere in the corpus and was a fabrication. Even the **unhusked** SOURCE
control named a real outside entity on a minority of items, all of them guesses.

## Defect found, worth fixing

`llm-translation` left the source module name `meterworks` in its output, though
the system prompt explicitly requires imports of the input's own modules to be
renamed. That is a direct, checkable leak and a candidate acceptance test for
RSCH-2's verifier.

## To finish this run

Raise or wait out the HF monthly cap, then — every completed call is cached, so
only the missing ones are paid for again:

    python3 evals/run_rsch1.py --stage attack --split held-out --workers 10 \
      --arms blind,source,fpe,literal-tagging,composed,llm-translation \
      --modes forced_choice,open_ended --run-id 20260819T182111Z-rsch1-held-out
    python3 evals/score_rsch1.py evals/runs/20260819T182111Z-rsch1-held-out
    python3 evals/kappa_judge.py --sample evals/runs/20260819T182111Z-rsch1-held-out

The judge stage (§6.2 pass 2) never ran — it needs the same endpoint.
