# Corrected ISO 52016-1 against a matched EnergyPlus reference

Weather: `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. Case: Apt 305, 20 m², five conditioned adjacent zones. EnergyPlus 24.1.0.

## Summary

**Relative agreement worsened on both components.** **In absolute energy the gap narrowed on both — heating by 92 %, cooling by 75 %.** The two are not in conflict: the corrections cut the loads themselves by roughly an order of magnitude, so a much smaller absolute residual sits on a much smaller denominator. Neither statement should be quoted without the other.

- **Heating**: the ISO engine differs from the matched reference by **-15.7 %**, against **-14.5 %** for the baseline engine against its own matched reference — worsened by 1.1 percentage points. In absolute terms the gap falls from 302.6 kWh to 23.0 kWh.
- **Cooling**: **-50.9 %** against **-8.1 %** — worsened by 42.8 percentage points. In absolute terms the gap *falls*, from 56.5 kWh to 13.9 kWh. The percentage grows because the cooling load itself collapses by 98 % across the corrections, so a smaller absolute residual sits on a far smaller denominator.
- **Largest remaining contributor in absolute energy**: sensible heating, -23.0 kWh, against -13.9 kWh on sensible cooling. See `DISCREPANCY.md`.

### Three defects in the published baseline reference

The headline the paper currently carries — that the baseline ISO engine over-predicts heating by **+58.8 %** against EnergyPlus — is an artefact of defects in the EnergyPlus input, not a property of the ISO engine. Three were found while building the matched case, all in the shared IDF builder, all now fixed there.

1. **No ventilation air was delivered.** `DesignSpecification:OutdoorAir` wrote the rate into the *per Person* field while the method was `Flow/Area`, which reads the *per Zone Floor Area* field. That field was blank, so EnergyPlus ran with no designed ventilation at all while the ISO side carried `H_ve = 48.4 W/K`.
2. **Ventilation was on the wrong object.** Even with the rate in the right field, outdoor air attached to `ZoneHVAC:IdealLoadsAirSystem` is delivered only in the hours the system runs — 686 of 8760 here — and not at all in the deadband, so the zone free-floated unventilated. ISO 52016-1 applies `H_ve` every hour. It is now a `ZoneVentilation:DesignFlowRate` zone air exchange on an always-on schedule, which reproduces the ISO term hour for hour.
3. **Heating was not sensible-only.** Humidification control was `ConstantSupplyHumidityRatio`, which books humidification of the ventilation air as heating once that air actually flows. Both humidity controls are now `None`.

All three are now fixed in `examples/baseline_vs_energyplus.py`. Re-running the *unchanged* baseline engine against the repaired reference gives:

| | ISO 52016-1 (baseline engine) | EnergyPlus | Difference |
|---|---:|---:|---:|
| Heating, published reference | 1,779.36 | 1,120.25 | +58.8 % |
| Heating, repaired reference | 1,779.36 | 2,081.97 | -14.5 % |
| Cooling, published reference | 640.84 | 697.16 | -8.1 % |
| Cooling, repaired reference | 640.84 | 697.35 | -8.1 % |

The ISO column is byte-identical to the committed trajectory's baseline state; only the reference moved. The baseline engine does not over-predict heating by 58.8 % — it **under-predicts** it by 14.5 %. Every before/after figure in this document uses the repaired reference on both sides, so that the comparison is like-for-like.

## 1. The corrected comparison

| Metric | ISO 52016-1 (corrected) | EnergyPlus (matched) | Difference | Difference % | ISO kWh/m² | E+ kWh/m² |
|---|---:|---:|---:|---:|---:|---:|
| Heating | 123.74 | 146.75 | -23.01 | -15.7 % | 6.19 | 7.34 |
| Cooling | 13.41 | 27.34 | -13.93 | -50.9 % | 0.67 | 1.37 |
| Total | 137.15 | 174.09 | -36.94 | -21.2 % | 6.86 | 8.70 |

Differences are stated **relative to the EnergyPlus reference**, following the existing validation. Both engines are sensible-only: the ISO side reports gated latent separately (1.14 kWh) and the EnergyPlus ideal loads carry 1.20 kWh of latent cooling with humidification disabled.

## 2. Before and after

Both rows are measured against a reference matched to the engine beside them: the baseline engine against the ISO 13789 buffer reference with inflated gains and no infiltration, the corrected engine against the 20 °C-neighbour reference with EN 16798-1 gains and infiltration. Both references carry the three IDF repairs.

| Metric | Baseline discrepancy | Corrected discrepancy | Change in absolute difference | Direction |
|---|---:|---:|---:|---|
| Heating | -14.5 % | -15.7 % | +1.1 pp | worsened |
| Cooling | -8.1 % | -50.9 % | +42.8 pp | worsened |
| Total | -12.9 % | -21.2 % | +8.3 pp | worsened |

In absolute energy, which the percentages obscure on a load this small:

| Metric | Baseline gap (kWh) | Corrected gap (kWh) | Change |
|---|---:|---:|---:|
| Heating | -302.6 | -23.0 | -279.6 |
| Cooling | -56.5 | -13.9 | -42.6 |
| Total | -359.1 | -36.9 | -322.2 |

**Every absolute gap narrows.** Heating by 279.6 kWh (92 %), cooling by 42.6 kWh (75 %). The cooling *percentage* worsens only because the load it is a percentage of fell from 697 kWh to 27 kWh.

## 3. Monthly

| Month | ISO heating | E+ heating | Δ | ISO cooling | E+ cooling | Δ |
|---|---:|---:|---:|---:|---:|---:|
| Jan | 0.01 | 0.04 | -0.04 | 6.82 | 12.25 | -5.43 |
| Feb | 0.00 | 0.00 | +0.00 | 1.25 | 3.85 | -2.60 |
| Mar | 0.00 | 0.00 | -0.00 | 1.15 | 2.65 | -1.50 |
| Apr | 3.42 | 3.90 | -0.47 | 0.00 | 0.00 | +0.00 |
| May | 12.53 | 14.66 | -2.12 | 0.00 | 0.00 | +0.00 |
| Jun | 26.31 | 31.99 | -5.67 | 0.00 | 0.00 | +0.00 |
| Jul | 29.84 | 34.62 | -4.78 | 0.00 | 0.00 | +0.00 |
| Aug | 28.79 | 34.79 | -6.00 | 0.00 | 0.00 | +0.00 |
| Sep | 16.17 | 18.55 | -2.38 | 0.00 | 0.14 | -0.14 |
| Oct | 5.95 | 6.84 | -0.89 | 0.00 | 0.42 | -0.42 |
| Nov | 0.71 | 1.32 | -0.61 | 0.89 | 2.11 | -1.22 |
| Dec | 0.00 | 0.04 | -0.04 | 3.30 | 5.92 | -2.62 |
| **Year** | **123.74** | **146.75** | **-23.01** | **13.41** | **27.34** | **-13.93** |

## Files

- `validation_corrected.csv` — this comparison, the before/after table and the monthly series, machine-readable
- `validation_corrected.pdf` / `.png` — the figure
- `apt305_conditioned.idf` — the matched EnergyPlus model, self-contained (the 8760-value infiltration schedule is embedded, not a companion file)
- `apt305_baseline_repaired.idf` — the baseline reference with the two IDF defects fixed, for audit of the before/after table
- `alignment.md` — the input-alignment table, gains and infiltration matching, and the choice of adjacent-zone representation
- `DISCREPANCY.md` — the loss-path and monthly decomposition, and the comparison to the reference literature
