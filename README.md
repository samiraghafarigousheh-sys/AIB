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

### Run it locally

```bash
python examples/compare_branches_apt305.py                        # auto-resolve Melbourne weather
python examples/compare_branches_apt305.py --weather MEL.epw      # explicit EPW (validated)
python examples/compare_branches_apt305.py --weather-source pvgis # TMY at the building's coords
```

| File | Contents |
| --- | --- |
| `examples/apt305_building.py` | Building definition only — no engine import, so one dictionary feeds every engine version |
| `examples/weather_melbourne.py` | Weather resolution + the site-validation guard |
| `examples/compare_branches_apt305.py` | Checks out each branch into a throwaway worktree, runs it in its own subprocess, emits table + chart |
| `notebooks/AIB_apt305_colab.ipynb` | Colab notebook |
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
warning. `examples/weather_melbourne.py` now rejects any EPW more than 1.5° from
the building's coordinates:

```
EPW site mismatch:
  file    : 2020_Athens.epw
  station : Athinai at lat 37.967, lon 23.717
  building: Melbourne at lat -37.800, lon 144.968
  offset  : 143.0 deg (limit 1.5)
```

`--allow-site-mismatch` overrides it deliberately; results are then labelled with
the EPW's own location.

Resolution order is: explicit `--weather` (validated) → cached EPW under
`weather_cache/` → download from public TMY mirrors → PVGIS at the building's own
lat/lon. If none is reachable the run **fails with instructions** rather than
substituting another city.

> **No results are committed.** This sandbox blocks PVGIS, `climate.onebuilding.org`
> and every EPW mirror (only `raw.githubusercontent.com` is reachable), so no
> Melbourne TMY could be obtained here and no Melbourne figures have been produced.
> The pipeline itself is verified end to end; run the Colab notebook, which has open
> network, to generate real Melbourne numbers.

## Reference case

Diffing any two branches on the same weather file and building object gives the
isolated impact of the change that separates them. Because the baseline branch is
byte-identical to upstream, absolute validation against upstream published results
remains possible at any point.
