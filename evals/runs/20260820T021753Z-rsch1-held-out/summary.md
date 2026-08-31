# RSCH-1 — results

**Run:** `20260820T021753Z-rsch1-held-out`  ·  **split:** `held-out`  ·  **sources:** 30
**Pre-registration commit:** `1977895e2029055b18cc2d5ec24ba9fae3a053e9` (§12 rule 4)
**Repo commit:** `652976ec0740999d43f4a95d0592099a5201a78b`  ⚠️ **working tree dirty**
**Attackers:** moonshotai/Kimi-K3:baseten, deepseek-ai/DeepSeek-V4-Pro-0813:baseten  ·  **judge:** zai-org/GLM-5.2:baseten
**Rewriter:** Qwen/Qwen2.5-Coder-7B-Instruct  ·  endpoint `router.huggingface.co`

## 1. Validity gate (§8) — evaluated first

If this fails, **no verdict is issued for any arm**.

| attacker | p_source | parse failure (all arms) | gate |
|---|---|---|---|
| `moonshotai/Kimi-K3:baseten` | 0/0 (0.0%) [0.00, 1.00] | 0/51 (0.0%) | ❌ FAIL |
| `deepseek-ai/DeepSeek-V4-Pro-0813:baseten` | 0/0 (0.0%) [0.00, 1.00] | 0/60 (0.0%) | ❌ FAIL |

> **GATE FAILED.** Per §8 no verdict is issued for any arm. An attacker that cannot identify the domain from the unmodified original means the task or the labels are broken, and every husk number below would be measuring the harness rather than the husk.

## 2. Arm B — forced choice (pre-registered primary endpoint, §6.1)

Chance on a 12-option menu is 0.083. **BLIND, not chance, is the baseline C1 is measured against** (§3).

> ⚠️ **This table measures RECOGNITION, not recall, and the difference is large enough to change what the result means.** The attacker is handed twelve options with the correct one among them. Picking it off a list is far easier than describing the domain cold, and the two endpoints disagree sharply — on the first domain measured, `llm-translation` scored **71.7% on the menu but 21.7% in free text**, against a `source` control of 100% and 93.8%. C1 is phrased in terms of THIS table, so C1 can fail while the husk is still removing most of the free-text signal — and that is what happened. Read §4 and §5b before quoting anything from here.

| arm | `Kimi-K3:baseten` | `DeepSeek-V4-Pro-0813:baseten` | **panel max** |
|---|---|---|---|
| `structure-only` | 13/25 (52.0%)<br><sub>[0.33, 0.70]</sub> | 14/30 (46.7%)<br><sub>[0.30, 0.64]</sub> | **0.520** |
| `structure-only-nonum` | 14/26 (53.8%)<br><sub>[0.35, 0.71]</sub> | 15/30 (50.0%)<br><sub>[0.33, 0.67]</sub> | **0.538** |

§7 and §12.1: the headline is the **maximum** across the panel, never the mean — averaging a strong attacker against a weak one launders a failure.

### 2b. Corrected for attacker response bias (A4.1)

Each attacker's answers are held fixed and the true labels permuted 10,000 times across **source files** (§9's clustering rule, replicates carried with their file). `corrected` is observed minus that null; `p` is how often response bias alone reaches the observed value.

| arm | attacker | n | observed | permuted null | **corrected** | p | modal answer |
|---|---|---:|---:|---:|---:|---:|---|
| `structure-only-nonum` | DeepSeek-V4-Pro-0813 | 30 | 0.500 | 0.243 [0.10, 0.40] | **+0.257** | 0.0008 | ham-radio-logbook 10/30 |
| `structure-only-nonum` | Kimi-K3 | 26 | 0.538 | 0.273 [0.12, 0.42] | **+0.265** | 0.0023 | ham-radio-logbook 9/26 |
| `structure-only` | DeepSeek-V4-Pro-0813 | 30 | 0.467 | 0.232 [0.10, 0.37] | **+0.234** | 0.0014 | ham-radio-logbook 9/30 |
| `structure-only` | Kimi-K3 | 25 | 0.520 | 0.276 [0.12, 0.44] | **+0.244** | 0.0031 | seismic-monitoring 11/25 |

Full detail, including the analytic cross-check and the leak-channel attribution, is in `permutation.md` beside this file.

### Accuracy at confidence ≥ 0.7 (§6.1)

| arm | `Kimi-K3:baseten` | `DeepSeek-V4-Pro-0813:baseten` |
|---|---|---|
| `structure-only` | 11/11 (100.0%) | 13/24 (54.2%) |
| `structure-only-nonum` | 8/8 (100.0%) | 13/19 (68.4%) |

### Per-domain accuracy (§9 — always reported)

One leaky domain is invisible in an aggregate and is exactly the case that matters.

| arm | attacker | `ham-radio-logbook` | `seismic-monitoring` | `water-utility-metering` |
|---|---|---|---|---|
| `structure-only` | `Kimi-K3:baseten` | 5/8 (62.5%) | 7/10 (70.0%) | 1/7 (14.3%) |
| `structure-only` | `DeepSeek-V4-Pro-0813:baseten` | 5/10 (50.0%) | 6/10 (60.0%) | 3/10 (30.0%) |
| `structure-only-nonum` | `Kimi-K3:baseten` | 5/9 (55.6%) | 6/9 (66.7%) | 3/8 (37.5%) |
| `structure-only-nonum` | `DeepSeek-V4-Pro-0813:baseten` | 6/10 (60.0%) | 6/10 (60.0%) | 3/10 (30.0%) |

## 3. Verdicts (§8)

| solution | p_husk (strongest attacker) | p_blind (same attacker) | attacker | 95% CI on difference (cluster bootstrap over source files) | verdict |
|---|---|---|---|---|---|
| `structure-only` | 13/25 (52.0%) | — | `Kimi-K3:baseten` | — | **NOT COMPUTABLE — no BLIND arm in this run.** Read §2b: these arms are interpreted against their own permuted baseline (A4.1), not against BLIND. |
| `structure-only-nonum` | 14/26 (53.8%) | — | `Kimi-K3:baseten` | — | **NOT COMPUTABLE — no BLIND arm in this run.** Read §2b: these arms are interpreted against their own permuted baseline (A4.1), not against BLIND. |

> **INCONCLUSIVE is reported as inconclusive** — never as support for C1, never as "no evidence of leakage." (§8, registered literally so it cannot be softened later.)

## 4. Arm A — open ended (§6.2). Can only FALSIFY C1, never support it.

### 4.1 Deterministic leak-term pre-check — no model, fully reproducible

| arm | attacker | guesses containing a source-domain leak term | veto |
|---|---|---|---|

## 5. Mechanism — copied source vs successful re-identification

*Not pre-registered. Descriptive, and reported as such.* Measured with the shipped `app/solutions/_husk_check.inspect`, the same implementation the request-path gate uses, so this cannot drift from what the service enforces.

| arm | mean copied-span share when attacker was RIGHT | when WRONG | n right / n wrong |
|---|---|---|---|
| `structure-only` | 0.060 | 0.069 | 27 / 28 |
| `structure-only-nonum` | 0.055 | 0.077 | 29 / 27 |

A higher figure in the first column than the second means the attacker succeeded disproportionately on husks that had returned more of their own source verbatim — i.e. the leak is *copying*, which is a fixable defect with a gate already built for it. Similar figures mean the leak survives a genuine rewrite, which is the harder and more interesting result and is what `docs/working-paper.md` §4.2 predicts.

## 5b. What this corpus cannot test

Every source domain here is **synthetic** — fabricated for this evaluation, modelling no real institution, product, vendor or system. The threat model the project states it cares about is *"the organization, the product line, the proprietary algorithm, the regulatory domain"* (§6.2). **None of those exist in this corpus**, so identifier-level re-identification is not merely unmeasured here — it is untestable by construction.

The check that shows it: on the **unhusked SOURCE** control the attacker named a real outside entity on only a minority of items, and the names it produced do not appear in the corpus at all — they were plausible guesses about the sector, not recoveries. The ceiling for identifier-level recovery on synthetic input is therefore near zero for *every* arm, husked or not, and no arm can be credited or blamed for it.

Consequence for the writeup: this experiment measures **problem-domain** leakage and nothing narrower. A result here, in either direction, says nothing about whether a husk protects a real organization's identity. Testing that needs real proprietary source with real identifiers in it — a different experiment, with different consent and handling requirements.

## 6. Power, registered in advance (§10)

With 30 clustered source files this design reliably resolves a difference of ~0.20–0.25 and **cannot resolve differences below ~0.10**. A null result therefore means *"no leak detectable at this corpus scale"* — **not** that the husk is private.

