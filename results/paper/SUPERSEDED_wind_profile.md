# SUPERSEDED — what the wind-profile correction changed

The preceding paper set is retained verbatim under `results/paper_pre_wind_profile/`. Nothing in it has been edited; this file records what was later found out about it and by how much the result set moved.

## The defect

Correction C2 replaces the ISO 13789 constant external convective coefficient with `h_ce = 4 + 4u`. The correlation wants the wind local to the building surface. The engine fed it the EPW wind column, which is a **10 m reading over open terrain at the meteorological station** — which asserts that the site and the station share both terrain class and measurement height. Apt 305 shares neither with Essendon Fields aerodrome.

The pivot at which `4u + 4` equals the ISO constant of 20 W/(m²·K) is u = 4 m/s. On the station column **59.8 %** of hours are above it. At Carlton's terrain and height only **29.4 %** are. **That is a change of side, not of degree.**

## The fourth input mismatch in the EnergyPlus validation

`Site:HeightVariation` is absent from both generated IDFs, so EnergyPlus fell back to the `Building` object's `Terrain` field — `Suburbs`, a = 0.22, δ = 370 m — and applied a terrain **and** height profile to every wind-exposed surface. The ISO side used the raw station column. Measured by re-running the committed IDF with the per-surface wind reported hourly:

| Engine | Wind driving the external film | Annual mean |
| --- | --- | ---: |
| EnergyPlus, as published | station × the `Suburbs` profile at z = 1.35 m | **2.23 m/s** |
| ISO 52016-1, as published | station column, unadjusted | **4.84 m/s** |
| ISO 52016-1, corrected | station × `suburban` at z = 6.75 m | **3.18 m/s** |

The two engines were driven by winds differing by a factor of 2.17. This is a fourth input mismatch of the same class as the three found in `results/paper/validation_corrected/`, and it is now closed on both sides: the ISO engine applies the profile, and the matched IDF's geometry is translated up so the west wall's centroid sits at the same z = 6.75 m.

## The headline finding: C2 reverses sign

The same engine, run twice, changing only the `h_ce` model — once on each wind. Both arms are on this engine tree, so nothing but the wind differs.

| | Station wind | Terrain-corrected | |
| --- | ---: | ---: | --- |
| Annual mean wind | 4.84 m/s | 3.18 m/s | × 0.6574 |
| Hours above the 4 m/s pivot | 59.8 % | 29.4 % | |
| Mean h_ce | 23.36 W/(m²·K) | 16.73 W/(m²·K) | ISO constant is 20 |
| Sensible cooling, ISO fixed h_ce | 18.14 kWh | 18.14 kWh | identical — the control arm |
| Sensible cooling, `4u + 4` | 13.41 kWh | 19.90 kWh | |
| **C2 effect on cooling** | **-4.73 kWh** | **+1.75 kWh** | **sign reverses** |
| C2 effect on heating | -0.35 kWh | -1.21 kWh | |

**C2 reverses sign on sensible cooling: -4.73 → +1.75 kWh.** On the station wind the dynamic coefficient sits above the ISO constant for most of the year, a stronger film sheds more of the absorbed solar off the west wall, and C2 *reduces* cooling. On the wind the wall actually sees, the coefficient sits below the constant for 70.6 % of the year, the film is weaker, the sol-air temperature rises, and C2 *increases* cooling.

The reported C2 result did rest on an unstated terrain assumption. Any text that describes C2 as reducing cooling is now wrong.

The control arm is identical to machine precision in both runs (18.1428 vs 18.1428 kWh): with `h_ce` on `table` the wind is never consumed, so anything other than the wind having changed would show up there.

## The canonical trajectory

The trajectory gains a fourteenth state. The thirteen before it are unchanged to the printed digit — each is a cherry-pick of one historical commit and none contains the wind profile — so all of the movement is in the last row.

Largest drift on `+Closure fixes` against the retained set: **0.00e+00 kWh**.

| | Superseded (`+Closure fixes`) | Canonical (`+Wind profile`) | Δ |
| --- | ---: | ---: | ---: |
| Sensible heating | 123.74 | **122.88** | -0.86 |
| Sensible cooling | 13.41 | **19.90** | +6.48 |
| Latent cooling, gated | 1.14 | **1.51** | +0.37 |
| Total (kWh/m²·yr) | 6.91 | **7.21** | +0.30 |

The wind-profile state moves sensible heating by **-0.86 kWh** and sensible cooling by **+6.48 kWh**. Cooling moves the more of the two in relative terms because the cooling load is small and the west wall's sol-air temperature is what the external film controls.

## The gate

| Condition | Result |
| --- | :-: |
| V2 residual < 5 % on every state (worst 1.7701 %) | PASS |
| Seven transmission line items on every state (found [7]) | PASS |
| Latent heating a residue, not a demand (0.0000 kWh) | PASS |
| Final engine tree identical to HEAD | PASS |
| Final state reproduces a live HEAD run | PASS |

## The EnergyPlus validation, with the wind now matched on both sides

Both columns are the corrected engine against a reference matched to it. The *after* column additionally matches the wind on both sides — the ISO engine applies the profile, and the IDF geometry is raised so EnergyPlus evaluates the west wall at the same height.

| Metric | Before: ISO / E+ / diff vs E+ | After: ISO / E+ / diff vs E+ |
| --- | --- | --- |
| Heating | 123.74 / 146.75 / -15.7 % | **122.88 / 148.97 / -17.5 %** |
| Cooling | 13.41 / 27.34 / -50.9 % | **19.90 / 21.59 / -7.8 %** |
| Total | 137.15 / 174.09 / -21.2 % | **142.78 / 170.56 / -16.3 %** |

**Cooling agreement improves from -50.9 % to -7.8 %** — the absolute gap falls from 13.9 kWh to 1.7 kWh. That is the single clearest external check on the correction: an independent detailed-simulation reference, driven by the same wind, now agrees with the ISO engine on cooling to within 8 %.

## What did NOT change

* **The correlation.** `h_ce = 4 + 4u` is untouched and still returns the ISO constant of exactly 20 W/(m²·K) at 4 m/s. Only the wind fed to it moved.
* **Infiltration.** The stack/wind modulation keeps the meteorological wind: its shelter is already carried by the LBL N = 20 divisor and its normalisation is anchored to a station-referenced 4 m/s. Reducing u as well would count the same shelter twice.
* **The weather file.** Still `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`.
* **The first thirteen trajectory states**, to the printed digit.
* **`results/diagnostics/wind_stats_essendon.json`** and the F7 weather-integrity figure built from it. That comparison is about the RO file's dead-calm months, a different question, and its numbers are from a pre-closure-fix engine; it is left as the historical record it is rather than half-updated.

## Where to look

| | |
| --- | --- |
| `results/paper/wind_profile/wind_profile.md` | Items 0, 1, 3, 5 — what EnergyPlus did, the profile, terrain sensitivity, other Australian sites |
| `results/paper/wind_profile/wind_verdict_terrain.md` | Item 2 — the C2 sign, on the corrected wind |
| `results/paper/wind_profile/wind_verdict_station.md` | the same experiment on the station wind, i.e. the *before* |
| `results/paper/trajectory_v2/comparison.md` | the gated trajectory |
| `results/paper_pre_wind_profile/` | everything above, as it stood before |

Generated by `tools/diagnostics/write_wind_profile_superseded.py`.
