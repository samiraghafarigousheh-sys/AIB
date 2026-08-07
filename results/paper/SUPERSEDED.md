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

## Invariants (corrected final state)

Closure residual 0.0000 %; 7 transmission line items (5 ADJ); latent 0.000 kWh
with plant off and 0.000 kWh while heating; regression suite 181 passed / 17
skipped. See `RUN_REPORT_v2.md §4`.

## Not regenerated here

EnergyPlus baseline validation (no EP binary — unaffected by Items 1–3 because the
baseline engine has no infiltration path) and the full ten-state trajectory /
Tables 4–5b / Sankey charts (the trajectory harness needs its `TRAJECTORY` SHA list
extended with the new states plus EnergyPlus). See `RUN_REPORT_v2.md §5`.
