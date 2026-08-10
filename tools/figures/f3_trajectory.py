"""F3 -- The correction trajectory, one axis per metric, all thirteen states."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

import figstyle as F

SUBTITLE = (
    "Methodology order: the two literature corrections (C1, C2) first, then the implementation "
    "defects found in the engine, then the closure fixes.\n"
    "Each state is the previous state plus exactly one correction, cherry-picked onto the "
    "unmodified baseline. The final state, +Closure fixes, is canonical.\n"
    "One axis per metric — the trajectory spans roughly 4,200 kWh to 4 kWh, so no two of these "
    "series may share a scale."
)


def _bars(ax, values, *, width=0.74, edge=True):
    x = np.arange(len(F.STATES))
    return ax.bar(
        x, values, width,
        color=[F.STATE_COLOR[s] for s in F.STATES],
        edgecolor="white" if edge else "none", linewidth=0.5, zorder=3,
    )


def _panel(ax, title, ylabel, *, label_states=True):
    ax.set_title(title, loc="left", pad=7)
    ax.set_ylabel(ylabel)
    ax.set_xlim(-0.7, len(F.STATES) - 0.3)
    F.mark_infiltration_group(ax)
    if label_states:
        F.state_ticks(ax, rotation=58)
        for t in ax.get_xticklabels():
            t.set_fontsize(7.2)
    else:
        ax.set_xticks(range(len(F.STATES)))
        ax.set_xticklabels([])


def build() -> dict:
    traj = F.load_trajectory()
    st = traj["states"]
    v = lambda key: [st[s][key] for s in F.STATES]

    fig, axes = plt.subplots(3, 2, figsize=(13.4, 14.2))
    (a1, a2), (a3, a4), (a5, a6) = axes

    # ---- 1. sensible heating ------------------------------------------------
    heat = v("Q_H_sens")
    _panel(a1, "1 — Sensible heating", "Annual sensible heating (kWh)")
    b = _bars(a1, heat)
    a1.set_ylim(0, max(heat) * 1.16)
    for r, val in zip(b, heat):
        a1.annotate(f"{val:,.0f}", (r.get_x() + r.get_width() / 2, val),
                    xytext=(0, 2), textcoords="offset points", ha="center",
                    va="bottom", fontsize=6.6, color=F.INK, rotation=90)

    # ---- 2. sensible cooling ------------------------------------------------
    cool = v("Q_C_sens")
    _panel(a2, "2 — Sensible cooling", "Annual sensible cooling (kWh)")
    b = _bars(a2, cool)
    a2.set_ylim(0, max(cool) * 1.16)
    for r, val in zip(b, cool):
        a2.annotate(f"{val:,.1f}", (r.get_x() + r.get_width() / 2, val),
                    xytext=(0, 2), textcoords="offset points", ha="center",
                    va="bottom", fontsize=6.6, color=F.INK, rotation=90)

    # ---- 3. total energy need, the paper's metric ---------------------------
    per_area = v("Q_need_per_sqm")
    _panel(a3, "3 — Total energy need, paper metric "
               "($Q_{H,sens}+Q_{C,sens}+Q_{C,lat}$ gated)",
           "Annual energy need (kWh/m²·yr)")
    b = _bars(a3, per_area)
    a3.set_ylim(0, max(per_area) * 1.20)
    # Bars are drawn at the full-precision value; the printed label is the
    # paper's published figure, which the loader has already asserted agrees with
    # it. Re-rounding here would print 119.69 where the methodology table prints
    # 119.70 (the table rounds the already-rounded kWh total), and the figure and
    # the table must show the same number.
    for r, state, val in zip(b, F.STATES, per_area):
        a3.annotate(f"{F.EXPECTED_PER_AREA[state]:,.2f}",
                    (r.get_x() + r.get_width() / 2, val),
                    xytext=(0, 2), textcoords="offset points", ha="center",
                    va="bottom", fontsize=6.6, color=F.INK, rotation=90)
    can_i = F.STATES.index(F.CANONICAL_STATE)
    can_v = per_area[can_i]
    a3.axhline(can_v, color=F.GROUP_BASE["closure"], lw=1.1, ls="--", zorder=2)
    a3.annotate(
        f"canonical state\n$\\bf{{{can_v:.2f}}}$ kWh/m²·yr",
        xy=(can_i, can_v), xytext=(can_i - 3.4, max(per_area) * 0.40),
        fontsize=8.4, color=F.INK, ha="center", va="center", linespacing=1.4,
        arrowprops=dict(arrowstyle="->", color=F.GROUP_BASE["closure"], lw=1.1,
                        connectionstyle="arc3,rad=-0.25"),
        bbox=dict(boxstyle="round,pad=0.45", facecolor="#F8F0F5",
                  edgecolor=F.GROUP_BASE["closure"], linewidth=0.9),
        zorder=6,
    )

    # ---- 4. gated latent, with the ungated moisture balance behind ----------
    gated = v("Q_C_lat_gated")
    ungated = v("Q_C_lat_ungated")
    a4.set_title("4 — Latent cooling: gated charge against the ungated moisture balance",
                 loc="left", pad=7)
    x = np.arange(len(F.STATES))

    a4b = a4.twinx()
    a4b.set_zorder(1)
    a4.set_zorder(2)
    a4.patch.set_visible(False)
    a4b.grid(False)
    a4b.bar(x, ungated, 0.86, color=F.MUTED_FILL, edgecolor="none", zorder=1,
            label="Ungated zone moisture balance (right axis)")
    a4b.set_ylim(0, max(ungated) * 1.75)
    a4b.set_ylabel("Ungated zone moisture balance (kWh)", color="#6E6E6E")
    a4b.tick_params(axis="y", colors="#6E6E6E")

    a4.bar(x, gated, 0.46, color=[F.STATE_COLOR[s] for s in F.STATES],
           edgecolor="white", linewidth=0.5, zorder=3,
           label="Gated latent cooling (left axis)")
    a4.set_ylim(0, max(gated) * 1.75)
    a4.set_ylabel("Gated latent cooling (kWh)")
    _panel(a4, "4 — Latent cooling: gated charge against the ungated moisture balance",
           "Gated latent cooling (kWh)")
    a4.annotate(
        "Two independent axes: the ungated balance runs\n"
        f"{min(u / g for u, g in zip(ungated, gated)):.0f}–"
        f"{max(u / g for u, g in zip(ungated, gated)):,.0f}× the gated charge "
        "and must not share a scale.\n"
        "At the canonical state the gate removes\n"
        f"{ungated[can_i]:,.2f} → {gated[can_i]:,.2f} kWh, "
        f"{100.0 * (1 - gated[can_i] / ungated[can_i]):.1f} % of the raw balance.",
        xy=(0.985, 0.965), xycoords="axes fraction", ha="right", va="top",
        fontsize=7.6, color=F.INK, linespacing=1.45, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )
    a4.legend(
        handles=[
            Patch(facecolor=F.GROUP_BASE["defect"], edgecolor="white",
                  label="Gated (left axis)"),
            Patch(facecolor=F.MUTED_FILL, edgecolor="none",
                  label="Ungated (right axis)"),
        ],
        loc="upper left", fontsize=7.2,
    )

    # ---- 5. ventilation + infiltration loss ---------------------------------
    ve = v("Q_ve_loss")
    _panel(a5, "5 — Ventilation + infiltration loss", "Annual ventilation + infiltration loss (kWh)")
    b = _bars(a5, ve)
    a5.set_ylim(0, max(ve) * 1.16)
    for r, val in zip(b, ve):
        a5.annotate(f"{val:,.0f}", (r.get_x() + r.get_width() / 2, val),
                    xytext=(0, 2), textcoords="offset points", ha="center",
                    va="bottom", fontsize=6.6, color=F.INK, rotation=90)

    # ---- 6. V2 closure residual ---------------------------------------------
    res = v("residual_pct")
    _panel(a6, "6 — V2 closure residual, with the ±5 % gate",
           "Sankey closure residual (% of inputs)")
    a6.axhspan(-5, 5, color=F.GATE_BAND, alpha=0.30, zorder=0, lw=0)
    a6.axhline(0, color="#7A7A7A", lw=0.9, zorder=2)
    for edge in (-5, 5):
        a6.axhline(edge, color="#B9A600", lw=1.0, ls="--", zorder=2)
    _bars(a6, res)
    a6.set_ylim(-6.6, 6.6)
    a6.text(0.5, 5.0, "±5 % gate", ha="left", va="bottom", fontsize=7.8,
            color="#8A7B00", fontweight="bold")
    worst = min(res)
    worst_i = int(np.argmin(res))
    a6.annotate(
        f"largest excursion {worst:.2f} % at {F.SHORT[F.STATES[worst_i]]};\n"
        "machine-zero from +Ground contact onward.\n"
        "Every state PASSES the gate.",
        xy=(worst_i, worst), xytext=(6.4, -3.3), fontsize=7.6, color=F.INK,
        ha="center", va="center", linespacing=1.45, zorder=6,
        arrowprops=dict(arrowstyle="->", color="#7A7A7A", lw=0.9,
                        connectionstyle="arc3,rad=0.2"),
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )

    # ---- figure furniture ---------------------------------------------------
    fig.suptitle("F3 — The correction trajectory, thirteen states in methodology order",
                 fontsize=14, fontweight="bold", y=0.998)
    fig.text(0.5, 0.973, SUBTITLE, ha="center", va="top", fontsize=8.4,
             color="#4D4D4D", linespacing=1.45)

    handles = F.group_legend_handles() + [
        Patch(facecolor=F.GROUP_BASE["infiltration"], alpha=0.10,
              edgecolor=F.GROUP_BASE["infiltration"],
              label="shaded band: the three infiltration states (Section 3.7.1)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8.6,
               bbox_to_anchor=(0.5, 0.001), frameon=True)

    fig.tight_layout(rect=(0.005, 0.052, 0.995, 0.938))
    files = F.save(fig, "F3_correction_trajectory")

    return {
        "id": "F3",
        "title": "The correction trajectory (core result figure)",
        "files": files,
        "sources": [
            "results/paper/trajectory_v2/trajectory_raw.json",
            "results/paper/trajectory_v2/comparison.md (the same table, for cross-check)",
        ],
        "numbers": [
            "Sensible heating, Baseline → canonical: "
            f"{heat[0]:,.2f} → {heat[can_i]:,.2f} kWh (peak {max(heat):,.2f} kWh at "
            f"{F.STATES[int(np.argmax(heat))]})",
            "Sensible cooling, Baseline → canonical: "
            f"{cool[0]:,.2f} → {cool[can_i]:,.2f} kWh",
            "Total energy need on the paper's metric, Baseline → canonical: "
            f"{F.EXPECTED_PER_AREA[F.STATES[0]]:.2f} → "
            f"{F.EXPECTED_PER_AREA[F.CANONICAL_STATE]:.2f} kWh/m²·yr "
            "(peak 220.82 at +Internal gains)",
            f"Gated latent, Baseline → canonical: {gated[0]:.2f} → {gated[can_i]:.2f} kWh; "
            f"ungated {ungated[0]:.2f} → {ungated[can_i]:.2f} kWh",
            f"Ventilation + infiltration loss, Baseline → canonical: {ve[0]:,.2f} → "
            f"{ve[can_i]:,.2f} kWh (peak {max(ve):,.2f} kWh at +Ventilation)",
            f"V2 residual: worst {worst:.2f} % at {F.STATES[worst_i]}; "
            "machine zero from +Ground contact; all 13 states inside ±5 %",
            "Per-area values printed on panel 3 (the paper's published figures, "
            "each asserted against the recomputed value): "
            + ", ".join(f"{F.SHORT_PLAIN[s]} {F.EXPECTED_PER_AREA[s]:.2f}" for s in F.STATES),
        ],
        "note": (
            "Panel 3 uses the paper's metric (sensible heating + sensible cooling + gated "
            "latent), not the engine's own total column; the loader asserts all thirteen "
            "per-area values against the methodology list before the figure is drawn. Panel 4 "
            "carries two independent y axes because the ungated balance is up to 560× the "
            "gated charge."
        ),
        "placement": "main",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build()["files"])
