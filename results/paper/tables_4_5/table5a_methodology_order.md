# Table 5a — ventilation and latent, in methodology order

**Source: the Part 2 canonical trajectory, states 3–5. No extra engine run.**

Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. **Cumulative**, so each column is the previous one plus exactly one fix, and the baseline for this step is the state the trajectory has actually reached by then (`+C2`), not the unmodified engine.

This is the form to cite if the results text is written in methodology order. It answers "what does each fix add, at the point the methodology applies it". It does **not** answer "do the two fixes interact" — for that, see Table 5b, which is the 2×2.

| Metric | Before (= +C2) | +Ventilation | +Latent (cumulative) | +Ventilation vs Before (= +C2) | +Latent (cumulative) vs Before (= +C2) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sensible heating (kWh) | 1,788.11 | 2,197.42 | 2,197.42 | +22.89 % | +22.89 % |
| Sensible cooling (kWh) | 580.77 | 445.68 | 445.68 | -23.26 % | -23.26 % |
| Ventilation + infiltration loss (kWh) | 2,010.58 | 2,860.65 | 2,860.65 | +42.28 % | +42.28 % |
| Latent cooling, gated (kWh) | 25.02 | 25.10 | 14.53 | +0.31 % | -41.92 % |
| Latent cooling, ungated (kWh) | 906.29 | 1,148.49 | 634.24 | +26.72 % | -30.02 % |
| Latent heating (kWh) | 152.9055 | 184.9387 | 0.0047 | +20.95 % | -100.00 % |
| Total energy need (kWh) | 2,546.80 | 2,853.14 | 2,657.64 | +12.03 % | +4.35 % |

### Closure, per state

| State | V2 residual (kWh) | V2 residual (%) | < 5 %? | Transmission items |
| --- | ---: | ---: | :-: | ---: |
| Before (= +C2) | -95.69 | -1.17 % | PASS | 7 |
| +Ventilation | -86.45 | -1.01 % | PASS | 7 |
| +Latent (cumulative) | -86.45 | -1.01 % | PASS | 7 |

