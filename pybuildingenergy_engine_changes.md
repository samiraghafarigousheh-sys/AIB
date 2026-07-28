# pyBuildingEnergy engine changes — Australian correction plan

> **This file did not exist in the AIB repository and was created here.** The
> repo's pre-existing log is [`CHANGES.md`](CHANGES.md), which covers the window
> and surface-heat-transfer branches in a similar but differently-headed format
> (Severity / Applies to / Root cause / Fix / Validation / Measured effect /
> Caveats). This file uses the headings the correction plan asked for
> (Severity / Applies to / Symptom / Root cause / Fix / Impact of fix /
> Diagnostic) and covers the four Australian corrections only. If a
> `pybuildingenergy_engine_changes.md` exists elsewhere — the
> `PyBuildingEnergy_AIBteam_AU` fork is the likely home — these four entries
> should be merged into it rather than maintained twice.

Reference case throughout: Apt 305, 50 Barry St, Carlton, on
`AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`.

---

## Summary table

| # | Change | Branch | Severity | apt 305 effect |
| --- | --- | --- | --- | --- |
| 1 | Internal-gains inflation from the adjacent-zone loop | `claude/internal-gains-fix` | **Critical** | Internal gains ÷7.335 (5 356.7 → 730.3 kWh) |
| 2 | Conditioned adjacent zones (Issue 7) | `claude/conditioned-adjacent-zones-fix` | **Critical** | Total 210.4 → 34.9 kWh/m² (−83.4 %) |
| 3 | Ground-contact-area fallback | `claude/ground-contact-fix` | **High** | Ground loss 68.8 → 0.0 kWh; demand unchanged |
| 4 | Hemisphere-aware `coldest_month` | `claude/coldest-month-hemisphere-fix` | **Medium** | None (correctly — see entry) |

Cumulative: **172.9 → 34.9 kWh/m², −79.8 %**.

Each branch is cut from the previous one, so a diff between two adjacent
branches isolates exactly one change. The chain starts at
`claude/ventilation-plus-latent-fix`.

## Priority order

1. **Change 2** — largest single effect, and the only one that makes the
   reference case behave like the building it describes. Depends on the
   surface-typing correction below.
2. **Change 1** — largest error *in magnitude* (a 7.3× overstatement of a
   primary input), and it contaminates any gains-sensitive comparison.
3. **Change 3** — removes a fabricated energy path from every report; live in
   the solver too for genuine ground-floor buildings.
4. **Change 4** — no effect on this building, but wrong by six months for every
   southern-hemisphere ground-floor building.

### Prerequisite, outside the four changes

**apt 305's party surfaces were typed `"opaque"` instead of `"adjacent"`.** The
engine classifies a surface as ADJ purely from `type`; a `name_adj_zone` on an
`"opaque"` surface is ignored. Worse, `type == "opaque"` with
`sky_view_factor == 0` maps to **`GR` — slab-on-ground**, so all five party
surfaces *including the ceiling* were modelled as buried in the earth: 75.1 m²
of ground contact on a third-floor apartment. Change 2 is provably inert without
this correction (measured: heating and cooling bit-identical to 12 significant
figures with the neighbours conditioned vs not). Fixed in
`examples/apt305_building.py`; only the `type` changed.

### Highest-value remaining defect

**The `type == "opaque"` + `sky_view_factor == 0` → `GR` rule itself**
(`utils.py`, both single-zone cores). It is what produced the 75.1 m², and it
will silently mis-type any internal partition given a zero sky view factor. Not
addressed by these four changes.

---

## Change 1 — Internal-gains inflation from the adjacent-zone loop

**Severity** — Critical. A primary input overstated by 7.3× for this building,
scaling with neighbour count, contaminating every gains-sensitive result.

**Applies to** — `VentilationInternalGains.internal_gains()` in
`source/ventilation.py`. Reached from two call sites in each single-zone core.

**Symptom** — Internal gains reported as 616 W occupants / 440 W appliances for
a 20 m² apartment whose ISO 16798-1 table values are 84 W / 60 W. The
EnergyPlus alignment audit reported 52.8 W/m² against a dictionary value of
16 W/m² and attributed the gap to the ISO table rather than to a bug.

**Root cause** —

```python
if unconditioned_zones_nearby:
    Phi_int_dir_z_t = q_int_total * a_use
    for zones in range(list_adj_zones):
        Phi_int_z_t += Phi_int_dir_z_t + (1-b_ztu)*Fztc_ztu_m*Phi_int_dir_z_t
```

`q_int_total` is built from **this** zone's `building_type_class` and `a_use`,
so nothing was transferred from the neighbour. The loop multiplied the zone's
own gain by `1 + n·(1 + (1-b_ztu)·F_ztc_ztu_m)` — 7.335× for apt 305. It also
read whichever `b_ztu` and `F_ztc_ztu_m` the caller's loop left in scope (the
*last* adjacent zone's), so reordering the neighbour list changed the result.

**Fix** — Loop removed. `Phi_int_z_t = q_int_total * a_use`, whatever the
neighbour count. The neighbour's real contribution is modelled elsewhere and
exactly once, as `phi_gn_dir_ztu` inside the `theta_ztu` buffer temperature;
verified it has no other consumer, so this removes an inflation, not a transfer.
The four adjacency arguments stay in the signature but are inert.

**Impact of fix** — Internal gains 5 356.69 → 730.29 kWh (÷7.335, matching the
analytic factor to four significant figures). Heating 1 522.6 → 3 228.2 kWh,
cooling 646.3 → 308.3 kWh, ventilation loss 2 377.3 → 1 796.6 kWh.

**Diagnostic** — Run the same building with `number_adj_zone` 0, 1 and 5: annual
internal gains must be identical. Or compare `Q_internal_gains_kWh` against
`q_int_table × a_use × mean_profile × 8760`.

---

## Change 2 — Conditioned adjacent zones (Issue 7)

**Severity** — Critical. Determines transmission through every shared surface,
which for an internal apartment is most of the envelope.

**Applies to** — `theta_ztu` assembly in both single-zone cores
(`_Temperature_and_Energy_needs_calculation_core` and its `_ahu_causal` twin),
plus `source/check_input.py`.

**Symptom** — A 20 m² apartment with five occupied neighbours predicting
3 228 kWh of heating (161 kWh/m²), dominated by transmission through party
walls that in reality see almost no temperature difference.

**Root cause** — ISO 52016-1 routes every adjacent zone through the ISO 13789
unconditioned-buffer model, `theta_ztu = theta_int − b_ztu(theta_int − T_e) +
phi_gn_dir_ztu/H_ztu`. With `b_ztu` 0.73–0.93 the neighbour tracks **outdoor**
air. Correct for an attic or garage; wrong for a party wall shared with another
conditioned apartment.

**Fix** — Adjacent zones may declare `conditioned: bool` and `setpoint: float`.
A conditioned zone is held at its setpoint; with none declared it falls back to
the zone's own previous operative temperature (ΔT = 0 exactly). Both optional,
defaulting to previous behaviour. Implemented through three shared helpers —
`_adjacent_zone_conditioning`, `_init_theta_ztu` (conditioned zones seeded at
their setpoint, so the pinning holds at *every* timestep including before the
solver's first update) and `_theta_ztu_unconditioned` — used by both cores.
`check_input.py` validates both fields.

Two further fixes inside the rewritten block: `b_ztu` is now read **per zone**
(it was the last adjacent zone's, applied to all), and `theta_ztu_df` is only
built on the multi-zone path (the single-zone path raised `NameError`).

**Impact of fix** — Heating 3 228.2 → 123.4 kWh (−96.2 %), cooling 308.3 → 20.1
kWh (−93.5 %), heating attributed to transmission 748.4 → 33.6 kWh (−95.5 %),
total 210.4 → 34.9 kWh/m² (−83.4 %).

**Diagnostic** — Capture `theta_ztu` and assert it equals the declared setpoint
at every timestep (max deviation measured: **0.0 K** over 9 504 steps × 5 zones).
Complementary check: `_theta_ztu_unconditioned` must be called **0** times when
every neighbour is conditioned — it is called ≈71 000 times when they are not.

> ADJ surfaces produce no `Q_tr_surface_*` entries and are excluded from
> `Q_tr_opaque_*`, so party-wall transmission cannot be read as a line item.
> Use the attribution columns.

---

## Change 3 — Ground-contact-area fallback

**Severity** — High. Fabricates an energy path that does not exist, in every
report, for any building without explicit ground tagging.

**Applies to** — `_ground_contact_area()` and `Temp_calculation_of_ground()` in
`source/utils.py`; new coherence check in `source/check_input.py`.

**Symptom** — A Level 3 apartment with a non-zero ground loss and gain in its
Sankey, every hour of the year.

**Root cause** — `_ground_contact_area()` fell back to
`building.net_floor_area` when no surface was tagged, so absence of evidence
became a full-footprint slab. The legacy `sky_view_factor`/`tilt` path that was
supposed to catch real floors used `tilt > 170`, which presumes 0 = up /
180 = down; this codebase uses 0 = horizontal / 90 = vertical, under which a
floor and a ceiling are both tilt 0. So it matched nothing and always fell
through.

**Fix** — Returns **0.0** when nothing is tagged; no longer raises. Recognises
`boundary == "GROUND"`, then `ISO52016_type_string == "GR"`, then the legacy
inference — now **opt-in** via `building.legacy_ground_inference`, accepting
horizontal under either convention and requiring `name_adj_zone` to be empty (a
floor over another zone is a party slab, never ground). `check_input.py` warns
when `exposed_perimeter > 0` with no ground tag, reading the *declared*
perimeter so the validator's own 0 → 1.0 coercion cannot cause a false positive.
`B' = A/(0.5·P)` divisor guarded for unsanitised dictionaries.

**Impact of fix** — Ground contact 20.0 → 0.0 m², ground loss 68.81 → 0.00 kWh,
ground gain 2.19 → 0.00 kWh. **Heating and cooling unchanged to 12 significant
figures** — correct: after change 2 the building has no `GR` elements, so the
ground term only ever existed in the reported balance. Live in the solver for
genuine ground-floor buildings.

**Diagnostic** — `_ground_contact_area()` must return 0.0 for a building with no
ground tag *and* the correct area for one with a `boundary: "GROUND"` surface;
the second case is what distinguishes the fix from a blanket zero. Cross-check
`R_gr_ve` against ISO 13370 §8.1–8.2 by hand (reference case: `B'` = 3.750,
`d_t` = 10.880, `U_sog` = 0.15881 W/m²K, `R_gr_ve` = 0.5769 — engine agrees to
1e-6).

---

## Change 4 — Hemisphere-aware `coldest_month`

**Severity** — Medium. Six-month phase error in the whole ground model for every
southern-hemisphere site; zero effect on buildings without ground contact.

**Applies to** — `Temp_calculation_of_ground()` in `source/utils.py`, all three
`coldest_month` usage sites.

**Symptom** — Ground temperature peaking in July and troughing in February for a
Melbourne building — exactly opposite the local air-temperature cycle.

**Root cause** — `coldest_month = 1`, hardcoded. It sets the phase of the
internal-temperature estimate and both periodic ground heat-flow terms. The
function's own docstring already specified hemisphere selection ("1 for northern
hemisphere or 7 in southern hemisphere"); only the code disagreed.

**Fix** — `_resolve_coldest_month()` drives all three sites. An explicit
`building_parameters.coldest_month` wins; otherwise latitude < 0 → July,
latitude ≥ 0 → January. A missing or unusable latitude keeps January
deliberately — that is the previous behaviour, and flipping a building's ground
phase on an absent input would be worse than leaving it alone. Resolution is
idempotent, which matters because the function writes its result back into the
dictionary.

**Impact of fix** — **None for apt 305, and that is the correct outcome**:
change 3 already resolved its ground-contact area to zero, so every ground term
is inert regardless of phase. On a ground-floor test building at Melbourne's
latitude the ground temperature peak moves from August to **February** and the
trough from February to **August**.

**Diagnostic** — On a southern ground-floor building, `Theta_gr_ve` must peak in
the southern summer. Flipping the latitude sign must move peak and trough by
exactly six months while leaving the amplitude unchanged. Peak lands in February
rather than January because the ISO 13370 external term carries a one-month lag
(`b_tl = 1`) — ground lags air, so the offset is correct.
