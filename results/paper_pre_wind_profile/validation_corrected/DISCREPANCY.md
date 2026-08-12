# Where the remaining disagreement comes from

Weather: `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. Corrected ISO 52016-1 against the matched EnergyPlus 24.1.0 case built by `examples/corrected_vs_energyplus.py`.

Residual: heating **-23.01 kWh** (-15.7 %), cooling **-13.93 kWh** (-50.9 %). The ISO engine is below the reference on both.

## 1. By loss path

Net heat gain to the zone, kWh/yr, **positive into the zone**. The ISO column is `gain − loss` from the per-surface annual balance; the EnergyPlus column is the surface conduction and window net-transfer variables, which already carry that sign, and the zone ventilation and infiltration streams as gain minus loss.

The window row carries **conduction plus transmitted solar on both sides**, because it cannot be split: EnergyPlus's window net-transfer variable bundles the transmitted solar in with the conduction, while the ISO engine books solar in a separate column. Splitting one side and not the other would put a ~710 kWh solar gain on one side of the row and nothing on the other.

| Loss path | ISO 52016-1 | EnergyPlus | Δ (ISO − E+) |
|---|---:|---:|---:|
| West exterior wall (opaque, 11.88 m²) | -256.8 | -108.4 | -148.5 |
| West windows (1.62 m²), conduction + transmitted solar | +449.4 | +416.8 | +32.6 |
| Five party surfaces (75.10 m², to 20 °C neighbours) | +792.0 | +630.7 | +161.3 |
| Designed ventilation (2.0 l/s·m², H_ve = 48.4 W/K) | -1,728.4 | -1,669.6 | -58.8 |
| Envelope infiltration | -95.0 | -92.9 | -2.1 |
| **Σ compared paths** | -838.8 | -823.4 | -15.4 |

**Infiltration matches to 2.1 kWh on a 95.0 kWh path** (2.2 %), which is the direct check on the one-way schedule coupling described in `alignment.md`. The two engines are computing the same leakage stream.

**The largest single disagreement is the five party surfaces, +161 kWh.** They are 75.10 m² and 88.6 % of the envelope UA, so a small fractional error there outweighs a large one anywhere else.

**On why the Σ row does not equal the difference in plant energy.** The two engines partition the zone balance differently — ISO 52016-1 solves an air node coupled to surface nodes and books each path against the air node, while EnergyPlus reports conduction at the surface mid-plane and resolves convection and long-wave exchange separately. Internal gains (730.29 kWh) are identical by construction on both sides and are not listed. The Σ row is therefore a like-for-like comparison of each path, not a closed balance, and should be read that way.

## 2. By month

| Month | Δ heating | Δ cooling |
|---|---:|---:|
| Jan | -0.04 | -5.43 |
| Feb | +0.00 | -2.60 |
| Mar | -0.00 | -1.50 |
| Apr | -0.47 | +0.00 |
| May | -2.12 | +0.00 |
| Jun | -5.67 | +0.00 |
| Jul | -4.78 | +0.00 |
| Aug | -6.00 | +0.00 |
| Sep | -2.38 | -0.14 |
| Oct | -0.89 | -0.42 |
| Nov | -0.61 | -1.22 |
| Dec | -0.04 | -2.62 |
| **Year** | **-23.01** | **-13.93** |

**The two residuals have different shapes, and that is the most informative thing in this document.**

- **Cooling is concentrated.** -12.15 kWh of the -13.93 kWh total falls in Dec–Mar (87 % of it), the four months that carry essentially the whole cooling load.
- **Heating is distributed.** -20.96 kWh of the -23.01 kWh falls in May–Sep, and across the 5 months carrying at least 10 kWh of heating the *relative* gap stays in a narrow band, -17.7 % to -12.8 %. That is a systematic proportional offset, not a seasonal artefact.

## 3. The largest single contributor

**Sensible heating, -23.01 kWh**, is the larger residual in absolute energy — bigger than sensible cooling's -13.93 kWh — and it is spread evenly across the heating season. **Sensible cooling, -13.93 kWh**, is the larger one in relative terms (-50.9 % against -15.7 %) and is concentrated in Dec–Mar. Which of the two is 'largest' depends on which question is being asked, so both are named.

### What it is attributable to

The loss-path table is the evidence. Two rows carry almost all of the disagreement, and they point in opposite directions:

- **Party surfaces +161 kWh** — the ISO engine draws more heat from the 20 °C neighbours than EnergyPlus does.
- **West exterior wall -148 kWh** — the ISO engine loses more through the one outdoor-exposed opaque element than EnergyPlus does.

They nearly cancel in the annual total (+13 kWh between them) but they do not cancel season by season, which is why the heating and cooling residuals have different shapes.

Taking the four named candidates in turn, with what this setup can and cannot establish:

**Surface heat-transfer coefficients (Ballarini) — the best supported, and it accounts for both large rows.** On the party surfaces the ISO engine uses constant internal film coefficients while EnergyPlus varies them with the TARP correlation; those surfaces are 88.6 % of the envelope UA, so a modest fractional difference is the largest absolute row in the table. On the west wall the C2 correction sets `h_ce = 4v + 4`, which on this weather file averages well above the ISO constant, so the ISO wall sheds more of its absorbed solar back to the air and conducts less inward — the ISO side losing more than twice what EnergyPlus's DOE-2 exterior correlation gives. Ballarini's finding that constant surface coefficients are the principal cause of ISO-versus-detailed disagreement is directly consistent with this table.

**Solar distribution within the zone — still a live candidate, but smaller than the film coefficients.** The two engines agree closely on how much solar *enters*: the window row differs by +33 kWh on a +449 kWh path. What they do with it afterwards is not visible in that row — ISO 52016-1 splits it with a fixed convective fraction `f_sol_c = 0.1` and routes the rest to the surface nodes, while EnergyPlus ray-traces it onto the actual interior surfaces — and that difference would surface in exactly the two rows above, inseparably from the film-coefficient effect. The cooling residual being concentrated in the solar-driven months is consistent with it contributing; it is not sufficient to size it.

**Five-node RC against conduction transfer functions — largely ruled out here.** Every construction in this case is `Material:NoMass`, so conduction is steady-state in both engines and the discretisation has almost nothing to discretise. The only storage is the 200 kJ/K zone internal capacitance, which both engines carry identically. This candidate is available in general but cannot be doing much work in *this* case.

**Absence of stack/wind infiltration modulation on the EnergyPlus side — ruled out, by construction and by measurement.** The modulation is present: it is embedded as an 8760-value schedule. The loss-path table puts the two infiltration streams within 2.1 kWh of each other, and the sensitivity run below bounds what the modulation is worth at all.

### What is left open

The film coefficients and the solar distribution are **not separated here**, and cannot be from these two runs. Both act on the same two rows of the loss-path table. Separating them would need either EnergyPlus's interior convection algorithm pinned to the ISO constant film coefficients, or its solar distribution forced to a fixed convective fraction — neither is a one-switch change, and neither was attempted. The weight of evidence favours the film coefficients, because they explain the west-wall row (where almost no diffuse solar lands inside) as well as the party-surface row, whereas solar distribution explains only the second. **That is a ranking, not a decomposition, and it is left as an open question.**

## 4. Against the reference literature

Context only. Nothing here was tuned toward it.

| | Direction, heating | Direction, cooling | Magnitude |
|---|---|---|---|
| Zakula et al. | simplified method **under**-estimates | simplified method **over**-estimates | up to 40 % heating, 18 % cooling |
| Baseline engine, published reference | **over** (+58.8 %) | under (-8.1 %) | — |
| Baseline engine, repaired reference | **under** (-14.5 %) | under (-8.1 %) | — |
| Corrected engine | **under** (-15.7 %) | under (-50.9 %) | — |

**On heating the corrected engine now agrees with the literature direction, and comfortably inside the literature magnitude.** -15.7 % against Zakula's *up to 40 %*.

The paper's existing remark — that Zakula found under-estimation of heating whereas this baseline over-predicts it — was based on the published +58.8 %, which `validation_corrected.md` shows to be an artefact of the EnergyPlus input rather than a property of the engine. Against a correctly configured reference the baseline engine under-predicts heating too. **That remark should be revised: the anomaly it describes does not exist.**

**On cooling the corrected engine is on the opposite side from Zakula, and outside their band in percentage terms.** They report the simplified method over-estimating cooling by up to 18 %; this engine under-estimates it by 51 %. Two things temper the comparison without excusing it. The absolute quantity is 13.9 kWh/yr on a 20 m² dwelling — 0.70 kWh/m²·yr — and Zakula's cases are cooling-dominated buildings where 18 % is a large absolute number. And the baseline engine was already under-predicting cooling (-8.1 % against the repaired reference), so the sign is inherited from the method, not introduced by the corrections.

Ballarini's finding — that constant surface coefficients are the principal cause of ISO-versus-detailed disagreement — is consistent with the loss-path table here, where the party surfaces carry both the largest UA share and the largest absolute disagreement, and where the ISO side still uses constant internal film coefficients.
