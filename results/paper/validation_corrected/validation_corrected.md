# Corrected ISO 52016-1 against a matched EnergyPlus reference

Weather: `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. Case: Apt 305, 20 m², five conditioned adjacent zones. EnergyPlus 24.1.0.

## Summary

**Relative agreement improved on cooling and worsened on heating.** **In absolute energy the gap narrowed on both — heating by 91 %, cooling by 97 %.** The two are not in conflict: the corrections cut the loads themselves by roughly an order of magnitude, so a much smaller absolute residual sits on a much smaller denominator. Neither statement should be quoted without the other.

- **Heating**: the ISO engine differs from the matched reference by **-17.5 %**, against **-14.5 %** for the baseline engine against its own matched reference — worsened by 3.0 percentage points. In absolute terms the gap falls from 302.6 kWh to 26.1 kWh.
- **Cooling**: **-7.8 %** against **-8.1 %** — improved by 0.3 percentage points. In absolute terms the gap *falls*, from 56.5 kWh to 1.7 kWh.
- **Largest remaining contributor in absolute energy**: sensible heating, -26.1 kWh, against -1.7 kWh on sensible cooling. See `DISCREPANCY.md`.

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
| Heating | 122.88 | 148.97 | -26.09 | -17.5 % | 6.14 | 7.45 |
| Cooling | 19.90 | 21.59 | -1.69 | -7.8 % | 0.99 | 1.08 |
| Total | 142.78 | 170.56 | -27.79 | -16.3 % | 7.14 | 8.53 |

Differences are stated **relative to the EnergyPlus reference**, following the existing validation. Both engines are sensible-only: the ISO side reports gated latent separately (1.51 kWh) and the EnergyPlus ideal loads carry 0.93 kWh of latent cooling with humidification disabled.

## 2. Before and after

Both rows are measured against a reference matched to the engine beside them: the baseline engine against the ISO 13789 buffer reference with inflated gains and no infiltration, the corrected engine against the 20 °C-neighbour reference with EN 16798-1 gains and infiltration. Both references carry the three IDF repairs.

| Metric | Baseline discrepancy | Corrected discrepancy | Change in absolute difference | Direction |
|---|---:|---:|---:|---|
| Heating | -14.5 % | -17.5 % | +3.0 pp | worsened |
| Cooling | -8.1 % | -7.8 % | -0.3 pp | **improved** |
| Total | -12.9 % | -16.3 % | +3.4 pp | worsened |

In absolute energy, which the percentages obscure on a load this small:

| Metric | Baseline gap (kWh) | Corrected gap (kWh) | Change |
|---|---:|---:|---:|
| Heating | -302.6 | -26.1 | -276.5 |
| Cooling | -56.5 | -1.7 | -54.8 |
| Total | -359.1 | -27.8 | -331.3 |

**Every absolute gap narrows.** Heating by 276.5 kWh (91 %), cooling by 54.8 kWh (97 %). The cooling *percentage* worsens only because the load it is a percentage of fell from 697 kWh to 22 kWh.

## 3. Monthly

| Month | ISO heating | E+ heating | Δ | ISO cooling | E+ cooling | Δ |
|---|---:|---:|---:|---:|---:|---:|
| Jan | 0.01 | 0.05 | -0.04 | 9.61 | 10.41 | -0.80 |
| Feb | 0.00 | 0.00 | +0.00 | 2.12 | 2.65 | -0.53 |
| Mar | 0.00 | 0.00 | -0.00 | 1.82 | 1.99 | -0.18 |
| Apr | 3.41 | 3.97 | -0.56 | 0.00 | 0.00 | +0.00 |
| May | 12.47 | 14.86 | -2.39 | 0.00 | 0.00 | +0.00 |
| Jun | 26.12 | 32.52 | -6.40 | 0.00 | 0.00 | +0.00 |
| Jul | 29.64 | 35.12 | -5.47 | 0.00 | 0.00 | +0.00 |
| Aug | 28.57 | 35.26 | -6.68 | 0.00 | 0.00 | +0.00 |
| Sep | 16.05 | 18.82 | -2.77 | 0.00 | 0.04 | -0.04 |
| Oct | 5.90 | 7.00 | -1.10 | 0.09 | 0.17 | -0.08 |
| Nov | 0.71 | 1.34 | -0.64 | 1.45 | 1.50 | -0.06 |
| Dec | 0.00 | 0.04 | -0.04 | 4.81 | 4.83 | -0.01 |
| **Year** | **122.88** | **148.97** | **-26.09** | **19.90** | **21.59** | **-1.69** |

## Files

- `validation_corrected.csv` — this comparison, the before/after table and the monthly series, machine-readable
- `validation_corrected.pdf` / `.png` — the figure
- `apt305_conditioned.idf` — the matched EnergyPlus model, self-contained (the 8760-value infiltration schedule is embedded, not a companion file)
- `apt305_baseline_repaired.idf` — the baseline reference with the two IDF defects fixed, for audit of the before/after table
- `alignment.md` — the input-alignment table, gains and infiltration matching, and the choice of adjacent-zone representation
- `DISCREPANCY.md` — the loss-path and monthly decomposition, and the comparison to the reference literature
