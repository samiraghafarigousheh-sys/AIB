# Step 1 — Internal-gains inflation from the adjacent-zone loop

Branch `claude/internal-gains-fix`, off `claude/ventilation-plus-latent-fix`.
Weather `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`.

## What the fix changes physically

`internal_gains()` used to re-add the zone's **own** internal gain once per
adjacent zone, undiscounted, plus a `(1-b_ztu)`-weighted term. Nothing was
transferred from the neighbour — `q_int_total` is built from *this* zone's
`building_type_class` and `a_use` — so the loop simply multiplied the zone's
gain by `1 + n·(1 + (1-b_ztu)·F_ztc_ztu_m)`. For apt 305 that is **7.335×**,
using the corridor's `b_ztu = 0.733`, which is the value the caller's own loop
happens to leave in scope. The zone was being told it contained seven
apartments' worth of people and appliances. Removed; the zone now gets the
ISO 16798-1 table value for its own area and nothing else.

The neighbour's real contribution is unaffected: it is modelled separately, and
exactly once, as `phi_gn_dir_ztu` inside the `theta_ztu` buffer temperature,
which then drives conduction across the shared surface. Checked that
`phi_gn_dir_ztu` has no other consumer, so this removes an inflation, not a
transfer.

## Expected direction, and whether it matched

| Metric | Expected | Actual | Match |
| --- | --- | --- | :-: |
| Total internal gains | ÷7.335 exactly | 5 356.7 → 730.3 kWh (÷**7.335**) | ✅ |
| Heating | large increase — the phantom gains were free heat | 37.3 → 1 274.6 kWh | ✅ |
| Cooling | large decrease — less heat to reject | 1 727.2 → 699.8 kWh (−59.5 %) | ✅ |
| Ventilation+infiltration loss | decrease — cooler zone, smaller ΔT | 3 235.4 → 1 846.1 kWh (−42.9 %) | ✅ |
| Ground loss / gain | small second-order shift only | 175.6 → 139.0 / 47.2 → 74.6 kWh | ✅ |
| Total energy need | direction not predictable a priori | 2 070.8 → 2 615.9 kWh (+26.3 %) | — |

The ÷7.335 is the load-bearing check: it is the analytically predicted factor,
reproduced to three decimals by the engine, so the effect is exactly the removed
term and nothing else. 730.3 kWh/yr for a 20 m² apartment at a 144 W full-load
table value implies a ~58 % mean profile load, which is sensible for residential
occupancy.

Total energy need rising is not a regression: heating gains far more than
cooling loses, because the removed phantom gain was warming a zone whose
neighbours are (still, at this step) modelled as unconditioned buffers tracking
outdoor air. Step 2 addresses that.

## Flags

- **63.7 kWh/m² heating is high for a 20 m² Melbourne apartment** with one
  exposed facade. Not treated as a failure of this step — the five neighbours
  are still ISO 13789 unconditioned buffers with `b_ztu` 0.73–0.93, i.e. they
  mostly track outdoor air, so the apartment is effectively surrounded by
  outside on six sides. Step 2 is the test of that reading: if heating does not
  fall sharply there, something else is wrong.
- **`b_ztu` is still applied per-building, not per-zone**, at
  `utils.py:8080` / `utils.py:9703` — the `theta_ztu` loop indexes `H_ztu` per
  zone but reuses the scalar `b_ztu` left over from the coefficient loop.
  Deliberately **not** fixed here (one fix per branch); it is inside the block
  Step 2 rewrites, and is fixed there.

## Validation

- `tests/test_internal_gains_adjacency.py` (engine branch), 16 tests: invariance
  over 0/1/5 neighbours, invariance to `b_ztu` and `F_ztc_ztu_m`, exact
  agreement with the ISO table value, profiles and `full_load` overrides intact.
- `tests/test_apt305_internal_gains_invariance.py` (harness branch), 5 tests:
  the same sweep driven from apt 305's own dictionary and its five neighbours'
  real coefficients, confirming the 7.335 factor from the building rather than
  from a remembered number.
- Upstream suite: **284 passed, 7 failed, 10 skipped**, identical counts and an
  identical failure set to the parent branch (2 network-blocked, 5 pre-existing
  ventilation-boundary).
