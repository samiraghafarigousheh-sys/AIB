# Defect notice — the EnergyPlus column in this directory

**Nothing in this directory has been changed.** The numbers below are still the
ones `baseline_vs_energyplus.csv`, `.md` and `.png` carry, and `F1` in
`results/paper/figures/` is still built from them. This file only records what
was later found out about them.

## What was found

Three defects in the EnergyPlus input, all in the shared IDF builder
`examples/baseline_vs_energyplus.py`, were found in
`results/paper/validation_corrected/`. All three affect the **EnergyPlus
column** only. The ISO 52016-1 column is unaffected.

1. **No ventilation air was delivered.** `DesignSpecification:OutdoorAir` was
   emitted as `Apt305_OA, Flow/Area, 0.002, , , , Always1`, which puts the rate
   in `N1` (*Outdoor Air Flow per Person*). The method `Flow/Area` reads `N2`
   (*per Zone Floor Area*), which was blank and therefore zero. EnergyPlus ran
   with no designed ventilation at all, while the ISO side carried
   `H_ve = 48.4 W/K`.
2. **Ventilation was attached to the wrong object.** Outdoor air on
   `ZoneHVAC:IdealLoadsAirSystem` is delivered only in the hours the system
   runs, and not while the zone free-floats in the deadband. ISO 52016-1
   applies `H_ve` every hour.
3. **Heating was not sensible-only.** Humidification control was
   `ConstantSupplyHumidityRatio`, which books humidification of the ventilation
   air as heating once that air flows.

All three are now fixed in `examples/baseline_vs_energyplus.py`.

## What it cost

Re-running the **unchanged** baseline engine against a reference with all three
repaired, on the same weather file:

| Metric | ISO 52016-1 | E+ as published here | E+ repaired | Difference as published | Difference repaired |
|---|---:|---:|---:|---:|---:|
| Heating | 1,779.36 | 1,120.25 | 2,081.97 | **+58.8 %** | **−14.5 %** |
| Cooling | 640.84 | 697.16 | 697.35 | −8.1 % | −8.1 % |

The cooling figure is essentially unaffected. **The heating figure is not.** The
headline "+58.8 % over-prediction" is an artefact of the EnergyPlus input, not a
property of the ISO engine: against a correctly configured reference the
baseline engine **under**-predicts heating by 14.5 %.

This matters beyond the number, because the paper uses the +58.8 % to contrast
against Zakula et al., who report the simplified method *under*-estimating
heating. That contrast does not survive the repair — the corrected sign agrees
with the literature.

## Where to look

`results/paper/validation_corrected/` — `validation_corrected.md` for the
before/after tables, `alignment.md` for the full input alignment, and
`DISCREPANCY.md` for the decomposition. `apt305_baseline_repaired.idf` there is
the repaired baseline reference, for audit.
