# Table 5b — ventilation and latent, isolated (the 2×2)

**Source: a separate 2×2 measured for this table — four states cherry-picked from the same vendored baseline onto the same closure-capable instrument as Part 2. Three extra engine runs.**

Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. **Not cumulative**: every column starts from the unmodified engine, so C1 is the ventilation fix alone, C2 is the latent fix alone, and C3 is both.

This form exists because the cumulative trajectory structurally cannot produce it — the latent fix applied *without* the ventilation fix is not a state on that path — and neither can the six-state closed-balance harness, whose second state is ventilation and latent already combined. It is the only way to make the interaction claim.

`Base` is reconciled against the Part 2 trajectory's `Baseline` row to 0.0e+00 kWh before this table is written: same engine, same weather, so a disagreement would mean the two tables describe different buildings.

| Metric | Base | C1 · ventilation | C2 · latent | C3 · both | C1 · ventilation vs Base | C2 · latent vs Base | C3 · both vs Base |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Sensible heating (kWh) | 1,779.36 | 2,046.50 | 1,779.36 | 2,046.50 | +15.01 % | +0.00 % | +15.01 % |
| Sensible cooling (kWh) | 640.84 | 541.75 | 640.84 | 541.75 | -15.46 % | +0.00 % | -15.46 % |
| Ventilation + infiltration loss (kWh) | 2,031.91 | 2,606.92 | 2,031.91 | 2,606.92 | +28.30 % | +0.00 % | +28.30 % |
| Latent cooling, gated (kWh) | 26.12 | 26.40 | 18.21 | 16.37 | +1.08 % | -30.29 % | -37.34 % |
| Latent cooling, ungated (kWh) | 900.05 | 1,061.23 | 512.02 | 591.09 | +17.91 % | -43.11 % | -34.33 % |
| Latent heating (kWh) | 152.6506 | 173.6289 | 0.0000 | 0.0015 | +13.74 % | -100.00 % | -100.00 % |
| Total energy need (kWh) | 2,598.97 | 2,788.29 | 2,438.41 | 2,604.62 | +7.28 % | -6.18 % | +0.22 % |

### Closure, per state

| State | V2 residual (kWh) | V2 residual (%) | < 5 %? | Transmission items |
| --- | ---: | ---: | :-: | ---: |
| Base | -96.72 | -1.16 % | PASS | 7 |
| C1 · ventilation | -90.36 | -1.06 % | PASS | 7 |
| C2 · latent | -96.72 | -1.16 % | PASS | 7 |
| C3 · both | -90.36 | -1.06 % | PASS | 7 |

