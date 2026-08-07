# Pre-infiltration-fix reference (superseded)

This directory preserves the paper result set **as it stood before** the
infiltration-model corrections (Items 1–3 of
`AIB_infiltration_fix_and_recalibration.md`), for contrast with the corrected
run in `results/paper/`.

The pre-fix canonical trajectory and its provenance are the ones committed under
[`results/au_canonical_essendon/`](../au_canonical_essendon/) — that directory is
unchanged and remains the historical record of the pre-fix engine on the Essendon
weather file. It is **not** copied here to avoid duplicating a large binary/CSV
set; treat `results/au_canonical_essendon/` as the pre-fix reference alongside the
numbers below.

## Pre-fix headline (Apt 305, Essendon EPW, uncorrected infiltration model)

| Quantity | Pre-fix value |
|---|---|
| Sensible heating | **172.82 kWh** (8.64 kWh/m²) |
| Sensible cooling | **6.34 kWh** (0.32 kWh/m²) |
| Headline (per doc) | **9.00 kWh/m²·yr** |
| Infiltration envelope area A_env | 88.6 m² (all surfaces, incl. party walls) |
| Mean H_ve,inf | 5.36 W/K, air booked as entering at **0 °C** |
| q₅₀ (band "2006-today") | 4.0 m³/(h·m²)@50 Pa (European) |

These are the values the corrected run in `results/paper/SUPERSEDED.md` is measured
against. The three defects behind them (A1 source term, A3 envelope area, A4
European q₅₀) are documented in `results/paper/CONFORMANCE.md`.
