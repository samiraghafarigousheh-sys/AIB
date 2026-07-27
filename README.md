# AIB

Research fork of the **pyBuildingEnergy** ISO 52016-1 building energy engine, used to
quantify the effect of individual physics improvements on predicted energy demand.

## Layout

| Path                | Contents                                                            |
| ------------------- | ------------------------------------------------------------------- |
| `pybuildingenergy/` | Vendored upstream engine — see [VENDORING.md](VENDORING.md)          |
| `VENDORING.md`      | Upstream provenance and verification procedure                       |
| `CHANGES.md`        | Log of physics modifications (added on the modification branches)    |

## Branch structure

Changes are layered one at a time so the effect of each can be isolated by
re-running the same example against successive branches.

| Branch                                     | Contents                                       |
| ------------------------------------------ | ---------------------------------------------- |
| `main`                                     | Repository root / README only                  |
| `claude/pybuildingenergy-baseline-anjro8`  | Unmodified upstream engine (reference case)    |
| `claude/dynamic-window-properties-anjro8`  | Baseline **+ change 1**: dynamic window properties |
| `claude/window-plus-dynamic-hce-anjro8`    | Change 1 **+ change 2**: wind-dependent surface heat transfer coefficients |

Each modification branch is a strict superset of the one above it, so a
difference between two adjacent branches isolates exactly one change.

## Worked example — Apt 305, 50 Barry St, Carlton

A 20 m² Melbourne apartment with a single exposed (west) facade, five conditioned
neighbours, zeroed thermal mass and ideal loads.

### Run it in Google Colab

Open `notebooks/AIB_apt305_colab.ipynb`, or paste this single cell into a blank
notebook:

```python
!git clone --quiet --branch claude/window-plus-dynamic-hce-anjro8 \
    https://github.com/samiraghafarigousheh-sys/AIB.git AIB
%cd AIB
!git fetch --quiet origin '+refs/heads/*:refs/remotes/origin/*'
!git config user.email colab@example.com && git config user.name Colab
!pip install -q -r pybuildingenergy/requirements.txt
!python examples/compare_branches_apt305.py --outdir results/apt305

import pandas as pd
from IPython.display import Image, display
display(pd.read_csv("results/apt305/comparison.csv"))
display(Image("results/apt305/apt305_comparison.png"))
```

Repository: `https://github.com/samiraghafarigousheh-sys/AIB.git`
Branch: `claude/window-plus-dynamic-hce-anjro8`
If the repo is private, clone with a personal access token:
`https://<TOKEN>@github.com/samiraghafarigousheh-sys/AIB.git`

### Baseline vs EnergyPlus

`examples/baseline_vs_energyplus.py` runs the **unmodified** engine against
EnergyPlus 24.1 on the same building, weather and schedules. It builds the IDF
from `apt305_building.py`, so there is one source of truth for the inputs.

```bash
# install EnergyPlus, then
python examples/baseline_vs_energyplus.py --audit-only          # alignment table + IDF
python examples/baseline_vs_energyplus.py --energyplus /opt/ep/energyplus
```

It prints a **parameter alignment audit** before running. That audit is the
point of the script: several ISO behaviours are invisible in the building
dictionary, and the first three below dominate the comparison.

| Finding | Detail |
| --- | --- |
| **Internal gains ignore `full_load`** | `internal_gains()` returns ISO 16798-1 tabulated `q_int` for `building_type_class` × `a_use`, plus the neighbours' transferred gains. The dictionary says 16 W/m²; the engine uses **52.8 W/m²** (occupants 30.8, appliances 22.0, lighting **0.0**). Only the *profiles* are taken from the dictionary. |
| **Neighbours are unconditioned buffers, not conditioned rooms** | `θ_ztu = (1−b_ztu)·θ_int + b_ztu·T_out`, with b_ztu = 0.73–0.93 here — so they mostly track **outdoor** air. Pinning them at a fixed 21 °C in EnergyPlus (as a naive IDF does) changes total energy by ~40×. |
| **Control is on operative temperature** | ISO controls 0.5·T_air + 0.5·MRT; an EnergyPlus thermostat defaults to zone **air** temperature, which ran ~2 K cooler. |
| **Declared window shading does nothing** | The 0.25 m overhang on both windows produces a shading factor of exactly **1.0000 for all 8760 hours**. The `W_*` columns are emitted, but no shading is ever applied — so `shading: True` in the building dictionary is silently inert here. |

**Cross-check.** The ISO figures in this comparison are bit-identical to the
`Baseline` column of `compare_branches_apt305.py`, confirming both harnesses
drive the same unmodified engine with the same inputs. On the bundled Melbourne
Regional Office TMYx that is 15.862 kWh heating and 2027.506 kWh cooling in both,
and `examples/check_baseline_consistency.py` asserts it:

```bash
python examples/check_baseline_consistency.py
# Heating   15.861617   15.861617   0.00e+00
# Cooling 2,027.506478 2,027.506478  0.00e+00
# PASS  both harnesses report the same baseline engine result.
```

> **The two harnesses did once disagree** — 150 kWh heating on one chart against
> 40 kWh on the other. Neither the engine nor the building was at fault: one run
> had fallen back to a PVGIS TMY while the other used an EPW, because
> `resolve()` degrades silently through cached EPW → download → PVGIS. Same
> engine, same building, *different weather*.
>
> Both scripts now write `run_meta.json` next to their outputs recording the
> file actually used, `check_baseline_consistency.py` compares that **before**
> comparing numbers, and `--require-epw` refuses the PVGIS fallback outright for
> any run that has to line up with an EnergyPlus run.

### Sankey — where the ISO energy actually goes

`baseline_vs_energyplus.py` also writes an annual energy-balance Sankey for the
ISO side, built from the engine's own `Q_*_loss_kWh` / `Q_*_gain_kWh` columns:

| Output | Notes |
| --- | --- |
| `sankey_pybuildingenergy.png` | matplotlib; displays anywhere, including Colab |
| `sankey_pybuildingenergy.html` | plotly, interactive; written only if plotly is installed |
| `iso_results.json` | the raw ISO result, so a notebook can rebuild the Sankey without re-running the engine |

The PNG is the one to use in a notebook. A plotly HTML file cannot be shown with
`IFrame(src=...)` — Colab runs no web server on that path, which is what produces
*localhost refused to connect*; render the figure object with `fig.show()` instead.

The balance does not close exactly, and the gap is shown rather than hidden.
ISO 52016-1 is a node network, not one lumped air node: gains are split between
the air node and the surface nodes, which then exchange with each other, so the
air-node paths summed here need not add up. On the bundled EPW that residual is
about 10 %.

The script corrects the first three — probing the engine for its real gain
magnitudes and b_ztu values, then building the IDF from them — plus the frame
fraction, surface film coefficient, radiant split, internal capacitance,
thermostat control type, daylight saving and day-of-week.

**22 parameters checked: 10 already aligned, 9 corrected, 3 irreducible**
(timestep, solar distribution, and the surface heat transfer algorithm).

### Run it locally

```bash
python examples/compare_branches_apt305.py                        # auto-resolve Melbourne weather
python examples/compare_branches_apt305.py --weather MEL.epw      # explicit EPW (validated)
python examples/compare_branches_apt305.py --weather-source pvgis # TMY at the building's coords
```

| File | Contents |
| --- | --- |
| `examples/apt305_building.py` | Building definition only — no engine import, so one dictionary feeds every engine version |
| `examples/weather_melbourne.py` | Weather resolution, the site-validation guard, and `run_meta.json` recording |
| `examples/compare_branches_apt305.py` | Checks out each branch into a throwaway worktree, runs it in its own subprocess, emits table + chart |
| `examples/baseline_vs_energyplus.py` | Baseline ISO vs EnergyPlus: alignment audit, table, bar chart, Sankey |
| `examples/check_baseline_consistency.py` | Asserts both harnesses report the same baseline result, weather first |
| `notebooks/AIB_apt305_colab.ipynb` | Colab notebook |
| `weather_cache/` | Bundled EPW, so every run uses the same weather with nothing to download |
| `results/apt305/` | Outputs, written on each run |

Each branch runs in a **separate process** because three versions of the same
`pybuildingenergy` package cannot coexist on one `sys.path`. The building always
comes from the current branch, so the engine is the only thing that varies.

### Weather: why there is a guard

The engine takes its coordinates from **two different places** depending on the
source, and getting it wrong is silent:

| Source | Coordinates come from |
| --- | --- |
| `weather_source="epw"` | the **EPW header** — the building dictionary's `latitude` is ignored |
| `weather_source="pvgis"` | the **building dictionary** — site-correct by construction |

So handing the Melbourne apartment an Athens EPW simulates it in Athens, with no
warning. `examples/weather_melbourne.py` grades the distance in two bands:
within **1.5°** is greater-Melbourne and silent; **1.5–2.5°** is a regional
Victorian station — a genuinely different climate, so it is accepted but
announced and the station name is carried onto every chart; beyond **2.5°** it is
another region and is refused:

```
EPW site mismatch:
  file    : 2020_Athens.epw
  station : Athinai at lat 37.967, lon 23.717
  building: Melbourne at lat -37.800, lon 144.968
  offset  : 143.0 deg (limit 2.5)
```

The EPW bundled in `weather_cache/` is
`AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025` — Melbourne Regional Office, at
lat −37.8075, lon 144.970. That is **0.008°** from the building's own
coordinates, so it lands well inside the silent band and every chart is simply
labelled *Melbourne.RO*.

> Earlier revisions of this repo bundled `AUS_VIC_Charlton.948390_TMYx.2009-2023`
> instead, which sits 2.0° inland and therefore ran in the announced band. Inland
> Charlton has both colder winters and hotter summers than the coast, so it
> overstated demand at both ends: baseline heating was 85.472 kWh against
> 15.862 kWh on the true site, and cooling 2539.262 against 2027.506. Any figure
> quoted from a run before that swap is on Charlton, not Melbourne.

`--allow-site-mismatch` overrides it deliberately; results are then labelled with
the EPW's own location.

Resolution order is: explicit `--weather` (validated) → cached EPW under
`weather_cache/` → download from public TMY mirrors → PVGIS at the building's own
lat/lon. If none is reachable the run **fails with instructions** rather than
substituting another city.

That fallback chain is convenient and was also the source of the harness
disagreement above, so every run records its choice in `run_meta.json`, and
`--require-epw` turns the PVGIS step off for runs that must stay comparable with
EnergyPlus.

## Reference case

Diffing any two branches on the same weather file and building object gives the
isolated impact of the change that separates them. Because the baseline branch is
byte-identical to upstream, absolute validation against upstream published results
remains possible at any point.
