# SUPERSEDED — the complete record of what the wind-profile correction replaced

The preceding paper set is retained verbatim under `results/paper_pre_wind_profile/`. Nothing in it has been edited. This file is the list the manuscript is edited against: every trajectory state, both EnergyPlus validations, Tables 4 / 5a / 5b, and every figure, with the old and new value side by side.

**Rows marked `unchanged` are a measurement, not an assumption** — each was re-run and compared, and the drift is printed.

## 1. The defect

Correction C2 replaces the ISO 13789 constant external convective coefficient with `h_ce = 4 + 4u`. The correlation wants the wind local to the building surface. The engine fed it the EPW wind column, which is a **10 m reading over open terrain at the meteorological station** — asserting that the site and the station share both terrain class and measurement height. Apt 305 shares neither with Essendon Fields aerodrome.

The pivot at which `4u + 4` equals the ISO constant of 20 W/(m²·K) is u = 4 m/s. On the station column **59.8 %** of hours are above it; at Carlton's terrain and height only **29.4 %** are. **That is a change of side, not of degree**, which is why it is sign-determining rather than a conservatism.

## 2. The fourth input mismatch in the EnergyPlus validation

`Site:HeightVariation` is absent from both generated IDFs, so EnergyPlus fell back to the `Building` object's `Terrain` field — `Suburbs`, a = 0.22, δ = 370 m — and applied a terrain **and** height profile to every wind-exposed surface. Measured by re-running the committed IDF with `Surface Outside Face Outdoor Air Wind Speed` reported hourly, not inferred from the algorithm:

| Engine | Wind driving the external film | Annual mean |
| --- | --- | ---: |
| EnergyPlus, as published | station × the `Suburbs` profile at z = 1.35 m | **2.23 m/s** |
| ISO 52016-1, as published | station column, unadjusted | **4.84 m/s** |
| Both, after this run | station × `suburban` at z = 6.75 m | **3.18 m/s** |

**The height EnergyPlus uses after the fix: z = 6.75 m**, factor 0.6574 — read back off the live IDF, and equal to the ISO side's 6.75 m and 0.6574. The IDF placed a third-floor apartment's zone origin at z = 0, so the wall was being evaluated at 1.35 m; the whole geometry is now translated up. Nothing else in the model reads absolute height — no ground surface, no shading geometry, and the view factor to ground comes from tilt — so the translation moves the wind and nothing else.

The two engines had been driven by winds differing by a factor of 2.17. This is a fourth input mismatch of the same class as the three recorded in `results/paper/validation_corrected/`, and it is now closed on both sides.

## 3. The C2 effect and its sign

The same engine, run twice, changing only the `h_ce` model — once on each wind. **Both arms are on this engine tree**, so nothing but the wind differs. An older `wind_stats.json` would also carry every closure fix made since and would attribute those to the terrain correction.

| | Station wind (superseded) | Terrain-corrected (new) | |
| --- | ---: | ---: | --- |
| Annual mean wind | 4.84 m/s | 3.18 m/s | × 0.6574 |
| Hours above the 4 m/s pivot | 59.8 % | 29.4 % | |
| Mean h_ce | 23.36 W/(m²·K) | 16.73 W/(m²·K) | ISO constant is 20 |
| Sensible cooling, ISO fixed h_ce | 18.1428 kWh | 18.1428 kWh | identical — the control arm |
| Sensible cooling, `4u + 4` | 13.41 kWh | 19.90 kWh | |
| **C2 effect on sensible cooling** | **-4.73 kWh** | **+1.75 kWh** | **SIGN REVERSES** |
| C2 effect on sensible heating | -0.35 kWh | -1.21 kWh | same sign, 3.5× larger |
| Cooling-plant hours | 65 → 54 | 65 → 73 | |

> **The paper currently describes C2 as reducing cooling. That text is wrong in direction and must be rewritten.** On the wind the wall actually sees, C2 **increases** sensible cooling by +1.75 kWh. The mechanism is the same either way — the external film controls how much of the absorbed solar a west wall of absorptance 0.75 sheds back to the air — but with the local mean at 3.18 m/s the coefficient sits *below* the ISO constant for 70.6 % of the year, so the film is weaker rather than stronger, the sol-air temperature rises, and more heat is conducted inward.

The control arm is identical to machine precision (18.142786 vs 18.142786 kWh): with `h_ce` on `table` the wind is never consumed, so anything other than the wind having changed would show up there. The sign finding cannot be read off an uncontrolled experiment, so the F6 generator asserts this too.

## 4. The canonical headline

| Quantity | Superseded (`+Closure fixes`) | New canonical (`+Wind profile`) | Δ |
| --- | ---: | ---: | ---: |
| Sensible heating (kWh) | 123.74 | **122.88** | -0.86 |
| Sensible cooling (kWh) | 13.41 | **19.90** | +6.48 |
| Latent cooling, gated (kWh) | 1.14 | **1.51** | +0.37 |
| Latent heating (kWh) | 0.0000 | **0.0000** | +0.0000 |
| **Total, sensible + gated latent (kWh)** | 138.29 | **144.28** | +5.99 |
| **Per area (kWh/m²·yr)** | 6.91 | **7.21** | +0.30 |

Every reported value derived from the old headline — reduction percentages against the baseline, the kWh/m²·yr figure, the sensible/latent split — must be recomputed from the new column.

## 5. Every trajectory state

The metric is the paper's: Q_H,sens + Q_C,sens + Q_C,lat(gated), per 20 m². Δ is new − old on the per-area figure.

| State | Old H | New H | Old C | New C | Old kWh/m² | New kWh/m² | Δ kWh/m² |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 1779.36 | 1779.36 | 640.84 | 640.84 | 122.32 | 122.32 | +0.00 |
| +C1 dynamic window | 1783.96 | 1783.96 | 606.07 | 606.07 | 120.77 | 120.77 | +0.00 |
| +C2 wind-dependent h_ce | 1788.11 | 1788.11 | 580.77 | 580.77 | 119.69 | 119.69 | +0.00 |
| +Ventilation | 2197.42 | 2197.42 | 445.68 | 445.68 | 133.41 | 133.41 | +0.00 |
| +Latent | 2197.42 | 2197.42 | 445.68 | 445.68 | 132.88 | 132.88 | +0.00 |
| +Internal gains | 4228.46 | 4228.46 | 180.79 | 180.79 | 220.82 | 220.82 | +0.00 |
| +Conditioned zones | 210.28 | 210.28 | 4.12 | 4.12 | 10.75 | 10.75 | +0.00 |
| +Ground contact | 210.28 | 210.28 | 4.12 | 4.12 | 10.75 | 10.75 | +0.00 |
| +Hemisphere | 210.28 | 210.28 | 4.12 | 4.12 | 10.75 | 10.75 | +0.00 |
| +Infiltration supply temp | 153.95 | 153.95 | 15.15 | 15.15 | 8.52 | 8.52 | +0.00 |
| +Infiltration envelope area | 114.87 | 114.87 | 12.89 | 12.89 | 6.44 | 6.44 | +0.00 |
| +AU q50 recalibration | 123.74 | 123.74 | 13.41 | 13.41 | 6.91 | 6.91 | +0.00 |
| +Closure fixes | 123.74 | 123.74 | 13.41 | 13.41 | 6.91 | 6.91 | +0.00 |
| **+Wind profile** | — | 122.88 | — | 19.90 | *new state* | **7.21** | — |

**13 of the 13 pre-existing states are unchanged to the printed digit; the largest per-area drift across all of them is 0.00e+00 kWh/m².** Each is a cherry-pick of one historical commit and none carries the wind profile, so this is both the expected result and its verification: had a state moved, the correction would not be separable at the point the trajectory applies it.

### The C2 row in the trajectory is C2 *as published*

`+C2 wind-dependent h_ce` moves sensible cooling by **-25.30 kWh** at its own position in the order, driven by the raw station column — that state's engine is the C2 commit and does not contain the wind profile. The `+Wind profile` state at the end is what corrects it. **The two rows cannot be added**: the trajectory is cumulative and each row is measured where it sits. The isolated one-switch experiments on both winds are in `results/paper/wind_profile/`.

## 6. The EnergyPlus validation

### 6a. Corrected engine against its matched reference

Both columns are the corrected engine against a reference matched to it. The *new* column additionally matches the wind on both sides.

| Metric | Superseded: ISO / E+ / diff | New: ISO / E+ / diff | Old gap | New gap |
| --- | --- | --- | ---: | ---: |
| Heating | 123.74 / 146.75 / -15.7 % | **122.88 / 148.97 / -17.5 %** | 23.0 kWh | **26.1 kWh** |
| Cooling | 13.41 / 27.34 / -50.9 % | **19.90 / 21.59 / -7.8 %** | 13.9 kWh | **1.7 kWh** |
| Total | 137.15 / 174.09 / -21.2 % | **142.78 / 170.56 / -16.3 %** | 36.9 kWh | **27.8 kWh** |

**Absolute convergence is the primary statement.** The cooling gap falls from 13.9 kWh to 1.7 kWh; the heating gap moves from 23.0 kWh to 26.1 kWh. In relative terms cooling improves from -50.9 % to -7.8 % and heating moves from -15.7 % to -17.5 %.

**Relative error is unstable here and should not carry the argument.** The cooling load is 21.6 kWh on a 20 m² zone — 1.08 kWh/m²·yr — so a residual of one kWh is several percent, while the same residual on the baseline's 697 kWh would be under a fifth of one. Quote the kWh; use the percentage only alongside it.

### 6b. Baseline engine against its matched reference

Unaffected by the wind profile: the baseline engine has no wind profile, and its reference is the ISO 13789 buffer case. Re-run and compared rather than assumed.

| Metric | Superseded | New | Δ on the E+ column |
| --- | --- | --- | --- |
| Heating | 1,779.36 / 2,081.97 / -14.5 % | 1,779.36 / 2,081.97 / -14.5 % | 0.000 kWh |
| Cooling | 640.84 / 697.35 / -8.1 % | 640.84 / 697.35 / -8.1 % | 0.000 kWh |
| Total | 2,420.20 / 2,779.32 / -12.9 % | 2,420.20 / 2,779.32 / -12.9 % | 0.000 kWh |

The published `baseline_vs_ep_v2/` directory is **not** regenerated: its three IDF defects are recorded in its own `DEFECT_NOTICE.md` and the repaired comparison is the table above. Nothing in it has been edited.

## 7. Tables 4, 5a and 5b

There is **no copy of Tables 4 or 5 in the paper tree on this branch**: they were last generated on `claude/aib-canonical-clean-weather-0fr0mp` at `f5a5229`, which is not an ancestor of HEAD. The generator has been restored to `tools/paper/tables_4_5.py` and re-run against the regenerated trajectory, so the tables exist on this branch for the first time.

| Table | Source | Extra engine runs | Moved by the wind profile? |
| --- | --- | ---: | --- |
| **4** — window / h_ce | trajectory states 1–3 | 0 | **No.** Those three states reproduce their committed values exactly (§5), so the table derives from unchanged measurements |
| **5a** — ventilation + latent, methodology order | trajectory states 3–5 | 0 | **No**, same reason |
| **5b** — ventilation + latent, isolated 2×2 | four branch states from the vendored baseline | 3 | **No** — none of the four states contains the wind-profile commit. It *has* moved against `f5a5229`, for an unrelated reason; see below |

### Table 5b has moved, and not because of the wind

| Latent cooling, gated (kWh) | Base | C1 · ventilation | C2 · latent | C3 · both |
| --- | ---: | ---: | ---: | ---: |
| As published at `f5a5229` | 26.12 | 26.40 | 18.21 | 16.37 |
| This run | 26.12 | 26.66 | 18.21 | 15.53 |

**Interaction term: -3.22 kWh**, against -2.12 kWh as published. The claim the table exists to make — that the two fixes are *not additive on the latent side* — is unchanged in kind and larger in degree.

The cause is the **q₅₀ band**, not the wind. Table 5b's four states are branch engines from July 2026, but the harness reads the building dictionary from the repository rather than from the worktree (`closed_balance_six_state.EXAMPLES_DIR = REPO_ROOT / "examples"`). At `f5a5229` that dictionary declared `construction_year: "2006-today"`; it now declares `"1991-2005"`. Looked up in those branch engines' own pre-recalibration table, that is q₅₀ = 4.0 → 6.0 m³/(h·m²)@50 Pa — a 50 % increase in envelope permeability for every state with an infiltration path, which is exactly the states that moved.

The q₅₀ calibration is correct as committed and is not re-opened here. This is recorded so the movement is attributed to the right cause: **a reader comparing Table 5b against the `f5a5229` version must not read the difference as a wind-profile effect.**

Files: `results/paper/tables_4_5/table4_window_hce.{csv,md}`, `table5a_methodology_order.{csv,md}`, `table5b_isolation_2x2.{csv,md}`, `table5b_raw.json`, `PROVENANCE.md`.

## 8. Every figure in `results/paper/figures/`

Each figure asserts the quantities it prints before drawing and raises `figstyle.MissingQuantity` naming the figure and the value rather than substituting one from a different run. That gate was tested by re-pinning it to the superseded values and confirming it fires.

| Figure | Title | Status in this run | PNG sha256 (12) |
| --- | --- | --- | --- |
| `F1_baseline_iso_vs_energyplus` | Baseline ISO 52016-1 against EnergyPlus | unchanged — the baseline engine carries no wind profile and its reference is the ISO 13789 buffer case | `bd7a10a1fea1` |
| `F2_baseline_energy_balance_sankey` | Baseline energy-balance decomposition (Sankey) | unchanged in content; redrawn from the regenerated trajectory_raw.json (Baseline state, byte-identical numbers) | `39c74f37e65d` |
| `F3_correction_trajectory` | The correction trajectory | REDRAWN — gains a fourteenth state and a new canonical column | `82dd1675a5d0` |
| `F4_per_correction_waterfall` | Per-correction contribution (waterfall) | REDRAWN — the cascade now lands on 122.88 / 19.90 kWh | `ee01613048d2` |
| `F5_corrected_energy_balance_sankey` | Corrected-state energy balance (Sankey) | REDRAWN — the canonical state moved, so this is a different state's balance | `03ddf98c1775` |
| `F6_wind_field_and_c2` | Wind field and the C2 attribution | REBUILT — panels 1–4 now read the station run, panels 5–6 the terrain-corrected run, and panel 6 draws three bars showing the sign reversal | `4c51cb32e921` |
| `F7_weather_record_integrity` | Weather-record integrity: the superseded contrast | unchanged — it compares two weather FILES on station wind, a different question, and its numbers predate the closure fixes | `952a8e600c99` |
| `F8_latent_gate` | The latent gate | REDRAWN — the gated share moves from 99.81 % to 99.75 % and the Dec–Feb total from 1.07 to 1.30 kWh | `5379d73cb8e1` |
| `F9_closure_residual_and_inventory` | Closure residual and inventory completeness | REDRAWN — one more state on the residual axis | `aa79bedafd4c` |
| `F10_q50_sensitivity` | Envelope permeability sensitivity | unchanged — its two measured points are the +Infiltration envelope area and +AU q50 states, neither of which moved | `bcd124b1bc84` |

`FIGURES.md` in the same directory records, per figure, the source files it was built from and the key numbers it displays.

## 9. The gate

| Condition | Measured | Result |
| --- | --- | :-: |
| V2 closure residual < 5 % on every state | worst 1.7701 % at `+Conditioned zones` | PASS |
| Seven transmission line items, every state | found [7] | PASS |
| Independent re-integration within 0.1 % | worst 0.0000 % | PASS |
| Latent: nothing charged with the plant off | 0.00e+00 kWh | PASS |
| Latent: nothing charged while heating runs | 0.00e+00 kWh | PASS |
| Latent heating a residue, not a demand | 0.0000 kWh | PASS |
| Final engine tree identical to HEAD | source-tree comparison | PASS |
| Final state reproduces a live HEAD run | tolerance 0.01 kWh | PASS |
| Baseline and closure base pinned | baseline `2e6e910`, closure base `978db37` | PASS |
| Closure set exactly the four expected commits | `6e549fa18, 82a909d3f, 9fd8c696c, 09357302f` | PASS |

## 10. What did NOT change

* **The correlation.** `h_ce = 4 + 4u` is untouched and still returns the ISO constant of exactly 20 W/(m²·K) at 4 m/s. Only the wind fed to it moved.
* **Infiltration.** The stack/wind modulation keeps the meteorological wind: its shelter is already carried by the LBL N = 20 divisor and its normalisation is anchored to a station-referenced 4 m/s. Reducing u as well would count the same shelter twice. A unit test changes the terrain class and asserts the infiltration conductance is unmoved.
* **The q₅₀ calibration**, the infiltration corrections and the closure fixes — none re-opened.
* **The weather file.** Still `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`.
* **The first thirteen trajectory states**, to the printed digit (§5).
* **`results/paper/baseline_vs_ep_v2/`**, including its `DEFECT_NOTICE.md`.
* **`results/diagnostics/wind_stats_essendon.json`** and F7, built from it. That comparison is between two weather *files* on station wind — a different question — and its numbers predate the closure fixes, so it is left as the historical record it is rather than half-updated.

## 11. Where to look

| | |
| --- | --- |
| `results/paper/wind_profile/wind_profile.md` | what EnergyPlus did, the profile and its acceptance, terrain sensitivity, other Australian sites |
| `results/paper/wind_profile/wind_verdict_terrain.md` | the C2 sign on the corrected wind |
| `results/paper/wind_profile/wind_verdict_station.md` | the same experiment on the station wind — the *before* |
| `results/paper/trajectory_v2/comparison.md` | the gated 14-state trajectory |
| `results/paper/tables_4_5/` | Tables 4, 5a, 5b and their provenance |
| `results/paper/validation_corrected/` | the matched EnergyPlus case, its alignment table and the loss-path decomposition |
| `results/paper/diagnostics/{latent,residual}/` | the latent gate and the residual by state |
| `results/paper/figures/` | F1–F10 and `FIGURES.md` |
| `results/paper_pre_wind_profile/` | all of the above, as it stood before |

Generated by `tools/diagnostics/write_wind_profile_superseded.py`.
