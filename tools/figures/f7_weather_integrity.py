"""F7 -- Weather-record integrity: the superseded Melbourne RO record against Essendon Fields."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

import figstyle as F

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

RO_COLOR = "#D55E00"          # superseded record
ESS_COLOR = "#0072B2"         # adopted record
DEAD_COLOR = "#B03030"
PIVOT_COLOR = "#7A7A7A"


def build() -> dict:
    ro = F.load_wind("ro")["summary"]
    ess = F.load_wind("essendon")["summary"]

    ro_mean = [ro["months"][str(m)]["mean"] for m in range(1, 13)]
    ess_mean = [ess["months"][str(m)]["mean"] for m in range(1, 13)]
    ro_zero = [100.0 * ro["months"][str(m)]["zero_share"] for m in range(1, 13)]
    dead = [m - 1 for m in ro["degenerate_months"]]

    if sorted(ro["degenerate_months"]) != [1, 3, 7, 9]:
        raise F.MissingQuantity(
            f"F7: the RO record reports degenerate months {ro['degenerate_months']}, "
            "the paper states Jan, Mar, Jul, Sep")
    if ess["degenerate_months"]:
        raise F.MissingQuantity(
            f"F7: the Essendon record reports degenerate months {ess['degenerate_months']}")

    fig, (a, b) = plt.subplots(1, 2, figsize=(13.6, 6.6),
                               gridspec_kw={"width_ratios": [1.45, 1.0]})

    # ---- A: monthly mean wind speed, both stations --------------------------
    x = np.arange(12)
    w = 0.38
    ba = a.bar(x - w / 2, ro_mean, w,
               color=[DEAD_COLOR if i in dead else RO_COLOR for i in x],
               edgecolor="white", linewidth=0.5, zorder=3)
    a.bar(x + w / 2, ess_mean, w, color=ESS_COLOR, edgecolor="white",
          linewidth=0.5, zorder=3)
    a.axhline(4.0, color=PIVOT_COLOR, lw=1.2, ls="--", zorder=4)

    top = max(max(ro_mean), max(ess_mean)) * 1.50
    a.set_ylim(0, top)
    for i in dead:
        a.annotate(
            f"{ro_mean[i]:.3f} m/s\n{ro_zero[i]:.1f} % of hours\nexactly 0.0",
            xy=(i - w / 2, 0.0), xytext=(i - w / 2, top * (0.62 if i in (0, 6) else 0.40)),
            ha="center", va="bottom", fontsize=7.0, color=DEAD_COLOR,
            fontweight="bold", linespacing=1.35, zorder=6,
            arrowprops=dict(arrowstyle="->", color=DEAD_COLOR, lw=1.0),
            bbox=dict(boxstyle="round,pad=0.32", facecolor="#FDEDED",
                      edgecolor=DEAD_COLOR, linewidth=0.8),
        )
    a.set_xticks(x)
    a.set_xticklabels(MONTHS)
    a.set_xlabel("Month")
    a.set_ylabel("Mean wind speed (m/s)")
    a.set_title("A — Monthly mean wind speed, the two station records", loc="left", pad=7)
    a.legend(handles=[
        Patch(facecolor=RO_COLOR, label="Melbourne Regional Office 948680 (superseded)"),
        Patch(facecolor=DEAD_COLOR, label="RO: dead-calm month (wind column identically 0.0 m/s)"),
        Patch(facecolor=ESS_COLOR, label="Melbourne-Essendon Fields 958660 (adopted)"),
        plt.Line2D([], [], color=PIVOT_COLOR, lw=1.2, ls="--", label="4 m/s pivot"),
    ], loc="upper center", ncol=1, fontsize=7.6)
    a.annotate(
        f"RO annual mean {ro['mean_wind_annual']:.2f} m/s, "
        f"{ro['pct_hours_exactly_zero']:.2f} % of hours exactly 0.0, "
        f"{ro['degenerate_hours']:,} h in four dead-calm months\n"
        f"Essendon annual mean {ess['mean_wind_annual']:.2f} m/s, "
        f"{ess['pct_hours_exactly_zero']:.2f} % exactly 0.0, no dead-calm month",
        xy=(0.5, 0.030), xycoords="axes fraction", ha="center", va="bottom",
        fontsize=7.8, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.42", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )

    # ---- B: the resulting C2 effect -----------------------------------------
    ro_dc, ess_dc = ro["delta_C"], ess["delta_C"]
    ro_zero_share = ro["bands"][0]["share_pct"]
    ess_zero_share = 100.0 - ess["pct_extra_from_nonzero_wind"]
    for want, got, name in ((48.73, ro_dc, "RO C2 effect"),
                            (-3.27, ess_dc, "Essendon C2 effect"),
                            (96.3, ro_zero_share, "RO exactly-zero share"),
                            (0.0, ess_zero_share, "Essendon exactly-zero share")):
        if abs(got - want) > 0.06:
            raise F.MissingQuantity(f"F7: {name} is {got:.3f}, the paper states {want}")

    bx = np.arange(2)
    b.bar(bx, [ro_dc, ess_dc], 0.46, color=[RO_COLOR, ESS_COLOR],
          edgecolor="white", linewidth=0.6, zorder=3)
    b.axhline(0, color="#7A7A7A", lw=1.0, zorder=4)
    b.set_xticks(bx)
    b.set_xticklabels(["Melbourne RO 948680\n(superseded)",
                       "Essendon Fields 958660\n(adopted)"])
    b.set_ylabel("C2 effect on annual sensible cooling (kWh)")
    b.set_ylim(-14, 78)
    b.set_title("B — The same correction, on the two records", loc="left", pad=7)

    # RO: value inside the bar head, note above it
    b.annotate(f"{ro_dc:+.2f} kWh", (0, ro_dc), xytext=(0, -6),
               textcoords="offset points", ha="center", va="top",
               fontsize=12, fontweight="bold", color="white")
    b.annotate(f"{ro_zero_share:.1f} % of it comes from hours\nreading exactly 0.0 m/s",
               (0, ro_dc), xytext=(0, 8), textcoords="offset points",
               ha="center", va="bottom", fontsize=8.0, color=F.INK, linespacing=1.4,
               bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                         edgecolor="#BBBBBB", linewidth=0.8), zorder=6)

    # Essendon: value just below the bar, note well clear above it
    b.annotate(f"{ess_dc:+.2f} kWh", (1, ess_dc), xytext=(0, -6),
               textcoords="offset points", ha="center", va="top",
               fontsize=12, fontweight="bold", color=ESS_COLOR)
    b.annotate(f"{ess_zero_share:.1f} % of it comes from hours\nreading exactly 0.0 m/s",
               (1, 14.0), ha="center", va="bottom", fontsize=8.0, color=F.INK,
               linespacing=1.4,
               arrowprops=dict(arrowstyle="->", color="#9A9A9A", lw=0.9),
               xytext=(1, 24.0),
               bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                         edgecolor="#BBBBBB", linewidth=0.8), zorder=6)

    b.annotate(
        "$\\bf{The\\ sign\\ inverts.}$ Same engine, same building,\n"
        "same correction — only the wind column differs.",
        xy=(0.5, 0.975), xycoords="axes fraction", ha="center", va="top",
        fontsize=8.4, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.42", facecolor="#FDEDED",
                  edgecolor=DEAD_COLOR, linewidth=0.9),
    )

    fig.suptitle("F7 — Weather-record integrity: a record can pass every conventional check "
                 "and still invert a correction",
                 fontsize=13, fontweight="bold", y=0.995)
    fig.text(0.5, 0.945,
             "The superseded Melbourne Regional Office file has the correct row count "
             "(8,760), no missing-value sentinels, and a plausible annual mean wind speed "
             f"({ro['mean_wind_annual']:.2f} m/s).\n"
             "Four calendar months of its wind column nevertheless read identically "
             "0.0 m/s — an artefact of the station's record ending in 2014 — which is enough "
             "to flip the sign of the C2 correction.",
             ha="center", va="top", fontsize=8.4, color="#4D4D4D", linespacing=1.45)

    fig.tight_layout(rect=(0.005, 0.005, 0.995, 0.900))
    files = F.save(fig, "F7_weather_record_integrity")

    return {
        "id": "F7",
        "title": "Weather-record integrity: the superseded contrast",
        "files": files,
        "sources": [
            "results/diagnostics/wind_stats.json (Melbourne RO 948680, superseded)",
            "results/diagnostics/wind_stats_essendon.json (Essendon Fields 958660, adopted)",
        ],
        "numbers": [
            f"RO: annual mean {ro['mean_wind_annual']:.2f} m/s, "
            f"{ro['pct_hours_exactly_zero']:.2f} % of hours exactly 0.0 m/s, "
            f"{ro['pct_hours_above_pivot']:.1f} % above the pivot, "
            f"dead-calm months Jan/Mar/Jul/Sep ({ro['degenerate_hours']:,} h, 33.7 % of the year)",
            f"Essendon: annual mean {ess['mean_wind_annual']:.2f} m/s, "
            f"{ess['pct_hours_exactly_zero']:.2f} % exactly 0.0 m/s, "
            f"{ess['pct_hours_above_pivot']:.1f} % above the pivot, no dead-calm month",
            f"C2 effect on sensible cooling: {ro_dc:+.2f} kWh on RO against "
            f"{ess_dc:+.2f} kWh on Essendon",
            f"Share attributable to exactly-zero-wind hours: {ro_zero_share:.1f} % (RO) "
            f"against {ess_zero_share:.1f} % (Essendon)",
            "RO monthly means (m/s): " + ", ".join(f"{m} {v:.3f}" for m, v in zip(MONTHS, ro_mean)),
            "Essendon monthly means (m/s): "
            + ", ".join(f"{m} {v:.2f}" for m, v in zip(MONTHS, ess_mean)),
        ],
        "note": (
            "Caption should make the general claim: a weather record can pass conventional "
            "validity checks — correct row count, no missing-value sentinels, plausible annual "
            "mean — and still invert the sign of a method-level correction."
        ),
        "placement": "supplementary",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build()["files"])
