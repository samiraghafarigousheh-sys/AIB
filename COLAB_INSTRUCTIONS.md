# Running the Australian Corrections Harness in Google Colab

> ### Notebooks, newest first
>
> | Notebook | Covers |
> | --- | --- |
> | `colab_canonical_trajectory.ipynb` | the green regression suite, the canonical trajectory in **methodology order** (literature corrections first), and the wind diagnostic that returns **verdict (c)** |
> | `colab_closed_balance.ipynb` | closing the energy balance: ADJ transmission into the inventory, latent gating, GR classification |
>
> **To open the newest in Colab:**
> ```
> https://colab.research.google.com/github/samiraghafarigousheh-sys/aib/blob/claude/aib-energy-balance-closure-83epu7/colab_canonical_trajectory.ipynb
> ```
>
> ### On the closed balance: `colab_closed_balance.ipynb`
>
> The two notebooks below run the **four-step** harness and report
> **172.9 → 34.9 kWh/m² (−79.8 %)**. That figure came off an **unclosed energy
> balance**: the V2 Sankey residual ran 62 % → −20 % across those states, with
> 75.10 m² of party surface — 88.6 % of the envelope UA — missing from the
> reported inventory entirely, and a latent term charged in 8 758 of 8 760 hours
> against ~146 hours of actual plant operation.
>
> Those defects are fixed. `colab_closed_balance.ipynb` runs the seven-state
> harness on a closed balance and enforces the gate — **residual < 5 % on every
> state** — before any headline is quoted. Use it for anything that is going into
> the paper. Full analysis: `results/au_corrections_closed/NOTES.md`.
>
> **To open in Colab:**
> ```
> https://colab.research.google.com/github/samiraghafarigousheh-sys/aib/blob/claude/aib-energy-balance-closure-83epu7/colab_closed_balance.ipynb
> ```
>
> It clones the repo, checks out the closed-balance branch, runs the harness,
> prints the gate table, rebuilds the faceted chart and runs the regression
> tests. Roughly 5–10 minutes on a CPU runtime.
>
> The two notebooks below are kept as the record of the four-step work. Read
> their numbers as *before* measurements.

Two notebooks are provided to execute the four-step cumulative correction harness in Colab:

## Quick Start

### Option 1: Comprehensive Notebook (Recommended for understanding)
**File:** `colab_au_corrections_harness.ipynb`

This notebook includes:
- Full setup and dependency installation
- Detailed step-by-step explanations
- Grouped bar chart visualization
- Per-step analysis and validation notes
- Remaining known defects
- Test coverage summary

**To open in Colab:**
```
https://colab.research.google.com/github/samiraghafarigousheh-sys/aib/blob/main/colab_au_corrections_harness.ipynb
```

### Option 2: Quick Run (For fast results)
**File:** `colab_quick_run.ipynb`

This notebook:
- Runs the harness with minimal setup
- Displays comparison tables immediately
- Shows grouped bar chart
- ~5-10 minutes total runtime

**To open in Colab:**
```
https://colab.research.google.com/github/samiraghafarigousheh-sys/aib/blob/main/colab_quick_run.ipynb
```

## Manual Copy-Paste into Colab

If the direct links don't work, copy the notebook `.ipynb` files and paste them into Colab:

1. Go to [colab.research.google.com](https://colab.research.google.com)
2. Click **File → Upload notebook**
3. Select `colab_au_corrections_harness.ipynb` or `colab_quick_run.ipynb`
4. Run all cells (Ctrl+F9 or Runtime → Run all)

## Expected Runtime

- **Quick Run:** ~5-10 minutes (includes full annual simulations)
- **Comprehensive:** ~10-15 minutes (more explanation, same computation)

## What Gets Computed

The harness runs through all four correction steps sequentially:

1. **Step 1:** Internal gains inflation removal (7.335× factor)
2. **Step 2:** Conditioned adjacent zones (neighbours at fixed 20°C setpoint)
3. **Step 3:** Ground contact area fallback fix (eliminates phantom 20 m² slab)
4. **Step 4:** Hemisphere-aware coldest month resolution (July for southern, January for northern)

Each step runs apt 305 (20 m² Melbourne apartment) through a full annual ISO 52016-1 simulation.

## Output

Both notebooks produce:

- **Comparison tables** (CSV format)
  - `comparison.csv` — states as rows, metrics as columns
  - `comparison_by_metric.csv` — metrics as rows, states as columns

- **Grouped bar chart** — Heating, Cooling, Total energy across all six states

- **Summary statistics**
  - Baseline: 172.9 kWh/m²·yr
  - Final (+Hemisphere Fix): 34.9 kWh/m²·yr
  - **Reduction: −79.8%**

## Dependencies

The notebooks automatically install:
- `pybuildingenergy` (from the cloned repository)
- `pytest` (for running tests, if needed)
- `matplotlib` (for charts)
- `pandas` (for data handling)

## Interpreting Results

### Energy Intensity Table

| State | Heating | Cooling | Total |
| --- | ---: | ---: | ---: |
| Baseline | 127.9 | 45.0 | 172.9 |
| +Vent+Latent | 138.6 | 43.4 | 182.0 |
| +Internal Gains | 119.9 | 32.0 | 151.9 |
| +Conditioned Zones | 4.8 | 30.2 | 35.0 |
| +Ground Fix | 4.8 | 30.2 | 35.0 |
| +Hemisphere Fix | 4.8 | 30.2 | 34.9 |

**Key observations:**

1. **Step 1 (Internal Gains):** Removes 7.335× inflation, saving ~20% of total
2. **Step 2 (Conditioned Zones):** Biggest impact (−78.4%); neighbours at fixed setpoint rather than tracking outdoor air
3. **Step 3 (Ground Contact):** No change to heating/cooling (correct: step 2 already zeroed the term)
4. **Step 4 (Hemisphere):** No change to apt 305 (correct: step 3 zeroed ground contact)

## Technical Details

### What Each Correction Fixes

**Step 1 — Internal Gains Inflation**
- **Problem:** Adjacent-zone gains multiplied by 1 + n×(1 + (1−b_ztu)×F_ztc_ztu_m) = 7.335×
- **Root Cause:** Erroneous for-loop in `ventilation.py` summing gains repeatedly
- **Fix:** Removed the loop; now `Phi_int_z_t = q_int_total × a_use`
- **Impact:** 730.3 kWh internal gains (was 5356.7 kWh)

**Step 2 — Conditioned Adjacent Zones**
- **Problem:** Neighbours modeled using ISO 13789 buffer formula → tracking outdoor air
- **Root Cause:** No `conditioned` field support; all zones treated as unconditioned
- **Fix:** Added `conditioned: True/False` and optional `setpoint` (°C)
  - Conditioned → held at setpoint every timestep
  - Unconditioned → ISO 13789 formula (outdoor tracker)
- **Impact:** θ_ztu = 20.0°C ± 0 K across all 9504 timesteps; buffer formula never called

**Step 3 — Ground Contact Area Fallback**
- **Problem:** Buildings without explicit ground surface get full-footprint slab (20 m² for apt 305)
- **Root Cause:** `_ground_contact_area()` fell back to `net_floor_area` when no tag found
- **Fix:** Absence of ground surface → return 0.0; legacy inference now opt-in
- **Impact:** Ground loss/gain reduced from 68.8 / 2.2 → 0.0 / 0.0 kWh

**Step 4 — Hemisphere-aware Coldest Month**
- **Problem:** Ground sinusoid phase hardcoded to month 1 (January) globally
- **Root Cause:** Southern-hemisphere sites six months out of phase
- **Fix:** `_resolve_coldest_month()` resolves from latitude:
  - South (lat < 0) → July (month 7)
  - North (lat ≥ 0) → January (month 1)
- **Impact:** Validated on ground-floor test case; no change to apt 305 (ground zeroed in step 3)

### Validation Approach

Each step includes:

1. **Engine branch tests** (25–27 per step)
   - Unit tests for the core fixes
   - Edge cases and boundary conditions
   - Validation against ISO standards (e.g., table B.16 caps, ISO 13370 hand calculations)

2. **Harness branch tests** (5–7 per step)
   - Full annual simulations via worktree isolation
   - Real weather (Melbourne EPW)
   - Acceptance criteria as direct assertions (not eyeballed charts)

3. **Upstream suite integrity**
   - All 284 passing tests remain unchanged
   - Same 7 failures, 10 skipped as parent branch

## Files in Repository

### Notebooks
- `colab_au_corrections_harness.ipynb` — comprehensive with detailed explanations
- `colab_quick_run.ipynb` — streamlined for quick execution

### Harness
- `examples/compare_au_corrections.py` — cumulative comparison runner
  - Usage: `python examples/compare_au_corrections.py --through-step 4`
  - Outputs: `results/au_corrections_summary/{comparison.csv, comparison_by_metric.csv, comparison_*.png}`

### Step Notes (Engine Branch Documentation)
- `results/step_1_internal_gains/NOTES.md`
- `results/step_2_conditioned_zones/NOTES.md`
- `results/step_3_ground/NOTES.md`
- `results/step_4_hemisphere/NOTES.md`
- `results/au_corrections_summary/NOTES.md` — overall cumulative summary

### Engine Changes
- `pybuildingenergy_engine_changes.md` — four-entry changelog

### Feature Branches
All implemented on separate branches, each a strict superset of its predecessor:

```
main
 ├── claude/internal-gains-fix
 ├── claude/conditioned-adjacent-zones-fix
 ├── claude/ground-contact-fix
 └── claude/coldest-month-hemisphere-fix
```

## Troubleshooting

### Notebook fails to clone repository
- Ensure you have internet access
- Repository is public: https://github.com/samiraghafarigousheh-sys/aib

### Harness takes too long
- Expected runtime: 5–15 minutes (includes full annual simulations)
- If > 20 minutes: check Colab's CPU/RAM allocation

### Chart not displaying
- Matplotlib should render automatically in Colab
- If not: ensure cell output is not suppressed, try `plt.show()`

### Weather file not found
- Harness requires EPW file in `weather_cache/`
- If missing, tests will skip gracefully
- (The repository includes a Melbourne EPW by default)

## References

- **ISO 52016-1:2017** — Energy performance of buildings — Calculation methodology for energy use
- **ISO 13789:2017** — Thermal performance of buildings — Transmission and ventilation heat transfer coefficients
- **ISO 13370:2017** — Thermal performance of buildings — Ground heat transfer
- **apt 305** — Test building: 20 m² apartment on level 3 of a residential block in Melbourne
- **pyBuildingEnergy** — Python implementation of the ISO standards on this repository's engine branch

## Contact

For issues or questions about the harness, analysis, or engine implementation, refer to:
- Issue tracker: https://github.com/samiraghafarigousheh-sys/aib/issues
- NOTES.md files in `results/step_*/` for detailed per-step analysis
