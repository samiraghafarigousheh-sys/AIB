# Closing the energy balance — what was wrong, what was done, what now holds

**Status: the hard gate passes.** The V2 Sankey closure residual is under 5 % on
the canonical baseline and on every downstream state; the ADJ transmission is in
the inventory; latent cooling is charged only in plant-on hours.

Deliverables in this directory:

| File | What it is |
| --- | --- |
| `six_state_closed.md` | the six-state table with the residual column and the gate |
| `six_state_closed.csv` | the same, machine-readable |
| `six_state_closed_raw.json` | every number the harness collected, plus provenance |
| `au_corrections_closed_balance.png` | the faceted chart, rebuilt from these numbers |

Regenerate with:

```
python tools/diagnostics/closed_balance_six_state.py \
    --weather weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw \
    --outdir results/au_corrections_closed
python tools/diagnostics/make_closed_balance_chart.py
```

---

## 1. Defect A — the ADJ surfaces were not in the inventory

### Case 1 or case 2: decided by experiment, not by reading

The plan asked for these two to be distinguished explicitly rather than assumed.
The test: if the party surfaces were thermally inert (case 1), moving the
neighbours' setpoint could not move the demand.

| Neighbours held at | Q_H (kWh) | Q_C (kWh) | mean zone air (°C) | Sankey transmission line items |
| ---: | ---: | ---: | ---: | --- |
| 20 °C | 122.69 | 67.12 | 19.090 | 2 |
| 26 °C | 0.00 | 494.98 | 22.476 | 2 |

**Case 2.** `theta_ztu` is consumed by the solver — the ADJ branch of the
external-node assembly drives both `VecB` and `MatA` with it — so the
conditioning numbers were never wrong. The inventory was the problem: the
per-timestep accumulator carried `if surface_types[Eli] not in ("OP", "W"):
continue`, so 75.10 m² of party surface, 88.6 % of the envelope UA, appeared in
neither the inputs nor the outputs. The setpoint sweep moves the answer while
the line-item count stays at two, which is exactly what case 2 predicts.

### The residual that remained after tallying ADJ alone

Tallying the ADJ surfaces took the canonical baseline from **+62.41 % to
+23.98 %**, leaving **1 084.58 kWh** open. Reported before proceeding, as the
plan requires, and it is not a rounding artefact — it is one term, exactly:

```
(1 − f_int_c) · Q_int + (1 − f_sol_c) · Q_sol
  = 0.6 × 730.29 + 0.9 × 718.23
  = 438.17 + 646.40
  = 1 084.58 kWh          measured residual: 1 084.58 kWh
```

ISO 52016-1 formula (39) deposits the radiative fractions of the internal and
solar gains **directly onto the internal surface nodes**. That energy reaches
the envelope without ever crossing the air node, so a transmission term read at
the internal face cannot see it — while the inputs side was counting the gains
in full. The inventory was measuring two different control volumes at once.

The fix picks the volume the storage term already spans (`C_state` carries every
element node's capacity): **zone air plus envelope**. Transmission is therefore
read at each element's *outer* face, mirroring the external-node row the solver
assembled — same coefficients, same boundary temperature, same sky and solar
treatment, so the two cannot drift. Absorbed short-wave is a source at that same
node and is netted per surface (the sol-air convention); the gross figure is
still published as `Q_sol_envelope`, because on a dark west brick wall the two
gross terms are ~9.2 and ~10.1 MWh and publishing them separately would bury a
123 kWh heating need under a pair of near-cancelling arrows.

Result on the canonical building: **inputs 4 007.25 kWh, outputs 4 007.25 kWh,
residual 0.00 %.**

### Three smaller things found on the way, all fixed

* **`0 × inf`.** With no ground contact `h_ground` is exactly 0, while
  `Theta_gr_ve` is formed by dividing by that same zero area — so `q_ground`
  came back `NaN`, and because every comparison against `NaN` is False it was
  folded into the inputs, making the whole balance unevaluable. The previous
  diagnostic harness had to monkey-patch around this to measure anything. It is
  now short-circuited to 0 in the engine. This does not touch the
  ground-contact-area fix itself.
* **Two neighbours, one element.** Surface aggregation keyed on
  `adjacent_zone` (usually `None`) and not on `name_adj_zone`, so a floor over
  apt 205 and a ceiling under apt 405 — both HOR, both ADJ — collapsed into one
  element carrying whichever neighbour was seen first. Both sit at 20 °C here so
  apt 305's numbers are unchanged, but the five party surfaces now report as
  five line items rather than four.
* **Stale index.** `name_adjacent_zones` was built from the pre-aggregation
  surface list and then indexed with post-aggregation `Eli`.

## 2. Defect B — latent cooling was a moisture balance wearing plant clothing

Before, on the canonical building: **8 758 of 8 760 hours** charged with latent
cooling against **146 hours** of actual cooling-plant operation; 550.6 of
554.62 kWh accrued with the plant off. Outdoor air is essentially never at
exactly the indoor reference humidity, so an unconditional accumulation books
latent energy almost every hour of the year — including hours when the *heating*
plant is running.

Latent cooling is now charged only where both conditions hold: the cooling plant
is operating (`Q_C > 0`), and the moisture balance calls for dehumidification.
Latent heating is gated symmetrically on the heating plant.

| | before | after |
| --- | ---: | ---: |
| latent cooling | 554.62 kWh | **3.98 kWh** |
| hours charged | 8 758 | **146** |
| charged with cooling off | 550.64 kWh | **0.00 kWh** |
| charged while heating runs | 17.34 kWh (as diagnosed) | **0.00 kWh** |
| latent heating | 0.0043 kWh | **0.0000 kWh** |

The monthly maximum stays in January — the southern-hemisphere phase survives
the gate. The ungated moisture balance is kept, not discarded
(`Q_latent_W_ungated`, `Q_C_latent_ungated_kWh`, plus per-timestep gate flags),
so the fix is auditable and the moisture balance is still available as what it
actually is.

**On "latent heating stays at ~0.03 kWh".** The plan's expected value came from
`claude/coldest-month-hemisphere-fix`. On main the ungated term is 0.0043 kWh,
not 0.034 — a difference that predates this work and comes from what landed on
main afterwards. Either way it is ~0 and the C2 fix has not regressed; the six
states in `six_state_closed.md` report their own actual values rather than the
expected one.

### The reported total

Never again one number with an ungated latent term folded into it. Every run now
reports `Q_H_sensible_kWh`, `Q_C_sensible_kWh`, `Q_H_latent_kWh`,
`Q_C_latent_kWh`, `Q_sensible_total_kWh`, `Q_latent_total_kWh` and
`Q_need_total_kWh`. On the current engine:

```
189.81 kWh sensible  +  3.98 kWh latent  =  193.79 kWh   (9.69 kWh/m²·yr)
```

against the 697.10 kWh / 34.85 kWh/m² the ungated definition produced.

## 3. Upstream — the GR rule that made two baselines out of one building

`type == "opaque"` with `sky_view_factor == 0` was mapped to `GR`,
slab-on-ground. A zero sky-view factor means "not exposed to sky", which is true
of every internal partition, floor and ceiling. Typed `"opaque"`, apt 305's five
party surfaces — the ceiling of a third-floor apartment included — became
75.10 m² of phantom slab clamped near the ISO 13370 ground temperature.

Classification now lives in one function, `_classify_iso52016_element`, shared by
the single-zone core and both multizone paths. `GR` requires an explicit
`boundary: "GROUND"`. An opaque surface naming an adjacent zone is a partition
whatever its declared type — which is what makes config A and config B the same
building. `check_input.py` warns on the genuinely undeclared case (`svf == 0`,
no ground boundary, no adjacent zone) instead of silently burying it.

Convergence, measured:

| | config A | config B | difference |
| --- | ---: | ---: | ---: |
| `Q_H_annual_kWh` | 122.691925 | 122.691925 | 0.000e+00 |
| `Q_C_annual_kWh` | 67.121099 | 67.121099 | 0.000e+00 |
| `Q_need_total_kWh` | 193.788899 | 193.788899 | 0.000e+00 |
| `Q_tr_adjacent_loss_kWh` | 1 135.233741 | 1 135.233741 | 0.000e+00 |
| surfaces classified `GR` | none | none | — |

Bit-exact. Config A no longer produces 15.86 / 2 027.5.

## 4. What the closed table shows

Every state passes. The residual that survives on the four states before the
ground fix is **exactly** the phantom ground term — a lumped
`h_ground · (T_in − T_gr)` flow with no `GR` element behind it in the solver —
and the ground fix removes it, taking the residual to zero. That is the same
+66.61 kWh effect the Item 3 diagnosis attributed to that fix, now measured on a
balance where it is the only thing left to remove.

Two cautions for whoever writes the text:

* **`+Hemisphere Fix` and `+Closure Fixes (HEAD)` are different engines.** The
  seventh row is main plus these three commits; the sixth is the historical
  branch. They differ by what landed on main afterwards, chiefly the dynamic
  external convective coefficient, which moves sensible cooling 20.06 → 67.12 kWh.
  Quote one, name which, and do not average them.
* **The six historical states are measured with a back-ported instrument.** The
  three closure commits are cherry-picked onto each branch so the reporting is
  identical across states; the mechanics, including the one compatibility shim
  and the one conflict resolution, are in the harness docstring and in §6 of
  `six_state_closed.md`. The *physics* of each state is untouched.

## 5. Verification

* `tests/test_sankey_closure_adj_transmission.py` — all five party surfaces
  present as line items; Sankey transmission total equals an independent
  per-surface re-integration from the hourly frame to within 0.1 % (measured:
  0.0000 %); residual under the gate; no republished residual flow; and a
  ground-floor building still reports a non-zero ground flow, counted once.
* `tests/test_latent_gating.py` — gated to plant-on hours; zero with the plant
  off; zero while heating runs; southern-hemisphere phase retained; latent
  heating negligible; the split adds up.
* `tests/test_gr_classification.py` — the classifier never returns `GR` without
  a ground boundary; the validator warns on the ambiguous case and stays quiet
  on the canonical dictionary; config A and config B converge.

198 tests pass.

## 6. Not touched, by instruction

The ground fix, the internal-gains fix, the Melbourne/Zone 6 labelling, the
window F_w,dir methodology, the High-Fidelity Upgrades document, and every
`.tex` file.
