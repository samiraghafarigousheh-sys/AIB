# AIB — Code ↔ Paper Conformance Audit

**Repo:** `samiraghafarigousheh-sys/AIB`
**Engine audited:** `pybuildingenergy/src/pybuildingenergy/source/utils.py` (+ `ventilation.py`, `check_input.py`)
**Case:** `examples/apt305_building.py` (Apt 305, 20 m², one exposed west façade, five conditioned neighbours)
**Weather:** `weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`
**Method:** every item traced to the code that evaluates it; quantities reproduced by running the
corrected engine on the case + weather above (`weather_source="epw"`). Line numbers are 1-indexed
against the files as they stand on branch `claude/calibration-epw-rewrite-xwspe6`.

> This is a conformance audit. Where code and paper disagree the disagreement is recorded and the
> code is treated as authoritative — **no `.tex` and no engine logic were edited.** Divergences that
> are themselves defects are called out as such and left for a separate task.

---

## Summary

### Verdict counts (Part A)

| Verdict | Items | Count |
|---|---|---|
| **CONFORMS** | A2, A5, A6, A7, A8, A9, A12, A13 | 8 |
| **DIVERGES** | A1, A3, A4, A10, A11 | 5 |
| **OPEN** (implemented but undocumented; needs paper text) | A14 | 1 |

**Part B:** all six claims **CONFIRMED** (B1–B6).

Three of the five divergences are **latent for Apt 305** (A4 q₅₀ band, A10 ground U-value branches
and R_si/R_f) because the ground-contact guard zeroes every ground term for this third-floor case;
they are still equation-level mismatches the paper must not assert. Two divergences are **live and
affect the reported demand**: **A1** (infiltration source term) and **A3** (infiltration envelope
area), plus the sanitiser's perimeter rewrite under A10/A14 which injects a ~2 kWh thermal bridge.

### Reproduced quantities (corrected engine, Essendon EPW)

| Quantity | Value |
|---|---|
| Internal gain, occupants (full load) | **84.0 W** (= 4.2 W/m² × 20 m²) |
| Internal gain, appliances (full load) | **60.0 W** (= 3.0 W/m² × 20 m²) |
| Defective inflation factor | **7.335** = 1 + 5·(1 + (1−0.733)·1) |
| b_ztu per zone | above/below **0.926**, north/south **0.867**, corridor **0.733** |
| Design ventilation H_ve,nat | **48.45 W/K** (declared 2.0 l/s·m², not tabulated 0.5) |
| Envelope infiltration H_ve,inf | mean **5.36 W/K** (range 0.68–10.26) |
| Envelope area a_env used | **88.6 m²** (all surfaces, incl. party walls) |
| q₅₀ (2006-today band) | **4.0 m³/(h·m²)@50 Pa** |
| n₅₀ / mean n_inf | **6.56 /h** / **0.328 /h** (N = 20) |
| Ground-contact area (sog_area) | **0.0 m²** |
| exposed_perimeter after `sanitize(fix=True)` | **1.0 m** (declared 0 → rewritten) |
| Coldest month (implemented, latitude rule) | **7** (July) |
| Coldest month (arg min θ̄ₑ, Essendon) | **7** (July mean 9.85 °C — the minimum) |
| A6 constant-4 m/s test: max |ΔQ_HC| dynamic vs table | **2.2 × 10⁻¹² W** (bit-identical) |
| Sankey closure residual | 0.0 Wh (0.000 %) |

### Text changes the paper requires (produced, not applied)

1. **A1** — Document that infiltration adds a conductance H_ve,inf to H_ve **but its source term
   H_ve,inf·θₑ is not added to S_ve** (so infiltration air is booked as if supplied at 0 °C). The
   sentence "it enters the balance exactly like H_ve,nat" is not what the code does. *Recommend
   fixing the code rather than the paper — see A1.*
2. **A2** — State the engine applies the **declared 2.0 l/(s·m²)** (H_ve,nat = 48.45 W/K), not the
   0.5 l/(s·m²) tabulated `ventilation_rate(min)`; and that EnergyPlus was given the same 2.0
   l/(s·m²) (`DesignSpecification:OutdoorAir, Flow/Area, 0.002`), so the parity input is consistent.
   Note the key read is `flow_rate_per_person`, used as an **area**-normalised rate.
3. **A3** — State that a_env is the **total surface area (88.6 m², party walls included)**, not the
   exterior-exposed area (~13.5 m²). *This over-sizes infiltration ≈6.5× and is a defect — see A3.*
4. **A4** — Replace the "Australian / CSIRO-calibrated q₅₀ bands" description with the **European
   stock table actually coded** (2006-today = 4.0), or complete the recalibration first.
5. **A5** — Report F̄_rel (F_W,diff) = **0.85534** (the **two-pane** default the single-glazed case
   silently resolves to) and the coefficient provenance: fitted to a Fresnel + Beer–Lambert curve
   for **uncoated clear float glass**, *not* the published Karlsson–Roos table.
6. **A7** — State that pyBuildingEnergy uses the **raw 10 m weather-file wind** while EnergyPlus
   applies a **terrain/height correction** (IDF `Building` terrain = *Suburbs*); the two engines
   differ here and it bears on the C2 comparison.
7. **A8** — Correct the inflation expression to **1 + N_adj·(1 + (1−b_ztu)·F_ztc,ztu)** with
   b_ztu = 0.733 (the corridor, i.e. the last adjacent zone left in scope) and F_ztc,ztu = 1,
   which is exactly 7.335. The forms `(1+N_adj)` and `1+Σ[1+(1−b_ztu)]` in the draft are both wrong.
8. **A10** — Correct d_t to match the code (**R_si is omitted**; d_t = w + λ_gr(R_f + R_se)); state
   R_f is **hardcoded 5.3** m²K/W, not read from the slab; and state the validator **rewrites a
   zero exposed_perimeter to 1.0** under `fix=True`.
9. **A11** — State the implementation uses the **latitude-sign rule** (July for φ<0), not
   arg min_m θ̄ₑ; note the two agree (July) for Essendon so the heuristic is correct at this site.
10. **A12** — Describe the latent model as **instantaneous / quasi-static**: no zone humidity state
    x_air is carried between timesteps; x_int is a *reference* (band edge) at the zone temperature.
11. **A14** — Add a thermal-bridge description: H_tb = P·ψ (ISO 13370 ground edge, ψ = 0.05 W/m·K)
    on the sanitiser-fabricated **P = 1 m**; note `construction.thermal_bridges = 1.5` is **ignored**
    by the engine, and that no frame bridge is added, so the whole-window U_win = 5.40 is not
    double-counted.

---

## Part A — Conformance items

### A1. Air exchange — additivity — **DIVERGES** (defect)

**Paper:** H_ve(t) = H_ve,nat(t) + H_ve,inf(t), summed per EN 16798-7; infiltration enters the
balance "exactly like H_ve,nat".

**Code:** the dispatch is genuinely **additive, not if/elif** — the mutually-exclusive `if/elif`
in `ventilation.py:224–398` only selects the *ventilation type* (temp_wind / occupancy / …); the
sum happens one level up. The design term is resolved to a single `VentilationStream`
(`ventilation.py:881–922`) and infiltration is added on top:

- `utils.py:8697` (legacy solver) and `utils.py:10670` (causal solver):
  `H_ve_nat = float(H_ve_nat) + _infiltration_h_ve_inf_w_k(...)`.

So H_ve,nat = 48.45 W/K (design, constant here) and H_ve,inf averages **5.36 W/K** over the year
(range 0.68–10.26) — **non-zero for the case study**, as required.

**Divergence (defect).** When H_ve,inf is added to the conductance, the matching source term
**H_ve,inf·θₑ is never added to S_ve**:

- `utils.py:8685` `S_ve_nat = _vent_bdy.source_term_w` (design streams only),
- `utils.py:8697` adds infiltration to `H_ve_nat` only; `utils.py:8710` stores the **unchanged**
  `S_ve_nat`.
- Balance assembly: LHS `MatA += … + H_ve_nat` (`utils.py:8837`, includes infiltration) but RHS
  `VecB += … + S_ve_nat` (`utils.py:8789`, design only). The Sankey mirrors it:
  `q_vent = H_ve_nat*T_in − S_ve_nat` (`utils.py:9186`).

Since Q_ve = H_ve·θ_int − S_ve, omitting H_ve,inf·θₑ books the infiltration stream as if it entered
at **0 °C** instead of outdoor temperature — an over-stated loss of H_ve,inf·θₑ each hour
(≈5.4 W/K × ~10 °C ≈ 54 W in a Melbourne winter hour). The energy balance still *closes* (solver and
report share the convention), so closure does not catch it.

---

### A2. Occupancy-driven ventilation rate — **CONFORMS** (was OPEN)

**Code:** `ventilation.py:324–340`, occupancy branch:
`flowrate_per_area = _vent_param("flow_rate_per_person", …)` (line 327) →
`qv = flowrate_per_area·A_floor/1000` → `H_ve = ρ·c_air·qv`.

The engine applies the **declared 2.0 l/(s·m²)**, giving **H_ve,nat = 48.45 W/K**
(= 1.204 × 1006 × (2.0 × 20 / 1000)). The tabulated `ventilation_rate(min) = 0.5` in
`table_iso_16798_1.py` is **not** consulted by this path — no override occurs.

- Key read: `flow_rate_per_person`, used for an **area**-normalised quantity (l/s·m²), as the
  audit suspected. Worth stating in the paper.
- Consistency with EnergyPlus: the calibration IDF supplies
  `DesignSpecification:OutdoorAir, Flow/Area, 0.002 m³/s·m²` = 2.0 l/(s·m²) — the same input, so the
  parity table's "2.0" is valid on both sides. No mismatch to invalidate the comparison.

---

### A3. Infiltration derivation — **DIVERGES** (steps conform; envelope area is wrong)

**Code:** `_infiltration_h_ve_inf_w_k` (`utils.py:517–577`). Each paper step is present:

- n₅₀ = q₅₀·A_env/V — `utils.py:555` → **6.56 /h**.
- n_inf = n₅₀/N with **N = 20** (`_LBL_N_DIVISOR`, `utils.py:456,556`) → **0.328 /h**.
- f(t) = √((C_s·|Δθ| + C_w·u²)/reference) with **C_s = 0.015**, **C_w = 0.001** (`utils.py:460–461`),
  normalised to unity at **Δθ_ref = 10 K, u_ref = 4 m/s** (`utils.py:462–463, 572–574`).
- H_ve,inf = ρc_p·V·n_inf(t) with ρc_p/3600 = **0.33 Wh/m³K** (`utils.py:466, 577`).

All confirmed, with the reference-normalisation exactly as the paper states.

**Divergence (defect).** `_envelope_area_m2` (`utils.py:480–488`) sums **every** entry in
`building_surface`, so A_env = **88.6 m²** — it includes the four party walls, the floor and the
ceiling that face *conditioned neighbours*, not outdoor air. Physically only the exterior-exposed
surface (west wall + windows ≈ 13.5 m²) drives infiltration to outdoors. The result over-sizes
H_ve,inf ≈ 6.5× (5.36 W/K where an exterior-only area gives ≈0.8 W/K). The three derivation steps
conform; the **area they are applied to does not "include only the surfaces intended."**

---

### A4. Envelope permeability defaults — **DIVERGES** (expected; PENDING RECALIBRATION)

**Code:** `_Q50_BY_CONSTRUCTION_AGE` (`utils.py:441–451`), self-annotated "Follows the usual
**European stock** ranges" (`utils.py:438–440`). `2006-today → 4.0 m³/(h·m²)@50 Pa`;
`apt305_building.py` (`construction_year: "2006-today"`) resolves to **4.0**
(`_q50_for_construction_age`, `utils.py:469–477`).

The paper claims **Australian CSIRO-calibrated** bands. The table is European. Divergence expected
until the recalibration task runs; recorded so the paper's q₅₀ table is written against what is
implemented (currently 4.0 for the case).

---

### A5. Window transmittance — beam/diffuse split — **CONFORMS**

**Code:** `window_solar_correction_factor` (`utils.py:2759–2807`):
F_W = (F_W,diff·I_dif + F_W,dir(θ)·I_dir·F_sh) / (I_dif + I_dir·F_sh).

- The **angular** factor F_W,dir(θ) (Karlsson–Roos, `karlsson_roos_direct_factor`,
  `utils.py:2744–2756`) is applied to the **beam only**; the **diffuse** stream uses a
  hemispherically-averaged constant F_W,diff (`_window_angular_diffuse_factor`, `utils.py:2724–2741`).
- **Ground-reflected radiation** is bundled into the diffuse total upstream —
  `I_dif_tot = I_dif − I_circum + I_dif_ground` (`utils.py:3541`) — so it receives the **hemispherical**
  factor, exactly as the paper requires (circumsolar is moved to the beam, which is standard).
- **F_fr = 0.25** multiplies the **solar** term only: `… * area_elements[Eli] * (1 − Ffr_wi)`
  (`utils.py:8646`, `Ffr_wi = 0.25` at `utils.py:8614`). Conduction area (U·A) is untouched — no
  reduction of the conduction area.

**Reported values / provenance.** The coefficient sets (`utils.py:2521–2525`) and the diffuse
averages (`utils.py:2532–2536`) were **fitted to a Fresnel + Beer–Lambert curve for uncoated clear
float glass** by `tools/derive_karlsson_roos_coefficients.py` — explicitly **not** the published
Karlsson–Roos table (`utils.py:2511–2518`). `_window_glazing_panes` **defaults to 2**
(`utils.py:2701`) when panes are not declared, and the case declares none, so the single-glazed
window uses the **two-pane** set and **F_W,diff = 0.85534**. Structurally conformant; the paper
should report this diffuse value and the single-vs-double default.

---

### A6. Wind-dependent convection — dual role — **CONFORMS**

**Code:**

- Wind-dependent h_ce is used **only in the hourly external-node boundary**:
  `_compute_h_ce_window_t` (`utils.py:8150–8203`), consumed at `utils.py:8823` in the matrix assembly.
- It is applied **only to `Type_eli == "EXT"`** surfaces (`utils.py:8184` `if Type_eli != "EXT":
  continue`), so **ground-contact and adiabatic elements are excluded**.
- The **construction resistance keeps the fixed film**: `Conductance_node_of_element`
  (`utils.py:3977–3982`) derives R_c from the **table** h_ce/h_re (`r_se = 1/(h_ce+h_re)`), never the
  wind value; GR elements skip r_se entirely (`utils.py:3972–3975`). The ISO 13370 equivalent
  thickness likewise uses the fixed **R_se = 0.04** (`utils.py:4182, 4378`), not wind.
- **Verification test.** Forcing constant wind = 4.0 m/s and comparing the default dynamic
  (`simplecombined`, h_ce = 4 + 4v = 20 at 4 m/s) against the table run gives
  **max |ΔQ_HC| = 2.2 × 10⁻¹² W** (annual heating identical to 5 dp, 171.7406 kWh both) — bit-identical
  to floating-point noise.

---

### A7. Wind-speed height correction — **CONFORMS** (code) — flag for C2

**Code:** the weather-file wind is read raw (`WS10m_arr = _series_to_float_array(sim_df,"WS10m")`,
`utils.py:8464`; used at `utils.py:8178`). A grep of the engine finds **no** power-law, terrain, or
height adjustment anywhere — a = 0 implied, as the paper states.

**C2 implication.** EnergyPlus **does** apply a terrain/height correction by default; the calibration
IDF sets `Building … Suburbs …`, so EnergyPlus scales the 10 m met wind to a local surface wind. The
two engines therefore differ on wind exposure, and the paper must say so where it discusses C2.

---

### A8. Internal gains — the inflation and its removal — **CONFORMS**

**Derivation of 7.335.** The defective loop (documented in the source, `ventilation.py:634–646`) was
`Phi += Phi_dir + (1−b_ztu)·F_ztc·Phi_dir` **per adjacent zone**, multiplying the zone's own gain by

  1 + N_adj·(1 + (1 − b_ztu)·F_ztc,ztu)

with the caller leaving **b_ztu = 0.733** (the corridor, the last adjacent zone in scope) and
**F_ztc,ztu = 1** (`utils.py:4599`). Then **1 + 5·(1 + 0.267·1) = 7.335** — reproduced exactly. The
draft's `(1+N_adj)=6.0` and `1+Σ[1+(1−b_ztu)]=6.68` are both wrong because they use neither the
surviving corridor b_ztu nor the multiplicative (rather than additive) structure.

**Corrected engine** (`ventilation.py:661`): `Phi_int_z_t = q_int_total · a_use`, no inflation. Run
returns **84.0 W** occupants and **60.0 W** appliances (4.2 and 3.0 W/m² × 20 m² from the ISO table),
i.e. the 616.14 / 440.10 W figures are recovered by ×7.335.

**No double-counting.** A neighbour's own gains are computed separately (`phi_gn_dir_ztu`) and enter
only through the buffer temperature θ_ztu (`utils.py:918–920`), never re-added to Φ_int. Confirmed.

*(Note: the case's `full_load` overrides live under `building_parameters.internal_gains`, whereas the
override reader looks at top-level `internal_gains` (`ventilation.py:611`); the override is therefore
inert and the ISO-table 4.2/3.0 are used — which is exactly why the run yields 84/60 W.)*

---

### A9. Adjacent-zone boundary condition — **CONFORMS**

**Code:**

- b_ztu = H_ue/(H_ue + H_iu) — `utils.py:4586`. Values reproduced: above/below **0.926**,
  north/south **0.867**, corridor **0.733**.
- **Sign:** `_theta_ztu_unconditioned` (`utils.py:908–920`)
  θ_ztu = θ_int − b_ztu·(θ_int − θₑ) + φ/H → as b_ztu → 1 the neighbour tracks **θₑ (outdoor)**. Correct.
- **Conditioned branch bypasses the buffer:** `utils.py:8862–8871` (single) and `utils.py:8885–8888`
  (multi) set θ_ztu = declared setpoint and `continue`, with **no blending**. All five neighbours in
  the case are `conditioned: True, setpoint: 20`, so they are held at 20 °C.
- The unconditioned branch reads **b_ztu per zone** (`utils.py:8895`), fixing the "last zone's scalar"
  bug.
- **Baseline:** `conditioned`/`setpoint` default to False/None (`_adjacent_zone_conditioning`,
  `utils.py:865–866`); with the flags absent every zone runs through the buffer — the baseline has no
  conditioned branch, as the paper states (see also B1).

---

### A10. Ground coupling — guard and U-value branches — **DIVERGES**

**Code:** `Temp_calculation_of_ground` (`utils.py:4181–4469`).

- **Denominator πB' + d_t (not π(B'+d_t)):** `utils.py:4383–4388` —
  `2λ/(π·B' + d_t)·ln(π·B'/d_t + 1)`. **Correct.**
- **Well-insulated branch d_t ≥ B':** `utils.py:4389–4390` `λ/(0.457·B' + d_t)`. **Present.**
- **Guard:** `_ground_contact_area` (`utils.py:1247–1305`) returns **0.0** for Apt 305 — no surface
  declares `boundary="GROUND"` / `ISO52016_type_string="GR"`, and legacy sky-view inference is
  opt-in (off). *Which condition fails:* the floor and ceiling are typed `adjacent` with a
  `name_adj_zone` (party slabs), so neither the explicit-tag nor the ISO-type test matches. Ground
  conductance is therefore inert for the case. **Confirmed.**

**Divergences:**

1. **d_t omits R_si.** `utils.py:4378`:
   `equivalent_ground_thickness = wall_thickness + λ_gr·(thermal_resistance_floor + R_se)`. The
   paper's d_t = w + λ_gr·(**R_si** + R_f + R_se). R_si (= 0.17, `utils.py:4182`) is **not** included
   — the "previously omitted" R_si is still omitted.
2. **R_f is hardcoded, not read from the slab.** `thermal_resistance_floor = 5.3` (`utils.py:4374`),
   independent of the declared floor construction.
3. **The validator substitutes a non-zero perimeter.** `check_input.py:167–169`: with `fix=True` a
   zero `exposed_perimeter` is rewritten to `max(eps,1.0) = 1.0`. Apt 305 declares 0 and the scoring
   path calls `sanitize(fix=True)`, so P = **1.0** downstream. This contradicts the audit's
   "does not substitute". Its only live effect on Apt 305 is the thermal bridge P·ψ (see A14), since
   sog_area·U_sog = 0.

All three are inert for the case's demand except the perimeter→bridge, but they are equation-level
mismatches the paper must not assert.

---

### A11. Coldest month — **DIVERGES** (latitude rule implemented, not arg min)

**Code:** `_resolve_coldest_month` (`utils.py:791–828`): an explicit
`building_parameters.coldest_month` wins, else **latitude sign** — `latitude < 0 → July (7)`,
else January (`utils.py:828`). It is **not** arg min_m θ̄ₑ.

The case's `coldest_month: 7` sits under `building_parameters.**climate_parameters**.coldest_month`,
not the `building_parameters.coldest_month` key the resolver reads, so the explicit path is not
taken and the **latitude rule governs** → returns **7**.

**arg min for Essendon:** monthly-mean θₑ minimum is **July (9.85 °C)**, so arg min = **7** as well —
the heuristic happens to be correct for this site. The paper should state the latitude rule is what
runs, and that it coincides with arg min here.

---

### A12. Latent conditioning — **CONFORMS** (OPEN resolved)

**Code:** `_latent_heat_load_from_air_exchange` (`utils.py:57–151`) + post-processing
(`utils.py:9526–9637`).

- **RH band → humidity ratio at the zone temperature:** band edges are converted with
  `_humidity_ratio_from_t_rh(θ_int, RH)` (`utils.py:123–124`), i.e. RH-based, evaluated at the
  prevailing zone temperature — not fixed absolute humidity ratios. Band limits (25/60 %) are read
  from the ISO table (`min/max_relative_humidity`, `utils.py:9532–9535`).
- **Psychrometrics:** p_sat = 610.94·exp(17.625·T/(T+243.04)) (Magnus/Alduchov–Eskridge,
  `utils.py:44–46`); x = ε_w·p_w/(p−p_w) (`utils.py:49–54`); latent heat **h_fg = L_V = 2.501×10⁶
  J/kg**, c_p,da = 1005, P = 101325 (`utils.py:38–40`).
- **Timestep inferred, not hardcoded:** `dt_h = Dtime[Tstepi]/3600` in the loop (`utils.py:9159`) and
  `_infer_timestep_hours_from_index(...)` in post-processing (`utils.py:9526`); for the hourly EPW,
  **dt_h = 1.0**.
- **Evaporative sign reversed:** `if evaporative_cooling: latent_power_w = −latent_power_w`
  (`utils.py:140–141`), selected by `cooling_system_type == "evaporative"` (`utils.py:9536–9541`).
- **Plant gate:** latent cooling is charged only when the sensible cooling plant runs —
  `Q_latent_W = where(Q_C>0, …, 0)` (`utils.py:9621, 9634`); latent heating gated on Q_H symmetrically
  (`utils.py:9636`). Occupant moisture uses the tabulated 2.12 g/(m²·h) (`_occupancy_latent_gain_w`,
  `utils.py:154–196`).
- **OPEN resolved:** zone humidity is **not** advanced as a state variable — there is no x_air carried
  between timesteps; x_int is a *reference* (band edge) recomputed each hour from the zone temperature
  and outdoor air. The model is **instantaneous / quasi-static**, and the paper must describe it as such.

---

### A13. Energy-balance closure — **CONFORMS**

**Code:** per-timestep Sankey accumulation (`utils.py:9155–9348`), close-out (`utils.py:9362–9448`).

- **All seven surfaces traversed, incl. the five ADJ:** the transmission loop runs `for Eli in
  range(bui_eln)` over `OP, W, ADJ, GR` (`utils.py:9273–9275`); ADJ surfaces are tallied via the same
  boundary temperature the solver used (`utils.py:9290–9305`).
- **Outer-face / sol-air convention:** transmission is read at the **external node**
  `T_se = VecB[row_ext]` (`utils.py:9279–9280`) and netted against absorbed short-wave `q_cond −=
  q_sol_eli` (`utils.py:9317–9321`). The control volume is the zone air **plus** the envelope nodes
  (the span of `C_state`), stated at `utils.py:9234–9238`.
- **Residual excluded from outputs:** `outputs_Wh` sums cooling + ventilation + bridges + ground +
  transmission only (`utils.py:9380–9386`); the residual is computed separately
  (`utils.py:9389`) and, when < 1 % of inputs, absorbed into storage with the **pre-absorption** value
  preserved in the `closure` block (`utils.py:9392–9394, 9437–9442`). It is surfaced in the Sankey as
  a distinct "Transmission (residual)" arrow only when non-zero (`utils.py:9418–9419`), never folded
  into the outputs sum. Run residual: **0.000 %**.

---

### A14. Thermal bridges — **OPEN** (implemented, undocumented)

The paper carries no thermal-bridge description; here is what runs.

- **H_tb = P·ψ** (ISO 13370 ground-edge bridge): `thermal_bridge_heat = exposed_perimeter · psi_k`
  (`utils.py:4402`, `psi_k = 0.05` default, `utils.py:4182`). It enters the real solver
  (`MatA += … + thermal_bridge_heat`, `utils.py:8836`; RHS `… · T2m`, `utils.py:8788`) and the Sankey
  (`utils.py:9202`). For Apt 305 P is the **sanitiser-fabricated 1.0 m** (A10), so H_tb = 0.05 W/K →
  the **≈2 kWh** bridge the Sankey shows is an artefact of that rewrite, not a declared bridge.
- **`construction.thermal_bridges = 1.5` is ignored.** The declared value is never read by the engine
  (only `thermal_bridge_heat` from the perimeter is used); a grep finds no consumer.
- **No frame bridge / no double count.** The only `frame` term is `frame_area_fraction`
  (`utils.py:6108`, `8614`), applied to the **solar** area alone. No frame *conduction* bridge is
  added, so the whole-window **U_win = 5.40** (applied as U·A over the full window area, conduction not
  reduced by the frame fraction) is not double-counted. The declared U_win therefore follows the
  **whole-window** convention and is used consistently.

---

## Part B — Claims

1. **Baseline routes all adjacent zones through the ISO 13789 buffer, no conditioned branch —
   CONFIRMED.** The conditioned branch is gated on `conditioned` (default False,
   `utils.py:865`); with the flags absent every zone falls to `_theta_ztu_unconditioned`
   (`utils.py:8872–8876, 8896–8899`). The branch is the AIB addition; baseline behaviour is
   all-through-buffer.
2. **Inflation vanishes with no adjacent zones — CONFIRMED.** The defective factor
   1 + N_adj·(…) is 1 at N_adj = 0; single-zone cases take the `adj_zones_present == False` path
   (`utils.py:8768–8776`, `int_gains_conditioned_zone`) which never carried the loop. Hence single-zone
   tests never exposed it.
3. **Latent deadband collapses to the single setpoint when band limits are undefined — CONFIRMED.**
   `utils.py:114–117`: with both `rh_int_min/max` None the code books
   `mass·L_V·(x_ext − x(θ_int, rh_int_pct))`, i.e. the previous single-reference behaviour. The
   correction generalises rather than replaces.
4. **Ground-contact correction has no effect on Apt 305 conditioning energy (reporting path only) —
   CONFIRMED.** Apt 305 has no GR element, so ground never enters the solver; the lumped
   `h_ground·(T_in − T_gr)` term lives in the Sankey block (`utils.py:9214–9230`) and is 0 because
   sog_area = 0. Demand is untouched.
5. **Hemisphere (coldest-month) correction has no effect on Apt 305 because ground area is zero —
   CONFIRMED.** The coldest month only phases the ISO 13370 ground sinusoids; with sog_area = 0 those
   terms drive no flux into the zone, so the July-vs-January choice cannot change demand.
6. **Closure corrections change what the balance measures, not what the engine computes;
   +Closure ≡ +Hemisphere demand — CONFIRMED.** The closure/latent machinery is post-processing over
   the already-solved series: sensible `Q_C_sensible = Q_C` (`utils.py:9647`) and Q_H are the solver's
   outputs, untouched by the Sankey accumulation or the latent overlay. The sensible demand is
   identical across the two states.

---

*Generated by a code-reading + instrumented-run audit on the Essendon EPW. No `.tex` or engine
source was modified.*
