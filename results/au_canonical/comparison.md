# The canonical trajectory, in methodology order

**V2 residual gate (< 5 % on every state): PASSED.** **HEAD invariance: CONFIRMED.**

Literature corrections first (C1, C2), then the implementation defects found in the engine, then the closure fixes. Each state is the previous state plus exactly one correction, cherry-picked onto the unmodified baseline (`2e6e910`). Canonical building: apt 305, party surfaces typed `adjacent`. Weather `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`.

Ventilation and latent are reported **split**, not combined: they are already two separate commits (`9a89334`, `0bab14f`), so splitting them was free and changed neither one's physics. C1 **is included** as a cumulative step — the plan's stated default for "literature corrections first" — rather than being confined to its own window comparison.

## 1. The trajectory

| State | Sensible heating (kWh) | Sensible cooling (kWh) | Latent cooling, gated (kWh) | Latent cooling, ungated (kWh) | Latent heating (kWh) | Total (kWh) | Total (kWh/m²) | V2 residual (kWh) | V2 residual (%) | < 5 %? | Transmission items |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :-: | ---: |
| Baseline | 1,308.60 | 741.83 | 55.76 | 617.38 | 157.9951 | 2,264.18 | 113.21 | -87.42 | -1.11 % | PASS | 7 |
| +C1 dynamic window | 1,300.63 | 749.71 | 56.32 | 618.64 | 157.6558 | 2,264.32 | 113.22 | -87.09 | -1.11 % | PASS | 7 |
| +C2 wind-dependent h_ce | 1,303.28 | 869.29 | 59.62 | 619.24 | 157.9651 | 2,390.15 | 119.51 | -87.54 | -1.09 % | PASS | 7 |
| +Ventilation | 1,517.89 | 770.46 | 60.46 | 736.06 | 179.9926 | 2,528.81 | 126.44 | +0.00 | +0.00 % | PASS | 7 |
| +Latent | 1,517.89 | 770.46 | 31.01 | 405.96 | 0.0112 | 2,319.38 | 115.97 | +0.00 | +0.00 % | PASS | 7 |
| +Internal gains | 3,226.38 | 413.48 | 17.73 | 672.89 | 0.0442 | 3,657.63 | 182.88 | -55.56 | -1.02 % | PASS | 7 |
| +Conditioned zones | 122.69 | 67.12 | 3.98 | 554.62 | 0.0000 | 193.79 | 9.69 | -67.58 | -1.69 % | PASS | 7 |
| +Ground contact | 122.69 | 67.12 | 3.98 | 554.62 | 0.0000 | 193.79 | 9.69 | -0.00 | -0.00 % | PASS | 7 |
| +Hemisphere | 122.69 | 67.12 | 3.98 | 554.62 | 0.0000 | 193.79 | 9.69 | -0.00 | -0.00 % | PASS | 7 |
| +Closure fixes | 122.69 | 67.12 | 3.98 | 554.62 | 0.0000 | 193.79 | 9.69 | -0.00 | -0.00 % | PASS | 7 |

`Latent cooling, ungated` is the diagnostic contrast column only — the zone moisture balance before the plant-on gate. It is never part of a total.

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
| +Closure fixes | `6e549fa18`, `82a909d3f`, `9fd8c696c`, `09357302f` | ADJ transmission into the inventory, latent gating, GR classification |

## 3. Order-independence and the canonical figure

Applying the same set of corrections in a different order must land on the same engine, so the check is made on the **source**, not only on the numbers — a difference that happened not to move this particular building's annual result would still be caught.

The reordered trajectory's final state is **byte-for-byte identical** to HEAD's engine tree across every `.py` file under `pybuildingenergy/src/`. The reordering therefore cannot have moved the canonical figure, and did not:

| Metric | Canonical (closed-balance run) | This trajectory's final state | Δ |
| --- | ---: | ---: | ---: |
| `Q_H_sensible_kWh` | 122.69 | 122.69 | 0.002 |
| `Q_C_sensible_kWh` | 67.12 | 67.12 | 0.001 |
| `Q_C_latent_kWh` | 3.98 | 3.98 | 0.004 |
| `Q_need_total_kWh_per_sqm` | 9.69 | 9.69 | 0.001 |

HEAD remains canonical: **122.69 kWh sensible heating + 67.12 kWh sensible cooling + 3.98 kWh gated latent = 193.79 kWh = 9.69 kWh/m²·yr**, unchanged by the reordering.

## 4. The residual gate

The V2 Sankey closure residual is under the 5 % gate on **every** state of the reordered trajectory; the largest excursion is -1.69 % at *+Conditioned zones*, and from the ground-contact fix onward it is machine-zero. Every state lists 7 transmission line items, so no state is measured with part of the envelope missing from its inventory. The instrument is identical across states by construction — the closure commits are cherry-picked onto each one — which is what makes the states comparable at all, and is also why the final `+Closure fixes` step moves no number: its content is already in the instrument. That the closure fixes change the measurement and not the physics is the finding, not an artefact.

## 5. A caveat on the sensible-cooling column

`+C2 wind-dependent h_ce` raises sensible cooling by +119.58 kWh here, and by +48.73 kWh when the same switch is thrown on the final engine. The wind diagnostic (`results/diagnostics/wind_verdict.md`) traces **96 % of that increase to hours where the EPW's wind column reads exactly 0.0 m/s** — and four whole months of that column (January, March, July, September) are identically zero, which is missing data rather than calm. Two of them are the peak cooling months.

The trajectory above is reported as it stands and the canonical figure is unchanged, but the cooling component of every state from `+C2` onward carries that caveat, and it should be resolved before the h_ce correction is defended in the text.

## 6. Provenance

* baseline: `2e6e910`
* closure commits: `6e549fa18`, `82a909d3f`, `9fd8c696c`, `09357302f`
* weather: `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`
* Baseline: `2e6e910c1`
* +C1 dynamic window: `244001d0a`
* +C2 wind-dependent h_ce: `4fa31ffad`
* +Ventilation: `4130739cf`
* +Latent: `08b79507b`
* +Internal gains: `fe79adece` — conflicts outside the engine resolved in favour of the state in `.gitignore`
* +Conditioned zones: `9d92854e5`
* +Ground contact: `6590e927a`
* +Hemisphere: `ae09e2b3a`
* +Closure fixes: `85976e0ff` — conflicts outside the engine resolved in favour of the state in `.gitignore, colab_closed_balance.ipynb`

**Gate passed and HEAD invariant.** Reduction percentages and kWh/m² headlines may be computed from this table.
