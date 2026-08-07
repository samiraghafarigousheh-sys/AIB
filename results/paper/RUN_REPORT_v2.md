# Paper result set v2 — infiltration fix + Australian recalibration (GATED)

**Case:** `examples/apt305_building.py` (Apt 305, 20 m², five conditioned neighbours)
**Weather:** `weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`
**Engine:** corrected + recalibrated (Items 1–3 of `AIB_infiltration_fix_and_recalibration.md`)
**Predecessor:** `results/paper_pre_infiltration_fix/` and `results/au_canonical_essendon/`

This report covers **Item 4** (re-run + gate) and **Item 5** (documentation defects).
The full multi-state gate has now been run: the corrected engine is EnergyPlus-validated,
the thirteen-state canonical trajectory passes the V2 residual gate on every state, and the
trajectory's final state reproduces HEAD byte-for-byte. Primary artefacts:

- `results/paper/trajectory_v2/comparison.md` — the gated 13-state trajectory
- `results/paper/baseline_vs_ep_v2/` — the EnergyPlus validation
- Regression suite: **198 passed / 0 skipped / 0 failed**

---

## 1. Headline — GATED

**123.74 kWh sensible heating + 13.41 kWh sensible cooling + 1.14 kWh gated latent
= 138.29 kWh = 6.91 kWh/m²·yr.** Latent heating is 0.0000 kWh at this state.

The figure is verified three ways to the printed digit: (i) the corrected engine run
directly on HEAD, (ii) the trajectory's reconstructed final state, and (iii) an isolated
run holding all fixes at final — all give 123.74 / 13.41 / 1.14. Δ vs a live HEAD run is
0.00e+00 on every invariant metric.

| Quantity | Corrected (v2, gated) | Superseded (pre-fix, Essendon) | Δ |
|---|---|---|---|
| Sensible heating | **123.74 kWh** (6.19 kWh/m²) | 172.82 kWh (8.64) | −49.08 kWh (−28.4 %) |
| Sensible cooling | **13.41 kWh** (0.67 kWh/m²) | 6.34 kWh (0.32) | +7.07 kWh |
| Latent cooling (gated) | **1.14 kWh** (0.06 kWh/m²) | ~0.78 kWh/m² (doc) | — |
| **Total, sensible + gated latent** | **138.29 kWh (6.91 kWh/m²·yr)** | 9.00 kWh/m²·yr | **−≈2.1 kWh/m²·yr (−23 %)** |

## 2. Per-item contribution — canonical (methodology-order) trajectory

From `trajectory_v2/comparison.md`, each state is the previous plus exactly one correction,
cherry-picked onto the unmodified baseline and measured with the same closure instrument.
The three infiltration states sit after `+Hemisphere`:

| State | Heating (kWh) | Cooling (kWh) | kWh/m² | ΔHeating |
|---|---:|---:|---:|---:|
| +Hemisphere (pre-infiltration-fix) | 210.28 | 4.12 | 10.75 | — |
| **+Infiltration supply temp (A1)** | 153.95 | 15.15 | 8.52 | **−56.33** |
| **+Infiltration envelope area (A3)** | 114.87 | 12.89 | 6.44 | **−39.08** |
| **+AU q₅₀ recalibration (Item 3)** | 123.74 | 13.41 | 6.91 | **+8.87** |
| +Closure fixes (measurement, not physics) | 123.74 | 13.41 | 6.91 | 0.00 |

The three act in **opposing directions** — A1 and A3 reduce heating, the Australian q₅₀
increases it — exactly as anticipated. A single net figure would hide that two defects were
inflating heating and the recalibration partly offsets them. `+Closure fixes` moves no number:
its content is already in the instrument used to measure every state.

*(An isolated view — toggling one dimension on the otherwise-final engine — gives the same
directions with different magnitudes, −34.93 / −25.19 / +11.04 kWh, because it does not carry
the cumulative methodology-order context. The trajectory table above is canonical.)*

### q₅₀ sensitivity (isolated on the corrected engine, varying only q₅₀)

| q₅₀ [m³/(h·m²)@50 Pa] | Source | Heating | Cooling | Total |
|---|---|---:|---:|---:|
| 4.0 | European legacy (superseded) | 112.70 | 12.76 | 125.46 kWh |
| 6.9 | CSIRO 2024 (Ambrose, n=233) new-dwelling mean | 115.85 | 12.94 | 128.79 kWh |
| **14.0** | **adopted** — Australian pre-2006 band | 123.74 | 13.41 | 137.15 kWh |

## 3. EnergyPlus validation — unaffected by Items 1–3 (confirmed, not assumed)

`results/paper/baseline_vs_ep_v2/` — the **baseline** ISO engine (unmodified vendor engine,
`claude/pybuildingenergy-baseline-anjro8`) against EnergyPlus 24.1.0, both on the Essendon EPW:

| Metric | ISO 52016-1 (baseline) | EnergyPlus | Diff | ISO kWh/m² | E+ kWh/m² |
|---|---:|---:|---:|---:|---:|
| Heating | 1,779.4 | 1,120.2 | −37.0 % | 89.0 | 56.0 |
| Cooling | 640.8 | 697.2 | +8.8 % | 32.0 | 34.9 |
| Total | 2,420.2 | 1,817.4 | −24.9 % | 121.0 | 90.9 |

The alignment table records **"Infiltration: none (no infiltration configured)"** on both
sides, and the baseline heating (1,779.4) is byte-consistent with the trajectory's Baseline
state (1,779.36). Items 1–3 modify only the AIB infiltration path, which the baseline engine
does not contain, so this validation table is **unchanged** by the fixes — as reasoned, now
demonstrated by running it.

## 4. Invariants — the full cross-state gate PASSES

From `trajectory_v2/comparison.md §8` and the regression run:

| Condition | Result |
|---|:-:|
| V2 residual < 5 % on **every** state (13 states) | **PASS** (max −1.77 % at +Conditioned; machine-zero from +Ground on) |
| Seven transmission line items, every state (5 ADJ + wall + window) | **PASS** |
| Independent re-integration within 0.1 %, every state | **PASS** (0.0000 %) |
| Latent gated — 0 charged with plant off, 0 while heating, every state | **PASS** (0.000000) |
| HEAD invariant under the reordering | **PASS** |
| Final engine tree identical to HEAD | **PASS** (byte-for-byte) |
| Regression suite `tests/` | **PASS** (198 passed / 0 skipped / 0 failed) |

The 17 previously-skipped worktree tests were skipping for want of the engine branches +
`pyecharts`, not because of the new commits; with the branches fetched and the dependency
installed, all 198 pass.

## 5. Sankey breakdown (corrected final state)

| Sankey output | kWh |
|---|---:|
| Ventilation (losses) — design + infiltration, supplied at θₑ | 1974.73 |
| Thermal bridges (see §6) | 1.93 |
| Ground | 0.00 |
| Transmission, 7 line items (1 OP + 5 ADJ + 1 W) | 1766.98 |
| Cooling (extracted) | 13.41 |

Inputs: Heating 123.74, Internal gains 730.29, Solar & free-gain 2903.03 kWh. Closure residual
0.0000 %. The five party surfaces (75.10 m², 88.6 % of envelope UA) each carry a transmission
line item; the reported sum equals an independent re-integration of the hourly flows to 0.0000 %.

## 6. Item 5 — two documentation defects (analysis + recommendation)

Behaviour is **not** changed under this item (kept stable so §1–§5 stay gated); each is
analysed with its quantified effect for a scoped follow-up.

### 6a. Thermal bridges

- `building_parameters.construction.thermal_bridges = 1.5` is **ignored** — no code reads it.
- The Sankey's bridge term is **1.93 kWh**, arising entirely from
  `thermal_bridge_heat = exposed_perimeter · psi_k` with the sanitiser-fabricated
  `exposed_perimeter = 1.0` (§6b) and `psi_k = 0.05` W/m·K — the ISO 13370 **ground-edge** ψ
  bridge, meaningless for a third-floor apartment with no ground contact.
- **Recommendation (both):** (i) the ISO 13370 perimeter bridge should be **zero** for a
  building with no ground contact — removing the fabricated 1 m perimeter (§6b) drops the
  spurious 1.93 kWh; (ii) if a whole-fabric bridge allowance is wanted,
  `construction.thermal_bridges` should be **wired in** with documented units. Effect of
  removing the perimeter bridge: −1.93 kWh from the loss side; closure stays exact.

### 6b. Exposed-perimeter rewrite

- `check_input.py:167–169` rewrites a **zero** `exposed_perimeter` to `1.0` under `fix=True`.
- Harmless to the ground result (the guard zeroes ground contact independently; the B'
  divisor is separately guarded at `utils.py:4361`), but it fabricates geometry and is the
  sole source of the §6a bridge.
- **Recommendation:** replace the rewrite **for `exposed_perimeter` only** with a validation
  **warning**, leaving the value at 0. P = 0 is physically valid (no slab edge) and every
  downstream consumer already guards P = 0, so nothing breaks. Keep the rewrite→1.0 for
  `net_floor_area`/`height`, where zero is genuinely invalid.

---

*Items 1–3 committed and verified; the full trajectory + EnergyPlus validation now run and
gated in this environment (EnergyPlus 24.1.0 installed, all engine branches fetched). No `.tex`
was edited.*
