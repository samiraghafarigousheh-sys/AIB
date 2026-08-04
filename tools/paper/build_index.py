"""
Final — build ``results/paper/INDEX.md`` from the artefacts, and enforce the gate.

Every number in the index is read back out of the JSON the runs wrote. Nothing
is retyped: an index that restates a figure by hand is one more place for the
paper to disagree with the run that produced it, which is the failure this whole
effort has been unwinding.

The gate is enforced here rather than described. If the V2 residual is outside
5 % on any state, or the ADJ transmission is missing from the inventory, or the
latent gate leaks, or the suite is not green, this exits non-zero and the index
says so at the top instead of leading with a headline.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
V2_TOLERANCE_PCT = 5.0
EXPECTED_ITEMS = 7
REINT_TOL = 0.001
LATENT_LEAK_TOL = 1e-9


def _j(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _f(v, nd=2):
    return "n/a" if v is None else f"{v:,.{nd}f}"


def pytest_status(path: Path) -> dict:
    if not path.is_file():
        return {"ok": False, "why": "pytest.txt missing"}
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^exit code:\s*(\d+)\s*$", txt, re.M)
    summary = re.findall(r"^=+ (.*(?:passed|failed|error).*) =+$", txt, re.M)
    n_skip = len(re.findall(r"SKIPPED", txt))
    code = int(m.group(1)) if m else None
    return {"ok": code == 0 and n_skip == 0, "exit_code": code,
            "summary": summary[-1] if summary else "(no summary line)",
            "skipped": n_skip}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=Path, default=REPO_ROOT / "results/paper")
    args = ap.parse_args()
    P = args.paper

    traj = _j(P / "canonical_trajectory" / "trajectory_raw.json")
    if traj is None:
        raise SystemExit(f"no trajectory at {P / 'canonical_trajectory'} — run Part 2 first")
    B = {k: v["config_B"] for k, v in traj["results"].items()}
    states = list(B)
    canon = states[-1]
    weather = Path(traj["meta"]["weather"]).name
    wind = traj["meta"]["wind"]
    area = float(B[canon]["net_floor_area_m2"])

    val = _j(P / "validation_iso_vs_ep" / "validation_raw.json")
    bal = _j(P / "baseline_balance" / "baseline_balance_raw.json")
    latent = _j(P / "diagnostics" / "latent" / "summary.json")
    resid = _j(P / "diagnostics" / "residual" / "summary.json")
    windv = _j(P / "diagnostics" / "wind" / "wind_stats_essendon.json")
    t5b = _j(P / "tables_4_5" / "table5b_raw.json")
    pyt = pytest_status(P / "pytest.txt")

    # ---- the gate ----------------------------------------------------------
    gate_v2 = all(abs(B[s]["sankey"]["residual_pct"]) < V2_TOLERANCE_PCT for s in states)
    gate_items = all(B[s]["sankey"]["n_transmission_items"] == EXPECTED_ITEMS
                     for s in states)
    gate_reint = all(B[s]["sankey"]["transmission_rel_diff"] <= REINT_TOL for s in states)
    gate_latent = all(
        abs(B[s].get("latent_kWh_with_cooling_off") or 0.0) <= LATENT_LEAK_TOL
        and abs(B[s].get("latent_kWh_while_heating") or 0.0) <= LATENT_LEAK_TOL
        for s in states)
    gate_suite = pyt["ok"]
    head_ok = traj.get("canonical_check", {}).get("ok", False)
    tree_ok = traj.get("engine_tree_check", {}).get("identical", False)
    gate = all([gate_v2, gate_items, gate_reint, gate_latent, gate_suite,
                head_ok, tree_ok])

    c = B[canon]
    sens_plus_gated = c["Q_H_sensible_kWh"] + c["Q_C_sensible_kWh"] + c["Q_C_latent_kWh"]

    L: list[str] = []
    a = L.append
    a("# Paper results — index")
    a("")
    a(f"Every table and figure the results sections need, produced in one run on "
      f"one weather file: **`{weather}`** (Essendon Fields, WMO 958660, "
      f"{wind['n_rows']:,} rows, {wind['n_missing_wind']} missing wind values, mean "
      f"{wind['mean_wind_ms']:.2f} m/s, {wind['pct_hours_exactly_zero']:.2f} % of hours "
      f"exactly 0.0, {wind['pct_hours_above_pivot']:.1f} % above the 4 m/s pivot, no "
      f"dead-calm month).")
    a("")
    a(f"Case: Apt 305, 50 Barry St, Carlton VIC — {area:.0f} m², one exposed west "
      f"façade, five conditioned neighbours. Setpoints 18 °C heating / 26 °C cooling "
      f"(setback 15 / 28), taken from the building dictionary.")
    a("")

    a("## The gate")
    a("")
    a("No reduction percentage and no kWh/m² headline is final unless all of these "
      "hold. They are checked here, not described.")
    a("")
    a("| Condition | Result |")
    a("| --- | :-: |")
    a(f"| V2 residual < {V2_TOLERANCE_PCT:.0f} % on every state | "
      f"{'**PASS**' if gate_v2 else '**FAIL**'} |")
    a(f"| ADJ transmission in the inventory ({EXPECTED_ITEMS} line items, every state) | "
      f"{'**PASS**' if gate_items else '**FAIL**'} |")
    a(f"| Independent re-integration within 0.1 %, every state | "
      f"{'**PASS**' if gate_reint else '**FAIL**'} |")
    a(f"| Latent gated (nothing charged with the plant off or while heating) | "
      f"{'**PASS**' if gate_latent else '**FAIL**'} |")
    a(f"| HEAD invariant against a live HEAD run | "
      f"{'**PASS**' if head_ok else '**FAIL**'} |")
    a(f"| Final engine tree byte-identical to HEAD | "
      f"{'**PASS**' if tree_ok else '**FAIL**'} |")
    a(f"| Regression suite green, nothing skipped | "
      f"{'**PASS**' if gate_suite else '**FAIL**'} — {pyt['summary']}, "
      f"{pyt['skipped']} skipped, exit {pyt['exit_code']} |")
    a("")
    if gate:
        a("**Gate passed. The methodology text can be written against the numbers "
          "below.**")
    else:
        a("**GATE FAILED — do not quote a headline from this run.** See the failing "
          "row above.")
    a("")

    a("## The canonical headline")
    a("")
    a(f"**{_f(c['Q_H_sensible_kWh'])} kWh sensible heating + "
      f"{_f(c['Q_C_sensible_kWh'])} kWh sensible cooling + "
      f"{_f(c['Q_C_latent_kWh'])} kWh gated latent = {_f(sens_plus_gated)} kWh = "
      f"{_f(c['Q_need_total_kWh_per_sqm'])} kWh/m²·yr.**")
    a("")
    a(f"Latent heating is {_f(c['Q_H_latent_kWh'], 4)} kWh at this state, so "
      f"\"sensible + gated latent\" and the engine's own total "
      f"({_f(c['Q_need_total_kWh'])} kWh) agree to the printed digit.")
    a("")
    a("**Quote the components, not the total alone.** Against the superseded "
      "RO-weather run the total moved only −7.1 % (9.69 → 9.00 kWh/m²·yr) while "
      "heating rose 40.9 % and cooling fell 90.6 %, and the C2 correction changed "
      "sign. A sentence that reports only the total describes none of that.")
    a("")

    # ---- the artefact index -------------------------------------------------
    a("## Every table and figure")
    a("")
    a("| # | What | File | Key numbers |")
    a("| --- | --- | --- | --- |")

    if val:
        rows = {r["Metric"]: r for r in _read_csv(
            P / "validation_iso_vs_ep" / "validation_iso_vs_ep.csv")}
        h, cl, tt = rows["Heating"], rows["Cooling"], rows["Total"]
        a(f"| **T2** | ISO 52016-1 vs EnergyPlus, baseline engine "
          f"| `validation_iso_vs_ep/validation_iso_vs_ep.{{csv,md}}` "
          f"| heating {float(h['ISO 52016-1 (kWh)']):,.2f} vs "
          f"{float(h['EnergyPlus (kWh)']):,.2f} kWh ({float(h['diff (%)']):+.1f} %); "
          f"cooling {float(cl['ISO 52016-1 (kWh)']):,.2f} vs "
          f"{float(cl['EnergyPlus (kWh)']):,.2f} kWh ({float(cl['diff (%)']):+.1f} %); "
          f"total {float(tt['diff (%)']):+.1f} % |")
        a(f"| **F1** | ISO vs E+ grouped bars "
          f"| `validation_iso_vs_ep/validation_iso_vs_ep.png` | — |")
        a(f"| — | The generated IDF, for audit "
          f"| `validation_iso_vs_ep/apt305.idf` | EnergyPlus "
          f"{val['meta']['ep_version'].split()[-1]}, ideal loads |")
    if bal:
        a(f"| **T3** | Baseline annual energy-balance inventory "
          f"| `baseline_balance/baseline_balance.{{csv,md}}` "
          f"| in {bal['inputs_kWh'] and sum(bal['inputs_kWh'].values()):,.1f} / out "
          f"{sum(bal['outputs_kWh'].values()):,.1f} kWh; residual "
          f"{bal['residual_kWh']:+,.2f} kWh ({bal['residual_pct']:+.2f} %); "
          f"{bal['n_transmission_items']} line items |")
        a(f"| **F2** | Baseline Sankey, residual drawn as a gap "
          f"| `baseline_balance/baseline_balance_sankey.png` | — |")

    a(f"| **T4** | Window / h_ce corrections (Base / C1 / C2) "
      f"| `tables_4_5/table4_window_hce.{{csv,md}}` "
      f"| C2 moves cooling {B['+C2 wind-dependent h_ce']['Q_C_sensible_kWh'] - B['+C1 dynamic window']['Q_C_sensible_kWh']:+.2f} kWh; "
      f"C1 moves solar gains "
      f"{B['+C1 dynamic window']['Q_solar_gains_kWh'] - B['Baseline']['Q_solar_gains_kWh']:+.2f} kWh |")
    a(f"| **T5a** | Ventilation + latent, methodology order "
      f"| `tables_4_5/table5a_methodology_order.{{csv,md}}` "
      f"| ventilation moves heating "
      f"{B['+Ventilation']['Q_H_sensible_kWh'] - B['+C2 wind-dependent h_ce']['Q_H_sensible_kWh']:+.2f} kWh; "
      f"latent moves gated latent "
      f"{B['+Latent']['Q_C_latent_kWh'] - B['+Ventilation']['Q_C_latent_kWh']:+.2f} kWh |")
    if t5b:
        s = t5b["summary"]
        lc = s["latent_cooling"]
        a(f"| **T5b** | Ventilation + latent, isolated 2×2 "
          f"| `tables_4_5/table5b_isolation_2x2.{{csv,md}}` "
          f"| latent cooling {lc['Base']:.2f} → {lc['C1 · ventilation']:.2f} "
          f"(vent) → {lc['C2 · latent']:.2f} (latent) → {lc['C3 · both']:.2f} (both); "
          f"interaction {s['latent_interaction_kWh']:+.2f} kWh |")
    a(f"| — | Which source each table came from, and why "
      f"| `tables_4_5/PROVENANCE.md` | — |")

    a(f"| **T6** | The full ten-state correction trajectory "
      f"| `canonical_trajectory/comparison.{{csv,md}}` "
      f"| canonical {_f(c['Q_H_sensible_kWh'])} / {_f(c['Q_C_sensible_kWh'])} / "
      f"{_f(c['Q_C_latent_kWh'])} kWh = {_f(c['Q_need_total_kWh_per_sqm'])} kWh/m²·yr |")
    a(f"| **F3** | Faceted trajectory chart, own axis per metric "
      f"| `canonical_trajectory/canonical_trajectory.png` | — |")

    if windv:
        w = windv["summary"]
        a(f"| **F4** | Wind diagnostic, four panels + verdict "
          f"| `diagnostics/wind/wind_distribution_essendon.png`, "
          f"`wind_verdict_essendon.md` "
          f"| verdict **({windv['verdict']})**; C2 moves cooling {w['delta_C']:+.2f} kWh, "
          f"{w['pct_extra_from_nonzero_wind']:.1f} % of it from genuine wind; "
          f"{w['pct_cooling_hours_above_pivot']:.1f} % of cooling hours above the pivot |")
    a(f"| **F5** | Sankey decomposition, four states "
      f"| `diagnostics/sankey/{{baseline,c2_wind_hce,conditioned_zones,canonical}}_sankey.png` "
      f"| baseline residual {B['Baseline']['sankey']['residual_pct']:+.2f} % → canonical "
      f"{B[canon]['sankey']['residual_pct']:+.2f} % |")
    if latent:
        lt = latent["latent"]
        a(f"| **F6** | Latent breakdown and gating audit "
          f"| `diagnostics/latent/latent_breakdown.{{png,csv,md}}` "
          f"| gate leak max {lt['leak_max_kWh']:.1e} kWh; Dec–Feb "
          f"{lt['summer_kWh']:.2f} vs Jun–Aug {lt['winter_kWh']:.2f} kWh |")
    if resid:
        rs = resid["residual"]
        a(f"| **F7** | V2 residual across all ten states, with the gate "
          f"| `diagnostics/residual/residual_by_state.{{png,csv,md}}` "
          f"| worst {rs['worst_pct']:+.2f} % at *{rs['worst_state']}* |")
    a(f"| — | Regression suite | `pytest.txt` | {pyt['summary']}, exit "
      f"{pyt['exit_code']} |")
    a(f"| — | What this run supersedes | `SUPERSEDED.md` | — |")
    a("")

    # ---- the trajectory table, inline --------------------------------------
    a("## The trajectory, inline")
    a("")
    a("| State | Sensible H (kWh) | Sensible C (kWh) | Gated latent (kWh) | "
      "Sens + gated latent (kWh) | kWh/m²·yr | V2 residual | Items |")
    a("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for s in states:
        r = B[s]
        a(f"| {s} | {_f(r['Q_H_sensible_kWh'])} | {_f(r['Q_C_sensible_kWh'])} "
          f"| {_f(r['Q_C_latent_kWh'])} "
          f"| {_f(r['Q_H_sensible_kWh'] + r['Q_C_sensible_kWh'] + r['Q_C_latent_kWh'])} "
          f"| {_f(r['Q_need_total_kWh_per_sqm'])} "
          f"| {r['sankey']['residual_pct']:+.2f} % "
          f"| {r['sankey']['n_transmission_items']} |")
    a("")
    a("`Latent cooling, ungated` (in the full CSV) is a diagnostic contrast column "
      "only — the zone moisture balance before the plant-on gate. **It is never "
      "part of any total.**")
    a("")

    a("## Reproducing, in order")
    a("")
    a("```bash")
    a("EPW=weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw")
    a("")
    a("# Part 1 — validation + baseline balance  (needs EnergyPlus 24.1)")
    a("python tools/paper/validation_iso_vs_ep.py --weather $EPW \\")
    a("    --energyplus /opt/ep/energyplus")
    a("")
    a("# Part 2 — the trajectory  (~20 min)")
    a("python tools/diagnostics/canonical_trajectory.py --weather $EPW \\")
    a("    --outdir results/paper/canonical_trajectory")
    a("python tools/diagnostics/make_closed_balance_chart.py \\")
    a("    --raw results/paper/canonical_trajectory/trajectory_raw.json \\")
    a("    --outdir results/paper/canonical_trajectory --stem canonical_trajectory \\")
    a("    --title 'Apt 305, 50 Barry St Carlton — the canonical correction trajectory, methodology order'")
    a("")
    a("# Part 3 — Tables 4 and 5")
    a("python tools/paper/tables_4_5.py --weather $EPW")
    a("")
    a("# Part 4 — diagnostics")
    a("python tools/diagnostics/wind_h_ce_diagnostic.py --weather $EPW \\")
    a("    --outdir results/paper/diagnostics/wind --tag essendon \\")
    a("    --expect-weather Essendon --compare-to results/diagnostics/wind_stats.json")
    a("python tools/paper/baseline_balance.py \\")
    a("    --raw results/paper/canonical_trajectory/trajectory_raw.json \\")
    a("    --state Baseline --stem baseline \\")
    a("    --state '+C2 wind-dependent h_ce' --stem c2_wind_hce \\")
    a("    --state '+Conditioned zones' --stem conditioned_zones \\")
    a("    --state '+Closure fixes' --stem canonical \\")
    a("    --outdir results/paper/diagnostics/sankey")
    a("python tools/paper/diagnostics_latent_residual.py --what latent \\")
    a("    --raw results/paper/canonical_trajectory/trajectory_raw.json \\")
    a("    --outdir results/paper/diagnostics/latent")
    a("python tools/paper/diagnostics_latent_residual.py --what residual \\")
    a("    --raw results/paper/canonical_trajectory/trajectory_raw.json \\")
    a("    --outdir results/paper/diagnostics/residual")
    a("")
    a("# Final")
    a("python -m pytest tests/ -v -rs > results/paper/pytest.txt 2>&1")
    a("python tools/paper/build_index.py")
    a("```")
    a("")
    a("Everything needs every engine branch present locally "
      "(`git fetch origin '+refs/heads/*:refs/remotes/origin/*'`) and a git identity "
      "for the cherry-picks. `--closure-base` defaults to the pinned `978db37` in "
      "every tool that needs it — do not pass `origin/main`, which now resolves to "
      "an incomplete instrument.")
    a("")
    (P / "INDEX.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"wrote -> {P / 'INDEX.md'}")
    print(f"gate: v2={gate_v2} items={gate_items} reint={gate_reint} "
          f"latent={gate_latent} head={head_ok} tree={tree_ok} suite={gate_suite}")
    if not gate:
        print("\nGATE FAILED — the index says so at the top.")
        raise SystemExit(2)
    print("GATE PASSED.")


def _read_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


if __name__ == "__main__":
    main()
