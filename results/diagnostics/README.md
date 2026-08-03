# Diagnostics — findings before the results are finalised

> **The wind finding is closed.** The h_ce diagnostic originally returned verdict
> **(c)** — the C2 cooling increase was *not* explained by real wind, because
> 96 % of it came from hours the Melbourne Regional Office EPW recorded as
> exactly 0.0 m/s across four fabricated dead-calm months. Re-run on the
> replacement station (Essendon Fields, WMO 958660, complete record) it returns
> **(a+b)**: 100 % of the C2 effect now comes from genuine non-zero wind bands,
> and 84.8 % of the cooling-plant hours sit above the 4 m/s pivot against 59.8 %
> of the year.
>
> | | Superseded (RO 948680) | Current (Essendon 958660) |
> | --- | --- | --- |
> | Verdict | [`wind_verdict.md`](wind_verdict.md) — **(c)**, weather column unusable | [`wind_verdict_essendon.md`](wind_verdict_essendon.md) — **(a+b)** |
> | Figure | `wind_distribution.png` | `wind_distribution_essendon.png` |
> | Stats | `wind_stats.json` | `wind_stats_essendon.json` |
> | Side-by-side wind integrity | \_ | [`weather_integrity_essendon_vs_ro.json`](weather_integrity_essendon_vs_ro.json) |
>
> `wind_verdict.md` and `wind_distribution.png` are **kept, not deleted**: they
> are the evidence for why the weather file was replaced. Do not quote a number
> from them as a result.
>
> The canonical numbers on the clean file are in
> [`../au_canonical_essendon/`](../au_canonical_essendon/). Everything below this
> box was written against the RO file and is retained as the record of how the
> defect was found.

Five items, run diagnostic-first. **No engine code was modified and no published
result was overwritten**, except the Item 5 chart, which Item 5 asked to be
regenerated. Three findings are defects that are logged, not fixed.

| Item | Report | Verdict |
| --- | --- | --- |
| 1 | [`baseline_reconciliation.md`](baseline_reconciliation.md) | **Resolved.** Cause is the **building input**, not weather/schedule/commit. Canonical baseline: **1 308.60 / 741.83 kWh**. |
| 2 | — | **Does not trigger.** Scoped to Item 1 verdict (b); the gain and solar hourly hashes match exactly, so there is no schedule offset. |
| 3 | [`sankey_residual_by_state.md`](sankey_residual_by_state.md) | **All six states FAIL the 5 % V2 tolerance.** Step 3 improves the residual by 66.6 kWh — exactly the phantom ground term — against a gap of 450–5 066 kWh. |
| 4 | [`latent_breakdown.md`](latent_breakdown.md) | **Not a C2 regression** (latent heating 0.03 kWh, holds throughout). The ~554 kWh is latent *cooling*, but **ungated**: 99.6 % charged with the cooling plant off. |
| 5 | `../au_corrections_summary/au_corrections_summary.png` | **Rebuilt** as six faceted panels, one axis per metric, with title, axis labels, state labels and legend. |

## The three headline findings

1. **The two "unmodified baselines" differ in the building dictionary, not the
   engine.** Both published runs were reproduced **bit-exactly (Δ = 0.0)** from a
   single engine commit by changing one field: five party surfaces typed
   `"opaque"` vs `"adjacent"`. Typed `"opaque"` with `sky_view_factor: 0`, the
   core classifies them **`GR` — slab-on-ground**, giving this third-floor
   apartment 75.10 m² of buried envelope, its ceiling included. Weather,
   setpoints, internal-gain series and solar series are bit-identical between
   the two runs.

   *Consequence for the paper:* the harness Baseline is an unmodified **engine**
   but not the same **model**. The difference is a **model-input correction**,
   and must be named separately from the engine corrections C1–C4.

2. **The Sankey balance does not close in any state, and the ground fix was never
   able to close it.** The `ADJ` surface class — 75.10 m², **88.6 % of envelope
   UA** — appears **nowhere** in the Sankey inventory. `Q_tr_total` is exactly
   `Q_tr_opaque + Q_tr_window`; the party surfaces contribute zero to reported
   transmission on either side. That is the unaccounted term, and it is the next
   thing to fix.

3. **~79 % of the headline 34.85 kWh/m²·yr is ungated latent cooling.**
   Dehumidification is charged in 8 757 of 8 760 hours, of which 99.6 % occurs
   while the cooling plant is off and 6 129 hours have zone air below 20 °C.
   Sensible-only the building is **7.17 kWh/m²·yr**; with latent gated to cooling
   operation, **7.29**. All three numbers are defensible readings of the same
   run, so the definition has to be stated.

## Stale artefacts — flagged, not edited

Everything produced before 2026-07-28 10:25 used the mis-specified building:
`results/baseline_vs_ep/`, `results/ventilation_latent/`,
`corrected_weather_results_rewrite.tex`, and the EnergyPlus alignment audit's
claim that the ISO side modelled the neighbours as ISO 13789 buffers (it did
not — they were `GR`). No `.tex` file was touched.

## Reproducing

```bash
# Item 1 — one engine, two building dictionaries
python tools/diagnostics/probe_baseline.py --src <baseline-worktree>/pybuildingenergy/src \
    --bui-dir <dir containing apt305_building.py> \
    --epw weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw --out A.json

# Items 3 and 4 — six states, residual + latent columns
python tools/diagnostics/six_state_diagnostics.py --repair-ground-nan \
    --weather weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw \
    --out results/diagnostics/six_state_raw.json

# Item 5 — chart, from the canonical numbers
python tools/diagnostics/make_comparison_chart.py
```

`--repair-ground-nan` is a **measurement device, not a model change**: after Step 3
`_ground_contact_area()` correctly returns 0, but `Temp_calculation_of_ground`
still divides by it (`utils.py:3946`), so `Theta_gr_ve` is ±inf and
`q_ground = 0.0 * inf = NaN` latches into the Sankey input accumulator. Heating,
cooling and latent are bit-identical with and without it.
