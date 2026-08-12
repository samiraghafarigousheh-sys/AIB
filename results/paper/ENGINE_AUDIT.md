# Engine audit — is every correction in HEAD, and does each still work?

HEAD `65fde6c`. Case `examples/apt305_building.py`. Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`.

Engine source clean at audit time: **yes**. Uncommitted paths, none under `pybuildingenergy/src`: `results/paper/ENGINE_AUDIT.json`, `tools/diagnostics/engine_audit.py`.

Every correction is established **twice**: located in the HEAD working tree and blamed to the commit that introduced it (Part A), then measured on the case study (Part B). Presence in a commit message is not presence in HEAD, and presence in HEAD is not the same as being reachable — a correction can be present and overridden downstream.

This is a verification record. Nothing was repaired to produce it.

## Summary

| # | Correction | Present | Verdict | File : line | Introduced by |
| ---: | --- | :-: | :-: | --- | --- |
| 1 | C1 — dynamic window transmittance | PRESENT | VERIFIED | `utils.py:3143` | `a66eec7d7` |
| 2 | C2 — wind-dependent external h_ce | PRESENT | VERIFIED | `utils.py:3063` | `56f5d0883` |
| 3 | C2b — ASHRAE terrain and height wind profile | PRESENT | VERIFIED | `utils.py:2313` | `fab0ab0d4` |
| 4 | Ventilation — additive infiltration path | PRESENT | VERIFIED | `utils.py:636` | `107983200` |
| 5 | Infiltration A1 — supply temperature at theta_e | PRESENT | VERIFIED | `utils.py:9160` | `c641378a9` |
| 6 | Infiltration A3 — envelope scoped to outdoor-exposed | PRESENT | VERIFIED | `utils.py:525` | `bb678a9dd` |
| 7 | Infiltration — Australian q50 age bands | PRESENT | VERIFIED | `utils.py:460` | `421c2823c` |
| 8 | Latent — deadband, occupant moisture, dt, sign | PRESENT | VERIFIED | `utils.py:64` | `8263fca5f` |
| 9 | Latent — plant-operation gate | PRESENT | VERIFIED | `utils.py:10088` | `82a909d3f` |
| 10 | Internal gains — neighbour-count de-inflation | PRESENT | VERIFIED | `ventilation.py:632` | `5aca6ce43` |
| 11 | Adjacent zones — conditioned-neighbour branch | PRESENT | VERIFIED | `utils.py:962` | `73390763d` |
| 12 | Ground contact — no implicit slab-on-ground fallback | PRESENT | VERIFIED | `utils.py:1311` | `418496bf2` |
| 13 | Ground temperature — hemisphere-resolved coldest month | PRESENT | VERIFIED | `utils.py:887` | `ef312fe42` |
| 14 | Classification — ground class needs a declared boundary | PRESENT | VERIFIED | `utils.py:1165` | `9fd8c696c` |
| 15 | Closure — ADJ transmission in the inventory | PRESENT | VERIFIED | `utils.py:1255` | `6e549fa18` |
| 16 | Closure — transmission at the outer face, net of short-wave | PRESENT | VERIFIED | `utils.py:9725` | `6e549fa18` |

**All 16 corrections are present in HEAD and each is verified by the test stated for it.**

## Part A — Provenance: is every correction actually in HEAD?

The anchor for each row is a line the correction *itself* introduced, not a structural line that happens to sit nearby. That distinction matters: blaming a `def` or a dict-opening brace returns the vendored baseline even when the correction is present, which would make a correct engine look gutted.

| # | Correction | File : line | Anchor | Commit | Ancestor of HEAD |
| ---: | --- | --- | --- | --- | :-: |
| 1 | C1 — dynamic window transmittance | `pybuildingenergy/src/pybuildingenergy/source/utils.py:3143` | karlsson_roos_direct_factor, the angular beam model | `a66eec7d7` Change 1: dynamic window properties (U_win(t | yes |
| 2 | C2 — wind-dependent external h_ce | `pybuildingenergy/src/pybuildingenergy/source/utils.py:3063` | _resolve_opaque_convection_model, which defaults opaque surfaces to 4+4u | `56f5d0883` Change 2: wind-dependent surface heat transf | yes |
| 3 | C2b — ASHRAE terrain and height wind profile | `pybuildingenergy/src/pybuildingenergy/source/utils.py:2313` | local_wind_speed_factor, the two-layer profile | `fab0ab0d4` Wind profile: drive h_ce with the wind local | yes |
| 4 | Ventilation — additive infiltration path | `pybuildingenergy/src/pybuildingenergy/source/utils.py:636` | the H_ve_inf return, rho*cp*V*n_inf(t) | `107983200` Ventilation/infiltration fix: additive H_ve_ | yes |
| 5 | Infiltration A1 — supply temperature at theta_e | `pybuildingenergy/src/pybuildingenergy/source/utils.py:9160` | the A1 source-term addition, S_ve += H_ve_inf * theta_e | `c641378a9` Item 1 (A1): supply infiltration air at outd | yes |
| 6 | Infiltration A3 — envelope scoped to outdoor-exposed | `pybuildingenergy/src/pybuildingenergy/source/utils.py:525` | the outdoor-air classification used to scope A_env | `bb678a9dd` Item 2 (A3): scope infiltration envelope are | yes |
| 7 | Infiltration — Australian q50 age bands | `pybuildingenergy/src/pybuildingenergy/source/utils.py:460` | the recalibrated "1991-2005": 14.0 band | `421c2823c` Item 3: recalibrate envelope permeability q5 | yes |
| 8 | Latent — deadband, occupant moisture, dt, sign | `pybuildingenergy/src/pybuildingenergy/source/utils.py:64` | the rh_int_min_pct deadband parameter | `8263fca5f` Latent heat fix: EN 16798-1 deadband, occupa | yes |
| 9 | Latent — plant-operation gate | `pybuildingenergy/src/pybuildingenergy/source/utils.py:10088` | _cooling_on, the gate the latent charge is masked by | `82a909d3f` Defect B: gate latent conditioning to hours  | yes |
| 10 | Internal gains — neighbour-count de-inflation | `pybuildingenergy/src/pybuildingenergy/source/ventilation.py:632` | the note and code dropping the per-neighbour scaling | `5aca6ce43` Internal gains: stop scaling the zone's own  | yes |
| 11 | Adjacent zones — conditioned-neighbour branch | `pybuildingenergy/src/pybuildingenergy/source/utils.py:962` | the branch holding theta_ztu at the declared setpoint | `73390763d` Adjacent zones: hold conditioned neighbours  | yes |
| 12 | Ground contact — no implicit slab-on-ground fallback | `pybuildingenergy/src/pybuildingenergy/source/utils.py:1311` | _ground_contact_area: absence of a ground surface means none | `418496bf2` Ground contact: absence of a ground surface  | yes |
| 13 | Ground temperature — hemisphere-resolved coldest month | `pybuildingenergy/src/pybuildingenergy/source/utils.py:887` | the latitude-sign return | `ef312fe42` Ground: pick the coldest month from the hemi | yes |
| 14 | Classification — ground class needs a declared boundary | `pybuildingenergy/src/pybuildingenergy/source/utils.py:1165` | the 'declared to be' guard replacing the sky-view inference | `9fd8c696c` Upstream: a surface is ground contact only w | yes |
| 15 | Closure — ADJ transmission in the inventory | `pybuildingenergy/src/pybuildingenergy/source/utils.py:1255` | the Q_tr_adjacent loss/gain line item | `6e549fa18` Defect A: tally ADJ surface transmission and | yes |
| 16 | Closure — transmission at the outer face, net of short-wave | `pybuildingenergy/src/pybuildingenergy/source/utils.py:9725` | the sol-air netting note and the control volume it describes | `6e549fa18` Defect A: tally ADJ surface transmission and | yes |

Every one of the sixteen introducing commits is an ancestor of HEAD, and the implementing code is present in the working tree at the line given. No correction has been dropped by a rebase, reverted by a merge, or overwritten.

## Part B — Behaviour: does each correction still do what the paper says?

| # | Correction | Measured | Verdict |
| ---: | --- | --- | :-: |
| 1 | C1 — dynamic window transmittance | beam factor 1.000 / 0.813 / 0.283 at 0 / 60 / 80 deg; the overall F_W reduces to that angular factor on a pure-beam hour and to the angle-free hemispherical 0.855 on a pure-diffuse hour, both below the upstream constant 0.9 | VERIFIED |
| 2 | C2 — wind-dependent external h_ce | at a uniform 4 m/s the dynamic and fixed-coefficient runs differ by a maximum of 0.000e+00 kWh | VERIFIED |
| 3 | C2b — ASHRAE terrain and height wind profile | identity exact (|f - 1| = 0.0); the case resolves z = 6.75 m and factor 0.6574 | VERIFIED |
| 4 | Ventilation — additive infiltration path | designed 48.449 W/K and leakage 3.119 W/K, both non-zero, summed into a reported mean H_ve of 50.821 W/K | VERIFIED |
| 5 | Infiltration A1 — supply temperature at theta_e | Q_ve = H_ve(theta_int - theta_e) holds to 3.553e-13 W in the worst hour of 8,760 | VERIFIED |
| 6 | Infiltration A3 — envelope scoped to outdoor-exposed | A_env = 13.5 m2, against 88.6 m2 of total surface (75.1 m2 of it party surfaces) | VERIFIED |
| 7 | Infiltration — Australian q50 age bands | the declared 1991-2005 band resolves to 14.0 m3/(h m2)@50Pa; a measured 3.3 scales H_ve_inf by 0.235714286 against the expected 0.235714286 | VERIFIED |
| 8 | Latent — deadband, occupant moisture, dt, sign | at a fixed 40 % RH the humidity ratio moves 0.005783 -> 0.008349 kg/kg between 20 and 26 C, so the band is RH-derived at zone temperature and not a fixed humidity ratio; occupant moisture 29.46 W at full occupancy and 0.00 W at none | VERIFIED |
| 9 | Latent — plant-operation gate | 0.0 kWh charged across the 8687 hours the cooling plant is off, and 0.0 kWh across the 580 hours the heating plant runs | VERIFIED |
| 10 | Internal gains — neighbour-count de-inflation | 84.0 W occupants and 60.0 W appliances over 20 m2; declaring five neighbours leaves the occupant term at 84.0 W, so the neighbour-count multiplier is gone | VERIFIED |
| 11 | Adjacent zones — conditioned-neighbour branch | sensible heating 122.88 kWh with the neighbours at 20 C, 0.00 kWh at 24 C, 4252.13 kWh with them undeclared, which is the b_ztu buffer path | VERIFIED |
| 12 | Ground contact — no implicit slab-on-ground fallback | ground contact area 0.0 m2 — no surface declares a ground boundary and none is inferred | VERIFIED |
| 13 | Ground temperature — hemisphere-resolved coldest month | returns month 7 at latitude -37.8 | VERIFIED |
| 14 | Classification — ground class needs a declared boundary | 0 GR, 5 ADJ, 1 OP, 2 W — the five party surfaces classify as adjacent, none as ground | VERIFIED |
| 15 | Closure — ADJ transmission in the inventory | 7 transmission line items; ADJ transmission is in the inventory at 1,015.3 kWh loss / 1,729.4 kWh gain | VERIFIED |
| 16 | Closure — transmission at the outer face, net of short-wave | the control volume is the outer face and the line item is conduction + radiation to ambient minus absorbed short-wave; the gross absorbed total is still published separately as Q_sol_envelope = 9,975.9 kWh, so nothing is hidden by the netting | VERIFIED |

## Part C — Interaction and interference

### Wind-profile scope

The profile must reach the `h_ce` correlation and nothing else. The infiltration stack/wind term keeps the **meteorological** wind, because its shelter is already carried by the LBL divide-by-N value and its normalisation is anchored to a station-referenced reference speed; reducing u as well would count the same shelter twice.

| Term | Wind it receives | Evidence |
| --- | --- | --- |
| `h_ce = 4 + 4u` | station × 0.6574 = local | utils.py lines [6573, 7531, 8635, 10617], each `u_wind ... * wind_factor_h_ce` |
| infiltration stack/wind | station column, unadjusted | utils.py lines [9150, 11175], each reading `WS10m` with no factor applied |

Measured rather than read: changing the declared terrain class across all four values leaves the infiltration conductance at 3.557284 W/K in every case (**invariant: yes**), while the same change moves the h_ce wind by a factor of 0.6574. Reference conditions unchanged: u_ref = 4.0 m/s, ΔT_ref = 10.0 K, N = 20.

### h_ce dual use

The construction resistance must be derived against the **fixed** coefficient — the rated U was measured under standard films, so `R_c = 1/U − R_si − R_se` has to keep using the standard value — while the hourly boundary condition uses the wind-dependent one.

- `Conductance_node_of_element` reads `convective_heat_transfer_coefficient_external`, which on every outdoor-exposed surface is **[20.0]** W/(m²·K) — the ISO Table 25 constant 20.0.
- The hourly correlation returns **20.0** W/(m²·K) at 4 m/s, i.e. the same constant, which is why correction 2's test is a bit-identity check rather than a tolerance.
- Neither the wind profile nor any later change touches the static value: the profile is applied to `u_wind` at the four `h_ce` call sites listed above and nowhere else.

### Ground path

`Temp_calculation_of_ground` takes `R_se = 0.04` as a fixed default and the equivalent thickness is `d_t = wall_thickness + λ_gr (R_floor + R_se)` — no wind term, and no reference to `wind_factor_h_ce` or the dynamic coefficient anywhere in the ISO 13370 path. For this case the question is moot in effect as well as in form: ground contact area is 0.0 m², so every ground term is zero.

### Latent and ventilation

The latent balance must see the corrected **total** air flow, not the designed ventilation alone. In the solver `H_ve_nat` is reassigned to `H_ve_nat + H_ve_inf` before it is recorded, and the recorded series is what the reported latent load is computed from.

- Designed only, at 20/10 °C and 4 m/s: 48.449 W/K.
- Reported hourly mean `H_ve`: 50.821 W/K — **above** the designed value, so the leakage stream is in the series the latent balance reads.

### Double application

- **Closure commits.** Each of the four appears exactly once in HEAD's history. They are back-ported onto earlier states only inside the trajectory harness's throwaway worktrees, never into the engine tree; the trajectory's final state is verified byte-identical to HEAD's `pybuildingenergy/src`, which is the check that no instrument commit leaked in as an ordinary engine commit.
- **Wind profile.** The factor is resolved at 4 sites (one per engine path) and applied at 4 sites, one per path per solver. `_dynamic_external_convection_h` takes `u_wind_ms` as given and does not re-resolve or re-apply it, so the profile is applied once, at the resolver, and not again at the surface.

## Part D — The building dictionary

| Field | Declared value |
| --- | --- |
| net_floor_area (m2) | 20.0 |
| ceiling height (m) | 2.7 |
| zone volume (m3) | 54.0 |
| U ext wall / partition / slab (W/m2K) | 1.0 / 2.5 / 1.8 |
| U window (W/m2K) / g (-) | 5.4 / 0.65 |
| window area (m2), orientation | 1.62, azimuth 270 (west), tilt 90 |
| solar absorptance, exterior / interior | 0.75 / 0.0 |
| surface thermal capacity (J/m2K) | 0 (all elements) |
| setpoints heat / setback (C) | 18.0 / 15.0 |
| setpoints cool / setback (C) | 26.0 / 28.0 |
| ventilation | occupancy, 2.0 l/(s m²) |
| construction_year band | 1991-2005 |
| terrain_class | suburban |
| weather_station_terrain | open_country |
| weather station sensor height (m) | 10.0 |
| floor_level used for the height | 3 |
| resolved surface height z (m) | 6.75 |
| latitude / longitude | -37.8 / 144.968 |
| building_type_class | Residential_apartment |
| number_adj_zone | 5 |
| exposed_perimeter (declared) | 0 |
| construction.thermal_bridges (declared) | 1.5 |
| climate_parameters.coldest_month | 7 |

### Adjacent zones

| Zone | conditioned | setpoint (°C) | volume (m³) | a_use (m²) |
| --- | :-: | ---: | ---: | ---: |
| apt_above | True | 20.0 | 54.0 | 20.0 |
| apt_below | True | 20.0 | 54.0 | 20.0 |
| apt_north | True | 20.0 | 54.0 | 20.0 |
| apt_south | True | 20.0 | 54.0 | 20.0 |
| corridor | True | 20.0 | 162.0 | 60.0 |

**All 5 of 5 adjacent zones are declared `conditioned` with a single setpoint of 20.0 °C.**

### What the validator rewrites

Every scalar field was compared before and after `sanitize_and_validate_BUI`. **3 field(s) are rewritten:**

| Field | Declared | After sanitisation |
| --- | ---: | ---: |
| `/building/exposed_perimeter` | 0 | 1.0 |
| `/building_surface[6]/parapet` | 1.0 | 0.9 |
| `/building_surface[7]/parapet` | 1.0 | 0.9 |

`exposed_perimeter` is the consequential one: **declared 0, rewritten to 1.0 m**. A thermal-bridge term follows directly from it — `H_tb = P · ψ_k` with the default ψ_k = 0.05 W/(m·K), giving **H_tb = 0.05 W/K**. The declared `construction.thermal_bridges = 1.5` has **0 consumers in the engine** — it is read by nothing. The bridge the balance reports is therefore an artefact of the sanitiser's fabricated perimeter, not of the declared value.

The two `parapet` rewrites are a clamp on a window parapet fraction and carry no energy consequence for this case; they are listed for completeness rather than flagged.

## Part E — The headline, three ways

| Quantity | 1. HEAD run | 2. Trajectory final state | 3. Figure gate | Max spread |
| --- | ---: | ---: | ---: | ---: |
| Sensible heating (kWh) | 122.88 | 122.88 | 122.88 | 0.00e+00 |
| Sensible cooling (kWh) | 19.9 | 19.9 | 19.9 | 0.00e+00 |
| Gated latent cooling (kWh) | 1.51 | 1.51 | 1.51 | 0.00e+00 |
| Total (kWh) | 144.28 | 144.28 | 144.28 | 0.00e+00 |
| Per area (kWh/m²·yr) | 7.21 | 7.21 | 7.21 | 0.00e+00 |

**Largest disagreement across the three routes: 0.00e+00.** All three agree to the printed precision, so the headline is reproducible independently of the harness that produced it.

## Part F — Known open items, confirmed still open

| Item | Status | Magnitude / detail |
| --- | --- | --- |
| Thermal bridges | **OPEN** | `construction.thermal_bridges = 1.5` has no consumer in the engine. The reported bridge follows from the sanitiser's fabricated perimeter: P = 1.0 m (declared 0) × ψ_k = 0.05 → **H_tb = 0.05 W/K**, which books **1.95 kWh** of bridge loss over the year |
| Coldest month | **DIVERGES** (CONFORMANCE A11) | latitude heuristic, not arg min over the record: latitude -37.8 < 0 → month 7. For this file arg min over the monthly means is **also July (9.85 °C)**, so the heuristic and the measurement agree here — the divergence is in the method, not in this result |
| Wind profile scope | **BY DECISION, not oversight** | applies to `h_ce` only; infiltration keeps meteorological wind. Verified in Part C: the infiltration conductance is invariant across all four terrain classes |
| EnergyPlus reference | **PARTIALLY AUDITED** | three defects were found and fixed in the shared IDF builder (outdoor-air field offset, ventilation on the ideal-loads object, humidification booked as heating) and a fourth — the wind treatment — in the wind-profile work. The reference has had **no systematic audit equivalent to this one**; the four were found by building a matched case, not by looking for them |
| Ground coupling | **DIVERGES** (CONFORMANCE A10) | U-value branch and R_si/R_f detail. Latent for this case: ground contact area is 0.0 m², so every ground term is zero and the divergence cannot reach the result — but it is still an equation-level mismatch the paper must not assert |

`CONFORMANCE.md` records A10 and A11 as DIVERGES and A14 (thermal bridges) as OPEN. This audit re-measured all three and they are unchanged. A1, A3 and A4 are marked DIVERGES → RESOLVED there and are verified present here as corrections 5, 6 and 7.

## Regression suite

`python -m pytest tests/ -q` — **228 passed, 0 skipped, 0 failed (161 s)**.

A green suite is not a substitute for Parts A to E. The suite tests what it was written to test; this audit exists to check what the paper claims, and the two overlap only partly.

## Conclusion

**HEAD contains all 16 corrections, each verified by the stated test; the headline reproduces three ways to within 0.00e+00; the open items are as listed in Part F.**

Generated by `tools/diagnostics/engine_audit.py`.
