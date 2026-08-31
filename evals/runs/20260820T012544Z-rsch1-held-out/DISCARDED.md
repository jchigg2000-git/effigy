# DISCARDED — attacker budget too small for this arm. Raw output kept.

**Recorded 2026-08-19**, per pre-registration §12 rule 3: the reason is recorded here and the
discarded raw output **stays committed**.

## What went wrong

This was the first attack stage for the RSCH-1B structure-only arms, run at the RSCH-1 default of
`--max-tokens 16000`. Of the 29 forced-choice records that landed, **14 (48.3%) never resolved to an
answer** — against §8's validity ceiling of **5% parse failure**. Continuing would have bought an
INCONCLUSIVE verdict at full price.

Two causes, separated by inspecting the raw records:

| cause | records | note |
|---|---|---|
| `finish_reason: length`, empty text | 7 | the model's internal deliberation consumed the whole budget |
| `504 Gateway Time-out` from the router | 6 | all on `moonshotai/Kimi-K3:baseten` |
| other | 1 | |
| resolved | 15 | |

**The root cause is the arm itself, and it is worth stating plainly: a vocabulary-free artifact makes
these reasoning models deliberate far longer than a husk does.** RSCH-1 re-ran at 16000 with 0%
parse failure on the same models and the same menu; the only thing that changed is that the artifact
carries no vocabulary to reason from. Observed latencies here were 100–240s per call, which is also
why the router's gateway timed out during a slow window.

## What was verified before re-running

Replaying two failed records with their **stored prompts**, at both budgets:

| item | attacker | 16000 | 32000 |
|---|---|---|---|
| `meterworks__App.tsx__structure-only-nonum` | Kimi-K3 | `stop` after 239s | `stop` after 110s |
| `meterworks__App.tsx__structure-only` | DeepSeek-V4-Pro | **`length`, empty** | `stop` after 111s |

So 16000 is deterministically insufficient for this arm, and the Kimi 504s were transient — the same
item succeeds on replay.

## What replaced it

A fresh run at a uniform `--max-tokens 32000`. Fresh rather than resumed **so that every item in the
analysed run is measured under one budget** — mixing two attacker budgets inside one arm would make
the comparison between items an artifact of when each call happened to run.

The `artifacts/` here are byte-identical to the replacement's: the canonicaliser is deterministic and
every one of them passed the gate. Only `raw/` is affected.
