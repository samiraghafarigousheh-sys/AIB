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

## Reference case

Diffing any two branches on the same weather file and building object gives the
isolated impact of the change that separates them. Because the baseline branch is
byte-identical to upstream, absolute validation against upstream published results
remains possible at any point.
