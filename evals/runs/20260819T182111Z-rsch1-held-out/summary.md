# RSCH-1 — results

**Run:** `20260819T182111Z-rsch1-held-out`  ·  **split:** `held-out`  ·  **sources:** 30
**Pre-registration commit:** `ae7f53ac9402ad45fb1ace7cce522bdb0ca55689` (§12 rule 4)
**Repo commit:** `c423c3dcf5032f35ac6a50d77562a185d2822b20`  ⚠️ **working tree dirty**
**Attackers:** moonshotai/Kimi-K3:baseten, deepseek-ai/DeepSeek-V4-Pro-0813:baseten  ·  **judge:** zai-org/GLM-5.2:baseten
**Rewriter:** Qwen/Qwen2.5-Coder-7B-Instruct  ·  endpoint `router.huggingface.co`

> ⚠️ **COVERAGE: 986/998 calls completed; 12 never reached the model** (transport failure — this run hit an account spending cap mid-flight). Those are excluded from every rate below as missing observations rather than scored incorrect, because nothing was asked and nothing was answered. **Check the per-domain table before reading any aggregate: a domain the run never got to will look absent, not clean.**

## 1. Validity gate (§8) — evaluated first

If this fails, **no verdict is issued for any arm**.

| attacker | p_source | parse failure (all arms) | gate |
|---|---|---|---|
| `moonshotai/Kimi-K3:baseten` | 30/30 (100.0%) [0.89, 1.00] | 0/242 (0.0%) | ✅ pass |
| `deepseek-ai/DeepSeek-V4-Pro-0813:baseten` | 30/30 (100.0%) [0.89, 1.00] | 5/249 (2.0%) | ✅ pass |

## 2. Arm B — forced choice (pre-registered primary endpoint, §6.1)

Chance on a 12-option menu is 0.083. **BLIND, not chance, is the baseline C1 is measured against** (§3).

> ⚠️ **This table measures RECOGNITION, not recall, and the difference is large enough to change what the result means.** The attacker is handed twelve options with the correct one among them. Picking it off a list is far easier than describing the domain cold, and the two endpoints disagree sharply — on the first domain measured, `llm-translation` scored **71.7% on the menu but 21.7% in free text**, against a `source` control of 100% and 93.8%. C1 is phrased in terms of THIS table, so C1 can fail while the husk is still removing most of the free-text signal — and that is what happened. Read §4 and §5b before quoting anything from here.

| arm | `Kimi-K3:baseten` | `DeepSeek-V4-Pro-0813:baseten` | **panel max** |
|---|---|---|---|
| `blind` | 10/30 (33.3%)<br><sub>[0.19, 0.51]</sub> | 10/30 (33.3%)<br><sub>[0.19, 0.51]</sub> | **0.333** |
| `source` | 30/30 (100.0%)<br><sub>[0.89, 1.00]</sub> | 30/30 (100.0%)<br><sub>[0.89, 1.00]</sub> | **1.000** |
| `fpe` | 30/30 (100.0%)<br><sub>[0.89, 1.00]</sub> | 30/30 (100.0%)<br><sub>[0.89, 1.00]</sub> | **1.000** |
| `literal-tagging` | 30/30 (100.0%)<br><sub>[0.89, 1.00]</sub> | 30/30 (100.0%)<br><sub>[0.89, 1.00]</sub> | **1.000** |
| `composed` | 30/30 (100.0%)<br><sub>[0.89, 1.00]</sub> | 30/30 (100.0%)<br><sub>[0.89, 1.00]</sub> | **1.000** |
| `llm-translation` | 65/83 (78.3%)<br><sub>[0.68, 0.86]</sub> | 62/90 (68.9%)<br><sub>[0.59, 0.78]</sub> | **0.783** |

§7 and §12.1: the headline is the **maximum** across the panel, never the mean — averaging a strong attacker against a weak one launders a failure.

### 2b. Corrected for attacker response bias (A4.1)

Each attacker's answers are held fixed and the true labels permuted 10,000 times across **source files** (§9's clustering rule, replicates carried with their file). `corrected` is observed minus that null; `p` is how often response bias alone reaches the observed value.

| arm | attacker | n | observed | permuted null | **corrected** | p | modal answer |
|---|---|---:|---:|---:|---:|---:|---|
| `blind` | DeepSeek-V4-Pro-0813 | 29 | 0.345 | 0.320 [0.24, 0.38] | **+0.025** | 0.4090 | ham-radio-logbook 26/29 |
| `blind` | Kimi-K3 | 30 | 0.333 | 0.300 [0.20, 0.40] | **+0.033** | 0.3870 | ham-radio-logbook 23/30 |
| `composed` | DeepSeek-V4-Pro-0813 | 30 | 1.000 | 0.332 [0.17, 0.50] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `composed` | Kimi-K3 | 30 | 1.000 | 0.332 [0.17, 0.50] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `fpe` | DeepSeek-V4-Pro-0813 | 30 | 1.000 | 0.332 [0.17, 0.50] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `fpe` | Kimi-K3 | 30 | 1.000 | 0.332 [0.17, 0.50] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `literal-tagging` | DeepSeek-V4-Pro-0813 | 30 | 1.000 | 0.332 [0.17, 0.50] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `literal-tagging` | Kimi-K3 | 30 | 1.000 | 0.332 [0.17, 0.50] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `llm-translation-ungated` | DeepSeek-V4-Pro-0813 | 9 | 1.000 | 1.000 [1.00, 1.00] | **+0.000** | 1.0000 | water-utility-metering 9/9 |
| `llm-translation-ungated` | Kimi-K3 | 9 | 1.000 | 1.000 [1.00, 1.00] | **+0.000** | 1.0000 | water-utility-metering 9/9 |
| `llm-translation` | DeepSeek-V4-Pro-0813 | 86 | 0.721 | 0.282 [0.14, 0.43] | **+0.439** | 0.0000 | seismic-monitoring 34/86 |
| `llm-translation` | Kimi-K3 | 83 | 0.783 | 0.304 [0.16, 0.47] | **+0.479** | 0.0000 | seismic-monitoring 30/83 |
| `source` | DeepSeek-V4-Pro-0813 | 30 | 1.000 | 0.332 [0.17, 0.50] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `source` | Kimi-K3 | 30 | 1.000 | 0.332 [0.17, 0.50] | **+0.668** | 0.0000 | water-utility-metering 10/30 |

Full detail, including the analytic cross-check and the leak-channel attribution, is in `permutation.md` beside this file.

### Accuracy at confidence ≥ 0.7 (§6.1)

| arm | `Kimi-K3:baseten` | `DeepSeek-V4-Pro-0813:baseten` |
|---|---|---|
| `blind` | — | 1/1 (100.0%) |
| `source` | 30/30 (100.0%) | 30/30 (100.0%) |
| `fpe` | 30/30 (100.0%) | 30/30 (100.0%) |
| `literal-tagging` | 30/30 (100.0%) | 30/30 (100.0%) |
| `composed` | 30/30 (100.0%) | 30/30 (100.0%) |
| `llm-translation` | 54/56 (96.4%) | 61/72 (84.7%) |

### Per-domain accuracy (§9 — always reported)

One leaky domain is invisible in an aggregate and is exactly the case that matters.

| arm | attacker | `ham-radio-logbook` | `seismic-monitoring` | `water-utility-metering` |
|---|---|---|---|---|
| `blind` | `Kimi-K3:baseten` | 8/10 (80.0%) | 0/10 (0.0%) | 2/10 (20.0%) |
| `blind` | `DeepSeek-V4-Pro-0813:baseten` | 9/10 (90.0%) | 1/10 (10.0%) | 0/10 (0.0%) |
| `source` | `Kimi-K3:baseten` | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| `source` | `DeepSeek-V4-Pro-0813:baseten` | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| `fpe` | `Kimi-K3:baseten` | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| `fpe` | `DeepSeek-V4-Pro-0813:baseten` | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| `literal-tagging` | `Kimi-K3:baseten` | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| `literal-tagging` | `DeepSeek-V4-Pro-0813:baseten` | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| `composed` | `Kimi-K3:baseten` | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| `composed` | `DeepSeek-V4-Pro-0813:baseten` | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| `llm-translation` | `Kimi-K3:baseten` | 21/26 (80.8%) | 24/28 (85.7%) | 20/29 (69.0%) |
| `llm-translation` | `DeepSeek-V4-Pro-0813:baseten` | 19/30 (63.3%) | 24/30 (80.0%) | 19/30 (63.3%) |

## 3. Verdicts (§8)

| solution | p_husk (strongest attacker) | p_blind (same attacker) | attacker | 95% CI on difference (cluster bootstrap over source files) | verdict |
|---|---|---|---|---|---|
| `fpe` | 30/30 (100.0%) | 10/30 (33.3%) | `Kimi-K3:baseten` | [+0.500, +0.833] | **FAIL** |
| `literal-tagging` | 30/30 (100.0%) | 10/30 (33.3%) | `Kimi-K3:baseten` | [+0.500, +0.833] | **FAIL** |
| `composed` | 30/30 (100.0%) | 10/30 (33.3%) | `Kimi-K3:baseten` | [+0.500, +0.833] | **FAIL** |
| `llm-translation` | 65/83 (78.3%) | 10/30 (33.3%) | `Kimi-K3:baseten` | [+0.243, +0.640] | **FAIL** |

> **INCONCLUSIVE is reported as inconclusive** — never as support for C1, never as "no evidence of leakage." (§8, registered literally so it cannot be softened later.)

## 4. Arm A — open ended (§6.2). Can only FALSIFY C1, never support it.

### 4.1 Deterministic leak-term pre-check — no model, fully reproducible

| arm | attacker | guesses containing a source-domain leak term | veto |
|---|---|---|---|
| `blind` | `Kimi-K3:baseten` | 0/30 (0.0%) | — |
| `blind` | `DeepSeek-V4-Pro-0813:baseten` | 0/30 (0.0%) | — |
| `source` | `Kimi-K3:baseten` | 29/30 (96.7%) | — |
| `source` | `DeepSeek-V4-Pro-0813:baseten` | 30/30 (100.0%) | — |
| `fpe` | `Kimi-K3:baseten` | 28/30 (93.3%) | 🚫 **FAIL — hard veto** |
| `fpe` | `DeepSeek-V4-Pro-0813:baseten` | 27/30 (90.0%) | 🚫 **FAIL — hard veto** |
| `literal-tagging` | `Kimi-K3:baseten` | 27/30 (90.0%) | 🚫 **FAIL — hard veto** |
| `literal-tagging` | `DeepSeek-V4-Pro-0813:baseten` | 29/30 (96.7%) | 🚫 **FAIL — hard veto** |
| `composed` | `Kimi-K3:baseten` | 22/29 (75.9%) | 🚫 **FAIL — hard veto** |
| `composed` | `DeepSeek-V4-Pro-0813:baseten` | 21/30 (70.0%) | 🚫 **FAIL — hard veto** |
| `llm-translation` | `Kimi-K3:baseten` | 43/86 (50.0%) | 🚫 **FAIL — hard veto** |
| `llm-translation` | `DeepSeek-V4-Pro-0813:baseten` | 41/90 (45.6%) | 🚫 **FAIL — hard veto** |

> **Hard veto fired (§8).** A solution whose open-ended guesses hit its own source-domain leak terms on ≥ 10% of items is **FAIL regardless of its forced-choice result**. Solutions vetoed: `fpe`, `literal-tagging`, `composed`, `llm-translation`

### 4.2 Judge (§6.2 pass 2)

| arm | MATCH | RELATED | MISS | unparsed |
|---|---|---|---|---|
| `blind` | 0 | 2 | 57 | 0 |
| `source` | 60 | 0 | 0 | 0 |
| `fpe` | 60 | 0 | 0 | 0 |
| `literal-tagging` | 59 | 1 | 0 | 0 |
| `composed` | 51 | 3 | 3 | 0 |
| `llm-translation` | 86 | 7 | 80 | 0 |

> **κ is OWED and this table is therefore DESCRIPTIVE ONLY.** §6.2 requires a random 20% of these hand-labelled and Cohen's κ reported, and registers in advance that **if κ < 0.6 only the deterministic pre-check counts as evidence**. Until the hand-labelling is done the weaker reading applies, because an unmeasured κ cannot be assumed to pass.

    python3 evals/kappa_judge.py --sample 20260819T182111Z-rsch1-held-out
    # fill in human_label on each row, then:
    python3 evals/kappa_judge.py --score  20260819T182111Z-rsch1-held-out

## 5. Mechanism — copied source vs successful re-identification

*Not pre-registered. Descriptive, and reported as such.* Measured with the shipped `app/solutions/_husk_check.inspect`, the same implementation the request-path gate uses, so this cannot drift from what the service enforces.

| arm | mean copied-span share when attacker was RIGHT | when WRONG | n right / n wrong |
|---|---|---|---|
| `fpe` | 0.058 | nan | 60 / 0 |
| `literal-tagging` | 0.450 | nan | 60 / 0 |
| `composed` | 0.000 | nan | 60 / 0 |
| `llm-translation` | 0.269 | 0.276 | 127 / 53 |

A higher figure in the first column than the second means the attacker succeeded disproportionately on husks that had returned more of their own source verbatim — i.e. the leak is *copying*, which is a fixable defect with a gate already built for it. Similar figures mean the leak survives a genuine rewrite, which is the harder and more interesting result and is what `docs/working-paper.md` §4.2 predicts.

## 5b. What this corpus cannot test

Every source domain here is **synthetic** — fabricated for this evaluation, modelling no real institution, product, vendor or system. The threat model the project states it cares about is *"the organization, the product line, the proprietary algorithm, the regulatory domain"* (§6.2). **None of those exist in this corpus**, so identifier-level re-identification is not merely unmeasured here — it is untestable by construction.

The check that shows it: on the **unhusked SOURCE** control the attacker named a real outside entity on only a minority of items, and the names it produced do not appear in the corpus at all — they were plausible guesses about the sector, not recoveries. The ceiling for identifier-level recovery on synthetic input is therefore near zero for *every* arm, husked or not, and no arm can be credited or blamed for it.

Consequence for the writeup: this experiment measures **problem-domain** leakage and nothing narrower. A result here, in either direction, says nothing about whether a husk protects a real organization's identity. Testing that needs real proprietary source with real identifiers in it — a different experiment, with different consent and handling requirements.

## 6. Power, registered in advance (§10)

With 30 clustered source files this design reliably resolves a difference of ~0.20–0.25 and **cannot resolve differences below ~0.10**. A null result therefore means *"no leak detectable at this corpus scale"* — **not** that the husk is private.

