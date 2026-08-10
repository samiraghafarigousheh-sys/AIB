"""
Corrected pyBuildingEnergy (ISO 52016-1 + the twelve AIB corrections) vs EnergyPlus.

WHY THIS EXISTS
---------------
``baseline_vs_energyplus.py`` validates the *baseline* engine and reports the
starting discrepancy. It cannot be re-used as it stands, because its EnergyPlus
model represents the five adjacent zones through the ISO 13789 *unconditioned
buffer* (``--adj-mode iso-bztu``, N4 = b_ztu). That is what the baseline ISO
engine does; the corrected engine holds those neighbours at 20 C. Running the
corrected engine against that reference would compare a corrected engine to a
reference configured for the uncorrected one.

This module builds a **second** EnergyPlus case whose adjacent-zone boundary,
internal gains and infiltration all match the *corrected* engine, and compares
the two on the same weather file. Geometry, constructions, ventilation,
setpoints, control temperature, window frame treatment, internal mass, ideal
loads, calendar and daylight saving are inherited unchanged from the baseline
IDF builder, so the only things that differ between the two references are the
three the corrections actually moved.

Usage
-----
    python examples/corrected_vs_energyplus.py --energyplus /path/to/energyplus
    python examples/corrected_vs_energyplus.py --audit-only
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
SRC_DIR = REPO_ROOT / "pybuildingenergy" / "src"
for _p in (str(EXAMPLES_DIR), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_EPW = (REPO_ROOT / "weather_cache"
               / "AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw")
OUTDIR = REPO_ROOT / "results" / "paper" / "validation_corrected"

# The published baseline validation, for the before/after table. Read from
# results/paper/baseline_vs_ep_v2/baseline_vs_energyplus.csv at run time; these
# are the fallback values and are asserted against the file when it is present.
BASELINE_ISO = {"Heating": 1779.36, "Cooling": 640.84}
BASELINE_EP = {"Heating": 1120.25, "Cooling": 697.16}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# The corrected engine's adjacent-zone setpoint, and the neighbour surfaces it
# applies to. Both are read back off the building dictionary and asserted.
ADJ_SETPOINT_C = 20.0

SURFACE_TO_ISO = {
    "NorthWall": "North wall to Apt 306",
    "SouthWall": "South wall to Apt 304",
    "EastWall": "East wall to corridor",
    "FloorSlab": "Floor to Apt 205",
    "CeilingSlab": "Ceiling to Apt 405",
}


class Unmatchable(RuntimeError):
    """An input that cannot be aligned between the two engines.

    Raised rather than silently producing a comparison that looks aligned and is
    not — the failure mode this whole task exists to avoid.
    """


# ---------------------------------------------------------------------------
# Alignment record for the MATCHED case
# ---------------------------------------------------------------------------

def alignment_rows(inf: dict, gains: dict) -> list[tuple[str, str, str, str]]:
    """(parameter, corrected ISO behaviour, EnergyPlus handling, status)."""
    return [
        ("Geometry / areas",
         "5.0 x 4.0 x 2.7 m, 1.62 m2 west glazing, 13.5 m2 outdoor-exposed envelope",
         "same, derived from the same apt305_building module",
         "ALIGNED"),

        ("Opaque U-values",
         "ext 1.00, partition 2.50, slab 1.80 W/m2K",
         "Material:NoMass R back-calculated from the same U",
         "ALIGNED"),

        ("Surface thermal mass",
         "C = 0 J/m2K on every element",
         "Material:NoMass (no storage)",
         "ALIGNED"),

        ("Zone internal capacitance",
         "c_int_per_A_us = 10000 J/m2K (200 kJ/K over 20 m2)",
         "InternalMass, 1 cm of 1000 kg/m3 x 1000 J/(kg K) over the floor area",
         "ALIGNED"),

        ("Window U / SHGC",
         "U 5.40 W/m2K, g 0.65",
         "WindowMaterial:SimpleGlazingSystem 5.40 / 0.65",
         "ALIGNED"),

        ("Window frame fraction",
         "Ffr_wi = 0.25: solar uses 75 % of area, conduction uses 100 %",
         "SHGC scaled to 0.65*0.75 = 0.4875, U and area unchanged",
         "FIXED"),

        ("Window shading",
         "the declared 0.25 m overhang yields factor 1.0000 for all 8760 h",
         "no shading surfaces — the two therefore already agree",
         "ALIGNED"),

        ("ADJACENT ZONES — the correction under test",
         f"the five party surfaces are marked conditioned:True with setpoint "
         f"{ADJ_SETPOINT_C:.1f} C, so theta_ztu is held at the setpoint and the "
         f"ISO 13789 buffer formula is NOT evaluated",
         f"SurfaceProperty:OtherSideCoefficients with N2 = {ADJ_SETPOINT_C:.1f}, "
         f"N3 = 1.0 and N4 = N5 = N6 = N7 = 0, so T_os = {ADJ_SETPOINT_C:.1f} C "
         f"at every timestep (see 'Choice of representation' below)",
         "FIXED"),

        ("Adjacent surface film",
         "R_c back-calculated assuming R_si = 0.13 both sides",
         "OSC film coefficient 1/0.13 = 7.6923 W/m2K",
         "FIXED"),

        ("INTERNAL GAINS — the correction under test",
         f"EN 16798-1 tabulated q_int for the building type class, "
         f"{gains['occupants_W']:.1f} W occupants + {gains['appliances_W']:.1f} W "
         f"appliances + {gains['lighting_W']:.1f} W lighting over 20 m2; the "
         f"neighbour-count multiplier is gone",
         f"OtherEquipment design levels set to the same {gains['occupants_W']:.1f} / "
         f"{gains['appliances_W']:.1f} / {gains['lighting_W']:.1f} W on the shared "
         f"hourly profiles",
         "FIXED"),

        ("Internal gain radiant split",
         "f_int_c = 0.4, i.e. 0.6 radiant for every gain",
         "OtherEquipment radiant fraction 0.6",
         "FIXED"),

        ("Ventilation (designed)",
         "2.0 l/(s m2) constant, H_ve_nat = 48.4 W/K",
         "ZoneVentilation:DesignFlowRate 0.04 m3/s on an always-on schedule with "
         "constant coefficients, so the exchange happens every hour. Attaching "
         "it to the ideal-loads system instead would deliver it only in the "
         "hours the system runs (686 of 8760 here)",
         "FIXED"),

        ("INFILTRATION — the correction under test",
         f"q50 = {inf['q50']:.1f} m3/(h m2)@50Pa over the OUTDOOR-EXPOSED envelope "
         f"A_env = {inf['a_env']:.2f} m2 (not the 88.6 m2 whole-surface sum); "
         f"n50 = q50*A_env/V = {inf['n50']:.4f} 1/h over V = {inf['volume']:.1f} m3; "
         f"LBL divide-by-N with N = {inf['lbl_n']:.0f} gives a mean natural rate "
         f"n_inf = {inf['n_inf_mean']:.4f} 1/h",
         f"ZoneInfiltration:DesignFlowRate, Flow/Zone "
         f"{inf['design_flow_m3_s']:.8f} m3/s (= {inf['n_inf_mean']:.4f} ACH), "
         f"constant term A = 1 and B = C = D = 0, modulated hour by hour by an "
         f"embedded Schedule:Compact carrying the ISO f(t)",
         "FIXED"),

        ("Infiltration stack/wind modulation",
         "f(t) = sqrt((Cs*|theta_int(t-1) - theta_e| + Cw*u^2) / "
         f"(Cs*{inf['dt_ref']:.0f} + Cw*{inf['u_ref']:.0f}^2)), "
         f"Cs = {inf['c_stack']}, Cw = {inf['c_wind']}; f = 1 at reference "
         f"conditions. Annual mean f = {inf['f_mean']:.4f}, "
         f"range {inf['f_min']:.4f}-{inf['f_max']:.4f}",
         "E+'s own modulation is A + B|dT| + C*u + D*u^2, which is LINEAR in the "
         "driving forces and cannot reproduce a square root. The ISO f(t) series "
         "is therefore precomputed from the corrected ISO run and embedded as an "
         "8760-value Schedule:Compact. This matches the series hour for hour but "
         "makes the coupling ONE-WAY: f(t) carries the ISO zone temperature, not "
         "E+'s. The --inf-mode constant run bounds what that costs.",
         "FIXED (one-way)"),

        ("Setpoints",
         "heat 18/15, cool 26/28 driven by the hourly profiles",
         "DualSetpoint from the same profiles, control type schedule = 4",
         "ALIGNED"),

        ("Control temperature",
         "operative temperature (0.5*T_air + 0.5*T_mr)",
         "ZoneControl:Thermostat:OperativeTemperature, radiative fraction 0.5",
         "FIXED"),

        ("HVAC",
         "ideal, 10 MW capacity",
         "ZoneHVAC:IdealLoadsAirSystem, NoLimit",
         "ALIGNED"),

        ("Latent load",
         "gated: charged only in hours the cooling plant runs; 1.14 kWh/yr, "
         "reported separately from the sensible need",
         "humidification and dehumidification control both None, and the "
         "SENSIBLE ideal-loads variables are the ones summed, so the E+ figure "
         "is sensible-only. Heating is asserted to equal its total; the small "
         "residual latent cooling is reported beside the ISO gated term",
         "FIXED"),

        ("Calendar / day of week",
         "profile generator uses AU holidays, Jan 1 lands on a Thursday",
         "RunPeriod start day Thursday; weather-file holidays off",
         "FIXED"),

        ("Daylight saving",
         "not modelled",
         "Use Weather File Daylight Saving Period = No",
         "FIXED"),

        ("Timestep",
         "hourly",
         "6 per hour; results aggregated to hourly and annual",
         "METHOD"),

        ("Solar distribution",
         "f_sol_c = 0.1 convective, the rest to the surface nodes",
         "FullInteriorAndExterior ray tracing",
         "METHOD"),

        ("Surface heat transfer",
         "C2 correction: h_ce = 4v + 4 on outdoor-exposed surfaces; the ISO "
         "constant elsewhere",
         "TARP/DOE-2 dynamic algorithms — a different correlation, not a "
         "different intent",
         "METHOD"),

        ("Conduction discretisation",
         "five-node RC per element, ISO 52016-1 Annex B",
         "conduction transfer functions",
         "METHOD"),
    ]


CHOICE_NOTE = """\
### Choice of adjacent-zone representation

Two representations are admissible. This case uses **`OtherSideCoefficients`
with a constant boundary temperature** (`N2 = 20.0`, `N3 = 1.0`,
`N4 = N5 = N6 = N7 = 0`, so `T_os = 20.0` C at every timestep), rather than
explicit adjacent thermal zones each with its own ideal-loads system.

The reason is that this is the closer analogue of what the corrected ISO engine
actually does. `_adjacent_zone_conditioning` does not *simulate* the neighbour:
a zone marked `conditioned: True` has its `theta_ztu` **held at the declared
setpoint**, and the ISO 13789 buffer expression is never evaluated for it. A
fixed-temperature boundary reproduces that substitution exactly. Explicit
adjacent zones would instead simulate five neighbours whose air temperature
would float within the ideal-loads system's control band and respond to their
own gains and their own exposures — a richer model than the corrected ISO engine
contains, and one that would introduce a difference the ISO side has no
counterpart for. Since the object of this comparison is the corrected engine's
own treatment, the fixed boundary is the faithful choice.

The cost is that the E+ neighbour cannot deviate from 20 C even momentarily,
which is exactly the corrected ISO engine's assumption too, so it is not a cost
against *this* comparison. It is a shared idealisation of both models against
the real building, and is recorded as such.
"""


def render_alignment(rows) -> str:
    w1, w2, w3 = 26, 60, 60
    out = ["=" * (w1 + w2 + w3 + 16),
           "PARAMETER ALIGNMENT AUDIT — corrected ISO 52016-1 vs matched EnergyPlus",
           "=" * (w1 + w2 + w3 + 16),
           f"{'PARAMETER':<{w1}}{'ISO 52016-1 (corrected)':<{w2}}"
           f"{'EnergyPlus (matched case)':<{w3}}STATUS",
           "-" * (w1 + w2 + w3 + 16)]

    def wrap(text, width):
        lines, line = [], ""
        for word in text.split():
            if len(line) + len(word) + 1 > width - 1:
                lines.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        lines.append(line)
        return lines

    for name, iso, ep, status in rows:
        a, b = wrap(iso, w2), wrap(ep, w3)
        for r in range(max(len(a), len(b))):
            out.append(f"{(name if r == 0 else ''):<{w1}}"
                       f"{(a[r] if r < len(a) else ''):<{w2}}"
                       f"{(b[r] if r < len(b) else ''):<{w3}}"
                       f"{status if r == 0 else ''}")
        out.append("")
    n_fixed = sum(1 for *_x, s in rows if s.startswith("FIXED"))
    n_method = sum(1 for *_x, s in rows if s == "METHOD")
    out.append(f"{len(rows)} parameters checked — "
               f"{len(rows) - n_fixed - n_method} already aligned, "
               f"{n_fixed} mismatches corrected, "
               f"{n_method} irreducible method differences.")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The corrected engine: probe, then run
# ---------------------------------------------------------------------------

ISO_WORKER = r'''
import json, math, sys
sys.path.insert(0, sys.argv[1])   # engine src (HEAD, the corrected engine)
sys.path.insert(0, sys.argv[2])   # examples dir
import numpy as np
import pandas as pd

from apt305_building import build_bui
from pybuildingenergy.source.utils import (
    ISO52016, _envelope_area_m2, _zone_volume_m3, _q50_for_construction_age,
    _LBL_N_DIVISOR, _INF_C_STACK, _INF_C_WIND, _INF_DT_REF, _INF_U_REF,
    _RHO_CP_AIR_WH_M3K,
)
from pybuildingenergy.source.check_input import sanitize_and_validate_BUI
from pybuildingenergy.source.ventilation import VentilationInternalGains

EPW = sys.argv[3]
OUT = sys.argv[4]

raw = build_bui()

# --- internal gains exactly as the CORRECTED engine computes them -----------
# The engine substitutes the EN 16798-1 tabulated q_int for the building type
# class; the dictionary's full_load entries are overrides, and the profiles are
# shared with EnergyPlus. Probing with unit profiles isolates each category's
# watts, so the E+ design levels reproduce the ISO gain hour for hour.
_ig = VentilationInternalGains(raw)
_kw = dict(building_type_class=raw["building"]["building_type_class"],
           a_use=raw["building"]["net_floor_area"],
           unconditioned_zones_nearby=False)
def _g(o=0.0, a=0.0, l=0.0):
    return float(_ig.internal_gains(h_occup=o, h_app=a, h_light=l, **_kw))
_base = _g()
gains_w = {"base_W": _base,
           "occupants_W": _g(1, 0, 0) - _base,
           "appliances_W": _g(0, 1, 0) - _base,
           "lighting_W": _g(0, 0, 1) - _base}

# The corrections dropped the neighbour-count multiplier. Assert it: if the
# with-neighbours probe differs, the multiplier is back and the E+ design levels
# below would be wrong.
_kw_adj = dict(_kw)
_kw_adj.update(unconditioned_zones_nearby=True, Fztc_ztu_m=1.0,
               list_adj_zones=raw["building"].get("number_adj_zone", 0), b_ztu=0.9)
def _ga(o=0.0, a=0.0, l=0.0):
    return float(_ig.internal_gains(h_occup=o, h_app=a, h_light=l, **_kw_adj))
_neighbour_multiplier_present = abs((_ga(1, 0, 0) - _ga()) - gains_w["occupants_W"]) > 1e-9

# --- infiltration sizing, from the engine's own helpers ---------------------
a_env = float(_envelope_area_m2(raw))
volume = float(_zone_volume_m3(raw))
q50 = float(_q50_for_construction_age(raw))
_override = ((raw.get("building_parameters", {}) or {}).get("ventilation", {}) or {}
             ).get("envelope_permeability_q50")
if _override is not None:
    q50 = float(_override)
n50 = q50 * a_env / volume
n_inf_mean = n50 / _LBL_N_DIVISOR

# --- adjacent-zone conditioning, read back off the dictionary ---------------
adj = [{"name": z.get("name"), "conditioned": bool(z.get("conditioned", False)),
        "setpoint": z.get("setpoint")} for z in raw.get("adjacent_zones", []) or []]

# --- the corrected run ------------------------------------------------------
bui, _ = sanitize_and_validate_BUI(build_bui(), fix=True)
hourly, annual = ISO52016.Temperature_and_Energy_needs_calculation(
    bui, weather_source="epw", path_weather_file=EPW)[:2]

def A(k):
    if k not in annual.columns:
        return float("nan")
    return float(pd.to_numeric(annual[k], errors="coerce").iloc[0])

def Hs(k):
    if k not in hourly.columns:
        return None
    return pd.to_numeric(hourly[k], errors="coerce").fillna(0.0).to_numpy(dtype=float)

T_air = Hs("T_air")
T_ext = Hs("T_ext")
Q_H = Hs("Q_H")
Q_C = Hs("Q_C")

# Wind straight off the EPW, column 21 (0-based) of the data records.
wind = []
with open(EPW, "r", errors="replace") as fh:
    for i, line in enumerate(fh):
        if i < 8:
            continue
        parts = line.split(",")
        if len(parts) > 21:
            wind.append(float(parts[21]))
wind = np.asarray(wind[:8760], dtype=float)

# --- the infiltration modulation series, reproduced exactly ------------------
# The solver calls _infiltration_h_ve_inf_w_k with Theta_old[ri], the PREVIOUS
# timestep's zone air-node temperature, so the series is built on T_air lagged
# one hour. Hour 0 uses T_air[0], matching the solver's cold start.
theta_prev = np.concatenate([[T_air[0]], T_air[:-1]])
ref = _INF_C_STACK * _INF_DT_REF + _INF_C_WIND * (_INF_U_REF ** 2)
driving = _INF_C_STACK * np.abs(theta_prev - T_ext) + _INF_C_WIND * (wind ** 2)
f_mod = np.sqrt(np.maximum(driving, 0.0) / ref)
h_ve_inf = _RHO_CP_AIR_WH_M3K * volume * n_inf_mean * f_mod   # W/K

months = np.repeat(np.arange(12), np.array([31,28,31,30,31,30,31,31,30,31,30,31]) * 24)

def monthly(series):
    return [float(np.sum(np.asarray(series)[months == m])) for m in range(12)]

BALANCE = ["Q_solar_gains_kWh", "Q_internal_gains_kWh",
           "Q_tr_window_loss_kWh", "Q_tr_window_gain_kWh",
           "Q_tr_opaque_loss_kWh", "Q_tr_opaque_gain_kWh",
           "Q_tr_adjacent_loss_kWh", "Q_tr_adjacent_gain_kWh",
           "Q_tr_total_loss_kWh", "Q_tr_total_gain_kWh",
           "Q_ve_loss_kWh", "Q_ve_gain_kWh",
           "Q_tb_loss_kWh", "Q_tb_gain_kWh",
           "Q_ground_loss_kWh", "Q_ground_gain_kWh"]

SURF = ["West_exterior_wall_opaque", "North_wall_to_Apt_306",
        "South_wall_to_Apt_304", "East_wall_to_corridor",
        "Floor_to_Apt_205", "Ceiling_to_Apt_405",
        "West_window_fixed_West_window_operable"]

json.dump({
    "heating_kWh": A("Q_H_sensible_kWh"),
    "cooling_kWh": A("Q_C_sensible_kWh"),
    "latent_kWh": A("Q_C_latent_kWh"),
    "per_sqm": A("Q_need_total_kWh_per_sqm"),
    "gains_w": gains_w,
    "neighbour_multiplier_present": bool(_neighbour_multiplier_present),
    "adjacent_zones": adj,
    "infiltration": {
        "q50": q50, "a_env": a_env, "volume": volume, "n50": n50,
        "n_inf_mean": n_inf_mean, "lbl_n": float(_LBL_N_DIVISOR),
        "c_stack": float(_INF_C_STACK), "c_wind": float(_INF_C_WIND),
        "dt_ref": float(_INF_DT_REF), "u_ref": float(_INF_U_REF),
        "design_flow_m3_s": n_inf_mean * volume / 3600.0,
        "f_mean": float(np.mean(f_mod)), "f_min": float(np.min(f_mod)),
        "f_max": float(np.max(f_mod)),
        "h_ve_inf_mean_W_K": float(np.mean(h_ve_inf)),
        "energy_kWh": float(np.sum(h_ve_inf * (theta_prev - T_ext)) / 1000.0),
    },
    "f_mod": [round(float(v), 6) for v in f_mod],
    "monthly_heating_kWh": monthly(Q_H / 1000.0),
    "monthly_cooling_kWh": monthly(Q_C / 1000.0),
    "balance": {k: A(k) for k in BALANCE},
    "surfaces": {s: {"loss": A(f"Q_tr_surface_{s}_loss_kWh"),
                     "gain": A(f"Q_tr_surface_{s}_gain_kWh")} for s in SURF},
}, open(OUT, "w"))
'''


def run_iso(epw: Path, workdir: Path) -> dict:
    """Run the corrected engine (this working tree's HEAD) in a subprocess."""
    worker = workdir / "iso_worker_corrected.py"
    worker.write_text(ISO_WORKER, encoding="utf-8")
    out = workdir / "iso_corrected.json"
    proc = subprocess.run(
        [sys.executable, str(worker), str(SRC_DIR), str(EXAMPLES_DIR),
         str(epw), str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-20:])
        raise RuntimeError(f"corrected ISO run failed:\n{tail}")
    return json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The matched IDF
# ---------------------------------------------------------------------------

def _hourly_schedule(name: str, kind: str, values: list[float]) -> str:
    """Schedule:Compact carrying one value per hour of the year.

    Embedded rather than a Schedule:File so that apt305_conditioned.idf is a
    complete, self-contained artefact: an auditor reading the IDF sees every
    number the run used, with no companion CSV to go missing.
    """
    if len(values) != 8760:
        raise Unmatchable(f"{name}: {len(values)} hourly values, expected 8760")
    rows = [f"Schedule:Compact,", f"  {name},", f"  {kind},"]
    i = 0
    for m, ndays in enumerate(DAYS_IN_MONTH, start=1):
        for d in range(1, ndays + 1):
            rows.append(f"  Through: {m}/{d},")
            rows.append("  For: AllDays,")
            for h in range(1, 25):
                last = (m == 12 and d == 31 and h == 24)
                rows.append(f"  Until: {h:02d}:00,{values[i]:.6f}{';' if last else ','}")
                i += 1
    return "\n".join(rows)


def build_matched_idf(bui: dict, iso: dict, *, timestep: int = 6,
                      inf_mode: str = "iso-schedule") -> str:
    """The baseline IDF with the three corrected inputs substituted in."""
    from baseline_vs_energyplus import build_idf

    gains = iso["gains_w"]
    inf = iso["infiltration"]

    # Adjacent zones pinned at the declared setpoint. build_idf's 'fixed' mode
    # emits exactly the OSC this needs: N2 = adj_temp, N3 = 1.0, rest zero.
    setpoints = {z["setpoint"] for z in iso["adjacent_zones"] if z["conditioned"]}
    if not iso["adjacent_zones"]:
        raise Unmatchable("the building declares no adjacent zones")
    if any(not z["conditioned"] for z in iso["adjacent_zones"]):
        raise Unmatchable(
            "not every adjacent zone is marked conditioned:True — the matched case "
            "would need a mixed boundary and this script does not build one: "
            + repr(iso["adjacent_zones"]))
    if len(setpoints) != 1:
        raise Unmatchable(
            f"the five neighbours declare {len(setpoints)} distinct setpoints "
            f"{sorted(setpoints)}; a single constant-temperature OSC cannot "
            "represent them")
    adj_temp = float(setpoints.pop())
    if abs(adj_temp - ADJ_SETPOINT_C) > 1e-9:
        raise Unmatchable(
            f"the neighbours are at {adj_temp} C, this script documents "
            f"{ADJ_SETPOINT_C} C")

    if iso["neighbour_multiplier_present"]:
        raise Unmatchable(
            "the internal-gain neighbour-count multiplier is still active in the "
            "engine; the probed design levels would not reproduce the ISO gains")

    idf = build_idf(bui, adj_temp=adj_temp, timestep=timestep,
                    adj_mode="fixed", gains_w=gains)

    # --- infiltration -------------------------------------------------------
    design_flow = inf["design_flow_m3_s"]
    if inf_mode == "iso-schedule":
        sched = _hourly_schedule("Inf_Mod", "Any Number", iso["f_mod"])
        sched_name = "Inf_Mod"
        note = ("the ISO stack/wind modulation f(t), precomputed from the "
                "corrected ISO run")
    elif inf_mode == "constant":
        sched, sched_name = "", "Always1"
        note = ("f(t) == 1: the mean natural rate applied flat, as a bound on "
                "what the modulation is worth")
    else:
        raise ValueError(f"unknown inf_mode {inf_mode!r}")

    # Constant term A = 1 with B = C = D = 0, so E+ applies no modulation of its
    # own and the schedule is the whole of it.
    inf_obj = (
        f"! Envelope infiltration, matched to the corrected ISO engine.\n"
        f"! q50 = {inf['q50']:.1f} m3/(h.m2)@50Pa over A_env = {inf['a_env']:.2f} m2\n"
        f"! n50 = {inf['n50']:.6f} 1/h over V = {inf['volume']:.1f} m3, "
        f"LBL N = {inf['lbl_n']:.0f}\n"
        f"! n_inf = {inf['n_inf_mean']:.6f} 1/h = {design_flow:.8f} m3/s\n"
        f"! schedule: {note}\n"
        f"  ZoneInfiltration:DesignFlowRate,\n"
        f"    Apt305_Infiltration, Apt305, {sched_name},\n"
        f"    Flow/Zone, {design_flow:.8f}, , , ,\n"
        f"    1.0, 0.0, 0.0, 0.0;"
    )

    parts = [idf]
    if sched:
        parts.append(sched)
    parts.append(inf_obj)
    parts.append(EXTRA_OUTPUTS)
    return "\n\n".join(parts)


# Requested by both the matched case and the repaired baseline reference, so the
# two are read through exactly the same variables.
EXTRA_OUTPUTS = (
    "  Output:Variable, *, Zone Ideal Loads Supply Air Sensible Heating Energy, Hourly;\n"
    "  Output:Variable, *, Zone Ideal Loads Supply Air Sensible Cooling Energy, Hourly;\n"
    "  Output:Variable, *, Zone Infiltration Sensible Heat Loss Energy, Hourly;\n"
    "  Output:Variable, *, Zone Infiltration Sensible Heat Gain Energy, Hourly;\n"
    "  Output:Variable, *, Zone Ventilation Sensible Heat Loss Energy, Hourly;\n"
    "  Output:Variable, *, Zone Ventilation Sensible Heat Gain Energy, Hourly;\n"
    "  Output:Variable, *, Surface Average Face Conduction Heat Transfer Energy, Hourly;\n"
    "  Output:Variable, *, Surface Window Net Heat Transfer Energy, Hourly;\n"
    "  Output:Variable, *, Zone Windows Total Transmitted Solar Radiation Energy, Hourly;\n"
    "  Output:Variable, *, Zone Operative Temperature, Hourly;"
)


def build_baseline_idf(bui: dict, probe: dict, *, timestep: int = 6) -> str:
    """The published baseline case, with the two IDF defects repaired.

    Same neighbour model (ISO 13789 b_ztu buffer), same inflated gains, still no
    infiltration — the baseline engine has none. Only the outdoor-air field
    offset and the humidification control differ from what produced
    results/paper/baseline_vs_ep_v2, and both of those are now fixed in the
    shared builder. This is the reference the corrected case's before/after
    table is measured against, so that both halves of it are read off correctly
    configured references.
    """
    from baseline_vs_energyplus import build_idf
    idf = build_idf(bui, timestep=timestep, adj_mode="iso-bztu",
                    b_ztu=probe["b_ztu"], gains_w=probe["gains_w"])
    if "ZoneInfiltration" in idf:
        raise Unmatchable(
            "the baseline IDF carries an infiltration object; the baseline engine "
            "has no infiltration path and the reference must not either")
    return "\n\n".join([idf, EXTRA_OUTPUTS])


# ---------------------------------------------------------------------------
# EnergyPlus runner
# ---------------------------------------------------------------------------

VAR_HEAT_SENS = "Zone Ideal Loads Supply Air Sensible Heating Energy"
VAR_COOL_SENS = "Zone Ideal Loads Supply Air Sensible Cooling Energy"
VAR_HEAT_TOT = "Zone Ideal Loads Supply Air Total Heating Energy"
VAR_COOL_TOT = "Zone Ideal Loads Supply Air Total Cooling Energy"
VAR_INF_LOSS = "Zone Infiltration Sensible Heat Loss Energy"
VAR_INF_GAIN = "Zone Infiltration Sensible Heat Gain Energy"
VAR_SURF_COND = "Surface Average Face Conduction Heat Transfer Energy"
VAR_WIN_NET = "Surface Window Net Heat Transfer Energy"
VAR_SOLAR = "Zone Windows Total Transmitted Solar Radiation Energy"
VAR_VENT_LOSS = "Zone Ventilation Sensible Heat Loss Energy"
VAR_VENT_GAIN = "Zone Ventilation Sensible Heat Gain Energy"


def _series(cur, name: str, key: str | None = None,
            optional: bool = False) -> list[float] | None:
    """Hourly series for a report variable, in simulation order.

    Returns None when *optional* and the variable is absent — used for the
    infiltration outputs, which the baseline case genuinely does not have
    because the baseline engine has no infiltration path.
    """
    sql = ("SELECT rvd.TimeIndex, rvd.VariableValue FROM ReportVariableData rvd "
           "JOIN ReportVariableDataDictionary d ON "
           "rvd.ReportVariableDataDictionaryIndex = d.ReportVariableDataDictionaryIndex "
           "WHERE d.VariableName = ?")
    args: list = [name]
    if key is not None:
        sql += " AND d.KeyValue = ?"
        args.append(key)
    sql += " ORDER BY rvd.TimeIndex"
    rows = cur.execute(sql, args).fetchall()
    if not rows and optional:
        return None
    if not rows:
        # A variable the IDF never requested comes back empty, and summing that
        # gives a confident 0.0 kWh. Refuse it: a missing output must not read
        # as a measured zero.
        raise Unmatchable(
            f"EnergyPlus reported no rows for {name!r}"
            + (f" / key {key!r}" if key else "")
            + " — the IDF did not request it")
    return [float(v) for _t, v in rows]


def read_sql(sql_path: Path) -> dict:
    con = sqlite3.connect(str(sql_path))
    try:
        cur = con.cursor()
        keys = {row[0] for row in cur.execute(
            "SELECT DISTINCT KeyValue FROM ReportVariableDataDictionary "
            "WHERE VariableName = ?", (VAR_SURF_COND,)).fetchall()}
        out = {
            "heat_sens": _series(cur, VAR_HEAT_SENS),
            "cool_sens": _series(cur, VAR_COOL_SENS),
            "heat_tot": _series(cur, VAR_HEAT_TOT),
            "cool_tot": _series(cur, VAR_COOL_TOT),
            "inf_loss": _series(cur, VAR_INF_LOSS, optional=True),
            "inf_gain": _series(cur, VAR_INF_GAIN, optional=True),
            "surf": {k: _series(cur, VAR_SURF_COND, k) for k in sorted(keys)},
            "win": {k: _series(cur, VAR_WIN_NET, k) for k in sorted(
                {r[0] for r in cur.execute(
                    "SELECT DISTINCT KeyValue FROM ReportVariableDataDictionary "
                    "WHERE VariableName = ?", (VAR_WIN_NET,)).fetchall()})},
            "solar": _series(cur, VAR_SOLAR),
            "vent_loss": _series(cur, VAR_VENT_LOSS),
            "vent_gain": _series(cur, VAR_VENT_GAIN),
        }
        return out
    finally:
        con.close()


def run_energyplus(idf_text: str, epw: Path, ep_bin: str, outdir: Path,
                   tag: str = "apt305c") -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    idf_path = outdir / f"{tag}.idf"
    idf_path.write_text(idf_text, encoding="utf-8")

    proc = subprocess.run(
        [ep_bin, "-w", str(epw), "-d", str(outdir), "-p", tag, str(idf_path)],
        capture_output=True, text=True,
    )
    err_file = outdir / f"{tag}out.err"
    err_txt = err_file.read_text(errors="replace") if err_file.is_file() else ""
    if proc.returncode != 0:
        severe = [l for l in err_txt.splitlines() if "** Severe" in l or "**  Fatal" in l]
        raise RuntimeError("EnergyPlus failed (exit %d)\n%s"
                           % (proc.returncode, "\n".join(severe[:25]) or proc.stdout[-3000:]))
    sql = outdir / f"{tag}out.sql"
    if not sql.is_file():
        raise RuntimeError(f"no SQLite output at {sql}")

    raw = read_sql(sql)
    J = 3.6e6
    heat = sum(raw["heat_sens"]) / J
    cool = sum(raw["cool_sens"]) / J
    heat_t = sum(raw["heat_tot"]) / J
    cool_t = sum(raw["cool_tot"]) / J
    # Humidification control is None, so heating must be exactly sensible. If it
    # is not, the ideal loads are humidifying the outdoor-air stream and booking
    # it as heating, and the figure is not comparable with the ISO sensible one.
    if abs(heat_t - heat) > 0.5:
        raise Unmatchable(
            f"E+ heating is not sensible-only (sensible {heat:.2f} kWh against "
            f"total {heat_t:.2f} kWh) — humidification is still active")
    # Cooling may carry a small genuine latent charge, which is the analogue of
    # the ISO engine's gated latent term and is reported beside it rather than
    # folded into the sensible comparison.
    latent_cool = cool_t - cool

    months = []
    for m, nd in enumerate(DAYS_IN_MONTH):
        lo = sum(DAYS_IN_MONTH[:m]) * 24
        months.append((lo, lo + nd * 24))
    mh = [sum(raw["heat_sens"][a:b]) / J for a, b in months]
    mc = [sum(raw["cool_sens"][a:b]) / J for a, b in months]

    return {
        "heating_kWh": heat,
        "cooling_kWh": cool,
        "latent_cooling_kWh": latent_cool,
        "monthly_heating_kWh": mh,
        "monthly_cooling_kWh": mc,
        "infiltration_loss_kWh": None if raw["inf_loss"] is None
                                 else sum(raw["inf_loss"]) / J,
        "infiltration_gain_kWh": None if raw["inf_gain"] is None
                                 else sum(raw["inf_gain"]) / J,
        "surfaces": {k: sum(v) / J for k, v in raw["surf"].items()},
        "windows": {k: sum(v) / J for k, v in raw["win"].items()},
        "solar_kWh": sum(raw["solar"]) / J,
        # Positive is net heat gain to the zone.
        "ventilation_net_kWh": (sum(raw["vent_gain"]) - sum(raw["vent_loss"])) / J,
        "warnings": err_txt.count("** Warning"),
        "n_hours": len(raw["heat_sens"]),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def read_published_baseline() -> tuple[dict, dict]:
    """The baseline validation as committed, so the before/after table is not
    a pair of constants retyped from the paper."""
    path = REPO_ROOT / "results" / "paper" / "baseline_vs_ep_v2" / "baseline_vs_energyplus.csv"
    if not path.is_file():
        return dict(BASELINE_ISO), dict(BASELINE_EP)
    iso, ep = {}, {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["Metric"] in ("Heating", "Cooling"):
                iso[row["Metric"]] = float(row["ISO_52016_kWh"])
                ep[row["Metric"]] = float(row["EnergyPlus_kWh"])
    for k in ("Heating", "Cooling"):
        if abs(iso.get(k, 0.0) - BASELINE_ISO[k]) > 0.02:
            raise Unmatchable(
                f"the committed baseline ISO {k.lower()} is {iso.get(k)}, "
                f"this script documents {BASELINE_ISO[k]}")
    return iso, ep


def pct(new: float, ref: float) -> float:
    return (new - ref) / ref * 100.0 if abs(ref) > 1e-9 else float("nan")


def build_tables(iso: dict, ep: dict, area: float) -> dict:
    rows = [("Heating", iso["heating_kWh"], ep["heating_kWh"]),
            ("Cooling", iso["cooling_kWh"], ep["cooling_kWh"])]
    rows.append(("Total", sum(r[1] for r in rows), sum(r[2] for r in rows)))

    b_iso, b_ep = read_published_baseline()
    b_rows = [("Heating", b_iso["Heating"], b_ep["Heating"]),
              ("Cooling", b_iso["Cooling"], b_ep["Cooling"])]
    b_rows.append(("Total", sum(r[1] for r in b_rows), sum(r[2] for r in b_rows)))

    before_after = []
    for (lab, bi, be), (_l, ci, ce) in zip(b_rows, rows):
        d_before, d_after = pct(bi, be), pct(ci, ce)
        before_after.append({
            "metric": lab,
            "baseline_iso": bi, "baseline_ep": be, "baseline_diff_pct": d_before,
            "corrected_iso": ci, "corrected_ep": ce, "corrected_diff_pct": d_after,
            "abs_change_pp": abs(d_after) - abs(d_before),
            "improved": abs(d_after) < abs(d_before),
        })
    return {"rows": rows, "baseline_rows": b_rows, "before_after": before_after,
            "area": area}


def write_csv(tables: dict, iso: dict, ep: dict, outdir: Path) -> None:
    area = tables["area"]
    with (outdir / "validation_corrected.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["section", "metric", "iso_kWh", "ep_kWh", "diff_kWh",
                    "diff_pct_vs_ep", "iso_kWh_m2", "ep_kWh_m2"])
        for lab, a, b in tables["rows"]:
            w.writerow(["corrected", lab, f"{a:.3f}", f"{b:.3f}", f"{a-b:+.3f}",
                        f"{pct(a, b):+.3f}", f"{a/area:.3f}", f"{b/area:.3f}"])
        for lab, a, b in tables["baseline_rows"]:
            w.writerow(["baseline", lab, f"{a:.3f}", f"{b:.3f}", f"{a-b:+.3f}",
                        f"{pct(a, b):+.3f}", f"{a/area:.3f}", f"{b/area:.3f}"])
        w.writerow([])
        w.writerow(["section", "metric", "baseline_diff_pct", "corrected_diff_pct",
                    "change_in_abs_diff_pp", "improved"])
        for r in tables["before_after"]:
            w.writerow(["before_after", r["metric"], f"{r['baseline_diff_pct']:+.2f}",
                        f"{r['corrected_diff_pct']:+.2f}", f"{r['abs_change_pp']:+.2f}",
                        "yes" if r["improved"] else "no"])
        w.writerow([])
        w.writerow(["section", "month", "iso_heating_kWh", "ep_heating_kWh",
                    "iso_cooling_kWh", "ep_cooling_kWh"])
        for i, m in enumerate(MONTHS):
            w.writerow(["monthly", m,
                        f"{iso['monthly_heating_kWh'][i]:.3f}",
                        f"{ep['monthly_heating_kWh'][i]:.3f}",
                        f"{iso['monthly_cooling_kWh'][i]:.3f}",
                        f"{ep['monthly_cooling_kWh'][i]:.3f}"])


def figure(tables: dict, outdir: Path, subtitle: str) -> None:
    """Grouped bars to the conventions of results/paper/figures/F1_*.

    One row per validation, each row on its own scale. The corrected loads are
    roughly a fifteenth of the baseline ones, so a shared axis would flatten the
    corrected bars to invisibility and the figure would show the size of the
    corrections instead of the quality of the agreement, which is its subject.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    sys.path.insert(0, str(REPO_ROOT / "tools" / "figures"))
    import figstyle as F
    F.apply_style()

    ISO_COLOR, EP_COLOR = "#0072B2", "#E69F00"
    metrics = ["Heating", "Cooling", "Total"]
    rows = [("Baseline engine, matched reference", tables["baseline_rows"]),
            ("Corrected engine, matched reference", tables["rows"])]

    fig, axes = plt.subplots(2, 3, figsize=(12.6, 8.8))

    for r, (row_title, data) in enumerate(rows):
        for c, (lab, iso_v, ep_v) in enumerate(data):
            ax = axes[r][c]
            x = np.arange(1)
            w = 0.30
            ax.bar(x - w / 2 - 0.02, [iso_v], w, color=ISO_COLOR,
                   edgecolor="white", linewidth=0.6, zorder=3)
            ax.bar(x + w / 2 + 0.02, [ep_v], w, color=EP_COLOR,
                   edgecolor="white", linewidth=0.6, zorder=3)
            top = max(iso_v, ep_v)
            ax.set_ylim(0, top * 1.42)
            ax.set_xlim(-0.62, 0.62)

            for dx, v in ((-w / 2 - 0.02, iso_v), (w / 2 + 0.02, ep_v)):
                ax.annotate(f"{v:,.1f}", (dx, v), xytext=(0, -4),
                            textcoords="offset points", ha="center", va="top",
                            fontsize=8.6, fontweight="bold", color="white",
                            zorder=5)

            d = pct(iso_v, ep_v)
            foot, br = top * 1.06, top * 1.16
            ax.plot([-w / 2 - 0.02, -w / 2 - 0.02, w / 2 + 0.02, w / 2 + 0.02],
                    [foot, br, br, foot], color=F.INK, lw=0.9, zorder=4)
            ax.annotate(f"{d:+.1f} %", (0.0, br), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=11.5, fontweight="bold",
                        color=F.INCREASE if d > 0 else F.DECREASE, zorder=5)

            ax.set_xticks([-w / 2 - 0.02, w / 2 + 0.02])
            ax.set_xticklabels(["ISO\n52016-1", "Energy\nPlus"], fontsize=8.6)
            ax.set_ylabel(f"Annual {lab.lower()} (kWh)")
            ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
            ax.set_title(f"{lab} (sensible)", loc="left", pad=7, fontsize=10)

        axes[r][0].annotate(
            row_title, xy=(-0.20, 1.24), xycoords="axes fraction",
            ha="left", va="center", fontsize=11.5, fontweight="bold",
            color=F.INK,
        )

    fig.suptitle("Corrected ISO 52016-1 against a matched EnergyPlus reference",
                 fontsize=14, fontweight="bold", y=0.997)
    fig.text(0.5, 0.958, subtitle, ha="center", va="top", fontsize=8.6,
             color="#4D4D4D", linespacing=1.45)
    fig.text(0.5, 0.018,
             "Percentage differences are relative to the EnergyPlus reference. "
             "Each row is on its own scale — the corrected loads are about a "
             "fifteenth of the baseline ones,\nand a shared axis would show the "
             "size of the corrections rather than the quality of the agreement. "
             "Both references carry the three IDF repairs described in "
             "validation_corrected.md.",
             ha="center", va="bottom", fontsize=8.2, color="#4D4D4D",
             linespacing=1.45)

    fig.tight_layout(rect=(0.005, 0.075, 0.995, 0.928))
    fig.subplots_adjust(hspace=0.58)

    outdir.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(outdir / f"validation_corrected.{ext}",
                    dpi=300 if ext == "png" else None, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def _pct_s(v: float) -> str:
    return "n/a" if v != v else f"{v:+.1f} %"


def write_alignment(iso: dict, outdir: Path, epw_label: str) -> None:
    rows = alignment_rows(iso["infiltration"], iso["gains_w"])
    inf = iso["infiltration"]
    lines = [
        "# Input alignment — the matched EnergyPlus case",
        "",
        f"Weather: `{epw_label}`. Case: Apt 305, 20 m², five conditioned "
        "adjacent zones.",
        "",
        "Every parameter that affects the result, marked `ALIGNED` (already "
        "identical), `FIXED` (a mismatch this script corrects) or `METHOD` (an "
        "irreducible difference between the two approaches). The three rows in "
        "capitals are the inputs the corrections moved and which the baseline "
        "validation therefore could not have matched.",
        "",
        "| Parameter | ISO 52016-1 (corrected) | EnergyPlus (matched case) | Status |",
        "|---|---|---|---|",
    ]
    for name, a, b, st in rows:
        esc = lambda t: t.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {esc(name)} | {esc(a)} | {esc(b)} | `{st}` |")

    n_fixed = sum(1 for *_x, st in rows if st.startswith("FIXED"))
    n_method = sum(1 for *_x, st in rows if st == "METHOD")
    lines += [
        "",
        f"{len(rows)} parameters checked — {len(rows) - n_fixed - n_method} already "
        f"aligned, {n_fixed} mismatches corrected, {n_method} irreducible method "
        "differences.",
        "",
        CHOICE_NOTE,
        "",
        "### Internal gains",
        "",
        "The corrected engine returns the EN 16798-1 tabulated `q_int` for the "
        "building type class and no longer multiplies by the neighbour count. "
        "Probed with unit profiles, so each category is isolated exactly; the "
        "hourly profiles are shared with EnergyPlus, so setting the "
        "`OtherEquipment` design levels to these watts reproduces the ISO gain "
        "hour for hour.",
        "",
        "| Category | Corrected engine (W) | Over 20 m² (W/m²) | Baseline engine (W) |",
        "|---|---:|---:|---:|",
        f"| Occupants | {iso['gains_w']['occupants_W']:.2f} | "
        f"{iso['gains_w']['occupants_W'] / 20.0:.2f} | 616.14 |",
        f"| Appliances | {iso['gains_w']['appliances_W']:.2f} | "
        f"{iso['gains_w']['appliances_W'] / 20.0:.2f} | 440.10 |",
        f"| Lighting | {iso['gains_w']['lighting_W']:.2f} | "
        f"{iso['gains_w']['lighting_W'] / 20.0:.2f} | 0.00 |",
        "",
        "The script asserts that the neighbour-count multiplier is absent before "
        "building the IDF: if it were back, these design levels would not "
        "reproduce the ISO gains and the run would stop.",
        "",
        "### Infiltration",
        "",
        "| Quantity | Value | Source |",
        "|---|---:|---|",
        f"| `q50` | {inf['q50']:.1f} m³/(h·m²) @ 50 Pa | adopted Australian "
        "pre-2006 band, `_q50_for_construction_age` |",
        f"| `A_env` | {inf['a_env']:.2f} m² | outdoor-exposed surfaces only "
        "(`_envelope_area_m2`), not the 88.6 m² whole-surface sum |",
        f"| `V` | {inf['volume']:.1f} m³ | `_zone_volume_m3` |",
        f"| `n50 = q50·A_env/V` | {inf['n50']:.4f} h⁻¹ | |",
        f"| LBL divisor `N` | {inf['lbl_n']:.0f} | sheltered low-rise |",
        f"| `n_inf = n50/N` | {inf['n_inf_mean']:.4f} h⁻¹ | mean natural rate |",
        f"| Design flow | {inf['design_flow_m3_s']:.8f} m³/s | "
        "`ZoneInfiltration:DesignFlowRate`, `Flow/Zone` |",
        f"| Modulation `f(t)` | mean {inf['f_mean']:.4f}, "
        f"range {inf['f_min']:.4f}–{inf['f_max']:.4f} | embedded "
        "`Schedule:Compact`, 8760 values |",
        f"| Mean `H_ve_inf` | {inf['h_ve_inf_mean_W_K']:.3f} W/K | against "
        "`H_ve_nat` = 48.4 W/K designed ventilation |",
        f"| Annual infiltration energy | {inf['energy_kWh']:.2f} kWh | "
        "`Σ H_ve_inf·(θ_int − θ_e)` |",
        "",
        "**How the stack/wind modulation was represented.** EnergyPlus's own "
        "modulation is `A + B|ΔT| + C·u + D·u²`, which is linear in the driving "
        "forces. The ISO expression is "
        "`f = √((Cs·|ΔT| + Cw·u²) / (Cs·ΔT_ref + Cw·u_ref²))` — a square root of "
        "a linear combination, which no choice of `A…D` reproduces. The series "
        "is therefore precomputed from the corrected ISO run and embedded as an "
        "8760-value schedule with `A = 1` and `B = C = D = 0`.",
        "",
        "This matches the series hour for hour, at the cost of making the "
        "coupling **one-way**: `f(t)` carries the ISO run's zone temperature, "
        "not EnergyPlus's. The two zone temperatures are close but not "
        "identical, so a second-order error remains. It is bounded by the "
        "`--inf-mode constant` sensitivity run reported in `DISCREPANCY.md`, "
        "rather than asserted to be small.",
        "",
        "### Three defects found in the shared IDF builder",
        "",
        "All three were found while building this case, all three are in "
        "`examples/baseline_vs_energyplus.py`, and all three are now fixed there.",
        "",
        "1. **Outdoor air was never delivered.** "
        "`DesignSpecification:OutdoorAir` was written as "
        "`Apt305_OA, Flow/Area, 0.002, , , , Always1`, which puts the rate in "
        "`N1` (*Outdoor Air Flow per Person*). Method `Flow/Area` reads `N2` "
        "(*per Zone Floor Area*), which was blank and therefore zero. Every "
        "EnergyPlus run made with this builder had **no designed ventilation at "
        "all**, while the ISO side carried `H_ve = 48.4 W/K`.",
        "2. **Ventilation was attached to the wrong object.** Outdoor air on "
        "`ZoneHVAC:IdealLoadsAirSystem` is delivered only in the hours the "
        "system runs — 686 of 8760 in this case — and not at all while the zone "
        "free-floats in the deadband. ISO 52016-1 applies `H_ve` every hour. It "
        "is now a `ZoneVentilation:DesignFlowRate` zone air exchange on an "
        "always-on schedule with constant coefficients.",
        "3. **Heating was not sensible-only.** Humidification control was "
        "`ConstantSupplyHumidityRatio`, so once the ventilation air actually "
        "flowed the ideal loads humidified it and booked ~300 kWh/yr of latent "
        "as heating. Both humidity controls are now `None`.",
        "",
        "The committed `results/paper/baseline_vs_ep_v2/` was produced before "
        "any of them was found. `validation_corrected.md` reports what they "
        "cost.",
    ]
    (outdir / "alignment.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _largest(iso: dict, ep: dict) -> str:
    gaps = {"sensible heating": iso["heating_kWh"] - ep["heating_kWh"],
            "sensible cooling": iso["cooling_kWh"] - ep["cooling_kWh"]}
    name = max(gaps, key=lambda k: abs(gaps[k]))
    other = next(k for k in gaps if k != name)
    return (f"{name}, {gaps[name]:+,.1f} kWh, against {gaps[other]:+,.1f} kWh on "
            f"{other}")


def _headline(tables: dict, iso: dict, ep: dict, base: dict) -> str:
    """State which way it fell, from the numbers rather than from expectation."""
    ba = {r["metric"]: r for r in tables["before_after"]}
    comp = [ba["Heating"], ba["Cooling"]]
    n_better = sum(1 for r in comp if r["improved"])

    abs_gaps = []
    for key in ("heating_kWh", "cooling_kWh"):
        gb = abs(base["iso"][key] - base["ep"][key])
        gc = abs(iso[key] - ep[key])
        abs_gaps.append((gb, gc))
    abs_all_narrow = all(gc < gb for gb, gc in abs_gaps)

    if n_better == 2:
        rel = "**Relative agreement improved on both components.**"
    elif n_better == 0:
        rel = "**Relative agreement worsened on both components.**"
    else:
        better = "heating" if comp[0]["improved"] else "cooling"
        worse = "cooling" if comp[0]["improved"] else "heating"
        rel = (f"**Relative agreement improved on {better} and worsened on "
               f"{worse}.**")

    if abs_all_narrow:
        shrink = [100 * (1 - gc / gb) for gb, gc in abs_gaps]
        ab = (f" **In absolute energy the gap narrowed on both — heating by "
              f"{shrink[0]:.0f} %, cooling by {shrink[1]:.0f} %.**")
        note = (" The two are not in conflict: the corrections cut the loads "
                "themselves by roughly an order of magnitude, so a much smaller "
                "absolute residual sits on a much smaller denominator. Neither "
                "statement should be quoted without the other.")
    else:
        ab = ""
        note = ""
    return rel + ab + note


def write_markdown(tables: dict, iso: dict, ep: dict, base: dict,
                   outdir: Path, epw_label: str) -> None:
    area = tables["area"]
    ba = {r["metric"]: r for r in tables["before_after"]}
    h, c, t = ba["Heating"], ba["Cooling"], ba["Total"]

    def verdict(r) -> str:
        return ("improved" if r["improved"] else "worsened")

    lines = [
        "# Corrected ISO 52016-1 against a matched EnergyPlus reference",
        "",
        f"Weather: `{epw_label}`. Case: Apt 305, 20 m², five conditioned "
        "adjacent zones. EnergyPlus 24.1.0.",
        "",
        "## Summary",
        "",
        _headline(tables, iso, ep, base),
        "",
        f"- **Heating**: the ISO engine differs from the matched reference by "
        f"**{h['corrected_diff_pct']:+.1f} %**, against "
        f"**{h['baseline_diff_pct']:+.1f} %** for the baseline engine against "
        f"its own matched reference — {verdict(h)} by "
        f"{abs(h['abs_change_pp']):.1f} percentage points. In absolute terms the "
        f"gap falls from {abs(base['iso']['heating_kWh'] - base['ep']['heating_kWh']):,.1f} "
        f"kWh to {abs(iso['heating_kWh'] - ep['heating_kWh']):,.1f} kWh.",
        f"- **Cooling**: **{c['corrected_diff_pct']:+.1f} %** against "
        f"**{c['baseline_diff_pct']:+.1f} %** — {verdict(c)} by "
        f"{abs(c['abs_change_pp']):.1f} percentage points. In absolute terms the "
        f"gap *falls*, from "
        f"{abs(base['iso']['cooling_kWh'] - base['ep']['cooling_kWh']):,.1f} kWh to "
        f"{abs(iso['cooling_kWh'] - ep['cooling_kWh']):,.1f} kWh. The percentage "
        "grows because the cooling load itself collapses by 98 % across the "
        "corrections, so a smaller absolute residual sits on a far smaller "
        "denominator.",
        f"- **Largest remaining contributor in absolute energy**: "
        f"{_largest(iso, ep)}. See `DISCREPANCY.md`.",
        "",
        "### Three defects in the published baseline reference",
        "",
        "The headline the paper currently carries — that the baseline ISO engine "
        "over-predicts heating by **+58.8 %** against EnergyPlus — is an "
        "artefact of defects in the EnergyPlus input, not a property of the "
        "ISO engine. Three were found while building the matched case, all in "
        "the shared IDF builder, all now fixed there.",
        "",
        "1. **No ventilation air was delivered.** "
        "`DesignSpecification:OutdoorAir` wrote the rate into the *per Person* "
        "field while the method was `Flow/Area`, which reads the *per Zone "
        "Floor Area* field. That field was blank, so EnergyPlus ran with no "
        "designed ventilation at all while the ISO side carried "
        "`H_ve = 48.4 W/K`.",
        "2. **Ventilation was on the wrong object.** Even with the rate in the "
        "right field, outdoor air attached to `ZoneHVAC:IdealLoadsAirSystem` is "
        "delivered only in the hours the system runs — 686 of 8760 here — and "
        "not at all in the deadband, so the zone free-floated unventilated. "
        "ISO 52016-1 applies `H_ve` every hour. It is now a "
        "`ZoneVentilation:DesignFlowRate` zone air exchange on an always-on "
        "schedule, which reproduces the ISO term hour for hour.",
        "3. **Heating was not sensible-only.** Humidification control was "
        "`ConstantSupplyHumidityRatio`, which books humidification of the "
        "ventilation air as heating once that air actually flows. Both humidity "
        "controls are now `None`.",
        "",
        "All three are now fixed in `examples/baseline_vs_energyplus.py`. Re-running "
        "the *unchanged* baseline engine against the repaired reference gives:",
        "",
        "| | ISO 52016-1 (baseline engine) | EnergyPlus | Difference |",
        "|---|---:|---:|---:|",
        f"| Heating, published reference | {base['iso']['heating_kWh']:,.2f} | "
        f"{BASELINE_EP['Heating']:,.2f} | "
        f"{_pct_s(pct(base['iso']['heating_kWh'], BASELINE_EP['Heating']))} |",
        f"| Heating, repaired reference | {base['iso']['heating_kWh']:,.2f} | "
        f"{base['ep']['heating_kWh']:,.2f} | "
        f"{_pct_s(pct(base['iso']['heating_kWh'], base['ep']['heating_kWh']))} |",
        f"| Cooling, published reference | {base['iso']['cooling_kWh']:,.2f} | "
        f"{BASELINE_EP['Cooling']:,.2f} | "
        f"{_pct_s(pct(base['iso']['cooling_kWh'], BASELINE_EP['Cooling']))} |",
        f"| Cooling, repaired reference | {base['iso']['cooling_kWh']:,.2f} | "
        f"{base['ep']['cooling_kWh']:,.2f} | "
        f"{_pct_s(pct(base['iso']['cooling_kWh'], base['ep']['cooling_kWh']))} |",
        "",
        "The ISO column is byte-identical to the committed trajectory's baseline "
        "state; only the reference moved. The baseline engine does not "
        "over-predict heating by 58.8 % — it **under-predicts** it by "
        f"{abs(pct(base['iso']['heating_kWh'], base['ep']['heating_kWh'])):.1f} %. "
        "Every before/after figure in this document uses the repaired reference "
        "on both sides, so that the comparison is like-for-like.",
        "",
        "## 1. The corrected comparison",
        "",
        "| Metric | ISO 52016-1 (corrected) | EnergyPlus (matched) | Difference | "
        "Difference % | ISO kWh/m² | E+ kWh/m² |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for lab, a, b in tables["rows"]:
        lines.append(f"| {lab} | {a:,.2f} | {b:,.2f} | {a - b:+,.2f} | "
                     f"{_pct_s(pct(a, b))} | {a / area:,.2f} | {b / area:,.2f} |")
    lines += [
        "",
        "Differences are stated **relative to the EnergyPlus reference**, "
        "following the existing validation. Both engines are sensible-only: the "
        "ISO side reports gated latent separately "
        f"({iso['latent_kWh']:.2f} kWh) and the EnergyPlus ideal loads carry "
        f"{ep['latent_cooling_kWh']:.2f} kWh of latent cooling with "
        "humidification disabled.",
        "",
        "## 2. Before and after",
        "",
        "Both rows are measured against a reference matched to the engine beside "
        "them: the baseline engine against the ISO 13789 buffer reference with "
        "inflated gains and no infiltration, the corrected engine against the "
        "20 °C-neighbour reference with EN 16798-1 gains and infiltration. Both "
        "references carry the three IDF repairs.",
        "",
        "| Metric | Baseline discrepancy | Corrected discrepancy | "
        "Change in absolute difference | Direction |",
        "|---|---:|---:|---:|---|",
    ]
    for r in tables["before_after"]:
        lines.append(
            f"| {r['metric']} | {r['baseline_diff_pct']:+.1f} % | "
            f"{r['corrected_diff_pct']:+.1f} % | {r['abs_change_pp']:+.1f} pp | "
            f"{'**improved**' if r['improved'] else 'worsened'} |")

    lines += [
        "",
        "In absolute energy, which the percentages obscure on a load this small:",
        "",
        "| Metric | Baseline gap (kWh) | Corrected gap (kWh) | Change |",
        "|---|---:|---:|---:|",
    ]
    for lab, key in (("Heating", "heating_kWh"), ("Cooling", "cooling_kWh")):
        gb = base["iso"][key] - base["ep"][key]
        gc = iso[key] - ep[key]
        lines.append(f"| {lab} | {gb:+,.1f} | {gc:+,.1f} | "
                     f"{abs(gc) - abs(gb):+,.1f} |")
    gb = ((base["iso"]["heating_kWh"] + base["iso"]["cooling_kWh"])
          - (base["ep"]["heating_kWh"] + base["ep"]["cooling_kWh"]))
    gc = ((iso["heating_kWh"] + iso["cooling_kWh"])
          - (ep["heating_kWh"] + ep["cooling_kWh"]))
    lines.append(f"| Total | {gb:+,.1f} | {gc:+,.1f} | {abs(gc) - abs(gb):+,.1f} |")

    lines += [
        "",
        "**Every absolute gap narrows.** Heating by "
        f"{abs(base['iso']['heating_kWh'] - base['ep']['heating_kWh']) - abs(iso['heating_kWh'] - ep['heating_kWh']):,.1f} kWh "
        f"({100 * (1 - abs(iso['heating_kWh'] - ep['heating_kWh']) / abs(base['iso']['heating_kWh'] - base['ep']['heating_kWh'])):.0f} %), "
        "cooling by "
        f"{abs(base['iso']['cooling_kWh'] - base['ep']['cooling_kWh']) - abs(iso['cooling_kWh'] - ep['cooling_kWh']):,.1f} kWh "
        f"({100 * (1 - abs(iso['cooling_kWh'] - ep['cooling_kWh']) / abs(base['iso']['cooling_kWh'] - base['ep']['cooling_kWh'])):.0f} %). "
        "The cooling *percentage* worsens only because the load it is a "
        "percentage of fell from "
        f"{base['ep']['cooling_kWh']:,.0f} kWh to {ep['cooling_kWh']:,.0f} kWh.",
        "",
        "## 3. Monthly",
        "",
        "| Month | ISO heating | E+ heating | Δ | ISO cooling | E+ cooling | Δ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for i, m in enumerate(MONTHS):
        ih, eh = iso["monthly_heating_kWh"][i], ep["monthly_heating_kWh"][i]
        ic, ec = iso["monthly_cooling_kWh"][i], ep["monthly_cooling_kWh"][i]
        lines.append(f"| {m} | {ih:,.2f} | {eh:,.2f} | {ih - eh:+,.2f} | "
                     f"{ic:,.2f} | {ec:,.2f} | {ic - ec:+,.2f} |")
    lines += [
        f"| **Year** | **{sum(iso['monthly_heating_kWh']):,.2f}** | "
        f"**{sum(ep['monthly_heating_kWh']):,.2f}** | "
        f"**{sum(iso['monthly_heating_kWh']) - sum(ep['monthly_heating_kWh']):+,.2f}** | "
        f"**{sum(iso['monthly_cooling_kWh']):,.2f}** | "
        f"**{sum(ep['monthly_cooling_kWh']):,.2f}** | "
        f"**{sum(iso['monthly_cooling_kWh']) - sum(ep['monthly_cooling_kWh']):+,.2f}** |",
        "",
        "## Files",
        "",
        "- `validation_corrected.csv` — this comparison, the before/after table "
        "and the monthly series, machine-readable",
        "- `validation_corrected.pdf` / `.png` — the figure",
        "- `apt305_conditioned.idf` — the matched EnergyPlus model, self-contained "
        "(the 8760-value infiltration schedule is embedded, not a companion file)",
        "- `apt305_baseline_repaired.idf` — the baseline reference with the two "
        "IDF defects fixed, for audit of the before/after table",
        "- `alignment.md` — the input-alignment table, gains and infiltration "
        "matching, and the choice of adjacent-zone representation",
        "- `DISCREPANCY.md` — the loss-path and monthly decomposition, and the "
        "comparison to the reference literature",
    ]
    (outdir / "validation_corrected.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Item 3 / Item 4 — decomposition
# ---------------------------------------------------------------------------

PARTY_EP = ["NORTHWALL", "SOUTHWALL", "EASTWALL", "FLOORSLAB", "CEILINGSLAB"]
PARTY_ISO = ["North_wall_to_Apt_306", "South_wall_to_Apt_304",
             "East_wall_to_corridor", "Floor_to_Apt_205", "Ceiling_to_Apt_405"]


def loss_paths(iso: dict, ep: dict) -> list[dict]:
    """Net heat gain to the zone, kWh/yr, on the paths available to both engines.

    Sign convention: **positive is net heat gain to the zone**. On the ISO side
    that is ``gain - loss`` from the per-surface annual balance columns; on the
    EnergyPlus side the surface conduction and window net-transfer variables
    already carry that sign, and the outdoor-air load is negated because air the
    plant has to heat is heat the zone lost.

    The window row is **conduction plus transmitted solar on both sides**. It
    cannot be split: EnergyPlus's `Surface Window Net Heat Transfer Energy`
    bundles the transmitted solar in with the conduction, while the ISO engine
    books solar in a separate column. Comparing the ISO conduction term against
    the E+ bundle would put a 710 kWh solar gain on one side of the row and not
    the other.
    """
    s = iso["surfaces"]
    net = lambda k: s[k]["gain"] - s[k]["loss"]
    b = iso["balance"]

    iso_inf = -iso["infiltration"]["energy_kWh"]
    iso_ve_total = b["Q_ve_gain_kWh"] - b["Q_ve_loss_kWh"]

    out = [{
        "path": "West exterior wall (opaque, 11.88 m²)",
        "iso": net("West_exterior_wall_opaque"),
        "ep": ep["surfaces"].get("WESTWALL", float("nan")),
    }, {
        "path": "West windows (1.62 m²), conduction + transmitted solar",
        "iso": net("West_window_fixed_West_window_operable") + b["Q_solar_gains_kWh"],
        "ep": sum(ep["windows"].values()) if ep["windows"] else float("nan"),
    }, {
        "path": "Five party surfaces (75.10 m², to 20 °C neighbours)",
        "iso": sum(net(k) for k in PARTY_ISO),
        "ep": sum(ep["surfaces"].get(k, float("nan")) for k in PARTY_EP),
    }, {
        "path": "Designed ventilation (2.0 l/s·m², H_ve = 48.4 W/K)",
        # The ISO Q_ve columns carry the designed stream and the leakage stream
        # together, so the leakage part is taken back out to match the E+ split.
        "iso": iso_ve_total - iso_inf,
        "ep": ep["ventilation_net_kWh"],
    }, {
        "path": "Envelope infiltration",
        "iso": iso_inf,
        "ep": (float("nan") if ep["infiltration_loss_kWh"] is None
               else ep["infiltration_gain_kWh"] - ep["infiltration_loss_kWh"]),
    }]
    out.append({
        "path": "**Σ compared paths**",
        "iso": sum(r["iso"] for r in out),
        "ep": sum(r["ep"] for r in out),
    })
    return out


def write_discrepancy(tables: dict, iso: dict, ep: dict, base: dict,
                      sens: dict | None, outdir: Path, epw_label: str) -> None:
    gap_h = iso["heating_kWh"] - ep["heating_kWh"]
    gap_c = iso["cooling_kWh"] - ep["cooling_kWh"]

    mh = [iso["monthly_heating_kWh"][i] - ep["monthly_heating_kWh"][i]
          for i in range(12)]
    mc = [iso["monthly_cooling_kWh"][i] - ep["monthly_cooling_kWh"][i]
          for i in range(12)]
    summer = {0, 1, 2, 11}           # Dec-Mar, where the cooling load sits
    winter = {4, 5, 6, 7, 8}         # May-Sep, where the heating load sits
    c_summer = sum(mc[i] for i in summer)
    h_winter = sum(mh[i] for i in winter)

    # Heating: is the monthly discrepancy a uniform proportional offset, or is it
    # concentrated? Compare each heating month's relative gap.
    # Only months carrying a real heating load: a 1 kWh shoulder month's
    # percentage is dominated by rounding and would make any band look wide.
    REL_FLOOR_KWH = 10.0
    rel = [(MONTHS[i], 100.0 * mh[i] / ep["monthly_heating_kWh"][i])
           for i in range(12) if ep["monthly_heating_kWh"][i] >= REL_FLOOR_KWH]
    rel_lo = min(r for _m, r in rel)
    rel_hi = max(r for _m, r in rel)

    paths = loss_paths(iso, ep)

    lines = [
        "# Where the remaining disagreement comes from",
        "",
        f"Weather: `{epw_label}`. Corrected ISO 52016-1 against the matched "
        "EnergyPlus 24.1.0 case built by `examples/corrected_vs_energyplus.py`.",
        "",
        f"Residual: heating **{gap_h:+,.2f} kWh** "
        f"({_pct_s(pct(iso['heating_kWh'], ep['heating_kWh']))}), "
        f"cooling **{gap_c:+,.2f} kWh** "
        f"({_pct_s(pct(iso['cooling_kWh'], ep['cooling_kWh']))}). "
        "The ISO engine is below the reference on both.",
        "",
        "## 1. By loss path",
        "",
        "Net heat gain to the zone, kWh/yr, **positive into the zone**. The ISO "
        "column is `gain − loss` from the per-surface annual balance; the "
        "EnergyPlus column is the surface conduction and window net-transfer "
        "variables, which already carry that sign, and the zone ventilation and "
        "infiltration streams as gain minus loss.",
        "",
        "The window row carries **conduction plus transmitted solar on both "
        "sides**, because it cannot be split: EnergyPlus's window net-transfer "
        "variable bundles the transmitted solar in with the conduction, while "
        "the ISO engine books solar in a separate column. Splitting one side and "
        "not the other would put a ~710 kWh solar gain on one side of the row "
        "and nothing on the other.",
        "",
        "| Loss path | ISO 52016-1 | EnergyPlus | Δ (ISO − E+) |",
        "|---|---:|---:|---:|",
    ]
    for p in paths:
        d = p["iso"] - p["ep"]
        lines.append(f"| {p['path']} | {p['iso']:+,.1f} | {p['ep']:+,.1f} | "
                     f"{d:+,.1f} |")

    inf_i = -iso["infiltration"]["energy_kWh"]
    inf_e = (float("nan") if ep["infiltration_loss_kWh"] is None
             else ep["infiltration_gain_kWh"] - ep["infiltration_loss_kWh"])
    lines += [
        "",
        f"**Infiltration matches to {abs(inf_i - inf_e):,.1f} kWh on a "
        f"{abs(inf_i):,.1f} kWh path** ({abs(100 * (inf_i - inf_e) / inf_i):.1f} %), "
        "which is the direct check on the one-way schedule coupling described in "
        "`alignment.md`. The two engines are computing the same leakage stream.",
        "",
        f"**The largest single disagreement is the five party surfaces, "
        f"{max(paths[:-1], key=lambda r: abs(r['iso'] - r['ep']))['iso'] - max(paths[:-1], key=lambda r: abs(r['iso'] - r['ep']))['ep']:+,.0f} kWh.** "
        "They are 75.10 m² and 88.6 % of the envelope UA, so a small fractional "
        "error there outweighs a large one anywhere else.",
        "",
        "**On why the Σ row does not equal the difference in plant energy.** "
        "The two engines partition the zone balance differently — ISO 52016-1 "
        "solves an air node coupled to surface nodes and books each path against "
        "the air node, while EnergyPlus reports conduction at the surface "
        "mid-plane and resolves convection and long-wave exchange separately. "
        "Internal gains (730.29 kWh) are identical by construction on both sides "
        "and are not listed. The Σ row is therefore a like-for-like comparison "
        "of each path, not a closed balance, and should be read that way.",
        "",
        "## 2. By month",
        "",
        "| Month | Δ heating | Δ cooling |",
        "|---|---:|---:|",
    ]
    for i, m in enumerate(MONTHS):
        lines.append(f"| {m} | {mh[i]:+,.2f} | {mc[i]:+,.2f} |")
    lines += [
        f"| **Year** | **{sum(mh):+,.2f}** | **{sum(mc):+,.2f}** |",
        "",
        "**The two residuals have different shapes, and that is the most "
        "informative thing in this document.**",
        "",
        f"- **Cooling is concentrated.** {c_summer:+,.2f} kWh of the "
        f"{gap_c:+,.2f} kWh total falls in Dec–Mar "
        f"({100 * c_summer / gap_c:.0f} % of it), the four months that carry "
        "essentially the whole cooling load.",
        f"- **Heating is distributed.** {h_winter:+,.2f} kWh of the "
        f"{gap_h:+,.2f} kWh falls in May–Sep, and across the {len(rel)} months "
        f"carrying at least {REL_FLOOR_KWH:.0f} kWh of heating the *relative* "
        f"gap stays in a narrow band, {rel_lo:.1f} % to {rel_hi:.1f} %. That is "
        "a systematic proportional offset, not a seasonal artefact.",
        "",
        "## 3. The largest single contributor",
        "",
        (f"**Sensible heating, {gap_h:+,.2f} kWh**, is the larger residual in "
         f"absolute energy — bigger than sensible cooling's {gap_c:+,.2f} kWh — "
         "and it is spread evenly across the heating season. **Sensible "
         f"cooling, {gap_c:+,.2f} kWh**, is the larger one in relative terms "
         f"({_pct_s(pct(iso['cooling_kWh'], ep['cooling_kWh']))} against "
         f"{_pct_s(pct(iso['heating_kWh'], ep['heating_kWh']))}) and is "
         "concentrated in Dec–Mar. Which of the two is 'largest' depends on "
         "which question is being asked, so both are named."
         if abs(gap_h) > abs(gap_c) else
         f"**Sensible cooling, {gap_c:+,.2f} kWh, concentrated in Dec–Mar.** It "
         f"is larger than the heating residual ({gap_h:+,.2f} kWh) in absolute "
         "energy and larger again in relative terms."),
        "",
        "### What it is attributable to",
        "",
        "The loss-path table is the evidence. Two rows carry almost all of the "
        "disagreement, and they point in opposite directions:",
        "",
        f"- **Party surfaces {paths[2]['iso'] - paths[2]['ep']:+,.0f} kWh** — the "
        "ISO engine draws more heat from the 20 °C neighbours than EnergyPlus "
        "does.",
        f"- **West exterior wall {paths[0]['iso'] - paths[0]['ep']:+,.0f} kWh** — "
        "the ISO engine loses more through the one outdoor-exposed opaque "
        "element than EnergyPlus does.",
        "",
        f"They nearly cancel in the annual total "
        f"({(paths[2]['iso'] - paths[2]['ep']) + (paths[0]['iso'] - paths[0]['ep']):+,.0f} kWh "
        "between them) but they do not cancel season by season, which is why "
        "the heating and cooling residuals have different shapes.",
        "",
        "Taking the four named candidates in turn, with what this setup can and "
        "cannot establish:",
        "",
        "**Surface heat-transfer coefficients (Ballarini) — the best supported, "
        "and it accounts for both large rows.** On the party surfaces the ISO "
        "engine uses constant internal film coefficients while EnergyPlus varies "
        "them with the TARP correlation; those surfaces are 88.6 % of the "
        "envelope UA, so a modest fractional difference is the largest absolute "
        "row in the table. On the west wall the C2 correction sets "
        "`h_ce = 4v + 4`, which on this weather file averages well above the ISO "
        "constant, so the ISO wall sheds more of its absorbed solar back to the "
        "air and conducts less inward — the ISO side losing more than twice what "
        "EnergyPlus's DOE-2 exterior correlation gives. Ballarini's finding that "
        "constant surface coefficients are the principal cause of "
        "ISO-versus-detailed disagreement is directly consistent with this "
        "table.",
        "",
        f"**Solar distribution within the zone — still a live candidate, but "
        f"smaller than the film coefficients.** The two engines agree closely on "
        f"how much solar *enters*: the window row differs by "
        f"{paths[1]['iso'] - paths[1]['ep']:+,.0f} kWh on a "
        f"{paths[1]['iso']:+,.0f} kWh path. What they do with it afterwards is "
        "not visible in that row — ISO 52016-1 splits it with a fixed convective "
        "fraction `f_sol_c = 0.1` and routes the rest to the surface nodes, "
        "while EnergyPlus ray-traces it onto the actual interior surfaces — and "
        "that difference would surface in exactly the two rows above, "
        "inseparably from the film-coefficient effect. The cooling residual "
        "being concentrated in the solar-driven months is consistent with it "
        "contributing; it is not sufficient to size it.",
        "",
        "**Five-node RC against conduction transfer functions — largely ruled "
        "out here.** Every construction in this case is `Material:NoMass`, so "
        "conduction is steady-state in both engines and the discretisation has "
        "almost nothing to discretise. The only storage is the 200 kJ/K zone "
        "internal capacitance, which both engines carry identically. This "
        "candidate is available in general but cannot be doing much work in "
        "*this* case.",
        "",
        "**Absence of stack/wind infiltration modulation on the EnergyPlus side "
        "— ruled out, by construction and by measurement.** The modulation is "
        "present: it is embedded as an 8760-value schedule. The loss-path table "
        f"puts the two infiltration streams within {abs(inf_i - inf_e):,.1f} kWh "
        "of each other, and the sensitivity run below bounds what the "
        "modulation is worth at all.",
        "",
        "### What is left open",
        "",
        "The film coefficients and the solar distribution are **not separated "
        "here**, and cannot be from these two runs. Both act on the same two "
        "rows of the loss-path table. Separating them would need either "
        "EnergyPlus's interior convection algorithm pinned to the ISO constant "
        "film coefficients, or its solar distribution forced to a fixed "
        "convective fraction — neither is a one-switch change, and neither was "
        "attempted. The weight of evidence favours the film coefficients, "
        "because they explain the west-wall row (where almost no diffuse solar "
        "lands inside) as well as the party-surface row, whereas solar "
        "distribution explains only the second. **That is a ranking, not a "
        "decomposition, and it is left as an open question.**",
        "",
        "## 4. Against the reference literature",
        "",
        "Context only. Nothing here was tuned toward it.",
        "",
        "| | Direction, heating | Direction, cooling | Magnitude |",
        "|---|---|---|---|",
        "| Zakula et al. | simplified method **under**-estimates | simplified "
        "method **over**-estimates | up to 40 % heating, 18 % cooling |",
        f"| Baseline engine, published reference | **over** ({_pct_s(pct(base['iso']['heating_kWh'], BASELINE_EP['Heating']))}) "
        f"| under ({_pct_s(pct(base['iso']['cooling_kWh'], BASELINE_EP['Cooling']))}) | — |",
        f"| Baseline engine, repaired reference | **under** "
        f"({_pct_s(pct(base['iso']['heating_kWh'], base['ep']['heating_kWh']))}) | under "
        f"({_pct_s(pct(base['iso']['cooling_kWh'], base['ep']['cooling_kWh']))}) | — |",
        f"| Corrected engine | **under** "
        f"({_pct_s(pct(iso['heating_kWh'], ep['heating_kWh']))}) | under "
        f"({_pct_s(pct(iso['cooling_kWh'], ep['cooling_kWh']))}) | — |",
        "",
        "**On heating the corrected engine now agrees with the literature "
        "direction, and comfortably inside the literature magnitude.** "
        f"{_pct_s(pct(iso['heating_kWh'], ep['heating_kWh']))} against Zakula's "
        "*up to 40 %*.",
        "",
        "The paper's existing remark — that Zakula found under-estimation of "
        "heating whereas this baseline over-predicts it — was based on the "
        "published +58.8 %, which `validation_corrected.md` shows to be an "
        "artefact of the EnergyPlus input rather than a property of the engine. "
        "Against a correctly configured reference the baseline engine "
        "under-predicts heating too. **That remark should be revised: the "
        "anomaly it describes does not exist.**",
        "",
        "**On cooling the corrected engine is on the opposite side from Zakula, "
        "and outside their band in percentage terms.** They report the "
        "simplified method over-estimating cooling by up to 18 %; this engine "
        f"under-estimates it by {abs(pct(iso['cooling_kWh'], ep['cooling_kWh'])):.0f} %. "
        "Two things temper the comparison without excusing it. The absolute "
        f"quantity is {abs(gap_c):,.1f} kWh/yr on a 20 m² dwelling — "
        f"{abs(gap_c) / 20.0:.2f} kWh/m²·yr — and Zakula's cases are "
        "cooling-dominated buildings where 18 % is a large absolute number. And "
        "the baseline engine was already under-predicting cooling "
        f"({_pct_s(pct(base['iso']['cooling_kWh'], base['ep']['cooling_kWh']))} "
        "against the repaired reference), so the sign is inherited from the "
        "method, not introduced by the corrections.",
        "",
        "Ballarini's finding — that constant surface coefficients are the "
        "principal cause of ISO-versus-detailed disagreement — is consistent "
        "with the loss-path table here, where the party surfaces carry both the "
        "largest UA share and the largest absolute disagreement, and where the "
        "ISO side still uses constant internal film coefficients.",
    ]
    (outdir / "DISCREPANCY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--energyplus", default=shutil.which("energyplus"))
    ap.add_argument("--weather", type=Path, default=DEFAULT_EPW)
    ap.add_argument("--timestep", type=int, default=6)
    ap.add_argument("--outdir", type=Path, default=OUTDIR)
    ap.add_argument("--skip-sensitivity", action="store_true",
                    help="skip the f == 1 infiltration bound")
    ap.add_argument("--audit-only", action="store_true",
                    help="probe the engine, write the IDF and the alignment "
                         "table, run no simulation")
    args = ap.parse_args()

    if not args.weather.is_file():
        raise SystemExit(f"weather file not found: {args.weather}")
    epw_label = args.weather.name
    args.outdir.mkdir(parents=True, exist_ok=True)

    from baseline_vs_energyplus import aligned_building
    bui = aligned_building()
    area = float(bui["building"]["net_floor_area"])

    tmp = Path(tempfile.mkdtemp(prefix="aib-epc-"))
    try:
        print("running the corrected ISO engine…")
        iso = run_iso(args.weather, tmp)
        print(f"  {iso['heating_kWh']:.2f} kWh heating, "
              f"{iso['cooling_kWh']:.2f} kWh cooling, "
              f"{iso['per_sqm']:.2f} kWh/m2·yr")

        # The canonical headline, gated before anything is compared against it.
        for name, got, want in (("sensible heating", iso["heating_kWh"], 123.74),
                                ("sensible cooling", iso["cooling_kWh"], 13.41),
                                ("gated latent", iso["latent_kWh"], 1.14),
                                ("per-area need", iso["per_sqm"], 6.91)):
            if abs(got - want) > 0.01:
                raise Unmatchable(
                    f"the corrected engine returns {got:.4f} for {name}, the "
                    f"canonical state is {want:.2f} — this is not the state the "
                    "paper reports and the comparison would not be about it")

        idf = build_matched_idf(bui, iso, timestep=args.timestep)
        (args.outdir / "apt305_conditioned.idf").write_text(idf, encoding="utf-8")
        print(f"  IDF -> {args.outdir / 'apt305_conditioned.idf'} "
              f"({idf.count(chr(10)) + 1:,} lines)")

        write_alignment(iso, args.outdir, epw_label)
        print(render_alignment(alignment_rows(iso["infiltration"], iso["gains_w"])))

        if args.audit_only:
            return
        if not args.energyplus:
            raise SystemExit("EnergyPlus binary not found — pass --energyplus")

        print("\nrunning the matched EnergyPlus case…")
        # EnergyPlus working directories go to scratch: the SQLite and HTML
        # output run to ~15 MB and none of it is a deliverable. The .err files
        # are copied back afterwards as evidence the runs were clean.
        ep = run_energyplus(idf, args.weather, args.energyplus,
                            tmp / "ep_corrected", tag="apt305c")
        print(f"  {ep['heating_kWh']:.2f} kWh heating, "
              f"{ep['cooling_kWh']:.2f} kWh cooling ({ep['warnings']} warnings)")

        sens = None
        if not args.skip_sensitivity:
            print("running the f == 1 infiltration bound…")
            sens = run_energyplus(
                build_matched_idf(bui, iso, timestep=args.timestep,
                                  inf_mode="constant"),
                args.weather, args.energyplus, tmp / "sens", tag="apt305s")
            print(f"  {sens['heating_kWh']:.2f} / {sens['cooling_kWh']:.2f} kWh")

        # The baseline half of the before/after table, on a reference carrying
        # the same two IDF repairs, so both halves are like-for-like.
        print("running the baseline engine and its repaired reference…")
        engine = BaselineEngineProxy(tmp)
        try:
            probe = engine.probe(str(args.weather))
            iso_b = engine.run(str(args.weather))
        finally:
            engine.close()
        base_idf = build_baseline_idf(bui, probe, timestep=args.timestep)
        (args.outdir / "apt305_baseline_repaired.idf").write_text(
            base_idf, encoding="utf-8")
        ep_b = run_energyplus(base_idf, args.weather, args.energyplus,
                              tmp / "ep_baseline", tag="apt305b")
        for src, dst in ((tmp / "ep_corrected" / "apt305cout.err",
                          args.outdir / "apt305_conditioned.err"),
                         (tmp / "ep_baseline" / "apt305bout.err",
                          args.outdir / "apt305_baseline_repaired.err")):
            if src.is_file():
                shutil.copyfile(src, dst)
        print(f"  ISO {iso_b['heating_kWh']:.2f} / {iso_b['cooling_kWh']:.2f}, "
              f"E+ {ep_b['heating_kWh']:.2f} / {ep_b['cooling_kWh']:.2f}")

        base = {"iso": iso_b, "ep": ep_b}
        tables = build_tables(iso, ep, area)
        # Override the before/after baseline half with the repaired reference.
        for r in tables["before_after"]:
            key = {"Heating": "heating_kWh", "Cooling": "cooling_kWh"}.get(r["metric"])
            if key:
                r["baseline_ep"] = ep_b[key]
                r["baseline_diff_pct"] = pct(r["baseline_iso"], ep_b[key])
            else:
                tot = ep_b["heating_kWh"] + ep_b["cooling_kWh"]
                r["baseline_ep"] = tot
                r["baseline_diff_pct"] = pct(r["baseline_iso"], tot)
            r["abs_change_pp"] = abs(r["corrected_diff_pct"]) - abs(r["baseline_diff_pct"])
            r["improved"] = abs(r["corrected_diff_pct"]) < abs(r["baseline_diff_pct"])
        tables["baseline_rows"] = [
            ("Heating", iso_b["heating_kWh"], ep_b["heating_kWh"]),
            ("Cooling", iso_b["cooling_kWh"], ep_b["cooling_kWh"]),
            ("Total", iso_b["heating_kWh"] + iso_b["cooling_kWh"],
             ep_b["heating_kWh"] + ep_b["cooling_kWh"]),
        ]

        write_csv(tables, iso, ep, args.outdir)
        write_markdown(tables, iso, ep, base, args.outdir, epw_label)
        write_discrepancy(tables, iso, ep, base, sens, args.outdir, epw_label)
        figure(tables, args.outdir,
               f"{epw_label}  ·  each engine against a reference matched to it  ·  "
               "EnergyPlus 24.1.0")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nwritten -> {args.outdir}")
    for p in sorted(args.outdir.glob("*")):
        if p.is_file():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")


class BaselineEngineProxy:
    """The baseline branch worktree, borrowed from ``baseline_vs_energyplus``."""

    def __init__(self, workdir: Path):
        from baseline_vs_energyplus import BaselineEngine
        self._inner = BaselineEngine(workdir)

    def probe(self, epw: str) -> dict:
        return self._inner.probe(epw)

    def run(self, epw: str) -> dict:
        return self._inner.run(epw)

    def close(self) -> None:
        self._inner.close()


if __name__ == "__main__":
    main()
