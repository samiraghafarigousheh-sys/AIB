# Australian correction plan — cumulative rollup

Apt 305, 50 Barry St, Carlton. Weather
`AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw` (Melbourne Regional Office,
0.008° from the building). Every column is the same building and the same
weather; only the engine varies.

| # | State | Branch |
| --- | --- | --- |
| 0 | Baseline | `claude/pybuildingenergy-baseline-anjro8` |
| 0 | +Vent+Latent | `claude/ventilation-plus-latent-fix` |
| 1 | +Internal Gains | `claude/internal-gains-fix` |
| 2 | +Conditioned Zones | `claude/conditioned-adjacent-zones-fix` |
| 3 | +Ground Fix | `claude/ground-contact-fix` |
| 4 | +Hemisphere Fix | `claude/coldest-month-hemisphere-fix` |

## The journey

| Metric (kWh) | Baseline | +Vent+Latent | +Int. Gains | +Cond. Zones | +Ground | +Hemisphere |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Heating | 1 308.58 | 1 522.63 | 3 228.24 | 123.39 | 123.39 | 123.39 |
| Cooling | 741.83 | 646.28 | 308.30 | 20.06 | 20.06 | 20.06 |
| Total internal gains | 5 356.69 | 5 356.69 | 730.29 | 730.29 | 730.29 | 730.29 |
| Ground loss | 90.19 | 84.66 | 63.14 | 68.81 | **0.00** | 0.00 |
| Ground gain | 2.85 | 3.27 | 7.79 | 2.19 | **0.00** | 0.00 |
| Ventilation+infiltration loss | 1 868.54 | 2 377.33 | 1 796.62 | 2 096.26 | 2 096.26 | 2 096.26 |
| **Total energy need** | 3 457.20 | 2 573.53 | 4 207.24 | **697.13** | 697.13 | 697.13 |
| **kWh/m²** | 172.86 | 128.68 | 210.36 | **34.86** | 34.86 | 34.86 |

**172.9 → 34.9 kWh/m², −79.8 %.** The path is not monotone, and shouldn't be:
step 1 removes phantom free heat and pushes demand *up* before step 2 removes
the phantom exposure that made that heat necessary.

Which step did what:

* **Step 1** divided internal gains by exactly **7.335**, the analytically
  predicted inflation factor. Heating up, cooling down.
* **Step 2** did the heavy lifting: −96 % heating, −93 % cooling, total from
  210.4 to 34.9 kWh/m². This is the step that makes the reference case behave
  like an apartment inside a block.
* **Step 3** zeroed the ground term (68.81 → 0.00 kWh loss) without moving
  demand, because after step 2 the building has no `GR` elements and the ground
  flow only ever existed in the *reported* balance.
* **Step 4** changed nothing for apt 305, correctly — step 3 had already made
  every ground term inert. Validated separately on a ground-floor test building,
  where it moves the ground temperature peak from August to February.

## What still can't be explained — flagged, not fixed

1. **`type == "opaque"` + `sky_view_factor == 0` → `GR` in both single-zone
   cores.** This is the rule that gave a third-floor apartment 75.1 m² of
   slab-on-ground, ceiling included. apt 305 no longer reaches it (its party
   surfaces are typed `adjacent`), but it will silently mis-type any internal
   partition given a zero sky view factor. **This is the highest-value remaining
   defect** and it is a silent misclassification, not a warned fallback.
2. **Issue 10 — schedule index offset**, the plan's own next candidate.
   Heating at 6.2 kWh/m² and cooling at 1.0 kWh/m² are low but no longer
   *implausible* for a 20 m² unit with one exposed facade, five conditioned
   neighbours and zeroed thermal mass, so this rollup does not provide new
   evidence for or against it. Out of scope here; still worth checking.
3. **Ventilation loss is now 3× total demand** (2 096 kWh against 697 kWh).
   That is arithmetically possible — losses are offset by 730 kWh of internal
   gains and by heat flowing back in — but the ratio is worth a look, and it is
   the one number in this table nothing in steps 1–4 was aimed at.
4. **The EnergyPlus comparison has not been re-run** on the corrected building.
   Its alignment audit asserts the ISO side models neighbours as ISO 13789
   buffers; on the ISO side it never did, while the E+ side did get OSC objects
   built from `b_ztu`. That comparison was mismatched in a way the audit could
   not detect, and every figure in it predates the surface-typing correction.
5. **The corridor's `conditioned: True` is an assumption.** It is the
   least-insulated neighbour (`b_ztu` 0.733), so it carries more weight than any
   other single zone. Worth confirming against the building's actual services.

## Deliverables

| Path | Contents |
| --- | --- |
| `comparison.csv` / `.md` | states as rows, metrics as columns, with % vs previous and % vs baseline |
| `comparison_by_metric.csv` / `.md` | the transpose — metrics as rows, all six states as columns |
| `au_corrections_summary.png` | grouped bars: heating, cooling, total (kWh/m²) across all six states |
| `results.json` | raw floats, full precision |
| `run_meta.json` | the weather file this run actually used |

Per-step deliverables and write-ups are under `results/step_1_internal_gains/`,
`results/step_2_conditioned_zones/`, `results/step_3_ground/` and
`results/step_4_hemisphere/`.
