| State | Branch | Adds | Heating (kWh) | Cooling (kWh) | Total internal gains (kWh) | Ground loss (kWh) | Ground gain (kWh) | Ventilation+infiltration loss (kWh) | Total energy need (kWh) | Total energy need (kWh/m2) | % vs previous step | % vs original baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | claude/pybuildingenergy-baseline-anjro8 | Unmodified ISO 52016-1 | 15.86 | 2,027.51 | 5,356.69 | 192.44 | 42.43 | 2,829.27 | 3,775.59 | 188.78 | n/a | +0.00% |
| +Vent+Latent | claude/ventilation-plus-latent-fix | Ventilation flow-rate + symmetric latent fix | 37.34 | 1,727.18 | 5,356.69 | 175.56 | 47.24 | 3,235.42 | 2,070.83 | 103.54 | -45.15% | -45.15% |
| +Internal Gains | claude/internal-gains-fix | Step 1 — neighbour-count gain inflation removed | 1,274.56 | 699.85 | 730.29 | 139.04 | 74.57 | 1,846.06 | 2,615.90 | 130.79 | +26.32% | -30.72% |
