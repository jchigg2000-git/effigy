# RSCH-1 attacker panel — selection record

**Probe:** `probe.json`, `source=endpoint`, 2026-08-19T17:37:46Z, `router.huggingface.co`.
**Selects for:** `preregistration.md` §7 (attacker panel) and §8 (validity gate).

## The catalog was stale by 98 models

`husk-api/static/llm-translation-models.json` names **32** models. The router serves **130**.
Every prior probe in this repo sourced its id list from that file, so
`20260819T123120Z-model-probe` reported "13/32 usable" against an inventory nearly four times
larger — and every frontier-class model on the endpoint was outside the list it probed. Re-probed
from the endpoint: **116/130 usable** (66 `ok`, 50 `budget-exhausted`, 9 `reasoning-leak`, 5 error).

`probe_models.py --from-endpoint` now asks the router for `/models` and probes that, recording each
model's live-provider count, maximum context length, and cheapest advertised price. Catalog mode is
kept only to reproduce older runs. **Prefer `--from-endpoint`.** This did not touch the UI catalog:
that dropdown is a product surface and refreshing it is a separate decision.

## The panel

Rewriter is Qwen (`Qwen2.5-Coder-7B-Instruct`), so §7 disqualifies the entire Qwen family from
every attacker and judge seat. Three distinct families, none of them Qwen:

| Seat | Model | Family | Ctx | $/Mtok in/out | Why |
|---|---|---|---|---|---|
| **A1 primary** | `moonshotai/Kimi-K3` | moonshotai | 1.05M | 2.85 / 14.25 | The strongest and most expensive model the endpoint serves. §7 wants the primary attacker to be frontier-class; this is the frontier available on this token. |
| **A2 robustness** | `deepseek-ai/DeepSeek-V4-Pro-0813` | deepseek-ai | 1.05M | 1.32 / 3.96 | Different family, comparable context, independently strong. |
| **Judge** | `zai-org/GLM-5.2` | zai-org | 1.05M | 0.75 / 2.40 | Third family, distinct from A1 as §6.2 requires. |

§7's "frontier hosted model from a different vendor family" is satisfied on family and on relative
strength within what is reachable. It is **not** satisfied in the sense of a Claude/GPT-class
hosted API: no such key exists in this environment. That gap is a real ceiling on the claim and
belongs in the writeup — a null result here means "not recovered by the strongest attacker
reachable on this token," never "not recoverable."

Rejected on parse reliability against §8's ≤5% parse-failure gate (strict JSON, temperature 0,
n=3): `Kimi-K2.6` 1/3, `Kimi-K2.5` 2/3, `Inkling-Small` 2/3, `Step-3.7-Flash` 2/3. Clean 3/3 and
available as substitutes: `thinkingmachines/Inkling`, `zai-org/GLM-4.7`, `XiaomiMiMo/MiMo-V2.5`,
`nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4`, `MiniMaxAI/MiniMax-M3`.

## Determinism — the trigger does not fire, and the first measurement of it was wrong

§10 escalates to **3 attacker trials everywhere** if temperature-0 determinism fails. It was first
measured against a deliberately domain-free stub (`handleGetX`, table `xs`, column `label`) and
appeared to fail badly — `Kimi-K3` returned `[4, 4, 2]`, `DeepSeek-V4-Pro-0813` `[3, 2, 2]`,
`GLM-5.1` `[2, 1, 4]`. Since every candidate is fanned across 4–8 live providers and the router
picks one per request, the obvious reading was that the endpoint cannot be deterministic at all.

**That reading was wrong.** Re-measured on a real corpus artifact
(`corpus/stacks/api/internal/interchange/dublincore.go`, first 150 lines) with the real 12-option
permuted menu, 5 calls each, pinned and unpinned:

| Model | unpinned | pinned | correct |
|---|---|---|---|
| `moonshotai/Kimi-K3` | `[3,3,3,3,3]` | `[3,3,3,3,3]` | 5/5 |
| `deepseek-ai/DeepSeek-V4-Pro-0813` | `[3,3,3,3,3]` | `[3,3,3,3,3]` | 5/5 |
| `zai-org/GLM-5.2` | `[3,3,3,3,3]` | `[3,3,3,3,3]` | 5/5 |

The scatter was **signal strength, not sampling**: given an artifact with no domain content, the
models are guessing, and guesses scatter. Given real domain signal they converge, and provider
pinning changes nothing. So the run stays at **one attacker call per item**, and §10's 20%
determinism subsample is still owed on the real corpus before that is final.

Two things this does not establish. It is one artifact, and it is the metadata-interchange file —
among the most domain-laden in the corpus, so 5/5 here is an easy case, not a general
`p_source`. And a model that is deterministic on a *strong-signal* item may well scatter on husks,
which are the low-signal case by construction. Expect the determinism subsample to be tighter on
HUSK items than on SOURCE items, and size it from the HUSK arm.

## Reproduce

    python3 evals/probe_models.py --from-endpoint --workers 12
