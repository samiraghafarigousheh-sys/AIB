# Process run order

> **The weather file has changed since this document was written, so re-running
> these commands will not reproduce the numbers below.** They were produced on
> `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`, which was later found to have
> four calendar months of identically-zero wind (the station's record ends in
> 2014). The case study now resolves to
> `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`
> (`CANONICAL_EPW` in `examples/weather_melbourne.py`), and a file with a
> dead-calm month is refused outright. To reproduce the figures below as
> historical output, pass both
> `--weather weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw` and
> `--allow-degenerate-wind` — the second is required because the first is the
> file the screen exists to catch.
>
> The current canonical numbers, and what they supersede, are in
> [`results/au_canonical_essendon/`](results/au_canonical_essendon/) — see
> `SUPERSEDED.md` there.

The four steps, in order, with the commands that produce each one. Every command
below was run end to end on `AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`
(Melbourne Regional Office, 0.008° from the building) and the numbers quoted are
that run's actual output.

Run everything from the repository root on **`main`**. `main` is the harness
branch: it carries all four example scripts, the notebook and the correct EPW.
The engine branches are checked out into throwaway git worktrees by the
comparison scripts themselves — you never work from one directly.

## Setup

```bash
git clone --branch main https://github.com/samiraghafarigousheh-sys/AIB.git
cd AIB
git fetch origin '+refs/heads/*:refs/remotes/origin/*'   # worktrees need every engine branch
git config user.email you@example.com                    # worktree add needs an identity
git config user.name  you

python3 -m venv .venv
.venv/bin/pip install -r pybuildingenergy/requirements.txt
```

> Use a virtualenv. Installing into a Debian/Ubuntu system Python fails while
> building the `pymeeus` wheel (`AttributeError: install_layout`, a
> distutils/setuptools clash in the distro packaging, not in this repo).

EnergyPlus 24.1, needed for step 1 only:

```bash
wget -qO /tmp/ep.tar.gz https://github.com/NREL/EnergyPlus/releases/download/v24.1.0/EnergyPlus-24.1.0-9d7789a3ac-Linux-Ubuntu22.04-x86_64.tar.gz
mkdir -p /opt/ep && tar -xzf /tmp/ep.tar.gz -C /opt/ep --strip-components=1
/opt/ep/energyplus --version      # EnergyPlus, Version 24.1.0-9d7789a3ac
```

The weather file needs no setup — it ships in `weather_cache/` and every script
picks it up automatically. Pass `--weather weather_cache/*.epw --require-epw` to
pin it explicitly and forbid the PVGIS fallback.

---

## Step 1 — Original engine vs EnergyPlus, and the Sankey

```bash
.venv/bin/python examples/baseline_vs_energyplus.py --audit-only
.venv/bin/python examples/baseline_vs_energyplus.py --energyplus /opt/ep/energyplus
```

The audit runs no simulation. It is the substance of this step, not a preamble:
several ISO behaviours are invisible in the building dictionary, and three of
them dominate the comparison — internal gains ignore the dictionary's
`full_load` values (52.8 W/m² is used, not 16), neighbours are ISO 13789
*unconditioned buffers* that mostly track outdoor air rather than rooms at 21 °C,
and control is on operative temperature, not air temperature.
**22 parameters checked: 10 already aligned, 9 corrected, 3 irreducible.**

Result:

| Metric | ISO 52016-1 | EnergyPlus | diff | diff % |
| --- | ---: | ---: | ---: | ---: |
| Heating | 15.9 | 766.2 | +750.4 | +4730.7 % |
| Cooling | 2,027.5 | 900.4 | −1,127.1 | −55.6 % |
| Total | 2,043.4 | 1,666.7 | −376.7 | −18.4 % |

The ISO engine also reports 301.2 kWh of latent load separately; the EnergyPlus
cooling figure is sensible-only (`ConstantSupplyHumidityRatio`), so the two
columns are comparable.

Outputs in `results/baseline_vs_ep/`:

| File | Contents |
| --- | --- |
| `baseline_vs_energyplus.csv` / `.md` | the table above |
| `baseline_vs_energyplus.png` | bar chart |
| `sankey_pybuildingenergy.png` | ISO annual energy balance — use this one in a notebook |
| `sankey_pybuildingenergy.html` | interactive plotly version |
| `iso_results.json` | raw ISO result, so a notebook can rebuild the Sankey without re-running |
| `apt305.idf` | the generated EnergyPlus input |
| `run_meta.json` | the weather file this run actually used |

Sankey, in 6,779 kWh / out 6,779 kWh: internal gains 5,357 (79 %) and solar 820
(12 %) in; ventilation loss 2,829 (42 %) and cooling extracted 2,028 (30 %) out.
The balance does not close exactly and the gap is drawn rather than hidden —
**residual 703 kWh (10 %)**. ISO 52016-1 is a node network, not one lumped air
node: gains are split between the air node and the surface nodes, which then
exchange with each other, so the air-node paths summed here need not add up.

---

## Steps 2 and 3 — the window changes, one at a time

```bash
.venv/bin/python examples/compare_branches_apt305.py
```

| Column | Branch | Engine |
| --- | --- | --- |
| Baseline | `claude/pybuildingenergy-baseline-anjro8` | unmodified ISO 52016-1 |
| + Window | `claude/dynamic-window-properties-anjro8` | + dynamic window properties |
| + Window + h_ce | `claude/window-plus-dynamic-hce-anjro8` | …+ wind-dependent transmittance on every surface |

Result:

| Metric (kWh) | Baseline | + Window | + Window + h_ce | C1 vs base | C2 vs C1 | C2 vs base |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Heating need | 15.9 | 13.9 | 14.1 | −12.48 % | +1.25 % | −11.39 % |
| Cooling need | 2,027.5 | 2,029.3 | 2,253.3 | +0.09 % | +11.04 % | +11.14 % |
| Solar gains | 819.6 | 718.2 | 718.2 | −12.37 % | 0.00 % | −12.37 % |
| Window transm. loss | 593.1 | 527.0 | 527.1 | −11.15 % | +0.02 % | −11.14 % |
| Opaque transm. loss | 433.6 | 441.5 | 439.5 | +1.84 % | −0.45 % | +1.37 % |
| Total transm. loss | 1,005.2 | 951.3 | 946.8 | −5.36 % | −0.47 % | −5.81 % |

The first column is the engine with no change at all, and it is bit-identical to
the ISO column of step 1 — asserted, not assumed; see the cross-check below.

Outputs in `results/apt305/`: `comparison.csv`, `comparison.md`,
`results.json` (raw floats), `apt305_comparison.png`, `run_meta.json`.

### One caveat on the middle column

`+ Window` is **not** the solar-angle correction on its own. That branch changes
two things at once:

1. the angular correction factor `F_W(θ)` applied to transmitted solar, and
2. a wind-dependent thermal transmittance on the **windows**.

`+ Window + h_ce` then extends that same wind-dependent transmittance to the
**opaque** envelope. So the progression is *window angle + window transmittance*
→ *…+ opaque transmittance*, not *window angle* → *window angle + transmittance*.

Both halves are switchable, so the angle effect can be isolated without touching
the branch structure. Run the engine with `window_convection_model="table"` to
keep the ISO constant film on the glazing and leave only the angular correction —
that is the true *window angle alone* case. `window_angular_solar_model="none"`
gives the complement.

---

## Step 4 — back to the original engine, plus ventilation and latent heat

```bash
.venv/bin/python examples/compare_ventilation_latent.py
```

This is a **separate** layering from steps 2–3. It does not stack on the window
branches — it starts again from the unmodified baseline.

| Column | Branch | Engine |
| --- | --- | --- |
| Base | `claude/pybuildingenergy-baseline-anjro8` | unmodified ISO 52016-1 |
| C1 | `claude/ventilation-infiltration-fix` | + ventilation / infiltration fix |
| C2 | `claude/latent-heat-fix` | + latent heat fix |
| C3 | `claude/ventilation-plus-latent-fix` | both together |

Result:

| Metric (kWh) | Base | C1 | C2 | C3 | C1 vs Base | C2 vs Base | C3 vs Base |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Heating need | 15.9 | 37.3 | 15.9 | 37.3 | +135.39 % | 0.00 % | +135.39 % |
| Cooling need | 2,027.5 | 1,727.2 | 2,027.5 | 1,727.2 | −14.81 % | 0.00 % | −14.81 % |
| Ventilation+infilt. loss | 2,829.3 | 3,235.4 | 2,829.3 | 3,235.4 | +14.36 % | 0.00 % | +14.36 % |
| Latent cooling need | 301.2 | 416.4 | 290.8 | 305.5 | +38.23 % | −3.46 % | +1.43 % |
| Latent heating need | 1,431.0 | 1,181.7 | 1.0 | 0.8 | −17.42 % | −99.93 % | −99.95 % |
| Total energy need | 3,775.6 | 3,362.6 | 2,335.2 | 2,070.8 | −10.94 % | −38.15 % | −45.15 % |

The two fixes separate cleanly on the sensible side and interact on the latent
side. C2 moves **no** sensible metric at all — 0.00 % on heating, cooling and
ventilation loss — so the whole sensible effect (+135 % heating, −15 % cooling)
is the ventilation fix. The −99.9 % collapse in phantom humidification demand is
just as clearly the latent fix, which replaces the baseline's flat 50 % RH
reference with the EN 16798-1 deadband; C1 also moves that figure (−17.4 %), but
indirectly, by changing the air-exchange rate that feeds the moisture balance.
Latent cooling is where the two genuinely interact: C1 alone +38.2 %, C2 alone
−3.5 %, both together +1.4 % — not the sum of the parts.

*Latent heating need* and *Total energy need* are derived in the comparison
script rather than read from the engine: upstream exposes latent heating only as
an hourly column and never sums the three demands, and adding them to the annual
aggregation would mean editing the baseline, which must stay byte-identical to
upstream. They are computed from columns present on all four branches, so every
variant is measured by the same definition.

Outputs in `results/ventilation_latent/`: `comparison.csv`, `comparison.md`,
`ventilation_latent_comparison.png`, `run_meta.json`.

---

## Cross-check

Steps 1 and 2–3 both drive the unmodified engine on the same building, so their
baseline figures must be identical.

```bash
.venv/bin/python examples/check_baseline_consistency.py
```

```
weather actually used
  compare_branches      : AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw — Melbourne.RO
  baseline_vs_energyplus: AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw — Melbourne.RO

Metric          compare_branches    baseline_vs_EP     rel. diff
----------------------------------------------------------------
Heating                15.861617         15.861617      0.00e+00
Cooling             2,027.506478      2,027.506478      0.00e+00

PASS  both harnesses report the same baseline engine result.
```

It compares the weather each run recorded in `run_meta.json` **before** comparing
any numbers, so a weather mismatch is reported as a weather mismatch rather than
as a physics bug. That distinction is why the script exists: two charts once
disagreed by 4× on heating with the same engine and the same building, because
one run had fallen back to a PVGIS TMY and the other used an EPW.

Both sides are read from raw-float JSON (`results.json` and `iso_results.json`),
not from the rounded tables. Comparing the tables instead puts 15.8616 against
15.861617 — 1.05e-6 apart, over the 1e-6 tolerance, and the check reports a
rounding artefact as a harness discrepancy. If only the CSVs are available the
script says so and loosens the tolerance to 1e-4 rather than failing.
