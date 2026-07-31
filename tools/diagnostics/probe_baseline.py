"""
Item 1 instrumentation probe.

Runs ONE engine (given by --src) against ONE building dictionary (given by
--bui-dir) and dumps the *effective* runtime inputs, not the declared ones:

  1. resolved weather file actually opened + HDD18/CDD18/GHI of the loaded series
  2. setpoint arrays actually applied (min/max/unique)
  3. internal-gain hourly series: sum, hour-of-day distribution, sha256 of the array
  4. solar-gain hourly series: sum, sha256
  5. surface classification actually used by the core (ADJ/GR/EXT counts)

argv: --src <engine/src> --bui-dir <dir with apt305_building.py> --epw <path> --out <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha(arr) -> str:
    import numpy as np
    a = np.asarray(arr, dtype=float)
    # round to 1e-9 so float noise in printing cannot change the hash meaning
    return hashlib.sha256(np.round(a, 9).tobytes()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--bui-dir", required=True)
    ap.add_argument("--epw", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    sys.path.insert(0, str(Path(a.src).resolve()))
    sys.path.insert(0, str(Path(a.bui_dir).resolve()))

    import numpy as np
    import pandas as pd

    from apt305_building import build_bui
    from pybuildingenergy.source import utils as U
    from pybuildingenergy.source.utils import ISO52016, ISO52010
    from pybuildingenergy.source.check_input import sanitize_and_validate_BUI

    out: dict = {}

    # --- 1. weather actually opened -----------------------------------------
    opened = {}
    orig_epw = ISO52010.get_tmy_data_epw.__func__

    def spy_epw(cls, path_weather_file):
        try:
            opened["path"] = str(Path(str(path_weather_file)).resolve())
        except Exception:
            opened["path"] = repr(path_weather_file)[:200]
        res = orig_epw(cls, path_weather_file)
        wd = res.weather_data
        opened["n_rows"] = int(len(wd))
        opened["columns"] = list(wd.columns)[:12]
        t = pd.to_numeric(wd["T2m"], errors="coerce").astype(float)
        g = pd.to_numeric(wd["G(h)"], errors="coerce").astype(float) if "G(h)" in wd.columns else None
        # hourly series -> degree-days by dividing the hourly deficit/excess by 24
        opened["HDD18_C_d"] = float(np.clip(18.0 - t.values, 0, None).sum() / 24.0)
        opened["CDD18_C_d"] = float(np.clip(t.values - 18.0, 0, None).sum() / 24.0)
        opened["T2m_mean_C"] = float(t.mean())
        opened["T2m_min_C"] = float(t.min())
        opened["T2m_max_C"] = float(t.max())
        opened["T2m_sha256"] = sha(t.values)
        if g is not None:
            opened["GHI_kWh_m2_yr"] = float(g.sum() / 1000.0)
            opened["GHI_sha256"] = sha(g.values)
        opened["utc_offset"] = getattr(res, "utc_offset", None)
        opened["latitude"] = float(getattr(res, "latitude", float("nan")))
        opened["longitude"] = float(getattr(res, "longitude", float("nan")))
        return res

    ISO52010.get_tmy_data_epw = classmethod(spy_epw)

    # --- building dictionary -------------------------------------------------
    raw = build_bui()
    area = float(raw["building"]["net_floor_area"])
    out["net_floor_area_m2"] = area
    out["surface_types_declared"] = [
        {"name": s.get("name"), "type": s.get("type"),
         "svf": s.get("sky_view_factor"), "adj": s.get("name_adj_zone"),
         "area": s.get("area")}
        for s in raw["building_surface"]
    ]
    out["adjacent_zones_declared"] = [
        {"name": z.get("name"), "conditioned": z.get("conditioned"),
         "setpoint": z.get("setpoint")}
        for z in raw.get("adjacent_zones", [])
    ]

    building, _issues = sanitize_and_validate_BUI(raw, fix=True)

    # --- 2. setpoints actually applied --------------------------------------
    sp = building["building_parameters"]["temperature_setpoints"]
    out["setpoints_declared"] = {k: v for k, v in sp.items() if k != "units"}

    # --- ground contact area the engine will use ----------------------------
    try:
        out["ground_contact_area_m2"] = float(U._ground_contact_area(building))
    except Exception as exc:
        out["ground_contact_area_m2"] = f"n/a ({type(exc).__name__})"

    # --- run -----------------------------------------------------------------
    res = ISO52016.Temperature_and_Energy_needs_calculation(
        building, weather_source="epw", path_weather_file=a.epw)
    hourly = res[0]
    annual = res[1]

    out["weather_effective"] = opened

    def ann(k):
        if k not in annual.columns:
            return float("nan")
        return float(pd.to_numeric(annual[k], errors="coerce").iloc[0])

    for k in ("Q_H_annual_kWh", "Q_C_annual_kWh", "Q_internal_gains_kWh",
              "Q_solar_gains_kWh", "Q_ground_loss_kWh", "Q_ground_gain_kWh",
              "Q_ve_loss_kWh", "Q_ve_gain_kWh", "Q_latent_annual_kWh",
              "Q_tr_opaque_loss_kWh", "Q_tr_opaque_gain_kWh",
              "Q_tr_window_loss_kWh", "Q_tr_window_gain_kWh",
              "Q_tb_loss_kWh", "Q_tb_gain_kWh",
              "Q_storage_charge_kWh", "Q_storage_discharge_kWh"):
        out[k] = ann(k)

    hcols = list(hourly.columns)
    out["hourly_columns"] = hcols

    # --- 3. internal-gain temporal profile ----------------------------------
    if "Q_internal_gains" in hourly.columns:
        gi = pd.to_numeric(hourly["Q_internal_gains"], errors="coerce").fillna(0.0).values
        out["Phi_int"] = {
            "n": int(len(gi)),
            "sum_kWh": float(gi.sum() / 1000.0),
            "mean_W": float(gi.mean()),
            "min_W": float(gi.min()),
            "max_W": float(gi.max()),
            "sha256": sha(gi),
            # hour-of-day mean, position 0 == first hour of the array
            "hour_of_day_mean_W": [float(gi[h::24].mean()) for h in range(24)],
            "first_48": [float(x) for x in gi[:48]],
        }

    # --- 4. solar temporal profile ------------------------------------------
    if "Q_solar_gains" in hourly.columns:
        gs = pd.to_numeric(hourly["Q_solar_gains"], errors="coerce").fillna(0.0).values
        out["Phi_sol"] = {
            "n": int(len(gs)),
            "sum_kWh": float(gs.sum() / 1000.0),
            "max_W": float(gs.max()),
            "sha256": sha(gs),
            "hour_of_day_mean_W": [float(gs[h::24].mean()) for h in range(24)],
            "argmax_hour_of_day": int(int(np.argmax(gs)) % 24),
        }

    # --- outdoor temperature as seen inside the solver ----------------------
    for cand in ("T_out", "T_ext", "T2m", "theta_e", "T_outdoor"):
        if cand in hourly.columns:
            te = pd.to_numeric(hourly[cand], errors="coerce").fillna(0.0).values
            out["T_ext_in_solver"] = {
                "column": cand, "sha256": sha(te),
                "mean_C": float(te.mean()),
                "argmin_hour_of_day": int(int(np.argmin(te)) % 24),
                "hour_of_day_mean_C": [float(te[h::24].mean()) for h in range(24)],
            }
            break

    # --- applied setpoint arrays (hourly) -----------------------------------
    for cand in ("T_set_H", "theta_set_H", "T_heating_setpoint", "setpoint_H"):
        if cand in hourly.columns:
            v = pd.to_numeric(hourly[cand], errors="coerce").dropna()
            out["setpoint_H_applied"] = {
                "column": cand, "min": float(v.min()), "max": float(v.max()),
                "unique": sorted({round(float(x), 3) for x in v.unique()})[:10]}
            break
    for cand in ("T_set_C", "theta_set_C", "T_cooling_setpoint", "setpoint_C"):
        if cand in hourly.columns:
            v = pd.to_numeric(hourly[cand], errors="coerce").dropna()
            out["setpoint_C_applied"] = {
                "column": cand, "min": float(v.min()), "max": float(v.max()),
                "unique": sorted({round(float(x), 3) for x in v.unique()})[:10]}
            break

    # --- 5. surface classification the CORE actually resolved ---------------
    resolved = []
    for srf in building["building_surface"]:
        resolved.append({"name": srf.get("name"), "declared_type": srf.get("type"),
                         "svf": srf.get("sky_view_factor"),
                         "ISO52016_type_string": srf.get("ISO52016_type_string"),
                         "area": float(srf.get("area", 0.0))})
    out["surface_classification_resolved"] = resolved
    agg = {}
    for r in resolved:
        agg[r["ISO52016_type_string"]] = agg.get(r["ISO52016_type_string"], 0.0) + r["area"]
    out["area_by_ISO52016_type_m2"] = agg

    Path(a.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"OK  {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
