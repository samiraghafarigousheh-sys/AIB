# Paper results — index

Every table and figure the results sections need, produced in one run on one weather file: **`AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`** (Essendon Fields, WMO 958660, 8,760 rows, 0 missing wind values, mean 4.84 m/s, 1.58 % of hours exactly 0.0, 59.8 % above the 4 m/s pivot, no dead-calm month).

Case: Apt 305, 50 Barry St, Carlton VIC — 20 m², one exposed west façade, five conditioned neighbours. Setpoints 18 °C heating / 26 °C cooling (setback 15 / 28), taken from the building dictionary.

## The gate

No reduction percentage and no kWh/m² headline is final unless all of these hold. They are checked here, not described.

| Condition | Result |
| --- | :-: |
| V2 residual < 5 % on every state | **PASS** |
| ADJ transmission in the inventory (7 line items, every state) | **PASS** |
| Independent re-integration within 0.1 %, every state | **PASS** |
| Latent gated (nothing charged with the plant off or while heating) | **PASS** |
| HEAD invariant against a live HEAD run | **PASS** |
| Final engine tree byte-identical to HEAD | **PASS** |
| Regression suite green, nothing skipped | **PASS** — 198 passed, 4 warnings in 157.94s (0:02:37), 0 skipped, exit 0 |

**Gate passed. The methodology text can be written against the numbers below.**

## The canonical headline

**172.82 kWh sensible heating + 6.34 kWh sensible cooling + 0.78 kWh gated latent = 179.95 kWh = 9.00 kWh/m²·yr.**

Latent heating is 0.0000 kWh at this state, so "sensible + gated latent" and the engine's own total (179.95 kWh) agree to the printed digit.

**Quote the components, not the total alone.** Against the superseded RO-weather run the total moved only −7.1 % (9.69 → 9.00 kWh/m²·yr) while heating rose 40.9 % and cooling fell 90.6 %, and the C2 correction changed sign. A sentence that reports only the total describes none of that.

## Every table and figure

| # | What | File | Key numbers |
| --- | --- | --- | --- |
| **T2** | ISO 52016-1 vs EnergyPlus, baseline engine | `validation_iso_vs_ep/validation_iso_vs_ep.{csv,md}` | heating 1,779.36 vs 1,120.25 kWh (+58.8 %); cooling 640.84 vs 697.16 kWh (-8.1 %); total +33.2 % |
| **F1** | ISO vs E+ grouped bars | `validation_iso_vs_ep/validation_iso_vs_ep.png` | — |
| — | The generated IDF, for audit | `validation_iso_vs_ep/apt305.idf` | EnergyPlus 24.1.0-9d7789a3ac, ideal loads |
| **T3** | Baseline annual energy-balance inventory | `baseline_balance/baseline_balance.{csv,md}` | in 8,305.6 / out 8,402.3 kWh; residual -96.72 kWh (-1.16 %); 7 line items |
| **F2** | Baseline Sankey, residual drawn as a gap | `baseline_balance/baseline_balance_sankey.png` | — |
| **T4** | Window / h_ce corrections (Base / C1 / C2) | `tables_4_5/table4_window_hce.{csv,md}` | C2 moves cooling -25.30 kWh; C1 moves solar gains -100.99 kWh |
| **T5a** | Ventilation + latent, methodology order | `tables_4_5/table5a_methodology_order.{csv,md}` | ventilation moves heating +269.68 kWh; latent moves gated latent -9.55 kWh |
| **T5b** | Ventilation + latent, isolated 2×2 | `tables_4_5/table5b_isolation_2x2.{csv,md}` | latent cooling 26.12 → 26.40 (vent) → 18.21 (latent) → 16.37 (both); interaction -2.12 kWh |
| — | Which source each table came from, and why | `tables_4_5/PROVENANCE.md` | — |
| **T6** | The full ten-state correction trajectory | `canonical_trajectory/comparison.{csv,md}` | canonical 172.82 / 6.34 / 0.78 kWh = 9.00 kWh/m²·yr |
| **F3** | Faceted trajectory chart, own axis per metric | `canonical_trajectory/canonical_trajectory.png` | — |
| **F4** | Wind diagnostic, four panels + verdict | `diagnostics/wind/wind_distribution_essendon.png`, `wind_verdict_essendon.md` | verdict **(a+b)**; C2 moves cooling -3.27 kWh, 100.0 % of it from genuine wind; 84.8 % of cooling hours above the pivot |
| **F5** | Sankey decomposition, four states | `diagnostics/sankey/{baseline,c2_wind_hce,conditioned_zones,canonical}_sankey.png` | baseline residual -1.16 % → canonical +0.00 % |
| **F6** | Latent breakdown and gating audit | `diagnostics/latent/latent_breakdown.{png,csv,md}` | gate leak max 0.0e+00 kWh; Dec–Feb 0.72 vs Jun–Aug 0.00 kWh |
| **F7** | V2 residual across all ten states, with the gate | `diagnostics/residual/residual_by_state.{png,csv,md}` | worst -1.94 % at *+Conditioned zones* |
| — | Regression suite | `pytest.txt` | 198 passed, 4 warnings in 157.94s (0:02:37), exit 0 |
| — | What this run supersedes | `SUPERSEDED.md` | — |

## The trajectory, inline

| State | Sensible H (kWh) | Sensible C (kWh) | Gated latent (kWh) | Sens + gated latent (kWh) | kWh/m²·yr | V2 residual | Items |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 1,779.36 | 640.84 | 26.12 | 2,446.32 | 129.95 | -1.16 % | 7 |
| +C1 dynamic window | 1,783.96 | 606.07 | 25.34 | 2,415.36 | 128.40 | -1.17 % | 7 |
| +C2 wind-dependent h_ce | 1,788.11 | 580.77 | 25.02 | 2,393.90 | 127.34 | -1.17 % | 7 |
| +Ventilation | 2,057.79 | 488.00 | 24.93 | 2,570.72 | 137.24 | -1.07 % | 7 |
| +Latent | 2,057.79 | 488.00 | 15.38 | 2,561.18 | 128.06 | -1.07 % | 7 |
| +Internal gains | 4,040.61 | 209.93 | 7.66 | 4,258.20 | 212.91 | -1.12 % | 7 |
| +Conditioned zones | 172.82 | 6.34 | 0.78 | 179.95 | 9.00 | -1.94 % | 7 |
| +Ground contact | 172.82 | 6.34 | 0.78 | 179.95 | 9.00 | +0.00 % | 7 |
| +Hemisphere | 172.82 | 6.34 | 0.78 | 179.95 | 9.00 | +0.00 % | 7 |
| +Closure fixes | 172.82 | 6.34 | 0.78 | 179.95 | 9.00 | +0.00 % | 7 |

`Latent cooling, ungated` (in the full CSV) is a diagnostic contrast column only — the zone moisture balance before the plant-on gate. **It is never part of any total.**

## Reproducing, in order

```bash
EPW=weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw

# Part 1 — validation + baseline balance  (needs EnergyPlus 24.1)
python tools/paper/validation_iso_vs_ep.py --weather $EPW \
    --energyplus /opt/ep/energyplus

# Part 2 — the trajectory  (~20 min)
python tools/diagnostics/canonical_trajectory.py --weather $EPW \
    --outdir results/paper/canonical_trajectory
python tools/diagnostics/make_closed_balance_chart.py \
    --raw results/paper/canonical_trajectory/trajectory_raw.json \
    --outdir results/paper/canonical_trajectory --stem canonical_trajectory \
    --title 'Apt 305, 50 Barry St Carlton — the canonical correction trajectory, methodology order'

# Part 3 — Tables 4 and 5
python tools/paper/tables_4_5.py --weather $EPW

# Part 4 — diagnostics
python tools/diagnostics/wind_h_ce_diagnostic.py --weather $EPW \
    --outdir results/paper/diagnostics/wind --tag essendon \
    --expect-weather Essendon --compare-to results/diagnostics/wind_stats.json
python tools/paper/baseline_balance.py \
    --raw results/paper/canonical_trajectory/trajectory_raw.json \
    --state Baseline --stem baseline \
    --state '+C2 wind-dependent h_ce' --stem c2_wind_hce \
    --state '+Conditioned zones' --stem conditioned_zones \
    --state '+Closure fixes' --stem canonical \
    --outdir results/paper/diagnostics/sankey
python tools/paper/diagnostics_latent_residual.py --what latent \
    --raw results/paper/canonical_trajectory/trajectory_raw.json \
    --outdir results/paper/diagnostics/latent
python tools/paper/diagnostics_latent_residual.py --what residual \
    --raw results/paper/canonical_trajectory/trajectory_raw.json \
    --outdir results/paper/diagnostics/residual

# Final
python -m pytest tests/ -v -rs > results/paper/pytest.txt 2>&1
python tools/paper/build_index.py
```

Everything needs every engine branch present locally (`git fetch origin '+refs/heads/*:refs/remotes/origin/*'`) and a git identity for the cherry-picks. `--closure-base` defaults to the pinned `978db37` in every tool that needs it — do not pass `origin/main`, which now resolves to an incomplete instrument.

