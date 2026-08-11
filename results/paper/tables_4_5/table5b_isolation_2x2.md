# Table 5b — ventilation and latent, isolated (the 2×2)

**Source: a separate 2×2 measured for this table — four states cherry-picked from the same vendored baseline onto the same closure-capable instrument as Part 2. Three extra engine runs.**

Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. **Not cumulative**: every column starts from the unmodified engine, so C1 is the ventilation fix alone, C2 is the latent fix alone, and C3 is both.

This form exists because the cumulative trajectory structurally cannot produce it — the latent fix applied *without* the ventilation fix is not a state on that path — and neither can the six-state closed-balance harness, whose second state is ventilation and latent already combined. It is the only way to make the interaction claim.

`Base` is reconciled against the Part 2 trajectory's `Baseline` row to 0.0e+00 kWh before this table is written: same engine, same weather, so a disagreement would mean the two tables describe different buildings.

| Metric | Base | C1 · ventilation | C2 · latent | C3 · both | C1 · ventilation vs Base | C2 · latent vs Base | C3 · both vs Base |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Sensible heating (kWh) | 1,779.36 | 2,184.93 | 1,779.36 | 2,184.93 | +22.79 % | +0.00 % | +22.79 % |
| Sensible cooling (kWh) | 640.84 | 496.81 | 640.84 | 496.81 | -22.47 % | +0.00 % | -22.47 % |
| Ventilation + infiltration loss (kWh) | 2,031.91 | 2,887.91 | 2,031.91 | 2,887.91 | +42.13 % | +0.00 % | +42.13 % |
| Latent cooling, gated (kWh) | 26.12 | 26.66 | 18.21 | 15.53 | +2.06 % | -30.29 % | -40.55 % |
| Latent cooling, ungated (kWh) | 900.05 | 1,141.07 | 512.02 | 631.47 | +26.78 % | -43.11 % | -29.84 % |
| Latent heating (kWh) | 152.6506 | 183.9370 | 0.0000 | 0.0029 | +20.50 % | -100.00 % | -100.00 % |
| Total energy need (kWh) | 2,598.97 | 2,892.34 | 2,438.41 | 2,697.27 | +11.29 % | -6.18 % | +3.78 % |

### Closure, per state

| State | V2 residual (kWh) | V2 residual (%) | < 5 %? | Transmission items |
| --- | ---: | ---: | :-: | ---: |
| Base | -96.72 | -1.16 % | PASS | 7 |
| C1 · ventilation | -87.46 | -1.01 % | PASS | 7 |
| C2 · latent | -96.72 | -1.16 % | PASS | 7 |
| C3 · both | -87.46 | -1.01 % | PASS | 7 |

