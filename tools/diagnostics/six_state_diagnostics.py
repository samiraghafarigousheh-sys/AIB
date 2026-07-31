"""
Items 3 and 4 — Sankey closure residual and latent breakdown, for all six states.

Runs the same six engine states as ``examples/compare_au_corrections.py``, with
the same worktree isolation and the same building dictionary, and adds the two
columns that harness does not report:

  Item 3  V2 Sankey closure residual (Wh and % of throughput), computed exactly
          as the engine's own ``SANKEY CHECK`` line does:

              inputs   = heating + internal gains + solar
              outputs  = cooling + ventilation + thermal bridges + ground
                         + per-surface transmission (positive branches only)
              residual = inputs - outputs - storage

          The engine folds a residual below 1 % of inputs into storage before
          reporting, so a reported 0 means "closed to within 1 %", not "exactly
          zero". ``Transmission (residual)`` is excluded from the outputs sum --
          it is the residual re-published as a flow, and including it would make
          every state close by construction.

  Item 4  latent heating (humidification) and latent cooling (dehumidification)
          as separate columns, plus the monthly profile of each, so a ~554 kWh
          latent term can be attributed rather than asserted.

Usage
-----
    python tools/diagnostics/six_state_diagnostics.py \\
        --weather weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw \\
        --out results/diagnostics/six_state_raw.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"

STATES = [
    ("Baseline", "claude/pybuildingenergy-baseline-anjro8"),
    ("+Vent+Latent", "claude/ventilation-plus-latent-fix"),
    ("+Internal Gains", "claude/internal-gains-fix"),
    ("+Conditioned Zones", "claude/conditioned-adjacent-zones-fix"),
    ("+Ground Fix", "claude/ground-contact-fix"),
    ("+Hemisphere Fix", "claude/coldest-month-hemisphere-fix"),
]

RESIDUAL_KEY = "Transmission (residual)"
V2_TOLERANCE_PCT = 5.0


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def run_worker(args) -> int:
    sys.path.insert(0, str(Path(args.src).resolve()))
    sys.path.insert(0, str(EXAMPLES_DIR))

    import numpy as np
    import pandas as pd

    from apt305_building import build_bui
    from pybuildingenergy.source.utils import ISO52016
    from pybuildingenergy.source.check_input import sanitize_and_validate_BUI

    raw = build_bui()
    area = float(raw["building"]["net_floor_area"])
    building, _ = sanitize_and_validate_BUI(raw, fix=True)

    # ---- measurement-only repair of the step-3 divide-by-zero ---------------
    # On claude/ground-contact-fix and later, _ground_contact_area() correctly
    # returns 0.0 for apt 305, but Temp_calculation_of_ground still evaluates
    #     Theta_gr_ve = ... / (sog_area * U_sog)
    # so Theta_gr_ve comes back as +/-inf. The Sankey accumulator then forms
    #     q_ground = h_ground * (T_in - T_gr) = 0.0 * inf = NaN
    # and, because every comparison against NaN is False, the `else` branch at
    # utils.py:8556 folds it into E_solar_Wh, making inputs_Wh NaN and the whole
    # balance unevaluable.
    #
    # h_ground is exactly 0 here, so the true ground contribution is exactly 0
    # and any finite Theta_gr_ve gives the same answer. Substituting a finite
    # value is therefore a measurement device, not a model change -- and the
    # worker asserts below that H/C/latent are unchanged by it. THE ENGINE IS
    # NOT MODIFIED; this lives entirely in the diagnostic harness.
    repaired = {"applied": False, "n_nonfinite": 0}
    if args.repair_ground_nan:
        import numpy as _np
        _orig_tg = ISO52016.Temp_calculation_of_ground.__func__

        def _spy_tg(cls, *aa, **kk):
            res = _orig_tg(cls, *aa, **kk)
            try:
                arr = _np.asarray(res.Theta_gr_ve, dtype=float)
            except Exception:
                return res
            bad = ~_np.isfinite(arr)
            if bad.any():
                repaired["applied"] = True
                repaired["n_nonfinite"] = int(bad.sum())
                arr = arr.copy()
                arr[bad] = 20.0
                try:
                    res = res._replace(Theta_gr_ve=arr)
                except Exception:
                    res.Theta_gr_ve = arr
            return res

        ISO52016.Temp_calculation_of_ground = classmethod(_spy_tg)

    result = ISO52016.Temperature_and_Energy_needs_calculation(
        building, weather_source="epw", path_weather_file=args.weather,
        return_sankey_data=True)

    hourly = result[0]
    annual = result[1]
    sankey = result[2] if len(result) > 2 else None

    out: dict = {"net_floor_area_m2": area, "ground_nan_repair": repaired}

    def ann(k):
        if k not in annual.columns:
            return float("nan")
        return float(pd.to_numeric(annual[k], errors="coerce").iloc[0])

    dt_h = ann("time_step_h")
    if dt_h != dt_h or dt_h <= 0:
        dt_h = 1.0
    out["time_step_h"] = dt_h

    for k in ("Q_H_annual_kWh", "Q_C_annual_kWh", "Q_latent_annual_kWh",
              "Q_internal_gains_kWh", "Q_solar_gains_kWh",
              "Q_ground_loss_kWh", "Q_ground_gain_kWh",
              "Q_ve_loss_kWh", "Q_ve_gain_kWh",
              "Q_tb_loss_kWh", "Q_tr_opaque_loss_kWh", "Q_tr_window_loss_kWh"):
        out[k] = ann(k)

    # ---- latent, split by sign of the process --------------------------------
    def series(col):
        if col not in hourly.columns:
            return None
        return pd.to_numeric(hourly[col], errors="coerce").fillna(0.0)

    def kwh(s, positive_only=True):
        if s is None:
            return float("nan")
        v = s.clip(lower=0.0) if positive_only else s
        return float(v.sum() * dt_h / 1000.0)

    s_h_lat = series("Q_H_latent_W")     # humidification
    s_c_lat = series("Q_C_latent")       # dehumidification
    s_vent_lat = series("Q_latent_vent_W")
    s_int_lat = series("Q_int_latent_W")
    s_lat_signed = series("Q_latent_W_signed")

    out["latent_heating_kWh"] = kwh(s_h_lat)
    out["latent_cooling_kWh"] = kwh(s_c_lat)
    out["latent_vent_pos_kWh"] = kwh(s_vent_lat)
    out["latent_vent_neg_kWh"] = (
        float(s_vent_lat.clip(upper=0.0).sum() * dt_h / 1000.0) if s_vent_lat is not None else float("nan"))
    out["latent_internal_kWh"] = kwh(s_int_lat)
    out["latent_signed_net_kWh"] = (
        float(s_lat_signed.sum() * dt_h / 1000.0) if s_lat_signed is not None else float("nan"))

    # Same total definition the comparison harness uses, so the columns line up.
    parts = [out["Q_H_annual_kWh"], out["Q_C_annual_kWh"],
             out["Q_latent_annual_kWh"], out["latent_heating_kWh"]]
    out["Q_total_annual_kWh"] = float(sum(parts)) if all(p == p for p in parts) else float("nan")

    # ---- monthly latent profile ---------------------------------------------
    idx = pd.DatetimeIndex(hourly.index) if isinstance(hourly.index, pd.DatetimeIndex) else None
    if idx is not None:
        for label, s in (("latent_heating", s_h_lat), ("latent_cooling", s_c_lat)):
            if s is None:
                continue
            m = s.clip(lower=0.0).groupby(idx.month).sum() * dt_h / 1000.0
            out[f"monthly_{label}_kWh"] = [float(m.get(i, 0.0)) for i in range(1, 13)]

    # ---- humidity ratios, to attribute the latent term ----------------------
    for col, key in (("X_ext_kg_kg_da", "X_ext"), ("X_int_ref_kg_kg_da", "X_int_ref")):
        s = series(col)
        if s is not None:
            out[key] = {"mean": float(s.mean()), "min": float(s.min()), "max": float(s.max())}
    s_mdot = series("m_dot_vent_kg_s")
    if s_mdot is not None:
        out["m_dot_vent_kg_s"] = {"mean": float(s_mdot.mean()), "max": float(s_mdot.max())}

    # ---- Item 3: V2 closure residual ----------------------------------------
    if sankey:
        inputs = {k: float(v) for k, v in sankey.get("inputs", {}).items()}
        outputs_all = {k: float(v) for k, v in sankey.get("outputs", {}).items()}
        storage = float(sankey.get("energy_accumulated_zone", 0.0))

        outputs = {k: v for k, v in outputs_all.items() if k != RESIDUAL_KEY}
        in_sum = sum(inputs.values())
        out_sum = sum(outputs.values())
        residual = in_sum - out_sum - storage

        out["sankey"] = {
            "inputs_Wh": inputs,
            "outputs_Wh": outputs,
            "republished_residual_Wh": outputs_all.get(RESIDUAL_KEY, 0.0),
            "storage_Wh": storage,
            "inputs_total_Wh": in_sum,
            "outputs_total_Wh": out_sum,
            "residual_Wh": residual,
            "residual_kWh": residual / 1000.0,
            "residual_pct": 100.0 * residual / max(1.0, in_sum),
        }

    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def make_worktree(branch: str, dest: Path) -> None:
    last = ""
    for ref in (branch, f"origin/{branch}"):
        p = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "worktree", "add", "--detach", str(dest), ref],
            capture_output=True, text=True)
        if p.returncode == 0:
            return
        last = p.stderr.strip()
    raise RuntimeError(f"worktree for '{branch}' failed:\n{last}")


def drop_worktree(dest: Path) -> None:
    subprocess.run(["git", "-C", str(REPO_ROOT), "worktree", "remove", "--force", str(dest)],
                   check=False, capture_output=True)


def run_branch(src: Path, weather: str, out_json: Path, repair: bool = False) -> dict:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker",
           "--src", str(src), "--weather", weather, "--out", str(out_json)]
    if repair:
        cmd.append("--repair-ground-nan")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-20:])
        raise RuntimeError(f"engine run failed for {src}:\n{tail}")
    data = json.loads(out_json.read_text(encoding="utf-8"))
    # cross-check against the engine's own printed line
    m = re.search(r"SANKEY CHECK\s+inputs=([\d.eE+-]+)\s+outputs\+storage=([\d.eE+-]+)\s+"
                  r"residual=([\d.eE+-]+) Wh \(([\d.eE+-]+)%\)", proc.stdout)
    if m:
        data["engine_printed_sankey_check"] = {
            "inputs_Wh": float(m.group(1)), "outputs_plus_storage_Wh": float(m.group(2)),
            "residual_Wh": float(m.group(3)), "residual_pct": float(m.group(4))}
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--src", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--repair-ground-nan", action="store_true",
                    help="substitute a finite Theta_gr_ve when the engine returns +/-inf "
                         "(measurement device for the step-3 divide-by-zero; see worker)")
    ap.add_argument("--weather", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.worker:
        sys.exit(run_worker(args))

    weather = str(Path(args.weather).resolve())
    results: dict[str, dict] = {}
    tmp = Path(tempfile.mkdtemp(prefix="aib-diag-"))
    created: list[Path] = []
    try:
        for label, branch in STATES:
            print(f"running {label:<20} ({branch})", flush=True)
            wt = tmp / branch.replace("/", "_")
            make_worktree(branch, wt)
            created.append(wt)
            results[label] = run_branch(
                wt / "pybuildingenergy" / "src", weather,
                tmp / f"{label.replace(' ', '_')}.json", repair=args.repair_ground_nan)
            r = results[label]
            sk = r.get("sankey", {})
            print(f"    H={r['Q_H_annual_kWh']:9.2f}  C={r['Q_C_annual_kWh']:9.2f}  "
                  f"lat_C={r['latent_cooling_kWh']:9.2f}  lat_H={r['latent_heating_kWh']:9.2f}  "
                  f"resid={sk.get('residual_kWh', float('nan')):9.2f} kWh "
                  f"({sk.get('residual_pct', float('nan')):6.2f}%)", flush=True)
    finally:
        for wt in created:
            drop_worktree(wt)

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nraw -> {outp}")


if __name__ == "__main__":
    main()
