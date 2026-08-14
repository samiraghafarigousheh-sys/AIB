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
import f11_reference_defects                            # noqa: E402
import f12_loss_paths                                   # noqa: E402
import f13_case_geometry                                # noqa: E402

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
    f11_reference_defects,
    f12_loss_paths,
    f13_case_geometry,
]

PLACEMENT_LABEL = {
    "main": "Main text",
    "main-if-budget": "Main text if the figure budget allows",
    "supplementary": "Supplementary / appendix",
}

PLACEMENT_ORDER = ["main", "main-if-budget", "supplementary"]

METRIC_NOTE_HEAD = """\
Every figure that prints a per-area value uses the paper's metric

> **Q_need = Q_H,sensible + Q_C,sensible + Q_C,latent (gated)**

that is, sensible heating + sensible cooling + gated latent cooling, excluding
latent heating and excluding the ungated moisture balance. This is the
`Total, sensible + gated latent` column of `results/paper/trajectory_v2/comparison.md`,
**not** the engine's own total column — the two differ on the four states before the
latent correction by the ~153–185 kWh of phantom humidification.

`tools/figures/figstyle.py` recomputes every per-area value from
`trajectory_raw.json` and asserts it against the methodology's list before any
figure is drawn:
"""


def metric_note() -> str:
    """The per-area table, generated from figstyle rather than restated."""
    states = list(F.EXPECTED_PER_AREA)
    half = (len(states) + 1) // 2
    left, right = states[:half], states[half:]
    rows = ["| State | kWh/m²·yr | State | kWh/m²·yr |",
            "| --- | ---: | --- | ---: |"]

    def cell(state):
        if state is None:
            return "| | "
        label = F.SHORT_PLAIN[state]
        value = f"{F.EXPECTED_PER_AREA[state]:.2f}"
        if state == F.CANONICAL_STATE:
            return f"| **{label} (canonical)** | **{value}** "
        return f"| {label} | {value} "

    for i in range(half):
        r = right[i] if i < len(right) else None
        rows.append(cell(left[i]) + cell(r) + "|")

    can = F.CANONICAL
    return "\n".join([
        METRIC_NOTE_HEAD, "\n".join(rows), "",
        f"The canonical headline — {can['Q_H_sensible_kWh']:.2f} kWh sensible heating + "
        f"{can['Q_C_sensible_kWh']:.2f} kWh sensible cooling + {can['Q_C_latent_kWh']:.2f} kWh "
        f"gated latent = {can['Q_need_kWh']:.2f} kWh = "
        f"**{can['Q_need_kWh_per_sqm']:.2f} kWh/m²·yr** at `{F.CANONICAL_STATE}` — is asserted "
        "separately. A mismatch on any of these aborts the whole run.",
        "",
    ])


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
- **State labels are rotated, never truncated.** Fourteen states do not fit
  horizontally.
- **The three infiltration states are shaded as a group** in every trajectory
  panel, because they are the subject of Section 3.7.1.
- **F2 and F5 share one renderer**, one band order, one colour map and one
  kWh-per-unit-height, so the difference between them is the model and not the
  drawing. F5 also carries a dashed ghost outline of F2's column extent.
- **No figure invents a number.** Where a required quantity is absent from the
  committed results it is drawn as an explicit gap and reported here (see F10,
  and panels 1–3 of F11).
- **One figure required a re-run, and only one.** F11 needs hourly EnergyPlus
  series that were never committed, because the raw output directory is
  gitignored as regenerable intermediate. They are regenerated by
  `tools/diagnostics/ep_hourly_defect_signatures.py` from the **committed** IDFs
  with `Output:Variable` lines added and no input to any model changed, and every
  run is asserted against the committed annual totals before its series are
  written. Every other figure is read from files already in the repository.
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
        "from the committed result files under `results/`. **The ISO 52016-1 engine was "
        "not re-run.** Every number in every figure is read from a file already in the "
        "repository, so the figures and the tables in the paper are the same "
        "measurements rather than two runs that happen to agree. The one exception is "
        "F11, which needs hourly EnergyPlus series that were never committed; they are "
        "regenerated from the committed IDFs by "
        "`tools/diagnostics/ep_hourly_defect_signatures.py` with output variables added "
        "and no input to any model changed, and each run is asserted against the "
        "committed annual totals before its series are written.",
        "",
        f"**Weather:** `{F.WEATHER}`  ",
        f"**Canonical state:** `{F.CANONICAL_STATE}` — "
        f"{F.CANONICAL['Q_H_sensible_kWh']:.2f} kWh sensible heating, "
        f"{F.CANONICAL['Q_C_sensible_kWh']:.2f} kWh sensible cooling, "
        f"{F.CANONICAL['Q_C_latent_kWh']:.2f} kWh gated latent, "
        f"{F.CANONICAL['Q_need_kWh']:.2f} kWh total, "
        f"**{F.CANONICAL['Q_need_kWh_per_sqm']:.2f} kWh/m²·yr**  ",
        f"**Net floor area:** {F.NET_FLOOR_AREA_M2:.0f} m²",
        "",
        "## The metric",
        "",
        metric_note(),
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
        "The paper's allocation before this round was F1, F2, F3, F5, F6 and F8 in the "
        "main text, F4 and F10 if the figure budget allows, and F7 and F9 supplementary. "
        "Three figures have been added and the allocation is revised as follows.",
        "",
        "- **F1 is unchanged in placement and mandatory in content.** It was rebuilt "
        "because the previous version contradicted Table 3; the old one must not be used.",
        "- **F13 does not consume a new slot.** It replaces the photograph placeholder "
        "already allotted space in the case-study section. If the photograph is kept "
        "instead, F13 is the first of the three new figures to drop — it carries no "
        "measurement that is not also in the text.",
        "- **F12 is the strongest candidate for promotion.** Section 4.1.3's argument — "
        "that the loss-path totals agree while two large opposing differences carry "
        "almost all the disagreement — is the paper's own statement of the failure mode "
        "it set out to detect, and it is hard to follow in prose. It should displace F4 "
        "or F10 before it is dropped.",
        "- **F11 is supplementary, but should exist either way.** It is the only evidence "
        "for a claim the paper makes prominently: that a detailed reference can be "
        "misconfigured in four separate ways and still produce plausible annual totals. "
        "If the appendix is constrained, F7 and F9 should go before it — F9 is a visual "
        "restatement of columns already in the trajectory table, and F7 compares two "
        "weather files on a question the wind-profile section now supersedes.",
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
            out.append(f"- `{src}`" if src.startswith(
                ("results/", "weather_cache/", "pybuildingenergy/", "examples/",
                 "tools/")) else f"- {src}")
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
        "Two committed inputs are themselves generated, and only need regenerating "
        "when the results they read move:",
        "",
        "```bash",
        "# F12: the loss-path decomposition, parsed out of DISCREPANCY.md section 1",
        "python3 tools/paper/extract_loss_paths.py",
        "",
        "# F11: hourly EnergyPlus series, from the committed IDFs with output",
        "#      variables added and no input to any model changed. Needs an",
        "#      EnergyPlus 24.1.0 binary; asserts every run against the committed",
        "#      annual totals before it writes anything.",
        "python3 tools/diagnostics/ep_hourly_defect_signatures.py \\",
        "    --energyplus /path/to/energyplus",
        "```",
        "",
    ]

    path = F.FIGDIR / "FIGURES.md"
    path.write_text("\n".join(out))
    print(f"  ok    index {path.relative_to(F.REPO)}")


if __name__ == "__main__":
    raise SystemExit(main())
