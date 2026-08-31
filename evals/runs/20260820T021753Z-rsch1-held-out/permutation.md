# Permutation baseline — 20260820T021753Z-rsch1-held-out

10,000 permutations, seed 20260819, labels permuted across SOURCE FILES
(prereg §9 clustering), replicates carried with their file.

`corrected` = observed − permuted mean. `p` = P(response bias alone reaches observed).

| arm | attacker | n | observed | permuted | corrected | p | modal answer |
|---|---|---:|---:|---:|---:|---:|---|
| `structure-only-nonum` | DeepSeek-V4-Pro-0813 | 30 | 0.500 | 0.243 [0.100, 0.400] | **+0.257** | 0.0008 | ham-radio-logbook 10/30 |
| `structure-only-nonum` | Kimi-K3 | 26 | 0.538 | 0.273 [0.115, 0.423] | **+0.265** | 0.0023 | ham-radio-logbook 9/26 |
| `structure-only` | DeepSeek-V4-Pro-0813 | 30 | 0.467 | 0.232 [0.100, 0.367] | **+0.234** | 0.0014 | ham-radio-logbook 9/30 |
| `structure-only` | Kimi-K3 | 25 | 0.520 | 0.276 [0.120, 0.440] | **+0.244** | 0.0031 | seismic-monitoring 11/25 |

Analytic cross-check `Σ_d P(ans=d)·P(true=d)` agrees with the permuted mean to within **0.0015** across every cell.
