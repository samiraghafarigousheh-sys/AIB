# Six-state harness on a closed energy balance

**Hard gate: V2 Sankey closure residual < 5 % on every state — PASSED.**

Canonical building: apt 305, 50 Barry St Carlton, party surfaces typed `adjacent` (config B). Weather `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`. One engine worktree per state, with the three closure commits cherry-picked on top so the reporting instrument is identical across states — see the harness docstring for what that involves and what it does not.

Residual is computed exactly as the engine's own `SANKEY CHECK` line does:

```
inputs   = heating + internal gains + solar & free-gain
outputs  = cooling + ventilation + thermal bridges + ground
           + per-surface transmission (positive branches only)
residual = inputs - outputs - storage
```

`Transmission (residual)` is excluded from the outputs sum — it is the residual re-published as a flow, and including it would make every state close by construction.

## 1. The gate

| State | Inputs (kWh) | Outputs (kWh) | Storage | Residual (kWh) | Residual % | < 5 %? | Transmission line items |
| --- | ---: | ---: | ---: | ---: | ---: | :-: | ---: |
| Baseline | 7,882.02 | 7,969.45 | 0.00 | **-87.42** | **-1.11 %** | PASS | 7 |
| +Vent+Latent | 8,065.33 | 8,146.75 | 0.00 | **-81.42** | **-1.01 %** | PASS | 7 |
| +Internal Gains | 5,276.34 | 5,331.66 | 0.00 | **-55.32** | **-1.05 %** | PASS | 7 |
| +Conditioned Zones | 3,864.43 | 3,931.04 | 0.00 | **-66.61** | **-1.72 %** | PASS | 7 |
| +Ground Fix | 3,862.23 | 3,862.23 | -0.00 | **-0.00** | **-0.00 %** | PASS | 7 |
| +Hemisphere Fix | 3,862.23 | 3,862.23 | -0.00 | **-0.00** | **-0.00 %** | PASS | 7 |
| +Closure Fixes (HEAD) | 4,007.25 | 4,007.25 | -0.00 | **-0.00** | **-0.00 %** | PASS | 7 |

Before these fixes the same column read 62.41 %, 58.61 %, 52.06 %, −22.52 %, −19.64 %, −19.64 % — every state failing, with only two transmission line items for a building with seven surfaces.

### What the residual that remains is made of

On the states before the ground fix it is not a rounding artefact: it is the phantom ground term, to the cent. Those states report a lumped `h_ground · (T_in − T_gr)` flow computed from a slab area that `_ground_contact_area()` filled in from `net_floor_area` because no surface carried a ground tag — a term that exists only in the reporting path and has no `GR` element behind it in the solver, so nothing in the balance answers for it.

| State | Residual (kWh) | −(ground loss − ground gain) (kWh) | Δ |
| --- | ---: | ---: | ---: |
| Baseline | -87.42 | -87.42 | 3.917e-11 |
| +Vent+Latent | -81.42 | -81.42 | 1.682e-12 |
| +Internal Gains | -55.32 | -55.32 | 1.673e-11 |
| +Conditioned Zones | -66.61 | -66.61 | 9.986e-12 |
| +Ground Fix | -0.00 | -0.00 | 1.397e-12 |
| +Hemisphere Fix | -0.00 | -0.00 | 1.397e-12 |
| +Closure Fixes (HEAD) | -0.00 | -0.00 | 9.313e-13 |

The ground fix removes that term, and the residual goes to zero — which is the same +66.61 kWh effect the Item 3 diagnosis attributed to it, now measured on a balance where it is the *only* thing left to remove.

## 2. Energy need, sensible and latent kept apart

| State | Sensible heating (kWh) | Sensible cooling (kWh) | Latent cooling, gated (kWh) | Latent heating (kWh) | Total (kWh) | Total (kWh/m²) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 1,308.60 | 741.83 | 55.76 | 157.9951 | 2,264.18 | 113.21 |
| +Vent+Latent | 1,522.61 | 646.25 | 29.21 | 0.0117 | 2,198.08 | 109.90 |
| +Internal Gains | 3,228.23 | 308.30 | 15.85 | 0.0450 | 3,552.43 | 177.62 |
| +Conditioned Zones | 123.39 | 20.06 | 2.29 | 0.0000 | 145.74 | 7.29 |
| +Ground Fix | 123.39 | 20.06 | 2.29 | 0.0000 | 145.74 | 7.29 |
| +Hemisphere Fix | 123.39 | 20.06 | 2.29 | 0.0000 | 145.74 | 7.29 |
| +Closure Fixes (HEAD) | 122.69 | 67.12 | 3.98 | 0.0000 | 193.79 | 9.69 |

## 3. The latent gate

| State | Steps | Cooling plant on | Latent charged | Latent gated (kWh) | Latent ungated (kWh) | Charged w/ cooling off | Charged while heating |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 8,760 | 1,030 | 288 | 55.76 | 617.38 | 0.0000 | 0.0000 |
| +Vent+Latent | 8,760 | 921 | 917 | 29.21 | 404.21 | 0.0000 | 0.0000 |
| +Internal Gains | 8,760 | 463 | 463 | 15.85 | 670.63 | 0.0000 | 0.0000 |
| +Conditioned Zones | 8,760 | 66 | 64 | 2.29 | 553.62 | 0.0000 | 0.0000 |
| +Ground Fix | 8,760 | 66 | 64 | 2.29 | 553.62 | 0.0000 | 0.0000 |
| +Hemisphere Fix | 8,760 | 66 | 64 | 2.29 | 553.62 | 0.0000 | 0.0000 |
| +Closure Fixes (HEAD) | 8,760 | 146 | 146 | 3.98 | 554.62 | 0.0000 | 0.0000 |

## 4. The adjacent-zone surfaces in the inventory

75.10 m², 88.6 % of the envelope UA. Previously absent from both sides of the balance.

| State | ADJ transmission loss (kWh) | ADJ transmission gain (kWh) | Line items | Reported Σ (kWh) | Independent Σ (kWh) | Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 4,554.61 | 2.82 | 7 | 5,267.01 | 5,267.01 | 0.0000 % |
| +Vent+Latent | 4,351.27 | 2.82 | 7 | 5,036.69 | 5,036.69 | 0.0000 % |
| +Internal Gains | 2,689.41 | 5.83 | 7 | 3,162.27 | 3,162.27 | 0.0000 % |
| +Conditioned Zones | 1,056.86 | 1,686.33 | 7 | 1,744.29 | 1,744.29 | 0.0000 % |
| +Ground Fix | 1,056.86 | 1,686.33 | 7 | 1,744.29 | 1,744.29 | 0.0000 % |
| +Hemisphere Fix | 1,056.86 | 1,686.33 | 7 | 1,744.29 | 1,744.29 | 0.0000 % |
| +Closure Fixes (HEAD) | 1,135.23 | 1,688.70 | 7 | 1,818.21 | 1,818.21 | 0.0000 % |

## 5. Config A / config B convergence

Config A types the five party surfaces `"opaque"`; config B types them `"adjacent"`. Before the GR-classification fix, config A buried all five as slab-on-ground and returned 15.86 kWh heating / 2 027.5 kWh cooling against config B's 1 308.60 / 741.83.

| State | Metric | Config A | Config B | Difference |
| --- | --- | ---: | ---: | ---: |
| +Closure Fixes (HEAD) | `Q_H_sensible_kWh` | 122.691925 | 122.691925 | 0.000e+00 |
| +Closure Fixes (HEAD) | `Q_C_sensible_kWh` | 67.121099 | 67.121099 | 0.000e+00 |
| +Closure Fixes (HEAD) | `Q_need_total_kWh` | 193.788899 | 193.788899 | 0.000e+00 |
| +Closure Fixes (HEAD) | `Q_tr_adjacent_loss_kWh` | 1,135.233741 | 1,135.233741 | 0.000e+00 |
| +Closure Fixes (HEAD) | `Q_ground_loss_kWh` | 0.000000 | 0.000000 | 0.000e+00 |

Surfaces classified `GR` on +Closure Fixes (HEAD): config A `[]`, config B `[]`.

## 6. Provenance

* closure commits back-ported: `6e549fa18, 82a909d3f, 9fd8c696c`
* weather: `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`
* Baseline: branch `claude/pybuildingenergy-baseline-anjro8`, conflicts resolved in favour of the branch in `pybuildingenergy/src/pybuildingenergy/source/check_input.py`, back-port shim applied
* +Vent+Latent: branch `claude/ventilation-plus-latent-fix`, conflicts resolved in favour of the branch in `pybuildingenergy/src/pybuildingenergy/source/check_input.py`, back-port shim applied
* +Internal Gains: branch `claude/internal-gains-fix`, conflicts resolved in favour of the branch in `pybuildingenergy/src/pybuildingenergy/source/check_input.py`, back-port shim applied
* +Conditioned Zones: branch `claude/conditioned-adjacent-zones-fix`, conflicts resolved in favour of the branch in `pybuildingenergy/src/pybuildingenergy/source/check_input.py`, back-port shim applied
* +Ground Fix: branch `claude/ground-contact-fix`, back-port shim applied
* +Hemisphere Fix: branch `claude/coldest-month-hemisphere-fix`, back-port shim applied
* +Closure Fixes (HEAD): branch `(this repository, unpatched)`

**Gate passed.** Reduction percentages and kWh/m² headlines computed from this table stand on a closed balance, and the methodology text can now be written against it.
