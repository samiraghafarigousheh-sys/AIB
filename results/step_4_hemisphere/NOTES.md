# Step 4 — Hemisphere-aware `coldest_month`

Branch `claude/coldest-month-hemisphere-fix`, off `claude/ground-contact-fix`.
Weather `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`.

## What the fix changes physically

`coldest_month = 1` was hardcoded in `Temp_calculation_of_ground`. It sets the
phase of every ISO 13370 ground sinusoid — the internal-temperature estimate and
both periodic heat-flow terms — so for any southern-hemisphere site the entire
ground model ran six months out of phase, putting peak ground temperature in
July for Melbourne.

The function's own docstring already specified the correct behaviour: *"the
default values: 1 for northern hemisphere or 7 in southern hemisphere are
used."* Only the code disagreed. `_resolve_coldest_month()` now drives all three
usage sites, with an explicit `building_parameters.coldest_month` still winning
so a site with a known local minimum can override the hemisphere default.

## Expected direction, and whether it matched

> **apt 305 shows no change from this fix, and that is the correct outcome, not
> a failed fix.** Step 3 already resolved this building's ground-contact area to
> zero, so every ground term is inert regardless of its phase. The `+Hemisphere
> Fix` column being identical to `+Ground Fix` is what *should* happen. Read it
> as confirmation that step 3 did its job, not as evidence that step 4 does
> nothing.

Validated instead on the ground-floor test building from step 3 (56.25 m² slab,
30 m perimeter, same Melbourne EPW), where the ground term is live:

| Metric | Expected | Actual | Match |
| --- | --- | --- | :-: |
| `coldest_month`, lat −37.8 | 7 (July) | **7** | ✅ |
| `coldest_month`, lat +45.5 | 1 (January) | **1** | ✅ |
| Ground temp peak, southern | southern summer | **February** | ✅ |
| Ground temp trough, southern | southern winter | **August** | ✅ |
| Northern vs southern | exactly 6 months apart | **6** for both peak and trough | ✅ |
| Amplitude | unchanged; phase only | max/min identical to 1e-9 | ✅ |
| apt 305 | no change | identical to 12 s.f. | ✅ |

Southern profile, °C by month:

```
Jan 22.5  Feb 23.5  Mar 22.5  Apr 19.8  May 16.1  Jun 12.4
Jul  9.7  Aug  8.7  Sep  9.7  Oct 12.4  Nov 16.1  Dec 19.8
```

Peak lands in **February, not January**, because the ISO 13370 external term
carries a one-month lag (`b_tl = 1`). Ground lags air — that is the point of the
periodic model — so the offset is correct, and the test asserts on the
southern-summer window rather than a single month.

## Flags

- **`building.latitude` is populated for apt 305** (−37.800) and is read
  directly, not inferred from the EPW header. Confirmed rather than assumed:
  under `weather_source="epw"` the *solar* geometry comes from the EPW header
  while this function takes latitude from the dictionary, so the two could in
  principle disagree. For apt 305 they do not — the bundled Melbourne Regional
  Office EPW is 0.008° from the declared coordinates.
- **A missing or unusable latitude keeps January**, deliberately. That is the
  previous behaviour, and silently flipping a building's ground phase on the
  strength of an absent input would be worse than leaving it alone. Any
  dictionary without a latitude therefore keeps the northern-hemisphere
  assumption and gets no warning — worth knowing if a southern building is ever
  fed in without coordinates.
- **This fix is invisible in the apt 305 comparison chart by construction.** If
  the reference case is ever changed to a ground-floor unit, this column will
  start moving and the step-3 column will too.

## Validation

- `tests/test_coldest_month_hemisphere.py` (engine branch), 21 tests: both
  hemispheres, the equator, the explicit override and its validation, missing
  and unusable latitude, and idempotence — which matters because
  `Temp_calculation_of_ground` writes the resolved value back into the
  dictionary and a second call reads its own output.
- `tests/test_apt305_ground_and_hemisphere.py` (harness branch): the phase
  assertions above on real weather, plus the latitude-flip inversion.
- Upstream suite: **284 passed, 7 failed, 10 skipped** — identical counts and an
  identical failure set to the parent branch.
