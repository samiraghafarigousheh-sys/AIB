# What this run supersedes

Every published figure computed on
`AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw` is superseded. The engine is
unchanged; the weather input is not. Nothing listed here has been edited or
deleted — the superseded artefacts are the record of how the defect was found,
and the RO file itself is kept in `weather_cache/` for the before/after
contrast. **No `.tex` file was touched.**

For orientation: no `.tex` source is present in this repository, so the mapping
below is by *content* — what the number is — rather than by line. Whoever holds
the manuscript should match on the values.

## 1. The headline

| | Superseded | Current |
| --- | ---: | ---: |
| Sensible heating | 122.69 kWh | **172.82 kWh** |
| Sensible cooling | 67.12 kWh | **6.34 kWh** |
| Gated latent cooling | 3.98 kWh | **0.78 kWh** |
| Total | 193.79 kWh | **179.95 kWh** |
| **Per area** | **9.69 kWh/m²·yr** | **9.00 kWh/m²·yr** |

Any sentence quoting **9.69 kWh/m²·yr**, or the 122.69 / 67.12 / 3.98 split, is
superseded. Source of the new figures:
[`comparison.md`](comparison.md) §3, raw floats in `trajectory_raw.json`.

## 2. The trajectory table (drafted as Table 2)

The whole ten-state table moves. Every state's sensible heating, sensible
cooling, gated and ungated latent, totals and V2 residual change, because every
state is measured on the new weather. First and last rows, for identification:

| State | | Sensible H | Sensible C | Gated latent | Total | kWh/m²·yr |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | superseded | 1,308.60 | 741.83 | 55.76 | 2,264.18 | 113.21 |
| Baseline | **current** | **1,779.36** | **640.84** | **26.12** | **2,598.97** | **129.95** |
| +Closure fixes | superseded | 122.69 | 67.12 | 3.98 | 193.79 | 9.69 |
| +Closure fixes | **current** | **172.82** | **6.34** | **0.78** | **179.95** | **9.00** |

Replace from [`comparison.csv`](comparison.csv) / [`comparison.md`](comparison.md) §1.

Two structural changes to the table itself, beyond the values:

* A column **`Total, sensible + gated latent (kWh)`** is now reported alongside
  the engine's own `Total (kWh)`. They differ on the five states before the
  latent fix — by the 153–174 kWh of phantom humidification that `Total (kWh)`
  carries — and coincide from `+Latent` onward. If the drafted table's "total"
  column was described as sensible + gated latent, it was mislabelled for those
  five rows on the old file too; that is now explicit rather than implied.
* The corresponding chart panel was plotting the engine total under a
  "sensible + gated latent" title and now plots what the title says.

## 3. The C2 row, and anything said about wind-dependent h_ce

This is the largest qualitative change, and it is a reversal of sign.

| | Superseded (RO) | Current (Essendon) |
| --- | ---: | ---: |
| C2 step, in the trajectory | **+119.58 kWh** cooling | **−25.30 kWh** cooling |
| C2 switch, on the final engine | **+48.73 kWh** cooling | **−3.27 kWh** cooling |
| Share of that from exactly-zero wind | 96.3 % | 0.0 % |
| Verdict | **(c)** — not explained by real wind | **(a+b)** |

Any text describing C2 as *increasing* cooling, or as tripling it, is superseded
and now says the opposite: with 59.8 % of hours above the 4 m/s pivot,
`h_ce = 4v + 4` sits above the ISO fixed 20 W/(m²·K) for most of the year, so the
correction couples the west wall more tightly to outdoor air and *reduces*
cooling. Source: [`../diagnostics/wind_verdict_essendon.md`](../diagnostics/wind_verdict_essendon.md).

Any caveat paragraph stating that the C2 cooling figure rests on hours of
fabricated calm and must be resolved before the correction is defended — that
open item is **closed**, and the caveat should be replaced by the (a+b) finding
rather than deleted silently.

## 4. Tables 4/5 — the closed-balance six-state harness

`results/au_corrections_closed/six_state_closed.{csv,md}` was run on the RO file
and is superseded in the same way. Its `+Closure Fixes (HEAD)` row is the same
122.69 / 67.12 / 3.98 / 9.69 as above; its `+Hemisphere Fix` row is
123.39 / 20.06 / 2.29 / 7.29 kWh/m²·yr.

That harness was **not** re-run here — this task re-ran the canonical trajectory,
which measures the same final state through the same instrument and does so on
the clean file. If Tables 4/5 are built from the six-state harness rather than
from the trajectory, re-run it before quoting:

```bash
python tools/diagnostics/closed_balance_six_state.py \
    --weather weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw \
    --outdir results/au_corrections_closed_essendon \
    --closure-base 978db37
```

`--closure-base 978db37` is required: PR #16 merged three of the four closure
commits into `main`, so the tool's `origin/main` default now resolves to an
incomplete set and would measure nine states with an instrument the tenth does
not use. The canonical-trajectory tool pins this base already.

## 5. `corrected_weather_results_rewrite.tex`

Flagged as stale in `../diagnostics/README.md` before this run, for a different
reason (the mis-specified building). It is superseded again, and now doubly: it
was written against the RO weather. It should be redone against
`results/au_canonical_essendon/`, not patched.

## 6. Everything else on the RO file

Retained, unedited, and not to be quoted as a result:

| Directory | Status |
| --- | --- |
| `results/au_canonical/` | the same trajectory on the RO file — superseded by this directory |
| `results/au_corrections_closed/` | six-state closed balance, RO — see §4 |
| `results/diagnostics/wind_verdict.md`, `wind_distribution.png`, `wind_stats.json` | the verdict-(c) evidence; **keep** — it is why the file was replaced |
| `results/au_corrections_summary/`, `results/step_1_*` … `step_4_*` | earlier steps, RO weather and (for the older ones) the mis-specified building |

## What is *not* superseded

The engine, and every claim about it. No engine logic changed in this run: the
trajectory's final state is byte-for-byte identical to HEAD's tree, and HEAD run
directly on this weather reproduces the trajectory's final state to 0.00e+00 on
all four headline metrics. The methodology order, the closure fixes, the ADJ
transmission inventory (7 line items, re-integration 0.0000 %), the latent gate
(nothing charged with the plant off or while heating), the GR classification and
the southern-hemisphere phase all hold exactly as before — see
[`comparison.md`](comparison.md) §5–§8 and `pytest.txt` (198 passed, 0 skipped,
exit 0).
