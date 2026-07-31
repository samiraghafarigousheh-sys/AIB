# Item 4 — Latent load breakdown and plausibility

**Verdict: the ~554 kWh is genuine latent _cooling_, not a regression of the C2
latent fix — but it is not a plausible energy demand, because the model charges
dehumidification in 8 757 of 8 760 hours, 99.6 % of it while the cooling plant is
switched off.** Latent *heating* is 0.03 kWh in the final state and stays near
zero through every downstream branch, so C2 holds. The number that needs
qualifying in the paper is the total, not the latent-heating fix.

Measured on the canonical building (Item 1), same six worktrees as Item 3.
Harness: `tools/diagnostics/six_state_diagnostics.py`. Raw: `six_state_raw.json`.

---

## 1. Definition of "Total energy need" — stated explicitly

**Sensible + latent**, specifically:

```
Q_total_annual_kWh = Q_H_annual_kWh          (sensible heating)
                   + Q_C_annual_kWh          (sensible cooling)
                   + Q_latent_annual_kWh     (latent cooling / dehumidification)
                   + Q_H_latent_annual_kWh   (latent heating / humidification)
```

Checked against the published final state:
`123.39 + 20.06 + 553.62 + 0.03 = 697.10` ✓ (published 697.098904).

`Q_latent_annual_kWh` and the hourly `Q_C_latent` are the same quantity — verified
equal in all six states — so "latent cooling" below refers to both.

---

## 2. The six-state latent table

| State | Sensible heating | Sensible cooling | **Latent cooling** | **Latent heating** | Total | latent-C share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 1 308.60 | 741.83 | **617.38** | **789.35** | 3 457.16 | 17.9 % |
| +Vent+Latent | 1 522.61 | 646.25 | **404.21** | **0.46** | 2 573.53 | 15.7 % |
| +Internal Gains | 3 228.23 | 308.30 | **670.63** | **0.07** | 4 207.23 | 15.9 % |
| +Conditioned Zones | 123.39 | 20.06 | **553.62** | **0.03** | 697.10 | 79.4 % |
| +Ground Fix | 123.39 | 20.06 | **553.62** | **0.03** | 697.10 | 79.4 % |
| +Hemisphere Fix | 123.39 | 20.06 | **553.62** | **0.03** | 697.10 | 79.4 % |

**The C2 latent fix holds.** Latent heating collapses 789.35 → 0.46 kWh at
`+Vent+Latent` and then stays at 0.07 / 0.03 / 0.03 / 0.03 through every
downstream state. **No regression** — the reappearance the brief was watching for
did not happen.

**Nothing downstream of `+Vent+Latent` touches the latent model.** Latent cooling
moves only because the states change zone temperature and therefore the reference
humidity: 404.21 → 670.63 (gains de-inflated, zone runs cooler) → 553.62
(neighbours pinned at 20 °C), then frozen for Steps 3 and 4, which are ground-only.

**The 79 % share is an artefact of the denominator collapsing, not of latent
growing.** Latent cooling *falls* from 670.63 to 553.62 across Step 2, while
sensible demand falls 3 536.53 → 143.45. Latent ends up dominant because the
sensible loads were corrected downward by 96 %, not because the latent term rose.

---

## 3. Composition — where the 553.62 kWh comes from

| Component | kWh | note |
| --- | ---: | --- |
| Ventilation latent | 348.36 | outdoor air moisture removed |
| Internal latent | 205.33 | occupant moisture generation |
| **Sum** | **553.69** | vs reported 553.62 ✓ |

Arithmetically self-consistent with the model's own psychrometrics:

| | value |
| --- | --- |
| `X_ext` mean | 0.007264 kg/kg da |
| `X_int_ref` mean | 0.006950 kg/kg da |
| mean ΔX | 0.000313 kg/kg da |
| `m_dot_vent` mean | 0.05198 kg/s |

`0.05198 × 0.000313 × 2.5e6 J/kg ≈ 40.7 W` → `40.7 W × 8 760 h ≈ 356 kWh`,
against the 348.36 kWh reported for the ventilation half. The number the engine
produces follows from its inputs; the problem is upstream of the arithmetic.

**Contributing input, worth flagging separately:** ventilation is declared as
`flow_rate_per_person: 2.0` with `units: "l/(s m²)"` — the key says *per person*,
the units say *per m²*, and the engine applies the per-area reading: 2.0 l/s·m² ×
20 m² = 40 l/s ≈ 156 m³/h ≈ **2.9 ACH** on a 54 m³ apartment. Typical dwelling
practice is nearer 0.5 ACH. The latent load scales linearly with this, so a large
part of the 348 kWh ventilation latent traces to a key/units mismatch in
`apt305_building.py`, not to the weather.

---

## 4. Seasonality — the shape is right

Latent cooling by month, kWh (final state):

| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 68.6 | **97.8** | 81.4 | 39.3 | 24.9 | 20.8 | **17.4** | 18.3 | 21.8 | 43.3 | 43.2 | 77.0 |

Peaks in the southern summer (Feb), troughs in the southern winter (Jul).
Correct hemisphere phase, correct shape for dehumidification.

**But it never goes to zero.** 17.4 kWh of dehumidification in July, in a month
whose sensible cooling is zero, is the first sign the term is not gated on
anything.

---

## 5. Why it is not plausible as an energy demand

Hour-by-hour, final state:

| | hours | share |
| --- | ---: | ---: |
| Total | 8 760 | — |
| **Latent cooling charged** | **8 757** | **100.0 %** |
| Sensible cooling running | 66 | 0.8 % |
| Sensible heating running | 594 | 6.8 % |

| | kWh | share of 553.62 |
| --- | ---: | ---: |
| Charged while sensible cooling is **ON** | **2.29** | **0.4 %** |
| Charged while cooling is **OFF** | **551.33** | **99.6 %** |
| …of which while **heating** is running | 17.34 | 3.1 % |

* Dehumidification is charged in **essentially every hour of the year**, against
  66 hours of actual cooling operation.
* **6 129 hours** are charged with zone air **below 20 °C**; mean zone temperature
  across all ungated hours is **18.99 °C**.
* 17.34 kWh is charged while the **heating** plant is running — the model
  simultaneously heats the zone and bills for removing moisture from it.

The latent term is computed unconditionally from the ventilation air stream
whenever `X_ext > X_int_ref`, with no coupling to whether a cooling coil (or any
dehumidifier) exists or is operating. It is a *moisture balance*, reported as if
it were *plant energy*. For an apartment whose sensible cooling is 20.06 kWh/yr, a
coincident 553.62 kWh of dehumidification is 27× the sensible cooling and cannot
be an energy demand the building actually incurs.

### What this does to the headline number

| Definition | Total (kWh) | kWh/m²·yr |
| --- | ---: | ---: |
| As currently reported (sensible + all latent) | 697.10 | **34.85** |
| Sensible + latent coincident with cooling operation | 145.77 | **7.29** |
| Sensible only | 143.45 | **7.17** |

The published **34.85 kWh/m²·yr is ~79 % ungated latent**. Whatever definition the
paper adopts, it has to be stated — the three numbers above differ by a factor of
five and all three are defensible readings of the same run.

---

## 6. Verdict

Per the brief's decision rule — *"If it is a regression of the C2 latent fix …
fix it. If it is genuine latent cooling, leave it but document the magnitude and
model"* — this is the **second** case, so **no code was changed**:

* It is **not** a C2 regression. Latent heating is 0.03 kWh and holds across all
  four downstream branches.
* It **is** latent cooling, correctly signed, correctly phased for the southern
  hemisphere, and arithmetically consistent with the engine's own psychrometrics.
* Its **magnitude is not plausible as a demand**, for one specific and testable
  reason: it is ungated (99.6 % charged with the cooling plant off, 6 129 h below
  20 °C zone temperature), and it is amplified by a ventilation rate of ~2.9 ACH
  that comes from a key/units mismatch in the building dictionary.

Two follow-ups, logged not fixed:

1. **Gate the latent term on cooling operation** (or report it as a separate
   moisture-balance quantity outside "Total energy need"). Effect on this
   building: 553.62 → 2.29 kWh, total 697.10 → 145.77 kWh, 34.85 → 7.29 kWh/m².
2. **Resolve `flow_rate_per_person` vs `units: l/(s m²)`** in
   `examples/apt305_building.py`. The engine reads it per-area; if per-person was
   intended, ventilation and its latent load are both several times too large.
