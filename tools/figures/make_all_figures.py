"""
Build the complete paper figure set into results/paper/figures/.

Every figure is drawn from the committed result files under results/. The engine
is never re-run. Each builder asserts the quantities the paper states before it
draws anything, and raises figstyle.MissingQuantity rather than substituting a
value from a different run -- so a failure here is a report, not a silent
disagreement between the figures and the tables.

    python3 tools/figures/make_all_figures.py
"""

from __future__ import annotations

import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import figstyle as F                                    # noqa: E402

import f1_iso_vs_ep                                     # noqa: E402
import f2_baseline_balance                              # noqa: E402
import f3_trajectory                                    # noqa: E402
import f4_per_correction                                # noqa: E402
import f5_corrected_balance                             # noqa: E402
import f6_wind_field                                    # noqa: E402
import f7_weather_integrity                             # noqa: E402
import f8_latent_gate                                   # noqa: E402
import f9_closure_residual                              # noqa: E402
import f10_q50_sensitivity                              # noqa: E402

BUILDERS = [
    f1_iso_vs_ep,
    f2_baseline_balance,
    f3_trajectory,
    f4_per_correction,
    f5_corrected_balance,
    f6_wind_field,
    f7_weather_integrity,
    f8_latent_gate,
    f9_closure_residual,
    f10_q50_sensitivity,
]

PLACEMENT_LABEL = {
    "main": "Main text",
    "main-if-budget": "Main text if the figure budget allows",
    "supplementary": "Supplementary / appendix",
}

PLACEMENT_ORDER = ["main", "main-if-budget", "supplementary"]

METRIC_NOTE = """\
Every figure that prints a per-area value uses the paper's metric

> **Q_need = Q_H,sensible + Q_C,sensible + Q_C,latent (gated)**

that is, sensible heating + sensible cooling + gated latent cooling, excluding
latent heating and excluding the ungated moisture balance. This is the
`Total, sensible + gated latent` column of `results/paper/trajectory_v2/comparison.md`,
**not** the engine's own total column — the two differ on the four states before the
latent correction by the ~153–185 kWh of phantom humidification.

`tools/figures/figstyle.py` recomputes all thirteen per-area values from
`trajectory_raw.json` and asserts them against the methodology's list before any
figure is drawn:

| State | kWh/m²·yr | State | kWh/m²·yr |
| --- | ---: | --- | ---: |
| Baseline | 122.32 | +Conditioned zones | 10.75 |
| +C1 dynamic window | 120.77 | +Ground contact | 10.75 |
| +C2 wind-dependent h_ce | 119.70 | +Hemisphere | 10.75 |
| +Ventilation | 133.41 | +Infiltration supply temp | 8.52 |
| +Latent | 132.88 | +Infiltration envelope area | 6.44 |
| +Internal gains | 220.82 | +AU q50 recalibration | 6.91 |
| | | **+Closure fixes (canonical)** | **6.91** |

The canonical headline — 123.74 kWh sensible heating + 13.41 kWh sensible cooling
+ 1.14 kWh gated latent = 138.29 kWh = **6.91 kWh/m²·yr** — is asserted separately.
A mismatch on any of these aborts the whole run.
"""

CONVENTIONS = """\
- **Vector + raster.** Every figure is written as PDF (vector, for the paper) and
  PNG (300 dpi, for preview).
- **One axis per metric.** The trajectory spans roughly 4,200 kWh to 4 kWh, so no
  two series of different magnitude share a scale. Where a panel carries two
  metrics (gated against ungated latent; monthly wind mean against exact-zero
  share) it uses two independent, separately labelled axes and says so on the
  panel.
- **Colour.** Okabe-Ito base hues, one per correction group, with a light-to-dark
  ramp inside each group, so a state keeps the same colour in every figure it
  appears in. Group hues separate under deuteranopia, protanopia and tritanopia;
  within-group separation is carried by lightness, which survives all three.
  Baseline = grey · literature corrections (C1, C2) = blue · implementation
  defects = vermillion · infiltration states = bluish green · closure fixes =
  reddish purple.
- **State labels are rotated, never truncated.** Thirteen states do not fit
  horizontally.
- **The three infiltration states are shaded as a group** in every trajectory
  panel, because they are the subject of Section 3.7.1.
- **F2 and F5 share one renderer**, one band order, one colour map and one
  kWh-per-unit-height, so the difference between them is the model and not the
  drawing. F5 also carries a dashed ghost outline of F2's column extent.
- **No figure invents a number.** Where a required quantity is absent from the
  committed results it is drawn as an explicit gap and reported here (see F10).
"""


def main() -> int:
    F.apply_style()
    results, failures = [], []

    for mod in BUILDERS:
        name = mod.__name__
        try:
            meta = mod.build()
            results.append(meta)
            print(f"  ok    {meta['id']:<4} {meta['title']}")
        except F.MissingQuantity as exc:
            failures.append((name, str(exc)))
            print(f"  STOP  {name}: {exc}", file=sys.stderr)
        except Exception:                                  # noqa: BLE001
            failures.append((name, traceback.format_exc()))
            print(f"  FAIL  {name}", file=sys.stderr)
            traceback.print_exc()

    write_index(results, failures)

    if failures:
        print(f"\n{len(failures)} figure(s) did not build.", file=sys.stderr)
        return 1
    print(f"\n{len(results)} figures written to {F.FIGDIR}")
    return 0


def write_index(results: list[dict], failures: list[tuple[str, str]]) -> None:
    out = [
        "# Paper figure set",
        "",
        f"Generated {date.today().isoformat()} by `tools/figures/make_all_figures.py` "
        "from the committed result files under `results/`. **The engine was not "
        "re-run.** Every number in every figure is read from a file already in the "
        "repository, so the figures and the tables in the paper are the same "
        "measurements rather than two runs that happen to agree.",
        "",
        f"**Weather:** `{F.WEATHER}`  ",
        "**Canonical state:** `+Closure fixes` — 123.74 kWh sensible heating, "
        "13.41 kWh sensible cooling, 1.14 kWh gated latent, 138.29 kWh total, "
        "**6.91 kWh/m²·yr**  ",
        f"**Net floor area:** {F.NET_FLOOR_AREA_M2:.0f} m²",
        "",
        "## The metric",
        "",
        METRIC_NOTE,
        "## Shared conventions",
        "",
        CONVENTIONS,
    ]

    if failures:
        out += ["## Figures that did not build", ""]
        for name, err in failures:
            out += [f"### `{name}`", "", "```", err.strip(), "```", ""]

    out += ["## Recommended placement", ""]
    for placement in PLACEMENT_ORDER:
        ids = [r["id"] for r in results if r["placement"] == placement]
        if ids:
            out.append(f"- **{PLACEMENT_LABEL[placement]}:** {', '.join(ids)}")
    out += [
        "",
        "The paper currently plans F1, F2, F3, F5, F6 and F8 in the main text, with "
        "F4 and F10 strong candidates if the figure budget allows, and F7 and F9 as "
        "supplementary. F9 is a visual restatement of the residual and line-item "
        "columns of the trajectory table, so it is the first to drop.",
        "",
        "## The figures",
        "",
    ]

    for r in results:
        out += [
            f"### {r['id']} — {r['title']}",
            "",
            f"*{PLACEMENT_LABEL[r['placement']]}*",
            "",
            "**Files**",
            "",
        ]
        for p in r["files"]:
            out.append(f"- `{p.relative_to(F.REPO)}`")
        out += ["", "**Built from**", ""]
        for src in r["sources"]:
            out.append(f"- `{src}`" if src.startswith("results/")
                       or src.startswith("weather_cache/")
                       or src.startswith("pybuildingenergy/") else f"- {src}")
        out += ["", "**Key numbers displayed**", ""]
        for n in r["numbers"]:
            out.append(f"- {n}")
        if r.get("note"):
            out += ["", "**Note**", "", r["note"]]
        out += ["", "---", ""]

    out += [
        "## Reproducing",
        "",
        "```bash",
        "python3 tools/figures/make_all_figures.py",
        "```",
        "",
        "Requires `matplotlib` and `numpy`. Each figure module is also runnable on "
        "its own (`python3 tools/figures/f3_trajectory.py`). If a required quantity "
        "is missing from the committed results, the builder raises "
        "`figstyle.MissingQuantity` naming the figure and the quantity, and the run "
        "records the failure in this file rather than substituting a value from "
        "another run.",
        "",
    ]

    path = F.FIGDIR / "FIGURES.md"
    path.write_text("\n".join(out))
    print(f"  ok    index {path.relative_to(F.REPO)}")


if __name__ == "__main__":
    raise SystemExit(main())
