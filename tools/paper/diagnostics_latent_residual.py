"""
Part 4 — the latent breakdown and the residual-by-state figures.

Both are read out of the Part 2 trajectory's ``trajectory_raw.json``. No engine
run: every number here was already measured by the closure-capable instrument
during the trajectory, and re-measuring would be a second chance for the paper's
figures to disagree with its tables.

LATENT (``--what latent``)
    Three panels and a table, answering the three things the gate has to show:
      * gated against ungated latent cooling, per state — the size of what the
        plant-on gate removes;
      * the monthly profile at the canonical state — the southern-hemisphere
        phase, which a northern-hemisphere-shaped gate would invert;
      * the gating audit — hours charged with the cooling plant off, and hours
        charged while the *heating* plant runs. Both must be zero, and they are
        drawn on a scale where a non-zero value would be visible rather than
        rounded away.

RESIDUAL (``--what residual``)
    The V2 closure residual across all ten states with the 5 % gate drawn, plus
    the transmission line-item count and the independent re-integration error,
    which are the other two things that must hold for the gate to mean anything.

Usage
-----
    python tools/paper/diagnostics_latent_residual.py --what latent \\
        --raw results/paper/canonical_trajectory/trajectory_raw.json \\
        --outdir results/paper/diagnostics/latent
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

V2_TOLERANCE_PCT = 5.0
REINT_TOL_PCT = 0.1
EXPECTED_ITEMS = 7
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"
GATE = "#c2255c"
GATED_C = "#1baf7a"
UNGATED_C = "#c8c6c0"
BLUE = "#2a78d6"
SUMMER = "#eb6834"


def _style(ax, title, xlabel=None, ylabel=None):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, fontsize=10.5, color=TEXT_PRIMARY, fontweight="semibold",
                 pad=8)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, color=TEXT_SECONDARY)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color=TEXT_SECONDARY)
    ax.tick_params(labelsize=8, colors=TEXT_SECONDARY, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.9, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def load(raw: Path):
    blob = json.loads(raw.read_text(encoding="utf-8"))
    states = list(blob["results"])
    return blob, states, {s: blob["results"][s]["config_B"] for s in states}


# ---------------------------------------------------------------------------
# Latent
# ---------------------------------------------------------------------------

def latent(blob, states, B, outdir: Path, weather: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    canon = states[-1]
    monthly = B[canon].get("monthly_latent_cooling_kWh") or [0.0] * 12

    fig, axes = plt.subplots(1, 3, figsize=(17.0, 5.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    x = np.arange(len(states))

    # 1 -- gated vs ungated ---------------------------------------------------
    ax = axes[0]
    ung = [B[s]["Q_C_latent_ungated_kWh"] for s in states]
    gat = [B[s]["Q_C_latent_kWh"] for s in states]
    ax.bar(x, ung, width=0.7, color=UNGATED_C, edgecolor="none", zorder=2,
           label="ungated — the zone moisture balance")
    ax.bar(x, gat, width=0.7, color=GATED_C, edgecolor="none", zorder=3,
           label="gated — charged to the plant")
    for i, (u, g) in enumerate(zip(ung, gat)):
        ax.annotate(f"{u:,.0f}", xy=(i, u), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7.5, color=TEXT_SECONDARY)
        ax.annotate(f"{g:,.1f}", xy=(i, g), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7.5, color=GATED_C,
                    fontweight="semibold")
    _style(ax, "Latent cooling: gated against the raw moisture balance", None, "kWh")
    ax.set_ylim(0, max(ung) * 1.22)
    ax.set_xticks(x)
    ax.set_xticklabels(states, fontsize=7.2, rotation=38, ha="right",
                       color=TEXT_SECONDARY)
    ax.legend(fontsize=8, frameon=False, labelcolor=TEXT_SECONDARY, loc="upper right")
    ax.text(0.02, 0.95,
            f"at the canonical state the gate removes\n"
            f"{ung[-1] - gat[-1]:,.0f} kWh of the {ung[-1]:,.0f} kWh balance "
            f"({100 * (1 - gat[-1] / ung[-1]):.1f} %)",
            transform=ax.transAxes, ha="left", va="top", fontsize=8.2,
            color=TEXT_PRIMARY)

    # 2 -- monthly phase ------------------------------------------------------
    ax = axes[1]
    cols = [SUMMER if m in (0, 1, 11) else BLUE for m in range(12)]
    ax.bar(range(12), monthly, width=0.68, color=cols, edgecolor="none", zorder=3)
    for i, v in enumerate(monthly):
        if v > 0:
            ax.annotate(f"{v:.2f}", xy=(i, v), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=7.5, color=TEXT_PRIMARY)
    _style(ax, f"Gated latent cooling by month — {canon}", "month", "kWh")
    ax.set_xticks(range(12))
    ax.set_xticklabels(MONTHS, fontsize=8)
    ax.set_ylim(0, max(monthly + [1e-6]) * 1.34)
    summer = monthly[0] + monthly[1] + monthly[11]
    winter = sum(monthly[5:8])
    ax.text(0.5, 0.95,
            f"Dec–Feb {summer:.2f} kWh   vs   Jun–Aug {winter:.2f} kWh\n"
            f"the load sits in the austral summer",
            transform=ax.transAxes, ha="center", va="top", fontsize=8.5,
            color=SUMMER, fontweight="semibold")

    # 3 -- the gating audit ---------------------------------------------------
    ax = axes[2]
    off = [abs(B[s].get("latent_kWh_with_cooling_off") or 0.0) for s in states]
    heat = [abs(B[s].get("latent_kWh_while_heating") or 0.0) for s in states]
    w = 0.38
    ax.bar(x - w / 2, off, w, color=GATE, edgecolor="none", zorder=3,
           label="charged with the cooling plant OFF")
    ax.bar(x + w / 2, heat, w, color="#8b5cf6", edgecolor="none", zorder=3,
           label="charged while the HEATING plant runs")
    _style(ax, "The gating audit — both must be exactly zero", None, "kWh")
    ax.set_xticks(x)
    ax.set_xticklabels(states, fontsize=7.2, rotation=38, ha="right",
                       color=TEXT_SECONDARY)
    worst = max(off + heat)
    # A linear axis at this magnitude renders zero as zero and so proves nothing.
    # The limit is set from the tolerance, so a leak of even 1e-6 kWh would show.
    ax.set_ylim(0, max(worst * 1.4, 1e-5))
    ax.legend(fontsize=8, frameon=False, labelcolor=TEXT_SECONDARY, loc="upper left")
    ax.text(0.5, 0.55,
            f"largest value across all {len(states)} states: {worst:.2e} kWh\n"
            f"(axis scaled to 1e-5 kWh so any leak would be visible)",
            transform=ax.transAxes, ha="center", va="top", fontsize=8.5,
            color=GATED_C, fontweight="semibold")

    fig.suptitle("Apt 305, Carlton — the latent gate", fontsize=15,
                 color=TEXT_PRIMARY, x=0.006, ha="left", y=1.005,
                 fontweight="semibold")
    fig.text(0.006, 0.945,
             f"Latent cooling is charged only in hours the cooling plant actually "
             f"runs. Weather {Path(weather).name}. Final state “{canon}” is canonical.",
             fontsize=9, color=TEXT_SECONDARY, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.905])
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / "latent_breakdown.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)

    rows = [{
        "State": s,
        "Steps": B[s].get("n_steps"),
        "Cooling plant on (h)": B[s].get("n_steps_cooling_on"),
        "Heating plant on (h)": B[s].get("n_steps_heating_on"),
        "Latent charged (h)": B[s].get("n_steps_latent_charged"),
        "Gated latent cooling (kWh)": B[s]["Q_C_latent_kWh"],
        "Ungated latent cooling (kWh)": B[s]["Q_C_latent_ungated_kWh"],
        "Removed by the gate (kWh)": B[s]["Q_C_latent_ungated_kWh"] - B[s]["Q_C_latent_kWh"],
        "Charged with cooling off (kWh)": B[s].get("latent_kWh_with_cooling_off"),
        "Charged while heating (kWh)": B[s].get("latent_kWh_while_heating"),
        "Latent heating (kWh)": B[s]["Q_H_latent_kWh"],
    } for s in states]
    with (outdir / "latent_breakdown.csv").open("w", newline="", encoding="utf-8") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w_.writeheader()
        w_.writerows(rows)

    ok = worst <= 1e-9
    L = [f"# The latent gate", "",
         f"**Latent charged with the plant off, or while heating: "
         f"{'zero on every state — PASS' if ok else f'up to {worst:.2e} kWh — FAIL'}.**",
         "",
         f"Weather `{Path(weather).name}`. All numbers read from the Part 2 "
         f"trajectory's raw output — no re-measurement.", "",
         f"![latent breakdown](latent_breakdown.png)", "",
         "## Per state", "",
         "| State | Cooling on (h) | Heating on (h) | Latent charged (h) | Gated (kWh) "
         "| Ungated (kWh) | Removed by the gate (kWh) | Charged, plant off | "
         "Charged while heating | Latent heating (kWh) |",
         "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in rows:
        L.append(f"| {r['State']} | {r['Cooling plant on (h)']:,} "
                 f"| {r['Heating plant on (h)']:,} | {r['Latent charged (h)']:,} "
                 f"| {r['Gated latent cooling (kWh)']:,.2f} "
                 f"| {r['Ungated latent cooling (kWh)']:,.2f} "
                 f"| {r['Removed by the gate (kWh)']:,.2f} "
                 f"| {r['Charged with cooling off (kWh)']:.6f} "
                 f"| {r['Charged while heating (kWh)']:.6f} "
                 f"| {r['Latent heating (kWh)']:.4f} |")
    L += ["",
          "`Ungated` is the zone moisture balance before the plant-on gate. It is a "
          "**diagnostic contrast column and never part of any total** — it is shown "
          "so the size of what the gate removes is visible rather than implied.",
          "",
          "## Southern-hemisphere phase, canonical state", "",
          "| " + " | ".join(MONTHS) + " |",
          "| " + " | ".join(["---:"] * 12) + " |",
          "| " + " | ".join(f"{v:.2f}" for v in monthly) + " |", "",
          f"Dec–Feb {summer:.2f} kWh against Jun–Aug {winter:.2f} kWh. A gate built "
          f"around a northern-hemisphere cooling season would put the load in the "
          f"middle of this table; it does not.", ""]
    (outdir / "latent_breakdown.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  latent: gate leak max {worst:.2e} kWh "
          f"({'PASS' if ok else 'FAIL'}); Dec-Feb {summer:.2f} vs Jun-Aug {winter:.2f} kWh")
    return {"leak_max_kWh": worst, "pass": ok, "summer_kWh": summer,
            "winter_kWh": winter}


# ---------------------------------------------------------------------------
# Residual
# ---------------------------------------------------------------------------

def residual(blob, states, B, outdir: Path, weather: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.8), dpi=150,
                             gridspec_kw={"width_ratios": [1.55, 1]})
    fig.patch.set_facecolor(SURFACE)
    x = np.arange(len(states))
    pct = [B[s]["sankey"]["residual_pct"] for s in states]
    kwh = [B[s]["sankey"]["residual_kWh"] for s in states]

    ax = axes[0]
    cols = [GATED_C if abs(p) < V2_TOLERANCE_PCT else GATE for p in pct]
    ax.bar(x, pct, width=0.66, color=cols, edgecolor="none", zorder=3)
    span = max([abs(p) for p in pct] + [V2_TOLERANCE_PCT]) * 1.5
    ax.set_ylim(-span, span)
    ax.axhspan(-V2_TOLERANCE_PCT, V2_TOLERANCE_PCT, color=GATE, alpha=0.07, zorder=1)
    for edge in (-V2_TOLERANCE_PCT, V2_TOLERANCE_PCT):
        ax.axhline(edge, color=GATE, linewidth=1.1, linestyle="--", zorder=4)
    ax.axhline(0.0, color=TEXT_SECONDARY, linewidth=0.8, zorder=4)
    for i, (p, k) in enumerate(zip(pct, kwh)):
        ax.annotate(f"{p:+.2f} %\n{k:+,.1f} kWh", xy=(i, p),
                    xytext=(0, 4 if p >= 0 else -20), textcoords="offset points",
                    ha="center", va="bottom" if p >= 0 else "top", fontsize=7.6,
                    color=TEXT_PRIMARY, zorder=5)
    _style(ax, "V2 Sankey closure residual, every state", None, "% of inputs")
    ax.set_xticks(x)
    ax.set_xticklabels(states, fontsize=7.4, rotation=38, ha="right",
                       color=TEXT_SECONDARY)
    ax.text(0.985, 0.965, f"gate: |residual| < {V2_TOLERANCE_PCT:.0f} %",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5,
            color=GATE, style="italic")

    ax = axes[1]
    items = [B[s]["sankey"]["n_transmission_items"] for s in states]
    rel = [100.0 * B[s]["sankey"]["transmission_rel_diff"] for s in states]
    ax.bar(x, items, width=0.62, color=BLUE, edgecolor="none", zorder=3)
    ax.axhline(EXPECTED_ITEMS, color=GATED_C, linewidth=1.4, linestyle="--", zorder=4)
    _style(ax, "Transmission line items in the inventory", None, "line items")
    ax.set_ylim(0, EXPECTED_ITEMS * 1.5)
    ax.set_xticks(x)
    ax.set_xticklabels(states, fontsize=7.4, rotation=38, ha="right",
                       color=TEXT_SECONDARY)
    for i, v in enumerate(items):
        ax.annotate(str(v), xy=(i, v), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5, color=TEXT_PRIMARY)
    ax.text(0.5, 0.93,
            f"expected {EXPECTED_ITEMS}: five party surfaces + the west wall + its "
            f"windows\nbefore the closure fixes this column read 2\n"
            f"independent re-integration error, worst state: {max(rel):.4f} % "
            f"(tolerance {REINT_TOL_PCT} %)",
            transform=ax.transAxes, ha="center", va="top", fontsize=8.3,
            color=TEXT_SECONDARY)

    fig.suptitle("Apt 305, Carlton — the closure gate across the trajectory",
                 fontsize=15, color=TEXT_PRIMARY, x=0.006, ha="left", y=0.985,
                 fontweight="semibold")
    fig.text(0.006, 0.935,
             f"No kWh/m² headline is final unless the residual is inside the gate on "
             f"every state and the ADJ surfaces are in the inventory. "
             f"Weather {Path(weather).name}.",
             fontsize=9, color=TEXT_SECONDARY, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.912])
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / "residual_by_state.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)

    rows = [{
        "State": s,
        "Inputs (kWh)": B[s]["sankey"]["inputs_total_Wh"] / 1000.0,
        "Outputs (kWh)": B[s]["sankey"]["outputs_total_Wh"] / 1000.0,
        "Storage (kWh)": B[s]["sankey"]["storage_Wh"] / 1000.0,
        "V2 residual (kWh)": B[s]["sankey"]["residual_kWh"],
        "V2 residual (%)": B[s]["sankey"]["residual_pct"],
        "< 5 %?": "PASS" if abs(B[s]["sankey"]["residual_pct"]) < V2_TOLERANCE_PCT else "FAIL",
        "Transmission items": B[s]["sankey"]["n_transmission_items"],
        "Re-integration error (%)": 100.0 * B[s]["sankey"]["transmission_rel_diff"],
    } for s in states]
    with (outdir / "residual_by_state.csv").open("w", newline="", encoding="utf-8") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w_.writeheader()
        w_.writerows(rows)

    gate_ok = all(r["< 5 %?"] == "PASS" for r in rows)
    items_ok = all(r["Transmission items"] == EXPECTED_ITEMS for r in rows)
    reint_ok = all(r["Re-integration error (%)"] <= REINT_TOL_PCT for r in rows)
    worst = max(rows, key=lambda r: abs(r["V2 residual (%)"]))

    L = ["# The closure gate across the trajectory", "",
         f"**V2 residual < {V2_TOLERANCE_PCT:.0f} % on every state: "
         f"{'PASS' if gate_ok else 'FAIL'}.** "
         f"**{EXPECTED_ITEMS} transmission line items on every state: "
         f"{'PASS' if items_ok else 'FAIL'}.** "
         f"**Independent re-integration within {REINT_TOL_PCT} %: "
         f"{'PASS' if reint_ok else 'FAIL'}.**", "",
         f"Weather `{Path(weather).name}`. Read from the Part 2 trajectory's raw "
         f"output — no re-measurement.", "",
         "![residual by state](residual_by_state.png)", "",
         "| State | Inputs (kWh) | Outputs (kWh) | Storage (kWh) | V2 residual (kWh) "
         "| V2 residual (%) | < 5 %? | Transmission items | Re-integration error |",
         "| --- | ---: | ---: | ---: | ---: | ---: | :-: | ---: | ---: |"]
    for r in rows:
        L.append(f"| {r['State']} | {r['Inputs (kWh)']:,.2f} | {r['Outputs (kWh)']:,.2f} "
                 f"| {r['Storage (kWh)']:,.2f} | {r['V2 residual (kWh)']:+,.2f} "
                 f"| {r['V2 residual (%)']:+.2f} % | {r['< 5 %?']} "
                 f"| {r['Transmission items']} | {r['Re-integration error (%)']:.4f} % |")
    L += ["",
          f"Largest excursion: **{worst['V2 residual (%)']:+.2f} %** at "
          f"*{worst['State']}*. From `+Ground contact` onward the residual is "
          f"machine-zero — that fix removes the phantom ground term, which is the "
          f"only thing the earlier states had left to shed.", "",
          "The three conditions are not interchangeable. A small residual on an "
          "inventory that is missing 88.6 % of the envelope UA would be a balance "
          "that closes over the wrong control volume, which is exactly the state "
          "this whole effort started from — hence the line-item count and the "
          "independent re-integration are checked alongside it.", ""]
    (outdir / "residual_by_state.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  residual: worst {worst['V2 residual (%)']:+.2f} % at {worst['State']}; "
          f"items {'PASS' if items_ok else 'FAIL'}; re-integration "
          f"{'PASS' if reint_ok else 'FAIL'}")
    return {"gate_ok": gate_ok, "items_ok": items_ok, "reint_ok": reint_ok,
            "worst_pct": worst["V2 residual (%)"], "worst_state": worst["State"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--what", choices=["latent", "residual", "both"], default="both")
    args = ap.parse_args()

    blob, states, B = load(args.raw)
    weather = blob["meta"]["weather"]
    summary = {}
    if args.what in ("latent", "both"):
        summary["latent"] = latent(blob, states, B, args.outdir, weather)
    if args.what in ("residual", "both"):
        summary["residual"] = residual(blob, states, B, args.outdir, weather)
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=2),
                                              encoding="utf-8")
    print(f"wrote -> {args.outdir}")


if __name__ == "__main__":
    main()
