# The local-wind profile: terrain and height

Weather: `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. Station wind column: mean **4.84 m/s**, 59.8 % of hours above the 4 m/s pivot at which `4u + 4 = 20 W/(m²·K)`, the ISO 13789 constant the correction replaces.

Covers Items 0, 1, 3 and 5. Item 2 — whether C2 changes sign — is the controlled experiment in `wind_verdict_*.md`, which this file does not restate.

## Item 0 — what EnergyPlus did

### The finding

****Yes — this is a fourth input mismatch, and it is the largest of the four in the wind term.** `Site:HeightVariation` is absent from both generated IDFs, so EnergyPlus fell back to the `Building` object's `Terrain` field, which the builder writes as `Suburbs` — a = 0.22, δ = 370 m. EnergyPlus therefore applied a terrain **and** height correction to every wind-exposed surface, evaluating the west wall at its centroid height of 1.35 m and driving its external film with a mean of 2.23 m/s. The ISO side used the raw 10 m station column, mean 4.84 m/s. The two engines were driven by winds differing by a factor of 2.17.**

### The static read of the IDF

| | |
| --- | --- |
| `Site:HeightVariation` | **absent** |
| `Site:WeatherStation` | **absent** — EnergyPlus defaults apply: 10 m sensor, a = 0.14, δ = 270 m |
| `Building` Terrain field | `Suburbs` |
| What that resolves to | a = 0.22, δ = 370 m (ASHRAE class `suburban`) |
| Basis | Site:HeightVariation ABSENT; EnergyPlus falls back to the Building object's Terrain = 'Suburbs' |

Wind-exposed surfaces and the profile EnergyPlus evaluates at each:

| Surface | Centroid height z (m) | u_local / u_met |
| --- | ---: | ---: |
| `WestWall` | 1.35 | 0.4614 |
| `WestWin_Fixed` | 1.45 | 0.4687 |
| `WestWin_Operable` | 1.45 | 0.4687 |

### What EnergyPlus actually used

Not inferred from the algorithm — measured, by re-running the committed IDF with `Surface Outside Face Outdoor Air Wind Speed` reported hourly. Only an `Output:Variable` was added.

| Reported key | Annual mean (m/s) | Hours | Implied factor |
| --- | ---: | ---: | ---: |
| `Environment` | 4.840 | 8,760 | 1.0000 |
| `WESTWALL` | 2.233 | 8,760 | 0.4614 |
| `WESTWIN_FIXED` | 2.269 | 8,760 | 0.4687 |
| `WESTWIN_OPERABLE` | 2.269 | 8,760 | 0.4687 |

### The mismatch

| Engine | Wind fed to the external film | Annual mean |
| --- | --- | ---: |
| EnergyPlus (as run) | station column × the `Suburbs` profile at each surface's own height | **2.23 m/s** |
| ISO 52016-1 (as run, before this change) | station column, unadjusted | **4.84 m/s** |
| ISO 52016-1 (after this change) | station column × the declared terrain and height | **3.18 m/s** |

Two separate errors are stacked here, and they must not be conflated.

**The terrain error is the one the task is about**, and it was on the ISO side: EnergyPlus applied a profile, the ISO engine did not.

**The height error is on the EnergyPlus side, and it is new.** The IDF places the zone origin at z = 0 and the west wall spans 0 → 2.70 m, so EnergyPlus evaluated a *third-floor* apartment's wall at a centroid height of 1.35 m. That is not a wind-profile question — the geometry says the apartment is at ground level. It affects the wind term (through the profile) and nothing else, because every other surface in the model is either adiabatic, on an OtherSideCoefficients boundary, or the window in that same wall.

After this change the ISO side runs at 3.18 m/s (suburban, z = 6.75 m) and EnergyPlus at 2.23 m/s (suburbs, z = 1.35 m). The remaining gap is entirely the height, and matching it requires moving the EnergyPlus zone up three storeys, not changing the profile. That is done in the matched validation case; see `results/paper/validation_corrected/`.

## Item 1 — the implementation

$$u_{local} = u_{met}\left(\frac{\delta_{met}}{z_{met}}\right)^{a_{met}}\left(\frac{z}{\delta}\right)^{a}$$

Coefficients: **ASHRAE Handbook — Fundamentals (2021), Chapter 24 "Airflow Around Buildings", Table 1 (Atmospheric Boundary Layer Parameters)**. All four classes are implemented with the published values; none differs from the task's table.

| Class | a | δ (m) | Description | EnergyPlus `Terrain` equivalent |
| --- | ---: | ---: | --- | --- |
| `flat_open` | 0.10 | 210 | unobstructed, open water | `Ocean` |
| `open_country` | 0.14 | 270 | flat open country, **airports** | `Country` |
| `suburban` | 0.22 | 370 | urban, suburban, wooded | `Suburbs` / `Urban` |
| `city_centre` | 0.33 | 460 | large city centres | `City` |

That the two columns agree is the point: the ISO engine and the EnergyPlus reference can now be driven by the same wind, which Item 0 shows they were not.

### Acceptance

**The identity case is exact.** `open_country` at z = 10 m — the station's own terrain at the station's own sensor height — returns a factor of 1, i.e. |f − 1| = 0.000e+00.

**Apt 305.** Declared `suburban`, level 3, storey height 2.70 m, so z = (3 − 0.5) × 2.70 = **6.75 m**. The resolved factor is **0.6574** and the local annual mean is **3.18 m/s**, against the station's 4.84 m/s.

The task's acceptance target was ~0.70 and ~3.39 m/s. **The computed factor is 0.657, not 0.70, and the mean is 3.18 m/s, not 3.39** — -6.1 % on the factor. This is reported rather than tuned away. The two differ only in the height: 0.70 corresponds to z ≈ 9.0 m, which is the *top* of level 3 at a 3.0 m floor-to-floor, not the mid-height of level 3 at the 2.70 m ceiling height the building dictionary declares. The height rule the task specifies — z = (n − 0.5) × h_storey, using the declared height per storey — is the one implemented, and it gives 6.75 m. Nothing in the sign question turns on the difference: both heights put the local mean well below the 4 m/s pivot.

The height floor is **1.0 m**, and it is a numerical guard rather than a claim about where the profile stops being valid: the power law sends u → 0 as z → 0, which would drive h_ce onto its own h_min floor. 1.0 m sits below the mid-height of any habitable storey (a 2.4 m ceiling gives 1.2 m), so **it does not bind on any case in this document**.

### What the corrected wind feeds

`h_ce = 4 + 4u` **only**. The infiltration stack/wind modulation of Equation (6) keeps the station value, for two reasons that are about what its numbers were fitted to:

1. **Shelter is already in that model once.** The 50 Pa rate is brought down to a mean natural rate by the LBL divide-by-N relation with N = 20, the standard value for a *sheltered* low-rise building. N is where site obstruction enters. Reducing u as well would count the same shelter twice.
2. **Its normalisation is anchored to a met-station speed.** f ≡ 1 at (ΔT = 10 K, u = 4 m/s), and that 4 m/s is the same station reference ISO 13789 §9.5 freezes. Feeding a local wind into the numerator while the denominator stays on the station reference would move f off 1 at the reference conditions and silently rescale the annual mean infiltration rate.

Ground-coupled and adiabatic surfaces are unaffected, as before — they are never wind-exposed and never reach the h_ce path.

## Item 3 — sensitivity across terrain class

Terrain class is a judgement the modeller assigns by inspection, not a measurement. At Apt 305's z = 6.75 m:

| Class | a | δ (m) | Factor | Local mean (m/s) | Hours above pivot | Mean h_ce W/(m²·K) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `flat_open` | 0.1 | 210 | 1.1249 | 5.44 | 68.4 % | 25.78 |
| `open_country` | 0.14 | 270 | 0.9465 | 4.58 | 54.2 % | 22.32 |
| `suburban` ← | 0.22 | 370 | 0.6574 | 3.18 | 29.4 % | 16.73 |
| `city_centre` | 0.33 | 460 | 0.3939 | 1.91 | 2.8 % | 11.63 |
| *station, unadjusted* | — | — | 1.0000 | 4.84 | 59.8 % | 23.36 |

**Every one of the four classes puts the mean h_ce below the ISO constant of 20 W/(m²·K), and the unadjusted station wind puts it above.** The classification moves the local mean by a factor of 2.86 across the four classes — a wide band — but the *side of the pivot* is the same for all four. The sign of C2 is therefore robust to the terrain judgement even though its magnitude is not.

## Item 5 — Australian applicability

| Case | Terrain | z (m) | Basis | Factor | Local mean (m/s) | Direction |
| --- | --- | ---: | --- | ---: | ---: | --- |
| Suburban single-storey dwelling | `suburban` | 1.35 | (level 1 - 0.5) x 2.7 m | **0.4614** | 2.23 | reduction |
| Inner-urban apartment, Level 3 (Apt 305) | `suburban` | 6.75 | (level 3 - 0.5) x 2.7 m | **0.6574** | 3.18 | reduction |
| City-centre apartment, Level 20 | `city_centre` | 58.50 | (level 20 - 0.5) x 3.0 m | **0.8032** | 3.89 | reduction |
| Rural dwelling, open ground | `open_country` | 1.35 | (level 1 - 0.5) x 2.7 m | **0.7555** | 3.66 | reduction |
| Identity case: station terrain at station height | `open_country` | 10.00 | explicit 10.0 m | **1.0000** | 4.84 | reduction |

### The Level 20 case does not come out as the task expected

The task asked to *confirm* that a city-centre apartment at z ≈ 58 m returns a factor **above** 1.0. **It does not: the factor is 0.8032.** Reported as it fell rather than tuned to the expectation.

The expectation is right about the mechanism and wrong about where it bites. A building does eventually project into faster-moving air than the 10 m station sees, and the implementation does return factors above 1.0 — but for `city_centre` (a = 0.33, δ = 460 m) the crossing is much higher than 58 m, because the same roughness that slows the wind near the ground also thickens the boundary layer that has to be climbed. Solving f = 1 for each class:

| Class | z at which u_local = u_met | Roughly |
| --- | ---: | --- |
| `flat_open` | 2.1 m | just above head height |
| `open_country` | 10.0 m | the station's own sensor height, by construction |
| `suburban` | 45.4 m | about level 15 at 3 m storeys |
| `city_centre` | 113.6 m | about level 38 at 3 m storeys |

So the check the task wanted — that nothing in the implementation assumes a reduction — passes, but on a different row: `suburban` at 58 m gives 1.0552, and `city_centre` crosses 1.0 at 114 m, roughly level 38. A level-20 city-centre apartment genuinely does sit in slower air than an open-country aerodrome mast.

The rural dwelling on open ground returns 0.7555 at 1.35 m — near unity, as it must be, since its terrain is the station's own and only the height differs.

Generated by `tools/diagnostics/wind_profile_terrain.py`.
