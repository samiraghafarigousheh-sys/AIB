"""
Extract the loss-path decomposition of Section 4.1.3 into a machine-readable CSV.

The per-path comparison behind figure F12 exists in the repository only as a
markdown table -- ``results/paper/validation_corrected/DISCREPANCY.md`` section 1
-- which no figure can read reliably. This script parses that table once and
writes ``loss_paths.csv`` beside it, so F12 is built from a committed data file
rather than from prose, and can be regenerated when the decomposition moves.

The parse is checked as it runs: every row's stated difference has to equal
ISO - EnergyPlus to the printed precision, and the paths have to sum to the
table's own total row. A markdown table that fails either check is not a
decomposition, and the script stops rather than writing it.

    python3 tools/paper/extract_loss_paths.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "results" / "paper" / "validation_corrected" / "DISCREPANCY.md"
TARGET = REPO / "results" / "paper" / "validation_corrected" / "loss_paths.csv"

HEADER = "| Loss path | ISO 52016-1 | EnergyPlus |"
TOTAL_LABEL = "Σ compared paths"

# Short labels for the figure's y axis. Keyed by the full label in the markdown,
# so a change of wording there fails loudly here rather than mislabelling a bar.
SHORT_LABEL = {
    "West exterior wall (opaque, 11.88 m²)": "West exterior wall\n(opaque, 11.88 m²)",
    "West windows (1.62 m²), conduction + transmitted solar":
        "West windows (1.62 m²)\nconduction + transmitted solar",
    "Five party surfaces (75.10 m², to 20 °C neighbours)":
        "Five party surfaces\n(75.10 m², to 20 °C neighbours)",
    "Designed ventilation (2.0 l/s·m², H_ve = 48.4 W/K)":
        "Designed ventilation\n(H_ve = 48.4 W/K)",
    "Envelope infiltration": "Envelope infiltration",
}


class ExtractionFailed(RuntimeError):
    """The markdown table is not a decomposition this script can trust."""


def _clean(cell: str) -> str:
    return cell.replace("**", "").replace("`", "").strip()


def _number(cell: str) -> float:
    text = _clean(cell).replace(",", "").replace("−", "-").replace("+", "")
    return float(text)


def parse(md: str) -> tuple[list[dict], dict]:
    lines = md.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(HEADER))
    except StopIteration as exc:
        raise ExtractionFailed(
            f"{SOURCE.name} has no loss-path table starting {HEADER!r}"
        ) from exc

    rows, total = [], None
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [c for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            break
        label = _clean(cells[0])
        iso, ep, delta = (_number(cells[1]), _number(cells[2]), _number(cells[3]))
        record = {"path": label, "iso_kWh": iso, "ep_kWh": ep, "diff_kWh": delta}
        if label == TOTAL_LABEL:
            total = record
        else:
            rows.append(record)

    if total is None:
        raise ExtractionFailed(f"{SOURCE.name}: no {TOTAL_LABEL!r} row in the table")
    if not rows:
        raise ExtractionFailed(f"{SOURCE.name}: loss-path table has no path rows")
    return rows, total


def verify(rows: list[dict], total: dict) -> None:
    """
    Check the table against itself, within what its own printed precision allows.

    Every cell is quoted to 0.1 kWh, so each carries up to 0.05 kWh of rounding.
    A stated difference is the difference of two *unrounded* values, so it may
    disagree with the difference of the two rounded ones by up to 0.1; a sum of
    n rounded rows may disagree with a separately rounded total by up to
    0.05(n + 1). Those are the tolerances used here. Anything outside them is a
    real inconsistency, not a rounding artefact.
    """
    problems = []
    for r in rows:
        stated, computed = r["diff_kWh"], r["iso_kWh"] - r["ep_kWh"]
        if abs(stated - computed) > 0.1 + 1e-9:
            problems.append(
                f"  {r['path']}: table states Δ = {stated:+.1f}, "
                f"ISO − E+ = {computed:+.1f}"
            )
    sum_tol = 0.05 * (len(rows) + 1) + 1e-9
    for key in ("iso_kWh", "ep_kWh"):
        summed = sum(r[key] for r in rows)
        if abs(summed - total[key]) > sum_tol:
            problems.append(
                f"  {key}: paths sum to {summed:+.1f}, the table's Σ row states "
                f"{total[key]:+.1f} (tolerance {sum_tol:.2f})"
            )
    missing = [r["path"] for r in rows if r["path"] not in SHORT_LABEL]
    if missing:
        problems.append(
            "  loss-path labels not known to this script (the decomposition changed "
            "wording or gained a path): " + ", ".join(repr(m) for m in missing)
        )
    if problems:
        raise ExtractionFailed(
            f"{SOURCE.name} loss-path table does not close:\n" + "\n".join(problems)
        )


def main() -> int:
    rows, total = parse(SOURCE.read_text())
    verify(rows, total)

    ordered = sorted(rows, key=lambda r: abs(r["diff_kWh"]), reverse=True)
    with TARGET.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "short_label", "iso_kWh", "ep_kWh", "diff_kWh", "is_total"])
        for r in ordered:
            w.writerow([r["path"], SHORT_LABEL[r["path"]].replace("\n", " | "),
                        f"{r['iso_kWh']:.1f}", f"{r['ep_kWh']:.1f}",
                        f"{r['diff_kWh']:.1f}", "no"])
        w.writerow([total["path"], "Sum of the compared paths",
                    f"{total['iso_kWh']:.1f}", f"{total['ep_kWh']:.1f}",
                    f"{total['diff_kWh']:.1f}", "yes"])

    print(f"  {len(ordered)} loss paths + total -> {TARGET.relative_to(REPO)}")
    for r in ordered:
        print(f"    {r['path']:<56} ISO {r['iso_kWh']:>9.1f}  "
              f"E+ {r['ep_kWh']:>9.1f}  Δ {r['diff_kWh']:>+7.1f}")
    print(f"    {total['path']:<56} ISO {total['iso_kWh']:>9.1f}  "
          f"E+ {total['ep_kWh']:>9.1f}  Δ {total['diff_kWh']:>+7.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
