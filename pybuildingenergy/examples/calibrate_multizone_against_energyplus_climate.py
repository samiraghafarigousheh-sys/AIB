#!/usr/bin/env python3
"""Calibrate multizone free-floating setup against EnergyPlus references.

The script runs a constrained parameter search for each climate and selects the
best non-envelope configuration by combining:
- summer indoor air temperature error (JJA)
- annual heating energy error
- summer heating energy error

Envelope properties (U-values, g-values, areas, capacities) are never changed.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pybuildingenergy.source.utils import ISO52016  # noqa: E402
from multizone_free_floating_example import (  # noqa: E402
    _resolve_summer_night_purge_config,
    apply_energyplus_infiltration_equivalence,
    building_object as BASE_BUILDING_OBJECT,
)


ZONE_MAP = {
    "Z1": "ZONEA_LIVING",
    "Z2": "ZONEB_BEDROOM",
}


@dataclass(frozen=True)
class ClimateCase:
    name: str
    epw_path: Path
    energyplus_csv: Path
    year: int = 2020


@dataclass(frozen=True)
class Candidate:
    name: str
    description: str
    apply: Callable[[dict], None]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrazione multiclima (Berlin/Madrid/Milan) del modello multizone "
            "contro reference EnergyPlus."
        )
    )
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "result_test" / "calibration_multiclimate"),
        help="Directory output principale.",
    )
    parser.add_argument(
        "--search-warmup-hours",
        type=int,
        default=168,
        help="Warmup per fase di ricerca candidati.",
    )
    parser.add_argument(
        "--final-warmup-hours",
        type=int,
        default=744,
        help="Warmup per run finale del candidato migliore.",
    )
    parser.add_argument(
        "--summer-months",
        nargs="*",
        type=int,
        default=[6, 7, 8],
        help="Mesi estivi usati per la calibrazione (default: 6 7 8).",
    )
    parser.add_argument(
        "--skip-compare-html",
        action="store_true",
        help="Salta il run dello script compare_energyplus_multizone_temperatures.py.",
    )
    parser.add_argument(
        "--limit-candidates",
        type=int,
        default=0,
        help="Se >0 limita il numero di candidati (debug rapido).",
    )
    return parser.parse_args()


def _parse_energyplus_datetime(
    series: pd.Series, *, year: int = 2020, shift_interval_end: bool = True
) -> pd.DatetimeIndex:
    raw = series.astype(str).str.strip()
    parts = raw.str.extract(
        r"(?P<month>\d{1,2})/(?P<day>\d{1,2})\s+(?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})"
    )
    if parts.isna().any().any():
        bad = raw[parts.isna().any(axis=1)].head(5).tolist()
        raise ValueError(
            "Formato Date/Time EnergyPlus non riconosciuto. "
            f"Esempi non parseabili: {bad}"
        )

    parts = parts.astype(int)
    day_roll = (parts["hour"] == 24).astype(int)
    parts.loc[day_roll == 1, "hour"] = 0

    ts = pd.to_datetime(
        {
            "year": year,
            "month": parts["month"],
            "day": parts["day"],
            "hour": parts["hour"],
            "minute": parts["minute"],
            "second": parts["second"],
        },
        errors="coerce",
    )
    ts = ts + pd.to_timedelta(day_roll, unit="D")
    if shift_interval_end:
        ts = ts - pd.Timedelta(hours=1)
    return pd.DatetimeIndex(ts)


def _infer_timestep_hours(index: pd.DatetimeIndex) -> float:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return 1.0
    dt_h = (
        index.to_series()
        .diff()
        .dt.total_seconds()
        .div(3600.0)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    dt_h = dt_h[dt_h > 0.0]
    if dt_h.empty:
        return 1.0
    return float(dt_h.median())


def _find_energyplus_col(columns: List[str], tokens: List[str]) -> str:
    for c in columns:
        cl = c.lower()
        if all(t.lower() in cl for t in tokens):
            return c
    raise KeyError(f"Colonna EnergyPlus non trovata per token={tokens}")


def load_energyplus_reference(case: ClimateCase) -> pd.DataFrame:
    if not case.energyplus_csv.exists():
        raise FileNotFoundError(f"EnergyPlus CSV non trovato: {case.energyplus_csv}")
    df = pd.read_csv(case.energyplus_csv)
    if "Date/Time" not in df.columns:
        raise KeyError(f"Colonna 'Date/Time' assente in {case.energyplus_csv}")
    ts = _parse_energyplus_datetime(df["Date/Time"], year=case.year, shift_interval_end=True)
    df = df.copy()
    df["timestamp"] = ts
    df = df.set_index("timestamp").sort_index()
    return df


def _set_night_purge(
    bui: dict,
    *,
    preset: str = "calibrated",
    enabled: bool | None = None,
    month_start: int | None = None,
    month_end: int | None = None,
    hour_start: int | None = None,
    hour_end: int | None = None,
    delta_t_min: float | None = None,
    boost_factor: float | None = None,
) -> None:
    cfg = _resolve_summer_night_purge_config(
        preset=preset,
        enabled=enabled,
        month_start=month_start,
        month_end=month_end,
        hour_start=hour_start,
        hour_end=hour_end,
        delta_t_min=delta_t_min,
        boost_factor=boost_factor,
    )
    for zone in bui.get("zones", []):
        zone["summer_night_purge"] = copy.deepcopy(cfg)


def _set_ventilation_occupancy(bui: dict, flow_rate_per_person: float) -> None:
    bp = bui.setdefault("building_parameters", {}).setdefault("ventilation", {})
    bp["ventilation_type"] = "occupancy"
    bp["flow_rate_per_person"] = float(flow_rate_per_person)
    for z in bui.get("zones", []):
        z["ventilation_type"] = "occupancy"
        z["flow_rate_per_person"] = float(flow_rate_per_person)


def _set_ventilation_eplus_infiltration(
    bui: dict,
    *,
    flow_per_ext_area: float,
    coef_a: float = 0.5,
    coef_b: float = 0.0,
    coef_c: float = 0.224,
    coef_d: float = 0.0,
    include_transparent_area: bool = True,
) -> None:
    bp = bui.setdefault("building_parameters", {}).setdefault("ventilation", {})
    bp["ventilation_type"] = "eplus_infiltration_ext_area"
    bp["infiltration_flow_per_exterior_area_m3_s_m2"] = float(flow_per_ext_area)
    bp["infiltration_coeff_constant"] = float(coef_a)
    bp["infiltration_coeff_temperature"] = float(coef_b)
    bp["infiltration_coeff_velocity"] = float(coef_c)
    bp["infiltration_coeff_velocity_squared"] = float(coef_d)
    bp["infiltration_include_transparent_area"] = bool(include_transparent_area)
    for z in bui.get("zones", []):
        z["ventilation_type"] = "eplus_infiltration_ext_area"
        z["infiltration_flow_per_exterior_area_m3_s_m2"] = float(flow_per_ext_area)
        z["infiltration_coeff_constant"] = float(coef_a)
        z["infiltration_coeff_temperature"] = float(coef_b)
        z["infiltration_coeff_velocity"] = float(coef_c)
        z["infiltration_coeff_velocity_squared"] = float(coef_d)
        z["infiltration_include_transparent_area"] = bool(include_transparent_area)


def _set_simulation_options(
    bui: dict,
    *,
    internal_convection_model: str | None = None,
    external_convection_model: str | None = None,
    external_radiation_model: str | None = None,
    sky_temperature_model: str | None = None,
) -> None:
    sim = bui.setdefault("building_parameters", {}).setdefault("simulation_options", {})
    if internal_convection_model is not None:
        sim["internal_convection_model"] = str(internal_convection_model)
    if external_convection_model is not None:
        sim["external_convection_model"] = str(external_convection_model)
    if external_radiation_model is not None:
        sim["external_radiation_model"] = str(external_radiation_model)
    if sky_temperature_model is not None:
        sim["sky_temperature_model"] = str(sky_temperature_model)


def _build_building_template() -> dict:
    bui = copy.deepcopy(BASE_BUILDING_OBJECT)
    # Keep envelope untouched; only align ventilation assumptions with EP setup.
    apply_energyplus_infiltration_equivalence(
        bui,
        summer_night_purge=_resolve_summer_night_purge_config(preset="calibrated"),
    )
    return bui


def build_candidates() -> List[Candidate]:
    cands: List[Candidate] = []
    cands.append(Candidate("baseline_calibrated", "Default calibrated setup", lambda b: None))
    cands.append(Candidate("purge_off", "Night purge OFF", lambda b: _set_night_purge(b, preset="off")))
    cands.append(
        Candidate(
            "purge_conservative",
            "Night purge conservative preset",
            lambda b: _set_night_purge(b, preset="conservative"),
        )
    )
    cands.append(Candidate("purge_balanced", "Night purge balanced preset", lambda b: _set_night_purge(b, preset="balanced")))
    cands.append(Candidate("purge_aggressive", "Night purge aggressive preset", lambda b: _set_night_purge(b, preset="aggressive")))
    cands.append(
        Candidate(
            "purge_custom_boost4p5",
            "Calibrated purge with lower boost",
            lambda b: _set_night_purge(
                b, preset="calibrated", month_start=6, month_end=8, hour_start=20, hour_end=9, delta_t_min=0.2, boost_factor=4.5
            ),
        )
    )
    cands.append(
        Candidate(
            "purge_custom_boost8p5",
            "Calibrated purge with higher boost",
            lambda b: _set_night_purge(
                b, preset="calibrated", month_start=6, month_end=8, hour_start=20, hour_end=9, delta_t_min=0.1, boost_factor=8.5
            ),
        )
    )
    cands.append(
        Candidate(
            "models_iso_table",
            "ISO-like exchange coefficients (table/table)",
            lambda b: _set_simulation_options(
                b,
                internal_convection_model="table",
                external_convection_model="table",
                external_radiation_model="table",
                sky_temperature_model="berdahl_fromberg",
            ),
        )
    )
    cands.append(
        Candidate(
            "models_doe2_dynamic",
            "DOE2 + dynamic radiation",
            lambda b: _set_simulation_options(
                b,
                internal_convection_model="tarp",
                external_convection_model="doe2",
                external_radiation_model="dynamic",
                sky_temperature_model="epw_ir",
            ),
        )
    )
    cands.append(
        Candidate(
            "models_mowitt_dynamic_swinbank",
            "MoWiTT + dynamic radiation + Swinbank sky",
            lambda b: _set_simulation_options(
                b,
                internal_convection_model="tarp",
                external_convection_model="mowitt",
                external_radiation_model="dynamic",
                sky_temperature_model="swinbank",
            ),
        )
    )
    cands.append(
        Candidate(
            "occupancy_flow_0p3",
            "Occupancy ventilation 0.3 l/s/m2",
            lambda b: _set_ventilation_occupancy(b, flow_rate_per_person=0.3),
        )
    )
    cands.append(
        Candidate(
            "occupancy_flow_0p8",
            "Occupancy ventilation 0.8 l/s/m2",
            lambda b: _set_ventilation_occupancy(b, flow_rate_per_person=0.8),
        )
    )
    cands.append(
        Candidate(
            "eplus_inf_base",
            "E+ infiltration ext-area baseline coefficients",
            lambda b: _set_ventilation_eplus_infiltration(
                b, flow_per_ext_area=3.0e-4, coef_a=0.5, coef_b=0.0, coef_c=0.224, coef_d=0.0
            ),
        )
    )
    cands.append(
        Candidate(
            "eplus_inf_low",
            "E+ infiltration ext-area low flow/wind",
            lambda b: _set_ventilation_eplus_infiltration(
                b, flow_per_ext_area=2.0e-4, coef_a=0.5, coef_b=0.0, coef_c=0.15, coef_d=0.0
            ),
        )
    )
    cands.append(
        Candidate(
            "eplus_inf_high",
            "E+ infiltration ext-area high flow/wind",
            lambda b: _set_ventilation_eplus_infiltration(
                b, flow_per_ext_area=4.0e-4, coef_a=0.5, coef_b=0.0, coef_c=0.30, coef_d=0.0
            ),
        )
    )
    cands.append(
        Candidate(
            "eplus_inf_base_purge_aggressive",
            "E+ infiltration + aggressive purge",
            lambda b: (
                _set_ventilation_eplus_infiltration(
                    b, flow_per_ext_area=3.0e-4, coef_a=0.5, coef_b=0.0, coef_c=0.224, coef_d=0.0
                ),
                _set_night_purge(b, preset="aggressive"),
            ),
        )
    )
    return cands


def _compute_energyplus_energy(ep_df: pd.DataFrame, summer_months: List[int]) -> Dict[str, float]:
    h_col = _find_energyplus_col(
        list(ep_df.columns),
        ["heating:energytransfer", "[j]", "(hourly)"],
    )
    c_col = _find_energyplus_col(
        list(ep_df.columns),
        ["cooling:energytransfer", "[j]", "(hourly)"],
    )
    e_heat_j = float(pd.to_numeric(ep_df[h_col], errors="coerce").fillna(0.0).sum())
    e_cool_j = float(pd.to_numeric(ep_df[c_col], errors="coerce").fillna(0.0).sum())
    summer_mask = ep_df.index.month.isin(summer_months)
    e_heat_j_summer = float(pd.to_numeric(ep_df.loc[summer_mask, h_col], errors="coerce").fillna(0.0).sum())
    e_cool_j_summer = float(pd.to_numeric(ep_df.loc[summer_mask, c_col], errors="coerce").fillna(0.0).sum())
    return {
        "ep_heating_kWh_annual": e_heat_j / 3.6e6,
        "ep_cooling_kWh_annual": e_cool_j / 3.6e6,
        "ep_heating_kWh_summer": e_heat_j_summer / 3.6e6,
        "ep_cooling_kWh_summer": e_cool_j_summer / 3.6e6,
    }


def _evaluate_run_against_energyplus(
    hourly_mz: pd.DataFrame,
    ep_df: pd.DataFrame,
    summer_months: List[int],
) -> Dict[str, float]:
    hourly = hourly_mz.copy()
    if not isinstance(hourly.index, pd.DatetimeIndex):
        hourly.index = pd.to_datetime(hourly.index, errors="coerce")
    hourly = hourly.loc[hourly.index.notna()].sort_index()
    common_idx = hourly.index.intersection(ep_df.index)
    if len(common_idx) == 0:
        raise ValueError("Nessun timestamp comune tra multizone ed EnergyPlus.")

    hourly = hourly.loc[common_idx]
    ep = ep_df.loc[common_idx]

    temp_deltas_annual: List[np.ndarray] = []
    temp_deltas_summer: List[np.ndarray] = []
    zone_summer_mae: Dict[str, float] = {}

    summer_mask = common_idx.month.isin(summer_months)

    for mz_zone, ep_zone in ZONE_MAP.items():
        mz_col = f"T_air_{mz_zone}"
        ep_col = _find_energyplus_col(
            list(ep.columns),
            [f"{ep_zone.lower()}:zone mean air temperature", "[c]", "(hourly)"],
        )
        if mz_col not in hourly.columns:
            raise KeyError(f"Colonna assente nel multizone: {mz_col}")
        mz_t = pd.to_numeric(hourly[mz_col], errors="coerce")
        ep_t = pd.to_numeric(ep[ep_col], errors="coerce")
        delta = (mz_t - ep_t).to_numpy(dtype=float)
        delta = delta[np.isfinite(delta)]
        if delta.size > 0:
            temp_deltas_annual.append(delta)
        delta_summer = (mz_t[summer_mask] - ep_t[summer_mask]).to_numpy(dtype=float)
        delta_summer = delta_summer[np.isfinite(delta_summer)]
        if delta_summer.size > 0:
            temp_deltas_summer.append(delta_summer)
            zone_summer_mae[f"summer_mae_{mz_zone}_C"] = float(np.mean(np.abs(delta_summer)))
        else:
            zone_summer_mae[f"summer_mae_{mz_zone}_C"] = float("nan")

    if not temp_deltas_annual:
        raise ValueError("Impossibile calcolare metriche temperatura annuali.")
    if not temp_deltas_summer:
        raise ValueError("Impossibile calcolare metriche temperatura estive.")

    d_ann = np.concatenate(temp_deltas_annual)
    d_sum = np.concatenate(temp_deltas_summer)

    q_cols = [c for c in hourly.columns if c.startswith("Q_HVAC_")]
    if not q_cols:
        raise KeyError("Colonne Q_HVAC_* non trovate nel multizone.")
    q = hourly[q_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    p_heat_w = q.clip(lower=0.0).sum(axis=1)
    p_cool_w = (-q.clip(upper=0.0)).sum(axis=1)
    dt_h = _infer_timestep_hours(pd.DatetimeIndex(hourly.index))
    e_heat_mz_annual = float(p_heat_w.sum() * dt_h / 1000.0)
    e_cool_mz_annual = float(p_cool_w.sum() * dt_h / 1000.0)
    e_heat_mz_summer = float(p_heat_w[summer_mask].sum() * dt_h / 1000.0)
    e_cool_mz_summer = float(p_cool_w[summer_mask].sum() * dt_h / 1000.0)

    ep_energy = _compute_energyplus_energy(ep, summer_months=summer_months)
    ep_heat_annual = float(ep_energy["ep_heating_kWh_annual"])
    ep_heat_summer = float(ep_energy["ep_heating_kWh_summer"])

    heat_rel_pct = (
        float("nan")
        if abs(ep_heat_annual) < 1e-9
        else 100.0 * abs(e_heat_mz_annual - ep_heat_annual) / abs(ep_heat_annual)
    )

    out = {
        "n_common_hours": float(len(common_idx)),
        "annual_air_mae_C": float(np.mean(np.abs(d_ann))),
        "annual_air_rmse_C": float(np.sqrt(np.mean(np.square(d_ann)))),
        "annual_air_bias_C": float(np.mean(d_ann)),
        "summer_air_mae_C": float(np.mean(np.abs(d_sum))),
        "summer_air_rmse_C": float(np.sqrt(np.mean(np.square(d_sum)))),
        "summer_air_bias_C": float(np.mean(d_sum)),
        "mz_heating_kWh_annual": e_heat_mz_annual,
        "ep_heating_kWh_annual": ep_heat_annual,
        "mz_heating_kWh_summer": e_heat_mz_summer,
        "ep_heating_kWh_summer": ep_heat_summer,
        "mz_cooling_kWh_annual": e_cool_mz_annual,
        "ep_cooling_kWh_annual": float(ep_energy["ep_cooling_kWh_annual"]),
        "mz_cooling_kWh_summer": e_cool_mz_summer,
        "ep_cooling_kWh_summer": float(ep_energy["ep_cooling_kWh_summer"]),
        "annual_heating_rel_err_pct": float(heat_rel_pct),
        "summer_heating_abs_err_kWh": float(abs(e_heat_mz_summer - ep_heat_summer)),
    }
    out.update(zone_summer_mae)

    # Composite score: lower is better.
    # Prioritize summer temperatures, then annual heating, then summer heating.
    out["score"] = (
        float(out["summer_air_mae_C"])
        + 0.50 * abs(float(out["summer_air_bias_C"]))
        + 0.05 * float(out["annual_heating_rel_err_pct"])
        + 0.01 * float(out["summer_heating_abs_err_kWh"])
    )
    return out


def _build_candidate_building(candidate: Candidate) -> dict:
    bui = _build_building_template()
    candidate.apply(bui)
    return bui


def run_one_candidate(
    candidate: Candidate,
    case: ClimateCase,
    ep_df: pd.DataFrame,
    summer_months: List[int],
    warmup_hours: int,
) -> Dict[str, float | str]:
    bui = _build_candidate_building(candidate)
    t0 = time.perf_counter()
    hourly, _annual = ISO52016.Temperature_and_Energy_needs_calculation_multizone(
        building_object=bui,
        path_weather_file=str(case.epw_path),
        weather_source="epw",
        include_solar=True,
        warmup_hours=int(warmup_hours),
        hvac_control_variable="air",
    )
    elapsed = float(time.perf_counter() - t0)
    metrics = _evaluate_run_against_energyplus(
        hourly_mz=hourly,
        ep_df=ep_df,
        summer_months=summer_months,
    )
    row: Dict[str, float | str] = {
        "candidate": candidate.name,
        "description": candidate.description,
        "runtime_s": elapsed,
        "status": "ok",
    }
    row.update(metrics)
    return row


def run_final_best_case(
    climate_out_dir: Path,
    case: ClimateCase,
    best_candidate: Candidate,
    final_warmup_hours: int,
    summer_months: List[int],
    skip_compare_html: bool,
) -> Dict[str, float | str]:
    bui = _build_candidate_building(best_candidate)
    t0 = time.perf_counter()
    hourly, annual = ISO52016.Temperature_and_Energy_needs_calculation_multizone(
        building_object=bui,
        path_weather_file=str(case.epw_path),
        weather_source="epw",
        include_solar=True,
        warmup_hours=int(final_warmup_hours),
        hvac_control_variable="air",
    )
    elapsed = float(time.perf_counter() - t0)

    climate_out_dir.mkdir(parents=True, exist_ok=True)
    hourly_path = climate_out_dir / "multizone_v1_hourly.csv"
    annual_path = climate_out_dir / "multizone_v1_annual.csv"
    best_json = climate_out_dir / "best_candidate.json"
    timings_csv = climate_out_dir / "multizone_v1_timings_seconds.csv"

    hourly.to_csv(hourly_path)
    annual.to_csv(annual_path, index=False)
    pd.DataFrame(
        [{"fully_integrated_v1_s": elapsed, "total_run_s": elapsed}]
    ).to_csv(timings_csv, index=False)
    best_json.write_text(
        json.dumps(
            {
                "climate": case.name,
                "candidate": best_candidate.name,
                "description": best_candidate.description,
                "epw_path": str(case.epw_path),
                "energyplus_csv": str(case.energyplus_csv),
                "final_warmup_hours": int(final_warmup_hours),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    ep_df = load_energyplus_reference(case)
    metrics = _evaluate_run_against_energyplus(
        hourly_mz=hourly,
        ep_df=ep_df,
        summer_months=summer_months,
    )

    if not skip_compare_html:
        compare_script = SCRIPT_DIR / "compare_energyplus_multizone_temperatures.py"
        out_prefix = f"energyplus_vs_multizone_temperatures_{case.name}"
        cmd = [
            sys.executable,
            str(compare_script),
            "--energyplus-csv",
            str(case.energyplus_csv),
            "--multizone-csv",
            str(hourly_path),
            "--out-dir",
            str(climate_out_dir),
            "--out-prefix",
            out_prefix,
            "--zone-map",
            "Z1=ZONEA_LIVING",
            "Z2=ZONEB_BEDROOM",
        ]
        subprocess.run(cmd, check=True)

    out: Dict[str, float | str] = {
        "climate": case.name,
        "best_candidate": best_candidate.name,
        "final_runtime_s": elapsed,
        "hourly_csv": str(hourly_path),
        "annual_csv": str(annual_path),
    }
    out.update(metrics)
    return out


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    summer_months = [int(m) for m in args.summer_months]

    cases = [
        ClimateCase(
            name="milan",
            epw_path=(SCRIPT_DIR / "2020_Milan.epw").resolve(),
            energyplus_csv=(SCRIPT_DIR / "two_zone_ideal_24_2_fixedout.csv").resolve(),
        ),
        ClimateCase(
            name="berlin",
            epw_path=(SCRIPT_DIR / "2020_Berlin.epw").resolve(),
            energyplus_csv=(SCRIPT_DIR / "two_zone_ideal_24_2_fixedout_Berlin.csv").resolve(),
        ),
        ClimateCase(
            name="madrid",
            epw_path=(SCRIPT_DIR / "2020_Madrid.epw").resolve(),
            energyplus_csv=(SCRIPT_DIR / "two_zone_ideal_24_2_fixedout_Madrid.csv").resolve(),
        ),
    ]

    for case in cases:
        if not case.epw_path.exists():
            raise FileNotFoundError(f"EPW non trovato ({case.name}): {case.epw_path}")
        if not case.energyplus_csv.exists():
            raise FileNotFoundError(f"CSV EnergyPlus non trovato ({case.name}): {case.energyplus_csv}")

    candidates = build_candidates()
    if int(args.limit_candidates) > 0:
        candidates = candidates[: int(args.limit_candidates)]

    print(f"[info] Candidates: {len(candidates)}")
    print(f"[info] Search warmup hours: {int(args.search_warmup_hours)}")
    print(f"[info] Final warmup hours: {int(args.final_warmup_hours)}")
    print(f"[info] Summer months: {summer_months}")
    print(f"[info] Output dir: {out_dir}")

    global_rows: List[Dict[str, float | str]] = []
    final_rows: List[Dict[str, float | str]] = []

    for case in cases:
        print("")
        print(f"=== Climate: {case.name} ===")
        ep_df = load_energyplus_reference(case)
        climate_dir = out_dir / case.name
        climate_dir.mkdir(parents=True, exist_ok=True)

        rows: List[Dict[str, float | str]] = []
        for i, cand in enumerate(candidates, start=1):
            print(f"[{case.name}] [{i:02d}/{len(candidates):02d}] {cand.name} ...", flush=True)
            try:
                row = run_one_candidate(
                    candidate=cand,
                    case=case,
                    ep_df=ep_df,
                    summer_months=summer_months,
                    warmup_hours=int(args.search_warmup_hours),
                )
                row["climate"] = case.name
                rows.append(row)
                print(
                    f"  ok | score={float(row['score']):.4f} | "
                    f"summer_mae={float(row['summer_air_mae_C']):.3f} C | "
                    f"heat_err={float(row['annual_heating_rel_err_pct']):.2f}%",
                    flush=True,
                )
            except Exception as exc:
                rows.append(
                    {
                        "climate": case.name,
                        "candidate": cand.name,
                        "description": cand.description,
                        "status": f"error: {exc}",
                    }
                )
                print(f"  failed: {exc}", flush=True)

        climate_runs = pd.DataFrame(rows)
        runs_csv = climate_dir / "candidate_runs.csv"
        climate_runs.to_csv(runs_csv, index=False)
        print(f"[{case.name}] saved candidate runs: {runs_csv}")

        ok = climate_runs.loc[climate_runs["status"] == "ok"].copy()
        if ok.empty:
            print(f"[{case.name}] no successful candidates, skipping final run.")
            continue

        ok = ok.sort_values("score", ascending=True).reset_index(drop=True)
        ranking_csv = climate_dir / "candidate_ranking.csv"
        ok.to_csv(ranking_csv, index=False)
        print(f"[{case.name}] saved ranking: {ranking_csv}")

        best_name = str(ok.iloc[0]["candidate"])
        best = next(c for c in candidates if c.name == best_name)
        print(f"[{case.name}] best candidate: {best.name}")

        final_dir = climate_dir / "best_final"
        final_metrics = run_final_best_case(
            climate_out_dir=final_dir,
            case=case,
            best_candidate=best,
            final_warmup_hours=int(args.final_warmup_hours),
            summer_months=summer_months,
            skip_compare_html=bool(args.skip_compare_html),
        )
        final_rows.append(final_metrics)

        best_top3 = ok.head(3).copy()
        best_top3_path = climate_dir / "top3_candidates.csv"
        best_top3.to_csv(best_top3_path, index=False)
        print(f"[{case.name}] saved top3: {best_top3_path}")

        global_rows.extend(rows)

    if global_rows:
        pd.DataFrame(global_rows).to_csv(out_dir / "all_candidate_runs.csv", index=False)
    if final_rows:
        final_df = pd.DataFrame(final_rows)
        final_csv = out_dir / "final_best_by_climate.csv"
        final_df.to_csv(final_csv, index=False)
        print("")
        print("=== Final best by climate ===")
        for _, r in final_df.iterrows():
            print(
                f"{r['climate']}: {r['best_candidate']} | "
                f"summer_mae={float(r['summer_air_mae_C']):.3f} C | "
                f"annual_heat_err={float(r['annual_heating_rel_err_pct']):.2f}%"
            )
        print(f"Saved final summary: {final_csv}")


if __name__ == "__main__":
    main()

