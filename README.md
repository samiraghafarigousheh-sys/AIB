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

```bash
python examples/compare_branches_apt305.py                      # bundled stand-in weather
python examples/compare_branches_apt305.py --weather MEL.epw    # site-correct
python examples/compare_branches_apt305.py --weather-source pvgis
```

| File | Contents |
| --- | --- |
| `examples/apt305_building.py` | Building definition only — no engine import, so one dictionary feeds every engine version |
| `examples/compare_branches_apt305.py` | Checks out each branch into a throwaway worktree, runs it in its own subprocess, emits table + chart |
| `results/apt305/` | Committed outputs: `comparison.csv`, `comparison.md`, `apt305_comparison.png` |

Each branch runs in a **separate process** because three versions of the same
`pybuildingenergy` package cannot coexist on one `sys.path`. The building always
comes from the current branch, so the engine is the only thing that varies.

> **Weather caveat.** The proxy in this environment blocks PVGIS and every EPW
> mirror, so no Melbourne TMY could be obtained. The committed run uses the
> bundled **Athens** EPW (lat +37.97) as a stand-in for Melbourne (lat −37.80):
> nearly the mirror latitude, so solar-geometry magnitude and the wind regime are
> close — but the seasons are inverted and Athens is warmer. **The committed
> numbers are therefore not Melbourne results.** Re-run with `--weather` pointing
> at a Melbourne TMY, or `--weather-source pvgis`, for site-correct figures. Note
> that when an EPW is supplied the engine takes latitude from the *file*, not from
> the building dictionary.

## Reference case

Diffing any two branches on the same weather file and building object gives the
isolated impact of the change that separates them. Because the baseline branch is
byte-identical to upstream, absolute validation against upstream published results
remains possible at any point.
