"""
Hourly EnergyPlus series for the four reference-model defects (figure F11).

The raw EnergyPlus output directory is gitignored as regenerable intermediate,
so the hourly series F11 needs are not in the repository. This script
regenerates them, from the **committed** IDFs and with **output variables only**
added -- no input to any model is changed, which is what makes the re-run the
same measurement rather than a second one.

Three runs, each an unmodified committed IDF plus an ``Output:Variable`` block:

  A  results/paper/validation_corrected/apt305_conditioned.idf
     The matched corrected reference. Carries the outdoor-air, ventilation and
     plant-operation series for defects 1-3, and the west-wall surface wind at
     the corrected height for defect 4.

  B  results/paper_pre_wind_profile/validation_corrected/apt305_conditioned.idf
     The SAME case as published, before the geometry was translated up three
     storeys. This is the only one of the four defects whose defective state is
     committed, so defect 4 is instrumented in the defective state and the other
     three in their repaired state.

  C  results/paper/validation_corrected/apt305_baseline_repaired.idf
     The baseline reference. The ~300 kWh/yr humidification term belongs to this
     case, so the total-against-sensible heating audit for defect 3 is read here.

Every run is asserted against the annual totals already committed in
``results/paper/validation_corrected/validation_corrected.csv`` before anything
is written. A run that does not reproduce them is not the same model, and the
script stops rather than writing a series the figures would then draw.

    python3 tools/diagnostics/ep_hourly_defect_signatures.py \
        --energyplus /path/to/energyplus
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPER = REPO / "results" / "paper"
VC = PAPER / "validation_corrected"
OUTDIR = VC / "hourly"
EPW = REPO / "weather_cache" / "AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw"

J_PER_KWH = 3.6e6

# Output variables added to each committed IDF. Nothing else is touched.
EXTRA_A = """
! ---- F11 instrumentation (tools/diagnostics/ep_hourly_defect_signatures.py).
! ---- Output variables only. No input to the model is changed.
  Output:Variable, *, Zone Ideal Loads Outdoor Air Mass Flow Rate, Hourly;
  Output:Variable, *, Zone Ideal Loads Supply Air Mass Flow Rate, Hourly;
  Output:Variable, *, Zone Ideal Loads Supply Air Latent Heating Energy, Hourly;
  Output:Variable, *, Zone Ideal Loads Supply Air Latent Cooling Energy, Hourly;
  Output:Variable, *, Zone Ventilation Mass Flow Rate, Hourly;
  Output:Variable, *, Zone Mechanical Ventilation Mass Flow Rate, Hourly;
  Output:Variable, *, Surface Outside Face Outdoor Air Wind Speed, Hourly;
  Output:Variable, *, Site Wind Speed, Hourly;
"""

EXTRA_B = """
! ---- F11 instrumentation (tools/diagnostics/ep_hourly_defect_signatures.py).
! ---- Output variables only. No input to the model is changed.
  Output:Variable, *, Surface Outside Face Outdoor Air Wind Speed, Hourly;
  Output:Variable, *, Site Wind Speed, Hourly;
"""

EXTRA_C = """
! ---- F11 instrumentation (tools/diagnostics/ep_hourly_defect_signatures.py).
! ---- Output variables only. No input to the model is changed.
  Output:Variable, *, Zone Ideal Loads Supply Air Sensible Heating Energy, Hourly;
  Output:Variable, *, Zone Ideal Loads Supply Air Total Heating Energy, Hourly;
  Output:Variable, *, Zone Ideal Loads Supply Air Latent Heating Energy, Hourly;
  Output:Variable, *, Zone Ideal Loads Supply Air Sensible Cooling Energy, Hourly;
  Output:Variable, *, Zone Ideal Loads Supply Air Latent Cooling Energy, Hourly;
  Output:Variable, *, Zone Ideal Loads Outdoor Air Mass Flow Rate, Hourly;
  Output:Variable, *, Zone Ideal Loads Supply Air Mass Flow Rate, Hourly;
  Output:Variable, *, Zone Ventilation Mass Flow Rate, Hourly;
"""

RUNS = {
    "A": {
        "idf": VC / "apt305_conditioned.idf",
        "extra": EXTRA_A,
        "out": "hourly_corrected_matched.csv",
        "columns": {
            "ideal_loads_outdoor_air_mass_flow_kg_s":
                "APT305_IDEALLOADS:Zone Ideal Loads Outdoor Air Mass Flow Rate",
            "zone_ventilation_mass_flow_kg_s":
                "APT305:Zone Ventilation Mass Flow Rate",
            "ideal_loads_supply_air_mass_flow_kg_s":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Mass Flow Rate",
            "heating_sensible_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Sensible Heating Energy",
            "heating_total_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Total Heating Energy",
            "heating_latent_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Latent Heating Energy",
            "cooling_sensible_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Sensible Cooling Energy",
            "cooling_latent_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Latent Cooling Energy",
            "site_wind_m_s": "Environment:Site Wind Speed",
            "westwall_surface_wind_m_s":
                "WESTWALL:Surface Outside Face Outdoor Air Wind Speed",
        },
    },
    "B": {
        "idf": (REPO / "results" / "paper_pre_wind_profile" / "validation_corrected"
                / "apt305_conditioned.idf"),
        "extra": EXTRA_B,
        "out": "hourly_as_published_wind.csv",
        "columns": {
            "site_wind_m_s": "Environment:Site Wind Speed",
            "westwall_surface_wind_m_s":
                "WESTWALL:Surface Outside Face Outdoor Air Wind Speed",
            "westwin_fixed_surface_wind_m_s":
                "WESTWIN_FIXED:Surface Outside Face Outdoor Air Wind Speed",
        },
    },
    "C": {
        "idf": VC / "apt305_baseline_repaired.idf",
        "extra": EXTRA_C,
        "out": "hourly_baseline_repaired.csv",
        "columns": {
            "heating_sensible_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Sensible Heating Energy",
            "heating_total_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Total Heating Energy",
            "heating_latent_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Latent Heating Energy",
            "cooling_sensible_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Sensible Cooling Energy",
            "cooling_latent_J":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Latent Cooling Energy",
            "ideal_loads_outdoor_air_mass_flow_kg_s":
                "APT305_IDEALLOADS:Zone Ideal Loads Outdoor Air Mass Flow Rate",
            "zone_ventilation_mass_flow_kg_s":
                "APT305:Zone Ventilation Mass Flow Rate",
            "ideal_loads_supply_air_mass_flow_kg_s":
                "APT305_IDEALLOADS:Zone Ideal Loads Supply Air Mass Flow Rate",
        },
    },
}

# The committed annual totals each run has to reproduce, in kWh, and the
# committed surface-wind means for the two wind states. Tolerances are one unit
# in the committed value's last printed place.
GATES = {
    "A": [("heating_sensible_J", 148.973, 5e-3), ("cooling_sensible_J", 21.590, 5e-3)],
    "C": [("heating_sensible_J", 2081.972, 5e-3), ("cooling_sensible_J", 697.348, 5e-3)],
}
WIND_GATES = {
    # run, column, committed mean (results/paper/wind_profile/wind_profile.md), tol
    "A": [("site_wind_m_s", 4.840, 5e-4), ("westwall_surface_wind_m_s", 3.182, 5e-4)],
    "B": [("site_wind_m_s", 4.840, 5e-4), ("westwall_surface_wind_m_s", 2.233, 5e-4),
          ("westwin_fixed_surface_wind_m_s", 2.269, 5e-4)],
}


class RunMismatch(RuntimeError):
    """A re-run did not reproduce the committed annual totals."""


def run_energyplus(idf: Path, extra: str, ep_bin: str, workdir: Path, tag: str) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / "in.idf"
    target.write_text(idf.read_text() + "\n" + extra)
    proc = subprocess.run(
        [ep_bin, "-w", str(EPW), "-d", str(workdir), "-p", tag, "-r", str(target)],
        capture_output=True, text=True,
    )
    csv_path = workdir / f"{tag}out.csv"
    if proc.returncode != 0 or not csv_path.exists():
        raise RunMismatch(
            f"EnergyPlus failed on {idf.name}:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
    return csv_path


def read_eplus_csv(path: Path) -> tuple[list[str], dict[str, list[float]]]:
    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    header = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if len(r) == len(header)]
    stamps = [r[0].strip() for r in body]
    cols: dict[str, list[float]] = {}
    for i, h in enumerate(header[1:], start=1):
        try:
            cols[h] = [float(r[i]) for r in body]
        except ValueError:
            continue
    return stamps, cols


def pick(cols: dict[str, list[float]], prefix: str) -> list[float]:
    for key, values in cols.items():
        if key.startswith(prefix):
            return values
    raise RunMismatch(f"EnergyPlus output has no column starting {prefix!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--energyplus", default=shutil.which("energyplus"),
                    help="path to the EnergyPlus 24.1.0 binary")
    ap.add_argument("--keep", type=Path, default=None,
                    help="keep the raw run directories here instead of a temp dir")
    args = ap.parse_args()
    if not args.energyplus:
        raise SystemExit("EnergyPlus binary not found -- pass --energyplus")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    provenance: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "energyplus": subprocess.run([args.energyplus, "--version"], capture_output=True,
                                     text=True).stdout.strip(),
        "weather": EPW.name,
        "note": ("Output variables only were added to each committed IDF; no input to "
                 "any model was changed."),
        "runs": {},
    }

    root = args.keep or Path(tempfile.mkdtemp(prefix="f11_hourly_"))
    for tag, spec in RUNS.items():
        idf = spec["idf"]
        if not idf.exists():
            raise SystemExit(f"committed IDF missing: {idf}")
        print(f"  run {tag}: {idf.relative_to(REPO)}")
        raw = run_energyplus(idf, spec["extra"], args.energyplus, root / f"run{tag}", tag)
        stamps, cols = read_eplus_csv(raw)
        if len(stamps) != 8760:
            raise RunMismatch(f"run {tag}: {len(stamps)} hourly rows, expected 8760")

        series = {name: pick(cols, prefix) for name, prefix in spec["columns"].items()}

        checks = []
        for column, expected_kWh, tol in GATES.get(tag, []):
            got = sum(series[column]) / J_PER_KWH
            checks.append({"quantity": column, "unit": "kWh", "expected": expected_kWh,
                           "measured": round(got, 6)})
            if abs(got - expected_kWh) > tol:
                raise RunMismatch(
                    f"run {tag}: {column} integrates to {got:.4f} kWh, the committed "
                    f"validation states {expected_kWh} kWh -- this is not the same model"
                )
        for column, expected_ms, tol in WIND_GATES.get(tag, []):
            got = sum(series[column]) / len(series[column])
            checks.append({"quantity": column, "unit": "m/s", "expected": expected_ms,
                           "measured": round(got, 6)})
            if abs(got - expected_ms) > tol:
                raise RunMismatch(
                    f"run {tag}: {column} mean is {got:.4f} m/s, the committed wind "
                    f"profile states {expected_ms} m/s"
                )

        out_path = OUTDIR / spec["out"]
        names = list(series)
        with out_path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["hour_of_year", "date_time"] + names)
            for h in range(8760):
                w.writerow([h + 1, stamps[h]] + [f"{series[n][h]:.7g}" for n in names])

        provenance["runs"][tag] = {
            "idf": str(idf.relative_to(REPO)),
            "output_csv": str(out_path.relative_to(REPO)),
            "n_hours": 8760,
            "columns": names,
            "assertions": checks,
        }
        for c in checks:
            print(f"        {c['quantity']:<44} {c['measured']:>12.4f} "
                  f"vs committed {c['expected']} {c['unit']}  OK")

    (OUTDIR / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"\n  wrote {OUTDIR.relative_to(REPO)}/ "
          f"({len(provenance['runs'])} runs, provenance.json)")
    if args.keep is None:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
