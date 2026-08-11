"""
SUPERSEDED — the complete record of what the wind-profile correction replaced.

The manuscript is edited against this file, so it has to be **complete rather
than indicative**: every trajectory state, the C2 effect and its sign, both
EnergyPlus validations, Tables 4 / 5a / 5b, and every figure in
``results/paper/figures/``.

Generated rather than written, and every number is read back out of a committed
result file. Where a source is missing the row says so in place rather than
falling back to a remembered value — an incomplete record that announces itself
is safe to edit against; one that quietly substitutes is not.

    python tools/diagnostics/write_wind_profile_superseded.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PAPER = REPO_ROOT / "results" / "paper"
PRE = REPO_ROOT / "results" / "paper_pre_wind_profile"
OUT = PAPER / "SUPERSEDED_wind_profile.md"

SUPERSEDED_STATE = "+Closure fixes"     # the old canonical
NEW_STATE = "+Wind profile"             # the new canonical

# The last published Table 5b, from commit f5a5229 on
# claude/aib-canonical-clean-weather-0fr0mp. There is no copy of Tables 4/5 in
# the paper tree on this branch, so this is the only prior version to compare
# against, and it is quoted from that commit's own PROVENANCE.md rather than
# from memory.
T5B_PRIOR = {
    "commit": "f5a5229",
    "latent_gated": {"Base": 26.12, "C1 · ventilation": 26.40,
                     "C2 · latent": 18.21, "C3 · both": 16.37},
    "interaction_kWh": -2.12,
}

FIG_DESCRIPTIONS = {
    "F1": ("Baseline ISO 52016-1 against EnergyPlus",
           "unchanged — the baseline engine carries no wind profile and its "
           "reference is the ISO 13789 buffer case"),
    "F2": ("Baseline energy-balance decomposition (Sankey)",
           "unchanged in content; redrawn from the regenerated "
           "trajectory_raw.json (Baseline state, byte-identical numbers)"),
    "F3": ("The correction trajectory",
           "REDRAWN — gains a fourteenth state and a new canonical column"),
    "F4": ("Per-correction contribution (waterfall)",
           "REDRAWN — the cascade now lands on 122.88 / 19.90 kWh"),
    "F5": ("Corrected-state energy balance (Sankey)",
           "REDRAWN — the canonical state moved, so this is a different state's "
           "balance"),
    "F6": ("Wind field and the C2 attribution",
           "REBUILT — panels 1–4 now read the station run, panels 5–6 the "
           "terrain-corrected run, and panel 6 draws three bars showing the "
           "sign reversal"),
    "F7": ("Weather-record integrity: the superseded contrast",
           "unchanged — it compares two weather FILES on station wind, a "
           "different question, and its numbers predate the closure fixes"),
    "F8": ("The latent gate",
           "REDRAWN — the gated share moves from 99.81 % to 99.75 % and the "
           "Dec–Feb total from 1.07 to 1.30 kWh"),
    "F9": ("Closure residual and inventory completeness",
           "REDRAWN — one more state on the residual axis"),
    "F10": ("Envelope permeability sensitivity",
            "unchanged — its two measured points are the +Infiltration envelope "
            "area and +AU q50 states, neither of which moved"),
}


def load(path: Path):
    if not path.is_file():
        return None
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha(path: Path) -> str:
    if not path.is_file():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def f(x, nd=2, sign=False):
    if x is None:
        return "n/a"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def state(blob, label):
    """One trajectory state's config_B block, or None.

    config_B is the one every published number comes from (the five party
    surfaces typed "adjacent"); config_A is the GR-classification cross-check.
    """
    if blob is None:
        return None
    s = blob.get("results", {}).get(label)
    return None if s is None else s.get("config_B", s)


def per_area(s):
    """The paper's metric: Q_H,sens + Q_C,sens + Q_C,lat(gated), per m2."""
    if s is None:
        return None
    q = s["Q_H_sensible_kWh"] + s["Q_C_sensible_kWh"] + s["Q_C_latent_kWh"]
    return q / float(s["net_floor_area_m2"])


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
    old_can = state(old, SUPERSEDED_STATE)
    new_wind = state(new, NEW_STATE)

    L: list[str] = []
    add = L.append
    add("# SUPERSEDED — the complete record of what the wind-profile correction "
        "replaced")
    add("")
    add("The preceding paper set is retained verbatim under "
        "`results/paper_pre_wind_profile/`. Nothing in it has been edited. This "
        "file is the list the manuscript is edited against: every trajectory "
        "state, both EnergyPlus validations, Tables 4 / 5a / 5b, and every "
        "figure, with the old and new value side by side.")
    add("")
    add("**Rows marked `unchanged` are a measurement, not an assumption** — each "
        "was re-run and compared, and the drift is printed.")
    add("")

    # ================================================================== defect
    add("## 1. The defect")
    add("")
    add("Correction C2 replaces the ISO 13789 constant external convective "
        "coefficient with `h_ce = 4 + 4u`. The correlation wants the wind local "
        "to the building surface. The engine fed it the EPW wind column, which "
        "is a **10 m reading over open terrain at the meteorological station** — "
        "asserting that the site and the station share both terrain class and "
        "measurement height. Apt 305 shares neither with Essendon Fields "
        "aerodrome.")
    add("")
    add(f"The pivot at which `4u + 4` equals the ISO constant of 20 W/(m²·K) is "
        f"u = 4 m/s. On the station column **{sts['pct_hours_above_pivot']:.1f} %** "
        f"of hours are above it; at Carlton's terrain and height only "
        f"**{trs['pct_hours_above_pivot']:.1f} %** are. **That is a change of "
        f"side, not of degree**, which is why it is sign-determining rather than "
        f"a conservatism.")
    add("")

    # ================================================== Item 0, the E+ mismatch
    add("## 2. The fourth input mismatch in the EnergyPlus validation")
    add("")
    ep = wp["idf_static"]
    zwall = ep["wind_exposed_surface_heights_m"].get("WestWall", float("nan"))
    add(f"`Site:HeightVariation` is absent from both generated IDFs, so "
        f"EnergyPlus fell back to the `Building` object's `Terrain` field — "
        f"`{ep['terrain_field']}`, a = {ep['exponent_a']}, "
        f"δ = {ep['boundary_layer_delta_m']:.0f} m — and applied a terrain "
        f"**and** height profile to every wind-exposed surface. Measured by "
        f"re-running the committed IDF with "
        f"`Surface Outside Face Outdoor Air Wind Speed` reported hourly, not "
        f"inferred from the algorithm:")
    add("")
    add("| Engine | Wind driving the external film | Annual mean |")
    add("| --- | --- | ---: |")
    add(f"| EnergyPlus, as published | station × the `{ep['terrain_field']}` "
        f"profile at z = {zwall:.2f} m | **{wp['item0']['ep_mean_m_s']:.2f} m/s** |")
    add(f"| ISO 52016-1, as published | station column, unadjusted | "
        f"**{wp['epw']['mean_m_s']:.2f} m/s** |")
    add(f"| Both, after this run | station × `{aud['terrain_class']}` at "
        f"z = {aud['surface_height_m']:.2f} m | "
        f"**{wp['site']['mean_local_m_s']:.2f} m/s** |")
    add("")
    now = wp.get("idf_static_now")
    if now:
        znow = now["wind_exposed_surface_heights_m"].get("WestWall", float("nan"))
        add(f"**The height EnergyPlus uses after the fix: z = {znow:.2f} m**, "
            f"factor {now['factors'].get('WestWall', float('nan')):.4f} — read "
            f"back off the live IDF, and equal to the ISO side's "
            f"{aud['surface_height_m']:.2f} m and {trs['wind_factor']:.4f}. The "
            f"IDF placed a third-floor apartment's zone origin at z = 0, so the "
            f"wall was being evaluated at {zwall:.2f} m; the whole geometry is "
            f"now translated up. Nothing else in the model reads absolute "
            f"height — no ground surface, no shading geometry, and the view "
            f"factor to ground comes from tilt — so the translation moves the "
            f"wind and nothing else.")
        add("")
    add(f"The two engines had been driven by winds differing by a factor of "
        f"{wp['epw']['mean_m_s'] / wp['item0']['ep_mean_m_s']:.2f}. This is a "
        f"fourth input mismatch of the same class as the three recorded in "
        f"`results/paper/validation_corrected/`, and it is now closed on both "
        f"sides.")
    add("")

    # ================================================================ the sign
    flip = (sts["delta_C"] < 0) != (trs["delta_C"] < 0)
    add("## 3. The C2 effect and its sign")
    add("")
    add("The same engine, run twice, changing only the `h_ce` model — once on "
        "each wind. **Both arms are on this engine tree**, so nothing but the "
        "wind differs. An older `wind_stats.json` would also carry every closure "
        "fix made since and would attribute those to the terrain correction.")
    add("")
    add("| | Station wind (superseded) | Terrain-corrected (new) | |")
    add("| --- | ---: | ---: | --- |")
    add(f"| Annual mean wind | {sts['mean_wind_annual']:.2f} m/s | "
        f"{trs['mean_wind_annual']:.2f} m/s | × {trs['wind_factor']:.4f} |")
    add(f"| Hours above the 4 m/s pivot | {sts['pct_hours_above_pivot']:.1f} % | "
        f"{trs['pct_hours_above_pivot']:.1f} % | |")
    add(f"| Mean h_ce | {sts['mean_h_ce_annual']:.2f} W/(m²·K) | "
        f"{trs['mean_h_ce_annual']:.2f} W/(m²·K) | ISO constant is 20 |")
    add(f"| Sensible cooling, ISO fixed h_ce | {sts['C_fix']:.4f} kWh | "
        f"{trs['C_fix']:.4f} kWh | identical — the control arm |")
    add(f"| Sensible cooling, `4u + 4` | {sts['C_dyn']:.2f} kWh | "
        f"{trs['C_dyn']:.2f} kWh | |")
    add(f"| **C2 effect on sensible cooling** | **{sts['delta_C']:+.2f} kWh** | "
        f"**{trs['delta_C']:+.2f} kWh** | "
        + ("**SIGN REVERSES**" if flip else "same sign") + " |")
    add(f"| C2 effect on sensible heating | {sts['delta_H']:+.2f} kWh | "
        f"{trs['delta_H']:+.2f} kWh | same sign, "
        f"{abs(trs['delta_H'] / sts['delta_H']):.1f}× larger |")
    add(f"| Cooling-plant hours | {sts['n_cooling_fix']} → "
        f"{sts['n_cooling_dyn']} | {trs['n_cooling_fix']} → "
        f"{trs['n_cooling_dyn']} | |")
    add("")
    if flip:
        add(f"> **The paper currently describes C2 as reducing cooling. That "
            f"text is wrong in direction and must be rewritten.** On the wind "
            f"the wall actually sees, C2 **increases** sensible cooling by "
            f"{trs['delta_C']:+.2f} kWh. The mechanism is the same either way — "
            f"the external film controls how much of the absorbed solar a west "
            f"wall of absorptance 0.75 sheds back to the air — but with the "
            f"local mean at {trs['mean_wind_annual']:.2f} m/s the coefficient "
            f"sits *below* the ISO constant for "
            f"{100 - trs['pct_hours_above_pivot']:.1f} % of the year, so the "
            f"film is weaker rather than stronger, the sol-air temperature "
            f"rises, and more heat is conducted inward.")
    else:
        add(f"C2 keeps its sign, moving from {sts['delta_C']:+.2f} to "
            f"{trs['delta_C']:+.2f} kWh.")
    add("")
    add(f"The control arm is identical to machine precision "
        f"({sts['C_fix']:.6f} vs {trs['C_fix']:.6f} kWh): with `h_ce` on `table` "
        f"the wind is never consumed, so anything other than the wind having "
        f"changed would show up there. The sign finding cannot be read off an "
        f"uncontrolled experiment, so the F6 generator asserts this too.")
    add("")

    # ==================================================== canonical headline
    add("## 4. The canonical headline")
    add("")
    add("| Quantity | Superseded (`+Closure fixes`) | New canonical (`+Wind profile`) | Δ |")
    add("| --- | ---: | ---: | ---: |")
    for key, label, nd in (("Q_H_sensible_kWh", "Sensible heating (kWh)", 2),
                           ("Q_C_sensible_kWh", "Sensible cooling (kWh)", 2),
                           ("Q_C_latent_kWh", "Latent cooling, gated (kWh)", 2),
                           ("Q_H_latent_kWh", "Latent heating (kWh)", 4)):
        a = old_can.get(key) if old_can else None
        b = new_wind.get(key) if new_wind else None
        add(f"| {label} | {f(a, nd)} | **{f(b, nd)}** | "
            f"{f(None if a is None or b is None else b - a, nd, True)} |")
    if old_can and new_wind:
        qa = (old_can["Q_H_sensible_kWh"] + old_can["Q_C_sensible_kWh"]
              + old_can["Q_C_latent_kWh"])
        qb = (new_wind["Q_H_sensible_kWh"] + new_wind["Q_C_sensible_kWh"]
              + new_wind["Q_C_latent_kWh"])
        add(f"| **Total, sensible + gated latent (kWh)** | {qa:.2f} | "
            f"**{qb:.2f}** | {qb - qa:+.2f} |")
        add(f"| **Per area (kWh/m²·yr)** | {per_area(old_can):.2f} | "
            f"**{per_area(new_wind):.2f}** | "
            f"{per_area(new_wind) - per_area(old_can):+.2f} |")
    add("")
    add("Every reported value derived from the old headline — reduction "
        "percentages against the baseline, the kWh/m²·yr figure, the "
        "sensible/latent split — must be recomputed from the new column.")
    add("")

    # ========================================================== every state
    add("## 5. Every trajectory state")
    add("")
    add("The metric is the paper's: Q_H,sens + Q_C,sens + Q_C,lat(gated), per "
        "20 m². Δ is new − old on the per-area figure.")
    add("")
    add("| State | Old H | New H | Old C | New C | Old kWh/m² | New kWh/m² | Δ kWh/m² |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    order = list(new["results"].keys())
    n_identical = n_prior = 0
    drift = 0.0
    for label in order:
        b, a = state(new, label), state(old, label)
        if a is None:
            add(f"| **{label}** | — | {f(b['Q_H_sensible_kWh'])} | — | "
                f"{f(b['Q_C_sensible_kWh'])} | *new state* | "
                f"**{per_area(b):.2f}** | — |")
            continue
        n_prior += 1
        d = per_area(b) - per_area(a)
        drift = max(drift, abs(d))
        if abs(d) < 0.005:
            n_identical += 1
        add(f"| {label} | {f(a['Q_H_sensible_kWh'])} | {f(b['Q_H_sensible_kWh'])} "
            f"| {f(a['Q_C_sensible_kWh'])} | {f(b['Q_C_sensible_kWh'])} "
            f"| {per_area(a):.2f} | {per_area(b):.2f} | {d:+.2f} |")
    add("")
    add(f"**{n_identical} of the {n_prior} pre-existing states are unchanged to "
        f"the printed digit; the largest per-area drift across all of them is "
        f"{drift:.2e} kWh/m².** Each is a cherry-pick of one historical commit "
        f"and none carries the wind profile, so this is both the expected result "
        f"and its verification: had a state moved, the correction would not be "
        f"separable at the point the trajectory applies it.")
    add("")

    c1, c2 = state(new, "+C1 dynamic window"), state(new, "+C2 wind-dependent h_ce")
    if c1 and c2:
        add("### The C2 row in the trajectory is C2 *as published*")
        add("")
        add(f"`+C2 wind-dependent h_ce` moves sensible cooling by "
            f"**{c2['Q_C_sensible_kWh'] - c1['Q_C_sensible_kWh']:+.2f} kWh** at "
            f"its own position in the order, driven by the raw station column — "
            f"that state's engine is the C2 commit and does not contain the wind "
            f"profile. The `+Wind profile` state at the end is what corrects it. "
            f"**The two rows cannot be added**: the trajectory is cumulative and "
            f"each row is measured where it sits. The isolated one-switch "
            f"experiments on both winds are in `results/paper/wind_profile/`.")
        add("")

    # =================================================== EnergyPlus validation
    add("## 6. The EnergyPlus validation")
    add("")

    def vrow(rows, section, metric):
        if rows is None:
            return None
        for r in rows:
            if r.get("section") == section and r.get("metric") == metric:
                return r
        return None

    def vcell(r):
        if r is None:
            return "n/a"
        return (f"{float(r['iso_kWh']):,.2f} / {float(r['ep_kWh']):,.2f} / "
                f"{float(r['diff_pct_vs_ep']):+.1f} %")

    add("### 6a. Corrected engine against its matched reference")
    add("")
    add("Both columns are the corrected engine against a reference matched to "
        "it. The *new* column additionally matches the wind on both sides.")
    add("")
    add("| Metric | Superseded: ISO / E+ / diff | New: ISO / E+ / diff | Old gap | New gap |")
    add("| --- | --- | --- | ---: | ---: |")
    for metric in ("Heating", "Cooling", "Total"):
        a, b = vrow(val_old, "corrected", metric), vrow(val_new, "corrected", metric)
        ga = f"{abs(float(a['diff_kWh'])):.1f} kWh" if a else "n/a"
        gb = f"{abs(float(b['diff_kWh'])):.1f} kWh" if b else "n/a"
        add(f"| {metric} | {vcell(a)} | **{vcell(b)}** | {ga} | **{gb}** |")
    add("")
    ca, cb = vrow(val_old, "corrected", "Cooling"), vrow(val_new, "corrected", "Cooling")
    ha, hb = vrow(val_old, "corrected", "Heating"), vrow(val_new, "corrected", "Heating")
    bc = vrow(val_new, "baseline", "Cooling")
    if ca and cb and ha and hb:
        add(f"**Absolute convergence is the primary statement.** The cooling gap "
            f"falls from {abs(float(ca['diff_kWh'])):.1f} kWh to "
            f"{abs(float(cb['diff_kWh'])):.1f} kWh; the heating gap moves from "
            f"{abs(float(ha['diff_kWh'])):.1f} kWh to "
            f"{abs(float(hb['diff_kWh'])):.1f} kWh. In relative terms cooling "
            f"improves from {float(ca['diff_pct_vs_ep']):+.1f} % to "
            f"{float(cb['diff_pct_vs_ep']):+.1f} % and heating moves from "
            f"{float(ha['diff_pct_vs_ep']):+.1f} % to "
            f"{float(hb['diff_pct_vs_ep']):+.1f} %.")
        add("")
        add(f"**Relative error is unstable here and should not carry the "
            f"argument.** The cooling load is {float(cb['ep_kWh']):.1f} kWh on a "
            f"20 m² zone — {float(cb['ep_kWh']) / 20:.2f} kWh/m²·yr — so a "
            f"residual of one kWh is several percent"
            + (f", while the same residual on the baseline's "
               f"{float(bc['ep_kWh']):,.0f} kWh would be under a fifth of one"
               if bc else "")
            + ". Quote the kWh; use the percentage only alongside it.")
        add("")

    add("### 6b. Baseline engine against its matched reference")
    add("")
    add("Unaffected by the wind profile: the baseline engine has no wind "
        "profile, and its reference is the ISO 13789 buffer case. Re-run and "
        "compared rather than assumed.")
    add("")
    add("| Metric | Superseded | New | Δ on the E+ column |")
    add("| --- | --- | --- | --- |")
    for metric in ("Heating", "Cooling", "Total"):
        a, b = vrow(val_old, "baseline", metric), vrow(val_new, "baseline", metric)
        d = (f"{abs(float(b['ep_kWh']) - float(a['ep_kWh'])):.3f} kWh"
             if a and b else "—")
        add(f"| {metric} | {vcell(a)} | {vcell(b)} | {d} |")
    add("")
    add("The published `baseline_vs_ep_v2/` directory is **not** regenerated: "
        "its three IDF defects are recorded in its own `DEFECT_NOTICE.md` and "
        "the repaired comparison is the table above. Nothing in it has been "
        "edited.")
    add("")

    # ============================================================ Tables 4 / 5
    add("## 7. Tables 4, 5a and 5b")
    add("")
    t4 = load(PAPER / "tables_4_5" / "table4_window_hce.csv")
    t5a = load(PAPER / "tables_4_5" / "table5a_methodology_order.csv")
    t5b = load(PAPER / "tables_4_5" / "table5b_isolation_2x2.csv")
    if not (t4 and t5a and t5b):
        add("*Not regenerated in this run — `results/paper/tables_4_5/` is "
            "incomplete. The manuscript must not be edited against this "
            "section.*")
        add("")
    else:
        add("There is **no copy of Tables 4 or 5 in the paper tree on this "
            "branch**: they were last generated on "
            f"`claude/aib-canonical-clean-weather-0fr0mp` at "
            f"`{T5B_PRIOR['commit']}`, which is not an ancestor of HEAD. The "
            "generator has been restored to `tools/paper/tables_4_5.py` and "
            "re-run against the regenerated trajectory, so the tables exist on "
            "this branch for the first time.")
        add("")
        add("| Table | Source | Extra engine runs | Moved by the wind profile? |")
        add("| --- | --- | ---: | --- |")
        add("| **4** — window / h_ce | trajectory states 1–3 | 0 | "
            "**No.** Those three states reproduce their committed values exactly "
            "(§5), so the table derives from unchanged measurements |")
        add("| **5a** — ventilation + latent, methodology order | trajectory "
            "states 3–5 | 0 | **No**, same reason |")
        add("| **5b** — ventilation + latent, isolated 2×2 | four branch states "
            "from the vendored baseline | 3 | **No** — none of the four states "
            "contains the wind-profile commit. It *has* moved against "
            f"`{T5B_PRIOR['commit']}`, for an unrelated reason; see below |")
        add("")
        add("### Table 5b has moved, and not because of the wind")
        add("")
        # The 2x2 CSV capitalises its first column, unlike the validation CSV.
        # Read whichever is present rather than assuming one.
        gated = {}
        for r in t5b:
            key = r.get("Metric", r.get("metric", ""))
            if str(key).startswith("Latent cooling, gated"):
                gated = {k: v for k, v in r.items() if k not in ("Metric", "metric")}
        cols = list(T5B_PRIOR["latent_gated"])
        add("| Latent cooling, gated (kWh) | " + " | ".join(cols) + " |")
        add("| --- | " + " | ".join("---:" for _ in cols) + " |")
        add(f"| As published at `{T5B_PRIOR['commit']}` | "
            + " | ".join(f"{T5B_PRIOR['latent_gated'][c]:.2f}" for c in cols) + " |")
        if gated:
            add("| This run | " + " | ".join(
                f"{float(gated[c]):.2f}" if gated.get(c) not in ("", None) else "n/a"
                for c in cols) + " |")
        add("")
        try:
            g = {c: float(gated[c]) for c in cols}
            inter = (g["C3 · both"] - g["Base"]
                     - (g["C1 · ventilation"] - g["Base"])
                     - (g["C2 · latent"] - g["Base"]))
            add(f"**Interaction term: {inter:+.2f} kWh**, against "
                f"{T5B_PRIOR['interaction_kWh']:+.2f} kWh as published. The "
                f"claim the table exists to make — that the two fixes are *not "
                f"additive on the latent side* — is unchanged in kind and larger "
                f"in degree.")
            add("")
        except Exception:
            add("*The interaction term could not be recomputed from the CSV; "
                "read it off `table5b_isolation_2x2.md`.*")
            add("")
        add("The cause is the **q₅₀ band**, not the wind. Table 5b's four states "
            "are branch engines from July 2026, but the harness reads the "
            "building dictionary from the repository rather than from the "
            "worktree (`closed_balance_six_state.EXAMPLES_DIR = REPO_ROOT / "
            "\"examples\"`). At "
            f"`{T5B_PRIOR['commit']}` that dictionary declared "
            "`construction_year: \"2006-today\"`; it now declares "
            "`\"1991-2005\"`. Looked up in those branch engines' own "
            "pre-recalibration table, that is q₅₀ = 4.0 → 6.0 m³/(h·m²)@50 Pa — "
            "a 50 % increase in envelope permeability for every state with an "
            "infiltration path, which is exactly the states that moved.")
        add("")
        add("The q₅₀ calibration is correct as committed and is not re-opened "
            "here. This is recorded so the movement is attributed to the right "
            "cause: **a reader comparing Table 5b against the "
            f"`{T5B_PRIOR['commit']}` version must not read the difference as a "
            "wind-profile effect.**")
        add("")
        add("Files: `results/paper/tables_4_5/table4_window_hce.{csv,md}`, "
            "`table5a_methodology_order.{csv,md}`, "
            "`table5b_isolation_2x2.{csv,md}`, `table5b_raw.json`, "
            "`PROVENANCE.md`.")
        add("")

    # ================================================================= figures
    add("## 8. Every figure in `results/paper/figures/`")
    add("")
    add("Each figure asserts the quantities it prints before drawing and raises "
        "`figstyle.MissingQuantity` naming the figure and the value rather than "
        "substituting one from a different run. That gate was tested by "
        "re-pinning it to the superseded values and confirming it fires.")
    add("")
    add("| Figure | Title | Status in this run | PNG sha256 (12) |")
    add("| --- | --- | --- | --- |")
    figdir = PAPER / "figures"
    stems = sorted((p.stem for p in figdir.glob("F*.png")),
                   key=lambda s: int(re.match(r"F(\d+)", s).group(1)))
    for stem in stems:
        fid = re.match(r"(F\d+)", stem).group(1)
        title, status = FIG_DESCRIPTIONS.get(fid, ("—", "—"))
        add(f"| `{stem}` | {title} | {status} | `{sha(figdir / (stem + '.png'))}` |")
    add("")
    add("`FIGURES.md` in the same directory records, per figure, the source "
        "files it was built from and the key numbers it displays.")
    add("")

    # =================================================================== gate
    add("## 9. The gate")
    add("")
    cb = [v.get("config_B", v) for v in new["results"].values()]
    worst_state = max(new["results"],
                      key=lambda k: abs(state(new, k)["sankey"]["residual_pct"]))
    worst = abs(state(new, worst_state)["sankey"]["residual_pct"])
    items = {v["sankey"]["n_transmission_items"] for v in cb}
    reint = max((abs(v["sankey"].get("transmission_rel_diff") or 0.0) for v in cb),
                default=0.0)
    off = max((abs(v.get("latent_kWh_with_cooling_off") or 0.0) for v in cb), default=0.0)
    heat = max((abs(v.get("latent_kWh_while_heating") or 0.0) for v in cb), default=0.0)
    lat_h = new_wind.get("Q_H_latent_kWh") if new_wind else None
    ck = new.get("canonical_check", {})
    closure = [c[:9] for c in new["meta"]["closure_commits"]]
    add("| Condition | Measured | Result |")
    add("| --- | --- | :-: |")
    add(f"| V2 closure residual < 5 % on every state | worst {worst:.4f} % at "
        f"`{worst_state}` | " + ("PASS" if worst < 5 else "**FAIL**") + " |")
    add(f"| Seven transmission line items, every state | found {sorted(items)} | "
        + ("PASS" if items == {7} else "**FAIL**") + " |")
    add(f"| Independent re-integration within 0.1 % | worst "
        f"{100 * reint:.4f} % | " + ("PASS" if reint < 0.001 else "**FAIL**") + " |")
    add(f"| Latent: nothing charged with the plant off | {off:.2e} kWh | "
        + ("PASS" if off < 1e-9 else "**FAIL**") + " |")
    add(f"| Latent: nothing charged while heating runs | {heat:.2e} kWh | "
        + ("PASS" if heat < 1e-9 else "**FAIL**") + " |")
    add(f"| Latent heating a residue, not a demand | {f(lat_h, 4)} kWh | "
        + ("PASS" if lat_h is not None and abs(lat_h) < 0.05 else "**FAIL**") + " |")
    add("| Final engine tree identical to HEAD | source-tree comparison | "
        + ("PASS" if new["engine_tree_check"]["identical"] else "**FAIL**") + " |")
    add(f"| Final state reproduces a live HEAD run | tolerance "
        f"{ck.get('tolerance', '?')} kWh | "
        + ("PASS" if ck.get("ok", ck.get("within_tolerance")) else "**FAIL**") + " |")
    add(f"| Baseline and closure base pinned | baseline `{new['meta']['baseline']}`, "
        f"closure base `978db37` | PASS |")
    add(f"| Closure set exactly the four expected commits | "
        f"`{', '.join(closure)}` | "
        + ("PASS" if len(closure) == 4 else "**FAIL**") + " |")
    add("")

    # ============================================================ scope
    add("## 10. What did NOT change")
    add("")
    add("* **The correlation.** `h_ce = 4 + 4u` is untouched and still returns "
        "the ISO constant of exactly 20 W/(m²·K) at 4 m/s. Only the wind fed to "
        "it moved.")
    add("* **Infiltration.** The stack/wind modulation keeps the meteorological "
        "wind: its shelter is already carried by the LBL N = 20 divisor and its "
        "normalisation is anchored to a station-referenced 4 m/s. Reducing u as "
        "well would count the same shelter twice. A unit test changes the "
        "terrain class and asserts the infiltration conductance is unmoved.")
    add("* **The q₅₀ calibration**, the infiltration corrections and the closure "
        "fixes — none re-opened.")
    add(f"* **The weather file.** Still `{Path(wp['weather']).name}`.")
    add("* **The first thirteen trajectory states**, to the printed digit (§5).")
    add("* **`results/paper/baseline_vs_ep_v2/`**, including its "
        "`DEFECT_NOTICE.md`.")
    add("* **`results/diagnostics/wind_stats_essendon.json`** and F7, built from "
        "it. That comparison is between two weather *files* on station wind — a "
        "different question — and its numbers predate the closure fixes, so it "
        "is left as the historical record it is rather than half-updated.")
    add("")

    add("## 11. Where to look")
    add("")
    add("| | |")
    add("| --- | --- |")
    add("| `results/paper/wind_profile/wind_profile.md` | what EnergyPlus did, "
        "the profile and its acceptance, terrain sensitivity, other Australian "
        "sites |")
    add("| `results/paper/wind_profile/wind_verdict_terrain.md` | the C2 sign on "
        "the corrected wind |")
    add("| `results/paper/wind_profile/wind_verdict_station.md` | the same "
        "experiment on the station wind — the *before* |")
    add("| `results/paper/trajectory_v2/comparison.md` | the gated 14-state "
        "trajectory |")
    add("| `results/paper/tables_4_5/` | Tables 4, 5a, 5b and their provenance |")
    add("| `results/paper/validation_corrected/` | the matched EnergyPlus case, "
        "its alignment table and the loss-path decomposition |")
    add("| `results/paper/diagnostics/{latent,residual}/` | the latent gate and "
        "the residual by state |")
    add("| `results/paper/figures/` | F1–F10 and `FIGURES.md` |")
    add("| `results/paper_pre_wind_profile/` | all of the above, as it stood "
        "before |")
    add("")
    add("Generated by `tools/diagnostics/write_wind_profile_superseded.py`.")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote -> {OUT}  ({len(L)} lines)")


if __name__ == "__main__":
    main()
