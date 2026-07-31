# Item 3 — V2 Sankey closure residual, all six states

**Result: every state fails the 5 % V2 tolerance, including after Step 3.** The
ground-contact fix does exactly what it claims and nothing more — it removes a
66.6 kWh phantom ground term — but the balance is short by 450–5 066 kWh, so
that fix was never capable of closing it. The unaccounted term is identified in
[§4](#4-where-the-missing-energy-is): the **ADJ surface class**, 75.10 m² and
88.6 % of the envelope UA, which appears **nowhere** in the Sankey inventory.

Measured on the **canonical** building (Item 1: party surfaces typed
`adjacent`), one worktree per state, weather
`AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`.
Harness: `tools/diagnostics/six_state_diagnostics.py`. Raw: `six_state_raw.json`.

---

## 1. The table

Residual is computed exactly as the engine's own `SANKEY CHECK` line does:

```
inputs   = heating + internal gains + solar & free-gain
outputs  = cooling + ventilation + thermal bridges + ground
           + per-surface transmission (positive branches only)
residual = inputs − outputs − storage
```

`Transmission (residual)` is excluded from the outputs sum — it is the residual
re-published as a flow, and including it would make every state close by
construction.

| State | Inputs (kWh) | Outputs (kWh) | Storage | **Residual (kWh)** | **Residual %** | **≤ 5 %?** |
| --- | ---: | ---: | ---: | ---: | ---: | :-: |
| Baseline | 8 117.58 | 3 051.10 | 0.00 | **+5 066.48** | **+62.41 %** | ❌ FAIL |
| +Vent+Latent | 8 308.06 | 3 438.92 | 0.00 | **+4 869.15** | **+58.61 %** | ❌ FAIL |
| +Internal Gains | 5 392.75 | 2 585.33 | 0.00 | **+2 807.42** | **+52.06 %** | ❌ FAIL |
| +Conditioned Zones | 2 295.48 | 2 812.40 | 0.00 | **−516.92** | **−22.52 %** | ❌ FAIL |
| +Ground Fix | 2 293.28 | 2 743.59 | 0.00 | **−450.31** | **−19.64 %** | ❌ FAIL |
| +Hemisphere Fix | 2 293.28 | 2 743.59 | 0.00 | **−450.31** | **−19.64 %** | ❌ FAIL |

The sign flips at Step 2. Before it, the model reports more energy in than out;
after it, more out than in. Both are the same defect seen from opposite sides —
see §4.

### On the brief's "10 % / ~703 kWh at baseline"

That figure is real but was measured on the **mis-specified** building (Item 1
config A, party surfaces typed `opaque` → classified `GR`):

```
config A (GR)   inputs=6 779 156.0 Wh   outputs+storage=6 078 826.7 Wh   residual=700 329.3 Wh (10.331 %)
```

On the canonical building the baseline residual is **62.41 % / 5 066 kWh**, six
times worse. The 10 % figure should not be carried into the paper.

---

## 2. Step 3 did not close the balance — and could not have

Step 3 moves the residual from −516.92 to −450.31 kWh, an improvement of
**+66.61 kWh**. That is exactly the phantom ground term it removes:

| | Step 2 | Step 3 | Δ |
| --- | ---: | ---: | ---: |
| `Ground` (an output) | 68.81 | 0.00 | −68.81 |
| ground gain (inside `Solar & free-gain`, an input) | 2.19 | 0.00 | −2.19 |
| residual = inputs − outputs | −516.92 | −450.31 | **+66.61** |

`(−2.19) − (−68.81) = +66.62` — matching the measured +66.61 to rounding. So the
ground fix is **arithmetically exactly what it claims**: it deletes a phantom
20 m² slab worth 66.6 kWh of throughput, no more and no less.

**The identical heating/cooling/total across Steps 2→3 is therefore the correct
outcome**, and the mechanism is now verified rather than asserted: those five
party surfaces are typed `adjacent`, so apt 305 has no `GR` element in the
solver at all. The ground term existed only in the *reporting* path, computed
from `t_Th.ground_contact_area` — which the pre-Step-3 `_ground_contact_area()`
filled from `net_floor_area` because no surface carried a ground tag. Removing a
term that was never in the solver cannot change the solved demand.

But the balance was short by 516.92 kWh and the phantom was worth 66.6 kWh.
**Step 3 was never a candidate to close a residual eight times its own size.**

---

## 3. A defect Step 3 *introduces*: `Theta_gr_ve` divides by zero

Running Steps 3 and 4 unmodified, the engine prints:

```
SANKEY CHECK  inputs=nan  outputs+storage=2743593.0  residual=nan Wh (nan%)
```

**The balance is not merely open after Step 3 — it is unevaluable.** Root cause,
traced end to end:

1. `_ground_contact_area()` correctly returns `0.0` for apt 305 (the Step 3 fix).
2. `Temp_calculation_of_ground` still evaluates, at `utils.py:3946`:
   ```python
   Theta_gr_ve = internal_temperature_by_month - (...) / (sog_area * U_sog)
   ```
   With `sog_area = 0.0` this is a division by zero, and `Theta_gr_ve` comes back
   as `[-inf, -inf, -inf, -inf, -inf, inf, ...]` — verified directly, all twelve
   months non-finite.
3. In the Sankey accumulator, `h_ground` is correctly `0.0`, so
   ```python
   q_ground = h_ground * (T_in - T_gr)   # 0.0 * inf  ->  NaN
   ```
4. At `utils.py:8555-8556`:
   ```python
   if q_ground > 0:  E_ground_loss_Wh += q_ground * dt_h
   else:             E_solar_Wh       += (-q_ground) * dt_h
   ```
   Every comparison against NaN is `False`, so the `else` branch runs and
   **`E_solar_Wh` is poisoned permanently**. `inputs_Wh` becomes NaN and the
   whole balance with it.

**Scope: reporting only.** Heating, cooling and latent are bit-identical with and
without the repair (123.387740 / 20.060292 / 553.62 / 0.03), because the ground
node is not in the solver's element network — there are no `GR` surfaces. The
solved demand is unaffected; only the Sankey inventory is.

### How §1 measured Steps 3–4 without touching the engine

`h_ground` is exactly `0`, so the true ground contribution is exactly `0` and
*any* finite `Theta_gr_ve` yields the same answer. The harness substitutes a
finite value when the engine returns non-finite, purely so the accumulator does
not latch NaN. That is a measurement device, not a model change, and the run
confirms it: H/C/latent come back bit-identical to the unrepaired run.

**No engine code was modified.** Per the brief this is logged, not fixed. The
one-line repair, when someone takes it: guard the division so that a zero
`sog_area * U_sog` yields `Theta_gr_ve = internal_temperature_by_month` (no
ground path ⇒ zero ground flux) instead of ±inf.

---

## 4. Where the missing energy is

**The `ADJ` surface class is absent from the Sankey inventory entirely.**

The inventory for the final state, complete:

| Inputs | kWh | | Outputs | kWh |
| --- | ---: | --- | --- | ---: |
| Heating | 123.39 | | Cooling (extracted) | 20.06 |
| Internal gains | 730.29 | | Ventilation (losses) | 2 096.26 |
| Solar & free-gain | 1 439.60 | | Thermal bridges | 1.62 |
| | | | Ground | 0.00 |
| | | | Transmission — West exterior wall | 333.92 |
| | | | Transmission — West windows | 291.73 |
| **total** | **2 293.28** | | **total** | **2 743.59** |

Two transmission entries. The building has **seven** opaque/transparent
surfaces. The five party surfaces are missing, and it is not that they net to
zero — they are structurally excluded. Measured on the hourly frame:

```
                        loss(+) kWh   gain(-) kWh     net kWh
Q_tr_total                   620.08       -512.03      108.05
Q_tr_opaque (OP)             333.92       -380.32      -46.40
Q_tr_window  (W)             291.73       -137.28      154.45
RESIDUAL = ADJ                 0.00         -0.00        0.00     <-- exactly zero
```

`Q_tr_total ≡ Q_tr_opaque + Q_tr_window`, to the last digit. No
`Q_tr_surface_*` column exists for any party surface. The ADJ class contributes
**nothing** to reported transmission on either side of the balance.

What is excluded:

| | value | share of envelope |
| --- | ---: | ---: |
| ADJ surfaces | 5 | — |
| ADJ area | **75.10 m²** | **84.8 %** of 88.60 m² |
| ADJ conductance | **159.75 W/K** | **88.6 %** of 180.38 W/K |

A first-order `U·A·ΔT` estimate against the zone air node (neighbours pinned at
20 °C, mean `T_air` 19.05 °C) puts the ADJ flow at **+2 225.8 kWh in / −891.6 kWh
out, net +1 334.2 kWh into the zone**. That is an upper bound — it ignores the
surface node's film resistance and capacity, which the ISO 52016 element model
interposes — but the sign and order of magnitude are what matter: the ADJ class
is a **large net heat input** that the inventory never records.

That resolves the sign flip in §1. Before Step 2 the party surfaces were `GR`,
so their inward flow was at least partly captured through the `Ground` term and
the balance ran input-heavy. From Step 2 they are `ADJ` and vanish from both
sides; since their net is a gain, the missing quantity is an **input**, and
outputs now exceed inputs by 450–517 kWh — the right order for the ~1.3 MWh
gross first-order estimate once film resistance is taken into account.

### Next candidate (not fixed here, per the brief)

Two defects, in priority order:

1. **ADJ surfaces are not inventoried in the Sankey energy balance**
   (`E_trans_loss_by_surface_Wh` / `E_solar_Wh` accumulators, both cores). Worth
   450–517 kWh on this building, 88.6 % of envelope UA. This is what has to be
   fixed for V2 to pass; nothing in the current correction chain touches it.
2. **`Theta_gr_ve` divides by zero when `sog_area == 0`** (`utils.py:3946`,
   introduced by Step 3). Worth nothing in energy terms — the solver is
   unaffected — but it makes the V2 metric unevaluable on Steps 3–4, so it
   blocks measuring defect 1.

---

## 5. Reproducing

```bash
python tools/diagnostics/six_state_diagnostics.py --repair-ground-nan \
    --weather weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw \
    --out results/diagnostics/six_state_raw.json
```

Drop `--repair-ground-nan` to see Steps 3–4 report `nan`.
