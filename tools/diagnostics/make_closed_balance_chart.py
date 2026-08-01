"""
Faceted comparison chart, rebuilt from the CLOSED-balance six-state numbers.

Same faceting discipline as ``make_comparison_chart.py`` — one panel per metric,
each on its own axis, so nothing at the ~5 000 kWh scale ever shares a y-axis
with anything at the ~10 kWh/m2 scale — but drawn from
``results/au_corrections_closed/six_state_closed_raw.json`` and carrying the two
things the earlier chart could not:

  * a **V2 closure residual panel**, with the 5 % gate drawn on it, because a
    demand number is not a result until the balance it came from closes; and
  * latent cooling shown **gated**, against the ungated moisture balance it
    replaced, so the ~550 kWh term that used to inflate the headline is visible
    as what it was rather than quietly absent.

    python tools/diagnostics/make_closed_balance_chart.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

V2_TOLERANCE_PCT = 5.0

# (accessor, panel title, unit)
PANELS = [
    ("Q_H_sensible_kWh",     "Sensible heating",                 "kWh"),
    ("Q_C_sensible_kWh",     "Sensible cooling",                 "kWh"),
    ("Q_need_total_kWh",     "Total energy need (sensible + gated latent)", "kWh"),
    ("Q_C_latent_kWh",       "Latent cooling — gated to plant-on hours", "kWh"),
    ("Q_ve_loss_kWh",        "Ventilation + infiltration loss",  "kWh"),
    ("__residual_pct",       "V2 Sankey closure residual",       "% of inputs"),
]

SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#8b5cf6", "#d4a017", "#c2255c", "#0f766e"]
GHOST = "#c8c6c0"
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"
GATE = "#c2255c"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path,
                    default=REPO_ROOT / "results/au_corrections_closed/six_state_closed_raw.json")
    ap.add_argument("--outdir", type=Path,
                    default=REPO_ROOT / "results/au_corrections_closed")
    ap.add_argument("--stem", default="au_corrections_closed_balance")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    blob = json.loads(args.raw.read_text(encoding="utf-8"))
    results = blob["results"]
    states = list(results.keys())
    area = float(results[states[0]]["config_B"]["net_floor_area_m2"])
    colors = [SERIES_COLORS[i % len(SERIES_COLORS)] for i in range(len(states))]

    def value(state: str, key: str) -> float:
        r = results[state]["config_B"]
        if key == "__residual_pct":
            return float(r["sankey"]["residual_pct"])
        v = r.get(key)
        return float("nan") if v is None else float(v)

    fig, axes = plt.subplots(2, 3, figsize=(16.0, 9.0), dpi=150)
    fig.patch.set_facecolor(SURFACE)

    for ax, (key, title, unit) in zip(axes.ravel(), PANELS):
        vals = [value(s, key) for s in states]
        ax.set_facecolor(SURFACE)

        # Latent panel: the ungated moisture balance behind the gated bars, so
        # the size of what the gate removed is on the page rather than implied.
        if key == "Q_C_latent_kWh":
            ghost = [value(s, "Q_C_latent_ungated_kWh") for s in states]
            ax.bar(range(len(states)), ghost, width=0.68, color=GHOST,
                   edgecolor="none", zorder=2)
            for x, v in zip(range(len(states)), ghost):
                if v == v:
                    ax.annotate(f"{v:,.0f}", xy=(x, v), xytext=(0, 3),
                                textcoords="offset points", ha="center",
                                va="bottom", fontsize=7, color=TEXT_SECONDARY)

        ax.bar(range(len(states)), vals, width=0.68, color=colors,
               edgecolor="none", zorder=3)

        finite = [v for v in vals if v == v]
        if key == "__residual_pct":
            span = max([abs(v) for v in finite] + [V2_TOLERANCE_PCT]) * 1.45
            ax.set_ylim(-span, span)
            ax.axhspan(-V2_TOLERANCE_PCT, V2_TOLERANCE_PCT, color=GATE, alpha=0.07, zorder=1)
            for edge in (-V2_TOLERANCE_PCT, V2_TOLERANCE_PCT):
                ax.axhline(edge, color=GATE, linewidth=1.0, linestyle="--", zorder=4)
            ax.axhline(0.0, color=TEXT_SECONDARY, linewidth=0.8, zorder=4)
            ax.text(0.985, 0.965, f"gate: |residual| < {V2_TOLERANCE_PCT:.0f} %",
                    transform=ax.transAxes, ha="right", va="top", fontsize=8,
                    color=GATE, style="italic")
        else:
            ceiling = max(
                finite + ([value(s, "Q_C_latent_ungated_kWh") for s in states]
                          if key == "Q_C_latent_kWh" else []) + [0.0]
            )
            ax.set_ylim(0, ceiling * 1.26 if ceiling > 0 else 1.0)

        for x, v in zip(range(len(states)), vals):
            if v != v:
                continue
            label = f"{v:+.2f}" if key == "__residual_pct" else f"{v:,.1f}"
            off = 3 if v >= 0 else -11
            ax.annotate(label, xy=(x, v), xytext=(0, off),
                        textcoords="offset points", ha="center",
                        va="bottom" if v >= 0 else "top",
                        fontsize=8, color=TEXT_PRIMARY, zorder=5)

        ax.set_title(title, fontsize=10.5, color=TEXT_PRIMARY,
                     fontweight="semibold", pad=8)
        ax.set_ylabel(unit, fontsize=9, color=TEXT_SECONDARY)
        ax.set_xticks(range(len(states)))
        ax.set_xticklabels(states, fontsize=7.5, color=TEXT_SECONDARY,
                           rotation=38, ha="right")
        ax.tick_params(axis="y", labelsize=8, colors=TEXT_SECONDARY, length=0)
        ax.tick_params(axis="x", length=0)
        ax.grid(axis="y", color=GRID, linewidth=0.9, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)

        if key in ("Q_H_sensible_kWh", "Q_C_sensible_kWh", "Q_need_total_kWh"):
            last = vals[-1]
            if last == last:
                ax.text(0.985, 0.94, f"final state: {last / area:,.2f} kWh/m²·yr",
                        transform=ax.transAxes, ha="right", va="top",
                        fontsize=8, color=TEXT_SECONDARY, style="italic")

    handles = [Patch(facecolor=colors[i], edgecolor="none", label=s)
               for i, s in enumerate(states)]
    handles.append(Patch(facecolor=GHOST, edgecolor="none",
                         label="latent, ungated (moisture balance)"))
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=8.5, labelcolor=TEXT_SECONDARY, bbox_to_anchor=(0.5, 0.005))

    fig.suptitle("Apt 305, 50 Barry St Carlton — AU corrections on a closed energy balance",
                 fontsize=15, color=TEXT_PRIMARY, x=0.008, ha="left", y=0.985,
                 fontweight="semibold")
    fig.text(0.008, 0.949,
             f"ISO 52016-1, ideal loads · {area:.0f} m² · 5 adjacent zones · "
             f"1.62 m² west-facing single glazing · "
             f"AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw",
             fontsize=9, color=TEXT_SECONDARY, ha="left")
    fig.text(0.008, 0.921,
             "Every state measured with the same reporting instrument: the ADJ-transmission, "
             "latent-gating and GR-classification fixes are applied to all seven. "
             "Each metric on its own axis.",
             fontsize=8.5, color=TEXT_SECONDARY, ha="left", style="italic")

    fig.tight_layout(rect=[0, 0.075, 1, 0.905])
    args.outdir.mkdir(parents=True, exist_ok=True)
    out = args.outdir / f"{args.stem}.png"
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print(f"chart -> {out}")


if __name__ == "__main__":
    main()
