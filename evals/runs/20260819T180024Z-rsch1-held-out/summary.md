# RSCH-1 — results

**Run:** `20260819T180024Z-rsch1-held-out`  ·  **split:** `held-out`  ·  **sources:** 2
**Pre-registration commit:** `ae7f53ac9402ad45fb1ace7cce522bdb0ca55689` (§12 rule 4)
**Repo commit:** `c423c3dcf5032f35ac6a50d77562a185d2822b20`  ⚠️ **working tree dirty**
**Attackers:** moonshotai/Kimi-K3:baseten, deepseek-ai/DeepSeek-V4-Pro-0813:baseten  ·  **judge:** zai-org/GLM-5.2:baseten
**Rewriter:** Qwen/Qwen2.5-Coder-7B-Instruct  ·  endpoint `router.huggingface.co`

## 1. Validity gate (§8) — evaluated first

If this fails, **no verdict is issued for any arm**.

| attacker | p_source | parse failure (all arms) | gate |
|---|---|---|---|
| `moonshotai/Kimi-K3:baseten` | 2/2 (100.0%) [0.34, 1.00] | 0/13 (0.0%) | ✅ pass |
| `deepseek-ai/DeepSeek-V4-Pro-0813:baseten` | 2/2 (100.0%) [0.34, 1.00] | 0/13 (0.0%) | ✅ pass |

## 2. Arm B — forced choice (pre-registered primary endpoint, §6.1)

Chance on a 12-option menu is 0.083. **BLIND, not chance, is the baseline C1 is measured against** (§3).

| arm | `Kimi-K3:baseten` | `DeepSeek-V4-Pro-0813:baseten` | **panel max** |
|---|---|---|---|
| `blind` | 0/2 (0.0%)<br><sub>[0.00, 0.66]</sub> | 0/2 (0.0%)<br><sub>[0.00, 0.66]</sub> | **0.000** |
| `source` | 2/2 (100.0%)<br><sub>[0.34, 1.00]</sub> | 2/2 (100.0%)<br><sub>[0.34, 1.00]</sub> | **1.000** |
| `fpe` | 2/2 (100.0%)<br><sub>[0.34, 1.00]</sub> | 2/2 (100.0%)<br><sub>[0.34, 1.00]</sub> | **1.000** |
| `literal-tagging` | 2/2 (100.0%)<br><sub>[0.34, 1.00]</sub> | 2/2 (100.0%)<br><sub>[0.34, 1.00]</sub> | **1.000** |
| `composed` | 2/2 (100.0%)<br><sub>[0.34, 1.00]</sub> | 2/2 (100.0%)<br><sub>[0.34, 1.00]</sub> | **1.000** |
| `llm-translation` | 3/3 (100.0%)<br><sub>[0.44, 1.00]</sub> | 3/3 (100.0%)<br><sub>[0.44, 1.00]</sub> | **1.000** |
| `llm-translation-ungated` | — | — | **0.000** |

§7 and §12.1: the headline is the **maximum** across the panel, never the mean — averaging a strong attacker against a weak one launders a failure.

### Accuracy at confidence ≥ 0.7 (§6.1)

| arm | `Kimi-K3:baseten` | `DeepSeek-V4-Pro-0813:baseten` |
|---|---|---|
| `blind` | — | — |
| `source` | 2/2 (100.0%) | 2/2 (100.0%) |
| `fpe` | 2/2 (100.0%) | 2/2 (100.0%) |
| `literal-tagging` | 2/2 (100.0%) | 2/2 (100.0%) |
| `composed` | 2/2 (100.0%) | 2/2 (100.0%) |
| `llm-translation` | 3/3 (100.0%) | 3/3 (100.0%) |
| `llm-translation-ungated` | — | — |

### Per-domain accuracy (§9 — always reported)

One leaky domain is invisible in an aggregate and is exactly the case that matters.

| arm | attacker | `water-utility-metering` |
|---|---|---|
| `blind` | `Kimi-K3:baseten` | 0/2 (0.0%) |
| `blind` | `DeepSeek-V4-Pro-0813:baseten` | 0/2 (0.0%) |
| `source` | `Kimi-K3:baseten` | 2/2 (100.0%) |
| `source` | `DeepSeek-V4-Pro-0813:baseten` | 2/2 (100.0%) |
| `fpe` | `Kimi-K3:baseten` | 2/2 (100.0%) |
| `fpe` | `DeepSeek-V4-Pro-0813:baseten` | 2/2 (100.0%) |
| `literal-tagging` | `Kimi-K3:baseten` | 2/2 (100.0%) |
| `literal-tagging` | `DeepSeek-V4-Pro-0813:baseten` | 2/2 (100.0%) |
| `composed` | `Kimi-K3:baseten` | 2/2 (100.0%) |
| `composed` | `DeepSeek-V4-Pro-0813:baseten` | 2/2 (100.0%) |
| `llm-translation` | `Kimi-K3:baseten` | 3/3 (100.0%) |
| `llm-translation` | `DeepSeek-V4-Pro-0813:baseten` | 3/3 (100.0%) |

## 3. Verdicts (§8)

| solution | p_husk (strongest attacker) | p_blind (same attacker) | attacker | 95% CI on difference (cluster bootstrap over source files) | verdict |
|---|---|---|---|---|---|
| `fpe` | 2/2 (100.0%) | 0/2 (0.0%) | `Kimi-K3:baseten` | [+1.000, +1.000] | **FAIL** |
| `literal-tagging` | 2/2 (100.0%) | 0/2 (0.0%) | `Kimi-K3:baseten` | [+1.000, +1.000] | **FAIL** |
| `composed` | 2/2 (100.0%) | 0/2 (0.0%) | `Kimi-K3:baseten` | [+1.000, +1.000] | **FAIL** |
| `llm-translation` | 3/3 (100.0%) | 0/2 (0.0%) | `Kimi-K3:baseten` | [+1.000, +1.000] | **FAIL** |

> **INCONCLUSIVE is reported as inconclusive** — never as support for C1, never as "no evidence of leakage." (§8, registered literally so it cannot be softened later.)

## 4. Arm A — open ended (§6.2). Can only FALSIFY C1, never support it.

### 4.1 Deterministic leak-term pre-check — no model, fully reproducible

| arm | attacker | guesses containing a source-domain leak term | veto |
|---|---|---|---|
| `blind` | `Kimi-K3:baseten` | 0/2 (0.0%) | — |
| `blind` | `DeepSeek-V4-Pro-0813:baseten` | 0/2 (0.0%) | — |
| `source` | `Kimi-K3:baseten` | 2/2 (100.0%) | — |
| `source` | `DeepSeek-V4-Pro-0813:baseten` | 2/2 (100.0%) | — |
| `fpe` | `Kimi-K3:baseten` | 2/2 (100.0%) | 🚫 **FAIL — hard veto** |
| `fpe` | `DeepSeek-V4-Pro-0813:baseten` | 2/2 (100.0%) | 🚫 **FAIL — hard veto** |
| `literal-tagging` | `Kimi-K3:baseten` | 2/2 (100.0%) | 🚫 **FAIL — hard veto** |
| `literal-tagging` | `DeepSeek-V4-Pro-0813:baseten` | 2/2 (100.0%) | 🚫 **FAIL — hard veto** |
| `composed` | `Kimi-K3:baseten` | 2/2 (100.0%) | 🚫 **FAIL — hard veto** |
| `composed` | `DeepSeek-V4-Pro-0813:baseten` | 2/2 (100.0%) | 🚫 **FAIL — hard veto** |
| `llm-translation` | `Kimi-K3:baseten` | 3/3 (100.0%) | 🚫 **FAIL — hard veto** |
| `llm-translation` | `DeepSeek-V4-Pro-0813:baseten` | 3/3 (100.0%) | 🚫 **FAIL — hard veto** |

> **Hard veto fired (§8).** A solution whose open-ended guesses hit its own source-domain leak terms on ≥ 10% of items is **FAIL regardless of its forced-choice result**. Solutions vetoed: `fpe`, `literal-tagging`, `composed`, `llm-translation`

## 5. Mechanism — copied source vs successful re-identification

*Not pre-registered. Descriptive, and reported as such.* Measured with the shipped `app/solutions/_husk_check.inspect`, the same implementation the request-path gate uses, so this cannot drift from what the service enforces.

| arm | mean copied-span share when attacker was RIGHT | when WRONG | n right / n wrong |
|---|---|---|---|
| `fpe` | 0.167 | nan | 4 / 0 |
| `literal-tagging` | 0.336 | nan | 4 / 0 |
| `composed` | 0.000 | nan | 4 / 0 |
| `llm-translation` | 0.219 | nan | 6 / 0 |

A higher figure in the first column than the second means the attacker succeeded disproportionately on husks that had returned more of their own source verbatim — i.e. the leak is *copying*, which is a fixable defect with a gate already built for it. Similar figures mean the leak survives a genuine rewrite, which is the harder and more interesting result and is what `docs/working-paper.md` §4.2 predicts.

## 6. Power, registered in advance (§10)

With 2 clustered source files this design reliably resolves a difference of ~0.20–0.25 and **cannot resolve differences below ~0.10**. A null result therefore means *"no leak detectable at this corpus scale"* — **not** that the husk is private.

