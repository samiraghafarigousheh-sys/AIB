# SUPERSEDED — what the infiltration fix + recalibration changed

The pre-fix paper numbers (`results/paper_pre_infiltration_fix/`,
`results/au_canonical_essendon/`) are superseded by the corrected + recalibrated
engine. This file lists what changed and by how much. Full detail:
`results/paper/RUN_REPORT_v2.md`.

## Headline

| | Superseded (pre-fix) | Corrected (v2) | Δ |
|---|---|---|---|
| Sensible heating | 172.82 kWh (8.64 kWh/m²) | **123.74 kWh (6.19 kWh/m²)** | −49.08 kWh (−28.4 %) |
| Sensible cooling | 6.34 kWh (0.32 kWh/m²) | **13.41 kWh (0.67 kWh/m²)** | +7.07 kWh |
| Total incl. gated latent | 9.00 kWh/m²·yr | **6.91 kWh/m²·yr** | −≈2.1 kWh/m²·yr (−23 %) |

## What changed, and by how much (cumulative, Essendon EPW)

| Change | Mechanism | Heating |
|---|---|---|
| **Item 1 — A1** | Infiltration air supplied at θₑ, not 0 °C (source term added to S_ve) | 172.82 → 137.89 kWh (**−34.93**) |
| **Item 2 — A3** | Infiltration envelope area exterior-only: A_env 88.6 → 13.5 m²; n₅₀ 6.56 → 1.00 /h | 137.89 → 112.70 kWh (**−25.19**) |
| **Item 3 — q₅₀** | Australian recalibration, pre-2006 band q₅₀ = 14.0 (was European 4.0); n₅₀ 1.00 → 3.50 /h | 112.70 → 123.74 kWh (**+11.04**) |

The three act in **opposing directions** — Items 1 and 2 reduce heating, Item 3
increases it. The net is −49.08 kWh heating; recalibrating on the broken model
would have hidden this.

## q₅₀ sensitivity (corrected + scoped engine)

| q₅₀ [m³/(h·m²)@50 Pa] | Source | Heating | Cooling | Total |
|---|---|---|---|---|
| 4.0 | European legacy (superseded) | 112.70 | 12.76 | 125.46 kWh |
| 6.9 | CSIRO 2024 (Ambrose, n=233) new-dwelling mean | 115.85 | 12.94 | 128.79 kWh |
| **14.0** | **adopted** — Australian pre-2006 band | 123.74 | 13.41 | 137.15 kWh |

## Gate — PASSED (full cross-state)

The thirteen-state canonical trajectory (`trajectory_v2/comparison.md`) passes the V2
residual gate on **every** state (max −1.77 %, machine-zero from +Ground on), with seven
transmission line items and independent re-integration to 0.0000 % each state, latent gated
to 0.000000 kWh both plant-off and while-heating, HEAD-invariant under reordering, and the
final engine tree byte-for-byte identical to HEAD. Regression suite **198 passed / 0 skipped
/ 0 failed**. See `RUN_REPORT_v2.md §4`.

## EnergyPlus validation — unchanged by the fixes

Baseline ISO engine vs EnergyPlus 24.1.0 on the Essendon EPW: 121.0 vs 90.9 kWh/m²
(heating −37.0 %, cooling +8.8 %). The baseline engine has no infiltration path
("Infiltration: none" on both sides), so Items 1–3 leave this table unchanged — reasoned
earlier, now demonstrated by running it. See `results/paper/baseline_vs_ep_v2/` and
`RUN_REPORT_v2.md §3`.
