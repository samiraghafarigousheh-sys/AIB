# Table 5a — ventilation and latent, in methodology order

**Source: the Part 2 canonical trajectory, states 3–5. No extra engine run.**

Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. **Cumulative**, so each column is the previous one plus exactly one fix, and the baseline for this step is the state the trajectory has actually reached by then (`+C2`), not the unmodified engine.

This is the form to cite if the results text is written in methodology order. It answers "what does each fix add, at the point the methodology applies it". It does **not** answer "do the two fixes interact" — for that, see Table 5b, which is the 2×2.

| Metric | Before (= +C2) | +Ventilation | +Latent (cumulative) | +Ventilation vs Before (= +C2) | +Latent (cumulative) vs Before (= +C2) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sensible heating (kWh) | 1,788.11 | 2,057.79 | 2,057.79 | +15.08 % | +15.08 % |
| Sensible cooling (kWh) | 580.77 | 488.00 | 488.00 | -15.97 % | -15.97 % |
| Ventilation + infiltration loss (kWh) | 2,010.58 | 2,581.45 | 2,581.45 | +28.39 % | +28.39 % |
| Latent cooling, gated (kWh) | 25.02 | 24.93 | 15.38 | -0.37 % | -38.52 % |
| Latent cooling, ungated (kWh) | 906.29 | 1,068.20 | 593.69 | +17.87 % | -34.49 % |
| Latent heating (kWh) | 152.9055 | 174.1352 | 0.0033 | +13.88 % | -100.00 % |
| Total energy need (kWh) | 2,546.80 | 2,744.86 | 2,561.18 | +7.78 % | +0.56 % |

### Closure, per state

| State | V2 residual (kWh) | V2 residual (%) | < 5 %? | Transmission items |
| --- | ---: | ---: | :-: | ---: |
| Before (= +C2) | -95.69 | -1.17 % | PASS | 7 |
| +Ventilation | -89.34 | -1.07 % | PASS | 7 |
| +Latent (cumulative) | -89.34 | -1.07 % | PASS | 7 |

