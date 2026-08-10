"""F6 -- Wind field and the C2 attribution, Essendon Fields."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

import figstyle as F

PIVOT = 4.0
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

WIND_COLOR = "#0072B2"
ABOVE_COLOR = "#009E73"
BELOW_COLOR = "#9EC9E2"
ZERO_COLOR = "#D55E00"
PIVOT_COLOR = "#D55E00"


def build() -> dict:
    stats = F.load_wind("essendon")
    s = stats["summary"]
    epw = F.load_epw_wind()
    F.verify_epw_against_stats(epw, stats)     # aborts if the two disagree

    w = epw["wind"]
    hour = epw["hour"]
    mean_annual = s["mean_wind_annual"]
    pct_above = s["pct_hours_above_pivot"]
    pct_zero = s["pct_hours_exactly_zero"]

    fig, axes = plt.subplots(3, 2, figsize=(13.2, 13.4))
    (p1, p2), (p3, p4), (p5, p6) = axes

    # ---- 1. annual wind-speed distribution ---------------------------------
    bins = np.arange(0, np.ceil(w.max()) + 0.5, 0.5)
    counts, edges = np.histogram(w, bins=bins)
    centres = 0.5 * (edges[:-1] + edges[1:])
    colours = [ABOVE_COLOR if c > PIVOT else BELOW_COLOR for c in centres]
    p1.bar(centres, counts, 0.46, color=colours, edgecolor="white", linewidth=0.4, zorder=3)
    p1.axvline(PIVOT, color=PIVOT_COLOR, lw=1.6, ls="--", zorder=4)
    p1.axvline(mean_annual, color=F.INK, lw=1.2, ls=":", zorder=4)
    p1.set_xlabel("Wind speed (m/s)")
    p1.set_ylabel("Hours of the year")
    p1.set_title("1 — Annual wind-speed distribution", loc="left", pad=7)
    p1.set_xlim(-0.4, w.max() + 0.6)
    p1.annotate(
        f"$\\bf{{{pct_above:.1f}\\ \\%}}$ of hours above the {PIVOT:.0f} m/s pivot\n"
        f"$\\bf{{{pct_zero:.2f}\\ \\%}}$ of hours exactly 0.0 m/s "
        f"({int(round(pct_zero / 100 * len(w)))} h)\n"
        f"mean $\\bf{{{mean_annual:.2f}}}$ m/s, median {s['median_wind_annual']:.1f}, "
        f"max {s['max_wind_annual']:.1f} m/s",
        xy=(0.985, 0.965), xycoords="axes fraction", ha="right", va="top",
        fontsize=8.0, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )
    ytop = p1.get_ylim()[1]
    p1.annotate(
        f"$\\bf{{{PIVOT:.0f}\\ m/s\\ pivot}}$\n$h_{{ce}} = 4v+4$ equals the\n"
        "ISO fixed 20 W/(m²·K) here",
        xy=(PIVOT, ytop * 0.50), xytext=(10.6, ytop * 0.62),
        color=PIVOT_COLOR, fontsize=7.6, va="center", ha="center", linespacing=1.4,
        arrowprops=dict(arrowstyle="->", color=PIVOT_COLOR, lw=1.0,
                        connectionstyle="arc3,rad=0.18"),
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor=PIVOT_COLOR, linewidth=0.8), zorder=6)
    p1.legend(handles=[
        Patch(facecolor=ABOVE_COLOR, label=f"above the {PIVOT:.0f} m/s pivot"),
        Patch(facecolor=BELOW_COLOR, label=f"at or below {PIVOT:.0f} m/s"),
        plt.Line2D([], [], color=PIVOT_COLOR, lw=1.6, ls="--",
                   label=f"{PIVOT:.0f} m/s pivot"),
        plt.Line2D([], [], color=F.INK, lw=1.2, ls=":",
                   label=f"annual mean, {mean_annual:.2f} m/s"),
    ], loc="center left", bbox_to_anchor=(0.40, 0.32), fontsize=7.6)

    # ---- 2. mean wind speed by hour of day ---------------------------------
    hours = np.arange(1, 25)
    by_hour = np.array([w[hour == h].mean() for h in hours])
    p2.plot(hours, by_hour, color=WIND_COLOR, lw=1.8, marker="o", ms=4.0,
            mfc="white", mew=1.2, zorder=4)
    p2.axhline(PIVOT, color=PIVOT_COLOR, lw=1.4, ls="--", zorder=3)
    p2.axhline(mean_annual, color=F.INK, lw=1.0, ls=":", zorder=3)
    p2.fill_between(hours, PIVOT, by_hour, where=by_hour >= PIVOT,
                    color=ABOVE_COLOR, alpha=0.22, zorder=2, interpolate=True)
    p2.fill_between(hours, PIVOT, by_hour, where=by_hour < PIVOT,
                    color=BELOW_COLOR, alpha=0.45, zorder=2, interpolate=True)
    p2.set_xlabel("Hour of day (EPW hour index, 1 = 00:01–01:00, local standard time)")
    p2.set_ylabel("Mean wind speed (m/s)")
    p2.set_title("2 — Mean wind speed by hour of day", loc="left", pad=7)
    p2.set_xticks(range(1, 25, 2))
    p2.set_xlim(0.4, 24.6)
    p2.annotate(
        f"Every hour of the diurnal cycle carries wind:\n"
        f"the calmest hour averages {by_hour.min():.2f} m/s "
        f"(hour {int(hours[by_hour.argmin()])}),\n"
        f"the windiest {by_hour.max():.2f} m/s (hour {int(hours[by_hour.argmax()])}).",
        xy=(0.020, 0.965), xycoords="axes fraction", ha="left", va="top",
        fontsize=8.0, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )
    p2.text(0.6, PIVOT + 0.06, f"{PIVOT:.0f} m/s pivot", color=PIVOT_COLOR,
            fontsize=7.4, va="bottom", ha="left", fontweight="bold")

    # ---- 3. mean wind speed by month, with the exact-zero share ------------
    m_mean = [s["months"][str(m)]["mean"] for m in range(1, 13)]
    m_zero = [100.0 * s["months"][str(m)]["zero_share"] for m in range(1, 13)]
    x = np.arange(12)
    p3.bar(x, m_mean, 0.68, color=[ABOVE_COLOR if v > PIVOT else BELOW_COLOR for v in m_mean],
           edgecolor="white", linewidth=0.5, zorder=3)
    p3.axhline(PIVOT, color=PIVOT_COLOR, lw=1.4, ls="--", zorder=4)
    p3.set_xticks(x)
    p3.set_xticklabels(MONTHS)
    p3.set_ylabel("Mean wind speed (m/s)")
    p3.set_xlabel("Month")
    p3.set_ylim(0, max(m_mean) * 1.95)
    p3.set_title("3 — Mean wind speed by month, with the exact-zero share", loc="left", pad=7)
    for xi, v in zip(x, m_mean):
        p3.annotate(f"{v:.2f}", (xi, v), xytext=(0, 2), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7.0, color=F.INK)

    p3b = p3.twinx()
    p3b.grid(False)
    p3b.plot(x, m_zero, color=ZERO_COLOR, lw=1.5, marker="s", ms=4.2, mfc="white",
             mew=1.2, zorder=5)
    p3b.set_ylabel("Hours exactly 0.0 m/s (% of the month)", color=ZERO_COLOR)
    p3b.tick_params(axis="y", colors=ZERO_COLOR)
    p3b.set_ylim(0, max(max(m_zero) * 3.2, 1.0))

    worst_m = int(np.argmax(m_zero))
    if s["degenerate_months"]:
        raise F.MissingQuantity(
            f"F6: the Essendon record reports degenerate months {s['degenerate_months']}; "
            "the figure's claim that none is degenerate would be false")
    p3.annotate(
        f"$\\bf{{No\\ month\\ is\\ degenerate.}}$\n"
        f"Worst exact-zero share: {MONTHS[worst_m]} at {m_zero[worst_m]:.1f} %.\n"
        "The superseded record had four\nmonths at ~100 % (see F7).",
        xy=(0.985, 0.965), xycoords="axes fraction", ha="right", va="top",
        fontsize=8.0, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )
    p3.legend(handles=[
        Patch(facecolor=ABOVE_COLOR, label="monthly mean above the pivot"),
        Patch(facecolor=BELOW_COLOR, label="monthly mean at or below the pivot"),
        plt.Line2D([], [], color=ZERO_COLOR, lw=1.5, marker="s", ms=4.0, mfc="white",
                   label="exact-zero share (right axis)"),
    ], loc="upper left", fontsize=7.2)

    # ---- 4. wind on cooling-plant-on hours against the year -----------------
    n_cool = s["n_cooling_dyn"]
    mean_cool = s["mean_wind_cooling_dyn"]
    ratio = s["wind_ratio_cooling_to_annual"]
    p4.bar([0, 1], [mean_annual, mean_cool], 0.5,
           color=[F.MUTED_FILL, WIND_COLOR], edgecolor="white", linewidth=0.6, zorder=3)
    p4.axhline(PIVOT, color=PIVOT_COLOR, lw=1.4, ls="--", zorder=4)
    p4.set_xticks([0, 1])
    p4.set_xticklabels([f"All {s['n_hours']:,} hours\nof the year",
                        f"The {n_cool} cooling-plant-on hours\n(dynamic $h_{{ce}}$ run)"])
    p4.set_ylabel("Mean wind speed (m/s)")
    p4.set_ylim(0, mean_cool * 1.55)
    p4.set_title("4 — Wind speed on cooling-plant-on hours against the year", loc="left", pad=7)
    for xi, v in zip([0, 1], [mean_annual, mean_cool]):
        p4.annotate(f"{v:.2f} m/s", (xi, v), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9.0, fontweight="bold", color=F.INK)
    p4.annotate(
        f"Cooling hours are $\\bf{{{ratio:.2f}×}}$ the annual mean wind speed.\n"
        f"$\\bf{{{s['pct_cooling_hours_above_pivot']:.1f}\\ \\%}}$ of them are above the "
        f"{PIVOT:.0f} m/s pivot, against {pct_above:.1f} % of the year;\n"
        f"mean $h_{{ce}}$ over cooling hours is {s['mean_h_ce_cooling']:.2f} W/(m²·K) "
        f"against {s['mean_h_ce_annual']:.2f} over the year,\n"
        "both above the ISO fixed 20 W/(m²·K).",
        xy=(0.5, 0.955), xycoords="axes fraction", ha="center", va="top",
        fontsize=8.0, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )
    p4.text(1.30, PIVOT, f"  {PIVOT:.0f} m/s pivot", color=PIVOT_COLOR, fontsize=7.6,
            va="center", ha="left", fontweight="bold")

    # ---- 5. extra sensible cooling by wind band -----------------------------
    bands = s["bands"]
    labels = [b["label"].replace("–", "–") for b in bands]
    extra = [b["extra_cooling_kWh"] for b in bands]
    hoursb = [b["hours"] for b in bands]
    xb = np.arange(len(bands))
    cols = [ZERO_COLOR if e > 0 else WIND_COLOR for e in extra]
    p5.bar(xb, extra, 0.6, color=cols, edgecolor="white", linewidth=0.6, zorder=3)
    p5.axhline(0, color="#7A7A7A", lw=0.9, zorder=4)
    p5.set_xticks(xb)
    p5.set_xticklabels([f"{l}\n({h:,} h)" for l, h in zip(labels, hoursb)], fontsize=8.0)
    p5.set_ylabel("Extra sensible cooling attributed to C2 (kWh)")
    p5.set_xlabel("Wind band")
    p5.set_title("5 — Extra sensible cooling attributed by wind band", loc="left", pad=7)
    lo, hi = min(extra), max(extra)
    p5.set_ylim(lo - (hi - lo) * 0.30, hi + (hi - lo) * 1.55)
    for xi, e, b in zip(xb, extra, bands):
        p5.annotate(f"{e:+.2f} kWh\n({b['share_pct']:.1f} %)",
                    (xi, e), xytext=(0, 4 if e >= 0 else -4),
                    textcoords="offset points", ha="center",
                    va="bottom" if e >= 0 else "top", fontsize=7.8, color=F.INK,
                    linespacing=1.35)
    if abs(s["pct_extra_from_nonzero_wind"] - 100.0) > 0.05:
        raise F.MissingQuantity(
            f"F6: {s['pct_extra_from_nonzero_wind']:.2f} % of the C2 effect comes from "
            "non-zero wind, the paper states 100 %")
    p5.annotate(
        f"$\\bf{{100.0\\ \\%}}$ of the {s['total_extra_cooling_kWh']:+.2f} kWh arises in "
        "genuine, non-zero wind.\n"
        f"The exactly-zero bucket contributes {s['extra_cooling_zero_wind_kWh']:+.2f} kWh "
        f"over {bands[0]['hours']} hours.\n"
        "Shares are of the signed total, so a band opposing the total reads negative.",
        xy=(0.5, 0.955), xycoords="axes fraction", ha="center", va="top",
        fontsize=8.0, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )

    # ---- 6. the controlled experiment ---------------------------------------
    c_fix, c_dyn = s["C_fix"], s["C_dyn"]
    h_fix, h_dyn = s["H_fix"], s["H_dyn"]
    delta_c = s["delta_C"]
    for want, got, name in ((9.61, c_fix, "ISO fixed cooling"),
                            (6.34, c_dyn, "dynamic cooling"),
                            (-3.27, delta_c, "C2 cooling effect")):
        if abs(got - want) > 0.006:
            raise F.MissingQuantity(
                f"F6: {name} is {got:.4f} kWh, the paper states {want}")
    p6.bar([0, 1], [c_fix, c_dyn], 0.5, color=[F.MUTED_FILL, WIND_COLOR],
           edgecolor="white", linewidth=0.6, zorder=3)
    p6.set_xticks([0, 1])
    p6.set_xticklabels(["ISO fixed\n$h_{ce}$ = 20 W/(m²·K)",
                        "Dynamic\n$h_{ce} = 4v + 4$"])
    p6.set_ylabel("Annual sensible cooling (kWh)")
    p6.set_ylim(0, c_fix * 2.25)
    p6.set_title("6 — The controlled experiment: one switch, nothing else changed",
                 loc="left", pad=7)
    for xi, v in zip([0, 1], [c_fix, c_dyn]):
        p6.annotate(f"{v:.2f} kWh", (xi, v), xytext=(0, -5), textcoords="offset points",
                    ha="center", va="top", fontsize=9.5, fontweight="bold",
                    color=F.INK if xi == 0 else "white")
    br = c_fix * 1.18
    p6.plot([0, 0, 1, 1], [c_fix * 1.08, br, br, c_dyn * 1.08], color=F.INK, lw=1.0)
    p6.annotate(f"{delta_c:+.2f} kWh", (0.5, br), xytext=(0, 3),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=11, fontweight="bold", color=F.DECREASE)
    p6.annotate(
        "The same engine, run twice, changing only the $h_{ce}$ model.\n"
        f"Sensible heating moves {s['delta_H']:+.2f} kWh ({h_fix:.2f} → {h_dyn:.2f}); "
        f"the cooling-plant hour count moves {s['n_cooling_dyn'] - s['n_cooling_fix']:+d} "
        f"({s['n_cooling_fix']} → {s['n_cooling_dyn']} h).\n"
        f"Verdict {stats['verdict']}: the year is windier than the pivot and the "
        "cooling hours are windier still.",
        xy=(0.5, 0.955), xycoords="axes fraction", ha="center", va="top",
        fontsize=8.0, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )

    fig.suptitle("F6 — Wind field and the C2 attribution, Melbourne-Essendon Fields",
                 fontsize=13.5, fontweight="bold", y=0.998)
    fig.text(0.5, 0.972,
             "AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011–2025 · 8,760 rows · "
             "0 missing wind values · screened by tools/diagnostics/weather_integrity.py\n"
             "Panels 3–6 are read from results/diagnostics/wind_stats_essendon.json; panels 1–2 "
             "are computed from the committed EPW wind column, whose annual aggregates are "
             "asserted against that file before plotting.",
             ha="center", va="top", fontsize=8.3, color="#4D4D4D", linespacing=1.45)

    fig.tight_layout(rect=(0.005, 0.004, 0.995, 0.948))
    files = F.save(fig, "F6_wind_field_and_c2")

    return {
        "id": "F6",
        "title": "Wind field and the C2 attribution",
        "files": files,
        "sources": [
            "results/diagnostics/wind_stats_essendon.json",
            "results/diagnostics/wind_verdict_essendon.md (the same numbers, for cross-check)",
            "weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw "
            "(panels 1–2 only, verified against wind_stats_essendon.json)",
        ],
        "numbers": [
            f"Annual: mean {mean_annual:.2f} m/s, median {s['median_wind_annual']:.1f}, "
            f"max {s['max_wind_annual']:.1f}; {pct_above:.1f} % above the 4 m/s pivot; "
            f"{pct_zero:.2f} % exactly 0.0 m/s",
            f"Diurnal: calmest hour {by_hour.min():.2f} m/s (hour {int(hours[by_hour.argmin()])}), "
            f"windiest {by_hour.max():.2f} m/s (hour {int(hours[by_hour.argmax()])})",
            "No degenerate month; worst exact-zero share "
            f"{MONTHS[worst_m]} {m_zero[worst_m]:.1f} %",
            f"Cooling-plant-on hours: {n_cool} h, mean wind {mean_cool:.2f} m/s "
            f"({ratio:.2f}× the annual mean), {s['pct_cooling_hours_above_pivot']:.1f} % "
            "above the pivot",
            "Wind bands (hours, extra cooling kWh, share): "
            + "; ".join(f"{b['label']} {b['hours']:,} h {b['extra_cooling_kWh']:+.2f} kWh "
                        f"{b['share_pct']:.1f} %" for b in bands),
            f"100.0 % of the {s['total_extra_cooling_kWh']:+.2f} kWh arises in non-zero wind",
            f"Controlled experiment: cooling {c_fix:.2f} kWh at the fixed ISO coefficient "
            f"against {c_dyn:.2f} kWh with h_ce = 4v + 4, a reduction of {abs(delta_c):.2f} kWh; "
            f"heating {h_fix:.2f} → {h_dyn:.2f} kWh; verdict {stats['verdict']}",
        ],
        "note": (
            "Panels 1 and 2 need hourly detail that the committed summary JSON does not carry, "
            "so they are computed from the committed EPW named in the trajectory's provenance — "
            "the same file the diagnostic ran on, not a second run. figstyle."
            "verify_epw_against_stats asserts hour count, mean, max, exact-zero share and "
            "above-pivot share against wind_stats_essendon.json and aborts on any mismatch."
        ),
        "placement": "main",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build()["files"])
