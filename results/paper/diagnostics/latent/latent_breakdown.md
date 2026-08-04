# The latent gate

**Latent charged with the plant off, or while heating: zero on every state — PASS.**

Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. All numbers read from the Part 2 trajectory's raw output — no re-measurement.

![latent breakdown](latent_breakdown.png)

## Per state

| State | Cooling on (h) | Heating on (h) | Latent charged (h) | Gated (kWh) | Ungated (kWh) | Removed by the gate (kWh) | Charged, plant off | Charged while heating | Latent heating (kWh) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 851 | 2,790 | 178 | 26.12 | 900.05 | 873.93 | 0.000000 | 0.000000 | 152.6506 |
| +C1 dynamic window | 834 | 2,808 | 173 | 25.34 | 905.27 | 879.93 | 0.000000 | 0.000000 | 152.7140 |
| +C2 wind-dependent h_ce | 813 | 2,817 | 171 | 25.02 | 906.29 | 881.27 | 0.000000 | 0.000000 | 152.9055 |
| +Ventilation | 713 | 3,052 | 154 | 24.93 | 1,068.20 | 1,043.27 | 0.000000 | 0.000000 | 174.1352 |
| +Latent | 713 | 3,052 | 673 | 15.38 | 593.69 | 578.31 | 0.000000 | 0.000000 | 0.0033 |
| +Internal gains | 371 | 4,554 | 341 | 7.66 | 887.80 | 880.14 | 0.000000 | 0.000000 | 0.0140 |
| +Conditioned zones | 33 | 726 | 30 | 0.78 | 670.74 | 669.96 | 0.000000 | 0.000000 | 0.0000 |
| +Ground contact | 33 | 726 | 30 | 0.78 | 670.74 | 669.96 | 0.000000 | 0.000000 | 0.0000 |
| +Hemisphere | 33 | 726 | 30 | 0.78 | 670.74 | 669.96 | 0.000000 | 0.000000 | 0.0000 |
| +Closure fixes | 33 | 726 | 30 | 0.78 | 670.74 | 669.96 | 0.000000 | 0.000000 | 0.0000 |

`Ungated` is the zone moisture balance before the plant-on gate. It is a **diagnostic contrast column and never part of any total** — it is shown so the size of what the gate removes is visible rather than implied.

## Southern-hemisphere phase, canonical state

| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.57 | 0.04 | 0.03 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.03 | 0.10 |

Dec–Feb 0.72 kWh against Jun–Aug 0.00 kWh. A gate built around a northern-hemisphere cooling season would put the load in the middle of this table; it does not.

