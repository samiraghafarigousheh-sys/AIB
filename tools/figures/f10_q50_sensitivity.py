"""
F10 -- Envelope permeability sensitivity.

The two anchor points come from the committed trajectory: the
``+Infiltration envelope area`` state carries the European default q50 = 4.0, and
``+AU q50 recalibration`` carries the adopted pre-2006 band q50 = 14.0. They are
the same engine, the same building and the same weather, one correction apart.

The CSIRO new-dwelling mean, q50 = 6.9, is NOT measured in any committed result
file. It appears only in the message of the recalibration commit (421c282), on a
different engine tree whose own q50 = 4.0 row reads H = 112.70 kWh against the
trajectory's 114.87 kWh -- a 2.17 kWh disagreement that makes the two sets
incommensurable. Mixing them in one chart would be a figure built from two runs.
It is therefore drawn as an explicit "not measured" gap, and never interpolated.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle as F

Q50_EUROPEAN = 4.0
Q50_CSIRO_MEAN = 6.9         # _Q50_DEFAULT in utils.py: CSIRO 2024 (Ambrose, n = 233)
Q50_ADOPTED = 14.0           # the "1991-2005" band; Apt 305 was built to pre-2006 practice
Q50_DESIGN_TARGET = 5.0      # CSIRO 2024 stated design target, utils.py:446

STATE_FOR_Q50 = {
    Q50_EUROPEAN: "+Infiltration envelope area",
    Q50_ADOPTED: "+AU q50 recalibration",
}

MEASURED_COLOR = F.GROUP_BASE["infiltration"]
MISSING_COLOR = "#9A9A9A"
CSIRO_COLOR = "#0072B2"
TARGET_COLOR = "#CC79A7"

BAR_W = 1.5


def build() -> dict:
    traj = F.load_trajectory()
    st = traj["states"]

    points = {}
    for q50, state in STATE_FOR_Q50.items():
        points[q50] = {
            "state": state,
            "heating": st[state]["Q_H_sens"],
            "cooling": st[state]["Q_C_sens"],
            "per_area": st[state]["Q_need_per_sqm"],
        }

    # The values the paper quotes for the two anchors.
    for q50, (h, c, pa) in {
        Q50_EUROPEAN: (114.87, 12.89, 6.44),
        Q50_ADOPTED: (123.74, 13.41, 6.91),
    }.items():
        p = points[q50]
        if (abs(p["heating"] - h) >= 0.01 or abs(p["cooling"] - c) >= 0.01
                or abs(p["per_area"] - pa) >= 0.01):
            raise F.MissingQuantity(
                f"F10: q50 = {q50} gives {p['heating']:.2f} / {p['cooling']:.2f} / "
                f"{p['per_area']:.2f}, the paper states {h} / {c} / {pa}")

    metrics = [
        ("heating", "A — Annual sensible heating", "Annual sensible heating (kWh)", "{:,.2f}"),
        ("cooling", "B — Annual sensible cooling", "Annual sensible cooling (kWh)", "{:,.2f}"),
        ("per_area", "C — Total energy need, paper metric",
         "Annual energy need (kWh/m²·yr)", "{:,.2f}"),
    ]

    fig, axes = plt.subplots(3, 1, figsize=(11.6, 12.0), sharex=True)

    for panel_i, (ax, (key, title, ylabel, fmt)) in enumerate(zip(axes, metrics)):
        vals = [points[Q50_EUROPEAN][key], points[Q50_ADOPTED][key]]
        ax.bar([Q50_EUROPEAN, Q50_ADOPTED], vals, BAR_W, color=MEASURED_COLOR,
               edgecolor="white", linewidth=0.6, zorder=3)
        top = max(vals) * 1.46
        ax.set_ylim(0, top)

        # The point that is not in the committed results. Drawn as a full-height
        # hatched band, not a bar: a bar of any height would read as a value.
        ax.axvspan(Q50_CSIRO_MEAN - BAR_W / 2, Q50_CSIRO_MEAN + BAR_W / 2,
                   facecolor="none", edgecolor=MISSING_COLOR, hatch="////",
                   linewidth=1.1, zorder=1)
        ax.text(Q50_CSIRO_MEAN, top * 0.50,
                "not measured\nin the committed\nresult files\n— not interpolated",
                ha="center", va="center", fontsize=8.0, color=MISSING_COLOR,
                fontweight="bold", linespacing=1.4, zorder=6,
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                          edgecolor=MISSING_COLOR, linewidth=0.9))

        for q50, v in zip([Q50_EUROPEAN, Q50_ADOPTED], vals):
            ax.annotate(fmt.format(v), (q50, v), xytext=(0, -5),
                        textcoords="offset points", ha="center", va="top",
                        fontsize=10, fontweight="bold", color="white")

        # reference lines: what Australian practice measures, and what it aims at
        ax.axvline(Q50_CSIRO_MEAN, color=CSIRO_COLOR, lw=1.4, ls="--", zorder=4)
        ax.axvline(Q50_DESIGN_TARGET, color=TARGET_COLOR, lw=1.4, ls=":", zorder=4)
        if panel_i == 0:      # label the reference line once; it is in the legend too
            ax.text(Q50_DESIGN_TARGET - 0.14, top * 0.96,
                    "design target ≈ 5", rotation=90, ha="right", va="top",
                    fontsize=7.6, color=TARGET_COLOR, fontweight="bold")

        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", pad=7)

        # the swing between the two measured points
        lo, hi = vals
        ax.annotate(
            f"{hi - lo:+,.2f} ({100.0 * (hi - lo) / lo:+.1f} %)\n"
            f"from $q_{{50}}$ = {Q50_EUROPEAN:.1f} to {Q50_ADOPTED:.1f}",
            xy=(0.985, 0.94), xycoords="axes fraction", ha="right", va="top",
            fontsize=8.6, color=F.INK, linespacing=1.45, zorder=6,
            bbox=dict(boxstyle="round,pad=0.42", facecolor="white",
                      edgecolor="#BBBBBB", linewidth=0.8),
        )

    ax = axes[-1]
    ax.set_xlabel("Assumed envelope permeability $q_{50}$  [m³/(h·m²) at 50 Pa]")
    ax.set_xlim(1.6, 16.6)
    ax.set_xticks([Q50_EUROPEAN, Q50_CSIRO_MEAN, Q50_ADOPTED])
    ax.set_xticklabels([
        f"{Q50_EUROPEAN:.1f}\nEuropean default",
        f"{Q50_CSIRO_MEAN:.1f}\nCSIRO measured mean",
        f"{Q50_ADOPTED:.1f}\nadopted pre-2006 band",
    ], fontsize=8.8)

    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=MEASURED_COLOR, edgecolor="white",
                      label="measured in the committed trajectory"),
        plt.Rectangle((0, 0), 1, 1, facecolor="none", edgecolor=MISSING_COLOR,
                      hatch="////", label="not measured in the committed results — not interpolated"),
        plt.Line2D([], [], color=CSIRO_COLOR, lw=1.4, ls="--",
                   label="CSIRO 2024 measured mean, $q_{50}$ = 6.9 (Ambrose, n = 233 new dwellings)"),
        plt.Line2D([], [], color=TARGET_COLOR, lw=1.4, ls=":",
                   label="CSIRO 2024 stated design target, $q_{50}$ ≈ 5"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=8.4,
               bbox_to_anchor=(0.5, 0.002))

    fig.suptitle("F10 — Envelope permeability sensitivity: the result depends strongly on a "
                 "quantity Australian practice does not routinely measure",
                 fontsize=12.6, fontweight="bold", y=0.998)
    fig.text(0.5, 0.968,
             "Both measured points are the same engine, the same building and the same "
             "weather, one correction apart: $q_{50}$ = 4.0 is the +Infiltration envelope "
             "area state, $q_{50}$ = 14.0 is +AU $q_{50}$ recalibration.\n"
             "Apt 305 was completed in 2006 but built to pre-2006 practice, so the case "
             "adopts the 1991–2005 band. A blower-door measurement would override the table "
             "outright — none exists for this building.",
             ha="center", va="top", fontsize=8.4, color="#4D4D4D", linespacing=1.45)

    fig.tight_layout(rect=(0.005, 0.048, 0.995, 0.940))
    files = F.save(fig, "F10_q50_sensitivity")

    return {
        "id": "F10",
        "title": "Envelope permeability sensitivity",
        "files": files,
        "sources": [
            "results/paper/trajectory_v2/trajectory_raw.json "
            "(+Infiltration envelope area → q50 = 4.0; +AU q50 recalibration → q50 = 14.0)",
            "pybuildingenergy/src/pybuildingenergy/source/utils.py "
            "(_Q50_BY_CONSTRUCTION_AGE, _Q50_DEFAULT = 6.9, stated design target ≈ 5)",
        ],
        "numbers": [
            f"q50 = 4.0 (European default): heating {points[Q50_EUROPEAN]['heating']:.2f} kWh, "
            f"cooling {points[Q50_EUROPEAN]['cooling']:.2f} kWh, "
            f"total {points[Q50_EUROPEAN]['per_area']:.2f} kWh/m²·yr",
            "q50 = 6.9 (CSIRO new-dwelling mean): NOT MEASURED in the committed results — "
            "drawn as a gap, not interpolated",
            f"q50 = 14.0 (adopted pre-2006 band): heating {points[Q50_ADOPTED]['heating']:.2f} kWh, "
            f"cooling {points[Q50_ADOPTED]['cooling']:.2f} kWh, "
            f"total {points[Q50_ADOPTED]['per_area']:.2f} kWh/m²·yr",
            f"Swing from q50 = 4.0 to 14.0: heating "
            f"{points[Q50_ADOPTED]['heating'] - points[Q50_EUROPEAN]['heating']:+.2f} kWh "
            f"({100.0 * (points[Q50_ADOPTED]['heating'] / points[Q50_EUROPEAN]['heating'] - 1):+.1f} %); "
            f"total {points[Q50_ADOPTED]['per_area'] - points[Q50_EUROPEAN]['per_area']:+.2f} "
            f"kWh/m²·yr "
            f"({100.0 * (points[Q50_ADOPTED]['per_area'] / points[Q50_EUROPEAN]['per_area'] - 1):+.1f} %)",
            "Reference lines: CSIRO 2024 measured mean q50 = 6.9; CSIRO 2024 stated design "
            "target q50 ≈ 5",
        ],
        "note": (
            "**The q50 = 6.9 row is not present in the committed result files.** It exists "
            "only in the message of the recalibration commit `421c282`, which reports "
            "H = 115.85 / C = 12.94 / total = 128.79 kWh for q50 = 6.9. That sweep is not "
            "commensurable with the trajectory: its own q50 = 4.0 row reads H = 112.70 kWh "
            "against the trajectory's 114.87 kWh, and its totals are sensible-only "
            "(123.74 + 13.41 = 137.15 kWh at q50 = 14.0, against the paper's 138.29 kWh, "
            "which includes gated latent). Plotting the two together would build one chart "
            "from two runs, so the 6.9 point is drawn as an explicit gap and is not "
            "interpolated."
        ),
        "placement": "main-if-budget",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build()["files"])
