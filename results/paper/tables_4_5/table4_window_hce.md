# Table 4 — the window and h_ce corrections (Base / C1 / C2)

**Source: the Part 2 canonical trajectory, states 1–3. No separate harness, no extra engine run — these are the same measurements as rows 1–3 of the trajectory table.**

Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. Cumulative: C1 is Base plus the dynamic window correction; C2 is C1 plus the wind-dependent external convective coefficient. Both are the *literature* corrections and both precede the found defects, which is the methodology order.

C1 changes two things at once and the paper should say so: the angular correction factor `F_w(θ)` on transmitted solar **and** a wind-dependent thermal transmittance on the windows. C2 then extends that transmittance to the opaque envelope. Both halves are switchable (`window_convection_model="table"` keeps the ISO constant film on the glazing, `window_angular_solar_model="none"` gives the complement), so the angle effect can be isolated without changing the branch structure.

| Metric | Baseline | +C1 dynamic window | +C2 wind-dependent h_ce | +C1 dynamic window vs Baseline | +C2 wind-dependent h_ce vs Baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sensible heating (kWh) | 1,779.36 | 1,783.96 | 1,788.11 | +0.26 % | +0.49 % |
| Sensible cooling (kWh) | 640.84 | 606.07 | 580.77 | -5.43 % | -9.37 % |
| Solar gains (kWh) | 810.54 | 709.55 | 709.55 | -12.46 % | -12.46 % |
| Window transmission loss (kWh) | 334.33 | 337.44 | 336.23 | +0.93 % | +0.57 % |
| Opaque transmission loss (kWh) | 429.61 | 428.73 | 436.69 | -0.21 % | +1.65 % |
| Total transmission loss (kWh) | 5,398.24 | 5,349.68 | 5,374.74 | -0.90 % | -0.44 % |

### Closure, per state

| State | V2 residual (kWh) | V2 residual (%) | < 5 %? | Transmission items |
| --- | ---: | ---: | :-: | ---: |
| Baseline | -96.72 | -1.16 % | PASS | 7 |
| +C1 dynamic window | -95.97 | -1.17 % | PASS | 7 |
| +C2 wind-dependent h_ce | -95.69 | -1.17 % | PASS | 7 |

