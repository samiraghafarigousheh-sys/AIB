"""F4 -- Per-correction contribution, as a waterfall for heating and for cooling."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

import figstyle as F

ZERO_TOL = 5e-3          # kWh; below this a step is reported as exactly zero


def _waterfall(ax, values, *, title, ylabel, fmt, annotate_key: dict[str, str]):
    """
    Cascade from the baseline total to the canonical total, one bar per correction.

    ``values`` is the metric on all thirteen states, in methodology order.
    """
    deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    labels = ["Baseline"] + [F.SHORT[s] for s in F.STATES[1:]] + ["Canonical\n(+Closure fixes)"]
    x = np.arange(len(labels))

    cum = values[0]
    tops = [values[0]]
    ax.bar(0, values[0], 0.66, color=F.STATE_COLOR["Baseline"],
           edgecolor="white", linewidth=0.5, zorder=3)

    for i, d in enumerate(deltas):
        lo, hi = (cum, cum + d) if d >= 0 else (cum + d, cum)
        height = max(hi - lo, 0.0)
        colour = F.INCREASE if d > ZERO_TOL else (F.DECREASE if d < -ZERO_TOL else F.MUTED)
        if height < ZERO_TOL:
            ax.plot([i + 1 - 0.33, i + 1 + 0.33], [cum, cum],
                    color=F.MUTED, lw=2.2, zorder=3, solid_capstyle="butt")
        else:
            ax.bar(i + 1, height, 0.66, bottom=lo, color=colour,
                   edgecolor="white", linewidth=0.5, zorder=3)
        # connector from the previous cumulative level
        ax.plot([i + 0.33, i + 1 + 0.33], [cum, cum], color="#9A9A9A", lw=0.8,
                ls=(0, (3, 2)), zorder=2)
        cum += d
        tops.append(cum)

    ax.bar(len(labels) - 1, cum, 0.66, color=F.STATE_COLOR[F.CANONICAL_STATE],
           edgecolor="white", linewidth=0.5, zorder=3)
    ax.plot([len(deltas) + 0.33, len(labels) - 1 - 0.33], [cum, cum],
            color="#9A9A9A", lw=0.8, ls=(0, (3, 2)), zorder=2)

    # cumulative running total
    ax.plot(x[:-1], tops, color=F.INK, lw=1.0, marker="o", ms=3.0,
            mfc="white", mew=0.9, zorder=5, label="Cumulative running total")

    top = max(max(tops), values[0]) * 1.24
    ax.set_ylim(0, top)
    ax.set_xlim(-0.72, len(labels) - 0.28)

    # bar labels: the signed delta for the steps, the level for the two totals
    ax.annotate(fmt(values[0]), (0, values[0]), xytext=(0, 4),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=7.4, fontweight="bold", color=F.INK)
    ax.annotate(fmt(cum), (len(labels) - 1, cum), xytext=(0, 4),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=7.4, fontweight="bold", color=F.INK)
    for i, d in enumerate(deltas):
        y = max(tops[i], tops[i + 1])
        colour = F.INCREASE if d > ZERO_TOL else (F.DECREASE if d < -ZERO_TOL else "#7A7A7A")
        txt = "0.00" if abs(d) < ZERO_TOL else f"{d:+,.2f}"
        ax.annotate(txt, (i + 1, y), xytext=(0, 5), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7.0, rotation=90,
                    color=colour, fontweight="bold" if abs(d) >= ZERO_TOL else "normal")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=58, ha="right", rotation_mode="anchor",
                       fontsize=7.2)
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", pad=7)

    # the three infiltration states, as a group
    lo = F.STATES.index("+Infiltration supply temp") - 0.5
    hi = F.STATES.index("+AU q50 recalibration") + 0.5
    ax.axvspan(lo, hi, color=F.GROUP_BASE["infiltration"], alpha=0.10, zorder=0, lw=0)
    ax.text((lo + hi) / 2, 0.975, "infiltration states (§3.7.1)",
            transform=ax.get_xaxis_transform(), ha="center", va="top",
            fontsize=7.0, color=F.GROUP_BASE["infiltration"], fontweight="bold")

    for state, (note, (tx, tyfrac)) in annotate_key.items():
        i = F.STATES.index(state)
        ax.annotate(
            note, xy=(i, max(tops[i - 1], tops[i])),
            xytext=(tx, top * tyfrac),
            fontsize=7.4, color=F.INK, ha="center", va="center", linespacing=1.4,
            arrowprops=dict(arrowstyle="->", color="#7A7A7A", lw=0.9,
                            connectionstyle="arc3,rad=0.2"),
            bbox=dict(boxstyle="round,pad=0.42", facecolor="white",
                      edgecolor="#BBBBBB", linewidth=0.8),
            zorder=6,
        )
    return deltas, cum


def build() -> dict:
    traj = F.load_trajectory()
    st = traj["states"]
    heat = [st[s]["Q_H_sens"] for s in F.STATES]
    cool = [st[s]["Q_C_sens"] for s in F.STATES]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13.0, 12.4))

    dh, heat_final = _waterfall(
        ax1, heat,
        title="A — Sensible heating: baseline 1,779.36 kWh → canonical 123.74 kWh",
        ylabel="Annual sensible heating (kWh)",
        fmt=lambda v: f"{v:,.2f}",
        annotate_key={
            "+Internal gains": (
                "de-inflating the internal gains\n$\\bf{raises}$ heating by +2,031.04 kWh",
                (2.15, 0.90)),
            "+Conditioned zones": (
                "the adjacent-zone boundary treatment\n$\\bf{lowers}$ it by −4,018.18 kWh",
                (10.3, 0.70)),
        },
    )
    dc, cool_final = _waterfall(
        ax2, cool,
        title="B — Sensible cooling: baseline 640.84 kWh → canonical 13.41 kWh",
        ylabel="Annual sensible cooling (kWh)",
        fmt=lambda v: f"{v:,.2f}",
        annotate_key={
            "+Internal gains": (
                "internal gains $\\bf{lower}$ cooling\nby −264.89 kWh",
                (9.4, 0.74)),
            "+Infiltration supply temp": (
                "supplying infiltration air at $\\theta_e$\n$\\bf{raises}$ cooling by +11.02 kWh",
                (11.4, 0.42)),
        },
    )

    # The five movements the figure exists to make visible.
    expect = {
        "+Internal gains": 2031.0,
        "+Conditioned zones": -4018.0,
        "+Infiltration supply temp": -56.33,
        "+Infiltration envelope area": -39.08,
        "+AU q50 recalibration": 8.87,
    }
    for state, want in expect.items():
        got = dh[F.STATES.index(state) - 1]
        if abs(got - want) > 0.6:
            raise F.MissingQuantity(
                f"F4: heating step at {state} is {got:+.2f} kWh, the paper states {want:+.2f}")
    if abs(heat_final - 123.74) > 0.01 or abs(cool_final - 13.41) > 0.01:
        raise F.MissingQuantity(
            f"F4: cascade lands on {heat_final:.2f} / {cool_final:.2f} kWh, "
            "not the canonical 123.74 / 13.41")

    handles = [
        Patch(facecolor=F.INCREASE, edgecolor="white", label="Correction raises the need"),
        Patch(facecolor=F.DECREASE, edgecolor="white", label="Correction lowers the need"),
        Patch(facecolor=F.MUTED, edgecolor="white", label="No change (|Δ| < 0.005 kWh)"),
        Patch(facecolor=F.STATE_COLOR["Baseline"], edgecolor="white", label="Baseline level"),
        Patch(facecolor=F.STATE_COLOR[F.CANONICAL_STATE], edgecolor="white",
              label="Canonical level"),
        plt.Line2D([], [], color=F.INK, lw=1.0, marker="o", ms=3.5, mfc="white",
                   label="Cumulative running total"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=6, fontsize=8.4,
               bbox_to_anchor=(0.5, 0.002))

    fig.suptitle("F4 — Per-correction contribution: the corrections act in opposing directions",
                 fontsize=13.5, fontweight="bold", y=0.998)
    fig.text(0.5, 0.968,
             "A net figure conceals this. The internal-gains correction raises heating by "
             "+2,031.04 kWh and the conditioned-zone correction lowers it by −4,018.18 kWh; "
             "the two infiltration\ndefect fixes take off a further −56.33 and −39.08 kWh, and "
             "the Australian $q_{50}$ recalibration returns +8.87 kWh. "
             "Derived from consecutive states of results/paper/trajectory_v2/comparison.md.",
             ha="center", va="top", fontsize=8.4, color="#4D4D4D", linespacing=1.45)

    fig.tight_layout(rect=(0.005, 0.043, 0.995, 0.944))
    files = F.save(fig, "F4_per_correction_waterfall")

    steps = lambda ds: ", ".join(
        f"{F.SHORT_PLAIN[F.STATES[i + 1]]} {d:+,.2f}" for i, d in enumerate(ds))

    return {
        "id": "F4",
        "title": "Per-correction contribution (waterfall), heating and cooling",
        "files": files,
        "sources": [
            "results/paper/trajectory_v2/comparison.md / trajectory_raw.json "
            "(differences between consecutive states)"
        ],
        "numbers": [
            f"Heating cascade: {heat[0]:,.2f} kWh → {heat_final:,.2f} kWh",
            f"Heating steps (kWh): {steps(dh)}",
            f"Cooling cascade: {cool[0]:,.2f} kWh → {cool_final:,.2f} kWh",
            f"Cooling steps (kWh): {steps(dc)}",
            "Opposing movements the figure exists to show: +Internal gains +2,031.04; "
            "+Conditioned zones −4,018.18; +Infil. supply temp −56.33; "
            "+Infil. envelope area −39.08; +AU q50 +8.87 (heating)",
        ],
        "note": (
            "Deltas are differences between consecutive states of the committed trajectory, "
            "not re-simulated. The script asserts the five signature movements and the "
            "canonical landing point before drawing."
        ),
        "placement": "main-if-budget",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build()["files"])
