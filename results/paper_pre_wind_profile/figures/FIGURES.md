# Paper figure set

Generated 2026-08-10 by `tools/figures/make_all_figures.py` from the committed result files under `results/`. **The engine was not re-run.** Every number in every figure is read from a file already in the repository, so the figures and the tables in the paper are the same measurements rather than two runs that happen to agree.

**Weather:** `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`  
**Canonical state:** `+Closure fixes` — 123.74 kWh sensible heating, 13.41 kWh sensible cooling, 1.14 kWh gated latent, 138.29 kWh total, **6.91 kWh/m²·yr**  
**Net floor area:** 20 m²

## The metric

Every figure that prints a per-area value uses the paper's metric

> **Q_need = Q_H,sensible + Q_C,sensible + Q_C,latent (gated)**

that is, sensible heating + sensible cooling + gated latent cooling, excluding
latent heating and excluding the ungated moisture balance. This is the
`Total, sensible + gated latent` column of `results/paper/trajectory_v2/comparison.md`,
**not** the engine's own total column — the two differ on the four states before the
latent correction by the ~153–185 kWh of phantom humidification.

`tools/figures/figstyle.py` recomputes all thirteen per-area values from
`trajectory_raw.json` and asserts them against the methodology's list before any
figure is drawn:

| State | kWh/m²·yr | State | kWh/m²·yr |
| --- | ---: | --- | ---: |
| Baseline | 122.32 | +Conditioned zones | 10.75 |
| +C1 dynamic window | 120.77 | +Ground contact | 10.75 |
| +C2 wind-dependent h_ce | 119.70 | +Hemisphere | 10.75 |
| +Ventilation | 133.41 | +Infiltration supply temp | 8.52 |
| +Latent | 132.88 | +Infiltration envelope area | 6.44 |
| +Internal gains | 220.82 | +AU q50 recalibration | 6.91 |
| | | **+Closure fixes (canonical)** | **6.91** |

The canonical headline — 123.74 kWh sensible heating + 13.41 kWh sensible cooling
+ 1.14 kWh gated latent = 138.29 kWh = **6.91 kWh/m²·yr** — is asserted separately.
A mismatch on any of these aborts the whole run.

## Shared conventions

- **Vector + raster.** Every figure is written as PDF (vector, for the paper) and
  PNG (300 dpi, for preview).
- **One axis per metric.** The trajectory spans roughly 4,200 kWh to 4 kWh, so no
  two series of different magnitude share a scale. Where a panel carries two
  metrics (gated against ungated latent; monthly wind mean against exact-zero
  share) it uses two independent, separately labelled axes and says so on the
  panel.
- **Colour.** Okabe-Ito base hues, one per correction group, with a light-to-dark
  ramp inside each group, so a state keeps the same colour in every figure it
  appears in. Group hues separate under deuteranopia, protanopia and tritanopia;
  within-group separation is carried by lightness, which survives all three.
  Baseline = grey · literature corrections (C1, C2) = blue · implementation
  defects = vermillion · infiltration states = bluish green · closure fixes =
  reddish purple.
- **State labels are rotated, never truncated.** Thirteen states do not fit
  horizontally.
- **The three infiltration states are shaded as a group** in every trajectory
  panel, because they are the subject of Section 3.7.1.
- **F2 and F5 share one renderer**, one band order, one colour map and one
  kWh-per-unit-height, so the difference between them is the model and not the
  drawing. F5 also carries a dashed ghost outline of F2's column extent.
- **No figure invents a number.** Where a required quantity is absent from the
  committed results it is drawn as an explicit gap and reported here (see F10).

## Recommended placement

- **Main text:** F1, F2, F3, F5, F6, F8
- **Main text if the figure budget allows:** F4, F10
- **Supplementary / appendix:** F7, F9

The paper currently plans F1, F2, F3, F5, F6 and F8 in the main text, with F4 and F10 strong candidates if the figure budget allows, and F7 and F9 as supplementary. F9 is a visual restatement of the residual and line-item columns of the trajectory table, so it is the first to drop.

## The figures

### F1 — Baseline ISO 52016-1 against EnergyPlus

*Main text*

**Files**

- `results/paper/figures/F1_baseline_iso_vs_energyplus.pdf`
- `results/paper/figures/F1_baseline_iso_vs_energyplus.png`

**Built from**

- `results/paper/baseline_vs_ep_v2/baseline_vs_energyplus.csv`
- `results/paper/baseline_vs_ep_v2/run_meta.json`

**Key numbers displayed**

- Heating: ISO 1,779.4 kWh vs EnergyPlus 1,120.2 kWh (+58.8 % vs EP)
- Cooling: ISO 640.8 kWh vs EnergyPlus 697.2 kWh (-8.1 % vs EP)
- Total: ISO 2,420.2 kWh vs EnergyPlus 1,817.4 kWh (+33.2 % vs EP)
- Per area: ISO 121.01 vs EP 90.87 kWh/m²·yr

**Note**

The committed CSV states `diff_pct` against the ISO figure; the paper quotes the difference against the EnergyPlus reference, so the figure recomputes it from the same two kWh columns and asserts +58.8 / −8.1 / +33.2 % before drawing.

---

### F2 — Baseline energy-balance decomposition (Sankey)

*Main text*

**Files**

- `results/paper/figures/F2_baseline_energy_balance_sankey.pdf`
- `results/paper/figures/F2_baseline_energy_balance_sankey.png`

**Built from**

- `results/paper/trajectory_v2/trajectory_raw.json (Baseline → config_B → sankey)`

**Key numbers displayed**

- Inputs 8,305.6 kWh; outputs 8,402.3 kWh; residual -96.72 kWh (-1.16 %)
- Internal gains 5,356.7 kWh = 64.5 % of input
- Heating 1,779.4 kWh; solar & free-gain 1,169.5 kWh
- Five party surfaces (ADJ) 4,864.5 kWh = 57.9 % of output — dominant loss
- Seven transmission line items resolved: West exterior wall (OP) 429.6 kWh; N wall → Apt 306 (ADJ) 819.9 kWh; S wall → Apt 304 (ADJ) 819.9 kWh; E wall → corridor (ADJ) 1,109.0 kWh; Floor → Apt 205 (ADJ) 1,057.8 kWh; Ceiling → Apt 405 (ADJ) 1,057.8 kWh; West windows (W) 334.3 kWh
- Ventilation (losses) 2,031.9 kWh; cooling 640.8 kWh; ground 99.0 kWh; thermal bridges 2.1 kWh

**Note**

The residual is drawn as a hatched, unfilled band on the input side — the side that is short — and is never folded into a transmission item. The source record carries `republished_residual_Wh = 0.0`, which the renderer asserts before drawing.

---

### F3 — The correction trajectory (core result figure)

*Main text*

**Files**

- `results/paper/figures/F3_correction_trajectory.pdf`
- `results/paper/figures/F3_correction_trajectory.png`

**Built from**

- `results/paper/trajectory_v2/trajectory_raw.json`
- `results/paper/trajectory_v2/comparison.md (the same table, for cross-check)`

**Key numbers displayed**

- Sensible heating, Baseline → canonical: 1,779.36 → 123.74 kWh (peak 4,228.46 kWh at +Internal gains)
- Sensible cooling, Baseline → canonical: 640.84 → 13.41 kWh
- Total energy need on the paper's metric, Baseline → canonical: 122.32 → 6.91 kWh/m²·yr (peak 220.82 at +Internal gains)
- Gated latent, Baseline → canonical: 26.12 → 1.14 kWh; ungated 900.05 → 600.11 kWh
- Ventilation + infiltration loss, Baseline → canonical: 2,031.91 → 1,974.73 kWh (peak 2,860.65 kWh at +Ventilation)
- V2 residual: worst -1.77 % at +Conditioned zones; machine zero from +Ground contact; all 13 states inside ±5 %
- Per-area values printed on panel 3 (the paper's published figures, each asserted against the recomputed value): Baseline 122.32, +C1 dynamic window 120.77, +C2 wind h_ce 119.70, +Ventilation 133.41, +Latent 132.88, +Internal gains 220.82, +Conditioned zones 10.75, +Ground contact 10.75, +Hemisphere 10.75, +Infil. supply temp 8.52, +Infil. envelope area 6.44, +AU q50 6.91, +Closure fixes 6.91

**Note**

Panel 3 uses the paper's metric (sensible heating + sensible cooling + gated latent), not the engine's own total column; the loader asserts all thirteen per-area values against the methodology list before the figure is drawn. Panel 4 carries two independent y axes because the ungated balance is up to 560× the gated charge.

---

### F4 — Per-correction contribution (waterfall), heating and cooling

*Main text if the figure budget allows*

**Files**

- `results/paper/figures/F4_per_correction_waterfall.pdf`
- `results/paper/figures/F4_per_correction_waterfall.png`

**Built from**

- `results/paper/trajectory_v2/comparison.md / trajectory_raw.json (differences between consecutive states)`

**Key numbers displayed**

- Heating cascade: 1,779.36 kWh → 123.74 kWh
- Heating steps (kWh): +C1 dynamic window +4.60, +C2 wind h_ce +4.15, +Ventilation +409.31, +Latent +0.00, +Internal gains +2,031.04, +Conditioned zones -4,018.18, +Ground contact +0.00, +Hemisphere +0.00, +Infil. supply temp -56.33, +Infil. envelope area -39.08, +AU q50 +8.87, +Closure fixes +0.00
- Cooling cascade: 640.84 kWh → 13.41 kWh
- Cooling steps (kWh): +C1 dynamic window -34.77, +C2 wind h_ce -25.30, +Ventilation -135.09, +Latent +0.00, +Internal gains -264.89, +Conditioned zones -176.66, +Ground contact +0.00, +Hemisphere +0.00, +Infil. supply temp +11.02, +Infil. envelope area -2.26, +AU q50 +0.53, +Closure fixes +0.00
- Opposing movements the figure exists to show: +Internal gains +2,031.04; +Conditioned zones −4,018.18; +Infil. supply temp −56.33; +Infil. envelope area −39.08; +AU q50 +8.87 (heating)

**Note**

Deltas are differences between consecutive states of the committed trajectory, not re-simulated. The script asserts the five signature movements and the canonical landing point before drawing.

---

### F5 — Corrected-state energy balance (Sankey), canonical state

*Main text*

**Files**

- `results/paper/figures/F5_corrected_energy_balance_sankey.pdf`
- `results/paper/figures/F5_corrected_energy_balance_sankey.png`

**Built from**

- `results/paper/trajectory_v2/trajectory_raw.json (+Closure fixes → config_B → sankey)`

**Key numbers displayed**

- Inputs 3,757.1 kWh; outputs 3,757.1 kWh; residual 9.313e-13 kWh (2.48e-14 %) — machine zero
- Heating 123.7 kWh; internal gains 730.3 kWh; solar & free-gain 2,903.0 kWh
- Five party surfaces (ADJ) 954.6 kWh = 25.4 % of output
- Seven transmission line items resolved: West exterior wall (OP) 459.2 kWh; N wall → Apt 306 (ADJ) 164.0 kWh; S wall → Apt 304 (ADJ) 164.0 kWh; E wall → corridor (ADJ) 205.0 kWh; Floor → Apt 205 (ADJ) 210.8 kWh; Ceiling → Apt 405 (ADJ) 210.8 kWh; West windows (W) 353.2 kWh
- Ventilation (losses) 1,974.7 kWh; cooling 13.4 kWh; ground 0.0 kWh (the phantom slab term is gone); thermal bridges 1.9 kWh

**Note**

Drawn by the same renderer as F2 with the same band order, colour map and kWh-per-unit-height, so the two figures are directly comparable. The corrected state has no residual band because there is no residual.

---

### F6 — Wind field and the C2 attribution

*Main text*

**Files**

- `results/paper/figures/F6_wind_field_and_c2.pdf`
- `results/paper/figures/F6_wind_field_and_c2.png`

**Built from**

- `results/diagnostics/wind_stats_essendon.json`
- `results/diagnostics/wind_verdict_essendon.md (the same numbers, for cross-check)`
- `weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw (panels 1–2 only, verified against wind_stats_essendon.json)`

**Key numbers displayed**

- Annual: mean 4.84 m/s, median 4.6, max 18.0; 59.8 % above the 4 m/s pivot; 1.58 % exactly 0.0 m/s
- Diurnal: calmest hour 3.88 m/s (hour 4), windiest 6.15 m/s (hour 15)
- No degenerate month; worst exact-zero share Jun 6.4 %
- Cooling-plant-on hours: 33 h, mean wind 5.74 m/s (1.19× the annual mean), 84.8 % above the pivot
- Wind bands (hours, extra cooling kWh, share): exactly 0 138 h +0.00 kWh -0.0 %; 0 – 2 m/s 601 h +0.00 kWh -0.0 %; 2 – 4 m/s 2,766 h +0.23 kWh -7.1 %; above 4 m/s 5,255 h -3.50 kWh 107.1 %
- 100.0 % of the -3.27 kWh arises in non-zero wind
- Controlled experiment: cooling 9.61 kWh at the fixed ISO coefficient against 6.34 kWh with h_ce = 4v + 4, a reduction of 3.27 kWh; heating 173.28 → 172.82 kWh; verdict a+b

**Note**

Panels 1 and 2 need hourly detail that the committed summary JSON does not carry, so they are computed from the committed EPW named in the trajectory's provenance — the same file the diagnostic ran on, not a second run. figstyle.verify_epw_against_stats asserts hour count, mean, max, exact-zero share and above-pivot share against wind_stats_essendon.json and aborts on any mismatch.

---

### F7 — Weather-record integrity: the superseded contrast

*Supplementary / appendix*

**Files**

- `results/paper/figures/F7_weather_record_integrity.pdf`
- `results/paper/figures/F7_weather_record_integrity.png`

**Built from**

- `results/diagnostics/wind_stats.json (Melbourne RO 948680, superseded)`
- `results/diagnostics/wind_stats_essendon.json (Essendon Fields 958660, adopted)`

**Key numbers displayed**

- RO: annual mean 2.71 m/s, 33.58 % of hours exactly 0.0 m/s, 31.0 % above the pivot, dead-calm months Jan/Mar/Jul/Sep (2,952 h, 33.7 % of the year)
- Essendon: annual mean 4.84 m/s, 1.58 % exactly 0.0 m/s, 59.8 % above the pivot, no dead-calm month
- C2 effect on sensible cooling: +48.73 kWh on RO against -3.27 kWh on Essendon
- Share attributable to exactly-zero-wind hours: 96.3 % (RO) against 0.0 % (Essendon)
- RO monthly means (m/s): Jan 0.009, Feb 3.769, Mar 0.001, Apr 3.388, May 4.756, Jun 3.953, Jul 0.006, Aug 5.172, Sep 0.005, Oct 3.807, Nov 3.904, Dec 3.841
- Essendon monthly means (m/s): Jan 5.60, Feb 4.84, Mar 4.36, Apr 4.16, May 3.75, Jun 4.20, Jul 5.50, Aug 5.20, Sep 5.49, Oct 4.80, Nov 4.98, Dec 5.21

**Note**

Caption should make the general claim: a weather record can pass conventional validity checks — correct row count, no missing-value sentinels, plausible annual mean — and still invert the sign of a method-level correction.

---

### F8 — The latent gate

*Main text*

**Files**

- `results/paper/figures/F8_latent_gate.pdf`
- `results/paper/figures/F8_latent_gate.png`

**Built from**

- `results/paper/trajectory_v2/trajectory_raw.json`
- `results/paper/trajectory_v2/comparison.md §6 (the same numbers, for cross-check)`

**Key numbers displayed**

- Gated latent by state (kWh): Baseline 26.12, +C1 dynamic window 25.34, +C2 wind h_ce 25.02, +Ventilation 25.10, +Latent 14.53, +Internal gains 7.07, +Conditioned zones 0.53, +Ground contact 0.53, +Hemisphere 0.53, +Infil. supply temp 1.22, +Infil. envelope area 1.05, +AU q50 1.14, +Closure fixes 1.14
- Ungated moisture balance by state (kWh): Baseline 900.05, +C1 dynamic window 905.27, +C2 wind h_ce 906.29, +Ventilation 1148.49, +Latent 634.24, +Internal gains 934.29, +Conditioned zones 718.56, +Ground contact 718.56, +Hemisphere 718.56, +Infil. supply temp 634.98, +Infil. envelope area 589.33, +AU q50 600.11, +Closure fixes 600.11
- Canonical state: the gate removes 600.11 → 1.14 kWh, 99.8 % of the raw balance
- Monthly gated latent at the canonical state (kWh): Jan 0.79, Feb 0.09, Mar 0.03, Apr 0.00, May 0.00, Jun 0.00, Jul 0.00, Aug 0.00, Sep 0.00, Oct 0.00, Nov 0.04, Dec 0.18; Dec–Feb 1.07 against Jun–Aug 0.00
- Gating audit: latent charged with the cooling plant off = 0.000000 kWh and latent charged while the heating plant runs = 0.000000 kWh, on all thirteen states; audit axis full scale 1e-03 kWh
- Cooling-plant hours at the canonical state: 54 of 8,760; latent charged in 47 hours

**Note**

Panel 3's y-limit is set to 1e-3 kWh so that any non-zero value would be visible; the script also asserts that all 26 audited values are exactly zero and refuses to draw otherwise.

---

### F9 — Closure residual and inventory completeness

*Supplementary / appendix*

**Files**

- `results/paper/figures/F9_closure_residual_and_inventory.pdf`
- `results/paper/figures/F9_closure_residual_and_inventory.png`

**Built from**

- `results/paper/trajectory_v2/trajectory_raw.json`
- `results/paper/trajectory_v2/comparison.md §4–§5`
- `results/au_corrections_closed/six_state_closed.md (the pre-closure line-item count of 2)`

**Key numbers displayed**

- V2 residual (% of inputs) by state: Baseline -1.16, +C1 dynamic window -1.17, +C2 wind h_ce -1.17, +Ventilation -1.01, +Latent -1.01, +Internal gains -1.04, +Conditioned zones -1.77, +Ground contact +0.00, +Hemisphere +0.00, +Infil. supply temp +0.00, +Infil. envelope area +0.00, +AU q50 +0.00, +Closure fixes +0.00
- Largest excursion -1.77 % at +Conditioned zones; machine zero from +Ground contact onward; all thirteen inside ±5 %
- Resolved transmission line items: 7 on every state (5 ADJ party surfaces + 1 OP west wall + 1 W west windows)
- Independent re-integration agrees with the reported sum to 0.0000 % on every state
- Pre-closure the same column read 2, against seven surfaces

**Note**

The residual column of the trajectory table carries the same numbers, so this figure is a visual restatement rather than new information — suitable for the appendix if the main figure count is constrained.

---

### F10 — Envelope permeability sensitivity

*Main text if the figure budget allows*

**Files**

- `results/paper/figures/F10_q50_sensitivity.pdf`
- `results/paper/figures/F10_q50_sensitivity.png`

**Built from**

- `results/paper/trajectory_v2/trajectory_raw.json (+Infiltration envelope area → q50 = 4.0; +AU q50 recalibration → q50 = 14.0)`
- `pybuildingenergy/src/pybuildingenergy/source/utils.py (_Q50_BY_CONSTRUCTION_AGE, _Q50_DEFAULT = 6.9, stated design target ≈ 5)`

**Key numbers displayed**

- q50 = 4.0 (European default): heating 114.87 kWh, cooling 12.89 kWh, total 6.44 kWh/m²·yr
- q50 = 6.9 (CSIRO new-dwelling mean): NOT MEASURED in the committed results — drawn as a gap, not interpolated
- q50 = 14.0 (adopted pre-2006 band): heating 123.74 kWh, cooling 13.41 kWh, total 6.91 kWh/m²·yr
- Swing from q50 = 4.0 to 14.0: heating +8.87 kWh (+7.7 %); total +0.47 kWh/m²·yr (+7.4 %)
- Reference lines: CSIRO 2024 measured mean q50 = 6.9; CSIRO 2024 stated design target q50 ≈ 5

**Note**

**The q50 = 6.9 row is not present in the committed result files.** It exists only in the message of the recalibration commit `421c282`, which reports H = 115.85 / C = 12.94 / total = 128.79 kWh for q50 = 6.9. That sweep is not commensurable with the trajectory: its own q50 = 4.0 row reads H = 112.70 kWh against the trajectory's 114.87 kWh, and its totals are sensible-only (123.74 + 13.41 = 137.15 kWh at q50 = 14.0, against the paper's 138.29 kWh, which includes gated latent). Plotting the two together would build one chart from two runs, so the 6.9 point is drawn as an explicit gap and is not interpolated.

---

## Reproducing

```bash
python3 tools/figures/make_all_figures.py
```

Requires `matplotlib` and `numpy`. Each figure module is also runnable on its own (`python3 tools/figures/f3_trajectory.py`). If a required quantity is missing from the committed results, the builder raises `figstyle.MissingQuantity` naming the figure and the quantity, and the run records the failure in this file rather than substituting a value from another run.
