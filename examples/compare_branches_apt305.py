"""
Run the Apt 305 reference case through all three engine branches and report the
effect of each change as a table and a bar chart.

    branch                                     engine
    -----------------------------------------  -------------------------------
    claude/pybuildingenergy-baseline-anjro8    unmodified ISO 52016-1
    claude/dynamic-window-properties-anjro8    + dynamic window properties
    claude/window-plus-dynamic-hce-anjro8      + wind-dependent surface h_ce

Each branch is checked out into a throwaway git worktree and driven in its own
subprocess. That isolation is not optional: three versions of the same
``pybuildingenergy`` package cannot coexist on one ``sys.path``, and the second
import would silently resolve to the first.

The *building* always comes from ``examples/apt305_building.py`` on the current
branch, so the only thing that varies between runs is the engine.

Usage
-----
    python examples/compare_branches_apt305.py
    python examples/compare_branches_apt305.py --weather path/to/Melbourne.epw
    python examples/compare_branches_apt305.py --weather-source pvgis

Outputs (into --outdir, default ``results/apt305``):
    comparison.csv        full metric table
    comparison.md         same table as markdown
    apt305_comparison.png bar chart
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"

BRANCHES = [
    ("Baseline", "claude/pybuildingenergy-baseline-anjro8", "Unmodified ISO 52016-1"),
    ("+ Window", "claude/dynamic-window-properties-anjro8", "Dynamic window properties"),
    ("+ Window + h_ce", "claude/window-plus-dynamic-hce-anjro8", "…plus wind-dependent h_ce"),
]

# (annual key, short label, unit). Order drives both table and chart.
METRICS = [
    ("Q_H_annual_kWh", "Heating need", "kWh"),
    ("Q_C_annual_kWh", "Cooling need", "kWh"),
    ("Q_solar_gains_kWh", "Solar gains", "kWh"),
    ("Q_tr_window_loss_kWh", "Window transm. loss", "kWh"),
    ("Q_tr_opaque_loss_kWh", "Opaque transm. loss", "kWh"),
    ("Q_tr_total_loss_kWh", "Total transm. loss", "kWh"),
]

# Categorical slots 1-3 of the validated palette. This exact triple was checked
# with the palette validator under --pairs all in light mode: all gates pass
# (worst CVD dE 9.2, worst normal-vision dE 24.0). The aqua slot sits at 2.74:1
# against the surface, which triggers the relief rule -- hence the direct value
# labels on every bar and the accompanying table view.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"


# ---------------------------------------------------------------------------
# Worker: runs one engine, prints one JSON blob on stdout
# ---------------------------------------------------------------------------

def run_worker(args) -> int:
    sys.path.insert(0, str(Path(args.src).resolve()))
    sys.path.insert(0, str(EXAMPLES_DIR))

    from apt305_building import build_bui
    from pybuildingenergy.source.utils import ISO52016
    from pybuildingenergy.source.check_input import sanitize_and_validate_BUI

    building, _ = sanitize_and_validate_BUI(build_bui(), fix=True)

    kwargs = {"weather_source": args.weather_source}
    if args.weather_source == "epw":
        kwargs["path_weather_file"] = args.weather

    result = ISO52016.Temperature_and_Energy_needs_calculation(building, **kwargs)
    annual = result[1] if isinstance(result, tuple) else None

    out = {}
    if annual is not None:
        import pandas as pd
        for key, _label, _unit in METRICS:
            if key in annual.columns:
                out[key] = float(pd.to_numeric(annual[key], errors="coerce").iloc[0])
            else:
                out[key] = float("nan")

    Path(args.out).write_text(json.dumps(out), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def make_worktree(branch: str, dest: Path) -> None:
    """
    Check a branch out into a throwaway worktree.

    On a fresh clone (Colab) the sibling branches exist only as remote-tracking
    refs, so fall back to origin/<branch> when the local name is absent.
    """
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
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-15:])
        raise RuntimeError(f"engine run failed for {src}:\n{tail}")
    return json.loads(out_json.read_text(encoding="utf-8"))


def fmt(v: float, width: int = 12) -> str:
    if v != v:  # NaN
        return "n/a".rjust(width)
    return f"{v:,.1f}".rjust(width)


def pct(new: float, old: float) -> float:
    if old != old or new != new or abs(old) < 1e-12:
        return float("nan")
    return (new - old) / old * 100.0


def print_table(results: dict[str, dict]) -> list[list]:
    names = [n for n, _, _ in BRANCHES]
    base = results[names[0]]

    rows = []
    for key, label, unit in METRICS:
        vals = [results[n].get(key, float("nan")) for n in names]
        rows.append([label, unit, *vals, pct(vals[1], vals[0]), pct(vals[2], vals[1]), pct(vals[2], vals[0])])

    head = (
        f"{'Metric':<22}{'Unit':>5}"
        f"{names[0]:>13}{names[1]:>13}{names[2]:>17}"
        f"{'C1 vs base':>12}{'C2 vs C1':>11}{'C2 vs base':>12}"
    )
    print()
    print(head)
    print("-" * len(head))
    for r in rows:
        label, unit, v0, v1, v2, r1, r21, r2 = r
        def p(x):
            return "n/a".rjust(10) if x != x else f"{x:+.2f}%".rjust(10)
        print(f"{label:<22}{unit:>5}{fmt(v0,13)}{fmt(v1,13)}{fmt(v2,17)}"
              f"{p(r1):>12}{p(r21):>11}{p(r2):>12}")
    print()
    return rows


def write_tables(rows: list[list], outdir: Path) -> None:
    names = [n for n, _, _ in BRANCHES]
    header = ["Metric", "Unit", *names, "C1 vs base %", "C2 vs C1 %", "C2 vs base %"]

    import csv
    with (outdir / "comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow([r[0], r[1]] + [f"{v:.4f}" if v == v else "" for v in r[2:]])

    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        cells = [r[0], r[1]]
        cells += [f"{v:,.1f}" if v == v else "n/a" for v in r[2:5]]
        cells += [f"{v:+.2f}%" if v == v else "n/a" for v in r[5:]]
        lines.append("| " + " | ".join(cells) + " |")
    (outdir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def rounded_bar_path(x0, x1, height, radius):
    """
    Bar with a 4px rounded data-end and a square baseline, per the mark spec.
    Handles negative heights so the rounding always lands on the data end.
    """
    from matplotlib.path import Path as MPath

    sign = 1.0 if height >= 0 else -1.0
    h = abs(height)
    r = min(radius, h / 2.0 if h > 0 else radius, (x1 - x0) / 2.0)
    if r <= 0 or h == 0:
        verts = [(x0, 0), (x0, height), (x1, height), (x1, 0), (x0, 0)]
        codes = [MPath.MOVETO, MPath.LINETO, MPath.LINETO, MPath.LINETO, MPath.CLOSEPOLY]
        return MPath(verts, codes)

    top = sign * h
    shoulder = sign * (h - r)
    verts = [
        (x0, 0),                 # baseline, square
        (x0, shoulder),
        (x0, top), (x0 + r, top),   # rounded corner (quadratic)
        (x1 - r, top),
        (x1, top), (x1, shoulder),  # rounded corner
        (x1, 0),
        (x0, 0),
    ]
    codes = [
        MPath.MOVETO,
        MPath.LINETO,
        MPath.CURVE3, MPath.CURVE3,
        MPath.LINETO,
        MPath.CURVE3, MPath.CURVE3,
        MPath.LINETO,
        MPath.CLOSEPOLY,
    ]
    return MPath(verts, codes)


def make_chart(results: dict[str, dict], outdir: Path, subtitle: str) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import PathPatch, Patch

    names = [n for n, _, _ in BRANCHES]

    # Small multiples, one panel per metric. The metrics span three orders of
    # magnitude, so a single shared axis would flatten everything except cooling
    # -- and a second y-axis is never the answer. Each panel gets its own scale.
    ncols, nrows = 3, 2
    fig, axes = plt.subplots(nrows, ncols, figsize=(13.5, 7.4), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    axes = axes.ravel()

    dpi = fig.dpi
    for ax_i, (key, label, unit) in enumerate(METRICS):
        ax = axes[ax_i]
        ax.set_facecolor(SURFACE)
        vals = [results[n].get(key, float("nan")) for n in names]

        # Cap rendered bar thickness at 24px, letting the band's leftover be air.
        # Panel size is estimated analytically rather than read from
        # get_window_extent(), which returns pre-layout values before the first
        # draw and would silently mis-size every bar.
        panel_w_px = fig.get_figwidth() * dpi / ncols * 0.78
        panel_h_px = fig.get_figheight() * dpi / nrows * 0.62
        max_frac = min(0.55, (24.0 * len(names)) / max(panel_w_px, 1.0))
        bar_w = max(0.22, max_frac)

        vmax = max([v for v in vals if v == v] + [0.0])
        vmin = min([v for v in vals if v == v] + [0.0])
        span = (vmax - vmin) or 1.0
        radius_data = 4.0 / panel_h_px * span

        for i, (name, val) in enumerate(zip(names, vals)):
            if val != val:
                continue
            # 2px surface gap between adjacent bars, in data units.
            gap = (2.0 / max(panel_w_px, 1.0)) * len(names)
            x0, x1 = i - bar_w / 2 + gap / 2, i + bar_w / 2 - gap / 2
            patch = PathPatch(
                rounded_bar_path(x0, x1, val, radius_data),
                facecolor=SERIES_COLORS[i], edgecolor="none", zorder=3,
            )
            ax.add_patch(patch)

            # Direct label on the cap -- also the relief for the low-contrast slot.
            # Precision follows the panel's magnitude: rounding 20.1 and 19.9 to
            # a bare "20" would hide the very difference the chart exists to show.
            dp = 1 if vmax < 100 else 0
            ax.annotate(
                f"{val:,.{dp}f}", xy=(i, val), xytext=(0, 5), textcoords="offset points",
                ha="center", va="bottom", fontsize=9, color=TEXT_PRIMARY, zorder=4,
            )
            if i > 0 and vals[0] == vals[0] and abs(vals[0]) > 1e-12:
                d = pct(val, vals[0])
                ax.annotate(
                    f"{d:+.1f}%", xy=(i, val), xytext=(0, 17), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5,
                    color=TEXT_SECONDARY, zorder=4,
                )

        ax.set_title(f"{label}  ({unit})", fontsize=10.5, color=TEXT_PRIMARY,
                     pad=10, loc="left", fontweight="medium")
        ax.set_xlim(-0.62, len(names) - 0.38)
        ax.set_ylim(min(0.0, vmin * 1.15), vmax * 1.32 if vmax > 0 else 1.0)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(["Base", "C1", "C2"], fontsize=9, color=TEXT_SECONDARY)
        ax.tick_params(axis="y", labelsize=8.5, colors=TEXT_SECONDARY, length=0)
        ax.tick_params(axis="x", length=0)

        # Recessive hairline grid; no dashes, no box.
        ax.grid(axis="y", color=GRID, linewidth=1.0, linestyle="-", zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.spines["bottom"].set_linewidth(1.0)

    handles = [Patch(facecolor=c, edgecolor="none", label=f"{n} — {d}")
               for c, (n, _b, d) in zip(SERIES_COLORS, BRANCHES)]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False,
               fontsize=9.5, labelcolor=TEXT_SECONDARY, bbox_to_anchor=(0.5, -0.005))

    fig.suptitle("Apt 305, 50 Barry St — effect of each engine change",
                 fontsize=14, color=TEXT_PRIMARY, x=0.011, ha="left", y=0.988,
                 fontweight="semibold")
    fig.text(0.011, 0.934, subtitle, fontsize=9.5, color=TEXT_SECONDARY, ha="left")

    fig.tight_layout(rect=[0, 0.05, 1, 0.912])
    # tight_layout packs the rows flush, which puts each lower title right on top
    # of the row above's tick labels. Re-open the gap after it has run.
    fig.subplots_adjust(hspace=0.42, wspace=0.22)
    out = outdir / "apt305_comparison.png"
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
    ap.add_argument(
        "--weather", default=None,
        help="Explicit Melbourne EPW. Validated against the building's coordinates; "
             "a wrong-city file is rejected rather than silently simulated.",
    )
    ap.add_argument("--weather-source", default="auto",
                    choices=["auto", "epw", "pvgis"],
                    help="'auto' (default): cached Melbourne EPW, else download one, "
                         "else PVGIS. 'pvgis' fetches a TMY for the building's own "
                         "lat/lon and is site-correct by construction.")
    ap.add_argument("--allow-site-mismatch", action="store_true",
                    help="Accept an EPW from another location. Results are then for "
                         "that location, not Melbourne, and are labelled as such.")
    ap.add_argument("--outdir", type=Path, default=REPO_ROOT / "results" / "apt305")
    args = ap.parse_args()

    if args.worker:
        sys.exit(run_worker(args))

    args.outdir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(EXAMPLES_DIR))
    from weather_melbourne import resolve, WeatherUnavailable

    print("resolving weather…")
    try:
        weather_source, weather_path, weather_label = resolve(
            args.weather, args.weather_source, args.allow_site_mismatch
        )
    except WeatherUnavailable as exc:
        print(f"\nERROR  {exc}\n")
        sys.exit(2)

    args.weather_source = weather_source
    args.weather = weather_path
    subtitle = (f"Weather: {weather_label}  ·  ideal loads, zeroed thermal mass, "
                f"1.62 m² west-facing single glazing")
    print(f"  -> {weather_label}\n")

    results: dict[str, dict] = {}
    tmp = Path(tempfile.mkdtemp(prefix="aib-branches-"))
    created: list[Path] = []
    try:
        for name, branch, _desc in BRANCHES:
            print(f"running {name:<16} ({branch})")
            wt = tmp / branch.replace("/", "_")
            make_worktree(branch, wt)
            created.append(wt)
            results[name] = run_branch(
                wt / "pybuildingenergy" / "src",
                args.weather if args.weather_source == "epw" else None,
                args.weather_source,
                tmp / f"{name}.json",
            )
    finally:
        for wt in created:
            drop_worktree(wt)

    rows = print_table(results)
    write_tables(rows, args.outdir)
    chart = make_chart(results, args.outdir, subtitle)

    print(f"table  -> {args.outdir / 'comparison.csv'}")
    print(f"table  -> {args.outdir / 'comparison.md'}")
    print(f"chart  -> {chart}")


if __name__ == "__main__":
    main()
