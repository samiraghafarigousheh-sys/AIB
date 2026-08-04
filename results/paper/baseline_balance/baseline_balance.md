# Annual energy balance — Baseline

**V2 closure residual -96.72 kWh (-1.16 % of inputs) — PASS against the 5 % gate.** **7 transmission line items — PASS.** **Independent re-integration PASS (0.0000 %).**

Apt 305, 50 Barry St Carlton, 20 m². Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. Inventory taken from the closure-capable instrument, not from the annual balance columns.

The residual is computed exactly as the engine's own `SANKEY CHECK` line does:

```
inputs   = heating + internal gains + solar & free-gain
outputs  = cooling + ventilation + thermal bridges + ground
           + per-surface transmission (positive branches only)
residual = inputs - outputs - storage
```

`Transmission (residual)` is **excluded** from the outputs sum. It is the residual re-published as a flow, and including it would make the balance close by construction — the diagram could then never fail, which would make it useless as a check.

![energy balance](baseline_balance_sankey.png)

## Inputs

| Term | kWh | % of inputs |
| --- | ---: | ---: |
| Internal gains | 5,356.69 | 64.5 % |
| Heating | 1,779.36 | 21.4 % |
| Solar & free-gain | 1,169.51 | 14.1 % |
| **Total in** | **8,305.56** | **100.0 %** |

## Outputs

| Term | kWh | % of inputs |
| --- | ---: | ---: |
| Ventilation (losses) | 2,031.91 | 24.5 % |
| Transmission - East wall to corridor | 1,109.04 | 13.4 % |
| Transmission - Floor to Apt 205 | 1,057.82 | 12.7 % |
| Transmission - Ceiling to Apt 405 | 1,057.82 | 12.7 % |
| Transmission - North wall to Apt 306 | 819.91 | 9.9 % |
| Transmission - South wall to Apt 304 | 819.91 | 9.9 % |
| Cooling (extracted energy) | 640.84 | 7.7 % |
| Transmission - West exterior wall (opaque) | 429.61 | 5.2 % |
| Transmission - West window - fixed + West window - operable | 334.33 | 4.0 % |
| Ground | 98.98 | 1.2 % |
| Thermal bridges | 2.10 | 0.0 % |
| **Total out** | **8,402.28** | **101.2 %** |

| | kWh | % of inputs |
| --- | ---: | ---: |
| Energy accumulated in the zone (storage) | +0.00 | +0.00 % |
| **V2 closure residual** | **-96.72** | **-1.16 %** |

## The transmission inventory

The five party surfaces are 75.10 m², 88.6 % of the envelope UA. Before the closure fixes they appeared on neither side of this balance and the inventory listed two line items for a building with seven surfaces. It now lists **7**.

| Surface | kWh |
| --- | ---: |
| East wall to corridor | 1,109.04 |
| Floor to Apt 205 | 1,057.82 |
| Ceiling to Apt 405 | 1,057.82 |
| North wall to Apt 306 | 819.91 |
| South wall to Apt 304 | 819.91 |
| West exterior wall (opaque) | 429.61 |
| West window - fixed + West window - operable | 334.33 |
| **Σ reported** | **5,628.46** |
| Σ independently re-integrated from the hourly frame | 5,628.46 |

The two come from different code paths — the reported figure from the in-loop accumulator, the independent one re-integrated from the hourly frame afterwards — and agree to 0.0000 %, inside the 0.1 % consistency check.

