# Input alignment — the matched EnergyPlus case

Weather: `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. Case: Apt 305, 20 m², five conditioned adjacent zones.

Every parameter that affects the result, marked `ALIGNED` (already identical), `FIXED` (a mismatch this script corrects) or `METHOD` (an irreducible difference between the two approaches). The three rows in capitals are the inputs the corrections moved and which the baseline validation therefore could not have matched.

| Parameter | ISO 52016-1 (corrected) | EnergyPlus (matched case) | Status |
|---|---|---|---|
| Geometry / areas | 5.0 x 4.0 x 2.7 m, 1.62 m2 west glazing, 13.5 m2 outdoor-exposed envelope | same, derived from the same apt305_building module | `ALIGNED` |
| Opaque U-values | ext 1.00, partition 2.50, slab 1.80 W/m2K | Material:NoMass R back-calculated from the same U | `ALIGNED` |
| Surface thermal mass | C = 0 J/m2K on every element | Material:NoMass (no storage) | `ALIGNED` |
| Zone internal capacitance | c_int_per_A_us = 10000 J/m2K (200 kJ/K over 20 m2) | InternalMass, 1 cm of 1000 kg/m3 x 1000 J/(kg K) over the floor area | `ALIGNED` |
| Window U / SHGC | U 5.40 W/m2K, g 0.65 | WindowMaterial:SimpleGlazingSystem 5.40 / 0.65 | `ALIGNED` |
| Window frame fraction | Ffr_wi = 0.25: solar uses 75 % of area, conduction uses 100 % | SHGC scaled to 0.65*0.75 = 0.4875, U and area unchanged | `FIXED` |
| Window shading | the declared 0.25 m overhang yields factor 1.0000 for all 8760 h | no shading surfaces — the two therefore already agree | `ALIGNED` |
| ADJACENT ZONES — the correction under test | the five party surfaces are marked conditioned:True with setpoint 20.0 C, so theta_ztu is held at the setpoint and the ISO 13789 buffer formula is NOT evaluated | SurfaceProperty:OtherSideCoefficients with N2 = 20.0, N3 = 1.0 and N4 = N5 = N6 = N7 = 0, so T_os = 20.0 C at every timestep (see 'Choice of representation' below) | `FIXED` |
| Adjacent surface film | R_c back-calculated assuming R_si = 0.13 both sides | OSC film coefficient 1/0.13 = 7.6923 W/m2K | `FIXED` |
| INTERNAL GAINS — the correction under test | EN 16798-1 tabulated q_int for the building type class, 84.0 W occupants + 60.0 W appliances + 0.0 W lighting over 20 m2; the neighbour-count multiplier is gone | OtherEquipment design levels set to the same 84.0 / 60.0 / 0.0 W on the shared hourly profiles | `FIXED` |
| Internal gain radiant split | f_int_c = 0.4, i.e. 0.6 radiant for every gain | OtherEquipment radiant fraction 0.6 | `FIXED` |
| Ventilation (designed) | 2.0 l/(s m2) constant, H_ve_nat = 48.4 W/K | ZoneVentilation:DesignFlowRate 0.04 m3/s on an always-on schedule with constant coefficients, so the exchange happens every hour. Attaching it to the ideal-loads system instead would deliver it only in the hours the system runs (686 of 8760 here) | `FIXED` |
| INFILTRATION — the correction under test | q50 = 14.0 m3/(h m2)@50Pa over the OUTDOOR-EXPOSED envelope A_env = 13.50 m2 (not the 88.6 m2 whole-surface sum); n50 = q50*A_env/V = 3.5000 1/h over V = 54.0 m3; LBL divide-by-N with N = 20 gives a mean natural rate n_inf = 0.1750 1/h | ZoneInfiltration:DesignFlowRate, Flow/Zone 0.00262500 m3/s (= 0.1750 ACH), constant term A = 1 and B = C = D = 0, modulated hour by hour by an embedded Schedule:Compact carrying the ISO f(t) | `FIXED` |
| Infiltration stack/wind modulation | f(t) = sqrt((Cs*\|theta_int(t-1) - theta_e\| + Cw*u^2) / (Cs*10 + Cw*4^2)), Cs = 0.015, Cw = 0.001; f = 1 at reference conditions. Annual mean f = 0.7589, range 0.0978-1.7106 | E+'s own modulation is A + B\|dT\| + C*u + D*u^2, which is LINEAR in the driving forces and cannot reproduce a square root. The ISO f(t) series is therefore precomputed from the corrected ISO run and embedded as an 8760-value Schedule:Compact. This matches the series hour for hour but makes the coupling ONE-WAY: f(t) carries the ISO zone temperature, not E+'s. The --inf-mode constant run bounds what that costs. | `FIXED (one-way)` |
| Setpoints | heat 18/15, cool 26/28 driven by the hourly profiles | DualSetpoint from the same profiles, control type schedule = 4 | `ALIGNED` |
| Control temperature | operative temperature (0.5*T_air + 0.5*T_mr) | ZoneControl:Thermostat:OperativeTemperature, radiative fraction 0.5 | `FIXED` |
| HVAC | ideal, 10 MW capacity | ZoneHVAC:IdealLoadsAirSystem, NoLimit | `ALIGNED` |
| Latent load | gated: charged only in hours the cooling plant runs; 1.14 kWh/yr, reported separately from the sensible need | humidification and dehumidification control both None, and the SENSIBLE ideal-loads variables are the ones summed, so the E+ figure is sensible-only. Heating is asserted to equal its total; the small residual latent cooling is reported beside the ISO gated term | `FIXED` |
| Calendar / day of week | profile generator uses AU holidays, Jan 1 lands on a Thursday | RunPeriod start day Thursday; weather-file holidays off | `FIXED` |
| Daylight saving | not modelled | Use Weather File Daylight Saving Period = No | `FIXED` |
| Timestep | hourly | 6 per hour; results aggregated to hourly and annual | `METHOD` |
| Solar distribution | f_sol_c = 0.1 convective, the rest to the surface nodes | FullInteriorAndExterior ray tracing | `METHOD` |
| Surface heat transfer | C2 correction: h_ce = 4v + 4 on outdoor-exposed surfaces; the ISO constant elsewhere | TARP/DOE-2 dynamic algorithms — a different correlation, not a different intent | `METHOD` |
| Conduction discretisation | five-node RC per element, ISO 52016-1 Annex B | conduction transfer functions | `METHOD` |

24 parameters checked — 8 already aligned, 12 mismatches corrected, 4 irreducible method differences.

### Choice of adjacent-zone representation

Two representations are admissible. This case uses **`OtherSideCoefficients`
with a constant boundary temperature** (`N2 = 20.0`, `N3 = 1.0`,
`N4 = N5 = N6 = N7 = 0`, so `T_os = 20.0` C at every timestep), rather than
explicit adjacent thermal zones each with its own ideal-loads system.

The reason is that this is the closer analogue of what the corrected ISO engine
actually does. `_adjacent_zone_conditioning` does not *simulate* the neighbour:
a zone marked `conditioned: True` has its `theta_ztu` **held at the declared
setpoint**, and the ISO 13789 buffer expression is never evaluated for it. A
fixed-temperature boundary reproduces that substitution exactly. Explicit
adjacent zones would instead simulate five neighbours whose air temperature
would float within the ideal-loads system's control band and respond to their
own gains and their own exposures — a richer model than the corrected ISO engine
contains, and one that would introduce a difference the ISO side has no
counterpart for. Since the object of this comparison is the corrected engine's
own treatment, the fixed boundary is the faithful choice.

The cost is that the E+ neighbour cannot deviate from 20 C even momentarily,
which is exactly the corrected ISO engine's assumption too, so it is not a cost
against *this* comparison. It is a shared idealisation of both models against
the real building, and is recorded as such.


### Internal gains

The corrected engine returns the EN 16798-1 tabulated `q_int` for the building type class and no longer multiplies by the neighbour count. Probed with unit profiles, so each category is isolated exactly; the hourly profiles are shared with EnergyPlus, so setting the `OtherEquipment` design levels to these watts reproduces the ISO gain hour for hour.

| Category | Corrected engine (W) | Over 20 m² (W/m²) | Baseline engine (W) |
|---|---:|---:|---:|
| Occupants | 84.00 | 4.20 | 616.14 |
| Appliances | 60.00 | 3.00 | 440.10 |
| Lighting | 0.00 | 0.00 | 0.00 |

The script asserts that the neighbour-count multiplier is absent before building the IDF: if it were back, these design levels would not reproduce the ISO gains and the run would stop.

### Infiltration

| Quantity | Value | Source |
|---|---:|---|
| `q50` | 14.0 m³/(h·m²) @ 50 Pa | adopted Australian pre-2006 band, `_q50_for_construction_age` |
| `A_env` | 13.50 m² | outdoor-exposed surfaces only (`_envelope_area_m2`), not the 88.6 m² whole-surface sum |
| `V` | 54.0 m³ | `_zone_volume_m3` |
| `n50 = q50·A_env/V` | 3.5000 h⁻¹ | |
| LBL divisor `N` | 20 | sheltered low-rise |
| `n_inf = n50/N` | 0.1750 h⁻¹ | mean natural rate |
| Design flow | 0.00262500 m³/s | `ZoneInfiltration:DesignFlowRate`, `Flow/Zone` |
| Modulation `f(t)` | mean 0.7589, range 0.0978–1.7106 | embedded `Schedule:Compact`, 8760 values |
| Mean `H_ve_inf` | 2.367 W/K | against `H_ve_nat` = 48.4 W/K designed ventilation |
| Annual infiltration energy | 95.01 kWh | `Σ H_ve_inf·(θ_int − θ_e)` |

**How the stack/wind modulation was represented.** EnergyPlus's own modulation is `A + B|ΔT| + C·u + D·u²`, which is linear in the driving forces. The ISO expression is `f = √((Cs·|ΔT| + Cw·u²) / (Cs·ΔT_ref + Cw·u_ref²))` — a square root of a linear combination, which no choice of `A…D` reproduces. The series is therefore precomputed from the corrected ISO run and embedded as an 8760-value schedule with `A = 1` and `B = C = D = 0`.

This matches the series hour for hour, at the cost of making the coupling **one-way**: `f(t)` carries the ISO run's zone temperature, not EnergyPlus's. The two zone temperatures are close but not identical, so a second-order error remains. It is bounded by the `--inf-mode constant` sensitivity run reported in `DISCREPANCY.md`, rather than asserted to be small.

### Three defects found in the shared IDF builder

All three were found while building this case, all three are in `examples/baseline_vs_energyplus.py`, and all three are now fixed there.

1. **Outdoor air was never delivered.** `DesignSpecification:OutdoorAir` was written as `Apt305_OA, Flow/Area, 0.002, , , , Always1`, which puts the rate in `N1` (*Outdoor Air Flow per Person*). Method `Flow/Area` reads `N2` (*per Zone Floor Area*), which was blank and therefore zero. Every EnergyPlus run made with this builder had **no designed ventilation at all**, while the ISO side carried `H_ve = 48.4 W/K`.
2. **Ventilation was attached to the wrong object.** Outdoor air on `ZoneHVAC:IdealLoadsAirSystem` is delivered only in the hours the system runs — 686 of 8760 in this case — and not at all while the zone free-floats in the deadband. ISO 52016-1 applies `H_ve` every hour. It is now a `ZoneVentilation:DesignFlowRate` zone air exchange on an always-on schedule with constant coefficients.
3. **Heating was not sensible-only.** Humidification control was `ConstantSupplyHumidityRatio`, so once the ventilation air actually flowed the ideal loads humidified it and booked ~300 kWh/yr of latent as heating. Both humidity controls are now `None`.

The committed `results/paper/baseline_vs_ep_v2/` was produced before any of them was found. `validation_corrected.md` reports what they cost.
