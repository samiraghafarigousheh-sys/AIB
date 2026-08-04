# Annual energy balance — +C2 wind-dependent h_ce

**V2 closure residual -95.69 kWh (-1.17 % of inputs) — PASS against the 5 % gate.** **7 transmission line items — PASS.** **Independent re-integration PASS (0.0000 %).**

Apt 305, 50 Barry St Carlton, 20 m². Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. Inventory taken from the closure-capable instrument, not from the annual balance columns.

The residual is computed exactly as the engine's own `SANKEY CHECK` line does:

```
inputs   = heating + internal gains + solar & free-gain
outputs  = cooling + ventilation + thermal bridges + ground
           + per-surface transmission (positive branches only)
residual = inputs - outputs - storage
```

`Transmission (residual)` is **excluded** from the outputs sum. It is the residual re-published as a flow, and including it would make the balance close by construction — the diagram could then never fail, which would make it useless as a check.

![energy balance](c2_wind_hce_sankey.png)

## Inputs

| Term | kWh | % of inputs |
| --- | ---: | ---: |
| Internal gains | 5,356.69 | 65.7 % |
| Heating | 1,788.11 | 21.9 % |
| Solar & free-gain | 1,003.32 | 12.3 % |
| **Total in** | **8,148.11** | **100.0 %** |

## Outputs

| Term | kWh | % of inputs |
| --- | ---: | ---: |
| Ventilation (losses) | 2,010.58 | 24.7 % |
| Transmission - East wall to corridor | 1,089.80 | 13.4 % |
| Transmission - Floor to Apt 205 | 1,040.25 | 12.8 % |
| Transmission - Ceiling to Apt 405 | 1,040.25 | 12.8 % |
| Transmission - North wall to Apt 306 | 804.58 | 9.9 % |
| Transmission - South wall to Apt 304 | 804.58 | 9.9 % |
| Cooling (extracted energy) | 580.77 | 7.1 % |
| Transmission - West exterior wall (opaque) | 436.69 | 5.4 % |
| Transmission - West window - fixed + West window - operable | 336.23 | 4.1 % |
| Ground | 97.98 | 1.2 % |
| Thermal bridges | 2.07 | 0.0 % |
| **Total out** | **8,243.80** | **101.2 %** |

| | kWh | % of inputs |
| --- | ---: | ---: |
| Energy accumulated in the zone (storage) | +0.00 | +0.00 % |
| **V2 closure residual** | **-95.69** | **-1.17 %** |

## The transmission inventory

The five party surfaces are 75.10 m², 88.6 % of the envelope UA. Before the closure fixes they appeared on neither side of this balance and the inventory listed two line items for a building with seven surfaces. It now lists **7**.

| Surface | kWh |
| --- | ---: |
| East wall to corridor | 1,089.80 |
| Floor to Apt 205 | 1,040.25 |
| Ceiling to Apt 405 | 1,040.25 |
| North wall to Apt 306 | 804.58 |
| South wall to Apt 304 | 804.58 |
| West exterior wall (opaque) | 436.69 |
| West window - fixed + West window - operable | 336.23 |
| **Σ reported** | **5,552.39** |
| Σ independently re-integrated from the hourly frame | 5,552.39 |

The two come from different code paths — the reported figure from the in-loop accumulator, the independent one re-integrated from the hourly frame afterwards — and agree to 0.0000 %, inside the 0.1 % consistency check.

