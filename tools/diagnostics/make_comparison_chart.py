"""
Item 5 — rebuild the six-state comparison chart so it is usable in the paper.

The chart it replaces put internal gains (~5 350 kWh) and total-per-area (~35
kWh/m2) on one shared y-axis, so the kWh/m2 bars were invisible, and carried no
legend, axis labels or title.

This is the faceted option from the brief: one panel per metric, each on its own
appropriately-scaled axis, so no series is crushed by another's range. Nothing
~5 000-scale ever shares an axis with anything ~35-scale.

Data is read from ``results/diagnostics/six_state_raw.json`` (the Item 3/4
harness), which is the canonical building established by Item 1 — party surfaces
typed ``adjacent``. Regenerate that first if the states change.

    python tools/diagnostics/make_comparison_chart.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

STATES = ["Baseline", "+Vent+Latent", "+Internal Gains",
          "+Conditioned Zones", "+Ground Fix", "+Hemisphere Fix"]

# (json key, panel title, unit). One panel each, own axis.
PANELS = [
    ("Q_H_annual_kWh",       "Sensible heating",        "kWh"),
    ("Q_C_annual_kWh",       "Sensible cooling",        "kWh"),
    ("Q_total_annual_kWh",   "Total energy need",       "kWh"),
    ("Q_internal_gains_kWh", "Internal gains",          "kWh"),
    ("Q_ve_loss_kWh",        "Ventilation + infiltration loss", "kWh"),
    ("latent_cooling_kWh",   "Latent cooling",          "kWh"),
]

# Same categorical palette as the earlier harnesses, extended to six slots.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#8b5cf6", "#d4a017", "#c2255c"]
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path,
                    default=REPO_ROOT / "results/diagnostics/six_state_raw.json")
    ap.add_argument("--outdir", type=Path,
                    default=REPO_ROOT / "results/au_corrections_summary")
    ap.add_argument("--stem", default="au_corrections_summary")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    data = json.loads(args.raw.read_text(encoding="utf-8"))
    area = float(data[STATES[0]]["net_floor_area_m2"])

    fig, axes = plt.subplots(2, 3, figsize=(15.0, 8.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)

    for ax, (key, title, unit) in zip(axes.ravel(), PANELS):
        vals = [float(data[s].get(key, float("nan"))) for s in STATES]
        ax.set_facecolor(SURFACE)
        bars = ax.bar(range(len(STATES)), vals, width=0.68,
                      color=SERIES_COLORS, edgecolor="none", zorder=3)

        vmax = max([v for v in vals if v == v] + [0.0])
        ax.set_ylim(0, vmax * 1.26 if vmax > 0 else 1.0)

        for x, v in zip(range(len(STATES)), vals):
            if v != v:
                continue
            ax.annotate(f"{v:,.1f}", xy=(x, v), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=8, color=TEXT_PRIMARY)

        ax.set_title(title, fontsize=11, color=TEXT_PRIMARY,
                     fontweight="semibold", pad=8)
        ax.set_ylabel(unit, fontsize=9, color=TEXT_SECONDARY)
        ax.set_xticks(range(len(STATES)))
        ax.set_xticklabels(STATES, fontsize=8, color=TEXT_SECONDARY,
                           rotation=38, ha="right")
        ax.tick_params(axis="y", labelsize=8, colors=TEXT_SECONDARY, length=0)
        ax.tick_params(axis="x", length=0)
        ax.grid(axis="y", color=GRID, linewidth=0.9, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)

        # kWh/m2 on the three conditioning metrics, where it is the number the
        # paper quotes; suppressed elsewhere, where per-area is not meaningful.
        if key in ("Q_H_annual_kWh", "Q_C_annual_kWh", "Q_total_annual_kWh"):
            last = vals[-1]
            if last == last:
                ax.text(0.985, 0.94,
                        f"final state: {last / area:,.2f} kWh/m²·yr",
                        transform=ax.transAxes, ha="right", va="top",
                        fontsize=8, color=TEXT_SECONDARY, style="italic")

    handles = [Patch(facecolor=SERIES_COLORS[i], edgecolor="none", label=s)
               for i, s in enumerate(STATES)]
    fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False,
               fontsize=9, labelcolor=TEXT_SECONDARY, bbox_to_anchor=(0.5, 0.005))

    fig.suptitle("Apt 305, 50 Barry St Carlton — cumulative effect of the AU corrections",
                 fontsize=15, color=TEXT_PRIMARY, x=0.008, ha="left", y=0.985,
                 fontweight="semibold")
    fig.text(0.008, 0.947,
             f"ISO 52016-1, ideal loads · {area:.0f} m² · 5 adjacent zones · "
             f"1.62 m² west-facing single glazing · "
             f"AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw",
             fontsize=9, color=TEXT_SECONDARY, ha="left")
    fig.text(0.008, 0.917,
             "Each metric on its own axis — the ~5 000 kWh and ~20 kWh series are not comparable "
             "and are never drawn on a shared scale.",
             fontsize=8.5, color=TEXT_SECONDARY, ha="left", style="italic")

    fig.tight_layout(rect=[0, 0.055, 1, 0.905])
    args.outdir.mkdir(parents=True, exist_ok=True)
    out = args.outdir / f"{args.stem}.png"
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print(f"chart -> {out}")


if __name__ == "__main__":
    main()
