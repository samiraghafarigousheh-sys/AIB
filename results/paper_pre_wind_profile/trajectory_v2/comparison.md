# The canonical trajectory, in methodology order — clean weather file

**V2 residual gate (< 5 % on every state): PASSED.** **HEAD invariance: CONFIRMED.**

Literature corrections first (C1, C2), then the implementation defects found in the engine, then the closure fixes. Each state is the previous state plus exactly one correction, cherry-picked onto the unmodified baseline (`2e6e910`). Canonical building: apt 305, 50 Barry St Carlton, party surfaces typed `adjacent`.

**Weather: `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`** — Melbourne-Essendon.Fields, WMO 958660, lat -37.7275, lon 144.9067, tz +10; 8,760 rows, 0 missing wind values, annual mean wind 4.84 m/s, 1.58 % of hours exactly 0.0 m/s, 59.8 % above the 4 m/s pivot, no dead-calm month.

**No engine logic changed in this run. Only the weather input changed.** The previous canonical run used `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`, which is superseded because four calendar months of its wind column — Jan, Mar, Jul, Sep, 2,952 h, 33.7 % of the year — read identically 0.0 m/s, an artefact of the Melbourne Regional Office station's record ending in 2014. Because `h_ce = 4v + 4` collapses to 4 W/(m²·K) at v = 0, those fabricated calms drove a spurious tripling of sensible cooling through C2. Every state below is the same commit as before, measured on a wind record that is actually a wind record.

Ventilation and latent are reported **split**, not combined: they are already two separate commits (`9a89334`, `0bab14f`), so splitting them was free and changed neither one's physics. C1 **is included** as a cumulative step — the plan's stated default for "literature corrections first" — rather than being confined to its own window comparison.

## 1. The trajectory

| State | Sensible heating (kWh) | Sensible cooling (kWh) | Latent cooling, gated (kWh) | Latent cooling, ungated (kWh) | Latent heating (kWh) | Total, sensible + gated latent (kWh) | Total (kWh) | Total (kWh/m²) | V2 residual (kWh) | V2 residual (%) | < 5 %? | Transmission items |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :-: | ---: |
| Baseline | 1,779.36 | 640.84 | 26.12 | 900.05 | 152.6506 | 2,446.32 | 2,598.97 | 129.95 | -96.72 | -1.16 % | PASS | 7 |
| +C1 dynamic window | 1,783.96 | 606.07 | 25.34 | 905.27 | 152.7140 | 2,415.36 | 2,568.08 | 128.40 | -95.97 | -1.17 % | PASS | 7 |
| +C2 wind-dependent h_ce | 1,788.11 | 580.77 | 25.02 | 906.29 | 152.9055 | 2,393.90 | 2,546.80 | 127.34 | -95.69 | -1.17 % | PASS | 7 |
| +Ventilation | 2,197.42 | 445.68 | 25.10 | 1,148.49 | 184.9387 | 2,668.20 | 2,853.14 | 142.66 | -86.45 | -1.01 % | PASS | 7 |
| +Latent | 2,197.42 | 445.68 | 14.53 | 634.24 | 0.0047 | 2,657.63 | 2,657.64 | 132.88 | -86.45 | -1.01 % | PASS | 7 |
| +Internal gains | 4,228.46 | 180.79 | 7.07 | 934.29 | 0.0157 | 4,416.31 | 4,416.33 | 220.82 | -63.38 | -1.04 % | PASS | 7 |
| +Conditioned zones | 210.28 | 4.12 | 0.53 | 718.56 | 0.0000 | 214.93 | 214.93 | 10.75 | -72.88 | -1.77 % | PASS | 7 |
| +Ground contact | 210.28 | 4.12 | 0.53 | 718.56 | 0.0000 | 214.93 | 214.93 | 10.75 | +0.00 | +0.00 % | PASS | 7 |
| +Hemisphere | 210.28 | 4.12 | 0.53 | 718.56 | 0.0000 | 214.93 | 214.93 | 10.75 | +0.00 | +0.00 % | PASS | 7 |
| +Infiltration supply temp | 153.95 | 15.15 | 1.22 | 634.98 | 0.0000 | 170.32 | 170.32 | 8.52 | +0.00 | +0.00 % | PASS | 7 |
| +Infiltration envelope area | 114.87 | 12.89 | 1.05 | 589.33 | 0.0000 | 128.80 | 128.80 | 6.44 | +0.00 | +0.00 % | PASS | 7 |
| +AU q50 recalibration | 123.74 | 13.41 | 1.14 | 600.11 | 0.0000 | 138.29 | 138.29 | 6.91 | +0.00 | +0.00 % | PASS | 7 |
| +Closure fixes | 123.74 | 13.41 | 1.14 | 600.11 | 0.0000 | 138.29 | 138.29 | 6.91 | +0.00 | +0.00 % | PASS | 7 |

`Latent cooling, ungated` is the diagnostic contrast column only — the zone moisture balance before the plant-on gate. It is never part of a total.

### The C2 step, which is what the weather change acts on

`+C2 wind-dependent h_ce` moves sensible cooling by **-25.30 kWh** (606.07 → 580.77) and sensible heating by +4.15 kWh. On the superseded RO file the same step moved cooling **+119.58 kWh**, and the wind diagnostic traced 96 % of that to hours reading exactly 0.0 m/s.

The sign has flipped because the physics has, and for a defensible reason. With 59.8 % of hours above the 4 m/s pivot, `h_ce = 4v + 4` now sits *above* the ISO fixed 20 W/(m²·K) for most of the year rather than collapsing to 4. A stronger external film on a west wall of absorptance 0.75 sheds more of the absorbed solar back to the air, the sol-air driving temperature falls, and less heat is conducted inward — so the correction now *reduces* cooling instead of manufacturing it. `results/diagnostics/wind_verdict_essendon.md` isolates this with a one-switch controlled experiment and returns verdict (a+b).

## 2. What each state adds

| State | Commit(s) | What it is |
| --- | --- | --- |
| Baseline | — | unmodified ISO 52016-1, as vendored |
| +C1 dynamic window | `a66eec7` | literature — angular/hourly window g-value and U_win(t) |
| +C2 wind-dependent h_ce | `56f5d08` | literature — external convective coefficient h_ce = 4v + 4 |
| +Ventilation | `9a89334` | found defect — additive H_ve_inf term |
| +Latent | `0bab14f` | found defect — EN 16798-1 deadband, occupancy moisture, dt_h |
| +Internal gains | `5aca6ce` | found defect — de-inflation; drop the neighbour-count multiplier |
| +Conditioned zones | `7339076` | found defect — Issue 7 adjacent-zone boundary treatment |
| +Ground contact | `418496b` | found defect — no implicit slab-on-ground fallback |
| +Hemisphere | `ef312fe` | found defect — latitude-resolved coldest month |
| +Infiltration supply temp | `c641378` | found defect (A1) — infiltration air supplied at theta_e, not 0 C |
| +Infiltration envelope area | `bb678a9` | found defect (A3) — leakage envelope = outdoor-exposed surfaces only |
| +AU q50 recalibration | `421c282` | recalibration — Australian CSIRO permeability bands; case adopts pre-2006 |
| +Closure fixes | `6e549fa18`, `82a909d3f`, `9fd8c696c`, `09357302f` | ADJ transmission into the inventory, latent gating, GR classification |

## 3. Order-independence and HEAD invariance

Applying the same set of corrections in a different order must land on the same engine, so the check is made on the **source**, not only on the numbers — a difference that happened not to move this particular building's annual result would still be caught.

The reordered trajectory's final state is **byte-for-byte identical** to HEAD's engine tree across every `.py` file under `pybuildingenergy/src/`. The reordering therefore cannot have moved the canonical figure, and did not.

The numeric half of the check is against **HEAD run on this same weather file**, not against a stored constant. That distinction matters here: a stored constant would assert "this reproduces the number we published on the RO file", which is false by design this time and says nothing about separability. Comparing to a live HEAD run asserts what the harness is actually for — that however the corrections are ordered, the engine lands in the same place — and it is the same claim on any weather file.

| Metric | HEAD, run directly | Trajectory's final state | Δ | within ±0.01? |
| --- | ---: | ---: | ---: | :-: |
| `Q_H_sensible_kWh` | 123.74 | 123.74 | 0.00e+00 | yes |
| `Q_C_sensible_kWh` | 13.41 | 13.41 | 0.00e+00 | yes |
| `Q_C_latent_kWh` | 1.14 | 1.14 | 0.00e+00 | yes |
| `Q_need_total_kWh_per_sqm` | 6.91 | 6.91 | 0.00e+00 | yes |

**The new canonical headline: 123.74 kWh sensible heating + 13.41 kWh sensible cooling + 1.14 kWh gated latent = 138.29 kWh = 6.91 kWh/m²·yr.** Latent heating is 0.0000 kWh at this state, so "sensible + gated latent" and the engine's own total agree to the printed digit.

### What changed against the superseded run

Same engine, same building, same commit — only the weather file differs. Prior column is `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`, read from `results/au_canonical/comparison.csv`.

| Metric | Prior (RO, corrupt wind) | This run (Essendon) | Δ | Δ % |
| --- | ---: | ---: | ---: | ---: |
| Sensible heating (kWh) | 122.69 | 123.74 | +1.05 | +0.9 % |
| Sensible cooling (kWh) | 67.12 | 13.41 | -53.71 | -80.0 % |
| Gated latent cooling (kWh) | 3.98 | 1.14 | -2.84 | -71.3 % |
| Total (kWh) | 193.79 | 138.29 | -55.50 | -28.6 % |
| Total (kWh/m²·yr) | 9.69 | 6.91 | -2.77 | -28.6 % |

Sensible cooling moves -53.71 kWh, which is the expected direction and the expected channel: Essendon is genuinely windier (4.84 m/s mean, 59.8 % of hours above the 4 m/s pivot) than the RO file's zero-filled column implied, so `h_ce = 4v + 4` now sits *above* the ISO constant for most of the year instead of collapsing to a fifth of it. See `results/diagnostics/wind_verdict_essendon.md` for the controlled experiment that isolates C2 on this file.

## 4. The residual gate

The V2 Sankey closure residual is under the 5 % gate on **every** state of the trajectory; the largest excursion is -1.77 % at *+Conditioned zones*, and from the ground-contact fix onward it is machine-zero. Every state lists 7 transmission line items, so no state is measured with part of the envelope missing from its inventory. The instrument is identical across states by construction — the closure commits are cherry-picked onto each one — which is what makes the states comparable at all, and is also why the final `+Closure fixes` step moves no number: its content is already in the instrument. That the closure fixes change the measurement and not the physics is the finding, not an artefact.

## 5. The ADJ transmission inventory

The five party surfaces are 75.10 m², 88.6 % of the envelope UA, and were absent from both sides of the balance before the closure fixes. They must appear as line items — 7 in total, the five party surfaces plus the exposed west wall and its window — and the tallied sum must agree with an **independent re-integration** of the per-surface hourly flows to within 0.1 %. The two come from different code paths: the reported figure from the in-loop accumulator, the independent one from the hourly frame afterwards.

| State | Line items | ADJ loss (kWh) | ADJ gain (kWh) | Reported Σ (kWh) | Independent Σ (kWh) | Δ | within 0.1 %? |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :-: |
| Baseline | 7 | 4,864.29 | 2.40 | 5,628.46 | 5,628.46 | 0.0000 % | yes |
| +C1 dynamic window | 7 | 4,802.11 | 2.50 | 5,568.46 | 5,568.46 | 0.0000 % | yes |
| +C2 wind-dependent h_ce | 7 | 4,779.31 | 2.56 | 5,552.39 | 5,552.39 | 0.0000 % | yes |
| +Ventilation | 7 | 4,475.06 | 2.55 | 5,206.65 | 5,206.65 | 0.0000 % | yes |
| +Latent | 7 | 4,475.06 | 2.55 | 5,206.65 | 5,206.65 | 0.0000 % | yes |
| +Internal gains | 7 | 3,001.56 | 11.39 | 3,546.51 | 3,546.51 | 0.0000 % | yes |
| +Conditioned zones | 7 | 756.95 | 2,098.26 | 1,524.47 | 1,524.47 | 0.0000 % | yes |
| +Ground contact | 7 | 756.95 | 2,098.26 | 1,524.47 | 1,524.47 | 0.0000 % | yes |
| +Hemisphere | 7 | 756.95 | 2,098.26 | 1,524.47 | 1,524.47 | 0.0000 % | yes |
| +Infiltration supply temp | 7 | 951.57 | 1,831.79 | 1,753.61 | 1,753.61 | 0.0000 % | yes |
| +Infiltration envelope area | 7 | 955.25 | 1,717.72 | 1,771.53 | 1,771.53 | 0.0000 % | yes |
| +AU q50 recalibration | 7 | 954.29 | 1,746.31 | 1,766.98 | 1,766.98 | 0.0000 % | yes |
| +Closure fixes | 7 | 954.29 | 1,746.31 | 1,766.98 | 1,766.98 | 0.0000 % | yes |

## 6. The latent gate

Latent cooling may be charged only in hours the cooling plant actually runs. Two leaks are checked directly rather than argued from the annual total: latent charged while the plant is off, and latent charged while the *heating* plant runs. Both must be zero.

| State | Steps | Cooling on | Heating on | Latent charged | Gated (kWh) | Ungated (kWh) | Charged, plant off | Charged while heating | Latent heating (kWh) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 8,760 | 851 | 2,790 | 178 | 26.12 | 900.05 | 0.000000 | 0.000000 | 152.6506 |
| +C1 dynamic window | 8,760 | 834 | 2,808 | 173 | 25.34 | 905.27 | 0.000000 | 0.000000 | 152.7140 |
| +C2 wind-dependent h_ce | 8,760 | 813 | 2,817 | 171 | 25.02 | 906.29 | 0.000000 | 0.000000 | 152.9055 |
| +Ventilation | 8,760 | 670 | 3,166 | 149 | 25.10 | 1,148.49 | 0.000000 | 0.000000 | 184.9387 |
| +Latent | 8,760 | 670 | 3,166 | 631 | 14.53 | 634.24 | 0.000000 | 0.000000 | 0.0047 |
| +Internal gains | 8,760 | 335 | 4,636 | 305 | 7.07 | 934.29 | 0.000000 | 0.000000 | 0.0157 |
| +Conditioned zones | 8,760 | 24 | 817 | 21 | 0.53 | 718.56 | 0.000000 | 0.000000 | 0.0000 |
| +Ground contact | 8,760 | 24 | 817 | 21 | 0.53 | 718.56 | 0.000000 | 0.000000 | 0.0000 |
| +Hemisphere | 8,760 | 24 | 817 | 21 | 0.53 | 718.56 | 0.000000 | 0.000000 | 0.0000 |
| +Infiltration supply temp | 8,760 | 58 | 654 | 51 | 1.22 | 634.98 | 0.000000 | 0.000000 | 0.0000 |
| +Infiltration envelope area | 8,760 | 51 | 559 | 45 | 1.05 | 589.33 | 0.000000 | 0.000000 | 0.0000 |
| +AU q50 recalibration | 8,760 | 54 | 575 | 47 | 1.14 | 600.11 | 0.000000 | 0.000000 | 0.0000 |
| +Closure fixes | 8,760 | 54 | 575 | 47 | 1.14 | 600.11 | 0.000000 | 0.000000 | 0.0000 |

Southern-hemisphere phase, gated latent cooling by month at the canonical state (kWh):

| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.79 | 0.09 | 0.03 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.04 | 0.18 |

Dec–Feb 1.07 kWh against Jun–Aug 0.00 kWh: the load sits in the austral summer, which is the phase check.

## 7. Provenance

* baseline: `2e6e910`
* closure commits: `6e549fa18`, `82a909d3f`, `9fd8c696c`, `09357302f`
* weather: `/home/user/AIB/weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`
* weather screened by `tools/diagnostics/weather_integrity.py`: 8,760 rows, 0 missing wind values, mean 4.84 m/s, 1.58 % exactly zero, 59.8 % above 4 m/s, dead-calm months: none
* superseded weather (kept in `weather_cache/` for the contrast): `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`
* Baseline: `2e6e910c1`
* +C1 dynamic window: `9d9fe477e`
* +C2 wind-dependent h_ce: `df346332b`
* +Ventilation: `ca5f00dff`
* +Latent: `7d5af6f72`
* +Internal gains: `ba375b5a4` — conflicts outside the engine resolved in favour of the state in `.gitignore`
* +Conditioned zones: `6ab94ce29`
* +Ground contact: `18eb20fbc`
* +Hemisphere: `f891f423e`
* +Infiltration supply temp: `70051c4b3`
* +Infiltration envelope area: `982236e32`
* +AU q50 recalibration: `e6267b998` — conflicts outside the engine resolved in favour of the state in `examples/apt305_building.py`
* +Closure fixes: `a6bd80baf` — conflicts outside the engine resolved in favour of the state in `.gitignore, colab_closed_balance.ipynb`

## 8. The gate

| Condition | Result |
| --- | :-: |
| V2 residual < 5 % on every state | PASS |
| ADJ transmission in the inventory (7 line items, every state) | PASS |
| Independent re-integration within 0.1 %, every state | PASS |
| Latent gated (no charge with plant off or while heating) | PASS |
| HEAD invariant under the reordering | PASS |
| Final engine tree identical to HEAD | PASS |

**Gate passed and HEAD invariant.** Reduction percentages and kWh/m² headlines may be computed from this table, and the methodology text can be written against it.
