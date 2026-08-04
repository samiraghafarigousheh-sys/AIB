# The closure gate across the trajectory

**V2 residual < 5 % on every state: PASS.** **7 transmission line items on every state: PASS.** **Independent re-integration within 0.1 %: PASS.**

Weather `AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`. Read from the Part 2 trajectory's raw output — no re-measurement.

![residual by state](residual_by_state.png)

| State | Inputs (kWh) | Outputs (kWh) | Storage (kWh) | V2 residual (kWh) | V2 residual (%) | < 5 %? | Transmission items | Re-integration error |
| --- | ---: | ---: | ---: | ---: | ---: | :-: | ---: | ---: |
| Baseline | 8,305.56 | 8,402.28 | 0.00 | -96.72 | -1.16 % | PASS | 7 | 0.0000 % |
| +C1 dynamic window | 8,195.65 | 8,291.62 | 0.00 | -95.97 | -1.17 % | PASS | 7 | 0.0000 % |
| +C2 wind-dependent h_ce | 8,148.11 | 8,243.80 | 0.00 | -95.69 | -1.17 % | PASS | 7 | 0.0000 % |
| +Ventilation | 8,386.98 | 8,476.32 | 0.00 | -89.34 | -1.07 % | PASS | 7 | 0.0000 % |
| +Latent | 8,386.98 | 8,476.32 | 0.00 | -89.34 | -1.07 % | PASS | 7 | 0.0000 % |
| +Internal gains | 5,880.76 | 5,946.61 | 0.00 | -65.85 | -1.12 % | PASS | 7 | 0.0000 % |
| +Conditioned zones | 3,971.49 | 4,048.51 | 0.00 | -77.02 | -1.94 % | PASS | 7 | 0.0000 % |
| +Ground contact | 3,970.29 | 3,970.29 | -0.00 | +0.00 | +0.00 % | PASS | 7 | 0.0000 % |
| +Hemisphere | 3,970.29 | 3,970.29 | -0.00 | +0.00 | +0.00 % | PASS | 7 | 0.0000 % |
| +Closure fixes | 3,970.29 | 3,970.29 | -0.00 | +0.00 | +0.00 % | PASS | 7 | 0.0000 % |

Largest excursion: **-1.94 %** at *+Conditioned zones*. From `+Ground contact` onward the residual is machine-zero — that fix removes the phantom ground term, which is the only thing the earlier states had left to shed.

The three conditions are not interchangeable. A small residual on an inventory that is missing 88.6 % of the envelope UA would be a balance that closes over the wrong control volume, which is exactly the state this whole effort started from — hence the line-item count and the independent re-integration are checked alongside it.

