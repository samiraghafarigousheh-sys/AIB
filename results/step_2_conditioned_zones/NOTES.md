# Step 2 — Conditioned adjacent zones (Issue 7)

Branch `claude/conditioned-adjacent-zones-fix`, off `claude/internal-gains-fix`.
Weather `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`.

## ⚠ Read this first: the baseline moved, and why

apt 305's five party surfaces were declared `type: "opaque"` with a
`name_adj_zone`. The engine classifies a surface as ADJ **purely from `type`** —
a `name_adj_zone` on an `"opaque"` surface is silently ignored. So all five party
surfaces were being modelled as **exterior walls exposed to outdoor air and
sky**: the apartment was effectively outdoors on six sides, `theta_ztu` was
computed every timestep and never consumed, and the adjacency pairing checks in
`check_input.py` (which key off the same `type`) never ran either.

Measured directly before touching anything: marking the neighbours conditioned
changed heating and cooling by **exactly zero** (bit-identical to 12 s.f.),
while `theta_ztu` swung from 4.2 °C to 28.0 °C — computed, unused. Step 2 is
provably inert without this.

The five surfaces are now typed `"adjacent"`. **Only the type changed** — areas,
U-values, capacities, orientations and the adjacent-zone definitions are
untouched. Every column in the comparison therefore shifts, including Baseline:

| | Heating (kWh) | Cooling (kWh) |
| --- | ---: | ---: |
| Baseline, party surfaces typed `opaque` (all figures published before this step) | 15.86 | 2 027.51 |
| Baseline, party surfaces typed `adjacent` | 1 308.58 | 741.83 |

Any earlier figure from this repo — the EnergyPlus comparison, the window
branches, the ventilation/latent table — is for a free-standing 20 m² box, not
an apartment inside a block. That includes the EnergyPlus alignment audit's
claim that the ISO side models neighbours as ISO 13789 buffers: on the ISO side
it never did. The E+ side *did* get OSC objects built from `b_ztu`, so that
comparison was mismatched in a way the audit did not detect.

## What the fix changes physically

A zone marked `conditioned: True` is held at its declared `setpoint` instead of
being run through the ISO 13789 unconditioned-buffer formula. With `b_ztu`
0.73–0.93 that formula makes the neighbour track *outdoor* air — right for an
attic or a garage, wrong for a party wall shared with another occupied,
conditioned apartment, where the real ΔT is small.

## Expected direction, and whether it matched

Comparison is `+Internal Gains` → `+Conditioned Zones`, i.e. step 2 alone.

| Metric | Expected | Actual | Match |
| --- | --- | --- | :-: |
| `theta_ztu` per zone | pinned at 20.0 °C, all timesteps | max deviation **0.0 K** over 9 504 steps × 5 zones | ✅ |
| Buffer formula evaluations | zero for conditioned zones | **0** (≈71 000 when unconditioned) | ✅ |
| Heating attributed to transmission | large fall | 748.4 → 33.6 kWh (**−95.5 %**) | ✅ |
| Cooling attributed to transmission | large fall | 113.6 → 8.0 kWh (−93.0 %) | ✅ |
| Heating | large fall | 3 228.2 → 123.4 kWh (−96.2 %) | ✅ |
| Cooling | large fall | 308.3 → 20.1 kWh (−93.5 %) | ✅ |
| Total energy need | large fall | 4 207.2 → 697.1 kWh (−83.4 %), **34.9 kWh/m²** | ✅ |

34.9 kWh/m²·yr total for a 20 m² Melbourne apartment with one exposed facade and
conditioned neighbours is a plausible number, which the previous 210 kWh/m² was
not. This is the step that makes the reference case behave like the building it
describes.

## Flags

- **The acceptance criterion "party-wall transmission → near zero" cannot be
  read off the annual frame.** Once typed ADJ, those surfaces produce no
  `Q_tr_surface_*` entries at all and are excluded from `Q_tr_opaque_*`, which
  now equals the West exterior wall alone. The evidence is therefore the
  attribution columns (`Q_H_attr_transmission_kWh`, −95.5 %) plus the direct
  `theta_ztu` assertion, not a party-wall line item. Worth knowing before
  looking for one.
- **ΔT across the party surfaces is not actually zero.** The neighbours sit at
  20 °C while this zone floats between its 18 °C heating and 26 °C cooling
  setpoints, so ΔT reaches ±6 K. "Near-isothermal" is the right description;
  "zero" is not, and the residual 33.6 kWh of transmission-attributed heating is
  real, not numerical noise.
- **The corridor's `conditioned: True` is an assumption, not a measurement.**
  Common corridors in this building type are usually tempered, but the actual
  services at 50 Barry St have not been checked. It is the least-insulated
  neighbour (`b_ztu` 0.733, lowest of the five), so it carries more weight than
  any other single zone. `ADJ_SETPOINT` in `apt305_building.py` documents this;
  set `conditioned: False` on that entry alone to test the alternative.
- **Two incidental fixes inside the rewritten block**, both flagged in the
  commit rather than folded in silently: `b_ztu` is now read per zone (it was
  the last adjacent zone's, applied to all — provably inert here, since no
  zone is unconditioned), and `theta_ztu_df` is only built on the multi-zone
  path (the single-zone path used to raise `NameError` at that line).

## Validation

- `tests/test_conditioned_adjacent_zones.py` (engine branch), 27 tests: field
  parsing, per-zone seeding, the unconditioned formula asserted against the
  inline expression it replaced, the table B.16 cap, every `check_input` branch.
- `tests/test_apt305_conditioned_zones.py` (harness branch), 5 tests over a full
  annual run: party surfaces really are typed `adjacent`, `theta_ztu` equals the
  setpoint at every timestep, the buffer formula is never reached, demand lands
  in a plausible band.
- Upstream suite: **284 passed, 7 failed, 10 skipped** — identical counts and an
  identical failure set to the parent branch.
