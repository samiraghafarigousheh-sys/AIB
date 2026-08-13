"""
F1 -- ISO 52016-1 against a matched EnergyPlus reference, before and after.

Rebuilt from ``results/paper/validation_corrected/``. The previous version of
this figure was built from ``results/paper/baseline_vs_ep_v2/``, which predates
the discovery of four defects in the EnergyPlus reference model; its EnergyPlus
heating column (1,120.2 kWh) is an artefact of those defects and it showed the
ISO engine OVER-predicting heating by +58.8 %. Against a repaired reference the
same, byte-identical ISO column UNDER-predicts by 14.5 %. The figure and Table 3
stated opposite conclusions about the paper's most visible number; this is the
figure that agrees with the table.

Two panels, because there are two comparisons and not one. Each engine is set
against a reference matched to IT, and the corrected loads are an order of
magnitude smaller, so the panels carry independent scales -- on a shared axis
the corrected pair would be four pixels tall.

Each pair is annotated with BOTH forms of the difference. The paper's argument
is that absolute convergence is the meaningful statement and that relative error
destabilises as the load approaches zero: the heating gap falls from 302.6 kWh
to 26.1 kWh, a 91 % narrowing, while the percentage moves the wrong way, from
-14.5 % to -17.5 %. Neither number characterises the result on its own.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle as F

ISO_COLOR = "#0072B2"      # Okabe-Ito blue, as in the superseded F1
EP_COLOR = "#E69F00"       # Okabe-Ito orange, as in the superseded F1

METRICS = ["Heating", "Cooling", "Total"]

PANEL_TITLE = {
    "baseline": "A  Baseline engine",
    "corrected": "B  Corrected engine",
}

SUBTITLE = (
    "Same weather ({weather}); ideal loads; both engines sensible-only.\n"
    "Each engine is compared against a reference matched to it, and both references carry "
    "the repairs to the four defects of Section 4.2. Differences are stated against the "
    "EnergyPlus reference."
).format(weather="Melbourne-Essendon Fields TMYx 2011–2025")


def _panel(ax, section: str, data: dict) -> None:
    x = np.arange(len(METRICS))
    w = 0.36
    iso_vals = [data[m]["iso"] for m in METRICS]
    ep_vals = [data[m]["ep"] for m in METRICS]

    b1 = ax.bar(x - w / 2, iso_vals, w, label="ISO 52016-1",
                color=ISO_COLOR, edgecolor="white", linewidth=0.6)
    b2 = ax.bar(x + w / 2, ep_vals, w, label="EnergyPlus (matched reference)",
                color=EP_COLOR, edgecolor="white", linewidth=0.6)

    top = max(iso_vals + ep_vals)
    ax.set_ylim(0, top * 1.40)

    fmt = "{:,.0f}" if top > 500 else "{:,.1f}"
    for bars in (b1, b2):
        for rect in bars:
            h = rect.get_height()
            # Inside the bar head, so the difference brackets above stay clear.
            ax.annotate(fmt.format(h),
                        (rect.get_x() + rect.get_width() / 2, h),
                        xytext=(0, -4), textcoords="offset points",
                        ha="center", va="top", fontsize=8.0, fontweight="bold",
                        color="white")

    for i, m in enumerate(METRICS):
        gap = data[m]["diff_kWh"]
        pct = data[m]["diff_pct_vs_ep"]
        y = max(iso_vals[i], ep_vals[i])
        foot = y + top * 0.030
        bracket_y = y + top * 0.080
        ax.plot([x[i] - w / 2, x[i] - w / 2, x[i] + w / 2, x[i] + w / 2],
                [foot, bracket_y, bracket_y, foot],
                color=F.INK, lw=0.9, clip_on=False)
        colour = F.INCREASE if gap > 0 else F.DECREASE
        # The absolute gap leads, because that is the statement the paper makes;
        # the percentage sits under it in lighter type, because on the corrected
        # panel it is a percentage of a very small number.
        ax.annotate(f"{gap:+,.1f} kWh",
                    (x[i], bracket_y), xytext=(0, 12), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9.5, fontweight="bold",
                    color=colour)
        ax.annotate(f"({pct:+.1f} %)",
                    (x[i], bracket_y), xytext=(0, 2), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.2, color=colour)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{m}\n(sensible)" for m in METRICS])
    ax.set_ylabel("Annual energy need (kWh)")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")

    ax.set_title(PANEL_TITLE[section], pad=26, loc="left")
    ax.text(0.0, 1.005, F.VALIDATION_PANEL_BASIS[section], transform=ax.transAxes,
            ha="left", va="bottom", fontsize=7.2, color="#4D4D4D", linespacing=1.35)

    # Same quantity, second unit -- a linear rescaling of the left axis, not a
    # second series.
    ax2 = ax.twinx()
    ax2.set_ylim(ax.get_ylim()[0] / F.NET_FLOOR_AREA_M2,
                 ax.get_ylim()[1] / F.NET_FLOOR_AREA_M2)
    ax2.set_ylabel("kWh/m²·yr", fontsize=8)
    ax2.grid(False)


def build() -> dict:
    val = F.load_validation_corrected()

    fig, axes = plt.subplots(1, 2, figsize=(11.8, 7.4))
    # Explicit spacing rather than tight_layout: the figure carries a two-line
    # title, a three-line subtitle and a three-line footer outside the axes, and
    # tight_layout does not know about any of them.
    fig.subplots_adjust(left=0.075, right=0.945, top=0.755, bottom=0.205, wspace=0.30)
    for ax, section in zip(axes, ("baseline", "corrected")):
        _panel(ax, section, val[section])

    axes[0].legend(loc="upper left", ncol=1, bbox_to_anchor=(0.0, 0.94))

    heat_b = val["baseline"]["Heating"]
    heat_c = val["corrected"]["Heating"]
    cool_b = val["baseline"]["Cooling"]
    cool_c = val["corrected"]["Cooling"]
    narrow_h = 100.0 * (1.0 - abs(heat_c["diff_kWh"]) / abs(heat_b["diff_kWh"]))
    narrow_c = 100.0 * (1.0 - abs(cool_c["diff_kWh"]) / abs(cool_b["diff_kWh"]))

    fig.text(
        0.5, 0.988,
        "F1 — ISO 52016-1 against a matched EnergyPlus reference, baseline and corrected\n"
        "The ISO engine under-predicts on both engines and both components; "
        "every absolute gap narrows",
        ha="center", va="top", fontsize=11.5, fontweight="bold", linespacing=1.45,
    )
    fig.text(0.5, 0.906, SUBTITLE, ha="center", va="top", fontsize=7.8,
             color="#4D4D4D", linespacing=1.45)

    fig.text(
        0.5, 0.135,
        "$\\bf{Read\\ the\\ absolute\\ gap,\\ not\\ the\\ percentage.}$  "
        f"Heating: {heat_b['diff_kWh']:+,.1f} → {heat_c['diff_kWh']:+,.1f} kWh, "
        f"a {narrow_h:.0f} % narrowing, while the percentage moves the other way, "
        f"{heat_b['diff_pct_vs_ep']:+.1f} % → {heat_c['diff_pct_vs_ep']:+.1f} %.  "
        f"Cooling: {cool_b['diff_kWh']:+,.1f} → {cool_c['diff_kWh']:+,.1f} kWh, "
        f"a {narrow_c:.0f} % narrowing, at "
        f"{cool_b['diff_pct_vs_ep']:+.1f} % → {cool_c['diff_pct_vs_ep']:+.1f} %.\n"
        "The corrections cut the loads themselves by an order of magnitude, so a much "
        "smaller residual sits on a much smaller denominator. Relative error is not a "
        "stable measure as the load approaches zero; neither figure should be quoted "
        "without the other.",
        ha="center", va="top", fontsize=8.0, color=F.INK, linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#FFF7E6",
                  edgecolor="#E69F00", linewidth=0.9),
    )

    # (spacing is set explicitly above)
    files = F.save(fig, "F1_baseline_iso_vs_energyplus")

    numbers = []
    for section in ("baseline", "corrected"):
        label = F.VALIDATION_PANEL_LABEL[section]
        for m in METRICS:
            r = val[section][m]
            numbers.append(
                f"{label}, {m.lower()}: ISO {r['iso']:,.2f} kWh vs EnergyPlus "
                f"{r['ep']:,.2f} kWh — {r['diff_kWh']:+,.2f} kWh "
                f"({r['diff_pct_vs_ep']:+.1f} % vs EP)"
            )
    numbers += [
        f"Absolute heating gap narrows {heat_b['diff_kWh']:+,.1f} → "
        f"{heat_c['diff_kWh']:+,.1f} kWh ({narrow_h:.0f} %); "
        f"cooling {cool_b['diff_kWh']:+,.1f} → {cool_c['diff_kWh']:+,.1f} kWh "
        f"({narrow_c:.0f} %)",
        f"Per area, total: baseline ISO {val['baseline']['Total']['iso_per_sqm']:.2f} vs "
        f"EP {val['baseline']['Total']['ep_per_sqm']:.2f}; corrected ISO "
        f"{val['corrected']['Total']['iso_per_sqm']:.2f} vs EP "
        f"{val['corrected']['Total']['ep_per_sqm']:.2f} kWh/m²·yr",
    ]

    return {
        "id": "F1",
        "title": "ISO 52016-1 against a matched EnergyPlus reference, baseline and corrected",
        "files": files,
        "sources": [
            "results/paper/validation_corrected/validation_corrected.csv",
            "results/paper/validation_corrected/validation_corrected.md (Table 3, for cross-check)",
            "results/paper/SUPERSEDED_wind_profile.md §6b (the baseline panel, re-run and confirmed unmoved)",
        ],
        "numbers": numbers,
        "note": (
            "**This figure replaces a version built from `results/paper/baseline_vs_ep_v2/`, "
            "which contradicted the paper.** That directory predates the discovery of the four "
            "defects in the EnergyPlus reference model, and its heating comparison — ISO 1,779.4 "
            "against EnergyPlus 1,120.2 kWh, +58.8 % — showed the ISO engine *over*-predicting. "
            "Against a repaired reference the same, byte-identical ISO column gives 1,779.4 "
            "against 2,081.97 kWh, −14.5 %: the engine *under*-predicts. `baseline_vs_ep_v2/` is "
            "left untouched and carries its own `DEFECT_NOTICE.md`; nothing in this figure is "
            "read from it.\n\n"
            "The twelve kWh values are asserted against Table 3 before the figure is drawn, and "
            "heating + cooling is asserted to equal the stated total on all four columns. "
            "Differences are recomputed from the two kWh columns rather than read from the "
            "CSV's `diff_pct_vs_ep`, and are drawn in both forms.\n\n"
            "Both engines are sensible-only here, so the corrected ISO total of 142.78 kWh is "
            "**not** the canonical 144.28 kWh of the paper's metric: that figure adds the "
            "1.51 kWh of gated latent cooling the ISO side reports separately, and the "
            "EnergyPlus ideal loads carry 0.93 kWh of latent cooling with humidification "
            "disabled. Each panel carries its own scale; the two must not be read as one axis."
        ),
        "placement": "main",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build())
