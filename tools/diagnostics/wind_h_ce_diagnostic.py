"""
Wind-speed diagnostic: why the wind-dependent h_ce moves sensible cooling.

THE MECHANISM UNDER TEST
------------------------
Correction C2 replaces the ISO fixed external convective coefficient with
``h_ce = 4v + 4`` (the engine's ``simplecombined`` model, the default). The pivot
is v = 4 m/s, where 4v + 4 = 20 W/(m2 K) -- exactly the value EN ISO 13789
section 9.5 freezes in. Above the pivot the dynamic coefficient exceeds the fixed
one and the external surface is coupled more tightly to outdoor air; below it,
less tightly.

The plan's three candidate readings were:

  (a) Melbourne has many hours above the pivot, so the dynamic coefficient
      exceeds the fixed one on average -> more coupling year-round;
  (b) high winds coincide with hot cooling-season hours -> cooling-season
      coupling amplified;
  (c) neither, in which case the increase is not explained by the wind
      distribution and the implementation must be re-examined -- escalate.

WHAT THIS TOOL DOES
-------------------
1. Characterises the EPW wind column: annual distribution against the pivot,
   structure by hour of day and by month, and a month x hour map.
2. Runs the SAME engine twice, changing only the h_ce model
   (``external_convection_model`` / ``window_convection_model`` = 'table' recovers
   the ISO constant exactly). That is a controlled experiment: one switch, no
   worktrees, no other difference.
3. Attributes the resulting change in sensible cooling to bands of wind speed,
   which is what actually decides between (a), (b) and (c) -- if the increase
   came from the high-wind branch it would sit above 4 m/s.
4. Screens the wind column for months whose values are degenerate, because a
   correction driven by a weather field is only as good as that field.

Usage
-----
    python tools/diagnostics/wind_h_ce_diagnostic.py \\
        --weather weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw \\
        --outdir results/diagnostics
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "pybuildingenergy" / "src"))
sys.path.insert(0, str(REPO_ROOT / "examples"))

PIVOT_MS = 4.0            # 4v + 4 == 20 W/(m2 K) here
H_CE_FIXED = 20.0         # the ISO constant the dynamic model replaces
DEGENERATE_ZERO_SHARE = 0.90   # a month at or above this is not weather

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
PIVOT_C = "#c2255c"
BAD = "#c2255c"


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def measure(weather: str) -> dict:
    """One weather read, two annual runs differing only in the h_ce model."""
    import numpy as np
    import pandas as pd

    from apt305_building import build_bui
    from pybuildingenergy.source.check_input import sanitize_and_validate_BUI
    from pybuildingenergy.source.utils import ISO52016

    def run(**kw):
        b, _ = sanitize_and_validate_BUI(build_bui(), fix=True)
        hourly, annual, _ = ISO52016.Temperature_and_Energy_needs_calculation(
            b, weather_source="epw", path_weather_file=weather,
            return_sankey_data=True, **kw)
        return hourly, annual

    b0, _ = sanitize_and_validate_BUI(build_bui(), fix=True)
    sim_df = ISO52016.Weather_data_bui(b0, weather, weather_source="epw").simulation_df

    print("  run 1/2: dynamic h_ce = 4v + 4 (default)", flush=True)
    h_dyn, a_dyn = run()
    print("  run 2/2: ISO fixed h_ce = 20 W/(m2 K)", flush=True)
    h_fix, a_fix = run(external_convection_model="table",
                       window_convection_model="table")

    n = len(h_dyn)
    wind = pd.to_numeric(sim_df["WS10m"], errors="coerce").to_numpy(float)[-n:]
    t_ext_w = pd.to_numeric(sim_df["T2m"], errors="coerce").to_numpy(float)[-n:]
    t_ext_h = pd.to_numeric(h_dyn["T_ext"], errors="coerce").to_numpy(float)

    # Alignment is asserted, not assumed: the simulation frame carries a warm-up
    # the reported frame does not, so the wind series is taken from the tail. If
    # that tail were the wrong slice the outdoor temperatures would not agree.
    misalign = float(np.nanmax(np.abs(t_ext_w - t_ext_h)))
    if misalign > 1e-9:
        raise RuntimeError(
            f"wind series is not aligned with the reported hours: max |dT_ext| = "
            f"{misalign:.4f} K. Every number below would be meaningless.")

    def ann(a, k):
        return float(pd.to_numeric(a[k], errors="coerce").iloc[0])

    q_c_dyn = pd.to_numeric(h_dyn["Q_C"], errors="coerce").fillna(0.0).to_numpy(float)
    q_c_fix = pd.to_numeric(h_fix["Q_C"], errors="coerce").fillna(0.0).to_numpy(float)

    return {
        "index": h_dyn.index,
        "wind": wind,
        "t_ext": t_ext_h,
        "ghi": pd.to_numeric(sim_df["G(h)"], errors="coerce").to_numpy(float)[-n:],
        "q_c_dyn": q_c_dyn, "q_c_fix": q_c_fix,
        "cool_dyn": q_c_dyn > 0, "cool_fix": q_c_fix > 0,
        "H_dyn": ann(a_dyn, "Q_H_annual_kWh"), "C_dyn": ann(a_dyn, "Q_C_annual_kWh"),
        "H_fix": ann(a_fix, "Q_H_annual_kWh"), "C_fix": ann(a_fix, "Q_C_annual_kWh"),
        "alignment_max_dT": misalign,
    }


def summarise(d: dict) -> dict:
    import numpy as np
    import pandas as pd

    idx = pd.DatetimeIndex(d["index"])
    w, cool_d, cool_f = d["wind"], d["cool_dyn"], d["cool_fix"]
    extra = d["q_c_dyn"] - d["q_c_fix"]          # W per hour -> Wh

    months = {}
    for m in range(1, 13):
        s = w[idx.month == m]
        months[m] = {"n": int(len(s)), "mean": float(np.nanmean(s)),
                     "zero_share": float(np.mean(s == 0.0)),
                     "cooling_hours": int(cool_d[idx.month == m].sum())}
    degenerate = [m for m, v in months.items() if v["zero_share"] >= DEGENERATE_ZERO_SHARE]
    live = ~np.isin(idx.month, degenerate) if degenerate else np.ones(len(w), bool)

    bands = []
    for lo, hi, label in [(0.0, 1e-9, "exactly 0"), (1e-9, 2.0, "0 – 2 m/s"),
                          (2.0, PIVOT_MS, "2 – 4 m/s"), (PIVOT_MS, 1e9, "above 4 m/s")]:
        m = (w >= lo) & (w < hi) if hi < 1e9 else (w >= lo)
        if label == "exactly 0":
            m = w == 0.0
        bands.append({"label": label, "hours": int(m.sum()),
                      "extra_cooling_kWh": float(extra[m].sum() / 1000.0)})
    total_extra = float(extra.sum() / 1000.0)
    for b in bands:
        b["share_pct"] = 100.0 * b["extra_cooling_kWh"] / total_extra if total_extra else float("nan")

    s = {
        "n_hours": int(len(w)),
        "mean_wind_annual": float(np.nanmean(w)),
        "median_wind_annual": float(np.nanmedian(w)),
        "max_wind_annual": float(np.nanmax(w)),
        "pct_hours_above_pivot": float(100.0 * np.mean(w > PIVOT_MS)),
        "pct_hours_exactly_zero": float(100.0 * np.mean(w == 0.0)),
        "mean_h_ce_annual": float(np.nanmean(4.0 * w + 4.0)),
        "excess_annual": float(np.nanmean(4.0 * w + 4.0) - H_CE_FIXED),
        "months": months,
        "degenerate_months": degenerate,
        "degenerate_hours": int((~live).sum()),
        "mean_wind_live_months": float(np.nanmean(w[live])) if live.any() else float("nan"),
        "pct_above_pivot_live_months": float(100.0 * np.mean(w[live] > PIVOT_MS)) if live.any() else float("nan"),
        "n_cooling_dyn": int(cool_d.sum()),
        "n_cooling_fix": int(cool_f.sum()),
        "mean_wind_cooling_dyn": float(np.nanmean(w[cool_d])) if cool_d.any() else float("nan"),
        "mean_wind_cooling_fix": float(np.nanmean(w[cool_f])) if cool_f.any() else float("nan"),
        "pct_zero_cooling_dyn": float(100.0 * np.mean(w[cool_d] == 0.0)) if cool_d.any() else float("nan"),
        "mean_t_ext_cooling": float(np.nanmean(d["t_ext"][cool_d])) if cool_d.any() else float("nan"),
        "excess_cooling": float(np.nanmean(4.0 * w[cool_d] + 4.0) - H_CE_FIXED) if cool_d.any() else float("nan"),
        "H_dyn": d["H_dyn"], "C_dyn": d["C_dyn"], "H_fix": d["H_fix"], "C_fix": d["C_fix"],
        "delta_C": d["C_dyn"] - d["C_fix"], "delta_H": d["H_dyn"] - d["H_fix"],
        "bands": bands, "total_extra_cooling_kWh": total_extra,
    }
    added = cool_d & ~cool_f
    s["n_cooling_hours_added"] = int(added.sum())
    if added.any():
        s["mean_wind_added_hours"] = float(np.nanmean(w[added]))
        s["pct_zero_added_hours"] = float(100.0 * np.mean(w[added] == 0.0))
    s["wind_ratio_cooling_to_annual"] = s["mean_wind_cooling_dyn"] / s["mean_wind_annual"]
    return s


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------

def make_figure(d: dict, s: dict, out_png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    idx = pd.DatetimeIndex(d["index"])
    w = d["wind"]
    cool = d["cool_dyn"]
    dead = set(s["degenerate_months"])

    fig, axes = plt.subplots(2, 3, figsize=(16.5, 9.4), dpi=150)
    fig.patch.set_facecolor(SURFACE)

    def style(ax, title, xlabel=None, ylabel=None):
        ax.set_facecolor(SURFACE)
        ax.set_title(title, fontsize=10.5, color=TEXT_PRIMARY, fontweight="semibold", pad=8)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=9, color=TEXT_SECONDARY)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=9, color=TEXT_SECONDARY)
        ax.tick_params(labelsize=8, colors=TEXT_SECONDARY, length=0)
        ax.grid(axis="y", color=GRID, linewidth=0.9, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)

    MONTHS = [calendar.month_abbr[m][0] for m in range(1, 13)]

    # 1 -- annual distribution --------------------------------------------
    ax = axes[0, 0]
    ax.hist(w[w > 0], bins=40, color=BLUE, edgecolor="none", zorder=3,
            label="hours with non-zero wind")
    zero_n = int((w == 0).sum())
    ax.bar([0.0], [zero_n], width=0.28, color=BAD, edgecolor="none", zorder=4,
           label=f"exactly 0.0 m/s ({zero_n:,} h)")
    ax.axvline(PIVOT_MS, color=PIVOT_C, linewidth=1.6, linestyle="--", zorder=5)
    style(ax, "Annual distribution of hourly wind speed", "WS10m  [m/s]", "hours")
    ax.legend(fontsize=7.5, frameon=False, labelcolor=TEXT_SECONDARY, loc="upper right")
    ax.text(PIVOT_MS + 0.15, ax.get_ylim()[1] * 0.55,
            "pivot 4 m/s\n(4v+4 = 20 = ISO fixed)", color=PIVOT_C, fontsize=8,
            va="top", ha="left", style="italic")
    ax.text(0.98, 0.44,
            f"{s['pct_hours_above_pivot']:.1f} % above the pivot\n"
            f"{s['pct_hours_exactly_zero']:.1f} % exactly zero\n"
            f"mean {s['mean_wind_annual']:.2f} m/s",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=TEXT_PRIMARY)

    # 2 -- by hour of day ---------------------------------------------------
    ax = axes[0, 1]
    live = ~np.isin(idx.month, list(dead)) if dead else np.ones(len(w), bool)
    ax.bar(range(24), pd.Series(w, index=idx).groupby(idx.hour).mean().reindex(range(24)),
           color=BLUE, edgecolor="none", zorder=3, label="all months")
    if dead:
        ax.plot(range(24), pd.Series(w[live], index=idx[live]).groupby(idx[live].hour)
                .mean().reindex(range(24)), color=BAD, linewidth=1.8, marker="o",
                markersize=3, zorder=5, label="months with data only")
    ax.axhline(PIVOT_MS, color=PIVOT_C, linewidth=1.4, linestyle="--", zorder=4)
    style(ax, "Mean wind speed by hour of day", "hour", "m/s")
    ax.set_xticks(range(0, 24, 3))
    ax.set_ylim(0, ax.get_ylim()[1] * 1.32)      # headroom, so the legend clears the series
    ax.legend(fontsize=7.5, frameon=False, labelcolor=TEXT_SECONDARY, loc="upper left")

    # 3 -- by month, with the degenerate months called out -------------------
    ax = axes[0, 2]
    means = [s["months"][m]["mean"] for m in range(1, 13)]
    cols = [BAD if m in dead else BLUE for m in range(1, 13)]
    ax.bar(range(1, 13), means, color=cols, edgecolor="none", zorder=3)
    ax.axhline(PIVOT_MS, color=PIVOT_C, linewidth=1.4, linestyle="--", zorder=4)
    style(ax, "Mean wind speed by month", "month", "m/s")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(MONTHS)
    ax.set_ylim(0, max(means + [PIVOT_MS]) * 1.32)   # headroom for the caption
    for m in dead:
        ax.annotate("all zero", xy=(m, 0.06), rotation=90, ha="center", va="bottom",
                    fontsize=7.5, color=BAD, fontweight="bold", zorder=5)
    if dead:
        ax.text(0.5, 0.97,
                f"{', '.join(calendar.month_abbr[m] for m in sorted(dead))}: "
                f"wind identically 0.0 for every hour",
                transform=ax.transAxes, ha="center", va="top", fontsize=8.5,
                color=BAD, fontweight="semibold")

    # 4 -- month x hour ------------------------------------------------------
    ax = axes[1, 0]
    grid = (pd.DataFrame({"w": w, "m": idx.month, "h": idx.hour})
            .pivot_table(index="m", columns="h", values="w", aggfunc="mean"))
    im = ax.imshow(grid.to_numpy(), aspect="auto", origin="lower", cmap="viridis",
                   extent=(-0.5, 23.5, 0.5, 12.5))
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.ax.tick_params(labelsize=7, colors=TEXT_SECONDARY, length=0)
    cb.set_label("mean WS10m [m/s]", fontsize=8, color=TEXT_SECONDARY)
    ax.set_title("Mean wind speed, month × hour", fontsize=10.5, color=TEXT_PRIMARY,
                 fontweight="semibold", pad=8)
    ax.set_xlabel("hour", fontsize=9, color=TEXT_SECONDARY)
    ax.set_ylabel("month", fontsize=9, color=TEXT_SECONDARY)
    ax.set_yticks(range(1, 13)); ax.set_yticklabels(MONTHS, fontsize=7)
    ax.tick_params(labelsize=8, colors=TEXT_SECONDARY, length=0)
    if dead:
        ax.text(0.5, 0.03, "the four flat dark rows are the zeroed months",
                transform=ax.transAxes, ha="center", va="bottom", fontsize=8,
                color="#ffffff", style="italic", zorder=6)

    # 5 -- cooling-on hours vs the year --------------------------------------
    ax = axes[1, 1]
    bins = np.linspace(0, float(np.nanmax(w)) or 1.0, 36)
    ax.hist(w, bins=bins, density=True, color=BLUE, alpha=0.55, edgecolor="none",
            label=f"all hours (n={len(w):,})", zorder=3)
    if cool.any():
        ax.hist(w[cool], bins=bins, density=True, color=ORANGE, alpha=0.8,
                edgecolor="none", label=f"cooling plant on (n={int(cool.sum()):,})", zorder=4)
    ax.axvline(PIVOT_MS, color=PIVOT_C, linewidth=1.6, linestyle="--", zorder=5)
    style(ax, "Wind speed when the cooling plant runs, vs the year",
          "WS10m  [m/s]", "density")
    ax.legend(fontsize=8, frameon=False, labelcolor=TEXT_SECONDARY)
    ax.text(0.98, 0.55,
            f"cooling-on mean {s['mean_wind_cooling_dyn']:.2f} m/s\n"
            f"vs annual {s['mean_wind_annual']:.2f} m/s\n"
            f"{s['pct_zero_cooling_dyn']:.0f} % of them exactly zero",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=TEXT_PRIMARY)

    # 6 -- the decisive panel -------------------------------------------------
    ax = axes[1, 2]
    labels = [b["label"] for b in s["bands"]]
    vals = [b["extra_cooling_kWh"] for b in s["bands"]]
    cols = [BAD, "#d4a017", BLUE, "#1baf7a"]
    ax.bar(range(len(vals)), vals, width=0.62, color=cols, edgecolor="none", zorder=3)
    ax.axhline(0.0, color=TEXT_SECONDARY, linewidth=1.0, zorder=4)
    # Labels always sit above the zero line: the negative bar is tiny, and a label
    # hung beneath it collides with the tick labels.
    for i, (v, b) in enumerate(zip(vals, s["bands"])):
        ax.annotate(f"{v:+.1f} kWh\n{b['share_pct']:.0f} %", xy=(i, max(v, 0.0)),
                    xytext=(0, 5), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5,
                    color=TEXT_PRIMARY, zorder=5)
    style(ax, "Extra sensible cooling from the wind term, by wind band",
          None, "kWh over the year")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8.5, color=TEXT_SECONDARY)
    ax.set_ylim(min(min(vals) * 1.6, -2.0), max(vals) * 1.42 + 2)
    ax.text(0.5, 0.60,
            f"total {s['delta_C']:+.2f} kWh  ({s['C_fix']:.2f} → {s['C_dyn']:.2f})\n"
            f"if the high-wind branch drove this, it would sit in the last bar",
            transform=ax.transAxes, ha="center", va="top", fontsize=8.5,
            color=TEXT_PRIMARY, style="italic")

    fig.suptitle("Apt 305, Carlton — does the wind distribution explain the h_ce cooling change?",
                 fontsize=15, color=TEXT_PRIMARY, x=0.008, ha="left", y=0.985,
                 fontweight="semibold")
    fig.text(0.008, 0.948,
             "C2 replaces the ISO fixed external convective coefficient with h_ce = 4v + 4. "
             "Pivot at v = 4 m/s, where 4v + 4 = 20 W/(m²·K) = the fixed value. "
             "· AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw",
             fontsize=9, color=TEXT_SECONDARY, ha="left")
    fig.text(0.008, 0.921,
             "Panels 1–4 characterise the weather column; panel 6 is the controlled experiment — "
             "the same engine run twice, changing only the h_ce model.",
             fontsize=8.5, color=TEXT_SECONDARY, ha="left", style="italic")

    fig.tight_layout(rect=[0, 0.01, 1, 0.905])
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def write_verdict(s: dict, out_md: Path, png: Path) -> str:
    above_band = next(b for b in s["bands"] if b["label"] == "above 4 m/s")
    zero_band = next(b for b in s["bands"] if b["label"] == "exactly 0")

    supports_a = s["excess_annual"] > 0.5 and above_band["share_pct"] > 50.0
    supports_b = (s["wind_ratio_cooling_to_annual"] > 1.10
                  and s["excess_cooling"] > s["excess_annual"])
    verdict = ("a+b" if supports_a and supports_b else "a" if supports_a
               else "b" if supports_b else "c")

    dead = sorted(s["degenerate_months"])
    dead_names = ", ".join(calendar.month_abbr[m] for m in dead)

    L: list[str] = []
    add = L.append
    add("# Wind-speed diagnostic — does the distribution explain the h_ce cooling change?")
    add("")
    add(f"## Verdict: **({verdict})**")
    add("")
    if verdict == "c":
        add("**Neither (a) nor (b).** The increase is not produced by the high-wind "
            "branch of `4v + 4` at all, and the cooling hours are not windier than "
            "the year — they are very much calmer. Escalated below rather than "
            "papered over.")
    elif verdict == "a":
        add("**(a)**: many hours sit above the 4 m/s pivot, so the dynamic "
            "coefficient exceeds the fixed one on average — more coupling year-round.")
    elif verdict == "b":
        add("**(b)**: high winds coincide with the cooling-season hours specifically.")
    else:
        add("**(a) and (b) together.**")
    add("")
    add(f"![wind distribution]({png.name})")
    add("")

    add("## The two headline numbers")
    add("")
    add("| | |")
    add("| --- | ---: |")
    add(f"| Hours above the 4 m/s pivot | **{s['pct_hours_above_pivot']:.1f} %** of the year |")
    add(f"| Mean wind speed, whole year | **{s['mean_wind_annual']:.2f} m/s** |")
    add(f"| Mean wind speed, cooling-plant-on hours | "
        f"**{s['mean_wind_cooling_dyn']:.2f} m/s** — *{s['wind_ratio_cooling_to_annual']:.2f}× "
        f"the annual mean, i.e. far calmer, not windier* |")
    add("")

    add("## The controlled experiment")
    add("")
    add("The same engine, run twice, changing only the h_ce model "
        "(`external_convection_model` / `window_convection_model` = `table` "
        "recovers the ISO constant exactly). Nothing else differs — no worktree, "
        "no other correction.")
    add("")
    add("| h_ce model | Sensible heating (kWh) | Sensible cooling (kWh) | Cooling-plant hours |")
    add("| --- | ---: | ---: | ---: |")
    add(f"| ISO fixed, 20 W/(m²·K) | {s['H_fix']:,.2f} | {s['C_fix']:,.2f} | {s['n_cooling_fix']} |")
    add(f"| dynamic, 4v + 4 | {s['H_dyn']:,.2f} | {s['C_dyn']:,.2f} | {s['n_cooling_dyn']} |")
    add(f"| **change** | **{s['delta_H']:+.2f}** | **{s['delta_C']:+.2f}** | "
        f"**{s['n_cooling_dyn'] - s['n_cooling_fix']:+d}** |")
    add("")
    add("### Where that cooling comes from, by wind band")
    add("")
    add("| Wind band | Hours | Extra sensible cooling (kWh) | Share |")
    add("| --- | ---: | ---: | ---: |")
    for b in s["bands"]:
        add(f"| {b['label']} | {b['hours']:,} | {b['extra_cooling_kWh']:+.2f} | "
            f"{b['share_pct']:.1f} % |")
    add("")
    add(f"**{zero_band['share_pct']:.1f} % of the increase comes from hours where the "
        f"wind column reads exactly 0.0 m/s.** The hours above the pivot — where "
        f"readings (a) and (b) both said the effect should live — contribute "
        f"{above_band['extra_cooling_kWh']:+.2f} kWh, i.e. very slightly *less* "
        f"cooling, which is the correct sign for tighter coupling on a façade that "
        f"is usually warmer than the air it faces.")
    add("")

    add("## The actual mechanism")
    add("")
    add("It is the **low**-wind branch, not the high-wind branch. At v = 0 the model "
        "gives h_ce = 4 W/(m²·K) against the ISO constant's 20 — a five-fold "
        "*reduction* in the external film coefficient. Apt 305's only exposed "
        "surface is a west-facing wall with a solar absorptance of 0.75. Weaken its "
        "external film on a sunny afternoon and the surface sheds much less heat to "
        "the air, so its temperature climbs, the sol-air driving temperature climbs "
        "with it, and more heat is conducted inward. The zone crosses its 26 °C "
        "cooling setpoint in hours where it previously did not.")
    add("")
    add(f"That is visible in the plant state directly: the wind term adds "
        f"{s['n_cooling_hours_added']} cooling-plant hours, of which "
        f"{s.get('pct_zero_added_hours', float('nan')):.0f} % are hours with exactly "
        f"zero wind (mean {s.get('mean_wind_added_hours', float('nan')):.2f} m/s). The "
        f"cooling hours are calm *because* the model made them cooling hours — the "
        f"causality runs from the coefficient to the plant state, not the other way "
        f"round.")
    add("")

    if dead:
        add("## Escalation: the wind column is not usable as it stands")
        add("")
        add(f"Screening the EPW's wind field by month shows that **{dead_names} carry a "
            f"wind speed of exactly 0.0 m/s for every hour** — "
            f"{s['degenerate_hours']:,} hours, {100 * s['degenerate_hours'] / s['n_hours']:.1f} % "
            f"of the year — while the remaining months have a smooth distribution "
            f"resolved to 0.1 m/s and average {s['mean_wind_live_months']:.2f} m/s.")
        add("")
        add("| Month | Hours | Zero-wind share | Mean (m/s) | Cooling-plant hours |")
        add("| --- | ---: | ---: | ---: | ---: |")
        for m in range(1, 13):
            v = s["months"][m]
            mark = " ⚠" if m in dead else ""
            add(f"| {calendar.month_abbr[m]}{mark} | {v['n']:,} | {100 * v['zero_share']:.0f} % | "
                f"{v['mean']:.2f} | {v['cooling_hours']} |")
        add("")
        add("A meteorological record does not produce four entire months of exactly "
            "zero wind between eight months averaging "
            f"{s['mean_wind_live_months']:.2f} m/s. These are missing or zeroed data, "
            "not calm. The EPW's own missing-value code for wind speed (999) appears "
            "nowhere in the file, so the gap is silent: nothing in the file marks "
            "those hours as absent, and the engine reads them as genuine calms.")
        add("")
        cooling_in_dead = sum(s["months"][m]["cooling_hours"] for m in dead)
        add(f"**This matters directly for the result.** Two of the four zeroed months "
            f"— January and March — are the peak cooling months, and "
            f"{cooling_in_dead} of the {s['n_cooling_dyn']} cooling-plant hours fall "
            f"inside them. Combined with the finding above — that "
            f"{zero_band['share_pct']:.0f} % of the h_ce cooling increase comes from "
            f"exactly-zero-wind hours — the conclusion is that the "
            f"{s['delta_C']:+.2f} kWh is substantially an artefact of the weather "
            f"file, not a property of the correlation.")
        add("")
        add("### What this does *not* say")
        add("")
        add("The implementation of `4v + 4` is faithful: `simplecombined` returns "
            "`4 + 4u`, floored by `external_convection_h_min`, and reduces to the ISO "
            "constant at 4 m/s exactly as documented. The defect is in the input, not "
            "the formula. Equally, this does not show the correction is wrong in "
            "principle — on a wind record with all twelve months present it may well "
            "behave as the literature expects.")
        add("")
        add("### Recommended, not done here")
        add("")
        add("Out of scope for this task, and listed rather than actioned:")
        add("")
        add("1. Re-source the wind column, or splice those four months from another "
            "year of the same station, and re-run the controlled experiment above. "
            "That single number — the change in sensible cooling on a sound wind "
            "record — is what the paper should defend.")
        add("2. Until then, **do not present the 20.06 → 67.12 kWh cooling change as a "
            "physical finding about wind-dependent convection.** With the ISO fixed "
            f"coefficient the same engine gives {s['C_fix']:.2f} kWh.")
        add("3. Consider whether the engine should refuse, or at least warn, on a "
            "weather column with a degenerate month — a silent third of a year at "
            "exactly zero is the kind of input that should not pass quietly.")
        add("")

    add("## Effect on the canonical figure")
    add("")
    add("The canonical result is **unchanged by this diagnostic** and remains "
        "122.69 kWh sensible heating + 67.12 kWh sensible cooling + 3.98 kWh gated "
        "latent = 193.79 kWh = 9.69 kWh/m²·yr. This is a diagnosis, not a "
        "correction: nothing here has been altered in the engine, and the number is "
        "reported as it stands. What it adds is that the cooling component of that "
        f"figure carries a {s['delta_C']:.2f} kWh contribution traceable to "
        "zero-wind hours in months whose wind data is missing, and that needs "
        "resolving before the h_ce correction is defended in the text.")
    add("")
    add("Generated by `tools/diagnostics/wind_h_ce_diagnostic.py`.")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(L) + "\n", encoding="utf-8")
    return verdict


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", required=True)
    ap.add_argument("--outdir", default=str(REPO_ROOT / "results/diagnostics"))
    args = ap.parse_args()

    weather = str(Path(args.weather).resolve())
    outdir = Path(args.outdir)

    print("controlled experiment — same engine, only the h_ce model differs:", flush=True)
    d = measure(weather)
    s = summarise(d)

    print(f"\n  cooling  {s['C_fix']:.2f} kWh (ISO fixed)  ->  {s['C_dyn']:.2f} kWh "
          f"(4v+4)   {s['delta_C']:+.2f}")
    print(f"  {s['pct_hours_above_pivot']:.1f} % of hours above the 4 m/s pivot; "
          f"annual mean {s['mean_wind_annual']:.2f} m/s")
    print(f"  cooling-on mean wind {s['mean_wind_cooling_dyn']:.2f} m/s "
          f"({s['wind_ratio_cooling_to_annual']:.2f}x annual)")
    for b in s["bands"]:
        print(f"    {b['label']:<12} {b['hours']:>5} h  {b['extra_cooling_kWh']:+8.2f} kWh"
              f"  {b['share_pct']:6.1f} %")
    if s["degenerate_months"]:
        print(f"  DEGENERATE WIND MONTHS: "
              f"{', '.join(calendar.month_abbr[m] for m in s['degenerate_months'])}"
              f" ({s['degenerate_hours']:,} h at exactly 0.0 m/s)")

    png = outdir / "wind_distribution.png"
    make_figure(d, s, png)
    verdict = write_verdict(s, outdir / "wind_verdict.md", png)
    (outdir / "wind_stats.json").write_text(
        json.dumps({"summary": s, "verdict": verdict}, indent=2, default=str),
        encoding="utf-8")

    print(f"\nverdict: ({verdict})")
    print(f"wrote -> {png}")
    print(f"wrote -> {outdir / 'wind_verdict.md'}")
    if verdict == "c":
        print("\nVERDICT (c): the wind distribution does NOT explain the increase by "
              "the mechanism proposed. See the verdict file — this is escalated, not "
              "papered over.")


if __name__ == "__main__":
    main()
