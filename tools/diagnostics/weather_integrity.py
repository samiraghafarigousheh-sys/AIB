"""
Weather-file integrity: read the EPW wind column and refuse a repeat of the RO defect.

WHY THIS EXISTS
---------------
The previous canonical run used ``AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw``
(Melbourne Regional Office, WMO 948680). Four whole calendar months of its wind
column -- January, March, July and September, 2,952 hours, 33.7 % of the year --
read exactly 0.0 m/s for every hour. That is not calm; the station's record ends
in 2014 and the TMYx composite silently filled those months with zeros. The EPW
missing-value code for wind speed (999) appears nowhere in the file, so nothing
marks the hours as absent and the engine reads them as genuine dead calm.

That mattered because correction C2 replaces the ISO fixed external convective
coefficient with ``h_ce = 4v + 4``. At v = 0 that collapses to 4 W/(m2 K)
against the ISO constant's 20 -- a five-fold *weakening* of the external film,
which drives the sol-air temperature of the exposed west wall up and tripled
sensible cooling. 96 % of the C2 cooling increase came from those fabricated
zero-wind hours.

So the wind column is now screened before any number is computed from it, and a
degenerate month aborts the run rather than producing a headline nobody can
defend. This module is pure stdlib on purpose: it is a *preflight*, and must be
able to run before -- and independently of -- the engine, numpy or pandas.

Usage
-----
    python tools/diagnostics/weather_integrity.py \\
        weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw

    # before/after contrast against the file this replaces
    python tools/diagnostics/weather_integrity.py A.epw B.epw --json out.json
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from pathlib import Path

# EPW data-row column indices (0-based), per the EnergyPlus Auxiliary Programs
# weather-file format: 0 year, 1 month, 2 day, 3 hour, ... 21 wind speed.
COL_MONTH = 1
COL_WIND = 21

EPW_HEADER_ROWS = 8          # LOCATION .. DATA PERIODS, then the hourly rows begin
EPW_WIND_MISSING = 999.0     # the format's own missing code, absent from the RO file
PIVOT_MS = 4.0               # 4v + 4 == 20 W/(m2 K), the ISO fixed value C2 replaces

# A month at or above this share of exactly-zero hours is not weather. The RO
# file's four bad months sit at 100 %; its worst genuine month sits far below.
DEGENERATE_ZERO_SHARE = 0.90


class WeatherIntegrityError(RuntimeError):
    """The wind column is not usable as a physical input."""


def read_epw_wind(path: Path) -> tuple[list[int], list[float], dict]:
    """Return (month per row, wind speed per row, LOCATION header fields).

    Rows whose wind speed is the EPW missing code are returned as ``None`` so a
    file that *does* flag its gaps is distinguishable from one that zero-fills
    them -- the whole point of the screen.
    """
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or not lines[0].upper().startswith("LOCATION"):
        raise WeatherIntegrityError(f"{path} does not start with an EPW LOCATION header")

    h = [p.strip() for p in lines[0].split(",")]
    header = {
        "city": h[1] if len(h) > 1 else "",
        "state": h[2] if len(h) > 2 else "",
        "country": h[3] if len(h) > 3 else "",
        "wmo": h[5] if len(h) > 5 else "",
        "latitude": float(h[6]) if len(h) > 6 else float("nan"),
        "longitude": float(h[7]) if len(h) > 7 else float("nan"),
        "timezone": float(h[8]) if len(h) > 8 else float("nan"),
        "elevation": float(h[9]) if len(h) > 9 else float("nan"),
    }

    months: list[int] = []
    winds: list[float | None] = []
    for ln in lines[EPW_HEADER_ROWS:]:
        if not ln.strip():
            continue
        f = ln.split(",")
        if len(f) <= COL_WIND:
            continue
        try:
            m = int(float(f[COL_MONTH]))
            v = float(f[COL_WIND])
        except ValueError:
            continue
        months.append(m)
        winds.append(None if v >= EPW_WIND_MISSING else v)
    return months, winds, header


def wind_integrity(path: Path) -> dict:
    """Characterise the wind column of one EPW. No engine, no numpy."""
    path = Path(path).resolve()
    months, winds, header = read_epw_wind(path)

    n = len(winds)
    present = [v for v in winds if v is not None]
    n_missing = n - len(present)
    mean = sum(present) / len(present) if present else float("nan")
    n_zero = sum(1 for v in present if v == 0.0)
    n_above = sum(1 for v in present if v > PIVOT_MS)

    per_month: dict[int, dict] = {}
    for m in range(1, 13):
        vals = [v for mm, v in zip(months, winds) if mm == m and v is not None]
        nm = sum(1 for mm in months if mm == m)
        z = sum(1 for v in vals if v == 0.0)
        per_month[m] = {
            "name": calendar.month_abbr[m],
            "hours": nm,
            "hours_present": len(vals),
            "zero_hours": z,
            "zero_share": (z / len(vals)) if vals else 1.0,
            "mean": (sum(vals) / len(vals)) if vals else float("nan"),
            "max": max(vals) if vals else float("nan"),
        }

    degenerate = [m for m in range(1, 13)
                  if per_month[m]["zero_share"] >= DEGENERATE_ZERO_SHARE]

    return {
        "path": str(path),
        "name": path.name,
        "header": header,
        "n_rows": n,
        "n_missing_wind": n_missing,
        "mean_wind_ms": mean,
        "pct_hours_exactly_zero": 100.0 * n_zero / len(present) if present else float("nan"),
        "pct_hours_above_pivot": 100.0 * n_above / len(present) if present else float("nan"),
        "pivot_ms": PIVOT_MS,
        "max_wind_ms": max(present) if present else float("nan"),
        "per_month": per_month,
        "degenerate_months": degenerate,
        "degenerate_hours": sum(per_month[m]["hours"] for m in degenerate),
        "usable": not degenerate and n_missing == 0 and n == 8760,
    }


def format_report(s: dict, indent: str = "  ") -> str:
    h = s["header"]
    L = [
        f"{indent}resolved path        : {s['path']}",
        f"{indent}station              : {h['city']}, {h['state']} {h['country']} "
        f"(WMO {h['wmo']}, lat {h['latitude']:.4f}, lon {h['longitude']:.4f}, tz {h['timezone']:+.0f})",
        f"{indent}rows                 : {s['n_rows']:,}   missing wind values: {s['n_missing_wind']:,}",
        f"{indent}annual mean wind     : {s['mean_wind_ms']:.2f} m/s   (max {s['max_wind_ms']:.1f})",
        f"{indent}hours exactly 0.0    : {s['pct_hours_exactly_zero']:.2f} %",
        f"{indent}hours above {s['pivot_ms']:.0f} m/s    : {s['pct_hours_above_pivot']:.1f} %   "
        f"(the pivot where 4v+4 = 20 = the ISO fixed h_ce)",
    ]
    bad = s["degenerate_months"]
    if bad:
        L.append(f"{indent}DEAD-CALM MONTHS     : "
                 + ", ".join(f"{calendar.month_abbr[m]} "
                             f"({100 * s['per_month'][m]['zero_share']:.0f} % zero)" for m in bad)
                 + f"   [{s['degenerate_hours']:,} h, "
                   f"{100 * s['degenerate_hours'] / max(1, s['n_rows']):.1f} % of the year]")
    else:
        worst = max(range(1, 13), key=lambda m: s["per_month"][m]["zero_share"])
        L.append(f"{indent}dead-calm months     : none — worst is "
                 f"{calendar.month_abbr[worst]} at "
                 f"{100 * s['per_month'][worst]['zero_share']:.1f} % exact-zero hours")
    return "\n".join(L)


def assert_usable(path: Path, expect_name_contains: str | None = None,
                  quiet: bool = False) -> dict:
    """Screen an EPW and abort the run if its wind column is not physical.

    ``expect_name_contains`` is the guard against a *cached* file being picked up
    instead of the intended one: the resolved absolute path is printed and its
    name checked, so silently re-running on the old RO file is impossible.
    """
    s = wind_integrity(path)
    if not quiet:
        print("weather preflight — EPW wind-column integrity", flush=True)
        print(format_report(s), flush=True)

    if expect_name_contains and expect_name_contains.lower() not in s["name"].lower():
        raise WeatherIntegrityError(
            f"\nWRONG WEATHER FILE.\n"
            f"  resolved: {s['path']}\n"
            f"  expected a file whose name contains '{expect_name_contains}'.\n"
            f"This run would not be on the intended station — very likely a cached "
            f"file was picked up. Aborting rather than publishing numbers labelled "
            f"with the wrong weather."
        )

    if s["n_missing_wind"]:
        raise WeatherIntegrityError(
            f"\n{s['name']}: {s['n_missing_wind']:,} hours carry the EPW wind "
            f"missing-value code ({EPW_WIND_MISSING:.0f}). h_ce = 4v + 4 cannot be "
            f"evaluated on absent data. Aborting."
        )

    if s["degenerate_months"]:
        names = ", ".join(calendar.month_abbr[m] for m in s["degenerate_months"])
        raise WeatherIntegrityError(
            f"\nDEGENERATE WIND COLUMN in {s['name']}.\n"
            f"  {names} are at or above {100 * DEGENERATE_ZERO_SHARE:.0f} % exactly-zero "
            f"wind — {s['degenerate_hours']:,} hours, "
            f"{100 * s['degenerate_hours'] / max(1, s['n_rows']):.1f} % of the year.\n\n"
            f"A meteorological record does not produce whole months of exactly zero "
            f"wind. This is the defect diagnosed in "
            f"AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw, where it drove a "
            f"spurious tripling of sensible cooling through h_ce = 4v + 4 collapsing "
            f"to 4 W/(m²·K) at v = 0.\n\n"
            f"Aborting: no cooling figure computed on this file is defensible."
        )

    if s["n_rows"] != 8760:
        raise WeatherIntegrityError(
            f"\n{s['name']}: {s['n_rows']:,} data rows, expected 8,760."
        )

    if not quiet:
        print("  VERDICT              : wind column passes — no dead-calm month, "
              "no missing values, 8,760 rows.\n", flush=True)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("epw", nargs="+")
    ap.add_argument("--json", default=None, help="write the full stats here")
    ap.add_argument("--no-assert", action="store_true",
                    help="report only; do not exit non-zero on a degenerate column")
    args = ap.parse_args()

    out, failed = {}, []
    for p in args.epw:
        s = wind_integrity(Path(p))
        out[s["name"]] = s
        print(f"\n{s['name']}")
        print(format_report(s))
        print(f"  usable               : {'YES' if s['usable'] else 'NO'}")
        if not s["usable"]:
            failed.append(s["name"])

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nwrote -> {args.json}")

    if failed and not args.no_assert:
        print(f"\nUNUSABLE: {', '.join(failed)}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
