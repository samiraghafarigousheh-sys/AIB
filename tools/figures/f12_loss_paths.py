"""
F12 -- the residual disagreement by loss path (Section 4.1.3).

Section 4.1.3 makes an argument that is hard to follow in prose: the loss-path
decomposition CLOSES -- the compared paths sum to the same total on both sides
-- and yet that agreement is not uniform. Two paths carry almost all of the
disagreement, and they point in opposite directions, so they partly cancel in
the annual total.

That is the same pattern that produced the false validation this work set out to
detect: a plausible total standing on offsetting errors. The figure exists to
make the offsetting visible, so the paths are ordered by absolute difference and
the two dominant rows land together at the top.

Built from ``results/paper/validation_corrected/loss_paths.csv``, extracted from
the section 1 table of ``DISCREPANCY.md`` by
``tools/paper/extract_loss_paths.py``. figstyle re-checks every value against
that markdown table and asserts that the paths sum to the stated total on both
sides before the figure is drawn.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle as F

ISO_COLOR = "#0072B2"      # as in F1: the ISO engine is blue everywhere
EP_COLOR = "#E69F00"       # as in F1: the EnergyPlus reference is orange
TOTAL_ISO = "#004C77"      # the same hues, darkened, for the summary row
TOTAL_EP = "#9A6B00"

SUBTITLE = (
    "Net heat gain to the zone, kWh/yr, positive into the zone. Corrected ISO 52016-1 against "
    "the matched EnergyPlus 24.1.0 case,\n"
    "Melbourne-Essendon Fields TMYx 2011–2025. Paths are ordered by absolute difference, so the "
    "two that carry the disagreement appear together."
)


def build() -> dict:
    lp = F.load_loss_paths()
    paths, total = lp["paths"], lp["total"]

    # Two rows carry the disagreement. Identify them from the data rather than
    # naming them, so the annotation follows the decomposition if it moves.
    first, second = paths[0], paths[1]
    net = first["diff"] + second["diff"]
    opposing = (first["diff"] > 0) != (second["diff"] > 0)
    share = 100.0 * (abs(first["diff"]) + abs(second["diff"])) / sum(
        abs(p["diff"]) for p in paths)

    n = len(paths)
    y = np.arange(n, dtype=float)
    y_total = n + 0.75

    fig, (ax, axd) = plt.subplots(
        1, 2, figsize=(12.6, 7.6), sharey=True,
        gridspec_kw={"width_ratios": [2.35, 1.0], "wspace": 0.07},
    )
    fig.subplots_adjust(left=0.205, right=0.975, top=0.745, bottom=0.205)

    # The two rows the figure exists to show, shaded across both panels so the
    # pairing is visible before any number is read.
    for a in (ax, axd):
        a.axhspan(-0.46, 1.46, color=F.MUTED_FILL, alpha=0.30, zorder=0, lw=0)

    h = 0.34
    iso = np.array([p["iso"] for p in paths])
    ep = np.array([p["ep"] for p in paths])

    ax.barh(y - h / 2, iso, h, color=ISO_COLOR, edgecolor="white", linewidth=0.5,
            label="ISO 52016-1 (corrected)")
    ax.barh(y + h / 2, ep, h, color=EP_COLOR, edgecolor="white", linewidth=0.5,
            label="EnergyPlus (matched reference)")
    ax.barh(y_total - h / 2, total["iso"], h, color=TOTAL_ISO, edgecolor="white",
            linewidth=0.5)
    ax.barh(y_total + h / 2, total["ep"], h, color=TOTAL_EP, edgecolor="white",
            linewidth=0.5)

    span = max(abs(iso).max(), abs(ep).max(), abs(total["iso"]))
    ax.set_xlim(-span * 1.30, span * 0.78)
    ax.axvline(0.0, color=F.INK, lw=0.9)

    def _label(axis, xv, yv, text, colour=F.INK, weight="normal", size=8.2):
        pad = span * 0.018
        axis.annotate(text, (xv, yv),
                      xytext=(pad if xv >= 0 else -pad, 0), textcoords="offset points",
                      ha="left" if xv >= 0 else "right", va="center",
                      fontsize=size, color=colour, fontweight=weight)

    for i in range(n):
        _label(ax, iso[i], y[i] - h / 2, f"{iso[i]:+,.1f}", ISO_COLOR)
        _label(ax, ep[i], y[i] + h / 2, f"{ep[i]:+,.1f}", EP_COLOR)
    _label(ax, total["iso"], y_total - h / 2, f"{total['iso']:+,.1f}", TOTAL_ISO, "bold")
    _label(ax, total["ep"], y_total + h / 2, f"{total['ep']:+,.1f}", TOTAL_EP, "bold")

    ax.set_yticks(list(y) + [y_total])
    ax.set_yticklabels([p["short_label"] for p in paths]
                       + ["$\\bf{Σ\\ compared\\ paths}$"])
    ax.invert_yaxis()
    ax.set_xlabel("Net heat gain to the zone (kWh/yr, positive into the zone)")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.set_title("Path by path, ISO against the reference", pad=8, loc="left")
    ax.legend(loc="lower right", ncol=1)

    # Separator between the compared paths and their sum: the Σ row is a sum of
    # the rows above it, not another path.
    ax.axhline(n + 0.05, color=F.MUTED, lw=0.8, ls=(0, (4, 3)))
    axd.axhline(n + 0.05, color=F.MUTED, lw=0.8, ls=(0, (4, 3)))

    # ---- difference column ------------------------------------------------
    diffs = np.array([p["diff"] for p in paths])
    colours = [F.INCREASE if d > 0 else F.DECREASE for d in diffs]
    axd.barh(y, diffs, 0.55, color=colours, edgecolor="white", linewidth=0.5)
    axd.barh(y_total, total["diff"], 0.55, color=F.MUTED_FILL, edgecolor=F.INK,
             linewidth=0.7)

    dspan = max(abs(diffs).max(), 1.0)
    axd.set_xlim(-dspan * 1.42, dspan * 1.42)
    axd.axvline(0.0, color=F.INK, lw=0.9)
    for i in range(n):
        _label(axd, diffs[i], y[i], f"{diffs[i]:+,.1f}",
               colours[i], "bold", 8.6)
    axd.annotate(f"{total['diff']:+,.1f}", (0.0, y_total), xytext=(0, -16),
                 textcoords="offset points", ha="center", va="center",
                 fontsize=8.8, fontweight="bold", color=F.INK)
    axd.set_xlabel("Δ  (ISO − EnergyPlus), kWh/yr")
    axd.set_title("The disagreement", pad=8, loc="left")

    # State the arithmetic of the shaded pair, in the empty lower half of the
    # difference panel -- the three remaining paths are small, so nothing is
    # covered.
    axd.text(
        0.5, 0.345,
        f"Shaded pair: {first['diff']:+,.1f} and {second['diff']:+,.1f} kWh\n"
        f"{'partly cancel' if opposing else 'compound'} to {net:+,.1f} kWh\n"
        f"{share:.0f} % of all disagreement, in two rows",
        transform=axd.transAxes, ha="center", va="top",
        fontsize=8.0, fontweight="bold", color=F.INK, linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="#FFF7E6",
                  edgecolor="#E69F00", linewidth=0.9),
    )

    fig.text(0.5, 0.985,
             "F12 — Where the remaining ISO-against-EnergyPlus disagreement sits, by loss path\n"
             "The totals agree to "
             f"{abs(total['diff']):.1f} kWh; the agreement rests on two large opposing "
             "differences, not on uniform agreement",
             ha="center", va="top", fontsize=11.5, fontweight="bold", linespacing=1.45)
    fig.text(0.5, 0.895, SUBTITLE, ha="center", va="top", fontsize=7.8,
             color="#4D4D4D", linespacing=1.45)

    fig.text(
        0.5, 0.128,
        "$\\bf{A\\ total\\ that\\ agrees\\ is\\ not\\ evidence\\ that\\ the\\ paths\\ agree.}$  "
        f"The compared paths sum to {total['iso']:+,.1f} kWh on the ISO side and "
        f"{total['ep']:+,.1f} kWh on the reference — a difference of "
        f"{abs(total['diff']):.1f} kWh — while individual paths differ by up to "
        f"{max(abs(diffs)):.0f} kWh.\n"
        "This is the same pattern as the false validation the work set out to detect: a "
        "plausible aggregate standing on offsetting errors. The Σ row is a like-for-like "
        "comparison of each path, not a closed balance — the two engines partition the zone "
        "balance differently, and internal gains (730.29 kWh) are identical by construction "
        "and not listed.",
        ha="center", va="top", fontsize=8.0, color=F.INK, linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#FFF7E6",
                  edgecolor="#E69F00", linewidth=0.9),
    )

    files = F.save(fig, "F12_residual_by_loss_path")

    numbers = [
        f"{p['path']}: ISO {p['iso']:+,.1f} kWh, EnergyPlus {p['ep']:+,.1f} kWh, "
        f"Δ {p['diff']:+,.1f} kWh"
        for p in paths
    ]
    numbers += [
        f"Σ compared paths: ISO {total['iso']:+,.1f} kWh, EnergyPlus "
        f"{total['ep']:+,.1f} kWh, Δ {total['diff']:+,.1f} kWh",
        f"Two dominant rows: {first['path']} {first['diff']:+,.1f} kWh and "
        f"{second['path']} {second['diff']:+,.1f} kWh — net {net:+,.1f} kWh, "
        f"{share:.0f} % of the total absolute disagreement",
        "Annual residual the decomposition explains: heating -26.09 kWh (-17.5 %), "
        "cooling -1.69 kWh (-7.8 %)",
    ]

    return {
        "id": "F12",
        "title": "The residual disagreement by loss path",
        "files": files,
        "sources": [
            "results/paper/validation_corrected/loss_paths.csv",
            "results/paper/validation_corrected/DISCREPANCY.md §1 (the source table, re-checked cell by cell)",
        ],
        "numbers": numbers,
        "note": (
            "**The per-path figures existed only in markdown.** "
            "`tools/paper/extract_loss_paths.py` parses the §1 table of `DISCREPANCY.md` "
            "into `loss_paths.csv` once, checking as it goes that every row's stated Δ equals "
            "ISO − E+ and that the paths sum to the table's own Σ row, within what 0.1 kWh "
            "printing allows. The figure then reads the CSV and re-checks every cell against "
            "the markdown, so the two cannot drift apart.\n\n"
            "**These are not the numbers the request quoted.** A brief for this figure cited "
            "Σ = −838.8 kWh against −823.4 kWh with party surfaces +161 kWh and the west wall "
            "−148 kWh. Those are the *superseded* values, from "
            "`results/paper_pre_wind_profile/validation_corrected/DISCREPANCY.md`, before the "
            "wind-profile correction. In the current committed decomposition both sides sum to "
            "−831.5 kWh and the two dominant rows are the west windows (+99.1 kWh) and the "
            "designed ventilation (−85.1 kWh); party surfaces fall to +9.9 kWh and the west "
            "wall to −20.4 kWh. The figure is built from the current file. Section 4.1.3 of "
            "the manuscript still carries the superseded pair and needs the same update.\n\n"
            "Rows are ordered by absolute difference, so which two rows the bracket picks out "
            "follows the data rather than being named in the script. The Σ row is separated by "
            "a rule because it is the sum of the rows above it, not a sixth path."
        ),
        "placement": "main-if-budget",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build())
