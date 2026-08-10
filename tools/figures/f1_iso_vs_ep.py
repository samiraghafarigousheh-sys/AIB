"""F1 -- Baseline ISO 52016-1 against EnergyPlus."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle as F

ISO_COLOR = "#0072B2"
EP_COLOR = "#E69F00"

SUBTITLE = (
    "Same weather ({weather}); same 18 / 26 °C setpoints; same probed internal gains;\n"
    "ISO 13789 buffer neighbours on both sides; ideal loads. Infiltration is absent "
    "from both engines at this state."
).format(weather="Melbourne-Essendon Fields TMYx 2011–2025")


def build() -> dict:
    ep = F.load_ep()
    metrics = ["Heating", "Cooling", "Total"]

    fig, ax = plt.subplots(figsize=(7.4, 5.2))

    x = np.arange(len(metrics))
    w = 0.36
    iso_vals = [ep[m]["iso"] for m in metrics]
    ep_vals = [ep[m]["ep"] for m in metrics]

    b1 = ax.bar(x - w / 2, iso_vals, w, label="ISO 52016-1 (baseline)",
                color=ISO_COLOR, edgecolor="white", linewidth=0.6)
    b2 = ax.bar(x + w / 2, ep_vals, w, label="EnergyPlus (reference)",
                color=EP_COLOR, edgecolor="white", linewidth=0.6)

    top = max(iso_vals + ep_vals)
    ax.set_ylim(0, top * 1.32)

    # Values sit inside the bar heads, so the difference brackets above them stay
    # clear of any text.
    for bars in (b1, b2):
        for rect in bars:
            h = rect.get_height()
            ax.annotate(f"{h:,.0f}",
                        (rect.get_x() + rect.get_width() / 2, h),
                        xytext=(0, -4), textcoords="offset points",
                        ha="center", va="top", fontsize=8.5, fontweight="bold",
                        color="white")

    # Percentage difference relative to the EnergyPlus reference.
    for i, m in enumerate(metrics):
        pct = ep[m]["diff_pct_vs_ep"]
        y = max(iso_vals[i], ep_vals[i])
        foot = y + top * 0.035
        bracket_y = y + top * 0.085
        ax.plot([x[i] - w / 2, x[i] - w / 2, x[i] + w / 2, x[i] + w / 2],
                [foot, bracket_y, bracket_y, foot],
                color=F.INK, lw=0.9, clip_on=False)
        ax.annotate(
            f"{pct:+.1f} %",
            (x[i], bracket_y), xytext=(0, 3), textcoords="offset points",
            ha="center", va="bottom", fontsize=10.5, fontweight="bold",
            color=F.INCREASE if pct > 0 else F.DECREASE,
        )

    ax.set_xticks(x)
    ax.set_xticklabels([f"{m}\n(sensible)" if m != "Total" else "Total\n(sensible)"
                        for m in metrics])
    ax.set_ylabel("Annual energy need (kWh)")
    ax.set_xlabel("Component of the annual sensible energy need")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")

    # Same quantity, second unit -- a linear rescaling of the left axis, not a
    # second series.
    ax2 = ax.twinx()
    ax2.set_ylim(ax.get_ylim()[0] / F.NET_FLOOR_AREA_M2,
                 ax.get_ylim()[1] / F.NET_FLOOR_AREA_M2)
    ax2.set_ylabel(f"Annual energy need (kWh/m²·yr, net floor area "
                   f"{F.NET_FLOOR_AREA_M2:.0f} m²)")
    ax2.grid(False)

    ax.set_title("F1 — Baseline ISO 52016-1 against EnergyPlus\n"
                 "Percentage differences are relative to the EnergyPlus reference",
                 pad=44)
    ax.text(0.5, 1.012, SUBTITLE, transform=ax.transAxes, ha="center", va="bottom",
            fontsize=7.6, color="#4D4D4D", linespacing=1.35)

    ax.legend(loc="upper left", ncol=1)

    ax.annotate(
        "The components disagree in\n"
        "$\\bf{opposite}$ $\\bf{directions}$: ISO\n"
        "over-predicts heating by 58.8 %\n"
        "and under-predicts cooling by\n"
        "8.1 %. The +33.2 % total is the\n"
        "residue of two errors of opposite\n"
        "sign, and characterises neither.",
        xy=(0.50, 0.905), xycoords="axes fraction", ha="center", va="top",
        fontsize=8.0, color=F.INK, linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.55", facecolor="#FFF7E6",
                  edgecolor="#E69F00", linewidth=0.9),
    )

    fig.tight_layout()
    files = F.save(fig, "F1_baseline_iso_vs_energyplus")

    return {
        "id": "F1",
        "title": "Baseline ISO 52016-1 against EnergyPlus",
        "files": files,
        "sources": [
            "results/paper/baseline_vs_ep_v2/baseline_vs_energyplus.csv",
            "results/paper/baseline_vs_ep_v2/run_meta.json",
        ],
        "numbers": [
            f"Heating: ISO {ep['Heating']['iso']:,.1f} kWh vs EnergyPlus "
            f"{ep['Heating']['ep']:,.1f} kWh ({ep['Heating']['diff_pct_vs_ep']:+.1f} % vs EP)",
            f"Cooling: ISO {ep['Cooling']['iso']:,.1f} kWh vs EnergyPlus "
            f"{ep['Cooling']['ep']:,.1f} kWh ({ep['Cooling']['diff_pct_vs_ep']:+.1f} % vs EP)",
            f"Total: ISO {ep['Total']['iso']:,.1f} kWh vs EnergyPlus "
            f"{ep['Total']['ep']:,.1f} kWh ({ep['Total']['diff_pct_vs_ep']:+.1f} % vs EP)",
            f"Per area: ISO {ep['Total']['iso_per_sqm']:.2f} vs EP "
            f"{ep['Total']['ep_per_sqm']:.2f} kWh/m²·yr",
        ],
        "note": (
            "The committed CSV states `diff_pct` against the ISO figure; the paper quotes "
            "the difference against the EnergyPlus reference, so the figure recomputes it "
            "from the same two kWh columns and asserts +58.8 / −8.1 / +33.2 % before drawing."
        ),
        "placement": "main",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build())
