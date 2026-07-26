# Physics changes relative to the vendored baseline

Each change lives on its own branch, layered so that the difference between two
adjacent branches isolates exactly one modification.

| Branch                                    | Adds     | Cumulative contents        |
| ----------------------------------------- | -------- | -------------------------- |
| `claude/pybuildingenergy-baseline-anjro8` | —        | unmodified upstream        |
| `claude/dynamic-window-properties-anjro8` | Change 1 | dynamic window properties  |
| `claude/window-plus-dynamic-hce-anjro8`   | Change 2 | change 1 + wind-dependent surface heat transfer coefficients |

---

## Change 1 — Dynamic window properties

### Severity
**Medium** — biases both the solar gain through glazing and the window's share
of transmission loss. The solar side is a systematic over-admission that grows
with latitude and with how far the sun sits off the glazing normal; the
transmission side scales with how far local wind departs from 4 m/s.

### Applies to
The single-zone ISO 52016-1 engine: both
`ISO52016._Temperature_and_Energy_needs_calculation_core` and
`ISO52016._Temperature_and_Energy_needs_calculation_core_ahu_causal`
in `pybuildingenergy/src/pybuildingenergy/source/utils.py`.

The multizone engine is untouched on this branch. Note that upstream already
wires a dynamic `h_ce` into the multizone free-floating engine via
`_dynamic_external_convection_h`; the single-zone engine did not use it.

### Root cause
EN ISO 52016-1 treats both window properties as constants:

* **`U_win`** is fixed for the whole year. It is a rated value measured against
  standard surface films, one of which assumes a frozen 4 m/s wind speed
  (EN ISO 13789 §9.5, consistent with ISO 6946). Real external film resistance
  moves with wind.
* **`g_win`** is applied at its normal-incidence value at every sun position.
  Physically, reflectance at the air-glass interfaces climbs towards unity at
  grazing incidence, so a window admits far less than its rated `g` when the sun
  is steeply off-normal. Applying the rated value regardless over-admits solar
  heat, and the error is worst exactly when the sun is low.

### Fix

**1. Time-step window thermal resistance**

    R_win(t) = 1 / U_win(t) - R_si - R_se(t)

Implemented as a split, which matters:

* The **construction** resistance `R_c` stays fixed. `Conductance_node_of_element`
  recovers it by subtracting standard film resistances from the rated
  `U_win`; that subtraction *must* keep using the standard values, because the
  rated `U` was measured against them. Changing it there would corrupt the
  material resistance rather than model anything.
* Only the **external film** at the hourly boundary node floats, via
  `h_ce = 4 + 4·v` (Magni et al. 2022, Eq. 2-7), evaluated per time step from
  `WS10m`.

The effect is that the window's *effective* U rises in wind, falls in calm air,
and returns exactly to the rated value at 4 m/s. Only transparent elements are
treated this way on this branch — extending it to opaque surfaces is change 2.
Ground-contact (`GR`) and adiabatic (`AD`) elements are excluded outright: they
are not wind exposed and an external convective coefficient on them is
meaningless.

**2. Solar-angle dependent correction factor `F_W`**

    F_W = (F_W,diff · I_sol,diff,t + F_W,dir · I_sol,dir,t · F_sh,obst,t)
          / (I_sol,diff,t + I_sol,dir,t · F_sh,obst,t)

`F_W,dir(θ)` comes from the Karlsson & Roos angular model

    g(θ)/g(0) = 1 - a·z^α - b·z^β - c·z^γ,    z = θ/90,   a + b + c = 1

evaluated at the hourly solar incidence angle. That angle was already being
computed inside `Solar_irradiance_calculation` for the irradiance
decomposition and then discarded; it is now returned and stored per orientation
as `theta_inc_<ORI>`.

The direct term carries `F_sh,obst` because radiation that obstacles block never
reaches the glazing and so must not be given weight in the average.

> **Provenance of the coefficients.** The functional form is Karlsson & Roos
> (2000). The shipped coefficients are **not** their published table, which is
> paywalled and was not consulted. They were fitted to a Fresnel + Beer-Lambert
> reference curve for uncoated clear float glass (n = 1.52, 4 mm, K = 26 m⁻¹) by
> `tools/derive_karlsson_roos_coefficients.py`, reproducing it to within 0.5 %
> over 0–90°. `F_W,diff` is the cosine-weighted hemispherical average of that
> same curve, not an assumed constant. For coated or solar-control glazing,
> supply the published coefficients per surface via
> `window_angular_coefficients` rather than relying on these defaults.
>
> Sanity anchor: the single-pane hemispherical average comes out at **0.907**,
> essentially the constant **0.9** that ISO 13790 / ISO 52016 use for the
> non-scattered-radiation correction.

### Configuration

All options are read from `simulation_options` or `building_parameters`, or
passed as engine kwargs.

| Option | Default | Meaning |
| --- | --- | --- |
| `dynamic_window_properties` | `True` | Master switch. `False` restores exact baseline behaviour. |
| `window_angular_solar_model` | `karlsson_roos` | Also `constant` (fixed 0.9) or `none`. |
| `window_convection_model` | `simplecombined` | Any model `_dynamic_external_convection_h` supports: `doe2`, `mowitt`, `blast`, `table`. |
| `glazing_panes` *(per surface)* | `2` | Selects the default coefficient set. |
| `window_angular_coefficients` *(per surface)* | — | `(a, b, c, α, β, γ)` override. |
| `window_angular_diffuse_factor` *(per surface)* | — | Overrides the integrated `F_W,diff`. |

The default is **on** so that running an unmodified example script exercises the
new physics, which is what makes a branch-to-branch diff meaningful.

### Validation

Two exact-reproduction tests, both passing:

1. **Change is inert when disabled.** With `dynamic_window_properties=False`,
   all 288 compared metrics match the baseline engine *exactly* (zero
   tolerance), confirming the modification is fully isolated behind its switch.

2. **`h_ce` collapses onto the ISO constant at 4 m/s.** With the weather forced
   to a constant `WS10m = 4.0` and the angular model disabled, all 288 metrics
   again match baseline *exactly* — i.e. `4 + 4·v` reproduces the ISO 13789
   constant of 20 W/(m²K) at the wind speed the standard assumes, so the change
   adds no offset of its own.

Reproduce with:

```bash
python tools/run_case.py --src pybuildingenergy/src --out on.json
python tools/run_case.py --src pybuildingenergy/src --out off.json \
    --option dynamic_window_properties=false
python tools/compare_runs.py base.json off.json --assert-identical

python tools/run_case.py --src pybuildingenergy/src --out w4.json \
    --force-wind 4.0 --option window_angular_solar_model=none
python tools/compare_runs.py base_w4.json w4.json --assert-identical
```

Upstream test suite: **289 passed, 2 failed, 10 skipped** — identical to the
baseline branch. The two failures are pre-existing and network-caused
(`test_iso52016_calculation`, `test_iso52016_calculation_climatedata` reach out
to PVGIS / climatedataforbuildings.eu, blocked in this environment).

New unit tests: `tests/test_dynamic_window_properties.py`, 32 passing, covering
endpoint values, monotonicity, boundedness, the Fresnel fit quality, the
irradiance weighting, the shaded-beam edge case, and option resolution.

### Measured effect

Archetype_ITA_SFH_2010, Milan 2020 EPW, 120 m² treated floor area.
Milan mean wind is **2.65 m/s**, with **77.7 %** of hours below the ISO's
assumed 4 m/s — so the ISO constant overestimates external convection most of
the year here.

| Metric | Baseline | Change 1 | Δ | rel. |
| --- | ---: | ---: | ---: | ---: |
| Annual heating need (kWh) | 34732.0 | 34625.3 | −106.6 | −0.31 % |
| Annual cooling need (kWh) | 4258.4 | 4228.8 | −29.6 | −0.69 % |
| Solar gains (kWh) | 3289.6 | 2929.6 | −360.0 | **−10.94 %** |
| Window transmission loss (kWh) | 2612.0 | 2382.4 | −229.6 | **−8.79 %** |
| Window transmission gain (kWh) | 471.3 | 586.0 | +114.7 | **+24.34 %** |
| Opaque transmission loss (kWh) | 31712.4 | 31856.4 | +143.9 | +0.45 % |

Reading these:

* **Solar gains fall ~11 %** — the angular correction stops the model admitting
  the full normal-incidence `g` at steep sun angles.
* **Window transmission loss falls ~8.8 %** — with mean `h_ce` at 14.6 rather
  than 20 W/(m²K), the external film resistance is higher, so the effective
  `U_win` is lower. This is the direction De Luca et al. report for low-wind
  sites, and it is the sign check that matters: had the loss risen in a
  sub-4 m/s climate, the implementation would be wrong.
* **Opaque loss rises slightly** — a second-order consequence of lower solar
  gains cooling the zone, not a direct effect. Opaque surfaces are untouched on
  this branch; change 2 addresses them.
* **Net heating/cooling barely moves (< 1 %)** because the two effects oppose:
  less solar gain raises heating demand, while reduced window transmission loss
  lowers it. The near-cancellation on the annual bottom line is precisely why
  the per-flow numbers above are the informative ones — and why layering the
  changes one branch at a time is worth doing.

### Caveats

* `WS10m` is used **unadjusted**. The `4 + 4·v` correlation wants wind at the
  surface, but EPW/PVGIS report it at 10 m in open terrain; EnergyPlus applies a
  terrain and height reduction first. A sheltered wall sees considerably less
  than the met-station wind, so this implementation likely overstates the
  wind swing. Using raw `WS10m` reproduces the Magni convention exactly, which
  is why it is the starting point, but a terrain factor is the obvious next
  refinement.
* The Karlsson-Roos defaults describe **uncoated clear float glass**. Low-e and
  solar-control coatings have materially different angular behaviour and should
  use per-surface overrides.
* `g(θ)` is approximated by the transmittance curve `τ(θ)/τ(0)`. The secondary
  inward-flowing fraction of absorbed radiation is slightly less angle-dependent,
  so the true `g` curve is a little flatter than modelled here.

---

## Change 2 — Wind-dependent surface heat transfer coefficients

Layered on top of change 1: the same wind-dependent external film, extended from
windows to **every air-exposed surface**.

### Severity
**Medium–High** — biases transmission losses on all air-exposed surfaces. The
effect is far larger than change 1 on the annual bottom line, because opaque
envelope area dominates glazing area in this archetype (and in most buildings).

### Applies to
Both single-zone cores, as change 1. Opaque and transparent elements now carry
**separate model selectors**, so setting the opaque model back to `table`
recovers change-1-only behaviour exactly — which is what makes the two changes
separately measurable.

### Root cause
EN ISO 52016-1 mandates constant surface heat transfer coefficients taken from
EN ISO 13789 §9.5 (consistent with the surface resistances in ISO 6946). Those
constants rest on two frozen assumptions: a linearised radiative exchange, and a
**fixed 4 m/s wind speed**.

The 20 W/(m²K) external convective constant is exactly `4·v + 4` evaluated at
`v = 4 m/s`. Wherever local wind differs from 4 m/s — which is most hours in most
climates — the standard misstates external convection, and makes transmission
overly sensitive to outdoor temperature. De Luca et al. (2020) measured
heating-load RMSD falling from 1.23 to 0.58 W·m⁻² on replacing the fixed value
with a wind-dependent one.

### Fix
The hourly external-node coupling uses `h_ce = 4 + 4·v` (Magni et al. 2022,
Eq. 2-7) for all `EXT` surfaces. As in change 1:

* `R_c` in `Conductance_node_of_element` is **left at the ISO constant** — it is
  needed to recover the construction-only resistance from the rated U-value, and
  is ISO-compliant as-is.
* `GR` (ground-contact) and `AD` (adiabatic) elements are excluded: they are not
  wind exposed.

Upstream already ships `_dynamic_external_convection_h` with the DOE-2, MoWiTT,
BLAST and simple-combined correlations, and already wires it into the multizone
free-floating engine — but the single-zone engine never used it. This change is
therefore largely a **port of existing upstream physics** into the single-zone
engine, plus the default flip, rather than new correlations.

### Configuration

| Option | Default | Meaning |
| --- | --- | --- |
| `dynamic_surface_heat_transfer` | `True` | Master switch for change 2. `False` gives change-1-only behaviour. |
| `external_convection_model` | `simplecombined` | Opaque surfaces. Also `doe2`, `mowitt`, `blast`, `table`. Upstream's option names are reused, so an explicitly configured value still wins. |
| `external_convection_h_min` | `2.0` | Floor on `h_ce`, so a dead-calm hour cannot produce a near-zero coupling. |

### Validation

Three exact-reproduction tests, all passing:

1. **Reduces to change 1.** With `dynamic_surface_heat_transfer=False`, all 288
   metrics match the change-1 branch *exactly*.
2. **Collapses onto the ISO constant at 4 m/s.** With `WS10m` forced to 4.0 and
   the angular model off, all 288 metrics match the **baseline** engine exactly
   — now with *every* surface dynamic, not just windows.
3. **Solar is untouched.** Solar gains are bit-identical between change 1 and
   change 2 (0.00 % difference), confirming change 2 is purely a surface
   coefficient change.

Upstream test suite: **289 passed, 2 failed, 10 skipped** — identical to
baseline; the two failures are the same pre-existing network ones.
AIB unit tests: **52 passing** (32 from change 1 + 20 new).

### Measured effect

Same case as change 1 (Archetype_ITA_SFH_2010, Milan 2020 EPW).

| Metric (kWh) | Baseline | Change 1 | Change 2 | C1 vs base | C2 vs C1 | C2 vs base |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Annual heating need | 34732.0 | 34625.3 | 33043.6 | −0.31 % | **−4.57 %** | −4.86 % |
| Annual cooling need | 4258.4 | 4228.8 | 5384.7 | −0.69 % | **+27.33 %** | +26.45 % |
| Solar gains | 3289.6 | 2929.6 | 2929.6 | −10.94 % | 0.00 % | −10.94 % |
| Window transm. loss | 2612.0 | 2382.4 | 2421.1 | −8.79 % | +1.62 % | −7.31 % |
| Window transm. gain | 471.3 | 586.0 | 563.5 | +24.34 % | −3.85 % | +19.56 % |
| Opaque transm. loss | 31712.4 | 31856.4 | 30184.4 | +0.45 % | **−5.25 %** | −4.82 % |
| Opaque transm. gain | 3812.2 | 3721.3 | 4850.3 | −2.39 % | **+30.34 %** | +27.23 % |
| Total transm. loss | 33857.2 | 33730.3 | 32104.0 | −0.37 % | −4.82 % | −5.18 % |
| Ventilation loss | 2613.3 | 2610.1 | 2613.7 | −0.12 % | +0.14 % | +0.01 % |

Reading these:

* **Change 2 dominates change 1 on the bottom line.** Heating falls 4.6 % and
  cooling rises 27 % from change 2 alone, against sub-1 % for change 1. Opaque
  envelope area is simply much larger than glazing area, so the same physics
  applied to opaque surfaces moves far more energy.
* **Direction is set by the climate.** Milan's mean wind is 2.65 m/s with 77.7 %
  of hours below 4 m/s, so mean `h_ce` is 14.6 rather than 20 W/(m²K). The
  envelope is better insulated on its outer face than the ISO assumes, hence
  lower heating demand and — the same mechanism working against you in summer —
  substantially worse heat rejection and higher cooling demand.
* **Cooling is where this bites.** The +27 % cooling change is the headline
  result, and matches the expectation that a wind-dependent `h_ce` matters most
  in cooling and in windy or cooling-weighted climates. For a Melbourne-type run
  this is the term to watch.

### Caveats

* The **unadjusted `WS10m`** caveat from change 1 applies with more force here,
  because it now affects the whole envelope. `4 + 4·v` wants wind at the surface;
  EPW reports it at 10 m in open terrain. EnergyPlus applies a terrain/height
  reduction first, and a sheltered wall sees far less than the met-station wind.
  Raw `WS10m` reproduces the Magni convention exactly, which is why it is the
  starting point, but a terrain factor is the clear next step — and given the
  magnitude of the cooling shift, it should be quantified before these numbers
  are used for anything load-bearing.
* The **radiative** constant `radiative_heat_transfer_coefficient_external =
  4.14` is the other half of the ISO's frozen assumptions (linearised radiative
  exchange, entangled with the sky-longwave term De Luca found coupled to this
  one). It is deliberately **not** changed here. Upstream already provides
  `_dynamic_external_radiative_h_and_ref` and a `dynamic` `h_re` model, so this
  is a natural change 3 on a further branch.
* Only the **single-zone** engine is modified. The multizone engine retains
  upstream behaviour, where a dynamic `h_ce` is available but defaults to
  `table`.
