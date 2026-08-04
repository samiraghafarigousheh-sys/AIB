# Tables 4 and 5 — where each one comes from

The methodology text must cite these correctly, so the decision is recorded here rather than left to be inferred from the file names.

| Table | Source | Extra engine runs | File |
| --- | --- | ---: | --- |
| **4** — window / h_ce | **Part 2 trajectory, states 1–3** | 0 | `table4_window_hce.{csv,md}` |
| **5a** — ventilation + latent, methodology order | **Part 2 trajectory, states 3–5** | 0 | `table5a_methodology_order.{csv,md}` |
| **5b** — ventilation + latent, isolated 2×2 | separate 4-state run, same baseline and same instrument | 3 | `table5b_isolation_2x2.{csv,md}` |

## Why Table 5 needed a second source and Table 4 did not

Table 4's three states *are* the trajectory's first three states, and the instrument already emits every column it needs — sensible heating and cooling, solar gains, and the window/opaque transmission split. Deriving it costs nothing and guarantees the paper's Table 4 and its trajectory rows are the same measurements rather than two runs that happen to agree.

Table 5 is a **2×2 isolation** experiment: it exists to show that the two fixes separate on the sensible side and interact on the latent side. The trajectory is **cumulative**, so it contains `+C2 → +Ventilation → +Latent` and structurally cannot contain *the latent fix without the ventilation fix*. That fourth cell is the whole point of the table.

**The obvious fallback does not fix this.** Re-running the six-state closed-balance harness on Essendon would not supply the missing cell either: its second state is `+Vent+Latent`, the two fixes already combined. So the isolated states were measured directly, from the same vendored baseline, with the same closure commits back-ported — the same instrument as Part 2, not a second one.

Both forms are emitted. **Cite 5a if the results text is written in methodology order** (what each fix adds where the methodology applies it); **cite 5b for the interaction claim** (whether the two fixes are separable). They answer different questions and their columns are not interchangeable.

## What the 2×2 shows on the clean file

* Sensible side: the latent fix alone moves sensible heating not at all — the two fixes separate cleanly there.
* Latent cooling: Base 26.12 → ventilation alone 26.40 → latent alone 18.21 → both 16.37 kWh.
* **Interaction term: -2.12 kWh** — the effect of both together minus the sum of the two separately. Non-zero means the fixes are not additive on the latent side, which is the claim the table is for.

## Guardrails

* weather: `/home/user/AIB/weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw`
* trajectory source: `/home/user/AIB/results/paper/canonical_trajectory/trajectory_raw.json`
* closure base pinned to `978db37` and the resolved set asserted
* every state reports through the closure-capable instrument, so the V2 residual and the transmission inventory are comparable across both tables

