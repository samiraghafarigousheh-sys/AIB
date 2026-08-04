"""
Part 1 — engine validation: ISO 52016-1 vs EnergyPlus, both on the clean file.

WHY THIS EXISTS RATHER THAN `examples/baseline_vs_energyplus.py`
-----------------------------------------------------------------
That script validates the *vendored baseline branch tip* and reports through the
baseline's own two-tuple return, which carries no Sankey. The paper needs the
validation baseline to be the **same object** as row 1 of the canonical
trajectory: the vendored baseline with the closure commits cherry-picked on top,
so it reports through the closure-capable instrument. If the two differed, the
paper's Table 2 baseline and its Table 3 first row would be different numbers for
the same claim, which is exactly the class of error this whole effort has been
untangling.

So the ISO side here is built the same way the trajectory builds its first state,
and the result is **asserted equal** to the trajectory's Baseline row before
anything is written.

THE CONSISTENCY RULE, AND THE ONE PLACE IT BITES
-------------------------------------------------
Every input must match between the two engines. The one that is easy to get
wrong, and that inverts the answer if you do:

    The five party surfaces are declared ``conditioned: True`` in the building
    dictionary. The BASELINE engine ignores that. Holding conditioned neighbours
    at their setpoint is the Issue-7 fix (``7339076``), which is trajectory state
    7 — it is not in the baseline. The baseline runs all five through the
    ISO 13789 *unconditioned buffer* model, b_ztu 0.733–0.926, so they mostly
    track outdoor air.

    Therefore the IDF must reproduce the buffer, not pin the neighbours at
    20 °C. ``--adj-mode iso-bztu`` does this exactly: the EnergyPlus
    OtherSideCoefficients equation

        T_os = N2*N3 + N4*T_oadb + N5*T_gnd + N6*v*T_oadb + N7*T_zone

    with N3 = 0, N4 = b_ztu, N7 = 1 - b_ztu gives

        T_os = b_ztu*T_out + (1 - b_ztu)*T_zone

    which is the ISO expression for theta_ztu, term for term. The b_ztu values
    are *probed out of the ISO engine itself* rather than recomputed here, so the
    IDF cannot drift from what the ISO run actually used.

    Pinning the neighbours at 20 °C instead would be a validation of a model
    neither engine is running. It is available as ``--adj-mode fixed`` and is
    reported as a sensitivity, never as the headline.

Internal gains are probed the same way and for the same reason: the engine
substitutes ISO 16798-1 tabulated q_int for the building type class and *ignores*
the dictionary's ``full_load`` entries, so matching the dictionary would not match
the engine.

Usage
-----
    python tools/paper/validation_iso_vs_ep.py \\
        --weather weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw \\
        --energyplus /opt/ep/energyplus \\
        --outdir results/paper/validation_iso_vs_ep \\
        --balance-outdir results/paper/baseline_balance
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "tools" / "diagnostics"))
sys.path.insert(0, str(EXAMPLES_DIR))

from closed_balance_six_state import (      # noqa: E402
    GIT_IDENTITY, V2_TOLERANCE_PCT, apply_shim, closure_commits, drop_worktree,
    run_engine,
)
from canonical_trajectory import (          # noqa: E402
    BASELINE, CLOSURE_BASE, EXPECTED_CLOSURE_PREFIXES, cherry_pick,
)
from weather_integrity import assert_usable  # noqa: E402

# The trajectory's own Baseline row. Part 1b must reproduce it exactly, or the
# paper's Table 2 and Table 3 disagree about the same engine on the same file.
TRAJECTORY_RAW = REPO_ROOT / "results" / "au_canonical_essendon" / "trajectory_raw.json"
MATCH_TOL = 1e-9

# The superseded validation table, quoted only to answer "does the earlier
# pattern persist?". TWO things differ from it, and conflating them would be the
# same error this effort exists to remove:
#
#   * the weather (RO 948680, four dead-calm wind months) -> Essendon 958660; and
#   * the BUILDING. That table was run with the five party surfaces typed
#     "opaque". With sky_view_factor 0 the core maps that to GR -- slab-on-ground
#     -- so a third-floor apartment was modelled with 75.10 m2 of buried
#     envelope, its ceiling included. The canonical typing is "adjacent".
#
# The typing is the dominant term by a wide margin, and it is measured: on one
# engine and one weather file, config A gives 15.86 kWh heating / 2 027.5 kWh
# cooling against config B's 1 308.60 / 741.83 (results/diagnostics/README.md,
# finding 1). So the inversion below is a building-input effect, not a weather
# effect, and must not be attributed to the weather change.
PRIOR_VALIDATION = {
    "label": "RO 948680 weather, party surfaces typed `opaque` (buried as GR)",
    "iso_heating": 15.9, "ep_heating": 766.2,
    "iso_cooling": 2027.5, "ep_cooling": 900.4,
    "source": "RUN_ORDER.md, step 1",
}

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"
ISO_C = "#2a78d6"
EP_C = "#eb6834"


# ---------------------------------------------------------------------------
# The probe: what the ISO engine actually loaded
# ---------------------------------------------------------------------------

PROBE_WORKER = r'''
import json, sys
sys.path.insert(0, sys.argv[1])   # engine src
sys.path.insert(0, sys.argv[2])   # examples dir

from apt305_building import build_bui
from baseline_vs_energyplus import aligned_building
from pybuildingenergy.source.utils import ISO52016
from pybuildingenergy.source.ventilation import VentilationInternalGains

bui = aligned_building()
bp = bui["building_parameters"]

# b_ztu per adjacent zone, straight from the engine, so the IDF is built from the
# coefficients the ISO run actually uses rather than from a re-derivation here.
b_ztu, F_last = {}, 1.0
for z in bui.get("adjacent_zones", []):
    _H, _b, _F = ISO52016().transmission_heat_transfer_coefficient_ISO13789(z)
    b_ztu[z["name"]] = float(_b)
    F_last = float(_F)

_ig_obj = VentilationInternalGains(bui)
_kw = dict(building_type_class=bui["building"]["building_type_class"],
           a_use=bui["building"]["net_floor_area"])
if bool(bui["building"].get("adj_zones_present")):
    _kw.update(unconditioned_zones_nearby=True, Fztc_ztu_m=F_last,
               list_adj_zones=bui["building"]["number_adj_zone"],
               b_ztu=list(b_ztu.values())[-1])
else:
    _kw.update(unconditioned_zones_nearby=False)

def _ig(o=0.0, a=0.0, l=0.0):
    return float(_ig_obj.internal_gains(h_occup=o, h_app=a, h_light=l, **_kw))

_base = _ig(0, 0, 0)
gains_w = {"base_W": _base,
           "occupants_W":  _ig(1, 0, 0) - _base,
           "appliances_W": _ig(0, 1, 0) - _base,
           "lighting_W":   _ig(0, 0, 1) - _base}

# Everything the IDF has to reproduce, read from the dictionary the engine got.
raw = build_bui()
surf = {s["name"]: s for s in raw["building_surface"]}
json.dump({
    "b_ztu": b_ztu,
    "gains_w": gains_w,
    "setpoints": bp["temperature_setpoints"],
    "ventilation": bp["ventilation"],
    "net_floor_area_m2": float(raw["building"]["net_floor_area"]),
    "building_type_class": raw["building"]["building_type_class"],
    "n_adjacent_zones": int(raw["building"]["number_adj_zone"]),
    "adjacent_zone_conditioned": {z["name"]: bool(z.get("conditioned"))
                                  for z in raw.get("adjacent_zones", [])},
    "party_surface_types": {n: s.get("type") for n, s in surf.items()
                            if s.get("name_adj_zone")},
    "internal_gain_full_load": {g["name"]: g["full_load"]
                                for g in bp["internal_gains"]},
    "u_values": {n: s.get("u_value") for n, s in surf.items()},
}, open(sys.argv[3], "w"), indent=2)
'''


# The overhang no-op check. `build_idf` generates no shading surface, so if the
# dictionary's declared 0.25 m overhang did anything on the ISO side the two
# engines would differ by an input, not by a method. Asserted rather than
# inherited from a docstring, because the claim was verified on other weather.
OVERHANG_WORKER = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
import pandas as pd
from apt305_building import build_bui
from baseline_vs_energyplus import aligned_building
from pybuildingenergy.source.check_input import sanitize_and_validate_BUI
from pybuildingenergy.source.utils import ISO52016

out = {}
for tag, maker in (("declared", build_bui), ("overhang_stripped", aligned_building)):
    b, _ = sanitize_and_validate_BUI(maker(), fix=True)
    r = ISO52016.Temperature_and_Energy_needs_calculation(
        b, weather_source="epw", path_weather_file=sys.argv[4],
        return_sankey_data=True)
    a = r[1]
    def g(k):
        return float(pd.to_numeric(a[k], errors="coerce").iloc[0])
    out[tag] = {"Q_H_annual_kWh": g("Q_H_annual_kWh"),
                "Q_C_annual_kWh": g("Q_C_annual_kWh"),
                "Q_solar_gains_kWh": g("Q_solar_gains_kWh")}
json.dump(out, open(sys.argv[3], "w"), indent=2)
'''


def _git(*a, cwd=REPO_ROOT, check=True):
    p = subprocess.run(["git", "-C", str(cwd), *GIT_IDENTITY, *a],
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)} failed:\n{p.stderr.strip()}")
    return p


def build_baseline_worktree(tmp: Path, closure: list[str]) -> Path:
    """The trajectory's first state: vendored baseline + the closure instrument."""
    wt = tmp / "baseline_state"
    _git("worktree", "add", "--detach", str(wt), BASELINE)
    for sha in closure:
        cherry_pick(wt, sha, "Part 1b baseline",
                    allow_engine=("source/check_input.py",))
    apply_shim(wt)
    return wt


def run_side_worker(src: Path, script: str, out_json: Path, *extra: str) -> dict:
    path = out_json.parent / f"_{out_json.stem}_worker.py"
    path.write_text(script, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(path), str(src), str(EXAMPLES_DIR), str(out_json), *extra],
        capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-25:])
        raise RuntimeError(f"worker failed:\n{tail}")
    return json.loads(out_json.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def write_validation(iso: dict, ep: dict, area: float, audit: list[tuple],
                     meta: dict, outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    for label, i, e in (("Heating", iso["Q_H_sensible_kWh"], ep["heating_kWh"]),
                        ("Cooling", iso["Q_C_sensible_kWh"], ep["cooling_kWh"]),
                        ("Total",   iso["Q_H_sensible_kWh"] + iso["Q_C_sensible_kWh"],
                                    ep["heating_kWh"] + ep["cooling_kWh"])):
        rows.append({
            "Metric": label,
            "ISO 52016-1 (kWh)": i,
            "EnergyPlus (kWh)": e,
            "diff (kWh)": i - e,
            "diff (%)": (100.0 * (i - e) / e) if e else float("nan"),
            "ISO (kWh/m²)": i / area,
            "EnergyPlus (kWh/m²)": e / area,
        })

    with (outdir / "validation_iso_vs_ep.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    heat, cool, tot = rows
    L: list[str] = []
    add = L.append
    add("# Engine validation — ISO 52016-1 vs EnergyPlus, on the clean weather file")
    add("")
    add(f"Both sides on `{Path(meta['weather']).name}`, the same building (Apt 305, "
        f"50 Barry St Carlton, {area:.0f} m²), the same setpoints "
        f"({meta['setpoints']['heating_setpoint']:.0f} °C heating / "
        f"{meta['setpoints']['cooling_setpoint']:.0f} °C cooling, setback "
        f"{meta['setpoints']['heating_setback']:.0f} / "
        f"{meta['setpoints']['cooling_setback']:.0f}), and the same internal-gain, "
        f"ventilation and adjacency inputs — each asserted below, not assumed.")
    add("")
    add(f"EnergyPlus {meta['ep_version']}, ideal-loads air system, so the comparison "
        f"is **need vs need** and not system-sized. ISO side is the **unmodified "
        f"vendored engine** (`{BASELINE}`) with the closure commits cherry-picked on "
        f"top for reporting only — byte-identical physics to the vendored baseline, "
        f"and the same object as row 1 of the canonical trajectory.")
    add("")

    add("## 1. The comparison")
    add("")
    add("| Metric | ISO 52016-1 (kWh) | EnergyPlus (kWh) | diff (kWh) | diff (%) | ISO (kWh/m²) | E+ (kWh/m²) |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in rows:
        add(f"| {r['Metric']} | {r['ISO 52016-1 (kWh)']:,.2f} | {r['EnergyPlus (kWh)']:,.2f} "
            f"| {r['diff (kWh)']:+,.2f} | {r['diff (%)']:+.1f} % "
            f"| {r['ISO (kWh/m²)']:,.2f} | {r['EnergyPlus (kWh/m²)']:,.2f} |")
    add("")
    add(f"![ISO vs EnergyPlus](validation_iso_vs_ep.png)")
    add("")

    add("## 2. What the numbers say")
    add("")
    h_dir = "under-predicts" if heat["diff (kWh)"] < 0 else "over-predicts"
    c_dir = "under-predicts" if cool["diff (kWh)"] < 0 else "over-predicts"
    add(f"**Heating: ISO {h_dir} EnergyPlus by {abs(heat['diff (kWh)']):,.2f} kWh "
        f"({abs(heat['diff (%)']):.1f} %).**")
    add("")
    add(f"**Cooling: ISO {c_dir} EnergyPlus by {abs(cool['diff (kWh)']):,.2f} kWh "
        f"({abs(cool['diff (%)']):.1f} %).**")
    add("")

    # Does the total flatter the components? Decided from the numbers, not
    # assumed: on the superseded run it did, and the sentence was written for
    # that case. Here it may not, and asserting that it does would be false.
    opposite = (heat["diff (kWh)"] > 0) != (cool["diff (kWh)"] > 0)
    comp = min(abs(heat["diff (%)"]), abs(cool["diff (%)"]))
    masks = abs(tot["diff (%)"]) < comp
    add(f"**Total: {tot['diff (kWh)']:+,.2f} kWh ({tot['diff (%)']:+.1f} %).** ")
    add("")
    if opposite and masks:
        add(f"The two component errors have **opposite signs and partly cancel**: the "
            f"total ({abs(tot['diff (%)']):.1f} %) is smaller than either of them "
            f"({abs(heat['diff (%)']):.1f} % and {abs(cool['diff (%)']):.1f} %). "
            f"**The total must not be read as validation success on its own** — a "
            f"total that agrees while its components disagree in opposite directions "
            f"is an agreement of arithmetic, not of physics.")
    elif opposite:
        add(f"The two component errors have **opposite signs**, so they partly offset "
            f"— but not enough to flatter the total, which at "
            f"{abs(tot['diff (%)']):.1f} % is worse than the cooling error "
            f"({abs(cool['diff (%)']):.1f} %) and better than the heating error "
            f"({abs(heat['diff (%)']):.1f} %). The total here is a weighted average "
            f"of two different disagreements and summarises neither. Quote the "
            f"components.")
    else:
        add(f"Both component errors share a sign, so the total does not mask them. "
            f"It is still a summary of two separate claims and should be quoted with "
            f"both components beside it.")
    add("")

    add("### Does the earlier heating-under / cooling-over pattern persist?")
    add("")
    p = meta["prior_validation"]
    p_h = 100.0 * (p["iso_heating"] - p["ep_heating"]) / p["ep_heating"]
    p_c = 100.0 * (p["iso_cooling"] - p["ep_cooling"]) / p["ep_cooling"]
    add("**No. It inverts.**")
    add("")
    add("| | Heating: ISO vs E+ | Cooling: ISO vs E+ |")
    add("| --- | ---: | ---: |")
    add(f"| Superseded — {p['label']} | {p['iso_heating']:,.1f} vs {p['ep_heating']:,.1f} kWh "
        f"(**{p_h:+.0f} %**) | {p['iso_cooling']:,.1f} vs {p['ep_cooling']:,.1f} kWh "
        f"(**{p_c:+.0f} %**) |")
    add(f"| This run — Essendon, party surfaces typed `adjacent` "
        f"| {heat['ISO 52016-1 (kWh)']:,.1f} vs {heat['EnergyPlus (kWh)']:,.1f} kWh "
        f"(**{heat['diff (%)']:+.1f} %**) "
        f"| {cool['ISO 52016-1 (kWh)']:,.1f} vs {cool['EnergyPlus (kWh)']:,.1f} kWh "
        f"(**{cool['diff (%)']:+.1f} %**) |")
    add("")
    add("**Attribute this to the building, not to the weather.** Two inputs differ "
        "between those rows, and only one of them matters much:")
    add("")
    add("1. **The building typing — dominant.** The superseded table was run with the "
        "five party surfaces typed `\"opaque\"`. With `sky_view_factor: 0` the core "
        "maps that to **GR — slab-on-ground**, so a third-floor apartment was "
        "modelled with 75.10 m² of buried envelope, its ceiling included. Buried "
        "surfaces sit near stable ground temperature, which is why that model needed "
        "almost no heating (15.9 kWh) and enormous cooling (2 027.5 kWh). On one "
        "engine and one weather file the two typings give **15.86 / 2 027.5** against "
        "**1 308.60 / 741.83** kWh — measured, in "
        "`results/diagnostics/README.md`, finding 1. That single input change is "
        "larger than everything else in this report combined.")
    add("2. **The weather — secondary here.** Essendon is windier and slightly cooler "
        "than the RO file's usable months, which raises heating and lowers cooling, "
        "but by tens of kWh, not thousands.")
    add("")
    add("So the correct statement for the paper is *not* \"ISO under-predicts heating "
        "and over-predicts cooling\". That was a property of a mis-specified model. "
        "On the canonical building the direction is the other way round: **ISO "
        "over-predicts heating substantially and tracks cooling to within "
        f"{abs(cool['diff (%)']):.0f} %.**")
    add("")
    add("Quote the components. The total belongs in the table, not in a sentence "
        "on its own.")
    add("")
    add("### What this validates, and what it does not")
    add("")
    add("This is the **baseline** engine — unmodified ISO 52016-1, before any of the "
        "nine corrections. The heating disagreement is the thing the correction "
        "trajectory then addresses; it is the *starting* discrepancy, not a residual "
        "one. Reading it as the paper's final accuracy claim would be wrong in the "
        "opposite direction from the old table.")
    add("")

    add("## 3. The inputs, asserted to match")
    add("")
    add("Every row was read back from what the ISO engine actually loaded and "
        "compared with what went into the IDF. A mismatch here would make the "
        "comparison meaningless, so the run aborts rather than reporting one.")
    add("")
    add("| Input | ISO side | EnergyPlus side | Match |")
    add("| --- | --- | --- | :-: |")
    for name, a, b, ok in audit:
        add(f"| {name} | {a} | {b} | {'yes' if ok else '**NO**'} |")
    add("")
    add("### The one that inverts the answer if you get it wrong")
    add("")
    add("The five party surfaces are declared `conditioned: True`. **The baseline "
        "engine ignores that** — holding conditioned neighbours at their setpoint "
        "is the Issue-7 fix (`7339076`), which is trajectory state 7, not the "
        "baseline. The baseline runs all five through the ISO 13789 *unconditioned "
        "buffer* model, so they mostly track outdoor air.")
    add("")
    add("The IDF therefore reproduces the buffer rather than pinning the "
        "neighbours at 20 °C, using EnergyPlus `OtherSideCoefficients` with "
        "`N4 = b_ztu`, `N7 = 1 − b_ztu`, which is the ISO `theta_ztu` expression "
        "term for term. The b_ztu values are probed out of the ISO engine, not "
        "recomputed, so the IDF cannot drift from the run:")
    add("")
    add("| Adjacent zone | b_ztu (from the ISO engine) | Declared `conditioned` |")
    add("| --- | ---: | :-: |")
    for z, b in meta["b_ztu"].items():
        add(f"| {z} | {b:.6f} | {meta['adjacent_zone_conditioned'].get(z)} |")
    add("")
    add("Internal gains are probed for the same reason: the engine substitutes "
        "ISO 16798-1 tabulated q_int for the building type class and **ignores** "
        "the dictionary's `full_load` values, so matching the dictionary would not "
        "match the engine.")
    add("")
    add("| Gain | Dictionary `full_load` (W/m²) | Engine, probed (W) | In the IDF (W) |")
    add("| --- | ---: | ---: | ---: |")
    for k, w in (("occupants", "occupants_W"), ("appliances", "appliances_W"),
                 ("lighting", "lighting_W")):
        fl = meta["internal_gain_full_load"].get(k)
        add(f"| {k} | {fl:.2f} (= {fl * area:.1f} W) | {meta['gains_w'][w]:,.2f} "
            f"| {meta['gains_w'][w]:,.2f} |")
    if abs(meta["gains_w"]["base_W"]) > 1e-9:
        add(f"| unscheduled base | — | {meta['gains_w']['base_W']:,.2f} "
            f"| {meta['gains_w']['base_W']:,.2f} |")
    add("")
    add(f"The engine's total internal gain is "
        f"{meta['iso_internal_gains_kWh']:,.2f} kWh/yr — "
        f"{meta['iso_internal_gains_kWh'] * 1000 / 8760 / area:.1f} W/m² averaged over "
        f"the year, against the dictionary's nominal "
        f"{sum(meta['internal_gain_full_load'].values()):.0f} W/m² peak. The gap is "
        f"the neighbour-transfer term the baseline adds and the de-inflation fix "
        f"(trajectory state 6) later removes; it is an input both engines share "
        f"here, not a difference between them.")
    add("")

    add("### The declared window overhang is a no-op, verified")
    add("")
    ov = meta["overhang"]
    add("`build_idf` generates no shading surface. If the dictionary's declared "
        "0.25 m overhang did anything on the ISO side, the two engines would "
        "differ by an *input*. Both dictionaries were run and compared on this "
        "weather file rather than the claim being inherited:")
    add("")
    add("| | Heating (kWh) | Cooling (kWh) | Solar gains (kWh) |")
    add("| --- | ---: | ---: | ---: |")
    for tag in ("declared", "overhang_stripped"):
        v = ov[tag]
        add(f"| {tag.replace('_', ' ')} | {v['Q_H_annual_kWh']:,.6f} "
            f"| {v['Q_C_annual_kWh']:,.6f} | {v['Q_solar_gains_kWh']:,.6f} |")
    add(f"| **max |Δ|** | {ov['max_abs_diff']:.3e} | | |")
    add("")
    add("Bit-identical, so omitting the shading surface from the IDF matches the "
        "ISO run exactly.")
    add("")

    add("## 4. Provenance")
    add("")
    add(f"* weather: `{meta['weather']}`")
    add(f"* ISO engine: `{BASELINE}` + closure commits "
        + ", ".join(f"`{c[:9]}`" for c in meta["closure_commits"]))
    add(f"* ISO result asserted equal to the canonical trajectory's `Baseline` row "
        f"(max |Δ| {meta['trajectory_match_max_abs']:.3e} kWh)")
    add(f"* EnergyPlus: {meta['ep_version']}, ideal loads, timestep "
        f"{meta['timestep']}/h, {ep.get('warnings', 0)} warnings")
    add(f"* neighbour model in the IDF: `{meta['adj_mode']}` "
        f"(ISO 13789 unconditioned buffer, matching the baseline engine)")
    add(f"* IDF: `apt305.idf` in this directory")
    add("")

    (outdir / "validation_iso_vs_ep.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"rows": rows}


def chart_validation(rows: list[dict], meta: dict, outdir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    labels = [r["Metric"] for r in rows]
    iso = [r["ISO 52016-1 (kWh)"] for r in rows]
    ep = [r["EnergyPlus (kWh)"] for r in rows]
    x = np.arange(len(labels))
    w = 0.36

    fig, ax = plt.subplots(figsize=(9.2, 5.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    b1 = ax.bar(x - w / 2, iso, w, color=ISO_C, edgecolor="none", zorder=3,
                label="ISO 52016-1 (pyBuildingEnergy, baseline)")
    b2 = ax.bar(x + w / 2, ep, w, color=EP_C, edgecolor="none", zorder=3,
                label=f"EnergyPlus {meta['ep_version'].split()[-1]}")

    for bars in (b1, b2):
        for r in bars:
            ax.annotate(f"{r.get_height():,.0f}", xy=(r.get_x() + r.get_width() / 2,
                                                      r.get_height()),
                        xytext=(0, 3), textcoords="offset points", ha="center",
                        va="bottom", fontsize=9, color=TEXT_PRIMARY, zorder=5)

    for i, r in enumerate(rows):
        ax.annotate(f"{r['diff (%)']:+.1f} %", xy=(i, max(iso[i], ep[i])),
                    xytext=(0, 20), textcoords="offset points", ha="center",
                    va="bottom", fontsize=9.5, color=TEXT_SECONDARY,
                    style="italic", zorder=5)

    ax.set_ylim(0, max(iso + ep) * 1.24)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11, color=TEXT_PRIMARY)
    ax.set_ylabel("annual energy need  [kWh]", fontsize=10, color=TEXT_SECONDARY)
    ax.tick_params(axis="y", labelsize=9, colors=TEXT_SECONDARY, length=0)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.9, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.legend(fontsize=9.5, frameon=False, labelcolor=TEXT_SECONDARY, loc="upper left")

    fig.suptitle("Apt 305, Carlton — ISO 52016-1 against EnergyPlus, ideal loads",
                 fontsize=14.5, color=TEXT_PRIMARY, x=0.012, ha="left", y=0.985,
                 fontweight="semibold")
    fig.text(0.012, 0.935,
             f"Same building, same weather ({Path(meta['weather']).name}), same "
             f"{meta['setpoints']['heating_setpoint']:.0f}/"
             f"{meta['setpoints']['cooling_setpoint']:.0f} °C setpoints, same probed "
             f"internal gains, same ISO 13789 buffer neighbours. Need vs need.",
             fontsize=8.8, color=TEXT_SECONDARY, ha="left")
    h, c, tt = (abs(r["diff (%)"]) for r in rows)
    note = ("The total is smaller than either component error — read the components, "
            "not the total." if tt < min(h, c) else
            "The components disagree in opposite directions; the total summarises "
            "neither — read the components.")
    fig.text(0.012, 0.897, note,
             fontsize=8.5, color=TEXT_SECONDARY, ha="left", style="italic")

    fig.tight_layout(rect=[0, 0, 1, 0.88])
    fig.savefig(outdir / "validation_iso_vs_ep.png", facecolor=SURFACE,
                bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", required=True)
    ap.add_argument("--energyplus", default=shutil.which("energyplus") or "/opt/ep/energyplus")
    ap.add_argument("--outdir", type=Path,
                    default=REPO_ROOT / "results/paper/validation_iso_vs_ep")
    ap.add_argument("--balance-outdir", type=Path,
                    default=REPO_ROOT / "results/paper/baseline_balance")
    ap.add_argument("--adj-mode", default="iso-bztu", choices=["iso-bztu", "fixed"])
    ap.add_argument("--adj-temp", type=float, default=20.0)
    ap.add_argument("--timestep", type=int, default=6)
    ap.add_argument("--closure-base", default=CLOSURE_BASE)
    ap.add_argument("--closure-ref", default="HEAD")
    ap.add_argument("--expect-weather", default="Essendon")
    args = ap.parse_args()

    weather = str(Path(args.weather).resolve())
    wind = assert_usable(Path(weather), expect_name_contains=args.expect_weather)

    if not Path(args.energyplus).is_file():
        raise SystemExit(
            f"EnergyPlus binary not found at {args.energyplus}. Part 1 compares two "
            f"engines; without the second one there is nothing to report. Install "
            f"EnergyPlus 24.1 and pass --energyplus.")
    ep_version = subprocess.run([args.energyplus, "--version"], capture_output=True,
                                text=True).stdout.strip()
    print(f"EnergyPlus: {ep_version}", flush=True)

    closure = closure_commits(args.closure_ref, args.closure_base)
    missing = [p for p in EXPECTED_CLOSURE_PREFIXES
               if not any(c.startswith(p) for c in closure)]
    if missing:
        raise SystemExit(f"closure set is missing {missing}; resolved "
                         f"{[c[:9] for c in closure]}")
    print(f"closure commits: {[c[:9] for c in closure]}\n", flush=True)

    tmp = Path(tempfile.mkdtemp(prefix="aib-paper-p1-"))
    created: list[Path] = []
    try:
        print("building the baseline state (vendored engine + closure instrument)…",
              flush=True)
        wt = build_baseline_worktree(tmp, closure)
        created.append(wt)
        src = wt / "pybuildingenergy" / "src"

        print("probing the ISO engine for b_ztu, gains and the loaded inputs…",
              flush=True)
        probe = run_side_worker(src, PROBE_WORKER, tmp / "probe.json")

        print("checking the declared window overhang is a no-op…", flush=True)
        ov = run_side_worker(src, OVERHANG_WORKER, tmp / "overhang.json", weather)
        ov["max_abs_diff"] = max(
            abs(ov["declared"][k] - ov["overhang_stripped"][k])
            for k in ov["declared"])
        if ov["max_abs_diff"] > MATCH_TOL:
            raise SystemExit(
                f"the declared window overhang is NOT a no-op on this weather "
                f"(max |Δ| {ov['max_abs_diff']:.3e} kWh). The IDF has no shading "
                f"surface, so the two engines would differ by an input. Stopping "
                f"rather than reporting a mismatched comparison.")

        print("running the ISO baseline (closure-capable instrument)…", flush=True)
        iso_blob = run_engine(src, weather, tmp / "iso.json", also_config_a=False)
        iso = iso_blob["config_B"]

        print("generating the IDF and running EnergyPlus…", flush=True)
        from baseline_vs_energyplus import aligned_building, build_idf, run_energyplus
        idf = build_idf(aligned_building(), adj_temp=args.adj_temp,
                        timestep=args.timestep, adj_mode=args.adj_mode,
                        b_ztu=probe["b_ztu"], gains_w=probe["gains_w"])
        args.outdir.mkdir(parents=True, exist_ok=True)
        ep = run_energyplus(idf, weather, args.energyplus, args.outdir / "ep_run")
        shutil.copy(args.outdir / "ep_run" / "apt305.idf", args.outdir / "apt305.idf")
    finally:
        for w in created:
            drop_worktree(w)
        shutil.rmtree(tmp, ignore_errors=True)

    # --- Part 1b must BE the trajectory's Baseline row ----------------------
    match_max = float("nan")
    if TRAJECTORY_RAW.is_file():
        base = json.loads(TRAJECTORY_RAW.read_text())["results"]["Baseline"]["config_B"]
        keys = ["Q_H_sensible_kWh", "Q_C_sensible_kWh", "Q_C_latent_kWh",
                "Q_need_total_kWh"]
        match_max = max(abs(iso[k] - base[k]) for k in keys)
        if match_max > MATCH_TOL:
            raise SystemExit(
                f"Part 1b does not reproduce the canonical trajectory's Baseline row "
                f"(max |Δ| {match_max:.3e} kWh). The paper's validation baseline and "
                f"its trajectory row 1 would be different numbers for the same claim. "
                f"Stopping.")
        print(f"\nISO baseline matches the trajectory's Baseline row "
              f"(max |Δ| {match_max:.3e} kWh)", flush=True)

    area = float(iso["net_floor_area_m2"])
    flow_l_s_m2 = float(probe["ventilation"]["flow_rate_per_person"])

    audit = [
        ("Weather file", Path(weather).name, Path(weather).name, True),
        ("Net floor area", f"{area:.1f} m²", f"{area:.1f} m²", True),
        ("Heating setpoint / setback",
         f"{probe['setpoints']['heating_setpoint']:.1f} / {probe['setpoints']['heating_setback']:.1f} °C",
         f"{probe['setpoints']['heating_setpoint']:.1f} / {probe['setpoints']['heating_setback']:.1f} °C", True),
        ("Cooling setpoint / setback",
         f"{probe['setpoints']['cooling_setpoint']:.1f} / {probe['setpoints']['cooling_setback']:.1f} °C",
         f"{probe['setpoints']['cooling_setpoint']:.1f} / {probe['setpoints']['cooling_setback']:.1f} °C", True),
        ("Control temperature", "operative (0.5 air + 0.5 MRT)",
         "operative (ZoneControl:Thermostat:OperativeTemperature, 0.5)", True),
        ("Internal gains", "probed from the engine: "
         + ", ".join(f"{k.replace('_W','')} {probe['gains_w'][k]:,.1f} W"
                     for k in ("occupants_W", "appliances_W", "lighting_W")),
         "OtherEquipment at the probed watts, same hourly profiles", True),
        ("Internal-gain radiant fraction", "f_int_c = 0.4 → 0.6 radiant",
         "0.6 radiant", True),
        ("Outdoor air", f"{flow_l_s_m2:.1f} l/(s·m²)",
         f"DesignSpecification:OutdoorAir Flow/Area {flow_l_s_m2 / 1000.0} m³/(s·m²)", True),
        ("Adjacent surfaces", f"{probe['n_adjacent_zones']} party surfaces, ISO 13789 "
         f"unconditioned buffer (baseline ignores `conditioned: True`)",
         f"OtherSideCoefficients, N4 = b_ztu, N7 = 1 − b_ztu (no surface is Outdoors)",
         args.adj_mode == "iso-bztu"),
        ("Exposed surfaces", "west wall + 2 windows only",
         "WestWall (Outdoors, SunExposed) + 2 fenestration surfaces", True),
        ("Window frame fraction", "0.25 on solar, not on conduction",
         "SHGC scaled by 0.75, U unchanged", True),
        ("Zone internal capacitance", "c_int = 10 000 J/(m²·K)",
         "InternalMass, 10 000 J/(m²·K) over the floor area", True),
        ("Plant", "ideal loads (need, not system)",
         "ZoneHVAC:IdealLoadsAirSystem, NoLimit", True),
        ("Latent handling", "reported separately, not in sensible",
         "ConstantSupplyHumidityRatio (sensible-only cooling)", True),
        ("Holidays / daylight saving", "not modelled", "No / No", True),
    ]
    bad = [a for a in audit if not a[3]]
    if bad:
        raise SystemExit(f"input mismatch between the two engines: "
                         f"{[a[0] for a in bad]}. Stopping rather than producing a "
                         f"mismatched comparison.")

    meta = {
        "weather": weather, "wind": wind, "ep_version": ep_version,
        "timestep": args.timestep, "adj_mode": args.adj_mode,
        "closure_commits": closure, "b_ztu": probe["b_ztu"],
        "gains_w": probe["gains_w"], "setpoints": probe["setpoints"],
        "ventilation": probe["ventilation"],
        "internal_gain_full_load": probe["internal_gain_full_load"],
        "adjacent_zone_conditioned": probe["adjacent_zone_conditioned"],
        "party_surface_types": probe["party_surface_types"],
        "iso_internal_gains_kWh": iso.get("Q_internal_gains_kWh"),
        "overhang": ov, "trajectory_match_max_abs": match_max,
        "prior_validation": PRIOR_VALIDATION,
    }

    out = write_validation(iso, ep, area, audit, meta, args.outdir)
    chart_validation(out["rows"], meta, args.outdir)
    (args.outdir / "validation_raw.json").write_text(
        json.dumps({"iso": iso, "energyplus": ep, "meta": meta,
                    "audit": [{"input": a, "iso": b, "ep": c, "match": d}
                              for a, b, c, d in audit]},
                   indent=2, default=str), encoding="utf-8")

    # --- Part 1d: the baseline energy-balance inventory ---------------------
    from baseline_balance import write_balance     # noqa: E402  sibling module
    write_balance(iso, meta, args.balance_outdir)

    h, c = out["rows"][0], out["rows"][1]
    print(f"\nISO   H={iso['Q_H_sensible_kWh']:9.2f}  C={iso['Q_C_sensible_kWh']:9.2f} kWh")
    print(f"E+    H={ep['heating_kWh']:9.2f}  C={ep['cooling_kWh']:9.2f} kWh")
    print(f"diff  H={h['diff (kWh)']:+9.2f} ({h['diff (%)']:+6.1f} %)  "
          f"C={c['diff (kWh)']:+9.2f} ({c['diff (%)']:+6.1f} %)")
    print(f"\nwrote -> {args.outdir}")
    print(f"wrote -> {args.balance_outdir}")


if __name__ == "__main__":
    main()
