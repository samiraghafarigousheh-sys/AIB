"""
Cumulative comparison harness for the Australian correction plan.

This is ``compare_ventilation_latent.py`` generalised: same worker, same
throwaway-worktree isolation, same chart language, but the state list grows by
one column per correction step instead of being fixed at four branches. Run it
after each step with ``--through-step N`` and it emits the full table for every
state applied so far, so the cumulative effect is always visible rather than
only the newest delta.

    step  label               branch                                     adds
    ----  ------------------  -----------------------------------------  ------------------------------
    0     Baseline            claude/pybuildingenergy-baseline-anjro8    unmodified ISO 52016-1
    0     +Vent+Latent        claude/ventilation-plus-latent-fix         ventilation flow rate + latent
    1     +Internal Gains     claude/internal-gains-fix                  no neighbour-count inflation
    2     +Conditioned Zones  claude/conditioned-adjacent-zones-fix      neighbours at their setpoint
    3     +Ground Fix         claude/ground-contact-fix                  no implicit slab-on-ground
    4     +Hemisphere Fix     claude/coldest-month-hemisphere-fix        southern-hemisphere ground cycle

Each branch is checked out into a throwaway git worktree and driven in its own
subprocess. That isolation is not optional: several versions of the same
``pybuildingenergy`` package cannot coexist on one ``sys.path``, and the second
import would silently resolve to the first.

The *building* always comes from ``examples/apt305_building.py`` on the current
branch, so the engine is the only thing that varies. Fields that only the later
engines understand (``conditioned``/``setpoint`` on adjacent zones, added in
step 2) are simply ignored by the earlier ones -- ``check_input.py`` validates
known keys and never rejects unknown ones -- which is what keeps a single
building dictionary valid across every column.

TWO TABLE ORIENTATIONS ARE WRITTEN, DELIBERATELY
------------------------------------------------
``comparison.csv``/``.md``      one row per engine state, one column per metric,
                                plus "% vs previous step" and "% vs original
                                baseline" -- those two only make sense per state,
                                so states have to be rows.
``comparison_by_metric.csv``    the transpose: one row per metric, one column per
                                state. This is the orientation the earlier
                                harnesses use and the one the final rollup wants.

Usage
-----
    python examples/compare_au_corrections.py --through-step 1
    python examples/compare_au_corrections.py --through-step 4 \\
        --outdir results/au_corrections_summary --title "AU corrections — cumulative"
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"

# (label, branch, step, description). ``step`` is the correction step that
# introduces the state; --through-step keeps everything at or below it.
STATES = [
    ("Baseline", "claude/pybuildingenergy-baseline-anjro8", 0,
     "Unmodified ISO 52016-1"),
    ("+Vent+Latent", "claude/ventilation-plus-latent-fix", 0,
     "Ventilation flow-rate + symmetric latent fix"),
    ("+Internal Gains", "claude/internal-gains-fix", 1,
     "Step 1 — neighbour-count gain inflation removed"),
    ("+Conditioned Zones", "claude/conditioned-adjacent-zones-fix", 2,
     "Step 2 — conditioned neighbours held at their setpoint"),
    ("+Ground Fix", "claude/ground-contact-fix", 3,
     "Step 3 — no implicit slab-on-ground fallback"),
    ("+Hemisphere Fix", "claude/coldest-month-hemisphere-fix", 4,
     "Step 4 — hemisphere-aware coldest month"),
]

# (annual key, column label, unit). Order drives table column order.
#
# Key names were confirmed against the engine's actual annual frame, not
# assumed: ventilation loss is ``Q_ve_loss_kWh`` (no ``_annual``), ground is
# ``Q_ground_loss_kWh`` / ``Q_ground_gain_kWh``, gains are
# ``Q_internal_gains_kWh``. The last two are derived in the worker -- see below.
METRICS = [
    ("Q_H_annual_kWh", "Heating", "kWh"),
    ("Q_C_annual_kWh", "Cooling", "kWh"),
    ("Q_internal_gains_kWh", "Total internal gains", "kWh"),
    ("Q_ground_loss_kWh", "Ground loss", "kWh"),
    ("Q_ground_gain_kWh", "Ground gain", "kWh"),
    ("Q_ve_loss_kWh", "Ventilation+infiltration loss", "kWh"),
    ("Q_total_annual_kWh", "Total energy need", "kWh"),
    ("Q_total_annual_kWh_m2", "Total energy need", "kWh/m2"),
]

# Metrics drawn in the grouped bar chart, in kWh/m2 so the three are comparable
# on one axis and the chart reads as a single figure.
CHART_METRICS = [
    ("Q_H_annual_kWh_m2", "Heating"),
    ("Q_C_annual_kWh_m2", "Cooling"),
    ("Q_total_annual_kWh_m2", "Total energy need"),
]

# Categorical slots 1-6. The first four are the validated set already used by
# compare_branches_apt305.py and compare_ventilation_latent.py; slots 5-6 extend
# it while staying separable under both normal and CVD vision. Every bar carries
# a direct value label, so no series depends on colour alone to be read.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#8b5cf6", "#d4a017", "#c2255c"]
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"


# ---------------------------------------------------------------------------
# Worker: runs one engine, writes one JSON blob
# ---------------------------------------------------------------------------

def run_worker(args) -> int:
    sys.path.insert(0, str(Path(args.src).resolve()))
    sys.path.insert(0, str(EXAMPLES_DIR))

    import pandas as pd

    from apt305_building import build_bui
    from pybuildingenergy.source.utils import ISO52016
    from pybuildingenergy.source.check_input import sanitize_and_validate_BUI

    raw = build_bui()
    area = float(raw["building"]["net_floor_area"])
    building, _ = sanitize_and_validate_BUI(raw, fix=True)

    kwargs = {"weather_source": args.weather_source}
    if args.weather_source == "epw":
        kwargs["path_weather_file"] = args.weather

    result = ISO52016.Temperature_and_Energy_needs_calculation(building, **kwargs)
    hourly = result[0] if isinstance(result, tuple) else None
    annual = result[1] if isinstance(result, tuple) else None

    out: dict[str, float] = {"net_floor_area_m2": area}
    if annual is not None:
        def annual_val(key: str) -> float:
            if key not in annual.columns:
                return float("nan")
            return float(pd.to_numeric(annual[key], errors="coerce").iloc[0])

        dt_h = annual_val("time_step_h")
        if dt_h != dt_h or dt_h <= 0:
            dt_h = 1.0

        for key, _label, _unit in METRICS:
            out[key] = annual_val(key)
        out["Q_latent_annual_kWh"] = annual_val("Q_latent_annual_kWh")

        # Latent heating (humidification) is only an hourly column upstream, and
        # adding it to the annual aggregation would mean editing the baseline,
        # which has to stay byte-identical to upstream. Derived here instead, so
        # every state is measured by exactly the same definition.
        if hourly is not None and "Q_H_latent_W" in hourly.columns:
            series = pd.to_numeric(hourly["Q_H_latent_W"], errors="coerce").fillna(0.0)
            out["Q_H_latent_annual_kWh"] = float(series.clip(lower=0.0).sum() * dt_h / 1000.0)

        # Total demand the plant must serve: sensible heating + sensible cooling
        # + latent cooling (dehumidification) + latent heating (humidification).
        # Same definition as compare_ventilation_latent.py, so the +Vent+Latent
        # column is directly comparable with the figures already published there.
        parts = [out.get(k, float("nan")) for k in
                 ("Q_H_annual_kWh", "Q_C_annual_kWh",
                  "Q_latent_annual_kWh", "Q_H_latent_annual_kWh")]
        out["Q_total_annual_kWh"] = float(sum(parts)) if all(p == p for p in parts) else float("nan")

        for key in ("Q_H_annual_kWh", "Q_C_annual_kWh", "Q_total_annual_kWh"):
            v = out.get(key, float("nan"))
            out[f"{key}_m2"] = v / area if area > 0 else float("nan")

    Path(args.out).write_text(json.dumps(out), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Worktree plumbing (identical to the earlier harnesses)
# ---------------------------------------------------------------------------

def make_worktree(branch: str, dest: Path) -> None:
    last = ""
    for ref in (branch, f"origin/{branch}"):
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "worktree", "add", "--detach", str(dest), ref],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return
        last = proc.stderr.strip()
    raise RuntimeError(
        f"could not create a worktree for '{branch}'.\n{last}\n\n"
        f"If this is a fresh clone, make sure all branches were fetched:\n"
        f"  git fetch origin '+refs/heads/*:refs/remotes/origin/*'"
    )


def drop_worktree(dest: Path) -> None:
    subprocess.run(
        ["git", "-C", str(REPO_ROOT), "worktree", "remove", "--force", str(dest)],
        check=False, capture_output=True, text=True,
    )


def run_branch(src: Path, weather: str | None, weather_source: str, out_json: Path) -> dict:
    cmd = [
        sys.executable, str(Path(__file__).resolve()),
        "--worker", "--src", str(src),
        "--weather-source", weather_source,
        "--out", str(out_json),
    ]
    if weather:
        cmd += ["--weather", weather]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-20:])
        raise RuntimeError(f"engine run failed for {src}:\n{tail}")
    return json.loads(out_json.read_text(encoding="utf-8"))


def pct(new: float, old: float) -> float:
    if old != old or new != new or abs(old) < 1e-12:
        return float("nan")
    return (new - old) / old * 100.0


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def build_rows(states, results: dict[str, dict]) -> list[dict]:
    """One row per engine state; '% vs' columns are on Total energy need."""
    labels = [s[0] for s in states]
    rows = []
    for i, label in enumerate(labels):
        r = results[label]
        row = {"State": label, "Branch": states[i][1], "Adds": states[i][3]}
        for key, mlabel, unit in METRICS:
            row[f"{mlabel} ({unit})"] = r.get(key, float("nan"))
        total = r.get("Q_total_annual_kWh", float("nan"))
        prev = results[labels[i - 1]].get("Q_total_annual_kWh", float("nan")) if i else float("nan")
        base = results[labels[0]].get("Q_total_annual_kWh", float("nan"))
        row["% vs previous step"] = pct(total, prev) if i else float("nan")
        row["% vs original baseline"] = pct(total, base) if i else 0.0
        rows.append(row)
    return rows


def _fmt_cell(key: str, v) -> str:
    if isinstance(v, str):
        return v
    if v != v:
        return "n/a"
    if key.startswith("%"):
        return f"{v:+.2f}%"
    return f"{v:,.2f}"


def write_tables(rows: list[dict], states, results: dict[str, dict], outdir: Path) -> None:
    header = list(rows[0].keys())

    with (outdir / "comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow([r[h] if isinstance(r[h], str)
                        else ("" if r[h] != r[h] else f"{r[h]:.6f}") for h in header])

    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(_fmt_cell(h, r[h]) for h in header) + " |")
    (outdir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Transpose: metrics as rows, states as columns.
    labels = [s[0] for s in states]
    t_header = ["Metric", "Unit", *labels]
    t_rows = []
    for key, mlabel, unit in METRICS:
        t_rows.append([mlabel, unit] + [results[l].get(key, float("nan")) for l in labels])

    with (outdir / "comparison_by_metric.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(t_header)
        for r in t_rows:
            w.writerow(r[:2] + ["" if v != v else f"{v:.6f}" for v in r[2:]])

    lines = ["| " + " | ".join(t_header) + " |",
             "|" + "|".join(["---"] * len(t_header)) + "|"]
    for r in t_rows:
        cells = [r[0], r[1]] + ["n/a" if v != v else f"{v:,.2f}" for v in r[2:]]
        lines.append("| " + " | ".join(cells) + " |")
    (outdir / "comparison_by_metric.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_table(rows: list[dict], states) -> None:
    cols = [("State", 20)] + [(f"{m} ({u})", 15) for _k, m, u in METRICS] \
           + [("% vs prev", 11), ("% vs base", 11)]
    head = "".join(c.rjust(w) if i else c.ljust(w) for i, (c, w) in enumerate(cols))
    print()
    print(head)
    print("-" * len(head))
    for r in rows:
        cells = [r["State"].ljust(20)]
        for _k, m, u in METRICS:
            v = r[f"{m} ({u})"]
            cells.append(("n/a" if v != v else f"{v:,.1f}").rjust(15))
        for k in ("% vs previous step", "% vs original baseline"):
            v = r[k]
            cells.append(("n/a" if v != v else f"{v:+.2f}%").rjust(11))
        print("".join(cells))
    print()


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def make_chart(states, results: dict[str, dict], outdir: Path,
               subtitle: str, title: str, stem: str) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    labels = [s[0] for s in states]
    n = len(labels)

    fig, ax = plt.subplots(figsize=(max(10.0, 2.0 + 1.55 * n), 6.0), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    group_w = 0.78
    bar_w = group_w / n
    all_vals = []

    for si, label in enumerate(labels):
        vals = [results[label].get(k, float("nan")) for k, _ in CHART_METRICS]
        all_vals += [v for v in vals if v == v]
        xs = [gi - group_w / 2 + bar_w * (si + 0.5) for gi in range(len(CHART_METRICS))]
        ax.bar(xs, vals, width=bar_w * 0.88, color=SERIES_COLORS[si % len(SERIES_COLORS)],
               edgecolor="none", zorder=3)
        for x, v in zip(xs, vals):
            if v != v:
                continue
            ax.annotate(f"{v:,.1f}", xy=(x, v), xytext=(0, 4),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=7.5, color=TEXT_PRIMARY, rotation=90, zorder=4)

    vmax = max(all_vals + [0.0])
    ax.set_ylim(0, vmax * 1.30 if vmax > 0 else 1.0)
    ax.set_xticks(range(len(CHART_METRICS)))
    ax.set_xticklabels([m for _k, m in CHART_METRICS], fontsize=10, color=TEXT_SECONDARY)
    ax.set_ylabel("kWh/m² per year", fontsize=9.5, color=TEXT_SECONDARY)
    ax.tick_params(axis="y", labelsize=8.5, colors=TEXT_SECONDARY, length=0)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=GRID, linewidth=1.0, linestyle="-", zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

    handles = [Patch(facecolor=SERIES_COLORS[i % len(SERIES_COLORS)], edgecolor="none",
                     label=f"{lbl} — {states[i][3]}") for i, lbl in enumerate(labels)]
    ncol = 2 if n > 3 else 3
    fig.legend(handles=handles, loc="lower center", ncol=ncol, frameon=False,
               fontsize=8.5, labelcolor=TEXT_SECONDARY, bbox_to_anchor=(0.5, -0.02))

    fig.suptitle(title, fontsize=14, color=TEXT_PRIMARY, x=0.011, ha="left",
                 y=0.985, fontweight="semibold")
    fig.text(0.011, 0.935, subtitle, fontsize=9, color=TEXT_SECONDARY, ha="left")

    fig.tight_layout(rect=[0, 0.06 + 0.028 * (len(handles) // ncol), 1, 0.915])
    out = outdir / f"{stem}.png"
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--src", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--out", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--through-step", type=int, default=4,
                    help="highest correction step to include (default 4 = all)")
    ap.add_argument("--weather", default=None,
                    help="Explicit Melbourne EPW, validated against the building's coordinates")
    ap.add_argument("--weather-source", default="auto", choices=["auto", "epw", "pvgis"])
    ap.add_argument("--allow-site-mismatch", action="store_true")
    ap.add_argument("--require-epw", action="store_true")
    ap.add_argument("--outdir", type=Path, default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--stem", default=None, help="PNG basename (without .png)")
    args = ap.parse_args()

    if args.worker:
        sys.exit(run_worker(args))

    states = [s for s in STATES if s[2] <= args.through_step]
    if len(states) < 2:
        print("ERROR  --through-step must keep at least two states")
        sys.exit(2)

    step_names = {1: "step_1_internal_gains", 2: "step_2_conditioned_zones",
                  3: "step_3_ground", 4: "step_4_hemisphere"}
    outdir = args.outdir or (REPO_ROOT / "results"
                             / step_names.get(args.through_step, "au_corrections"))
    stem = args.stem or f"{outdir.name}_comparison"
    title = args.title or f"Apt 305 — AU corrections through step {args.through_step}"
    outdir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(EXAMPLES_DIR))
    from weather_melbourne import resolve_and_record, WeatherUnavailable

    print("resolving weather…")
    try:
        weather_source, weather_path, weather_label = resolve_and_record(
            args.weather, args.weather_source, args.allow_site_mismatch,
            outdir, require_epw=args.require_epw,
        )
    except WeatherUnavailable as exc:
        print(f"\nERROR  {exc}\n")
        sys.exit(2)
    print(f"  -> {weather_label}\n")

    results: dict[str, dict] = {}
    tmp = Path(tempfile.mkdtemp(prefix="aib-au-"))
    created: list[Path] = []
    try:
        for label, branch, _step, _desc in states:
            print(f"running {label:<20} ({branch})")
            wt = tmp / branch.replace("/", "_")
            make_worktree(branch, wt)
            created.append(wt)
            results[label] = run_branch(
                wt / "pybuildingenergy" / "src",
                weather_path if weather_source == "epw" else None,
                weather_source,
                tmp / f"{label.replace(' ', '_')}.json",
            )
    finally:
        for wt in created:
            drop_worktree(wt)

    rows = build_rows(states, results)
    print_table(rows, states)
    write_tables(rows, states, results, outdir)
    (outdir / "results.json").write_text(
        json.dumps({s[0]: results[s[0]] for s in states}, indent=2), encoding="utf-8")

    subtitle = (f"Weather: {weather_label}  ·  ideal loads, 5 adjacent zones, "
                f"1.62 m² west-facing single glazing")
    chart = make_chart(states, results, outdir, subtitle, title, stem)

    print(f"table  -> {outdir / 'comparison.csv'}  (states as rows)")
    print(f"table  -> {outdir / 'comparison_by_metric.csv'}  (states as columns)")
    print(f"raw    -> {outdir / 'results.json'}")
    print(f"chart  -> {chart}")


if __name__ == "__main__":
    main()
