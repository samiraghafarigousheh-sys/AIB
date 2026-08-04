# What this run supersedes

Everything the paper's results sections were drafted against. This run regenerates
all of it on one weather file, one building specification, and one reporting
instrument. **No engine logic changed.** Nothing below has been edited or deleted
— the superseded artefacts are the record of how each defect was found, and the
RO weather file stays in `weather_cache/` because the wind before/after contrast
needs it. **No `.tex` file was touched.**

No `.tex` source is present in this repository, so the mapping below is by
*content* — what the number is — rather than by line. Match on the values.

---

## 1. The validation table and figure (drafted as Table 2 / Figure 1)

**Superseded, and the headline finding inverts.**

| | Heating: ISO vs E+ | Cooling: ISO vs E+ | Total |
| --- | ---: | ---: | ---: |
| Superseded — RO weather, party surfaces typed `opaque` | 15.9 vs 766.2 kWh (**−98 %**) | 2,027.5 vs 900.4 kWh (**+125 %**) | −18.4 % |
| **This run** — Essendon, typed `adjacent` | **1,779.36 vs 1,120.25 kWh (+58.8 %)** | **640.84 vs 697.16 kWh (−8.1 %)** | **+33.2 %** |

Any sentence saying **"ISO under-predicts heating and over-predicts cooling"** is
now wrong in both directions. On the canonical building ISO *over*-predicts
heating substantially and tracks cooling to within 8 %.

**Attribute the inversion to the building, not to the weather.** Two inputs
differ and only one matters much:

1. **The typing — dominant.** The old table ran with the five party surfaces
   typed `"opaque"`; with `sky_view_factor: 0` the core maps that to **GR —
   slab-on-ground**, so a third-floor apartment carried 75.10 m² of buried
   envelope including its ceiling. On one engine and one weather file the two
   typings give 15.86 / 2,027.5 against 1,308.60 / 741.83 kWh
   (`results/diagnostics/README.md`, finding 1).
2. **The weather — secondary.** Tens of kWh, not thousands.

Also superseded: any text reading the ~18 % total agreement as validation
success. On this run the total is +33.2 %, worse than the cooling error and
better than the heating error — it summarises neither.

→ `validation_iso_vs_ep/validation_iso_vs_ep.{csv,md,png}`, `apt305.idf`

## 2. The baseline energy balance (drafted as Section 4.1.1 / Figure 2)

**Superseded.** The old Sankey was built from the annual balance columns and drew
its gap as a `Transmission (residual)` *flow*, which makes any diagram close by
construction and so cannot check closure. Its stated figures were in 6,779 /
out 6,779 kWh with a **703 kWh (10 %) residual**, and only **two** transmission
line items for a seven-surface building.

This run: **in 8,305.6 / out 8,402.3 kWh, residual −96.72 kWh (−1.16 %), seven
line items**, residual drawn as an unmatched gap on the input side rather than
republished as a flow.

→ `baseline_balance/baseline_balance.{csv,md}`, `baseline_balance_sankey.png`

## 3. The 9.69 kWh/m²·yr headline

**Superseded by 9.00 kWh/m²·yr.**

| Metric | Superseded (RO) | This run (Essendon) | Δ | Δ % |
| --- | ---: | ---: | ---: | ---: |
| Sensible heating | 122.69 kWh | **172.82** | +50.13 | +40.9 % |
| Sensible cooling | 67.12 kWh | **6.34** | −60.78 | −90.6 % |
| Gated latent cooling | 3.98 kWh | **0.78** | −3.20 | −80.4 % |
| Total | 193.79 kWh | **179.95** | −13.84 | −7.1 % |
| **Per area** | **9.69 kWh/m²·yr** | **9.00** | −0.69 | −7.1 % |

**Do not report the total alone.** It moved −7.1 % while its components moved
+40.9 % and −90.6 %. A sentence quoting only the total describes none of what
changed.

→ `canonical_trajectory/comparison.{csv,md}`, `INDEX.md`

## 4. Anything describing C2 (wind-dependent h_ce) as increasing cooling

**Directionally wrong on clean wind, not merely imprecise.**

| | Superseded (RO) | This run (Essendon) |
| --- | ---: | ---: |
| C2 step in the trajectory | **+119.58 kWh** cooling | **−25.30 kWh** cooling |
| C2 switch on the final engine | **+48.73 kWh** cooling | **−3.27 kWh** cooling |
| Share of that from exactly-zero wind | 96.3 % | 0.0 % |
| Verdict | **(c)** — not explained by real wind | **(a+b)** |

With 59.8 % of hours above the 4 m/s pivot, `h_ce = 4v + 4` sits *above* the ISO
fixed 20 W/(m²·K) for most of the year instead of collapsing to a fifth of it, so
a stronger external film sheds more absorbed solar from the west wall
(absorptance 0.75) back to the air. **C2 now reduces cooling.**

Also superseded: the caveat paragraph saying the C2 cooling figure rests on hours
of fabricated calm and must be resolved before the correction is defended. **That
open item is closed** — replace it with the (a+b) finding rather than deleting it
silently.

→ `diagnostics/wind/wind_verdict_essendon.md`, `wind_distribution_essendon.png`

## 5. Tables 4 and 5

**Both superseded, and Table 5's provenance changed.**

* **Table 4** now comes directly from the trajectory's first three states — same
  measurements as the trajectory's rows 1–3, zero extra runs.
* **Table 5** is emitted in two forms because the cumulative trajectory
  structurally cannot produce the original 2×2: the latent fix *without* the
  ventilation fix is not a state on that path, and the six-state closed-balance
  harness cannot supply it either (its second state has both fixes already
  combined). **5a** is the methodology-order form from the trajectory; **5b** is
  the 2×2, measured from the same baseline on the same instrument.

Cite deliberately: 5a answers "what does each fix add where the methodology
applies it"; 5b answers "are the two fixes separable". Their columns are not
interchangeable.

→ `tables_4_5/` — see `PROVENANCE.md` there

## 6. `corrected_weather_results_rewrite.tex`

**Superseded twice over** — first for the mis-specified building (flagged in
`results/diagnostics/README.md` before this effort began), now also for the RO
weather. Redo it against `results/paper/`; do not patch it.

## 7. Everything else on the RO file

Retained, unedited, not to be quoted as a result:

| Directory | Status |
| --- | --- |
| `results/baseline_vs_ep/` | ISO vs E+ on RO weather **and** the mis-specified building |
| `results/au_canonical/` | the trajectory on RO weather |
| `results/au_canonical_essendon/` | correct, but superseded in *scope* by `results/paper/`, which carries the same trajectory plus validation, Tables 4/5 and the diagnostics |
| `results/au_corrections_closed/` | six-state closed balance, RO weather |
| `results/diagnostics/wind_verdict.md`, `wind_distribution.png`, `wind_stats.json` | the verdict-(c) evidence — **keep**, it is why the weather file was replaced |
| `results/au_corrections_summary/`, `results/step_1_*` … `step_4_*` | earlier steps, RO weather and (for the older ones) the mis-specified building |
| `RUN_ORDER.md` steps 1–4 | numbers are RO-era; the file carries a banner saying so |

---

## What is *not* superseded

The engine, and every claim about it.

* No engine logic changed in this run. The trajectory's final state is
  byte-for-byte identical to HEAD's tree, and HEAD run directly on this weather
  reproduces it to 0.00e+00 on all four headline metrics.
* The methodology order, the closure fixes, the ADJ transmission inventory
  (7 line items, re-integration 0.0000 %), the latent gate (nothing charged with
  the plant off or while heating), the GR classification and the
  southern-hemisphere phase all hold exactly as before.
* Regression suite: **198 passed, 0 skipped, exit 0**.

One test threshold changed during the preceding weather-file task and is recorded
here so it is not discovered later:
`test_latent_heating_stays_negligible` previously pinned the **ungated** latent
heating audit column at < 0.1 kWh. That column is weather-dependent — 0.004 kWh
over 2 hours on RO, 3.50 kWh over 28 hours on Essendon, same engine, because a
windier site strips more moisture and the zone dips under the EN 16798-1 deadband
in more hours. The **charged** quantity is now held at exactly zero and the audit
column bounded as a share of the 789 kWh the deadband replaced.
