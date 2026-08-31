# Permutation baseline — 20260819T182111Z-rsch1-held-out

10,000 permutations, seed 20260819, labels permuted across SOURCE FILES
(prereg §9 clustering), replicates carried with their file.

`corrected` = observed − permuted mean. `p` = P(response bias alone reaches observed).

| arm | attacker | n | observed | permuted | corrected | p | modal answer |
|---|---|---:|---:|---:|---:|---:|---|
| `blind` | DeepSeek-V4-Pro-0813 | 29 | 0.345 | 0.320 [0.241, 0.379] | **+0.025** | 0.4090 | ham-radio-logbook 26/29 |
| `blind` | Kimi-K3 | 30 | 0.333 | 0.300 [0.200, 0.400] | **+0.033** | 0.3870 | ham-radio-logbook 23/30 |
| `composed` | DeepSeek-V4-Pro-0813 | 30 | 1.000 | 0.332 [0.167, 0.500] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `composed` | Kimi-K3 | 30 | 1.000 | 0.332 [0.167, 0.500] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `fpe` | DeepSeek-V4-Pro-0813 | 30 | 1.000 | 0.332 [0.167, 0.500] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `fpe` | Kimi-K3 | 30 | 1.000 | 0.332 [0.167, 0.500] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `literal-tagging` | DeepSeek-V4-Pro-0813 | 30 | 1.000 | 0.332 [0.167, 0.500] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `literal-tagging` | Kimi-K3 | 30 | 1.000 | 0.332 [0.167, 0.500] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `llm-translation-ungated` | DeepSeek-V4-Pro-0813 | 9 | 1.000 | 1.000 [1.000, 1.000] | **+0.000** | 1.0000 | water-utility-metering 9/9 |
| `llm-translation-ungated` | Kimi-K3 | 9 | 1.000 | 1.000 [1.000, 1.000] | **+0.000** | 1.0000 | water-utility-metering 9/9 |
| `llm-translation` | DeepSeek-V4-Pro-0813 | 86 | 0.721 | 0.282 [0.140, 0.430] | **+0.439** | 0.0000 | seismic-monitoring 34/86 |
| `llm-translation` | Kimi-K3 | 83 | 0.783 | 0.304 [0.157, 0.470] | **+0.479** | 0.0000 | seismic-monitoring 30/83 |
| `source` | DeepSeek-V4-Pro-0813 | 30 | 1.000 | 0.332 [0.167, 0.500] | **+0.668** | 0.0000 | water-utility-metering 10/30 |
| `source` | Kimi-K3 | 30 | 1.000 | 0.332 [0.167, 0.500] | **+0.668** | 0.0000 | water-utility-metering 10/30 |

Analytic cross-check `Σ_d P(ans=d)·P(true=d)` agrees with the permuted mean to within **0.0037** across every cell.

## Leak-channel attribution — own-module name survival

The Go module name IS the domain in this corpus, and `llm_translation.py:133`
already forbids it surviving. Splitting by whether it did separates a fixable
rewriter defect from anything the architecture itself carries.

| arm | artifacts leaking module name | accuracy WHEN leaked | accuracy when removed |
|---|---|---:|---:|
| `composed` | 8/30 | 16/16 = 1.000 | 44/44 = 1.000 |
| `fpe` | 16/30 | 32/32 = 1.000 | 28/28 = 1.000 |
| `literal-tagging` | 11/30 | 22/22 = 1.000 | 38/38 = 1.000 |
| `llm-translation` | 22/90 | 44/44 = 1.000 | 83/125 = 0.664 |
| `source` | 19/30 | 38/38 = 1.000 | 22/22 = 1.000 |
