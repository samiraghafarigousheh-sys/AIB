"""
Assert that both harnesses report the SAME baseline engine result.

WHY THIS EXISTS
---------------
``compare_branches_apt305.py`` and ``baseline_vs_energyplus.py`` both drive the
unmodified ISO 52016-1 engine on the same building, so their baseline figures
must match. At one point they did not — 150 kWh heating in one chart, 40 kWh in
the other — and the charts alone could not say why, because a chart subtitle is
not evidence.

The cause was weather, not physics: one run had resolved to a PVGIS TMY and the
other to a Melbourne EPW, because ``resolve()`` falls back silently. Both runs
now write ``run_meta.json``, and this script compares those first. If the
weather differs it says so instead of blaming the engine.

Usage
-----
    python examples/check_baseline_consistency.py
    python examples/check_baseline_consistency.py --branches results/apt305 \
        --vs-ep results/baseline_vs_ep
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fractional tolerance. The two harnesses call the same engine with the same
# inputs, so agreement should be exact; 1e-6 leaves room for CSV rounding only.
TOL = 1e-6


def _meta(d: Path) -> dict:
    p = d / "run_meta.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _branch_baseline(d: Path) -> dict[str, float]:
    """Heating and cooling from the Baseline column of comparison.csv."""
    p = d / "comparison.csv"
    if not p.is_file():
        raise SystemExit(f"missing {p} — run compare_branches_apt305.py first")
    out = {}
    with p.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["Metric"] == "Heating need":
                out["heating_kWh"] = float(row["Baseline"])
            elif row["Metric"] == "Cooling need":
                out["cooling_kWh"] = float(row["Baseline"])
    return out


def _ep_iso(d: Path) -> dict[str, float]:
    """Heating and cooling from the ISO column of baseline_vs_energyplus.csv."""
    p = d / "baseline_vs_energyplus.csv"
    if not p.is_file():
        raise SystemExit(f"missing {p} — run baseline_vs_energyplus.py first")
    out = {}
    with p.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["Metric"] == "Heating":
                out["heating_kWh"] = float(row["ISO_52016_kWh"])
            elif row["Metric"] == "Cooling":
                out["cooling_kWh"] = float(row["ISO_52016_kWh"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--branches", type=Path, default=REPO_ROOT / "results" / "apt305")
    ap.add_argument("--vs-ep", type=Path, default=REPO_ROOT / "results" / "baseline_vs_ep")
    args = ap.parse_args()

    mb, me = _meta(args.branches), _meta(args.vs_ep)
    print("weather actually used")
    print(f"  compare_branches      : {mb.get('weather_label', '(no run_meta.json)')}")
    print(f"  baseline_vs_energyplus: {me.get('weather_label', '(no run_meta.json)')}")
    print()

    same_weather = (
        mb.get("weather_source") == me.get("weather_source")
        and mb.get("weather_path") == me.get("weather_path")
    )
    if mb and me and not same_weather:
        print("FAIL  the two runs used DIFFERENT weather, so their baselines cannot be\n"
              "      compared. Re-run both with the same --weather file.\n")
        sys.exit(1)

    a, b = _branch_baseline(args.branches), _ep_iso(args.vs_ep)
    ok = True
    head = f"{'Metric':<12}{'compare_branches':>20}{'baseline_vs_EP':>18}{'rel. diff':>14}"
    print(head)
    print("-" * len(head))
    for key, label in (("heating_kWh", "Heating"), ("cooling_kWh", "Cooling")):
        x, y = a.get(key, float("nan")), b.get(key, float("nan"))
        denom = max(abs(x), abs(y), 1e-12)
        rel = abs(x - y) / denom
        ok &= rel <= TOL
        print(f"{label:<12}{x:>20,.6f}{y:>18,.6f}{rel:>14.2e}")
    print()

    if ok:
        print("PASS  both harnesses report the same baseline engine result.\n")
    else:
        print("FAIL  the baselines differ by more than the tolerance on identical\n"
              "      weather — that is a real harness discrepancy, not weather.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
