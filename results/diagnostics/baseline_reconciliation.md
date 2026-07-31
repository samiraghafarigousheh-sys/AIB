# Item 1 — Reconciliation of the two contradictory "unmodified baselines"

**Status:** resolved. **Verdict: none of (a), (b) or (c).** The two runs differ in a
fourth input the brief did not enumerate: **the building dictionary**
(`examples/apt305_building.py`). Weather, setpoints, internal-gain hourly series,
solar hourly series and engine commit are all *identical*.

**Canonical for the paper: the six-state harness baseline — 1 308.60 kWh heating /
741.83 kWh cooling** — but it must not be described as the same model as the earlier
one. See [§6](#6-which-baseline-is-canonical) for the wording this forces.

---

## 1. What was reproduced

Both published runs were re-executed **from one engine worktree**
(`claude/pybuildingenergy-baseline-anjro8` @ `2e6e910`), one EPW, and the two versions
of the building dictionary. Every published figure came back bit-exact:

| Metric | Config A repro | Published `baseline_vs_ep` | Δ |
| --- | ---: | ---: | ---: |
| `Q_H_annual_kWh` | 15.861616700444602 | 15.861616700444602 | **0.000e+00** |
| `Q_C_annual_kWh` | 2027.5064783087112 | 2027.5064783087112 | **0.000e+00** |
| `Q_latent_annual_kWh` | 301.24591042387095 | 301.24591042387095 | **0.000e+00** |
| `Q_internal_gains_kWh` | 5356.685952 | 5356.685952 | **0.000e+00** |
| `Q_ground_loss_kWh` | 192.4430473450749 | 192.4430473450749 | **0.000e+00** |
| `Q_ve_loss_kWh` | 2829.2671794379244 | 2829.2671794379244 | **0.000e+00** |

| Metric | Config B repro | Published harness `Baseline` | Δ |
| --- | ---: | ---: | ---: |
| `Q_H_annual_kWh` | 1308.601259174238 | 1308.601259174238 | **0.000e+00** |
| `Q_C_annual_kWh` | 741.828245796808 | 741.828245796808 | **0.000e+00** |
| `Q_internal_gains_kWh` | 5356.685952 | 5356.685952 | **0.000e+00** |
| `Q_ground_loss_kWh` | 90.19910378124511 | 90.19910378124511 | **0.000e+00** |
| `Q_ve_loss_kWh` | 1868.4845473364412 | 1868.4845473364412 | **0.000e+00** |

Where

* **Config A** = `examples/apt305_building.py` at `4376658^` — five party surfaces
  declared `type: "opaque"`.
* **Config B** = `examples/apt305_building.py` at `HEAD` — the same five surfaces
  declared `type: "adjacent"`.

**This single fact settles the question.** Both endpoints of the contradiction are
reachable from *one* engine commit by changing *one* field in the building input.
No weather, schedule or commit difference is needed to explain anything.

---

## 2. The five required runtime diffs

Instrumented at runtime (`probe_baseline.py`), reporting values actually loaded, not
values declared.

### 2.1 Resolved weather — **IDENTICAL**, hypothesis (a) ruled out

| | Config A | Config B |
| --- | --- | --- |
| Path actually opened | `/home/user/AIB/weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw` | *(same)* |
| Rows loaded | 8 760 | 8 760 |
| HDD18 | 1 345.10 °C·d | 1 345.10 °C·d |
| CDD18 | 544.55 °C·d | 544.55 °C·d |
| Annual GHI | 1 612.887 kWh/m² | 1 612.887 kWh/m² |
| `T2m` series sha256 | `dafa13323c24b9c4` | `dafa13323c24b9c4` |
| `G(h)` series sha256 | `bef108cf5880122d` | `bef108cf5880122d` |
| UTC offset / lat / lon | +10 / −37.8075 / 144.97 | +10 / −37.8075 / 144.97 |

The path was captured by wrapping `ISO52010.get_tmy_data_epw`, so this is the file the
reader actually opened. **Neither run fell back to PVGIS** — the PVGIS branch
(`get_tmy_data_pvgis`) was never entered, and a PVGIS series would not hash equal to an
8 760-row EPW read.

### 2.2 Setpoints applied — **IDENTICAL**

Both: `heating_setpoint 18.0`, `heating_setback 15.0`, `cooling_setpoint 26.0`,
`cooling_setback 28.0`. The two dictionaries are byte-identical in
`building_parameters.temperature_setpoints`, and neither `check_input.py` nor the
baseline engine contains any code that rewrites those keys — a grep for
`heating_setpoint`/`cooling_setpoint` in `check_input.py` returns nothing, and there is
**no NCC/2022 auto-derivation path anywhere in the baseline engine** (grep for
`ncc|auto.?deriv|2022` returns nothing). So 18/26 passes through unmodified in both.

*Caveat, stated rather than glossed:* the baseline engine exposes no hourly
setpoint column, so this is verified from the sanitised dictionary plus the absence of
any rewrite path, not from a captured 8 760-length array.

### 2.3 Internal-gain temporal profile — **BIT-IDENTICAL**, hypothesis (b) ruled out

| | Config A | Config B |
| --- | --- | --- |
| n | 8 760 | 8 760 |
| Σ | 5 356.685952 kWh | 5 356.685952 kWh |
| mean / min / max | 611.494 / 334.476 / 1 056.24 W | *(same)* |
| **sha256 of the 8 760-array** | **`1b4d58a0c10bcfd6`** | **`1b4d58a0c10bcfd6`** |
| hour-of-day distribution | — | identical elementwise |
| first 48 values | — | identical elementwise |

This is the test the brief identified as the leading candidate. **The hashes match.**
The gains are not merely equal in annual sum — they are the same number in the same
hour. There is no schedule offset between the two runs.

### 2.4 Solar temporal profile — **BIT-IDENTICAL**

| | Config A | Config B |
| --- | --- | --- |
| Σ | 819.5857298352444 kWh | 819.5857298352444 kWh |
| max | 730.113 W | 730.113 W |
| **sha256** | **`df637e9c3e159e3d`** | **`df637e9c3e159e3d`** |
| argmax hour-of-day | 16 | 16 |

Peak solar at hour-of-day 16 on a **west-facing** window is the physically correct
phase, in both runs. No timezone or EPW-convention shift.

### 2.5 Branch provenance — **IDENTICAL**, hypothesis (c) ruled out

`claude/pybuildingenergy-baseline-anjro8` contains exactly two commits:

```
2e6e910 2026-07-26 04:23:45 +0000  Vendor pyBuildingEnergy ISO 52016-1 engine (unmodified baseline)
efe88ef 2026-07-26 12:49:19 +1000  Initial commit
```

`utils.py` and `ventilation.py` have been touched by exactly one commit (`2e6e910`),
dated **two days before both runs**. Engine file digests at that commit:

```
utils.py       4bb04afb965b38043cd27f71c90bdc78afe4e1d3deb1a41e286ce734fde66c4a
ventilation.py f1d5bba848f9de55fc990389a9918aac4b01353a862eed502825dcab6b8f6464
```

Both harnesses (`baseline_vs_energyplus.py` and `compare_au_corrections.py`) resolve
that same branch name into a detached worktree at run time. The reproduction in §1
is the decisive evidence: **one engine produced both published results.**

---

## 3. What actually differs

`examples/apt305_building.py`, changed by commit
**`4376658` "Step 2 harness: type party surfaces as adjacent; mark neighbours
conditioned" (2026-07-28 10:25:02 +0000)**. Diffing the two dictionaries, the only
functional changes are:

1. Five party surfaces: `"type": "opaque"` → `"type": "adjacent"`.
2. Five adjacent zones gain `conditioned: True` + `setpoint: 20.0` — **inert here**,
   because the baseline engine predates those fields and ignores unknown keys.

Areas, U-values, thermal capacities, orientations, sky-view factors, setpoints, gain
schedules and the adjacent-zone definitions are untouched. So for the baseline engine
the *effective* difference is exactly one field on five surfaces.

### Timeline

| When | What |
| --- | --- |
| 2026-07-26 04:23 | baseline engine vendored (`2e6e910`) |
| **2026-07-28 02:29** | `results/baseline_vs_ep/` written — building dict still `"opaque"` |
| **2026-07-28 10:25** | commit `4376658` retypes the five surfaces to `"adjacent"` |
| **2026-07-28 10:52** | `results/au_corrections_summary/` written — building dict now `"adjacent"` |

Both harnesses import `apt305_building` from the **repository working tree**, not from
the engine worktree (`sys.path.insert(0, EXAMPLES_DIR)` where `EXAMPLES_DIR` is the
repo's own `examples/`). So the building dictionary silently tracked whatever was
checked out at the moment of the run, while the engine was pinned. That is the
mechanism by which a "baseline" changed without any baseline code changing.

---

## 4. Why the balance inverts — mechanism, verified

The ISO 52016 element classifier in the single-zone core, `utils.py:6983-6994`:

```python
if surf["type"] == "opaque":
    if surf["sky_view_factor"] == 0:
        typology_elements[i] = "GR"        # slab-on-ground
    else:
        typology_elements[i] = "OP"
...
elif surf["type"] == "adjacent":
    typology_elements[i] = "ADJ"           # internal partition
```

All five party surfaces carry `sky_view_factor: 0.0`. Typed `"opaque"` they therefore
land in **`GR`**. Captured post-run from the dictionary the core mutated in place —
measured, not inferred:

| Surface | declared type | svf | area | A → | B → |
| --- | --- | ---: | ---: | :-: | :-: |
| West exterior wall | opaque | 0.5 | 11.88 | OP | OP |
| North wall to Apt 306 | opaque → adjacent | 0.0 | 10.80 | **GR** | **ADJ** |
| South wall to Apt 304 | opaque → adjacent | 0.0 | 10.80 | **GR** | **ADJ** |
| East wall to corridor | opaque → adjacent | 0.0 | 13.50 | **GR** | **ADJ** |
| Floor to Apt 205 | opaque → adjacent | 0.0 | 20.00 | **GR** | **ADJ** |
| Ceiling to Apt 405 | opaque → adjacent | 0.0 | 20.00 | **GR** | **ADJ** |
| West windows ×2 | transparent | 0.5 | 1.62 | W | W |

```
area by ISO 52016 class, A:  {OP: 11.88, GR: 75.10, W: 1.62}
area by ISO 52016 class, B:  {OP: 11.88, ADJ: 75.10, W: 1.62}
```

**75.1 m² moves between classes** — including the *ceiling* of a third-floor
apartment. In config A this apartment has 75.1 m² of envelope in contact with the
earth and no internal partitions at all.

That inverts the balance because `GR` couples those surfaces to the ISO 13370 ground
temperature — a warm, heavily damped sinusoid that in Melbourne sits near the annual
mean (≈16 °C) and never falls to winter air temperature. 75.1 m² clamped near 16 °C is
a large winter *heat source*: heating collapses to 15.9 kWh. In summer that same mass
holds the zone up while gains accumulate, so cooling inflates to 2 027.5 kWh. Retyped
`ADJ`, the surfaces instead couple to the ISO 13789 buffer `theta_ztu`, which tracks
outdoor air (`b_ztu` 0.73–0.93) — the winter heat source disappears and heating rises
to 1 308.6 kWh.

The corroborating annual terms move exactly as that story predicts:

| | A (`GR`) | B (`ADJ`) |
| --- | ---: | ---: |
| `Q_ground_loss_kWh` | 192.44 | 90.20 |
| `Q_ground_gain_kWh` | 42.43 | 2.77 |
| `Q_tr_opaque_loss_kWh` | 433.55 | 89.05 |

### Why internal gains are identical — and why that is *not* evidence of sameness

`Q_internal_gains_kWh = 5356.685952` in both, because internal gains are computed from
floor area and the **number of adjacent zones** (5, unchanged) and never read surface
`type`. The identity that made the two runs look comparable is precisely the one
quantity that is blind to the thing that differs. It should not have been read as
evidence the two models matched.

---

## 5. Hypotheses, resolved

| | Hypothesis | Verdict | Evidence |
| --- | --- | :-: | --- |
| (a) | different weather data | **ruled out** | identical path, row count, HDD/CDD/GHI, and sha256 of both `T2m` and `G(h)` |
| (b) | different hourly index for gains/solar (Issue 10) | **ruled out** | `Phi_int` sha256 `1b4d58a0c10bcfd6` and `Phi_sol` sha256 `df637e9c3e159e3d` match; hour-of-day distributions identical elementwise |
| (c) | different code commits | **ruled out** | one engine commit `2e6e910` reproduces **both** published results bit-exactly |
| (d) | **different building dictionary** | **CONFIRMED** | `4376658` retypes 5 party surfaces `opaque`→`adjacent`; 75.1 m² moves `GR`→`ADJ` |

**Item 2 does not trigger.** The brief scopes it to verdict (b); the schedule-offset
hypothesis is disproven by the matching hashes. Issue 10 may still be a real defect in
the abstract, but it is *not* the cause of this contradiction and no schedule change
would reconcile these two runs.

---

## 6. Which baseline is canonical

**Config B — the six-state harness baseline, 1 308.60 kWh heating / 741.83 kWh
cooling.**

Not because it is the more plausible number, but because config A is a
misdescription of the building: it models a Level 3 apartment with 75.1 m² of
slab-on-ground, its ceiling included. No amount of engine correction makes that the
right model of Apt 305. Config B describes the building the paper is about.

**The caveat the brief asked to have named, not assumed.** The harness's "Baseline"
column is an unmodified **engine** — that part of the label is exact, and §2.5 proves
it. But it is *not* the same **model** as the earlier baseline. Between the two runs
the building input was corrected, and that correction is a **model-input fix, not an
engine fix**. It therefore does not belong in the same sequence as C1–C4 (which are
engine corrections) without being distinguished from them, or the paper will appear to
credit an engine fix with an effect produced by fixing the input file.

Suggested framing: the six corrections are preceded by an **input-specification
correction (C0)**, whose effect is 15.86 → 1 308.60 kWh heating and 2 027.51 → 741.83
kWh cooling, and which is a property of `apt305_building.py`, not of the engine.

### Consequently stale — flagged, not edited

Every figure produced before 2026-07-28 10:25 is for the mis-specified building:

* `results/baseline_vs_ep/` — the EnergyPlus comparison, including
  `iso_results.json`, `baseline_vs_energyplus.{csv,md,png}` and the Sankey.
* `results/ventilation_latent/` — the vent+latent table (its baseline column is
  config A).
* `corrected_weather_results_rewrite.tex` and any table drawn from the above.
* The EnergyPlus alignment audit's claim that the ISO side modelled the neighbours as
  ISO 13789 buffers: under config A it did not — they were `GR`. The E+ side did build
  OSC objects from `b_ztu`, so that comparison was mismatched in a way the audit did
  not detect.

No `.tex` file was edited and no result was overwritten under this item, per the brief.

---

## 7. Reproducing this

```bash
# one engine, two building dictionaries
git worktree add --detach /tmp/wt_base origin/claude/pybuildingenergy-baseline-anjro8
git show 4376658^:examples/apt305_building.py > /tmp/cfgA/apt305_building.py   # "opaque"
cp examples/apt305_building.py                 /tmp/cfgB/apt305_building.py    # "adjacent"

python probe_baseline.py --src /tmp/wt_base/pybuildingenergy/src \
    --bui-dir /tmp/cfgA --epw weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw \
    --out A.json      # -> 15.861616700444602 / 2027.5064783087112
python probe_baseline.py --src /tmp/wt_base/pybuildingenergy/src \
    --bui-dir /tmp/cfgB --epw weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw \
    --out B.json      # -> 1308.601259174238  / 741.828245796808
```

The probe is committed at `tools/diagnostics/probe_baseline.py`.

---

## 8. Incidental observation, carried to Item 3

Both runs print a V2 Sankey closure residual to stdout, and it is **not** currently
captured by either harness:

```
config A (GR)   inputs=6 779 156.0 Wh  outputs+storage=6 078 826.7 Wh  residual=700 329.3 Wh (10.331 %)
config B (ADJ)  inputs=8 117 581.1 Wh  outputs+storage=3 051 103.2 Wh  residual=5 066 478.0 Wh (62.414 %)
```

The 10.331 % / ~700 kWh figure for config A is the "10 % / ~703 kWh at baseline"
quoted in the brief — so that number, too, was measured on the mis-specified building.
On the **canonical** baseline the residual is **62.4 %**, six times worse. Item 3
picks this up across all six states.
