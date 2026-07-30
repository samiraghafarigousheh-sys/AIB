# Step 3 — Ground-contact-area fallback

Branch `claude/ground-contact-fix`, off `claude/conditioned-adjacent-zones-fix`.
Weather `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`.

## What the fix changes physically

`_ground_contact_area()` ended with a last-resort fallback to
`building.net_floor_area` whenever no surface was tagged, so every unclassified
building silently got a full-footprint slab-on-ground. apt 305 — Level 3,
nothing touching the earth — came out with a 20 m² slab and a non-zero ground
flux every hour of the year. Absence of a ground surface now means **no ground
contact**, and the function returns 0.0 instead of guessing.

The legacy `sky_view_factor`/`tilt` inference is kept but made **opt-in** via
`building.legacy_ground_inference`. Its old condition, `tilt > 170`, presumes
the convention 0 = upward / 180 = downward; this codebase uses
0 = horizontal / 90 = vertical — stated in the example dictionaries' own `units`
block — under which a floor and a ceiling are *both* tilt 0 and cannot be told
apart by tilt at all. So the rule matched nothing in practice and fell straight
through to the fallback. It now accepts horizontal under either convention and
additionally requires `name_adj_zone` to be empty: a floor over another zone is
a party slab, never ground.

## Expected direction, and whether it matched

Comparison is `+Conditioned Zones` → `+Ground Fix`.

| Metric | Expected | Actual | Match |
| --- | --- | --- | :-: |
| Ground-contact area | 20.0 → 0.0 m² | 20.0 → **0.0** | ✅ |
| Ground loss | → exactly 0 | 68.81 → **0.00** kWh | ✅ |
| Ground gain | → exactly 0 | 2.19 → **0.00** kWh | ✅ |
| Heating / cooling | unchanged (see below) | 123.39 / 20.06, identical to 12 s.f. | ✅ |
| Ground-floor test building | still non-zero | `R_gr_ve` = 0.5769, matches hand calc | ✅ |

**Heating and cooling do not move, and that is the correct result.** With the
party surfaces now typed ADJ (step 2), apt 305 has no `GR` elements at all, so
the ground term never entered the solver — only the *reported* energy balance
carried the phantom, computed from `t_Th.ground_contact_area`. This step fixes a
reporting artefact for this building: the Sankey's ground arrows go away, the
demand does not change. For a genuine ground-floor building the term is live in
both the solver and the report.

## What the earlier ground numbers actually were

Worth recording, because they moved twice and for different reasons:

| | ground contact area | ground loss | ground gain |
| --- | ---: | ---: | ---: |
| Party surfaces typed `opaque` (pre-step-2) | **75.1 m²** | 139.04 | 74.57 |
| Party surfaces typed `adjacent` (step 2) | 20.0 m² | 68.81 | 2.19 |
| After this fix | **0.0 m²** | 0.00 | 0.00 |

The 75.1 m² is the more revealing number. With `type: "opaque"` and
`sky_view_factor: 0`, the core classifies a surface `GR` — so before the step-2
retyping, all five party surfaces *including the ceiling* were slab-on-ground.
A third-floor apartment was modelled as having 75 m² of its envelope buried in
the earth.

## Flags

- **The `type == "opaque"` + `sky_view_factor == 0` → `GR` rule in the core is
  the deeper defect** (`utils.py`, both single-zone cores). It is what produced
  the 75.1 m², and it will do the same to any dictionary that gives an internal
  partition a zero sky view factor without typing it `adjacent`. Not fixed here
  — it is outside step 3's scope and apt 305 no longer reaches it — but it is
  the obvious next candidate and it is a silent misclassification, not a
  fallback with a warning.
- **`_ground_contact_area()` no longer raises.** It used to raise `ValueError`
  when neither surfaces nor `net_floor_area` were available. Returning 0.0 is
  the right answer for a building with no ground contact, so the exception had
  to go; any caller depending on it for validation should use the new
  `check_input` warning instead.
- **The `check_input` warning reads the *declared* perimeter**, not the
  sanitised one. The building-level fixer rewrites a zero perimeter to 1.0, and
  warning on a value the validator itself invented would fire on every
  intermediate-floor building — including apt 305, which correctly declares
  `exposed_perimeter: 0`.

## Validation

- `tests/test_ground_contact_area.py` (engine branch), 25 tests: the zero
  default, both explicit tags, the opt-in gate, the party-slab exclusion, tilt
  under either convention, zero-area conductance, and every branch of the new
  `check_input` warning.
- `tests/test_apt305_ground_and_hemisphere.py` (harness branch): apt 305's
  ground loss and gain are exactly 0 over a full annual run, **and** a minimal
  ground-floor dictionary still produces `R_gr_ve` = 0.5769, matching an
  independent ISO 13370 recomputation (`B'` = 3.750, `d_t` = 10.880,
  `U_sog` = 0.15881 W/m²K) to 1e-6. That second case is what stops this being a
  blanket "always return 0".
- Upstream suite: **284 passed, 7 failed, 10 skipped** — identical counts and an
  identical failure set to the parent branch.
