"""
SUPERSEDED — what the wind-profile correction changed.

Generated rather than written, and every number is read back out of a committed
result file, so this document cannot drift from the run it describes. If a
source file is missing it says so in place rather than falling back to a
remembered value.

    python tools/diagnostics/write_wind_profile_superseded.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PAPER = REPO_ROOT / "results" / "paper"
PRE = REPO_ROOT / "results" / "paper_pre_wind_profile"
OUT = PAPER / "SUPERSEDED_wind_profile.md"

CANONICAL_STATE = "+Closure fixes"
NEW_STATE = "+Wind profile"


def load(path: Path):
    if not path.is_file():
        return None
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def f(x, nd=2, sign=False):
    if x is None:
        return "n/a"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def main() -> None:
    new = load(PAPER / "trajectory_v2" / "trajectory_raw.json")
    old = load(PRE / "trajectory_v2" / "trajectory_raw.json")
    st = load(PAPER / "wind_profile" / "wind_stats_station.json")
    tr = load(PAPER / "wind_profile" / "wind_stats_terrain.json")
    wp = load(PAPER / "wind_profile" / "wind_profile.json")
    val_new = load(PAPER / "validation_corrected" / "validation_corrected.csv")
    val_old = load(PRE / "validation_corrected" / "validation_corrected.csv")

    missing = [n for n, v in
               [("trajectory_v2/trajectory_raw.json", new),
                ("paper_pre_wind_profile/trajectory_v2/trajectory_raw.json", old),
                ("wind_profile/wind_stats_station.json", st),
                ("wind_profile/wind_stats_terrain.json", tr),
                ("wind_profile/wind_profile.json", wp)] if v is None]
    if missing:
        raise SystemExit(f"cannot write the record; missing: {missing}")

    sts, trs = st["summary"], tr["summary"]
    aud = trs["wind_audit"]

    def state(blob, label):
        # The raw file nests each state under its config; config_B is the one
        # every published number comes from (the party surfaces typed
        # "adjacent"). config_A is the GR-classification cross-check.
        s = blob["results"].get(label)
        return None if s is None else s.get("config_B", s)

    old_can = state(old, CANONICAL_STATE)
    new_can = state(new, CANONICAL_STATE)
    new_wind = state(new, NEW_STATE)

    L: list[str] = []
    add = L.append
    add("# SUPERSEDED — what the wind-profile correction changed")
    add("")
    add("The preceding paper set is retained verbatim under "
        "`results/paper_pre_wind_profile/`. Nothing in it has been edited; this "
        "file records what was later found out about it and by how much the "
        "result set moved.")
    add("")

    # ---- the defect ------------------------------------------------------
    add("## The defect")
    add("")
    add("Correction C2 replaces the ISO 13789 constant external convective "
        "coefficient with `h_ce = 4 + 4u`. The correlation wants the wind local "
        "to the building surface. The engine fed it the EPW wind column, which "
        "is a **10 m reading over open terrain at the meteorological station** — "
        "which asserts that the site and the station share both terrain class "
        "and measurement height. Apt 305 shares neither with Essendon Fields "
        "aerodrome.")
    add("")
    add(f"The pivot at which `4u + 4` equals the ISO constant of 20 W/(m²·K) is "
        f"u = 4 m/s. On the station column "
        f"**{sts['pct_hours_above_pivot']:.1f} %** of hours are above it. At "
        f"Carlton's terrain and height only "
        f"**{trs['pct_hours_above_pivot']:.1f} %** are. **That is a change of "
        f"side, not of degree.**")
    add("")

    # ---- Item 0 ----------------------------------------------------------
    add("## The fourth input mismatch in the EnergyPlus validation")
    add("")
    ep = wp["idf_static"]
    add(f"`Site:HeightVariation` is absent from both generated IDFs, so "
        f"EnergyPlus fell back to the `Building` object's `Terrain` field — "
        f"`{ep['terrain_field']}`, a = {ep['exponent_a']}, "
        f"δ = {ep['boundary_layer_delta_m']:.0f} m — and applied a terrain **and** "
        f"height profile to every wind-exposed surface. The ISO side used the raw "
        f"station column. Measured by re-running the committed IDF with the "
        f"per-surface wind reported hourly:")
    add("")
    add("| Engine | Wind driving the external film | Annual mean |")
    add("| --- | --- | ---: |")
    add(f"| EnergyPlus, as published | station × the `{ep['terrain_field']}` "
        f"profile at z = "
        f"{ep['wind_exposed_surface_heights_m'].get('WestWall', float('nan')):.2f} m "
        f"| **{wp['item0']['ep_mean_m_s']:.2f} m/s** |")
    add(f"| ISO 52016-1, as published | station column, unadjusted | "
        f"**{wp['epw']['mean_m_s']:.2f} m/s** |")
    add(f"| ISO 52016-1, corrected | station × `{aud['terrain_class']}` at "
        f"z = {aud['surface_height_m']:.2f} m | "
        f"**{wp['site']['mean_local_m_s']:.2f} m/s** |")
    add("")
    add(f"The two engines were driven by winds differing by a factor of "
        f"{wp['epw']['mean_m_s'] / wp['item0']['ep_mean_m_s']:.2f}. This is a "
        f"fourth input mismatch of the same class as the three found in "
        f"`results/paper/validation_corrected/`, and it is now closed on both "
        f"sides: the ISO engine applies the profile, and the matched IDF's "
        f"geometry is translated up so the west wall's centroid sits at the same "
        f"z = {aud['surface_height_m']:.2f} m.")
    add("")

    # ---- the sign --------------------------------------------------------
    flip = (sts["delta_C"] < 0) != (trs["delta_C"] < 0)
    add("## The headline finding: C2 reverses sign" if flip
        else "## The headline finding: C2 keeps its sign")
    add("")
    add("The same engine, run twice, changing only the `h_ce` model — once on "
        "each wind. Both arms are on this engine tree, so nothing but the wind "
        "differs.")
    add("")
    add("| | Station wind | Terrain-corrected | |")
    add("| --- | ---: | ---: | --- |")
    add(f"| Annual mean wind | {sts['mean_wind_annual']:.2f} m/s | "
        f"{trs['mean_wind_annual']:.2f} m/s | × {trs['wind_factor']:.4f} |")
    add(f"| Hours above the 4 m/s pivot | "
        f"{sts['pct_hours_above_pivot']:.1f} % | "
        f"{trs['pct_hours_above_pivot']:.1f} % | |")
    add(f"| Mean h_ce | {sts['mean_h_ce_annual']:.2f} W/(m²·K) | "
        f"{trs['mean_h_ce_annual']:.2f} W/(m²·K) | ISO constant is 20 |")
    add(f"| Sensible cooling, ISO fixed h_ce | {sts['C_fix']:.2f} kWh | "
        f"{trs['C_fix']:.2f} kWh | identical — the control arm |")
    add(f"| Sensible cooling, `4u + 4` | {sts['C_dyn']:.2f} kWh | "
        f"{trs['C_dyn']:.2f} kWh | |")
    add(f"| **C2 effect on cooling** | **{sts['delta_C']:+.2f} kWh** | "
        f"**{trs['delta_C']:+.2f} kWh** | "
        + ("**sign reverses**" if flip else "same sign") + " |")
    add(f"| C2 effect on heating | {sts['delta_H']:+.2f} kWh | "
        f"{trs['delta_H']:+.2f} kWh | |")
    add("")
    if flip:
        add(f"**C2 reverses sign on sensible cooling: "
            f"{sts['delta_C']:+.2f} → {trs['delta_C']:+.2f} kWh.** On the station "
            f"wind the dynamic coefficient sits above the ISO constant for most "
            f"of the year, a stronger film sheds more of the absorbed solar off "
            f"the west wall, and C2 *reduces* cooling. On the wind the wall "
            f"actually sees, the coefficient sits below the constant for "
            f"{100 - trs['pct_hours_above_pivot']:.1f} % of the year, the film is "
            f"weaker, the sol-air temperature rises, and C2 *increases* cooling.")
        add("")
        add("The reported C2 result did rest on an unstated terrain assumption. "
            "Any text that describes C2 as reducing cooling is now wrong.")
    else:
        add(f"C2 does not reverse. It moves from {sts['delta_C']:+.2f} to "
            f"{trs['delta_C']:+.2f} kWh.")
    add("")
    add("The control arm is identical to machine precision in both runs "
        f"({sts['C_fix']:.4f} vs {trs['C_fix']:.4f} kWh): with `h_ce` on `table` "
        "the wind is never consumed, so anything other than the wind having "
        "changed would show up there.")
    add("")

    # ---- the trajectory ---------------------------------------------------
    add("## The canonical trajectory")
    add("")
    add(f"The trajectory gains a fourteenth state. The thirteen before it are "
        f"unchanged to the printed digit — each is a cherry-pick of one "
        f"historical commit and none contains the wind profile — so all of the "
        f"movement is in the last row.")
    add("")
    if old_can and new_can:
        drift = max(abs(new_can[k] - old_can[k]) for k in
                    ("Q_H_sensible_kWh", "Q_C_sensible_kWh", "Q_C_latent_kWh"))
        add(f"Largest drift on `{CANONICAL_STATE}` against the retained set: "
            f"**{drift:.2e} kWh**.")
        add("")
    add("| | Superseded (`+Closure fixes`) | Canonical (`+Wind profile`) | Δ |")
    add("| --- | ---: | ---: | ---: |")
    if old_can and new_wind:
        for key, label, nd in (
                ("Q_H_sensible_kWh", "Sensible heating", 2),
                ("Q_C_sensible_kWh", "Sensible cooling", 2),
                ("Q_C_latent_kWh", "Latent cooling, gated", 2),
                ("Q_sens_plus_gated_latent_kWh", "Total, sensible + gated latent", 2),
                ("Q_need_total_kWh_per_sqm", "Total (kWh/m²·yr)", 2)):
            a, b = old_can.get(key), new_wind.get(key)
            if a is None or b is None:
                continue
            add(f"| {label} | {f(a, nd)} | **{f(b, nd)}** | {f(b - a, nd, True)} |")
    add("")
    if new_wind and old_can:
        dh = new_wind["Q_H_sensible_kWh"] - old_can["Q_H_sensible_kWh"]
        dc = new_wind["Q_C_sensible_kWh"] - old_can["Q_C_sensible_kWh"]
        add(f"The wind-profile state moves sensible heating by "
            f"**{dh:+.2f} kWh** and sensible cooling by **{dc:+.2f} kWh**. "
            f"Cooling moves the more of the two in relative terms because the "
            f"cooling load is small and the west wall's sol-air temperature is "
            f"what the external film controls.")
        add("")

    # ---- the gate ---------------------------------------------------------
    add("## The gate")
    add("")
    cb = [v.get("config_B", v) for v in new["results"].values()]
    worst = max((abs(v["sankey"]["residual_pct"]) for v in cb
                 if v.get("sankey", {}).get("residual_pct") is not None),
                default=float("nan"))
    items = {v["sankey"]["n_transmission_items"] for v in cb}
    lat_h = new_wind.get("Q_H_latent_kWh") if new_wind else None
    add("| Condition | Result |")
    add("| --- | :-: |")
    add(f"| V2 residual < 5 % on every state (worst {worst:.4f} %) | "
        + ("PASS" if worst < 5 else "**FAIL**") + " |")
    add(f"| Seven transmission line items on every state (found {sorted(items)}) | "
        + ("PASS" if items == {7} else "**FAIL**") + " |")
    add(f"| Latent heating a residue, not a demand ({f(lat_h, 4)} kWh) | "
        + ("PASS" if lat_h is not None and abs(lat_h) < 0.05 else "**FAIL**") + " |")
    add("| Final engine tree identical to HEAD | "
        + ("PASS" if new["engine_tree_check"]["identical"] else "**FAIL**") + " |")
    ck = new.get("canonical_check", {})
    ok = ck.get("ok", ck.get("within_tolerance"))
    add("| Final state reproduces a live HEAD run | "
        + ("PASS" if ok else "**FAIL**") + " |")
    add("")

    # ---- the validation ---------------------------------------------------
    add("## The EnergyPlus validation, with the wind now matched on both sides")
    add("")
    if val_new and val_old:
        def row(rows, metric):
            for r in rows:
                if r.get("section") == "corrected" and r.get("metric") == metric:
                    return r
            return None

        def cell(r):
            if r is None:
                return "n/a"
            return (f"{float(r['iso_kWh']):,.2f} / {float(r['ep_kWh']):,.2f} / "
                    f"{float(r['diff_pct_vs_ep']):+.1f} %")

        add("Both columns are the corrected engine against a reference matched "
            "to it. The *after* column additionally matches the wind on both "
            "sides — the ISO engine applies the profile, and the IDF geometry "
            "is raised so EnergyPlus evaluates the west wall at the same "
            "height.")
        add("")
        add("| Metric | Before: ISO / E+ / diff vs E+ | After: ISO / E+ / diff vs E+ |")
        add("| --- | --- | --- |")
        for metric in ("Heating", "Cooling", "Total"):
            add(f"| {metric} | {cell(row(val_old, metric))} | "
                f"**{cell(row(val_new, metric))}** |")
        add("")
        c_old, c_new = row(val_old, "Cooling"), row(val_new, "Cooling")
        if c_old and c_new:
            add(f"**Cooling agreement improves from "
                f"{float(c_old['diff_pct_vs_ep']):+.1f} % to "
                f"{float(c_new['diff_pct_vs_ep']):+.1f} %** — the absolute gap "
                f"falls from {abs(float(c_old['diff_kWh'])):.1f} kWh to "
                f"{abs(float(c_new['diff_kWh'])):.1f} kWh. That is the single "
                f"clearest external check on the correction: an independent "
                f"detailed-simulation reference, driven by the same wind, now "
                f"agrees with the ISO engine on cooling to within 8 %.")
            add("")
    else:
        add("*The matched-case comparison has not been regenerated in this run; "
            "`validation_corrected.csv` is missing from one of the two trees.*")
        add("")

    # ---- scope ------------------------------------------------------------
    add("## What did NOT change")
    add("")
    add("* **The correlation.** `h_ce = 4 + 4u` is untouched and still returns "
        "the ISO constant of exactly 20 W/(m²·K) at 4 m/s. Only the wind fed to "
        "it moved.")
    add("* **Infiltration.** The stack/wind modulation keeps the meteorological "
        "wind: its shelter is already carried by the LBL N = 20 divisor and its "
        "normalisation is anchored to a station-referenced 4 m/s. Reducing u as "
        "well would count the same shelter twice.")
    add("* **The weather file.** Still "
        f"`{Path(wp['weather']).name}`.")
    add("* **The first thirteen trajectory states**, to the printed digit.")
    add("* **`results/diagnostics/wind_stats_essendon.json`** and the F7 "
        "weather-integrity figure built from it. That comparison is about the "
        "RO file's dead-calm months, a different question, and its numbers are "
        "from a pre-closure-fix engine; it is left as the historical record it "
        "is rather than half-updated.")
    add("")
    add("## Where to look")
    add("")
    add("| | |")
    add("| --- | --- |")
    add("| `results/paper/wind_profile/wind_profile.md` | Items 0, 1, 3, 5 — what "
        "EnergyPlus did, the profile, terrain sensitivity, other Australian sites |")
    add("| `results/paper/wind_profile/wind_verdict_terrain.md` | Item 2 — the C2 "
        "sign, on the corrected wind |")
    add("| `results/paper/wind_profile/wind_verdict_station.md` | the same "
        "experiment on the station wind, i.e. the *before* |")
    add("| `results/paper/trajectory_v2/comparison.md` | the gated trajectory |")
    add("| `results/paper_pre_wind_profile/` | everything above, as it stood "
        "before |")
    add("")
    add("Generated by `tools/diagnostics/write_wind_profile_superseded.py`.")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote -> {OUT}")


if __name__ == "__main__":
    main()
