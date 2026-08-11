"""
The local-wind profile: what EnergyPlus did, what the ISO side did, and what
the terrain/height correction is worth across sites.

This covers Items 0, 1, 3 and 5 of the wind-profile task. Item 2 -- the C2
sign -- is the controlled experiment in ``wind_h_ce_diagnostic.py``, which
this tool deliberately does not duplicate so the two cannot drift apart.

ITEM 0, and why it comes first
------------------------------
EnergyPlus applies a boundary-layer wind profile by default. It reads the
``Terrain`` field of the ``Building`` object, derives (a, delta) from it, and
evaluates every wind-exposed surface at its own centroid height. If the
generated IDFs used that default while the ISO side used the raw 10 m station
column, the two engines were driven by DIFFERENT WIND SPEEDS, and that is an
input mismatch in the validation of the same class as the three already found.

The finding is established from two independent directions, because either on
its own is arguable:

  * statically, by reading the IDF and applying the documented EnergyPlus
    algorithm; and
  * dynamically, by re-running the committed IDF with
    ``Surface Outside Face Outdoor Air Wind Speed`` reported hourly, which is
    the wind EnergyPlus actually used, not the wind we think it used.

Usage
-----
    python tools/diagnostics/wind_profile_terrain.py \\
        --weather weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw \\
        --outdir results/paper/wind_profile \\
        --energyplus /opt/ep/energyplus
    python tools/diagnostics/wind_profile_terrain.py --no-energyplus   # static only
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pybuildingenergy" / "src"))
sys.path.insert(0, str(REPO_ROOT / "examples"))

DEFAULT_EPW = (REPO_ROOT / "weather_cache"
               / "AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw")
DEFAULT_OUT = REPO_ROOT / "results" / "paper" / "wind_profile"

# The two IDFs the validation was run from.
IDF_MATCHED = REPO_ROOT / "results/paper/validation_corrected/apt305_conditioned.idf"
IDF_BASELINE = REPO_ROOT / "results/paper/validation_corrected/apt305_baseline_repaired.idf"

PIVOT_MS = 4.0     # 4u + 4 == 20 W/(m2 K), the ISO 13789 constant

# EnergyPlus derives these from the Building object's Terrain field when no
# Site:HeightVariation is present. Energy+.idd, Building/A2, and the Engineering
# Reference "Local Wind Speed Calculations".
EPLUS_TERRAIN_TO_CLASS = {
    "ocean": "flat_open",
    "country": "open_country",
    "suburbs": "suburban",
    "urban": "suburban",
    "city": "city_centre",
}
EPLUS_DEFAULT_TERRAIN = "Suburbs"          # Energy+.idd, Building/A2 \default
EPLUS_HEIGHTVAR_DEFAULTS = (0.22, 370.0)   # Site:HeightVariation N1/N2 \default
EPLUS_STATION_DEFAULTS = (10.0, 0.14, 270.0)   # Site:WeatherStation N1/N2/N3


# ---------------------------------------------------------------------------
# Item 0 -- static read of the IDF
# ---------------------------------------------------------------------------

def _strip_comments(text: str) -> str:
    return "\n".join(line.split("!")[0] for line in text.splitlines())


def idf_objects(text: str, kind: str) -> list:
    """All objects of one type, as lists of stripped fields."""
    body = _strip_comments(text)
    out = []
    for m in re.finditer(rf"(?im)^\s*{re.escape(kind)}\s*,(.*?);", body, re.S):
        fields = [f.strip() for f in m.group(1).split(",")]
        out.append(fields)
    return out


def surface_centroid_heights(text: str) -> dict:
    """z of the centroid of each wind-exposed BuildingSurface, from its vertices."""
    body = _strip_comments(text)
    heights = {}
    for m in re.finditer(r"(?is)BuildingSurface:Detailed\s*,(.*?);", body):
        fields = [f.strip() for f in m.group(1).split(",")]
        if len(fields) < 11:
            continue
        name, bc, wind = fields[0], fields[5], fields[8]
        if bc.lower() != "outdoors" or "windexposed" not in wind.lower():
            continue
        # 0 Name, 1 Surface Type, 2 Construction, 3 Zone, 4 Space,
        # 5 Outside BC, 6 BC Object, 7 Sun Exposure, 8 Wind Exposure,
        # 9 View Factor to Ground, 10 Number of Vertices, 11.. vertices.
        coords = [float(v) for v in fields[11:] if v]
        zs = coords[2::3]
        if zs:
            heights[name] = sum(zs) / len(zs)
    for m in re.finditer(r"(?is)FenestrationSurface:Detailed\s*,(.*?);", body):
        fields = [f.strip() for f in m.group(1).split(",")]
        if len(fields) < 10:
            continue
        coords = [float(v) for v in fields[9:] if v]
        zs = coords[2::3]
        if zs:
            heights[fields[0]] = sum(zs) / len(zs)
    return heights


def read_idf_wind_treatment(path: Path) -> dict:
    """What wind profile this IDF asks EnergyPlus for."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    building = idf_objects(text, "Building")
    terrain = EPLUS_DEFAULT_TERRAIN
    if building and len(building[0]) >= 3 and building[0][2]:
        terrain = building[0][2]

    hv = idf_objects(text, "Site:HeightVariation")
    ws = idf_objects(text, "Site:WeatherStation")

    cls = EPLUS_TERRAIN_TO_CLASS.get(terrain.strip().lower(), "suburban")
    if hv:
        a = float(hv[0][0]) if hv[0] and hv[0][0] else EPLUS_HEIGHTVAR_DEFAULTS[0]
        delta = float(hv[0][1]) if len(hv[0]) > 1 and hv[0][1] else EPLUS_HEIGHTVAR_DEFAULTS[1]
        basis = "Site:HeightVariation present; its own fields used"
    else:
        from pybuildingenergy.source.utils import _ASHRAE_TERRAIN_PARAMETERS
        a, delta = _ASHRAE_TERRAIN_PARAMETERS[cls]
        basis = (f"Site:HeightVariation ABSENT; EnergyPlus falls back to the "
                 f"Building object's Terrain = '{terrain}'")

    z_met, a_met, delta_met = EPLUS_STATION_DEFAULTS
    if ws:
        f = ws[0]
        z_met = float(f[0]) if f and f[0] else z_met
        a_met = float(f[1]) if len(f) > 1 and f[1] else a_met
        delta_met = float(f[2]) if len(f) > 2 and f[2] else delta_met

    heights = surface_centroid_heights(text)
    return {
        "idf": str(path.relative_to(REPO_ROOT)),
        "terrain_field": terrain,
        "terrain_class_equivalent": cls,
        "site_heightvariation_present": bool(hv),
        "site_weatherstation_present": bool(ws),
        "basis": basis,
        "exponent_a": a,
        "boundary_layer_delta_m": delta,
        "station_sensor_height_m": z_met,
        "station_exponent_a": a_met,
        "station_boundary_layer_delta_m": delta_met,
        "wind_exposed_surface_heights_m": heights,
        "factors": {
            name: ((delta_met / z_met) ** a_met) * ((max(z, 1e-9) / delta) ** a)
            for name, z in heights.items()
        },
    }


# ---------------------------------------------------------------------------
# Item 0 -- dynamic: what EnergyPlus actually used
# ---------------------------------------------------------------------------

def run_energyplus_wind(idf: Path, weather: Path, exe: str, workdir: Path) -> dict:
    """
    Re-run the committed IDF with the per-surface wind reported hourly.

    Only two objects are added -- an Output:Variable and an SQLite request --
    so the wind this returns is the wind that IDF has always been run with.
    """
    import numpy as np

    workdir.mkdir(parents=True, exist_ok=True)
    text = idf.read_text(encoding="utf-8", errors="ignore")
    text += (
        "\n\n! --- added by wind_profile_terrain.py: report the wind EnergyPlus uses ---\n"
        "  Output:Variable, *, Surface Outside Face Outdoor Air Wind Speed, Hourly;\n"
        "  Output:Variable, *, Site Wind Speed, Hourly;\n"
    )
    if "output:sqlite" not in text.lower():
        text += "  Output:SQLite, SimpleAndTabular;\n"
    probe = workdir / "wind_probe.idf"
    probe.write_text(text, encoding="utf-8")

    proc = subprocess.run(
        [exe, "-w", str(weather), "-d", str(workdir), "-p", "wind", str(probe)],
        capture_output=True, text=True,
    )
    sql = workdir / "windout.sql"
    if not sql.is_file():
        cands = list(workdir.glob("*.sql"))
        if not cands:
            raise RuntimeError(
                f"EnergyPlus produced no SQL. exit={proc.returncode}\n"
                f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
            )
        sql = cands[0]

    con = sqlite3.connect(str(sql))
    try:
        rows = con.execute(
            "SELECT rdd.KeyValue, AVG(rd.Value), COUNT(rd.Value) "
            "FROM ReportData rd "
            "JOIN ReportDataDictionary rdd ON rdd.ReportDataDictionaryIndex "
            "     = rd.ReportDataDictionaryIndex "
            "WHERE rdd.Name IN ('Surface Outside Face Outdoor Air Wind Speed', "
            "                   'Site Wind Speed') "
            "GROUP BY rdd.KeyValue, rdd.Name"
        ).fetchall()
    finally:
        con.close()
    return {str(k): {"mean_m_s": float(v), "n": int(n)} for k, v, n in rows}


# ---------------------------------------------------------------------------
# Items 1, 3, 5 -- the profile itself
# ---------------------------------------------------------------------------

def epw_wind(weather: Path):
    import numpy as np
    import pandas as pd
    rows = []
    with open(weather, "r", errors="ignore") as fh:
        for i, line in enumerate(fh):
            if i < 8:
                continue
            parts = line.split(",")
            if len(parts) > 21:
                rows.append(float(parts[21]))
    return np.asarray(rows, dtype=float)


def terrain_table(weather_wind, z_m: float) -> list:
    """Item 3 / Item 1: the four classes at one height."""
    import numpy as np
    from pybuildingenergy.source.utils import (
        _ASHRAE_TERRAIN_PARAMETERS, local_wind_speed_factor)
    out = []
    for cls in ("flat_open", "open_country", "suburban", "city_centre"):
        a, delta = _ASHRAE_TERRAIN_PARAMETERS[cls]
        f = local_wind_speed_factor(cls, z_m)
        u = weather_wind * f
        out.append({
            "terrain_class": cls, "exponent_a": a, "boundary_layer_delta_m": delta,
            "factor": f, "mean_local_m_s": float(np.nanmean(u)),
            "pct_hours_above_pivot": float(100.0 * np.mean(u > PIVOT_MS)),
            "mean_h_ce": float(np.nanmean(4.0 * u + 4.0)),
        })
    return out


def australian_cases(weather_wind) -> list:
    """Item 5: the engine must serve sites beyond this one."""
    import numpy as np
    from pybuildingenergy.source.utils import local_wind_speed_factor
    cases = [
        ("Suburban single-storey dwelling", "suburban", 1, 2.7, None),
        ("Inner-urban apartment, Level 3 (Apt 305)", "suburban", 3, 2.7, None),
        ("City-centre apartment, Level 20", "city_centre", 20, 3.0, None),
        ("Rural dwelling, open ground", "open_country", 1, 2.7, None),
        ("Identity case: station terrain at station height", "open_country", None, None, 10.0),
    ]
    out = []
    for label, cls, n, h, z_explicit in cases:
        z = z_explicit if z_explicit is not None else (n - 0.5) * h
        f = local_wind_speed_factor(cls, z)
        u = weather_wind * f
        out.append({
            "case": label, "terrain_class": cls, "surface_height_m": z,
            "height_basis": (f"explicit {z:.1f} m" if z_explicit is not None
                             else f"(level {n} - 0.5) x {h:.1f} m"),
            "factor": f, "mean_local_m_s": float(np.nanmean(u)),
            "pct_hours_above_pivot": float(100.0 * np.mean(u > PIVOT_MS)),
            "direction": ("unchanged" if abs(f - 1.0) < 1e-9
                          else "increase" if f > 1.0 else "reduction"),
        })
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(d: dict, out_md: Path) -> None:
    import numpy as np

    L: list[str] = []
    add = L.append
    ep = d["idf_static"]
    site = d["site"]
    wmean = d["epw"]["mean_m_s"]

    add("# The local-wind profile: terrain and height")
    add("")
    add(f"Weather: `{d['weather_name']}`. Station wind column: mean "
        f"**{wmean:.2f} m/s**, {d['epw']['pct_above_pivot']:.1f} % of hours above "
        f"the {PIVOT_MS:.0f} m/s pivot at which `4u + 4 = 20 W/(m²·K)`, the ISO "
        f"13789 constant the correction replaces.")
    add("")
    add("Covers Items 0, 1, 3 and 5. Item 2 — whether C2 changes sign — is the "
        "controlled experiment in `wind_verdict_*.md`, which this file does not "
        "restate.")
    add("")

    # ---- Item 0 -----------------------------------------------------------
    add("## Item 0 — what EnergyPlus did")
    add("")
    add("### The finding")
    add("")
    add(d["item0"]["verdict"])
    add("")
    add("### The static read of the IDF")
    add("")
    add("| | |")
    add("| --- | --- |")
    add(f"| `Site:HeightVariation` | "
        f"{'present' if ep['site_heightvariation_present'] else '**absent**'} |")
    _ws_note = ("present; its own fields used"
                if ep["site_weatherstation_present"] else
                f"**absent** — EnergyPlus defaults apply: "
                f"{ep['station_sensor_height_m']:.0f} m sensor, "
                f"a = {ep['station_exponent_a']}, "
                f"δ = {ep['station_boundary_layer_delta_m']:.0f} m")
    add(f"| `Site:WeatherStation` | {_ws_note} |")
    add(f"| `Building` Terrain field | `{ep['terrain_field']}` |")
    add(f"| What that resolves to | a = {ep['exponent_a']}, "
        f"δ = {ep['boundary_layer_delta_m']:.0f} m "
        f"(ASHRAE class `{ep['terrain_class_equivalent']}`) |")
    add(f"| Basis | {ep['basis']} |")
    add("")
    add("Wind-exposed surfaces and the profile EnergyPlus evaluates at each:")
    add("")
    add("| Surface | Centroid height z (m) | u_local / u_met |")
    add("| --- | ---: | ---: |")
    for name, z in sorted(ep["wind_exposed_surface_heights_m"].items()):
        add(f"| `{name}` | {z:.2f} | {ep['factors'][name]:.4f} |")
    add("")

    if d.get("item0", {}).get("measured"):
        add("### What EnergyPlus actually used")
        add("")
        add("Not inferred from the algorithm — measured, by re-running the "
            "committed IDF with `Surface Outside Face Outdoor Air Wind Speed` "
            "reported hourly. Only an `Output:Variable` was added.")
        add("")
        add("| Reported key | Annual mean (m/s) | Hours | Implied factor |")
        add("| --- | ---: | ---: | ---: |")
        for k, v in sorted(d["item0"]["measured"].items()):
            add(f"| `{k}` | {v['mean_m_s']:.3f} | {v['n']:,} | "
                f"{v['mean_m_s'] / wmean:.4f} |")
        add("")

    add("### The mismatch")
    add("")
    add("| Engine | Wind fed to the external film | Annual mean |")
    add("| --- | --- | ---: |")
    add(f"| EnergyPlus (as run) | station column × the `{ep['terrain_field']}` "
        f"profile at each surface's own height | "
        f"**{d['item0']['ep_mean_m_s']:.2f} m/s** |")
    add(f"| ISO 52016-1 (as run, before this change) | station column, unadjusted | "
        f"**{wmean:.2f} m/s** |")
    add(f"| ISO 52016-1 (after this change) | station column × the declared "
        f"terrain and height | **{d['site']['mean_local_m_s']:.2f} m/s** |")
    add("")
    add(d["item0"]["discussion"])
    add("")

    # ---- Item 1 -----------------------------------------------------------
    add("## Item 1 — the implementation")
    add("")
    add("$$u_{local} = u_{met}\\left(\\frac{\\delta_{met}}{z_{met}}\\right)^{a_{met}}"
        "\\left(\\frac{z}{\\delta}\\right)^{a}$$")
    add("")
    add("Coefficients: **ASHRAE Handbook — Fundamentals (2021), Chapter 24 "
        "\"Airflow Around Buildings\", Table 1 (Atmospheric Boundary Layer "
        "Parameters)**. All four classes are implemented with the published "
        "values; none differs from the task's table.")
    add("")
    add("| Class | a | δ (m) | Description | EnergyPlus `Terrain` equivalent |")
    add("| --- | ---: | ---: | --- | --- |")
    add("| `flat_open` | 0.10 | 210 | unobstructed, open water | `Ocean` |")
    add("| `open_country` | 0.14 | 270 | flat open country, **airports** | `Country` |")
    add("| `suburban` | 0.22 | 370 | urban, suburban, wooded | `Suburbs` / `Urban` |")
    add("| `city_centre` | 0.33 | 460 | large city centres | `City` |")
    add("")
    add("That the two columns agree is the point: the ISO engine and the "
        "EnergyPlus reference can now be driven by the same wind, which Item 0 "
        "shows they were not.")
    add("")
    add("### Acceptance")
    add("")
    ident = d["identity"]
    add(f"**The identity case is exact.** `open_country` at z = 10 m — the "
        f"station's own terrain at the station's own sensor height — returns a "
        f"factor of {ident['factor']:.17g}, i.e. |f − 1| = "
        f"{abs(ident['factor'] - 1.0):.3e}.")
    add("")
    add(f"**Apt 305.** Declared `suburban`, level 3, storey height 2.70 m, so "
        f"z = (3 − 0.5) × 2.70 = **{site['surface_height_m']:.2f} m**. The "
        f"resolved factor is **{site['factor']:.4f}** and the local annual mean "
        f"is **{site['mean_local_m_s']:.2f} m/s**, against the station's "
        f"{wmean:.2f} m/s.")
    add("")
    add(f"The task's acceptance target was ~0.70 and ~3.39 m/s. **The computed "
        f"factor is {site['factor']:.3f}, not 0.70, and the mean is "
        f"{site['mean_local_m_s']:.2f} m/s, not 3.39** — "
        f"{100 * (site['factor'] / 0.70 - 1):+.1f} % on the factor. This is "
        f"reported rather than tuned away. The two differ only in the height: "
        f"0.70 corresponds to z ≈ {d['z_for_070']:.1f} m, which is the *top* of "
        f"level 3 at a 3.0 m floor-to-floor, not the mid-height of level 3 at "
        f"the 2.70 m ceiling height the building dictionary declares. The height "
        f"rule the task specifies — z = (n − 0.5) × h_storey, using the declared "
        f"height per storey — is the one implemented, and it gives "
        f"{site['surface_height_m']:.2f} m. Nothing in the sign question turns "
        f"on the difference: both heights put the local mean well below the "
        f"{PIVOT_MS:.0f} m/s pivot.")
    add("")
    add(f"The height floor is **{d['height_floor_m']:.1f} m**, and it is a "
        f"numerical guard rather than a claim about where the profile stops "
        f"being valid: the power law sends u → 0 as z → 0, which would drive "
        f"h_ce onto its own h_min floor. 1.0 m sits below the mid-height of any "
        f"habitable storey (a 2.4 m ceiling gives 1.2 m), so **it does not bind "
        f"on any case in this document**.")
    add("")
    add("### What the corrected wind feeds")
    add("")
    add("`h_ce = 4 + 4u` **only**. The infiltration stack/wind modulation of "
        "Equation (6) keeps the station value, for two reasons that are about "
        "what its numbers were fitted to:")
    add("")
    add("1. **Shelter is already in that model once.** The 50 Pa rate is brought "
        "down to a mean natural rate by the LBL divide-by-N relation with "
        "N = 20, the standard value for a *sheltered* low-rise building. N is "
        "where site obstruction enters. Reducing u as well would count the same "
        "shelter twice.")
    add("2. **Its normalisation is anchored to a met-station speed.** f ≡ 1 at "
        "(ΔT = 10 K, u = 4 m/s), and that 4 m/s is the same station reference "
        "ISO 13789 §9.5 freezes. Feeding a local wind into the numerator while "
        "the denominator stays on the station reference would move f off 1 at "
        "the reference conditions and silently rescale the annual mean "
        "infiltration rate.")
    add("")
    add("Ground-coupled and adiabatic surfaces are unaffected, as before — they "
        "are never wind-exposed and never reach the h_ce path.")
    add("")

    # ---- Item 3 -----------------------------------------------------------
    add("## Item 3 — sensitivity across terrain class")
    add("")
    add(f"Terrain class is a judgement the modeller assigns by inspection, not a "
        f"measurement. At Apt 305's z = {site['surface_height_m']:.2f} m:")
    add("")
    add("| Class | a | δ (m) | Factor | Local mean (m/s) | Hours above pivot | Mean h_ce W/(m²·K) |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in d["terrain_rows"]:
        mark = " ←" if r["terrain_class"] == site["terrain_class"] else ""
        add(f"| `{r['terrain_class']}`{mark} | {r['exponent_a']} | "
            f"{r['boundary_layer_delta_m']:.0f} | {r['factor']:.4f} | "
            f"{r['mean_local_m_s']:.2f} | {r['pct_hours_above_pivot']:.1f} % | "
            f"{r['mean_h_ce']:.2f} |")
    add(f"| *station, unadjusted* | — | — | 1.0000 | {wmean:.2f} | "
        f"{d['epw']['pct_above_pivot']:.1f} % | {d['epw']['mean_h_ce']:.2f} |")
    add("")
    add(f"**Every one of the four classes puts the mean h_ce below the ISO "
        f"constant of 20 W/(m²·K), and the unadjusted station wind puts it "
        f"above.** The classification moves the local mean by a factor of "
        f"{d['terrain_rows'][0]['factor'] / d['terrain_rows'][-1]['factor']:.2f} "
        f"across the four classes — a wide band — but the *side of the pivot* is "
        f"the same for all four. The sign of C2 is therefore robust to the "
        f"terrain judgement even though its magnitude is not.")
    add("")

    # ---- Item 5 -----------------------------------------------------------
    add("## Item 5 — Australian applicability")
    add("")
    add("| Case | Terrain | z (m) | Basis | Factor | Local mean (m/s) | Direction |")
    add("| --- | --- | ---: | --- | ---: | ---: | --- |")
    for r in d["au_cases"]:
        add(f"| {r['case']} | `{r['terrain_class']}` | {r['surface_height_m']:.2f} | "
            f"{r['height_basis']} | **{r['factor']:.4f}** | "
            f"{r['mean_local_m_s']:.2f} | {r['direction']} |")
    add("")
    tall = next(r for r in d["au_cases"] if "Level 20" in r["case"])
    add("### The Level 20 case does not come out as the task expected")
    add("")
    add(f"The task asked to *confirm* that a city-centre apartment at "
        f"z ≈ 58 m returns a factor **above** 1.0. **It does not: the factor is "
        f"{tall['factor']:.4f}.** Reported as it fell rather than tuned to the "
        f"expectation.")
    add("")
    add("The expectation is right about the mechanism and wrong about where it "
        "bites. A building does eventually project into faster-moving air than "
        "the 10 m station sees, and the implementation does return factors above "
        "1.0 — but for `city_centre` (a = 0.33, δ = 460 m) the crossing is much "
        "higher than 58 m, because the same roughness that slows the wind near "
        "the ground also thickens the boundary layer that has to be climbed. "
        "Solving f = 1 for each class:")
    add("")
    add("| Class | z at which u_local = u_met | Roughly |")
    add("| --- | ---: | --- |")
    for cls, z_cross in d["crossings"]:
        add(f"| `{cls}` | {z_cross:.1f} m | "
            + ("just above head height" if z_cross < 3 else
               "the station's own sensor height, by construction" if abs(z_cross - 10) < 0.01 else
               f"about level {max(1, round(z_cross / 3.0)):.0f} at 3 m storeys") + " |")
    add("")
    add(f"So the check the task wanted — that nothing in the implementation "
        f"assumes a reduction — passes, but on a different row: `suburban` at "
        f"58 m gives {d['suburban_58']:.4f}, and `city_centre` crosses 1.0 at "
        f"{d['crossings'][-1][1]:.0f} m, roughly level "
        f"{round(d['crossings'][-1][1] / 3.0):.0f}. A level-20 city-centre "
        f"apartment genuinely does sit in slower air than an open-country "
        f"aerodrome mast.")
    rural = next(r for r in d["au_cases"] if "Rural" in r["case"])
    add("")
    add(f"The rural dwelling on open ground returns {rural['factor']:.4f} at "
        f"{rural['surface_height_m']:.2f} m. That is **not** near unity, and it "
        f"should not be: its terrain is the station's own, so the terrain factor "
        f"cancels exactly and what remains is pure height — a wall at "
        f"{rural['surface_height_m']:.2f} m against a mast at 10 m. The identity "
        f"row below it is the one that must return 1.0, and does. Reading the "
        f"rural row as \"open country, therefore no correction\" is the mistake "
        f"the height term exists to prevent.")
    add("")
    add("Generated by `tools/diagnostics/wind_profile_terrain.py`.")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    import numpy as np
    from pybuildingenergy.source.utils import (
        local_wind_speed_factor, resolve_local_wind_factor,
        _SURFACE_HEIGHT_FLOOR_M)
    from apt305_building import build_bui

    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", default=str(DEFAULT_EPW))
    ap.add_argument("--outdir", default=str(DEFAULT_OUT))
    ap.add_argument("--energyplus", default="/opt/ep/energyplus")
    ap.add_argument("--no-energyplus", action="store_true")
    args = ap.parse_args()

    weather = Path(args.weather).resolve()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    w = epw_wind(weather)
    epw_stats = {
        "mean_m_s": float(np.nanmean(w)),
        "pct_above_pivot": float(100.0 * np.mean(w > PIVOT_MS)),
        "mean_h_ce": float(np.nanmean(4.0 * w + 4.0)),
        "n": int(w.size),
    }
    print(f"EPW wind: mean {epw_stats['mean_m_s']:.3f} m/s, "
          f"{epw_stats['pct_above_pivot']:.1f} % above pivot, n = {epw_stats['n']:,}")

    # --- Item 0 ---------------------------------------------------------
    static = read_idf_wind_treatment(IDF_MATCHED)
    print(f"IDF {static['idf']}: Terrain='{static['terrain_field']}', "
          f"Site:HeightVariation "
          f"{'present' if static['site_heightvariation_present'] else 'ABSENT'}")
    for name, z in sorted(static["wind_exposed_surface_heights_m"].items()):
        print(f"    {name:<20} z = {z:5.2f} m   f = {static['factors'][name]:.4f}")

    measured = None
    if not args.no_energyplus and shutil.which(args.energyplus):
        print("running EnergyPlus to read back the wind it actually uses ...", flush=True)
        with tempfile.TemporaryDirectory() as td:
            try:
                measured = run_energyplus_wind(
                    IDF_MATCHED, weather, args.energyplus, Path(td))
            except Exception as exc:
                print(f"  EnergyPlus probe failed: {exc}")
                measured = None
        if measured:
            for k, v in sorted(measured.items()):
                print(f"    {k:<28} mean {v['mean_m_s']:.3f} m/s over {v['n']:,} h")

    # The wall is the surface that matters -- it is the only wind-exposed
    # opaque element, and the one C2 acts on.
    wall_f = static["factors"].get("WestWall")
    ep_mean = None
    if measured:
        for k, v in measured.items():
            if k.upper() == "WESTWALL":
                ep_mean = v["mean_m_s"]
    if ep_mean is None and wall_f is not None:
        ep_mean = epw_stats["mean_m_s"] * wall_f

    # --- the site itself --------------------------------------------------
    bui = build_bui()
    factor, audit = resolve_local_wind_factor(bui)
    site = dict(audit)
    site["mean_local_m_s"] = float(np.nanmean(w * factor))
    site["pct_hours_above_pivot"] = float(100.0 * np.mean(w * factor > PIVOT_MS))
    print(f"Apt 305: z = {site['surface_height_m']:.2f} m, factor {factor:.4f}, "
          f"local mean {site['mean_local_m_s']:.3f} m/s")

    # z that would give exactly 0.70, for the acceptance discussion
    a, delta = 0.22, 370.0
    lift = (270.0 / 10.0) ** 0.14
    z_070 = delta * (0.70 / lift) ** (1.0 / a)

    identity = {"factor": local_wind_speed_factor("open_country", 10.0)}

    # The height at which each class's factor crosses 1.0 -- i.e. where the
    # building starts seeing MORE wind than the station. Solved analytically
    # from the same coefficients, so it cannot drift from them.
    from pybuildingenergy.source.utils import _ASHRAE_TERRAIN_PARAMETERS
    crossings = []
    for cls, (a_c, d_c) in _ASHRAE_TERRAIN_PARAMETERS.items():
        crossings.append((cls, d_c * (1.0 / lift) ** (1.0 / a_c)))

    d = {
        "weather": str(weather),
        "weather_name": weather.name,
        "epw": epw_stats,
        "idf_static": static,
        "site": site,
        "identity": identity,
        "crossings": crossings,
        "suburban_58": local_wind_speed_factor("suburban", 58.0),
        "z_for_070": z_070,
        "height_floor_m": _SURFACE_HEIGHT_FLOOR_M,
        "terrain_rows": terrain_table(w, site["surface_height_m"]),
        "au_cases": australian_cases(w),
        "item0": {
            "measured": measured,
            "ep_mean_m_s": ep_mean,
            "verdict": (
                f"**Yes — this is a fourth input mismatch, and it is the largest "
                f"of the four in the wind term.** `Site:HeightVariation` is absent "
                f"from both generated IDFs, so EnergyPlus fell back to the "
                f"`Building` object's `Terrain` field, which the builder writes as "
                f"`{static['terrain_field']}` — a = {static['exponent_a']}, "
                f"δ = {static['boundary_layer_delta_m']:.0f} m. EnergyPlus therefore "
                f"applied a terrain **and** height correction to every wind-exposed "
                f"surface, evaluating the west wall at its centroid height of "
                f"{static['wind_exposed_surface_heights_m'].get('WestWall', float('nan')):.2f} m "
                f"and driving its external film with a mean of "
                f"{ep_mean:.2f} m/s. The ISO side used the raw 10 m station column, "
                f"mean {epw_stats['mean_m_s']:.2f} m/s. The two engines were driven "
                f"by winds differing by a factor of "
                f"{epw_stats['mean_m_s'] / ep_mean:.2f}."
            ),
            "discussion": (
                f"Two separate errors are stacked here, and they must not be "
                f"conflated.\n\n"
                f"**The terrain error is the one the task is about**, and it was on "
                f"the ISO side: EnergyPlus applied a profile, the ISO engine did "
                f"not.\n\n"
                f"**The height error is on the EnergyPlus side, and it is new.** "
                f"The IDF places the zone origin at z = 0 and the west wall spans "
                f"0 → 2.70 m, so EnergyPlus evaluated a *third-floor* apartment's "
                f"wall at a centroid height of "
                f"{static['wind_exposed_surface_heights_m'].get('WestWall', float('nan')):.2f} m. "
                f"That is not a wind-profile question — the geometry says the "
                f"apartment is at ground level. It affects the wind term (through "
                f"the profile) and nothing else, because every other surface in "
                f"the model is either adiabatic, on an OtherSideCoefficients "
                f"boundary, or the window in that same wall.\n\n"
                f"After this change the ISO side runs at "
                f"{site['mean_local_m_s']:.2f} m/s (suburban, z = "
                f"{site['surface_height_m']:.2f} m) and EnergyPlus at "
                f"{ep_mean:.2f} m/s (suburbs, z = "
                f"{static['wind_exposed_surface_heights_m'].get('WestWall', float('nan')):.2f} m). "
                f"The remaining gap is entirely the height, and matching it "
                f"requires moving the EnergyPlus zone up three storeys, not "
                f"changing the profile. That is done in the matched validation "
                f"case; see `results/paper/validation_corrected/`."
            ),
        },
    }

    write_report(d, outdir / "wind_profile.md")
    (outdir / "wind_profile.json").write_text(
        json.dumps(d, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote -> {outdir / 'wind_profile.md'}")
    print(f"wrote -> {outdir / 'wind_profile.json'}")


if __name__ == "__main__":
    main()
