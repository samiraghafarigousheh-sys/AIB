"""
Compare two run_case.py JSON summaries metric by metric.

Two modes:

* ``--assert-identical`` — used to prove a change is inert when switched off.
  Exits non-zero if any metric differs by more than --tol (default: exactly 0).
* default — report the metrics that moved, largest relative change first.

Usage
-----
    python tools/compare_runs.py base.json off.json --assert-identical
    python tools/compare_runs.py base.json on.json --top 25
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--tol", type=float, default=0.0, help="absolute tolerance for 'identical'")
    ap.add_argument("--assert-identical", action="store_true")
    ap.add_argument("--top", type=int, default=20, help="how many changed metrics to list")
    args = ap.parse_args()

    da, db = load(args.a), load(args.b)
    keys = sorted((set(da) | set(db)) - {"_label", "_options"})

    diffs = []
    missing = []
    for k in keys:
        va, vb = da.get(k), db.get(k)
        if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
            if va != vb:
                missing.append((k, va, vb))
            continue
        if math.isnan(va) and math.isnan(vb):
            continue
        delta = vb - va
        if abs(delta) <= args.tol:
            continue
        rel = delta / va if va not in (0, None) and abs(va) > 1e-12 else float("inf")
        diffs.append((k, va, vb, delta, rel))

    print(f"A = {da.get('_label')}  opts={da.get('_options')}")
    print(f"B = {db.get('_label')}  opts={db.get('_options')}")
    print(f"{len(keys)} metrics compared; {len(diffs)} numeric differences; {len(missing)} non-numeric mismatches\n")

    if args.assert_identical:
        if diffs or missing:
            print("NOT IDENTICAL — differing metrics:")
            for k, va, vb, delta, rel in diffs[: args.top]:
                print(f"  {k}: {va!r} -> {vb!r}  (delta {delta:+.6g})")
            for k, va, vb in missing[: args.top]:
                print(f"  {k}: {va!r} -> {vb!r}")
            sys.exit(1)
        print("IDENTICAL: every metric matches exactly.")
        return

    diffs.sort(key=lambda t: abs(t[4]) if math.isfinite(t[4]) else float("inf"), reverse=True)
    if not diffs:
        print("No numeric differences.")
    else:
        print(f"{'metric':<62} {'A':>14} {'B':>14} {'delta':>13} {'rel':>9}")
        print("-" * 118)
        for k, va, vb, delta, rel in diffs[: args.top]:
            rel_s = f"{rel*100:+.2f}%" if math.isfinite(rel) else "n/a"
            print(f"{k[:62]:<62} {va:>14.4g} {vb:>14.4g} {delta:>+13.4g} {rel_s:>9}")
    for k, va, vb in missing:
        print(f"[non-numeric] {k}: {va!r} -> {vb!r}")


if __name__ == "__main__":
    main()
