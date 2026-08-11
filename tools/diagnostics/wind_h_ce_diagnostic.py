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

WHY THIS IS BEING RE-RUN
------------------------
The first pass, on AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw, returned (c):
96 % of the C2 cooling increase came from hours whose wind read exactly 0.0 m/s,
and four whole months of that column -- Jan, Mar, Jul, Sep, 33.7 % of the year --
were identically zero because the Melbourne Regional Office station's record ends
in 2014. That is missing data, not calm, and at v = 0 the model gives
h_ce = 4 W/(m2 K) against the ISO constant's 20: a five-fold *weakening* of the
external film, which raised the sol-air temperature of the exposed west wall and
manufactured cooling hours.

Verdict (c) was therefore a finding about the weather file, not about the
correlation, and it was left open. This re-run is on Essendon Fields (WMO 958660,
~8 km NW of the Carlton site, complete continuous record, no dead-calm month),
which is what lets the question finally be answered on the physics.

WHICH WIND (change 2b)
----------------------
The correlation is driven by the wind LOCAL TO THE WALL, not by the EPW column:
the engine lifts the 10 m open-terrain station reading to the site's own terrain
and height by the ASHRAE profile. Every statistic here that is about the
correlation -- the pivot, the bands, the mean h_ce -- is therefore taken on the
local series, and the station column is carried alongside for the contrast.

``--no-wind-profile`` forces the correlation back onto the raw station column.
That is the *before* state for the terrain question and has to be produced on
this engine tree: an older wind_stats.json predates the closure fixes and would
attribute those to the terrain correction. Run the two back to back:

    ... --tag station --no-wind-profile
    ... --tag terrain --compare-to <outdir>/wind_stats_station.json

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
        --weather weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw \\
        --outdir results/diagnostics --tag essendon
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


def _pct(v: float, nd: int = 1) -> str:
    """Format a share, snapping a rounding-negative zero to plain zero.

    Band shares are taken against the *signed* total, so when the total change is
    negative a band contributing +0.0001 kWh formats as "-0.0 %", which reads as
    a real negative rather than as nothing.
    """
    if v != v:
        return "n/a"
    if abs(v) < 0.5 * 10 ** (-nd):
        v = 0.0
    return f"{v:.{nd}f} %"


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def measure(weather: str, wind_profile: bool = True) -> dict:
    """
    One weather read, two annual runs differing only in the h_ce model.

    ``wind_profile=False`` forces the h_ce correlation back onto the raw 10 m
    station column. That is the *before* state for the terrain question, and it
    has to be produced by this same engine tree rather than read from an older
    result file: the earlier wind_stats predate the closure fixes, so comparing
    against them would attribute the closure changes to the terrain correction.
    """
    import numpy as np
    import pandas as pd

    from apt305_building import build_bui
    from pybuildingenergy.source.check_input import sanitize_and_validate_BUI
    from pybuildingenergy.source.utils import ISO52016

    def run(**kw):
        b, _ = sanitize_and_validate_BUI(build_bui(), fix=True)
        hourly, annual, _ = ISO52016.Temperature_and_Energy_needs_calculation(
            b, weather_source="epw", path_weather_file=weather,
            return_sankey_data=True, wind_profile=wind_profile, **kw)
        return hourly, annual

    b0, _ = sanitize_and_validate_BUI(build_bui(), fix=True)
    sim_df = ISO52016.Weather_data_bui(b0, weather, weather_source="epw").simulation_df

    print("  run 1/2: dynamic h_ce = 4v + 4 (default)", flush=True)
    h_dyn, a_dyn = run()
    print("  run 2/2: ISO fixed h_ce = 20 W/(m2 K)", flush=True)
    h_fix, a_fix = run(external_convection_model="table",
                       window_convection_model="table")

    n = len(h_dyn)
    wind_station = pd.to_numeric(sim_df["WS10m"], errors="coerce").to_numpy(float)[-n:]

    # The wind the h_ce correlation is actually driven by. The EPW column is a
    # 10 m open-terrain station reading; the engine lifts it to the building
    # surface's own terrain and height (change 2b). Every statistic below that
    # is about the correlation -- the pivot, the bands, the mean h_ce -- must
    # be taken on THIS series, not on the station column, or it describes a
    # wind the model never saw.
    from pybuildingenergy.source.utils import resolve_local_wind_factor
    wind_factor, wind_audit = resolve_local_wind_factor(
        build_bui(), wind_profile=wind_profile)
    wind = wind_station * wind_factor

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
        "wind_station": wind_station,
        "wind_factor": float(wind_factor),
        "wind_audit": wind_audit,
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

    # The station column, kept alongside so the terrain correction can be read
    # off directly rather than inferred. Every other wind statistic in this
    # dict is on the LOCAL series.
    ws = d["wind_station"]
    s["wind_factor"] = d["wind_factor"]
    s["wind_audit"] = d["wind_audit"]
    s["station_mean_wind_annual"] = float(np.nanmean(ws))
    s["station_median_wind_annual"] = float(np.nanmedian(ws))
    s["station_max_wind_annual"] = float(np.nanmax(ws))
    s["station_pct_hours_above_pivot"] = float(100.0 * np.mean(ws > PIVOT_MS))
    s["station_mean_h_ce_annual"] = float(np.nanmean(4.0 * ws + 4.0))
    s["station_excess_annual"] = s["station_mean_h_ce_annual"] - H_CE_FIXED
    s["station_pct_hours_exactly_zero"] = float(100.0 * np.mean(ws == 0.0))
    s["station_mean_wind_cooling_dyn"] = (
        float(np.nanmean(ws[cool_d])) if cool_d.any() else float("nan"))

    # How much of the delta comes from *genuine* wind, i.e. everything except the
    # exactly-zero bucket. On the RO file this was 4 %; it is the number the
    # earlier open finding turns on, so it is computed rather than inferred from
    # the table.
    zero_kwh = next(b["extra_cooling_kWh"] for b in s["bands"] if b["label"] == "exactly 0")
    s["extra_cooling_zero_wind_kWh"] = zero_kwh
    s["extra_cooling_nonzero_wind_kWh"] = total_extra - zero_kwh
    s["pct_extra_from_nonzero_wind"] = (
        100.0 * (total_extra - zero_kwh) / total_extra if total_extra else float("nan"))

    # Do the cooling hours actually sit above the pivot? The direct form of the
    # question, rather than inferring it from a mean.
    s["pct_cooling_hours_above_pivot"] = (
        float(100.0 * np.mean(w[cool_d] > PIVOT_MS)) if cool_d.any() else float("nan"))
    s["mean_h_ce_cooling"] = (
        float(np.nanmean(4.0 * w[cool_d] + 4.0)) if cool_d.any() else float("nan"))
    return s


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------

def make_figure(d: dict, s: dict, out_png: Path, weather_name: str = "") -> None:
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

    # 1 -- station vs terrain-corrected, the panel the correction turns on ---
    #
    # Both distributions on one axis with the pivot marked on both, because the
    # whole sign question is which side of that line each series sits on. The
    # station series is what the engine used to be driven by; the local series
    # is what it is driven by now.
    ax = axes[0, 0]
    ws = d["wind_station"]
    bins1 = np.linspace(0.0, float(np.nanmax(ws)) or 1.0, 46)
    ax.hist(ws, bins=bins1, color=TEXT_SECONDARY, alpha=0.38, edgecolor="none",
            zorder=3, label=f"station, 10 m open terrain (mean "
                            f"{s['station_mean_wind_annual']:.2f} m/s)")
    ax.hist(w, bins=bins1, color=BLUE, alpha=0.80, edgecolor="none", zorder=4,
            label=f"local, terrain + height (mean {s['mean_wind_annual']:.2f} m/s)")
    ax.axvline(PIVOT_MS, color=PIVOT_C, linewidth=1.8, linestyle="--", zorder=6)
    ax.axvline(s["station_mean_wind_annual"], color=TEXT_SECONDARY, linewidth=1.2,
               linestyle=":", zorder=5)
    ax.axvline(s["mean_wind_annual"], color=BLUE, linewidth=1.2, linestyle=":", zorder=5)
    style(ax, "Station wind vs the wind the correlation actually sees",
          "wind speed  [m/s]", "hours")
    ax.legend(fontsize=7.2, frameon=False, labelcolor=TEXT_SECONDARY, loc="upper right")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.30)
    ax.text(PIVOT_MS + 0.15, ax.get_ylim()[1] * 0.62,
            "pivot 4 m/s\n(4u+4 = 20 = ISO fixed)", color=PIVOT_C, fontsize=8,
            va="top", ha="left", style="italic")
    ax.text(0.98, 0.50,
            f"above the pivot:\n"
            f"  station  {s['station_pct_hours_above_pivot']:.1f} %\n"
            f"  local    {s['pct_hours_above_pivot']:.1f} %\n"
            f"factor {s['wind_factor']:.3f} "
            f"({s['wind_audit'].get('terrain_class', '?')}, "
            f"z = {s['wind_audit'].get('surface_height_m', float('nan')):.2f} m)",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.2,
            color=TEXT_PRIMARY)

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
    else:
        # Stated, not left to be inferred from the absence of red bars: this panel
        # is the direct check that the RO file's defect has not recurred.
        worst_m = max(range(1, 13), key=lambda m: s["months"][m]["zero_share"])
        ax.text(0.5, 0.97,
                f"no zeroed month — worst exact-zero share is "
                f"{calendar.month_abbr[worst_m]}, "
                f"{100 * s['months'][worst_m]['zero_share']:.1f} %",
                transform=ax.transAxes, ha="center", va="top", fontsize=8.5,
                color="#1baf7a", fontweight="semibold")

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
        ax.text(0.5, 0.03, f"the {len(dead)} flat dark rows are the zeroed months",
                transform=ax.transAxes, ha="center", va="bottom", fontsize=8,
                color="#ffffff", style="italic", zorder=6)
    else:
        ax.text(0.5, 0.03, "no flat dark row — every month carries a diurnal cycle",
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
            f"{s['pct_cooling_hours_above_pivot']:.0f} % of them above the pivot\n"
            f"{s['pct_zero_cooling_dyn']:.1f} % of them exactly zero",
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
        ax.annotate(f"{v:+.1f} kWh\n{_pct(b['share_pct'], 0)}", xy=(i, max(v, 0.0)),
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
            f"{s['pct_extra_from_nonzero_wind']:.0f} % of it from genuine "
            f"(non-zero) wind bands",
            transform=ax.transAxes, ha="center", va="top", fontsize=8.5,
            color=TEXT_PRIMARY, style="italic")

    fig.suptitle("Apt 305, Carlton — does the wind distribution explain the h_ce cooling change?",
                 fontsize=15, color=TEXT_PRIMARY, x=0.008, ha="left", y=0.985,
                 fontweight="semibold")
    fig.text(0.008, 0.948,
             "C2 replaces the ISO fixed external convective coefficient with h_ce = 4v + 4. "
             "Pivot at v = 4 m/s, where 4v + 4 = 20 W/(m²·K) = the fixed value. "
             + (f"· {weather_name}" if weather_name else ""),
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

def load_prior_stats(path: Path) -> dict | None:
    """The RO-file run's summary, for the before/after contrast.

    Read from the file the earlier verdict was written from, not retyped, so the
    contrast cannot drift from what was actually published.
    """
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_verdict(s: dict, out_md: Path, png: Path, weather_name: str = "",
                  prior: dict | None = None) -> str:
    above_band = next(b for b in s["bands"] if b["label"] == "above 4 m/s")
    zero_band = next(b for b in s["bands"] if b["label"] == "exactly 0")

    supports_a = s["excess_annual"] > 0.5 and above_band["share_pct"] > 50.0
    supports_b = (s["wind_ratio_cooling_to_annual"] > 1.10
                  and s["excess_cooling"] > s["excess_annual"])
    verdict = ("a+b" if supports_a and supports_b else "a" if supports_a
               else "b" if supports_b else "c")

    dead = sorted(s["degenerate_months"])
    dead_names = ", ".join(calendar.month_abbr[m] for m in dead)
    # Direction, stated rather than assumed: on a genuinely windy record the
    # dynamic coefficient sits *above* the ISO constant, which couples the façade
    # more tightly to outdoor air and can move cooling either way depending on
    # whether the surface is warmer or cooler than the air it faces.
    dirn = "increase" if s["delta_C"] > 0 else "reduction"
    dirn_verb = "raises" if s["delta_C"] > 0 else "lowers"

    L: list[str] = []
    add = L.append
    add("# Wind-speed diagnostic on the clean weather file — does the distribution "
        "explain the h_ce cooling change?")
    add("")
    wf_hdr = s.get("wind_factor", 1.0)
    if weather_name:
        add(f"Weather: `{weather_name}`. The h_ce correlation is driven by "
            + (f"the **wind local to the wall** — the station column × "
               f"{wf_hdr:.4f} for terrain and height."
               if abs(wf_hdr - 1.0) > 1e-9 else
               "the **raw 10 m station column**, unadjusted for terrain or "
               "height. This is the *before* state for the wind-profile "
               "question, produced on the current engine tree so that the "
               "contrast isolates the wind and nothing else.")
            )
        add("")
    add(f"## Verdict: **({verdict})**")
    add("")
    if verdict == "c":
        add("**Neither (a) nor (b).** The change is not produced by the high-wind "
            "branch of `4v + 4`, and the cooling hours are not windier than the "
            "year. Escalated below rather than papered over.")
    elif verdict == "a":
        add("**(a): many hours sit above the 4 m/s pivot, so the dynamic coefficient "
            "exceeds the fixed one on average — more coupling year-round.** The "
            f"C2 cooling change **is** now explained by the real wind distribution: "
            f"{s['pct_extra_from_nonzero_wind']:.1f} % of it comes from genuine, "
            f"non-zero wind bands, against 4 % on the file this replaces.")
    elif verdict == "b":
        add("**(b): high winds coincide with the cooling-season hours specifically**, "
            "so the cooling-season coupling is amplified beyond the year-round "
            "effect.")
    else:
        add("**(a) and (b) together**: the year is windier than the pivot *and* the "
            "cooling hours are windier still.")
    add("")
    add(f"![wind distribution]({png.name})")
    add("")

    # --- Item 2: the sign, stated before anything else -----------------------
    wf = s.get("wind_factor", 1.0)
    aud = s.get("wind_audit", {}) or {}
    add("## The sign of C2, on the terrain-corrected wind")
    add("")
    add(f"The h_ce correlation is now driven by the wind **local to the wall** — "
        f"terrain `{aud.get('terrain_class', '?')}` "
        f"(a = {aud.get('exponent_a', '?')}, "
        f"δ = {aud.get('boundary_layer_delta_m', 0) or 0:.0f} m) at "
        f"z = {aud.get('surface_height_m', float('nan')):.2f} m, a factor of "
        f"**{wf:.4f}** on the 10 m station column.")
    add("")
    add("| | Station wind (as previously run) | Terrain-corrected (this run) |")
    add("| --- | ---: | ---: |")
    add(f"| Annual mean wind | {s['station_mean_wind_annual']:.2f} m/s | "
        f"**{s['mean_wind_annual']:.2f} m/s** |")
    add(f"| Hours above the 4 m/s pivot | "
        f"{s['station_pct_hours_above_pivot']:.1f} % | "
        f"**{s['pct_hours_above_pivot']:.1f} %** |")
    add(f"| Mean h_ce implied | {s['station_mean_h_ce_annual']:.2f} W/(m²·K) "
        f"({s['station_excess_annual']:+.2f} vs the ISO {H_CE_FIXED:.0f}) | "
        f"**{s['mean_h_ce_annual']:.2f} W/(m²·K)** "
        f"({s['excess_annual']:+.2f}) |")
    add("")
    if prior and "summary" in prior:
        q = prior["summary"]
        add(f"**C2 on sensible cooling: {q['delta_C']:+.2f} kWh before, "
            f"{s['delta_C']:+.2f} kWh now.**")
        add("")
        reversed_sign = (q["delta_C"] < 0) != (s["delta_C"] < 0)
        if reversed_sign:
            add(f"**The sign reverses.** On the station wind C2 "
                f"{'reduced' if q['delta_C'] < 0 else 'increased'} sensible "
                f"cooling by {abs(q['delta_C']):.2f} kWh; on the terrain-corrected "
                f"wind it {'reduces' if s['delta_C'] < 0 else 'increases'} it by "
                f"{abs(s['delta_C']):.2f} kWh. The reported C2 result did rest on "
                f"an unstated terrain assumption, and correcting that assumption "
                f"flips the direction of the correction. This is the finding the "
                f"task exists to establish, and it is stated as it fell.")
        else:
            add(f"**The sign does not reverse.** C2 "
                f"{'reduces' if s['delta_C'] < 0 else 'increases'} sensible "
                f"cooling both before and after the terrain correction. The "
                f"margin by which it did not reverse: the local mean wind is "
                f"{s['mean_wind_annual']:.2f} m/s against the "
                f"{PIVOT_MS:.0f} m/s pivot, "
                f"{s['pct_hours_above_pivot']:.1f} % of hours sit above it, and "
                f"the magnitude moves from {q['delta_C']:+.2f} to "
                f"{s['delta_C']:+.2f} kWh.")
        add("")
    else:
        add(f"**C2 on sensible cooling: {s['delta_C']:+.2f} kWh** — it "
            f"{'reduces' if s['delta_C'] < 0 else 'increases'} it. No prior "
            f"summary was supplied via `--compare-to`, so the before/after "
            f"contrast is omitted rather than retyped from memory.")
        add("")

    # --- the three questions the task asks, answered in order ----------------
    add("## The three questions, answered")
    add("")
    add("| Question | Answer |")
    add("| --- | --- |")
    add(f"| Is the C2 cooling change explained by the real wind distribution? | "
        f"**{'Yes' if verdict != 'c' else 'No'}** — "
        f"{s['pct_extra_from_nonzero_wind']:.1f} % of the "
        f"{s['delta_C']:+.2f} kWh comes from hours with genuine, non-zero wind |")
    add(f"| Do cooling-plant-on hours coincide with above-pivot wind? | "
        f"**{s['pct_cooling_hours_above_pivot']:.1f} %** of the "
        f"{s['n_cooling_dyn']} cooling hours are above 4 m/s, against "
        f"{s['pct_hours_above_pivot']:.1f} % of the year — "
        + ("they are windier than the year"
           if s["wind_ratio_cooling_to_annual"] > 1.02 else
           "about as windy as the year"
           if s["wind_ratio_cooling_to_annual"] > 0.98 else
           "they are calmer than the year") + " |")
    add(f"| How much of the delta comes from genuine (non-zero) wind bands? | "
        f"**{s['extra_cooling_nonzero_wind_kWh']:+.2f} kWh of "
        f"{s['total_extra_cooling_kWh']:+.2f} kWh "
        f"({s['pct_extra_from_nonzero_wind']:.1f} %)**; the exactly-zero bucket "
        f"contributes {zero_band['extra_cooling_kWh']:+.2f} kWh over "
        f"{zero_band['hours']:,} hours |")
    add("")

    add("## The wind column itself")
    add("")
    add("| | |")
    add("| --- | ---: |")
    add(f"| Hours above the 4 m/s pivot | **{s['pct_hours_above_pivot']:.1f} %** of the year |")
    add(f"| Mean wind speed, whole year | **{s['mean_wind_annual']:.2f} m/s** |")
    add(f"| Median / max | {s['median_wind_annual']:.2f} / {s['max_wind_annual']:.1f} m/s |")
    add(f"| Hours reading exactly 0.0 m/s | {s['pct_hours_exactly_zero']:.2f} % |")
    add(f"| Months with a degenerate (all-zero) column | "
        + (f"**{dead_names}**" if dead else "**none**") + " |")
    add(f"| Mean h_ce implied over the year | {s['mean_h_ce_annual']:.2f} W/(m²·K), "
        f"i.e. {s['excess_annual']:+.2f} against the ISO fixed {H_CE_FIXED:.0f} |")
    add(f"| Mean wind, cooling-plant-on hours | "
        f"**{s['mean_wind_cooling_dyn']:.2f} m/s** — "
        f"{s['wind_ratio_cooling_to_annual']:.2f}× the annual mean |")
    add(f"| Mean h_ce over cooling-plant-on hours | {s['mean_h_ce_cooling']:.2f} W/(m²·K), "
        f"i.e. {s['excess_cooling']:+.2f} against the fixed value |")
    add("")
    if not dead:
        worst_m = max(range(1, 13), key=lambda m: s["months"][m]["zero_share"])
        add(f"**No calendar month is dead-calm.** The worst exact-zero share is "
            f"{calendar.month_abbr[worst_m]} at "
            f"{100 * s['months'][worst_m]['zero_share']:.1f} %, and every month "
            f"carries a diurnal cycle (panel 4). This is the specific defect that "
            f"invalidated the previous run, so it is checked directly rather than "
            f"assumed — and the harness now aborts on it "
            f"(`tools/diagnostics/weather_integrity.py`).")
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
    add("### Where that cooling change comes from, by wind band")
    add("")
    add("| Wind band | Hours | Extra sensible cooling (kWh) | Share |")
    add("| --- | ---: | ---: | ---: |")
    for b in s["bands"]:
        add(f"| {b['label']} | {b['hours']:,} | {b['extra_cooling_kWh']:+.2f} | "
            f"{_pct(b['share_pct'])} |")
    add("")
    add("Share is of the **signed** total, so a band moving the same way as the "
        "total reads positive and a band opposing it reads negative; the four "
        "shares sum to 100 %. That is why a share can exceed 100 % when another "
        "band pulls the other way.")
    add("")
    add(f"**{s['pct_extra_from_nonzero_wind']:.1f} % of the {s['delta_C']:+.2f} kWh "
        f"comes from hours with real, non-zero wind**, and the above-pivot band "
        f"alone carries {above_band['extra_cooling_kWh']:+.2f} kWh "
        f"({above_band['share_pct']:.1f} %) over {above_band['hours']:,} hours. "
        f"The exactly-zero bucket is "
        f"now {zero_band['hours']:,} hours and "
        f"{zero_band['extra_cooling_kWh']:+.2f} kWh, "
        f"{_pct(abs(zero_band['share_pct']))} of the total.")
    add("")

    add("## The mechanism")
    add("")
    if s["excess_annual"] > 0:
        add(f"With {s['pct_hours_above_pivot']:.1f} % of hours above the pivot the "
            f"dynamic coefficient sits **above** the ISO constant on the year "
            f"(mean {s['mean_h_ce_annual']:.2f} against {H_CE_FIXED:.0f} W/(m²·K)), "
            f"so the exposed west wall is coupled *more* tightly to outdoor air "
            f"than ISO 13789's frozen value assumes.")
    else:
        add(f"With only {s['pct_hours_above_pivot']:.1f} % of hours above the "
            f"pivot the dynamic coefficient sits **below** the ISO constant on the "
            f"year (mean {s['mean_h_ce_annual']:.2f} against "
            f"{H_CE_FIXED:.0f} W/(m²·K)), so the exposed west wall is coupled "
            f"*less* tightly to outdoor air than ISO 13789's frozen value assumes. "
            f"ISO 13789 §9.5 freezes 4 m/s, which is a met-station speed; a wall "
            f"in suburban terrain three storeys up does not see it.")
    add("")
    if s["delta_C"] < 0:
        add(f"Apt 305's only exposed surface is that west wall, solar absorptance "
            f"0.75. On a sunny afternoon it runs hotter than the air it faces, so "
            f"a **stronger** external film sheds more of the absorbed solar back "
            f"to the air, the sol-air driving temperature falls, and less heat is "
            f"conducted inward. That is why the wind term {dirn_verb} sensible "
            f"cooling by {abs(s['delta_C']):.2f} kWh here.")
    else:
        add(f"Apt 305's only exposed surface is that west wall, solar absorptance "
            f"0.75. On a sunny afternoon it runs hotter than the air it faces, and "
            f"a **weaker** external film sheds less of the absorbed solar back to "
            f"the air: the sol-air driving temperature rises and more heat is "
            f"conducted inward. With the local mean at "
            f"{s['mean_wind_annual']:.2f} m/s the coefficient sits *below* the ISO "
            f"constant for {100 - s['pct_hours_above_pivot']:.1f} % of the year, "
            f"which is why the wind term {dirn_verb} sensible cooling by "
            f"{abs(s['delta_C']):.2f} kWh here — the opposite of what the same "
            f"correlation does on the unadjusted station column.")
    add("")
    add(f"The plant state moves with it: the wind term changes the cooling-plant "
        f"hour count by {s['n_cooling_dyn'] - s['n_cooling_fix']:+d} "
        f"({s['n_cooling_fix']} → {s['n_cooling_dyn']}).")
    if s.get("n_cooling_hours_added"):
        add("")
        add(f"Of the hours the dynamic model adds to the cooling plant "
            f"({s['n_cooling_hours_added']}), the mean wind is "
            f"{s.get('mean_wind_added_hours', float('nan')):.2f} m/s and "
            f"{s.get('pct_zero_added_hours', float('nan')):.1f} % read exactly "
            f"zero.")
    add("")

    add("## Month by month")
    add("")
    add("| Month | Hours | Zero-wind share | Mean (m/s) | Cooling-plant hours |")
    add("| --- | ---: | ---: | ---: | ---: |")
    for m in range(1, 13):
        v = s["months"][m]
        mark = " ⚠" if m in dead else ""
        add(f"| {calendar.month_abbr[m]}{mark} | {v['n']:,} | {100 * v['zero_share']:.1f} % | "
            f"{v['mean']:.2f} | {v['cooling_hours']} |")
    add("")

    # --- before/after against the superseded run -----------------------------
    if prior and "summary" in prior:
        q = prior["summary"]
        prior_name = Path(str(prior.get("weather", "prior run"))).name
        same_file = prior_name == weather_name
        add("## Before and after")
        add("")
        if same_file:
            add("Same engine, same building, same weather file, same switch. The "
                "only difference is that the h_ce correlation is now fed the wind "
                "local to the wall rather than the raw 10 m station column.")
        else:
            add("Same engine, same building, same switch. The only difference is "
                "the wind column.")
        add("")
        col_before = ("station wind (before)" if same_file
                      else f"{prior_name} (superseded)")
        col_after = ("terrain-corrected (this run)" if same_file
                     else f"{weather_name} (this run)")
        add(f"| | {col_before} | {col_after} |")
        add("| --- | ---: | ---: |")
        add(f"| Annual mean wind | {q['mean_wind_annual']:.2f} m/s | "
            f"{s['mean_wind_annual']:.2f} m/s |")
        add(f"| Hours above the 4 m/s pivot | {q['pct_hours_above_pivot']:.1f} % | "
            f"{s['pct_hours_above_pivot']:.1f} % |")
        add(f"| Hours exactly 0.0 m/s | {q['pct_hours_exactly_zero']:.2f} % | "
            f"{s['pct_hours_exactly_zero']:.2f} % |")
        add("| Dead-calm months | "
            + (", ".join(calendar.month_abbr[int(m)] for m in q["degenerate_months"])
               or "none")
            + " | " + (dead_names or "none") + " |")
        add(f"| Sensible cooling, ISO fixed h_ce | {q['C_fix']:,.2f} kWh | "
            f"{s['C_fix']:,.2f} kWh |")
        add(f"| Sensible cooling, dynamic 4v + 4 | {q['C_dyn']:,.2f} kWh | "
            f"{s['C_dyn']:,.2f} kWh |")
        add(f"| C2 effect on sensible cooling | {q['delta_C']:+,.2f} kWh | "
            f"{s['delta_C']:+,.2f} kWh |")
        prior_zero = next((b for b in q["bands"] if b["label"] == "exactly 0"), None)
        if prior_zero:
            add(f"| Share of that from exactly-zero wind | "
                f"{_pct(prior_zero['share_pct'])} | "
                f"{_pct(zero_band['share_pct'])} |")
        add(f"| Verdict | ({prior.get('verdict', '?')}) | ({verdict}) |")
        add("")
        if same_file:
            add("Nothing in the correlation moved. `simplecombined` still returns "
                "`4 + 4u` and still reduces to the ISO constant at 4 m/s exactly. "
                "What moved is the wind fed to it, and with it which side of the "
                "pivot most of the year sits on.")
        else:
            add("The earlier open finding is therefore closed. It was correct as a "
                "diagnosis — the RO cooling increase genuinely was not explained "
                "by real wind — and the fix was the input, not the formula: "
                "`simplecombined` returns `4 + 4u` and reduces to the ISO constant "
                "at 4 m/s exactly as documented, on both files.")
        add("")

    if dead:
        add("## Escalation: the wind column is still not usable")
        add("")
        add(f"**{dead_names} carry a wind speed of exactly 0.0 m/s for every hour** — "
            f"{s['degenerate_hours']:,} hours, "
            f"{100 * s['degenerate_hours'] / s['n_hours']:.1f} % of the year. This is "
            f"the same defect as the file this run was meant to replace. No cooling "
            f"figure from this run is defensible.")
        add("")

    add("## Effect on the canonical figure")
    add("")
    add("This is a diagnostic, not a correction: nothing in the engine was altered "
        "to produce it. What it establishes is that the C2 component of the "
        "canonical trajectory now rests on a wind record that is a wind record — "
        f"{s['pct_extra_from_nonzero_wind']:.1f} % of the C2 cooling effect comes "
        f"from genuine wind bands, and the "
        f"{100 - s['pct_extra_from_nonzero_wind']:.1f} % attributable to "
        f"exactly-zero hours spans {zero_band['hours']:,} hours "
        f"({100.0 * zero_band['hours'] / s['n_hours']:.1f} % of the year) rather "
        f"than four fabricated months.")
    add("")
    add("The canonical numbers themselves are in "
        "`results/au_canonical_essendon/comparison.md`; this file does not restate "
        "them, so the two cannot drift apart.")
    add("")
    add("Generated by `tools/diagnostics/wind_h_ce_diagnostic.py`.")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(L) + "\n", encoding="utf-8")
    return verdict


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", required=True)
    ap.add_argument("--outdir", default=str(REPO_ROOT / "results/diagnostics"))
    ap.add_argument("--tag", default="",
                    help="suffix for the output filenames, e.g. 'essendon' gives "
                         "wind_distribution_essendon.png / wind_verdict_essendon.md")
    ap.add_argument("--expect-weather", default=None,
                    help="substring the weather filename must contain — the guard "
                         "against silently re-running on a cached file")
    ap.add_argument("--allow-degenerate", action="store_true",
                    help="do not abort on a dead-calm month. Only for studying a "
                         "known-bad file; never for producing a result.")
    ap.add_argument("--compare-to", default=None,
                    help="a wind_stats.json from an earlier run, for the "
                         "before/after contrast")
    ap.add_argument("--no-wind-profile", action="store_true",
                    help="force the h_ce correlation back onto the raw 10 m "
                         "station column. This produces the 'before' state for "
                         "the terrain question on THIS engine tree, which is the "
                         "only honest comparison — an older wind_stats.json also "
                         "carries every other change made since.")
    args = ap.parse_args()

    weather = str(Path(args.weather).resolve())
    outdir = Path(args.outdir)
    tag = f"_{args.tag}" if args.tag else ""

    # Preflight before the engine runs at all: the resolved absolute path, the
    # wind column's own numbers, and a hard stop on a dead-calm month.
    from weather_integrity import assert_usable, format_report, wind_integrity
    if args.allow_degenerate:
        w = wind_integrity(Path(weather))
        print("weather preflight — EPW wind-column integrity  [--allow-degenerate]")
        print(format_report(w), flush=True)
    else:
        assert_usable(Path(weather), expect_name_contains=args.expect_weather)

    print("controlled experiment — same engine, only the h_ce model differs:", flush=True)
    d = measure(weather, wind_profile=not args.no_wind_profile)
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

    print(f"  {s['pct_extra_from_nonzero_wind']:.1f} % of the change comes from "
          f"genuine (non-zero) wind bands")
    print(f"  {s['pct_cooling_hours_above_pivot']:.1f} % of the {s['n_cooling_dyn']} "
          f"cooling-plant hours are above the pivot "
          f"(year: {s['pct_hours_above_pivot']:.1f} %)")

    prior = load_prior_stats(Path(args.compare_to)) if args.compare_to else None
    if args.compare_to and prior is None:
        print(f"  NOTE  could not read {args.compare_to}; the before/after contrast "
              f"is omitted rather than guessed.")

    png = outdir / f"wind_distribution{tag}.png"
    md = outdir / f"wind_verdict{tag}.md"
    make_figure(d, s, png, weather_name=Path(weather).name)
    verdict = write_verdict(s, md, png, weather_name=Path(weather).name, prior=prior)
    (outdir / f"wind_stats{tag}.json").write_text(
        json.dumps({"summary": s, "verdict": verdict, "weather": weather},
                   indent=2, default=str),
        encoding="utf-8")

    print(f"\nverdict: ({verdict})")
    print(f"wrote -> {png}")
    print(f"wrote -> {md}")
    if verdict == "c":
        print("\nVERDICT (c): the wind distribution does NOT explain the change by "
              "the mechanism proposed. See the verdict file — this is escalated, not "
              "papered over.")


if __name__ == "__main__":
    main()
