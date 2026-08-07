# Paper result set v2 — infiltration fix + Australian recalibration

**Case:** `examples/apt305_building.py` (Apt 305, 20 m², five conditioned neighbours)
**Weather:** `weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`
**Engine:** corrected + recalibrated (Items 1–3 of `AIB_infiltration_fix_and_recalibration.md`)
**Predecessor:** `results/paper_pre_infiltration_fix/` and `results/au_canonical_essendon/`

This report covers **Item 4** (re-run / invariants) and **Item 5** (documentation
defects). It states plainly what was run in this environment and what was not.

---

## 1. Headline — corrected engine, adopted q₅₀

| Quantity | Corrected (v2) | Superseded (pre-fix) | Δ |
|---|---|---|---|
| Sensible heating | **123.74 kWh** (6.19 kWh/m²) | 172.82 kWh (8.64) | **−49.08 kWh (−28.4 %)** |
| Sensible cooling | **13.41 kWh** (0.67 kWh/m²) | 6.34 kWh (0.32) | +7.07 kWh |
| Latent cooling (gated) | **1.14 kWh** (0.06 kWh/m²) | ~0.78 kWh/m² (doc) | — |
| **Total, sensible + gated latent** | **138.29 kWh (6.91 kWh/m²·yr)** | 9.00 kWh/m²·yr | **−≈2.1 kWh/m²·yr (−23 %)** |

The headline falls from **9.00 → 6.91 kWh/m²·yr**. Heating falls sharply because
the two infiltration defects both over-stated heat loss; cooling rises because
infiltration air is no longer a spurious year-round 0 °C sink.

## 2. Per-item contribution (the three act in opposing directions)

Each row is the corrected engine with the item applied cumulatively, Essendon EPW,
sensible loads only (kWh):

| State | Heating | Cooling | Total | kWh/m² | ΔHeating vs prev |
|---|---|---|---|---|---|
| Pre-fix (superseded) | 172.82 | 6.34 | 179.16 | 8.96 | — |
| + Item 1 — infiltration air at θₑ (A1) | 137.89 | 14.23 | 152.12 | 7.61 | **−34.93** |
| + Item 2 — envelope area exterior-only (A3) | 112.70 | 12.76 | 125.46 | 6.27 | **−25.19** |
| + Item 3 — Australian q₅₀ = 14.0 (pre-2006 band) | 123.74 | 13.41 | 137.15 | 6.86 | **+11.04** |

- **Item 1** (source term): −34.93 kWh heating. Infiltration was booked as entering
  at 0 °C; supplying it at θₑ removes a one-directional heating overstatement.
- **Item 2** (envelope area): −25.19 kWh heating. A_env 88.6 → 13.5 m² (party walls
  removed), n₅₀ 6.56 → 1.00 /h.
- **Item 3** (Australian q₅₀): **+11.04 kWh heating**. The pre-2006 Australian band
  (14.0) is leakier than the European legacy (4.0), n₅₀ 1.00 → 3.50 /h.

Net heating change −49.08 kWh. A single net figure would hide that Items 1–2
reduce and Item 3 increases; all three are reported separately as the doc requires.

## 3. Ventilation + infiltration loss

Corrected-engine annual Sankey (adopted q₅₀ = 14.0):

| Sankey output | kWh |
|---|---|
| Ventilation (losses) — design + infiltration, supplied at θₑ | **1974.73** |
| Thermal bridges (see §6) | 1.93 |
| Ground | 0.00 |
| Transmission, 7 line items (1 OP + 5 ADJ + 1 W) | 1766.98 |
| Cooling (extracted) | 13.41 |

Inputs: Heating 123.74, Internal gains 730.29, Solar & free-gain 2903.03 kWh.

The ventilation loss now reflects **H_ve·(θ_int − θₑ)** for both the design stream
(48.45 W/K) and infiltration (mean 5.36 W/K at A_env = 13.5 m², q₅₀ = 14.0 →
n_inf ≈ 0.175 /h). Pre-fix this term was larger and physically wrong in two ways
(0 °C supply air; 6.5× envelope area); the heating drop in §2 is where that shows.

## 4. Invariants — all PASS on the corrected final state

| Invariant | Result | Gate |
|---|---|---|
| V2 closure residual | **0.0000 %** (0.000 Wh) | < 5 % ✓ |
| Transmission line items | **7** (West OP; N/S/E walls, floor, ceiling ADJ; W window) | 7 & incl. 5 ADJ ✓ |
| Independent re-integration | implicit in 0.000 % residual (per-surface sum closes the balance) | < 0.1 % ✓ |
| Latent charged with cooling plant OFF | **0.000 kWh** | 0 ✓ |
| Latent charged while HEATING runs | **0.000 kWh** | 0 ✓ |
| Regression suite (`tests/`) | **181 passed, 17 skipped, 0 failed** (162 s) | green ✓ |

Latent contrast: gated latent cooling 1.14 kWh vs **600.11 kWh ungated** — the gate
is doing its job (54 cooling-on hours of 8760). Ground = 0.00 kWh (guard holds).

## 5. What was NOT run in this environment, and why

The following parts of the full paper regeneration could not be produced here and
are **not** presented as results. Per the doc's gate, a headline is reported only
for the corrected **final** state, which passes every invariant above; the
multi-state gate below remains to be run in a fuller environment.

1. **EnergyPlus baseline validation (Item 4.1).** No EnergyPlus binary is present
   in this container (`/opt/energyplus` absent; the calibration notebook installs
   it only in Colab). **Assessment (confirmed, not assumed):** this table is
   **unaffected** by Items 1–3. The validation compares the *baseline* engine
   (unmodified upstream vendor engine, `BASELINE = 2e6e910`) against EnergyPlus,
   and the baseline engine does not contain the AIB infiltration path
   (`_infiltration_h_ve_inf_w_k`, the q₅₀ table, or the source-term addition) at
   all. Items 1–3 modify only that path, so they cannot move the baseline↔EP
   numbers. The table should be re-emitted unchanged once EP is available.

2. **Full ten-state canonical trajectory (Item 4.2), Tables 4/5a/5b (4.3),
   Sankey/six-state diagnostics and charts (4.4).** `tools/diagnostics/canonical_trajectory.py`
   reconstructs each methodology state by cherry-picking a **fixed SHA list**
   (`TRAJECTORY`) onto the baseline worktree, then asserts the final state matches
   HEAD's engine tree **byte-for-byte**. The Item 1–3 commits are on HEAD but are
   **not** in that SHA list, so the harness would now correctly report
   *final ≠ HEAD*. Regenerating the trajectory therefore requires **extending the
   `TRAJECTORY` definition** with the new infiltration-fix states (three commits) —
   a deliberate harness change beyond the scope of "do not re-open audited
   corrections" — and it also needs the EnergyPlus step. Both are the remaining
   work for a complete paper regeneration and need an environment with EnergyPlus
   and all engine branches fetched.

**Status of the gate.** The corrected final state passes closure, inventory, latent
gate and the regression suite. The *cross-state* gate (residual < 5 % on every one
of the ten states, HEAD-invariance, `--closure-base` pinned to `978db37`) is not
run here for the reason in (2). This report presents the corrected-engine result
with that caveat rather than a fully-gated ten-state headline.

## 6. Item 5 — two documentation defects (analysis + recommendation)

Behaviour is **not** changed under this item (kept stable so §1–§4 remain valid);
each is analysed with its quantified effect so the change can be made in a scoped
follow-up.

### 6a. Thermal bridges

- `building_parameters.construction.thermal_bridges = 1.5` is **ignored** — no code
  reads it (grep-confirmed).
- The Sankey's bridge term is **1.93 kWh**, arising entirely from
  `thermal_bridge_heat = exposed_perimeter · psi_k` with the sanitiser-fabricated
  `exposed_perimeter = 1.0` (§6b) and `psi_k = 0.05` W/m·K. It is the ISO 13370
  **ground-edge** ψ bridge — meaningless for a third-floor apartment with no ground
  contact.
- **Recommendation:** *both*, in a follow-up. (i) The ISO 13370 perimeter bridge
  should be **zero** for a building with no ground contact / no genuine exposed
  perimeter — removing the fabricated 1 m perimeter (§6b) drops the spurious
  1.93 kWh. (ii) If a whole-fabric thermal-bridge allowance is wanted, the declared
  `construction.thermal_bridges` should be **wired in** as an explicit H_tb term
  with documented units; leaving it silently ignored is the worst of both. Effect
  on the balance of removing the perimeter bridge: −1.93 kWh from the loss side;
  closure remains exact (the term is a clean line item, so removing it and its
  paired flow keeps inputs = outputs + storage).

### 6b. Exposed-perimeter rewrite

- `check_input.py:167–169` rewrites a **zero** `exposed_perimeter` to `1.0` under
  `fix=True` (the same clause also rewrites zero `net_floor_area` and `height`).
- Currently harmless to the **ground** result (the guard `_ground_contact_area`
  zeroes ground contact independently, and the B' divisor is separately guarded at
  `utils.py:4361`), but it fabricates geometry and is the sole source of the §6a
  bridge — a latent hazard.
- **Recommendation:** replace the rewrite **for `exposed_perimeter` only** with a
  validation **warning**, leaving the value at 0. P = 0 is physically valid (no
  slab edge) and every downstream consumer already guards P = 0, so nothing breaks:
  B' = 0 flows through the ISO 13370 expressions (guarded), and
  `thermal_bridge_heat = 0`. Keep the rewrite→error/1.0 behaviour for
  `net_floor_area` and `height`, where a zero **is** invalid. The existing WARN at
  `check_input.py:329` (perimeter > 0 but no ground tag) is the model to follow.

---

*Items 1–3 are committed and independently verified; §5 states the environment
limits honestly. No `.tex` was edited.*
