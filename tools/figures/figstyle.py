"""
Shared data access and drawing style for the paper figure set.

Every number that reaches a figure is read from a committed file under
``results/``. Nothing is re-simulated, and the two quantities the paper leans on
hardest -- the per-area energy need on the paper's metric, and the canonical
headline -- are asserted against the values written in the methodology before any
figure is drawn. A mismatch aborts the whole run rather than producing a plot
that disagrees with the text.

The paper's metric is

    Q_need = Q_H,sensible + Q_C,sensible + Q_C,latent (gated)

i.e. the ``Total, sensible + gated latent`` column of
``results/paper/trajectory_v2/comparison.md``. It excludes latent heating and
excludes the ungated moisture balance, and it is NOT the engine's own
``Q_need_total_kWh`` column: the two differ on the four states before the latent
correction by the phantom humidification term.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "results"
PAPER = RESULTS / "paper"
FIGDIR = PAPER / "figures"

TRAJECTORY_JSON = PAPER / "trajectory_v2" / "trajectory_raw.json"
TRAJECTORY_MD = PAPER / "trajectory_v2" / "comparison.md"
EP_CSV = PAPER / "baseline_vs_ep_v2" / "baseline_vs_energyplus.csv"
EP_META = PAPER / "baseline_vs_ep_v2" / "run_meta.json"
WIND_ESSENDON = RESULTS / "diagnostics" / "wind_stats_essendon.json"
WIND_RO = RESULTS / "diagnostics" / "wind_stats.json"
# The wind-profile pair. Both are on the Essendon file and on the current engine
# tree; they differ only in whether the h_ce correlation is fed the raw 10 m
# station column or the wind local to the wall. WIND_STATION's wind statistics
# ARE the station column (its factor is 1.0 exactly), which is what lets the EPW
# cross-check still run against it.
WIND_STATION = RESULTS / "paper" / "wind_profile" / "wind_stats_station.json"
WIND_TERRAIN = RESULTS / "paper" / "wind_profile" / "wind_stats_terrain.json"
EPW_ESSENDON = REPO / "weather_cache" / "AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw"

# The repaired ISO-against-EnergyPlus comparison. This is what F1 is built from;
# baseline_vs_ep_v2/ above predates the discovery of the reference-model defects
# and its EnergyPlus column is superseded (see its own DEFECT_NOTICE.md).
VALIDATION_CSV = PAPER / "validation_corrected" / "validation_corrected.csv"
VALIDATION_MD = PAPER / "validation_corrected" / "validation_corrected.md"
# The loss-path decomposition of Section 4.1.3, extracted from DISCREPANCY.md by
# tools/paper/extract_loss_paths.py.
LOSS_PATHS_CSV = PAPER / "validation_corrected" / "loss_paths.csv"
DISCREPANCY_MD = PAPER / "validation_corrected" / "DISCREPANCY.md"
# Hourly EnergyPlus series for the four reference-model defects, regenerated from
# the committed IDFs by tools/diagnostics/ep_hourly_defect_signatures.py.
EP_HOURLY_DIR = PAPER / "validation_corrected" / "hourly"

WEATHER = "AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw"
NET_FLOOR_AREA_M2 = 20.0

# ---------------------------------------------------------------------------
# States, in methodology order, with the group each one belongs to.
# ---------------------------------------------------------------------------

STATES = [
    "Baseline",
    "+C1 dynamic window",
    "+C2 wind-dependent h_ce",
    "+Ventilation",
    "+Latent",
    "+Internal gains",
    "+Conditioned zones",
    "+Ground contact",
    "+Hemisphere",
    "+Infiltration supply temp",
    "+Infiltration envelope area",
    "+AU q50 recalibration",
    "+Closure fixes",
    "+Wind profile",
]

# Short labels for crowded axes. Rotated, never truncated.
SHORT = {
    "Baseline": "Baseline",
    "+C1 dynamic window": "+C1 dynamic window",
    "+C2 wind-dependent h_ce": "+C2 wind $h_{ce}$",
    "+Ventilation": "+Ventilation",
    "+Latent": "+Latent",
    "+Internal gains": "+Internal gains",
    "+Conditioned zones": "+Conditioned zones",
    "+Ground contact": "+Ground contact",
    "+Hemisphere": "+Hemisphere",
    "+Infiltration supply temp": "+Infil. supply temp",
    "+Infiltration envelope area": "+Infil. envelope area",
    "+AU q50 recalibration": "+AU $q_{50}$",
    "+Closure fixes": "+Closure fixes",
    "+Wind profile": "+Wind profile",
}

# Plain-text variants of SHORT, for FIGURES.md and any other prose output where
# matplotlib mathtext would leak through as literal "$h_{ce}$".
SHORT_PLAIN = {
    k: v.replace("$h_{ce}$", "h_ce").replace("$q_{50}$", "q50")
    for k, v in SHORT.items()
}

GROUPS = {
    "baseline": ["Baseline"],
    "literature": ["+C1 dynamic window", "+C2 wind-dependent h_ce"],
    "defect": [
        "+Ventilation",
        "+Latent",
        "+Internal gains",
        "+Conditioned zones",
        "+Ground contact",
        "+Hemisphere",
    ],
    "infiltration": [
        "+Infiltration supply temp",
        "+Infiltration envelope area",
        "+AU q50 recalibration",
    ],
    "closure": ["+Closure fixes"],
    "wind": ["+Wind profile"],
}

GROUP_LABEL = {
    "baseline": "Baseline",
    "literature": "Literature corrections (C1, C2)",
    "defect": "Implementation defects",
    "infiltration": "Infiltration defects + AU recalibration (§3.7.1)",
    "closure": "Closure fixes",
    "wind": "Wind profile (terrain + height)",
}

CANONICAL_STATE = "+Wind profile"

# ---------------------------------------------------------------------------
# Colour. Okabe-Ito base hues, one per correction group, with a light-to-dark
# ramp inside each group so a state keeps a unique, stable colour across every
# figure it appears in. Group hues are distinguishable under deuteranopia,
# protanopia and tritanopia; within-group separation is carried by lightness,
# which survives all three.
# ---------------------------------------------------------------------------

GROUP_BASE = {
    "baseline": "#4D4D4D",   # neutral dark grey
    "literature": "#0072B2",  # Okabe-Ito blue
    "defect": "#D55E00",      # Okabe-Ito vermillion
    "infiltration": "#009E73",  # Okabe-Ito bluish green
    "closure": "#CC79A7",     # Okabe-Ito reddish purple
    "wind": "#56B4E9",        # Okabe-Ito sky blue
}

# Reference / annotation colours, also CVD-safe against the group hues.
INK = "#1A1A1A"
MUTED = "#8C8C8C"
MUTED_FILL = "#C8C8C8"
GATE_BAND = "#F0E442"      # Okabe-Ito yellow, used only for the +-5 % gate
REFERENCE = "#56B4E9"      # Okabe-Ito sky blue, used only for reference series
INCREASE = "#D55E00"       # waterfall: correction raises the need
DECREASE = "#0072B2"       # waterfall: correction lowers the need


def _ramp(base_hex: str, n: int) -> list[str]:
    """n colours from a light tint of ``base`` to a dark shade of it."""
    base = np.array(mpl.colors.to_rgb(base_hex))
    if n == 1:
        return [mpl.colors.to_hex(base)]
    out = []
    for i in range(n):
        t = i / (n - 1)          # 0 -> lightest, 1 -> darkest
        if t < 0.5:              # blend towards white
            f = 1.0 - 2.0 * t
            rgb = base + (np.ones(3) - base) * (0.55 * f)
        else:                    # blend towards black
            f = 2.0 * t - 1.0
            rgb = base * (1.0 - 0.42 * f)
        out.append(mpl.colors.to_hex(np.clip(rgb, 0.0, 1.0)))
    return out


STATE_COLOR: dict[str, str] = {}
STATE_GROUP: dict[str, str] = {}
for _g, _members in GROUPS.items():
    for _state, _c in zip(_members, _ramp(GROUP_BASE[_g], len(_members))):
        STATE_COLOR[_state] = _c
        STATE_GROUP[_state] = _g

assert set(STATE_COLOR) == set(STATES), "colour map must cover exactly the 13 states"

# Sankey flow colours. Identical mapping in F2 and F5 so the two read side by
# side: any difference between the figures is the model, not the drawing.
SANKEY_INPUT_COLOR = {
    "Heating": "#0072B2",
    "Internal gains": "#E69F00",
    "Solar & free-gain": "#F0E442",
}
SANKEY_OUTPUT_COLOR = {
    "Cooling (extracted energy)": "#56B4E9",
    "Ventilation (losses)": "#009E73",
    "Thermal bridges": "#CC79A7",
    "Ground": "#8C6D31",
    "Transmission - West exterior wall (opaque)": "#D55E00",
    "Transmission - West window - fixed + West window - operable": "#F4A582",
    "Transmission - North wall to Apt 306": "#4C72B0",
    "Transmission - South wall to Apt 304": "#6E8FCB",
    "Transmission - East wall to corridor": "#93A9DE",
    "Transmission - Floor to Apt 205": "#B7C4EC",
    "Transmission - Ceiling to Apt 405": "#D7DDF6",
}
RESIDUAL_COLOR = "#B03030"

# Order the Sankey bands are stacked in, top to bottom. Fixed, so F2 and F5
# stack identically.
SANKEY_INPUT_ORDER = ["Heating", "Internal gains", "Solar & free-gain"]
SANKEY_OUTPUT_ORDER = [
    "Cooling (extracted energy)",
    "Ventilation (losses)",
    "Thermal bridges",
    "Ground",
    "Transmission - West exterior wall (opaque)",
    "Transmission - West window - fixed + West window - operable",
    "Transmission - North wall to Apt 306",
    "Transmission - South wall to Apt 304",
    "Transmission - East wall to corridor",
    "Transmission - Floor to Apt 205",
    "Transmission - Ceiling to Apt 405",
]

# The five surfaces that face conditioned neighbours: the ADJ class that was
# absent from the inventory before the closure fixes.
PARTY_SURFACES = [
    "Transmission - North wall to Apt 306",
    "Transmission - South wall to Apt 304",
    "Transmission - East wall to corridor",
    "Transmission - Floor to Apt 205",
    "Transmission - Ceiling to Apt 405",
]

SANKEY_SHORT = {
    "Cooling (extracted energy)": "Cooling (extracted)",
    "Ventilation (losses)": "Ventilation + infiltration",
    "Thermal bridges": "Thermal bridges",
    "Ground": "Ground",
    "Transmission - West exterior wall (opaque)": "West exterior wall (OP)",
    "Transmission - West window - fixed + West window - operable": "West windows (W)",
    "Transmission - North wall to Apt 306": "N wall → Apt 306 (ADJ)",
    "Transmission - South wall to Apt 304": "S wall → Apt 304 (ADJ)",
    "Transmission - East wall to corridor": "E wall → corridor (ADJ)",
    "Transmission - Floor to Apt 205": "Floor → Apt 205 (ADJ)",
    "Transmission - Ceiling to Apt 405": "Ceiling → Apt 405 (ADJ)",
}


# ---------------------------------------------------------------------------
# Matplotlib style
# ---------------------------------------------------------------------------

def apply_style() -> None:
    mpl.rcParams.update({
        "figure.dpi": 120,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.12,
        "pdf.fonttype": 42,          # embed TrueType, keep text selectable
        "ps.fonttype": 42,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.edgecolor": "#4D4D4D",
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": "#DDDDDD",
        "grid.linewidth": 0.6,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "xtick.color": "#4D4D4D",
        "ytick.color": "#4D4D4D",
        "legend.fontsize": 8,
        "legend.frameon": True,
        "legend.framealpha": 0.92,
        "legend.edgecolor": "#CCCCCC",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })


def save(fig, name: str) -> list[Path]:
    """Write ``name`` as both vector PDF and 300 dpi PNG into results/paper/figures."""
    FIGDIR.mkdir(parents=True, exist_ok=True)
    written = []
    for ext in ("pdf", "png"):
        path = FIGDIR / f"{name}.{ext}"
        fig.savefig(path, format=ext)
        written.append(path)
    plt.close(fig)
    return written


def state_ticks(ax, rotation: int = 55) -> None:
    """Thirteen state labels, rotated rather than truncated."""
    ax.set_xticks(range(len(STATES)))
    ax.set_xticklabels(
        [SHORT[s] for s in STATES],
        rotation=rotation,
        ha="right",
        rotation_mode="anchor",
    )


def mark_infiltration_group(ax, label: bool = False) -> None:
    """Shade the three infiltration states so they read as a group (Section 3.7.1)."""
    members = GROUPS["infiltration"]
    lo = STATES.index(members[0]) - 0.5
    hi = STATES.index(members[-1]) + 0.5
    ax.axvspan(lo, hi, color=GROUP_BASE["infiltration"], alpha=0.10, zorder=0, lw=0)
    ax.axvline(lo, color=GROUP_BASE["infiltration"], lw=0.7, alpha=0.55, zorder=0)
    ax.axvline(hi, color=GROUP_BASE["infiltration"], lw=0.7, alpha=0.55, zorder=0)
    if label:
        ax.text(
            (lo + hi) / 2.0, 0.965, "infiltration states (§3.7.1)",
            transform=ax.get_xaxis_transform(), ha="center", va="top",
            fontsize=7.2, color=GROUP_BASE["infiltration"], fontweight="bold",
        )


def group_legend_handles():
    from matplotlib.patches import Patch
    return [
        Patch(facecolor=GROUP_BASE[g], edgecolor="none", label=GROUP_LABEL[g])
        for g in ("baseline", "literature", "defect", "infiltration", "closure", "wind")
    ]


# ---------------------------------------------------------------------------
# Data access, with the paper's numbers asserted on load
# ---------------------------------------------------------------------------

# The paper's per-area energy need, kWh/m2.yr, on Q_H,sens + Q_C,sens + Q_C,lat(gated).
# Any figure that prints a per-area value must agree with this list.
EXPECTED_PER_AREA = {
    "Baseline": 122.32,
    "+C1 dynamic window": 120.77,
    "+C2 wind-dependent h_ce": 119.70,
    "+Ventilation": 133.41,
    "+Latent": 132.88,
    "+Internal gains": 220.82,
    "+Conditioned zones": 10.75,
    "+Ground contact": 10.75,
    "+Hemisphere": 10.75,
    "+Infiltration supply temp": 8.52,
    "+Infiltration envelope area": 6.44,
    "+AU q50 recalibration": 6.91,
    "+Closure fixes": 6.91,
    "+Wind profile": 7.21,
}

CANONICAL = {
    "Q_H_sensible_kWh": 122.88,
    "Q_C_sensible_kWh": 19.9,
    "Q_C_latent_kWh": 1.51,
    "Q_need_kWh": 144.28,
    "Q_need_kWh_per_sqm": 7.21,
}


class MissingQuantity(RuntimeError):
    """A figure asked for a number that is not in the committed result files."""


def _require(path: Path) -> Path:
    if not path.exists():
        raise MissingQuantity(f"required result file is missing: {path}")
    return path


def load_trajectory() -> dict:
    """The 13-state trajectory, verified against the paper's published metric."""
    raw = json.loads(_require(TRAJECTORY_JSON).read_text())

    order = list(raw["results"].keys())
    if order != STATES:
        raise MissingQuantity(
            "trajectory state order does not match the methodology order:\n"
            f"  file: {order}\n  expected: {STATES}"
        )

    if raw["meta"]["weather"].split("/")[-1] != WEATHER:
        raise MissingQuantity(
            f"trajectory was run on {raw['meta']['weather']!r}, not {WEATHER!r}"
        )

    traj: dict[str, dict] = {}
    for state in STATES:
        c = raw["results"][state]["config_B"]
        area = float(c["net_floor_area_m2"])
        if abs(area - NET_FLOOR_AREA_M2) > 1e-9:
            raise MissingQuantity(f"{state}: net floor area {area} != {NET_FLOOR_AREA_M2}")
        q_need = c["Q_H_sensible_kWh"] + c["Q_C_sensible_kWh"] + c["Q_C_latent_kWh"]
        traj[state] = {
            "Q_H_sens": c["Q_H_sensible_kWh"],
            "Q_C_sens": c["Q_C_sensible_kWh"],
            "Q_C_lat_gated": c["Q_C_latent_kWh"],
            "Q_C_lat_ungated": c["Q_C_latent_ungated_kWh"],
            "Q_H_lat": c["Q_H_latent_kWh"],
            # The paper's metric. Deliberately not c["Q_need_total_kWh"], which
            # carries latent heating on the four pre-latent-fix states.
            "Q_need": q_need,
            "Q_need_per_sqm": q_need / area,
            "Q_engine_total": c["Q_need_total_kWh"],
            "Q_ve_loss": c["Q_ve_loss_kWh"],
            "Q_ve_gain": c["Q_ve_gain_kWh"],
            "residual_kWh": c["sankey"]["residual_kWh"],
            "residual_pct": c["sankey"]["residual_pct"],
            "n_transmission_items": c["sankey"]["n_transmission_items"],
            "transmission_reported_kWh": c["sankey"]["transmission_reported_kWh"],
            "transmission_independent_kWh": c["sankey"]["transmission_independent_kWh"],
            "transmission_rel_diff": c["sankey"]["transmission_rel_diff"],
            "n_steps": c["n_steps"],
            "n_steps_cooling_on": c["n_steps_cooling_on"],
            "n_steps_heating_on": c["n_steps_heating_on"],
            "n_steps_latent_charged": c["n_steps_latent_charged"],
            "latent_kWh_with_cooling_off": c["latent_kWh_with_cooling_off"],
            "latent_kWh_while_heating": c["latent_kWh_while_heating"],
            "monthly_latent_cooling_kWh": c["monthly_latent_cooling_kWh"],
            "sankey": c["sankey"],
        }

    # Gate 1: every per-area value must reproduce the paper's list. Tolerance is
    # one unit in the paper's last printed place: the list is quoted to 2 dp, so
    # anything within 0.01 kWh/m2 is the same measurement and anything outside it
    # is a different one.
    bad = []
    for state, expected in EXPECTED_PER_AREA.items():
        got = traj[state]["Q_need_per_sqm"]
        if abs(got - expected) >= 0.01:
            bad.append(f"  {state}: figure would print {got:.4f}, paper states {expected}")
    if bad:
        raise MissingQuantity(
            "per-area energy need disagrees with the paper's metric:\n" + "\n".join(bad)
        )

    # Gate 2: the canonical headline.
    can = traj[CANONICAL_STATE]
    for key, field in (
        ("Q_H_sensible_kWh", "Q_H_sens"),
        ("Q_C_sensible_kWh", "Q_C_sens"),
        ("Q_C_latent_kWh", "Q_C_lat_gated"),
        ("Q_need_kWh", "Q_need"),
        ("Q_need_kWh_per_sqm", "Q_need_per_sqm"),
    ):
        if abs(can[field] - CANONICAL[key]) >= 0.01:
            raise MissingQuantity(
                f"canonical {key}: file gives {can[field]:.4f}, paper states {CANONICAL[key]}"
            )

    return {"states": traj, "meta": raw["meta"], "state_notes": raw["states"]}


def load_ep() -> dict:
    """Baseline ISO 52016-1 against EnergyPlus, with differences on the EP reference."""
    lines = _require(EP_CSV).read_text().strip().splitlines()
    header = lines[0].split(",")
    rows = {}
    for line in lines[1:]:
        parts = line.split(",")
        rows[parts[0]] = {k: float(v) for k, v in zip(header[1:], parts[1:])}

    out = {}
    for metric in ("Heating", "Cooling", "Total"):
        if metric not in rows:
            raise MissingQuantity(f"{EP_CSV} has no {metric} row")
        iso = rows[metric]["ISO_52016_kWh"]
        ep = rows[metric]["EnergyPlus_kWh"]
        out[metric] = {
            "iso": iso,
            "ep": ep,
            # The committed CSV expresses diff_pct against the ISO figure. The
            # paper quotes the difference against the EnergyPlus reference, so
            # it is recomputed here from the same two kWh values.
            "diff_kWh": iso - ep,
            "diff_pct_vs_ep": 100.0 * (iso - ep) / ep,
            "iso_per_sqm": rows[metric]["ISO_kWh_m2"],
            "ep_per_sqm": rows[metric]["EP_kWh_m2"],
        }

    expected = {"Heating": 58.8, "Cooling": -8.1, "Total": 33.2}
    bad = [
        f"  {m}: computed {out[m]['diff_pct_vs_ep']:+.1f} %, paper states {e:+.1f} %"
        for m, e in expected.items()
        if abs(round(out[m]["diff_pct_vs_ep"], 1) - e) > 0.051
    ]
    if bad:
        raise MissingQuantity(
            "ISO-vs-EnergyPlus differences disagree with the paper:\n" + "\n".join(bad)
        )

    out["_meta"] = json.loads(_require(EP_META).read_text())
    return out


def load_wind(which: str) -> dict:
    path = {"essendon": WIND_ESSENDON, "ro": WIND_RO,
            "station": WIND_STATION, "terrain": WIND_TERRAIN}[which]
    return json.loads(_require(path).read_text())


def load_epw_wind(path: Path = EPW_ESSENDON) -> dict:
    """
    Wind speed, month and hour from the committed EPW.

    This is the same file the wind diagnostic was run on and the file named in
    the trajectory's provenance -- not a second run. Its annual aggregates are
    checked against ``wind_stats_essendon.json`` below, so the hourly detail the
    distribution and diurnal panels need is verified against the committed
    summary rather than taken on trust.
    """
    months, hours, speeds = [], [], []
    with _require(path).open("r", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i < 8:            # EPW header block is eight lines
                continue
            f = line.split(",")
            if len(f) < 22:
                continue
            months.append(int(f[1]))
            hours.append(int(f[3]))
            speeds.append(float(f[21]))
    return {
        "month": np.array(months, dtype=int),
        "hour": np.array(hours, dtype=int),
        "wind": np.array(speeds, dtype=float),
    }


def verify_epw_against_stats(epw: dict, stats: dict) -> None:
    """Abort unless the EPW column reproduces the committed wind summary."""
    s = stats["summary"]
    w = epw["wind"]
    checks = [
        ("n_hours", len(w), s["n_hours"], 0),
        ("mean_wind_annual", float(w.mean()), s["mean_wind_annual"], 1e-6),
        ("max_wind_annual", float(w.max()), s["max_wind_annual"], 1e-9),
        ("pct_hours_exactly_zero", 100.0 * float((w == 0.0).mean()),
         s["pct_hours_exactly_zero"], 1e-6),
        ("pct_hours_above_pivot", 100.0 * float((w > 4.0).mean()),
         s["pct_hours_above_pivot"], 1e-6),
    ]
    bad = [
        f"  {name}: EPW gives {got!r}, wind_stats gives {want!r}"
        for name, got, want, tol in checks
        if abs(float(got) - float(want)) > tol
    ]
    if bad:
        raise MissingQuantity(
            "committed EPW wind column does not reproduce the committed wind "
            "summary:\n" + "\n".join(bad)
        )


# ---------------------------------------------------------------------------
# The repaired ISO-against-EnergyPlus comparison (F1), and the loss-path
# decomposition behind it (F12).
# ---------------------------------------------------------------------------

# Table 3 of the manuscript, kWh/yr. Each engine is compared against a reference
# matched to IT: the baseline engine against the ISO 13789 buffer case with
# inflated gains and no infiltration, the corrected engine against the 20 degC
# neighbour case with EN 16798-1 gains and infiltration. Both references carry
# the repairs to the four defects. Any figure printing these must reproduce them.
EXPECTED_VALIDATION = {
    "baseline": {
        "Heating": (1779.36, 2081.97),
        "Cooling": (640.84, 697.35),
        "Total": (2420.20, 2779.32),
    },
    "corrected": {
        "Heating": (122.88, 148.97),
        "Cooling": (19.90, 21.59),
        "Total": (142.78, 170.56),
    },
}

VALIDATION_PANEL_LABEL = {
    "baseline": "Baseline engine",
    "corrected": "Corrected engine",
}

# What each engine's reference is matched on. Printed on the panel, because the
# whole point of the two-panel form is that these are two different references.
VALIDATION_PANEL_BASIS = {
    "baseline": ("reference matched to it: unconditioned buffer neighbours,\n"
                 "inflated internal gains, no infiltration"),
    "corrected": ("reference matched to it: neighbours at 20 °C, EN 16798-1 gains,\n"
                  "infiltration at the adopted permeability, terrain-corrected wind"),
}


def load_validation_corrected() -> dict:
    """
    Both halves of Table 3, with the twelve kWh values asserted on load.

    Differences are stated against the EnergyPlus reference, following the
    committed validation, and are carried in BOTH forms -- absolute kWh and per
    cent -- because the paper's argument is that the absolute gap is the
    meaningful statement and the relative one destabilises as the load falls.
    """
    lines = [ln for ln in _require(VALIDATION_CSV).read_text().splitlines() if ln.strip()]
    header = lines[0].split(",")
    if header[:4] != ["section", "metric", "iso_kWh", "ep_kWh"]:
        raise MissingQuantity(f"{VALIDATION_CSV} has an unexpected header: {header}")

    rows: dict[str, dict[str, dict]] = {"baseline": {}, "corrected": {}}
    for line in lines[1:]:
        parts = line.split(",")
        if parts[0] not in rows or len(parts) < len(header):
            continue
        rows[parts[0]][parts[1]] = {k: float(v) for k, v in zip(header[2:], parts[2:])}

    out: dict[str, dict] = {}
    bad = []
    for section, metrics in EXPECTED_VALIDATION.items():
        out[section] = {}
        for metric, (iso_expected, ep_expected) in metrics.items():
            if metric not in rows[section]:
                raise MissingQuantity(f"{VALIDATION_CSV}: no {section}/{metric} row")
            r = rows[section][metric]
            iso, ep = r["iso_kWh"], r["ep_kWh"]
            for name, got, want in (("ISO", iso, iso_expected), ("E+", ep, ep_expected)):
                if abs(got - want) >= 0.005:
                    bad.append(f"  {section} {metric} {name}: file gives {got:.4f}, "
                               f"Table 3 states {want}")
            out[section][metric] = {
                "iso": iso,
                "ep": ep,
                "diff_kWh": iso - ep,
                "diff_pct_vs_ep": 100.0 * (iso - ep) / ep,
                "iso_per_sqm": r["iso_kWh_m2"],
                "ep_per_sqm": r["ep_kWh_m2"],
            }
    if bad:
        raise MissingQuantity(
            "the corrected validation disagrees with Table 3:\n" + "\n".join(bad)
        )

    # Heating + cooling must be the stated total on both engines and both sides.
    for section in out:
        for side in ("iso", "ep"):
            parts_sum = out[section]["Heating"][side] + out[section]["Cooling"][side]
            if abs(parts_sum - out[section]["Total"][side]) >= 0.01:
                raise MissingQuantity(
                    f"{section} {side}: heating + cooling = {parts_sum:.4f} kWh but the "
                    f"total row states {out[section]['Total'][side]:.4f} kWh"
                )
    return out


def load_loss_paths() -> dict:
    """
    The Section 4.1.3 loss-path decomposition, ordered by absolute difference.

    Read from ``loss_paths.csv`` and re-checked against ``DISCREPANCY.md``, so
    the CSV cannot drift away from the document the paper cites.
    """
    lines = [ln for ln in _require(LOSS_PATHS_CSV).read_text().splitlines() if ln.strip()]
    import csv as _csv

    records = list(_csv.DictReader(lines))
    paths = [r for r in records if r["is_total"] == "no"]
    totals = [r for r in records if r["is_total"] == "yes"]
    if not paths or len(totals) != 1:
        raise MissingQuantity(
            f"{LOSS_PATHS_CSV}: expected several path rows and exactly one total row"
        )

    def _cast(r):
        return {
            "path": r["path"],
            "short_label": r["short_label"].replace(" | ", "\n"),
            "iso": float(r["iso_kWh"]),
            "ep": float(r["ep_kWh"]),
            "diff": float(r["diff_kWh"]),
        }

    out = {
        "paths": sorted((_cast(r) for r in paths), key=lambda r: abs(r["diff"]),
                        reverse=True),
        "total": _cast(totals[0]),
    }

    # Cross-check every value against the markdown table the paper cites. Cells
    # there are printed to 0.1 kWh, so equality is asserted at that precision.
    md = _require(DISCREPANCY_MD).read_text()
    for r in out["paths"] + [out["total"]]:
        row = next((ln for ln in md.splitlines()
                    if ln.startswith("|") and r["path"] in ln), None)
        if row is None:
            raise MissingQuantity(
                f"{DISCREPANCY_MD.name} has no loss-path row for {r['path']!r} -- "
                f"{LOSS_PATHS_CSV.name} is stale; re-run "
                f"tools/paper/extract_loss_paths.py"
            )
        cells = row.strip().strip("|").split("|")
        for idx, key in ((1, "iso"), (2, "ep"), (3, "diff")):
            want = float(cells[idx].replace("**", "").replace(",", "")
                         .replace("−", "-").replace("+", "").strip())
            if abs(want - r[key]) > 0.051:
                raise MissingQuantity(
                    f"{r['path']} {key}: CSV has {r[key]:+.1f} kWh, "
                    f"{DISCREPANCY_MD.name} has {want:+.1f} kWh"
                )

    # The decomposition has to close: the paths must sum to the stated total on
    # both sides, within what 0.1 kWh printing allows.
    tol = 0.05 * (len(out["paths"]) + 1) + 1e-9
    for key in ("iso", "ep"):
        summed = sum(r[key] for r in out["paths"])
        if abs(summed - out["total"][key]) > tol:
            raise MissingQuantity(
                f"loss paths do not close on the {key} side: {summed:+.1f} kWh against "
                f"a stated total of {out['total'][key]:+.1f} kWh"
            )
    return out


# ---------------------------------------------------------------------------
# Hourly EnergyPlus series for the four reference-model defects (F11)
# ---------------------------------------------------------------------------

EP_HOURLY_FILES = {
    "corrected_matched": "hourly_corrected_matched.csv",
    "as_published_wind": "hourly_as_published_wind.csv",
    "baseline_repaired": "hourly_baseline_repaired.csv",
}

J_PER_KWH = 3.6e6


def load_ep_hourly(which: str) -> dict:
    """One of the three committed hourly EnergyPlus series, as numpy arrays."""
    try:
        name = EP_HOURLY_FILES[which]
    except KeyError as exc:
        raise MissingQuantity(f"no hourly EnergyPlus series named {which!r}") from exc
    path = EP_HOURLY_DIR / name
    if not path.exists():
        raise MissingQuantity(
            f"hourly EnergyPlus series {path} is missing. The raw EnergyPlus output "
            f"directory is gitignored as regenerable intermediate; regenerate with "
            f"tools/diagnostics/ep_hourly_defect_signatures.py --energyplus <bin>"
        )
    lines = path.read_text().splitlines()
    header = lines[0].split(",")
    cols: dict[str, list[float]] = {h: [] for h in header[2:]}
    for line in lines[1:]:
        parts = line.split(",")
        for h, v in zip(header[2:], parts[2:]):
            cols[h].append(float(v))
    out = {k: np.array(v, dtype=float) for k, v in cols.items()}
    n = {len(v) for v in out.values()}
    if n != {8760}:
        raise MissingQuantity(f"{path}: hourly series are {n} long, expected 8760")
    return out


def load_ep_hourly_provenance() -> dict:
    path = EP_HOURLY_DIR / "provenance.json"
    if not path.exists():
        raise MissingQuantity(
            f"{path} is missing; regenerate the hourly series with "
            f"tools/diagnostics/ep_hourly_defect_signatures.py"
        )
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Case geometry (F13). Read from examples/apt305_building.py rather than
# restated, so the drawing cannot drift away from the simulated case.
# ---------------------------------------------------------------------------

def load_geometry() -> dict:
    """
    The Apt 305 envelope, from the building dictionary the engine is actually run on.

    Returns the one outdoor-exposed wall and its glazing, the five party
    surfaces, and the conductance share the adjacent-zone correction acts on.
    """
    import importlib.util

    src = REPO / "examples" / "apt305_building.py"
    spec = importlib.util.spec_from_file_location("apt305_building", _require(src))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bui = module.build_bui()

    exposed, party = [], []
    for s in bui["building_surface"]:
        rec = {
            "name": s["name"],
            "area": float(s["area"]),
            "u_value": float(s["u_value"]),
            "adj_zone": s.get("name_adj_zone"),
            "azimuth": float(s["orientation"]["azimuth"]),
            "tilt": float(s["orientation"]["tilt"]),
            "window": s["type"] == "transparent",
            "g_value": float(s["g_value"]) if "g_value" in s else None,
        }
        # The five party surfaces are the ADJ class; everything else in this case
        # is on the one outdoor-exposed west facade.
        (party if s["type"] == "adjacent" else exposed).append(rec)

    ua_exposed = sum(s["area"] * s["u_value"] for s in exposed)
    ua_party = sum(s["area"] * s["u_value"] for s in party)
    return {
        "exposed": exposed,
        "party": party,
        "area_exposed": sum(s["area"] for s in exposed),
        "area_party": sum(s["area"] for s in party),
        "UA_exposed": ua_exposed,
        "UA_party": ua_party,
        "party_UA_share_pct": 100.0 * ua_party / (ua_exposed + ua_party),
        "len_ns": module.LEN_NS,
        "len_ew": module.LEN_EW,
        "height": module.HEIGHT,
        "floor_area": module.FLOOR_AREA,
        "adj_setpoint": module.ADJ_SETPOINT,
        "floor_level": bui["site"]["floor_level"],
    }
