"""
Part 3 — Tables 4 and 5, and the decision about where they come from.

THE DECISION, MADE FROM THE DATA RATHER THAN ASSUMED
-----------------------------------------------------
**Table 4** (window / h_ce: Base / C1 / C2) comes **entirely from the Part 2
trajectory**. Its first three states are exactly Base -> +C1 -> +C2, and every
column it needs — sensible heating and cooling, solar gains, window and opaque
transmission — is emitted per state by the closure-capable instrument. Zero extra
engine runs; the paper's Table 4 and its Table 3 rows 1-3 are literally the same
measurements.

**Table 5** (ventilation + latent) is the one that does not fit, and it is worth
being precise about why, because the obvious fallback does not fix it either.

The original Table 5 was a 2x2 *isolation* experiment: Base, ventilation fix
alone, latent fix alone, both together — designed to show that the two fixes
separate on the sensible side and interact on the latent side. The Part 2
trajectory is **cumulative**, so it contains

    ... -> +C2 -> +Ventilation -> +Latent

which gives three of the four cells (base-for-this-step, +vent, +vent+latent) and
**cannot** give the fourth: the latent fix applied *without* the ventilation fix.
Re-running the six-state closed-balance harness would not help — its states are
Baseline, +Vent+Latent *combined*, +Internal Gains, ... so the isolated latent
state is absent there too.

So this tool emits Table 5 in **both** forms, clearly separated:

  * **5a, methodology order** — derived from the Part 2 trajectory, zero extra
    runs. The step deltas as the paper's narrative actually applies them. This is
    the form to cite if the text is written in methodology order.
  * **5b, isolation (2x2)** — four states cherry-picked from the *same* vendored
    baseline onto the *same* closure instrument, so the interaction claim can
    still be made. Three extra engine runs. Its Base is reconciled against the
    trajectory's Baseline before anything is written; if they differ, the run
    stops.

Both are on Essendon, both on one instrument, and the provenance of each is
stated in the output so the methodology text can cite the right one.

Usage
-----
    python tools/paper/tables_4_5.py \\
        --weather weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw \\
        --raw results/paper/canonical_trajectory/trajectory_raw.json \\
        --outdir results/paper/tables_4_5
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "tools" / "diagnostics"))

from closed_balance_six_state import (          # noqa: E402
    V2_TOLERANCE_PCT, apply_shim, closure_commits, drop_worktree,
    make_worktree, run_engine,
)
from canonical_trajectory import (              # noqa: E402
    BASELINE, CLOSURE_BASE, EXPECTED_CLOSURE_PREFIXES, cherry_pick,
)

# `closed_balance_six_state.backport` tolerates a conflict only in
# `check_input.py`; the fourth closure commit also touches `.gitignore` and a
# notebook, neither of which carries physics. `canonical_trajectory.cherry_pick`
# has the policy this needs: resolve conflicts OUTSIDE `pybuildingenergy/src/` in
# favour of the state, and abort on any conflict inside it — an engine conflict
# means the fix is not cleanly separable at this point, which is the one thing
# that must never be guessed.
ALLOW_ENGINE_CONFLICT = ("source/check_input.py",)
from weather_integrity import assert_usable      # noqa: E402

MATCH_TOL = 1e-9

# The 2x2 isolation states, as branches cut from the vendored baseline. Branches
# rather than cherry-picks on purpose: the latent fix and the ventilation fix are
# sequential commits on `ventilation-plus-latent-fix`, so cherry-picking the
# latent commit alone onto the bare baseline would apply it against a parent it
# was never written for. These branches are the fixes as they were actually
# authored in isolation.
ISOLATION_STATES = [
    ("Base", None,
     "unmodified ISO 52016-1, as vendored"),
    ("C1 · ventilation", "claude/ventilation-infiltration-fix",
     "ventilation / infiltration fix alone — additive H_ve_inf term"),
    ("C2 · latent", "claude/latent-heat-fix",
     "latent fix alone — EN 16798-1 deadband, occupancy moisture, dt_h"),
    ("C3 · both", "claude/ventilation-plus-latent-fix",
     "both fixes together"),
]

T4_METRICS = [
    ("Q_H_sensible_kWh", "Sensible heating (kWh)"),
    ("Q_C_sensible_kWh", "Sensible cooling (kWh)"),
    ("Q_solar_gains_kWh", "Solar gains (kWh)"),
    ("Q_tr_window_loss_kWh", "Window transmission loss (kWh)"),
    ("Q_tr_opaque_loss_kWh", "Opaque transmission loss (kWh)"),
    ("Q_tr_total_loss_kWh", "Total transmission loss (kWh)"),
]

T5_METRICS = [
    ("Q_H_sensible_kWh", "Sensible heating (kWh)"),
    ("Q_C_sensible_kWh", "Sensible cooling (kWh)"),
    ("Q_ve_loss_kWh", "Ventilation + infiltration loss (kWh)"),
    ("Q_C_latent_kWh", "Latent cooling, gated (kWh)"),
    ("Q_C_latent_ungated_kWh", "Latent cooling, ungated (kWh)"),
    ("Q_H_latent_kWh", "Latent heating (kWh)"),
    ("Q_need_total_kWh", "Total energy need (kWh)"),
]


def _f(v, nd=2):
    if v is None or (isinstance(v, float) and v != v):
        return "n/a"
    return f"{v:,.{nd}f}"


def _pct(new, base):
    if base in (None, 0) or new is None:
        return "n/a"
    return f"{100.0 * (new - base) / base:+.2f} %"


def emit(states: list[tuple[str, dict]], metrics: list[tuple[str, str]],
         path_stem: Path, title: str, preamble: list[str],
         deltas_vs_first: bool = True) -> None:
    labels = [s for s, _ in states]

    with path_stem.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Metric"] + labels
                   + [f"{l} vs {labels[0]} (%)" for l in labels[1:]])
        for key, name in metrics:
            vals = [s[1].get(key) for s in states]
            row = [name] + vals
            if deltas_vs_first:
                row += [(100.0 * (v - vals[0]) / vals[0]
                         if vals[0] not in (None, 0) and v is not None else "")
                        for v in vals[1:]]
            w.writerow(row)

    L: list[str] = []
    add = L.append
    add(f"# {title}")
    add("")
    L.extend(preamble)
    add("")
    add("| Metric | " + " | ".join(labels) + " | "
        + " | ".join(f"{l} vs {labels[0]}" for l in labels[1:]) + " |")
    add("| --- | " + " | ".join(["---:"] * (len(labels) + len(labels) - 1)) + " |")
    for key, name in metrics:
        vals = [s[1].get(key) for s in states]
        nd = 4 if key == "Q_H_latent_kWh" else 2
        cells = [name] + [_f(v, nd) for v in vals]
        cells += [_pct(v, vals[0]) for v in vals[1:]]
        add("| " + " | ".join(cells) + " |")
    add("")
    add("### Closure, per state")
    add("")
    add("| State | V2 residual (kWh) | V2 residual (%) | < 5 %? | Transmission items |")
    add("| --- | ---: | ---: | :-: | ---: |")
    for lab, r in states:
        sk = r["sankey"]
        ok = abs(sk["residual_pct"]) < V2_TOLERANCE_PCT
        add(f"| {lab} | {sk['residual_kWh']:+,.2f} | {sk['residual_pct']:+.2f} % "
            f"| {'PASS' if ok else 'FAIL'} | {sk['n_transmission_items']} |")
    add("")
    path_stem.with_suffix(".md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", required=True)
    ap.add_argument("--raw", type=Path,
                    default=REPO_ROOT / "results/paper/canonical_trajectory/trajectory_raw.json")
    ap.add_argument("--outdir", type=Path, default=REPO_ROOT / "results/paper/tables_4_5")
    ap.add_argument("--closure-base", default=CLOSURE_BASE)
    ap.add_argument("--closure-ref", default="HEAD")
    ap.add_argument("--expect-weather", default="Essendon")
    ap.add_argument("--skip-isolation", action="store_true",
                    help="emit only the trajectory-derived forms (no extra runs)")
    args = ap.parse_args()

    weather = str(Path(args.weather).resolve())
    assert_usable(Path(weather), expect_name_contains=args.expect_weather)

    blob = json.loads(args.raw.read_text(encoding="utf-8"))
    traj = {k: v["config_B"] for k, v in blob["results"].items()}
    if Path(blob["meta"]["weather"]).name != Path(weather).name:
        raise SystemExit(
            f"the trajectory in {args.raw} was run on "
            f"{Path(blob['meta']['weather']).name}, not {Path(weather).name}. "
            f"Tables 4/5 would sit on different weather from Part 2. Stopping.")

    args.outdir.mkdir(parents=True, exist_ok=True)

    # --- Table 4: straight from the trajectory ------------------------------
    t4_states = [(l, traj[l]) for l in
                 ("Baseline", "+C1 dynamic window", "+C2 wind-dependent h_ce")]
    emit(t4_states, T4_METRICS, args.outdir / "table4_window_hce",
         "Table 4 — the window and h_ce corrections (Base / C1 / C2)",
         [
             "**Source: the Part 2 canonical trajectory, states 1–3. No separate "
             "harness, no extra engine run — these are the same measurements as "
             "rows 1–3 of the trajectory table.**",
             "",
             f"Weather `{Path(weather).name}`. Cumulative: C1 is Base plus the "
             "dynamic window correction; C2 is C1 plus the wind-dependent external "
             "convective coefficient. Both are the *literature* corrections and both "
             "precede the found defects, which is the methodology order.",
             "",
             "C1 changes two things at once and the paper should say so: the angular "
             "correction factor `F_w(θ)` on transmitted solar **and** a wind-dependent "
             "thermal transmittance on the windows. C2 then extends that "
             "transmittance to the opaque envelope. Both halves are switchable "
             "(`window_convection_model=\"table\"` keeps the ISO constant film on the "
             "glazing, `window_angular_solar_model=\"none\"` gives the complement), so "
             "the angle effect can be isolated without changing the branch structure.",
         ])

    # --- Table 5a: methodology order, from the trajectory --------------------
    t5a_states = [("Before (= +C2)", traj["+C2 wind-dependent h_ce"]),
                  ("+Ventilation", traj["+Ventilation"]),
                  ("+Latent (cumulative)", traj["+Latent"])]
    emit(t5a_states, T5_METRICS, args.outdir / "table5a_methodology_order",
         "Table 5a — ventilation and latent, in methodology order",
         [
             "**Source: the Part 2 canonical trajectory, states 3–5. No extra engine "
             "run.**",
             "",
             f"Weather `{Path(weather).name}`. **Cumulative**, so each column is the "
             "previous one plus exactly one fix, and the baseline for this step is the "
             "state the trajectory has actually reached by then (`+C2`), not the "
             "unmodified engine.",
             "",
             "This is the form to cite if the results text is written in methodology "
             "order. It answers \"what does each fix add, at the point the "
             "methodology applies it\". It does **not** answer \"do the two fixes "
             "interact\" — for that, see Table 5b, which is the 2×2.",
         ])

    # --- Table 5b: the 2x2 isolation experiment ------------------------------
    iso_summary = None
    if not args.skip_isolation:
        closure = closure_commits(args.closure_ref, args.closure_base)
        missing = [p for p in EXPECTED_CLOSURE_PREFIXES
                   if not any(c.startswith(p) for c in closure)]
        if missing:
            raise SystemExit(f"closure set is missing {missing}")
        print(f"closure commits: {[c[:9] for c in closure]}\n", flush=True)

        tmp = Path(tempfile.mkdtemp(prefix="aib-paper-t5-"))
        created: list[Path] = []
        results: dict[str, dict] = {}
        prov: dict[str, dict] = {}
        try:
            for label, branch, note in ISOLATION_STATES:
                print(f"measuring {label:<20} ({branch or 'vendored baseline'})",
                      flush=True)
                wt = tmp / (branch.replace("/", "_") if branch else "base")
                make_worktree(branch or BASELINE, wt)
                created.append(wt)
                resolved = []
                for sha in closure:
                    resolved += cherry_pick(wt, sha, label,
                                            allow_engine=ALLOW_ENGINE_CONFLICT)
                apply_shim(wt)
                data = run_engine(wt / "pybuildingenergy" / "src", weather,
                                  tmp / f"{label.replace(' ', '_').replace('·','')}.json",
                                  also_config_a=False)
                results[label] = data["config_B"]
                prov[label] = {"branch": branch, "note": note, "resolved": resolved}
                r = results[label]
                print(f"    H={r['Q_H_sensible_kWh']:9.2f}  C={r['Q_C_sensible_kWh']:9.2f}  "
                      f"latC={r['Q_C_latent_kWh']:8.2f}  latH={r['Q_H_latent_kWh']:8.4f}  "
                      f"resid={r['sankey']['residual_pct']:+6.2f}%", flush=True)
        finally:
            for w in created:
                drop_worktree(w)
            shutil.rmtree(tmp, ignore_errors=True)

        # Reconcile: the isolation Base and the trajectory Baseline are the same
        # engine on the same file and must agree, or the two tables describe
        # different buildings.
        base_keys = ["Q_H_sensible_kWh", "Q_C_sensible_kWh", "Q_C_latent_kWh",
                     "Q_need_total_kWh", "Q_ve_loss_kWh"]
        dmax = max(abs(results["Base"][k] - traj["Baseline"][k]) for k in base_keys)
        if dmax > MATCH_TOL:
            raise SystemExit(
                f"Table 5b's Base does not reconcile with the trajectory's Baseline "
                f"(max |Δ| {dmax:.3e} kWh) — same engine, same weather, so they must "
                f"agree. Stopping rather than emitting two tables that describe "
                f"different baselines.")
        print(f"\nTable 5b Base reconciles with the trajectory Baseline "
              f"(max |Δ| {dmax:.3e} kWh)", flush=True)

        t5b = [(l, results[l]) for l, _, _ in ISOLATION_STATES]
        emit(t5b, T5_METRICS, args.outdir / "table5b_isolation_2x2",
             "Table 5b — ventilation and latent, isolated (the 2×2)",
             [
                 "**Source: a separate 2×2 measured for this table — four states "
                 "cherry-picked from the same vendored baseline onto the same "
                 "closure-capable instrument as Part 2. Three extra engine runs.**",
                 "",
                 f"Weather `{Path(weather).name}`. **Not cumulative**: every column "
                 "starts from the unmodified engine, so C1 is the ventilation fix "
                 "alone, C2 is the latent fix alone, and C3 is both.",
                 "",
                 "This form exists because the cumulative trajectory structurally "
                 "cannot produce it — the latent fix applied *without* the "
                 "ventilation fix is not a state on that path — and neither can the "
                 "six-state closed-balance harness, whose second state is "
                 "ventilation and latent already combined. It is the only way to "
                 "make the interaction claim.",
                 "",
                 f"`Base` is reconciled against the Part 2 trajectory's `Baseline` "
                 f"row to {dmax:.1e} kWh before this table is written: same engine, "
                 f"same weather, so a disagreement would mean the two tables "
                 f"describe different buildings.",
             ])

        h_sep = (abs(results["C2 · latent"]["Q_H_sensible_kWh"]
                     - results["Base"]["Q_H_sensible_kWh"]) < 1e-6)
        lat_c = {l: results[l]["Q_C_latent_kWh"] for l in
                 ("Base", "C1 · ventilation", "C2 · latent", "C3 · both")}
        interaction = (lat_c["C3 · both"] - lat_c["Base"]) - (
            (lat_c["C1 · ventilation"] - lat_c["Base"])
            + (lat_c["C2 · latent"] - lat_c["Base"]))
        iso_summary = {
            "sensible_separates": bool(h_sep),
            "latent_interaction_kWh": interaction,
            "latent_cooling": lat_c,
            "base_reconciliation_max_abs_kWh": dmax,
            "provenance": prov,
        }
        (args.outdir / "table5b_raw.json").write_text(
            json.dumps({"results": results, "provenance": prov,
                        "weather": weather, "closure_commits": closure,
                        "summary": iso_summary}, indent=2, default=str),
            encoding="utf-8")

    # --- The provenance note -------------------------------------------------
    P: list[str] = []
    a = P.append
    a("# Tables 4 and 5 — where each one comes from")
    a("")
    a("The methodology text must cite these correctly, so the decision is recorded "
      "here rather than left to be inferred from the file names.")
    a("")
    a("| Table | Source | Extra engine runs | File |")
    a("| --- | --- | ---: | --- |")
    a("| **4** — window / h_ce | **Part 2 trajectory, states 1–3** | 0 "
      "| `table4_window_hce.{csv,md}` |")
    a("| **5a** — ventilation + latent, methodology order | **Part 2 trajectory, "
      "states 3–5** | 0 | `table5a_methodology_order.{csv,md}` |")
    a("| **5b** — ventilation + latent, isolated 2×2 | separate 4-state run, same "
      "baseline and same instrument | 3 | `table5b_isolation_2x2.{csv,md}` |")
    a("")
    a("## Why Table 5 needed a second source and Table 4 did not")
    a("")
    a("Table 4's three states *are* the trajectory's first three states, and the "
      "instrument already emits every column it needs — sensible heating and "
      "cooling, solar gains, and the window/opaque transmission split. Deriving it "
      "costs nothing and guarantees the paper's Table 4 and its trajectory rows are "
      "the same measurements rather than two runs that happen to agree.")
    a("")
    a("Table 5 is a **2×2 isolation** experiment: it exists to show that the two "
      "fixes separate on the sensible side and interact on the latent side. The "
      "trajectory is **cumulative**, so it contains `+C2 → +Ventilation → +Latent` "
      "and structurally cannot contain *the latent fix without the ventilation "
      "fix*. That fourth cell is the whole point of the table.")
    a("")
    a("**The obvious fallback does not fix this.** Re-running the six-state "
      "closed-balance harness on Essendon would not supply the missing cell either: "
      "its second state is `+Vent+Latent`, the two fixes already combined. So the "
      "isolated states were measured directly, from the same vendored baseline, "
      "with the same closure commits back-ported — the same instrument as Part 2, "
      "not a second one.")
    a("")
    a("Both forms are emitted. **Cite 5a if the results text is written in "
      "methodology order** (what each fix adds where the methodology applies it); "
      "**cite 5b for the interaction claim** (whether the two fixes are separable). "
      "They answer different questions and their columns are not interchangeable.")
    a("")
    if iso_summary:
        a("## What the 2×2 shows on the clean file")
        a("")
        a(f"* Sensible side: the latent fix alone moves sensible heating "
          f"{'not at all' if iso_summary['sensible_separates'] else 'measurably'} "
          f"— the two fixes "
          f"{'separate cleanly' if iso_summary['sensible_separates'] else 'do not separate'} "
          f"there.")
        lc = iso_summary["latent_cooling"]
        a(f"* Latent cooling: Base {lc['Base']:,.2f} → ventilation alone "
          f"{lc['C1 · ventilation']:,.2f} → latent alone {lc['C2 · latent']:,.2f} → "
          f"both {lc['C3 · both']:,.2f} kWh.")
        a(f"* **Interaction term: {iso_summary['latent_interaction_kWh']:+,.2f} kWh** "
          f"— the effect of both together minus the sum of the two separately. "
          f"Non-zero means the fixes are not additive on the latent side, which is "
          f"the claim the table is for.")
        a("")
    a("## Guardrails")
    a("")
    a(f"* weather: `{weather}`")
    a(f"* trajectory source: `{args.raw}`")
    a(f"* closure base pinned to `{args.closure_base}` and the resolved set asserted")
    a("* every state reports through the closure-capable instrument, so the V2 "
      "residual and the transmission inventory are comparable across both tables")
    a("")
    (args.outdir / "PROVENANCE.md").write_text("\n".join(P) + "\n", encoding="utf-8")

    print(f"\nwrote -> {args.outdir}")


if __name__ == "__main__":
    main()
