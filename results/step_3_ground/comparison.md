| State | Branch | Adds | Heating (kWh) | Cooling (kWh) | Total internal gains (kWh) | Ground loss (kWh) | Ground gain (kWh) | Ventilation+infiltration loss (kWh) | Total energy need (kWh) | Total energy need (kWh/m2) | % vs previous step | % vs original baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | claude/pybuildingenergy-baseline-anjro8 | Unmodified ISO 52016-1 | 1,308.60 | 741.83 | 5,356.69 | 90.20 | 2.77 | 1,868.48 | 3,457.16 | 172.86 | n/a | +0.00% |
| +Vent+Latent | claude/ventilation-plus-latent-fix | Ventilation flow-rate + symmetric latent fix | 1,522.61 | 646.25 | 5,356.69 | 84.70 | 3.28 | 2,377.31 | 2,573.53 | 128.68 | -25.56% | -25.56% |
| +Internal Gains | claude/internal-gains-fix | Step 1 — neighbour-count gain inflation removed | 3,228.23 | 308.30 | 730.29 | 63.12 | 7.80 | 1,796.62 | 4,207.23 | 210.36 | +63.48% | +21.70% |
| +Conditioned Zones | claude/conditioned-adjacent-zones-fix | Step 2 — conditioned neighbours held at their setpoint | 123.39 | 20.06 | 730.29 | 68.81 | 2.19 | 2,096.26 | 697.10 | 34.85 | -83.43% | -79.84% |
| +Ground Fix | claude/ground-contact-fix | Step 3 — no implicit slab-on-ground fallback | 123.39 | 20.06 | 730.29 | 0.00 | 0.00 | 2,096.26 | 697.10 | 34.85 | +0.00% | -79.84% |
