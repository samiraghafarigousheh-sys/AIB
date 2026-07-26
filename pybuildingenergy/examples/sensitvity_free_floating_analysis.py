#!/usr/bin/env python3
"""Sensitivity analysis for multizone free-floating summer temperatures.

Runs one-at-a-time parameter perturbations and ranks impact on summer indoor
temperatures (JJA) for the multizone free-floating model.
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Sequence

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
    building_object as BASE_BUILDING_OBJECT,
    apply_summer_night_purge_to_zones,
    _auto_infiltration_coeff_constant_from_epw,
    _auto_purge_preset_from_latitude,
    _epw_latitude_abs,
    _normalize_idf_gross_opaque_areas,
    _resolve_summer_night_purge_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sensitivity analysis on free-floating summer temperatures "
            "(multizone model)."
        )
    )
    parser.add_argument(
        "--weather-path",
        default=str(SCRIPT_DIR / "2020_Athens.epw"),
        help="Path to EPW weather file.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "result_test"),
        help="Output directory.",
    )
    parser.add_argument(
        "--night-purge-preset",
        default="aggressive",
        help="Night purge preset applied to baseline before perturbations.",
    )
    parser.add_argument(
        "--warmup-hours",
        type=int,
        default=168,
        help="Warmup hours for simulation.",
    )
    parser.add_argument(
        "--months",
        nargs="*",
        type=int,
        default=[6, 7, 8],
        help="Months used for summer metrics (default: 6 7 8).",
    )
    parser.add_argument(
        "--temp-threshold-c",
        type=float,
        default=26.0,
        help="Temperature threshold for degree-hours metric.",
    )
    return parser.parse_args()


def set_free_floating_no_hvac(bui: dict) -> None:
    bp = bui.setdefault("building_parameters", {})
    caps = bp.setdefault("system_capacities", {})
    caps["heating_capacity"] = 0.0
    caps["cooling_capacity"] = 0.0
    for z in bui.get("zones", []):
        z["heating_capacity"] = 0.0
        z["cooling_capacity"] = 0.0


def get_zone_names(bui: dict) -> List[str]:
    zones = bui.get("zones", [])
    if not zones:
        return ["main"]
    return [str(z.get("name", "main")) for z in zones]


def _safe_scale(value: float, factor: float, vmin: float | None = None, vmax: float | None = None) -> float:
    out = float(value) * float(factor)
    if vmin is not None:
        out = max(float(vmin), out)
    if vmax is not None:
        out = min(float(vmax), out)
    return float(out)


def mutate_infiltration_flow_ext_area(bui: dict, factor: float) -> None:
    bp = bui.setdefault("building_parameters", {})
    vent = bp.setdefault("ventilation", {})
    base = float(vent.get("infiltration_flow_per_exterior_area_m3_s_m2", 3.0e-4))
    vent["infiltration_flow_per_exterior_area_m3_s_m2"] = _safe_scale(base, factor, vmin=0.0)
    for z in bui.get("zones", []):
        zbase = float(z.get("infiltration_flow_per_exterior_area_m3_s_m2", base))
        z["infiltration_flow_per_exterior_area_m3_s_m2"] = _safe_scale(zbase, factor, vmin=0.0)


def mutate_infiltration_velocity_coeff(bui: dict, factor: float) -> None:
    bp = bui.setdefault("building_parameters", {})
    vent = bp.setdefault("ventilation", {})
    base = float(vent.get("infiltration_coeff_velocity", 0.224))
    vent["infiltration_coeff_velocity"] = _safe_scale(base, factor, vmin=0.0)
    for z in bui.get("zones", []):
        zbase = float(z.get("infiltration_coeff_velocity", base))
        z["infiltration_coeff_velocity"] = _safe_scale(zbase, factor, vmin=0.0)


def mutate_infiltration_constant_coeff(bui: dict, factor: float) -> None:
    bp = bui.setdefault("building_parameters", {})
    vent = bp.setdefault("ventilation", {})
    base = float(vent.get("infiltration_coeff_constant", 0.0))
    vent["infiltration_coeff_constant"] = _safe_scale(base, factor, vmin=0.0)
    vent["infiltration_coeff_constant_auto_by_latitude"] = False
    for z in bui.get("zones", []):
        zbase = float(z.get("infiltration_coeff_constant", base))
        z["infiltration_coeff_constant"] = _safe_scale(zbase, factor, vmin=0.0)


def mutate_window_g_value(bui: dict, factor: float) -> None:
    for surf in bui.get("building_surface", []):
        if str(surf.get("type", "")).lower() != "transparent":
            continue
        g = float(surf.get("g_value", 0.6))
        surf["g_value"] = _safe_scale(g, factor, vmin=0.05, vmax=0.95)


def mutate_internal_gains(bui: dict, factor: float) -> None:
    for z in bui.get("zones", []):
        for gain in z.get("internal_gains", []):
            if gain.get("w_per_person") is not None:
                gain["w_per_person"] = _safe_scale(float(gain["w_per_person"]), factor, vmin=0.0)
            if gain.get("full_load") is not None:
                gain["full_load"] = _safe_scale(float(gain["full_load"]), factor, vmin=0.0)


def mutate_night_purge_boost_factor(bui: dict, factor: float) -> None:
    for z in bui.get("zones", []):
        purge = z.get("summer_night_purge")
        if isinstance(purge, dict):
            base = float(purge.get("boost_factor", 1.0))
            purge["boost_factor"] = _safe_scale(base, factor, vmin=1.0)


def mutate_night_purge_delta_t_min(bui: dict, factor: float) -> None:
    for z in bui.get("zones", []):
        purge = z.get("summer_night_purge")
        if isinstance(purge, dict):
            base = float(purge.get("delta_t_min", 0.5))
            purge["delta_t_min"] = _safe_scale(base, factor, vmin=0.0)


def set_night_purge_enabled(bui: dict, enabled: bool) -> None:
    for z in bui.get("zones", []):
        purge = z.get("summer_night_purge")
        if isinstance(purge, dict):
            purge["enabled"] = bool(enabled)
    purge_building = bui.setdefault("building_parameters", {}).get("summer_night_purge")
    if isinstance(purge_building, dict):
        purge_building["enabled"] = bool(enabled)


def set_external_convection_model(bui: dict, model: str) -> None:
    sim_opt = bui.setdefault("building_parameters", {}).setdefault("simulation_options", {})
    sim_opt["external_convection_model"] = str(model)


def set_external_radiation_model(bui: dict, model: str) -> None:
    sim_opt = bui.setdefault("building_parameters", {}).setdefault("simulation_options", {})
    sim_opt["external_radiation_model"] = str(model)


def set_sky_temperature_model(bui: dict, model: str) -> None:
    sim_opt = bui.setdefault("building_parameters", {}).setdefault("simulation_options", {})
    sim_opt["sky_temperature_model"] = str(model)


def set_external_emissivity_default(bui: dict, value: float) -> None:
    sim_opt = bui.setdefault("building_parameters", {}).setdefault("simulation_options", {})
    sim_opt["external_emissivity_default"] = float(np.clip(value, 0.01, 1.0))


def compute_summer_metrics(
    hourly_df: pd.DataFrame,
    zone_names: Sequence[str],
    months: Sequence[int],
    threshold_c: float,
) -> Dict[str, float]:
    if hourly_df.empty:
        raise ValueError("Hourly DataFrame is empty.")
    df = hourly_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors="coerce")
    df = df.loc[df.index.notna()].sort_index()
    df = df.loc[df.index.month.isin(list(months))]
    if df.empty:
        raise ValueError("No summer rows found for requested months.")

    dt_h = 1.0
    if isinstance(df.index, pd.DatetimeIndex) and len(df.index) >= 2:
        diff_h = (
            df.index.to_series().diff().dt.total_seconds().div(3600.0).dropna()
        )
        diff_h = diff_h[(diff_h > 0.0) & np.isfinite(diff_h)]
        if not diff_h.empty:
            dt_h = float(diff_h.median())

    temp_cols = [f"T_air_{z}" for z in zone_names if f"T_air_{z}" in df.columns]
    if not temp_cols:
        raise ValueError("No T_air_<zone> columns found.")

    tvals = df[temp_cols].apply(pd.to_numeric, errors="coerce")
    flat = tvals.to_numpy(dtype=float).ravel()
    flat = flat[np.isfinite(flat)]
    if flat.size == 0:
        raise ValueError("No valid temperature values.")

    over = np.maximum(0.0, tvals.to_numpy(dtype=float) - float(threshold_c))
    over = np.where(np.isfinite(over), over, 0.0)
    deg_h = float(over.sum() * dt_h)

    metrics: Dict[str, float] = {
        "summer_mean_Tair_C": float(np.mean(flat)),
        "summer_p95_Tair_C": float(np.percentile(flat, 95.0)),
        "summer_max_Tair_C": float(np.max(flat)),
        "summer_over_threshold_degC_h": deg_h,
        "summer_n_hours": float(len(df)),
    }

    for z in zone_names:
        c = f"T_air_{z}"
        if c in df.columns:
            s = pd.to_numeric(df[c], errors="coerce")
            s = s[np.isfinite(s)]
            if not s.empty:
                metrics[f"{z}_mean_Tair_C"] = float(s.mean())
                metrics[f"{z}_max_Tair_C"] = float(s.max())

    return metrics


def build_cases() -> List[Dict[str, object]]:
    cases: List[Dict[str, object]] = []
    # Continuous factors (low/high)
    cont_specs = [
        ("infiltration_flow_ext_area", "0.5x", lambda b: mutate_infiltration_flow_ext_area(b, 0.5)),
        ("infiltration_flow_ext_area", "1.5x", lambda b: mutate_infiltration_flow_ext_area(b, 1.5)),
        ("infiltration_constant_coeff", "0.0x", lambda b: mutate_infiltration_constant_coeff(b, 0.0)),
        ("infiltration_constant_coeff", "1.5x", lambda b: mutate_infiltration_constant_coeff(b, 1.5)),
        ("infiltration_velocity_coeff", "0.5x", lambda b: mutate_infiltration_velocity_coeff(b, 0.5)),
        ("infiltration_velocity_coeff", "1.5x", lambda b: mutate_infiltration_velocity_coeff(b, 1.5)),
        ("window_g_value", "0.8x", lambda b: mutate_window_g_value(b, 0.8)),
        ("window_g_value", "1.2x", lambda b: mutate_window_g_value(b, 1.2)),
        ("internal_gains", "0.7x", lambda b: mutate_internal_gains(b, 0.7)),
        ("internal_gains", "1.3x", lambda b: mutate_internal_gains(b, 1.3)),
        ("night_purge_boost_factor", "0.7x", lambda b: mutate_night_purge_boost_factor(b, 0.7)),
        ("night_purge_boost_factor", "1.3x", lambda b: mutate_night_purge_boost_factor(b, 1.3)),
        ("night_purge_delta_t_min", "0.5x", lambda b: mutate_night_purge_delta_t_min(b, 0.5)),
        ("night_purge_delta_t_min", "2.0x", lambda b: mutate_night_purge_delta_t_min(b, 2.0)),
        ("night_purge_enabled", "off", lambda b: set_night_purge_enabled(b, False)),
        ("night_purge_enabled", "on", lambda b: set_night_purge_enabled(b, True)),
        ("external_emissivity_default", "0.80", lambda b: set_external_emissivity_default(b, 0.80)),
        ("external_emissivity_default", "0.95", lambda b: set_external_emissivity_default(b, 0.95)),
    ]
    for i, (param, value_tag, fn) in enumerate(cont_specs, start=1):
        cases.append(
            {
                "case_id": f"{i:02d}_{param}_{value_tag}",
                "parameter": param,
                "value": value_tag,
                "mutate": fn,
            }
        )

    # Categorical choices
    for model in ["table", "doe2", "mowitt", "blast", "simplecombined"]:
        cases.append(
            {
                "case_id": f"ext_conv_model_{model}",
                "parameter": "external_convection_model",
                "value": model,
                "mutate": (lambda m: (lambda b: set_external_convection_model(b, m)))(model),
            }
        )
    for model in ["table", "dynamic"]:
        cases.append(
            {
                "case_id": f"ext_rad_model_{model}",
                "parameter": "external_radiation_model",
                "value": model,
                "mutate": (lambda m: (lambda b: set_external_radiation_model(b, m)))(model),
            }
        )
    for model in ["berdahl_fromberg", "swinbank", "epw_ir"]:
        cases.append(
            {
                "case_id": f"sky_model_{model}",
                "parameter": "sky_temperature_model",
                "value": model,
                "mutate": (lambda m: (lambda b: set_sky_temperature_model(b, m)))(model),
            }
        )
    return cases


def save_html_summary(df: pd.DataFrame, out_path: Path) -> bool:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception:
        return False

    if df.empty:
        return False

    d = df.copy()
    d["label"] = d["parameter"].astype(str) + " | " + d["value"].astype(str)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=False,
        subplot_titles=(
            "Absolute delta summer mean Tair [C] vs baseline",
            "Absolute delta summer p95 Tair [C] vs baseline",
            "Absolute delta summer over-threshold degree-hours [C*h] vs baseline",
        ),
        vertical_spacing=0.12,
    )
    fig.add_trace(
        go.Bar(
            x=d["label"],
            y=d["abs_delta_summer_mean_Tair_C"],
            name="|delta mean Tair|",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=d["label"],
            y=d["abs_delta_summer_p95_Tair_C"],
            name="|delta p95 Tair|",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=d["label"],
            y=d["abs_delta_summer_over_threshold_degC_h"],
            name="|delta degree-hours|",
        ),
        row=3,
        col=1,
    )
    fig.update_layout(
        title="Sensitivity analysis free-floating (summer)",
        template="plotly_white",
        height=1080,
        showlegend=False,
    )
    fig.update_yaxes(title_text="[C]", row=1, col=1)
    fig.update_yaxes(title_text="[C]", row=2, col=1)
    fig.update_yaxes(title_text="[C*h]", row=3, col=1)
    fig.update_xaxes(tickangle=-35, row=1, col=1)
    fig.update_xaxes(tickangle=-35, row=2, col=1)
    fig.update_xaxes(tickangle=-35, row=3, col=1)
    fig.write_html(out_path, include_plotlyjs="cdn")
    return True


def run_case(
    case_id: str,
    parameter: str,
    value_tag: str,
    mutate: Callable[[dict], None] | None,
    baseline_bui: dict,
    weather_path: str,
    warmup_hours: int,
    months: Sequence[int],
    threshold_c: float,
) -> Dict[str, float | str]:
    bui = copy.deepcopy(baseline_bui)
    if mutate is not None:
        mutate(bui)

    t0 = time.perf_counter()
    hourly, _annual = ISO52016.Temperature_and_Energy_needs_calculation_multizone(
        building_object=bui,
        path_weather_file=weather_path,
        weather_source="epw",
        include_solar=True,
        warmup_hours=int(warmup_hours),
        hvac_control_variable="air",
    )
    elapsed = float(time.perf_counter() - t0)

    metrics = compute_summer_metrics(
        hourly_df=hourly,
        zone_names=get_zone_names(bui),
        months=months,
        threshold_c=threshold_c,
    )
    out: Dict[str, float | str] = {
        "case_id": case_id,
        "parameter": parameter,
        "value": value_tag,
        "run_time_s": elapsed,
    }
    out.update(metrics)
    return out


def prepare_baseline_building(bui: dict, weather_path: str, night_purge_preset: str) -> tuple[dict, str]:
    prepared, _opaque_adjustments = _normalize_idf_gross_opaque_areas(bui)
    selected_purge_preset = str(night_purge_preset)
    if selected_purge_preset == "auto_geo":
        selected_purge_preset = _auto_purge_preset_from_latitude(_epw_latitude_abs(weather_path))
    purge_cfg = _resolve_summer_night_purge_config(preset=selected_purge_preset)
    apply_summer_night_purge_to_zones(prepared, summer_night_purge=purge_cfg)

    vent = prepared.setdefault("building_parameters", {}).setdefault("ventilation", {})
    if bool(vent.get("infiltration_coeff_constant_auto_by_latitude", False)):
        vent["infiltration_coeff_constant"] = _auto_infiltration_coeff_constant_from_epw(weather_path)

    return prepared, selected_purge_preset


def main() -> None:
    args = parse_args()
    weather_path = str(Path(args.weather_path).expanduser().resolve())
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    months = [int(m) for m in args.months]
    threshold_c = float(args.temp_threshold_c)

    if not os.path.exists(weather_path):
        raise FileNotFoundError(f"Weather file not found: {weather_path}")

    baseline_bui, resolved_purge_preset = prepare_baseline_building(
        copy.deepcopy(BASE_BUILDING_OBJECT),
        weather_path=weather_path,
        night_purge_preset=str(args.night_purge_preset),
    )
    set_free_floating_no_hvac(baseline_bui)

    print("Running baseline...")
    baseline = run_case(
        case_id="baseline",
        parameter="baseline",
        value_tag=resolved_purge_preset,
        mutate=None,
        baseline_bui=baseline_bui,
        weather_path=weather_path,
        warmup_hours=int(args.warmup_hours),
        months=months,
        threshold_c=threshold_c,
    )
    print(
        f"baseline done: mean={baseline['summer_mean_Tair_C']:.2f} C | "
        f"p95={baseline['summer_p95_Tair_C']:.2f} C | "
        f"over{threshold_c:.1f}={baseline['summer_over_threshold_degC_h']:.1f} C*h"
    )

    cases = build_cases()
    rows: List[Dict[str, float | str]] = [baseline]

    for i, case in enumerate(cases, start=1):
        cid = str(case["case_id"])
        print(f"[{i:02d}/{len(cases):02d}] {cid} ...")
        try:
            row = run_case(
                case_id=cid,
                parameter=str(case["parameter"]),
                value_tag=str(case["value"]),
                mutate=case["mutate"],  # type: ignore[arg-type]
                baseline_bui=baseline_bui,
                weather_path=weather_path,
                warmup_hours=int(args.warmup_hours),
                months=months,
                threshold_c=threshold_c,
            )
            row["status"] = "ok"
            rows.append(row)
            print(
                "  done "
                f"mean={row['summer_mean_Tair_C']:.2f} C "
                f"(delta={float(row['summer_mean_Tair_C']) - float(baseline['summer_mean_Tair_C']):+.2f})"
            )
        except Exception as exc:  # keep the campaign running
            rows.append(
                {
                    "case_id": cid,
                    "parameter": str(case["parameter"]),
                    "value": str(case["value"]),
                    "status": f"error: {exc}",
                }
            )
            print(f"  failed: {exc}")

    all_df = pd.DataFrame(rows)
    all_path = out_dir / "free_floating_sensitivity_runs.csv"
    all_df.to_csv(all_path, index=False)

    ok_df = all_df.loc[
        (all_df["case_id"] != "baseline") & (all_df.get("status", "ok") == "ok")
    ].copy()
    if not ok_df.empty:
        b_mean = float(baseline["summer_mean_Tair_C"])
        b_p95 = float(baseline["summer_p95_Tair_C"])
        b_max = float(baseline["summer_max_Tair_C"])
        b_dh = float(baseline["summer_over_threshold_degC_h"])

        ok_df["delta_summer_mean_Tair_C"] = pd.to_numeric(
            ok_df["summer_mean_Tair_C"], errors="coerce"
        ) - b_mean
        ok_df["delta_summer_p95_Tair_C"] = pd.to_numeric(
            ok_df["summer_p95_Tair_C"], errors="coerce"
        ) - b_p95
        ok_df["delta_summer_max_Tair_C"] = pd.to_numeric(
            ok_df["summer_max_Tair_C"], errors="coerce"
        ) - b_max
        ok_df["delta_summer_over_threshold_degC_h"] = pd.to_numeric(
            ok_df["summer_over_threshold_degC_h"], errors="coerce"
        ) - b_dh

        ok_df["abs_delta_summer_mean_Tair_C"] = ok_df["delta_summer_mean_Tair_C"].abs()
        ok_df["abs_delta_summer_p95_Tair_C"] = ok_df["delta_summer_p95_Tair_C"].abs()
        ok_df["abs_delta_summer_max_Tair_C"] = ok_df["delta_summer_max_Tair_C"].abs()
        ok_df["abs_delta_summer_over_threshold_degC_h"] = ok_df[
            "delta_summer_over_threshold_degC_h"
        ].abs()

        ranking_df = ok_df.sort_values(
            ["abs_delta_summer_mean_Tair_C", "abs_delta_summer_p95_Tair_C"],
            ascending=False,
        ).reset_index(drop=True)
    else:
        ranking_df = ok_df

    ranking_path = out_dir / "free_floating_sensitivity_ranking.csv"
    ranking_df.to_csv(ranking_path, index=False)

    html_path = out_dir / "free_floating_sensitivity_ranking.html"
    html_ok = save_html_summary(ranking_df, html_path)

    print(f"Saved runs: {all_path}")
    print(f"Saved ranking: {ranking_path}")
    if html_ok:
        print(f"Saved html: {html_path}")
    else:
        print("Plotly not available -> HTML not generated.")


if __name__ == "__main__":
    main()
