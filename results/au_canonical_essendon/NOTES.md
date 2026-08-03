# The canonical run on the clean weather file

Re-run of the established ten-state canonical trajectory with **no engine change
of any kind**. The only difference from the previous canonical run is the weather
input.

| | |
| --- | --- |
| Case | Apt 305, 50 Barry St, Carlton VIC (`examples/apt305_building.py`) |
| Weather | `weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw` |
| Station | Melbourne-Essendon Fields, WMO 958660, lat −37.7275, lon 144.9067, tz +10 |
| Supersedes | `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw` (Melbourne Regional Office, WMO 948680) |
| Engine | HEAD, unchanged — the final trajectory state is byte-for-byte identical to it |

## Why the weather file changed

The RO file is site-correct — 0.008° from the building, closer than Essendon — and
still unusable. Four whole calendar months of its wind column (January, March,
July, September; 2,952 h, 33.7 % of the year) read exactly 0.0 m/s, because the
Melbourne Regional Office station's record ends in 2014 and the TMYx composite
zero-filled the gap. The EPW's own missing-value code for wind (999) appears
nowhere in the file, so nothing marks those hours as absent.

Correction C2 replaces the ISO fixed external convective coefficient with
`h_ce = 4v + 4`, which collapses to 4 W/(m²·K) at v = 0 against the ISO
constant's 20. The fabricated calms therefore weakened the external film of the
one exposed surface five-fold, drove its sol-air temperature up, and manufactured
cooling. 96 % of the C2 cooling increase came from those hours.

Essendon Fields is ~8 km NW of the site, has a complete continuous record, and
passes the wind-integrity screen: 8,760 rows, 0 missing wind values, annual mean
4.84 m/s, 1.58 % of hours exactly 0.0, 59.8 % above the 4 m/s pivot, no dead-calm
month. The screen is now enforced (`tools/diagnostics/weather_integrity.py`) —
a run on a file with a dead-calm month aborts.

## The new canonical headline

**172.82 kWh sensible heating + 6.34 kWh sensible cooling + 0.78 kWh gated latent
= 179.95 kWh = 9.00 kWh/m²·yr** over 20 m².

Against the superseded run, same engine and same building:

| Metric | RO (corrupt wind) | Essendon (clean) | Δ | Δ % |
| --- | ---: | ---: | ---: | ---: |
| Sensible heating (kWh) | 122.69 | 172.82 | +50.13 | +40.9 % |
| Sensible cooling (kWh) | 67.12 | 6.34 | −60.78 | −90.6 % |
| Gated latent cooling (kWh) | 3.98 | 0.78 | −3.20 | −80.4 % |
| Total (kWh) | 193.79 | 179.95 | −13.84 | −7.1 % |
| **Total (kWh/m²·yr)** | **9.69** | **9.00** | **−0.69** | **−7.1 %** |

Cooling changed most, as expected, and through C2. In the trajectory the C2 step
now moves sensible cooling **−25.30 kWh** (606.07 → 580.77); on the RO file the
same step moved it **+119.58 kWh**. The sign flipped because the physics did:
with 59.8 % of hours above the pivot, `4v + 4` sits *above* 20 W/(m²·K) for most
of the year rather than collapsing to a fifth of it, so a stronger external film
sheds more of the absorbed solar from the west wall (absorptance 0.75) back to
the air instead of conducting it inward.

The headline total moved only −7.1 % because heating rose while cooling fell:
Essendon is windier and slightly cooler, so the building loses more heat in
winter and gains less in summer. This is a small apartment with one exposed
façade — heating dominates on either file.

## The gate

| Condition | Result |
| --- | :-: |
| V2 residual < 5 % on every one of the ten states | **PASS** (worst −1.94 % at *+Conditioned zones*; machine-zero from *+Ground contact* on) |
| ADJ transmission in the inventory: 7 line items, every state | **PASS** |
| Independent re-integration of per-surface flows within 0.1 % | **PASS** (0.0000 % on every state) |
| Latent gated: nothing charged with the plant off or while heating | **PASS** (0.000000 kWh on both, every state) |
| Latent heating at the canonical state | **0.0000 kWh** |
| Southern-hemisphere phase of gated latent cooling | **PASS** (Dec–Feb 0.72 kWh vs Jun–Aug 0.00 kWh) |
| HEAD invariant under the reordering | **PASS** (Δ = 0.00e+00 on all four metrics) |
| Final engine tree identical to HEAD | **PASS** (byte-for-byte, every `.py` under `pybuildingenergy/src/`) |
| Regression suite | **PASS** — see `pytest.txt` |

HEAD invariance is now checked against **HEAD run on the same weather file**
rather than against a stored constant. A stored constant would assert "this
reproduces the number we published on the RO file", which is false by design here
and says nothing about whether the corrections are separable. The live comparison
asserts the property the harness exists to test, on any weather file.

## Files

| File | Contents |
| --- | --- |
| `comparison.csv` / `comparison.md` | the ten-state trajectory, all metrics, the gate, and the before/after contrast |
| `au_canonical_trajectory_essendon.png` | faceted chart, one axis per metric |
| `trajectory_raw.json` | raw floats, per-state provenance, the HEAD reference run |
| `pytest.txt` | the regression suite on this configuration |

## Reproducing

```bash
python tools/diagnostics/weather_integrity.py \
    weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw \
    weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw --no-assert

python tools/diagnostics/canonical_trajectory.py \
    --weather weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw \
    --outdir results/au_canonical_essendon

python tools/diagnostics/make_closed_balance_chart.py \
    --raw results/au_canonical_essendon/trajectory_raw.json \
    --outdir results/au_canonical_essendon \
    --stem au_canonical_trajectory_essendon \
    --title "Apt 305, 50 Barry St Carlton — the canonical trajectory in methodology order, on the clean weather file"

python -m pytest tests/ -v -rs
```

The trajectory needs every engine branch present locally
(`git fetch origin '+refs/heads/*:refs/remotes/origin/*'`); two test modules
build worktrees from those branches and skip without them.

Add `--from-raw` to `canonical_trajectory.py` to rebuild the report from
`trajectory_raw.json` without re-running the engine. It cannot change a number —
every number is read back from that file.
