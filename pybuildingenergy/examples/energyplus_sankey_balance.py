#!/usr/bin/env python3
"""Build an EnergyPlus annual energy-balance Sankey from CSV output.

Reads `two_zone_ideal_24_2_fixedout.csv`-like files and extracts/aggregates:
- Inputs: heating, transmission gains, window gains, infiltration gains, internal lights
- Outputs: cooling, transmission losses, window losses, infiltration losses
- Storage/residual: closes the annual balance

Outputs:
- HTML Sankey report
- CSV summary (inputs/outputs/storage)
- CSV hourly components [W]
- JSON with column mapping used for each component
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

import sys
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pybuildingenergy.source.functions import plot_sankey_building  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Crea Sankey e bilancio input/output da output CSV EnergyPlus "
            "(two_zone_ideal_24_2_fixedout.csv)."
        )
    )
    parser.add_argument(
        "--energyplus-csv",
        default=str(SCRIPT_DIR / "two_zone_ideal_24_2_fixedout.csv"),
        help="Percorso CSV output EnergyPlus.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2020,
        help="Anno base per parsing Date/Time EnergyPlus.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "result_test"),
        help="Directory output.",
    )
    parser.add_argument(
        "--out-prefix",
        default="energyplus_balance_sankey",
        help="Prefisso output.",
    )
    return parser.parse_args()


def parse_energyplus_datetime(series: pd.Series, *, year: int) -> pd.DatetimeIndex:
    raw = series.astype(str).str.strip()
    parts = raw.str.extract(
        r"(?P<month>\d{1,2})/(?P<day>\d{1,2})\s+(?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})"
    )
    if parts.isna().any().any():
        bad = raw[parts.isna().any(axis=1)].head(5).tolist()
        raise ValueError(f"Date/Time EnergyPlus non parseabile. Esempi: {bad}")

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

    # Hourly EnergyPlus output is typically end-of-interval.
    return pd.DatetimeIndex(ts - pd.Timedelta(hours=1))


def infer_timestep_seconds(index: pd.DatetimeIndex, default: float = 3600.0) -> float:
    if len(index) < 2:
        return float(default)
    dt = (
        pd.Series(index)
        .diff()
        .dt.total_seconds()
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    dt = dt[dt > 0]
    if dt.empty:
        return float(default)
    return float(dt.median())


def cols_matching(columns: Iterable[str], token: str) -> List[str]:
    t = token.lower()
    return [c for c in columns if t in c.lower()]


def classify_conduction_surface(surface_name: str) -> Optional[str]:
    s = surface_name.upper()
    if "_INT" in s:
        return None
    if "ROOF" in s:
        return "roof"
    if "FLOOR" in s or "GROUND" in s:
        return "ground"
    if "WALL" in s:
        return "wall"
    return "other"


def _sum_cols_energy_j(df: pd.DataFrame, cols: List[str]) -> pd.Series:
    if not cols:
        return pd.Series(0.0, index=df.index, dtype=float)
    return df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)


def _build_lights_hourly_from_monthly_meter(df: pd.DataFrame, col: str, dt_s: float) -> pd.Series:
    s = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    monthly_j = s.resample("ME").sum()
    if monthly_j.empty:
        return pd.Series(0.0, index=df.index, dtype=float)

    out_w = pd.Series(0.0, index=df.index, dtype=float)
    for month_end, e_month_j in monthly_j.items():
        mask = (df.index.year == month_end.year) & (df.index.month == month_end.month)
        h_count = int(mask.sum())
        if h_count <= 0:
            continue
        out_w.loc[mask] = float(e_month_j) / (h_count * max(dt_s, 1e-9))
    return out_w


def build_balance_components(df: pd.DataFrame, dt_s: float) -> tuple[pd.DataFrame, Dict[str, List[str]]]:
    components = pd.DataFrame(index=df.index)
    columns_used: Dict[str, List[str]] = {}

    # HVAC meters
    c_heat = cols_matching(df.columns, "Heating:EnergyTransfer [J](Hourly)")
    c_cool = cols_matching(df.columns, "Cooling:EnergyTransfer [J](Hourly)")
    columns_used["Heating meter"] = c_heat
    columns_used["Cooling meter"] = c_cool
    components["in_heating_W"] = _sum_cols_energy_j(df, c_heat) / max(dt_s, 1e-9)
    components["out_cooling_W"] = _sum_cols_energy_j(df, c_cool) / max(dt_s, 1e-9)

    # Infiltration sensible gain/loss
    c_infil_gain = cols_matching(df.columns, "Zone Infiltration Sensible Heat Gain Energy [J](Hourly)")
    c_infil_loss = cols_matching(df.columns, "Zone Infiltration Sensible Heat Loss Energy [J](Hourly)")
    columns_used["Infiltration gain"] = c_infil_gain
    columns_used["Infiltration loss"] = c_infil_loss
    components["in_infiltration_gain_W"] = _sum_cols_energy_j(df, c_infil_gain) / max(dt_s, 1e-9)
    components["out_infiltration_loss_W"] = _sum_cols_energy_j(df, c_infil_loss) / max(dt_s, 1e-9)

    # Window gains/losses
    c_win_gain = cols_matching(df.columns, "Surface Window Heat Gain Energy [J](Hourly)")
    c_win_loss = cols_matching(df.columns, "Surface Window Heat Loss Energy [J](Hourly)")
    columns_used["Window heat gain"] = c_win_gain
    columns_used["Window heat loss"] = c_win_loss
    components["in_window_gain_W"] = _sum_cols_energy_j(df, c_win_gain) / max(dt_s, 1e-9)
    components["out_window_loss_W"] = _sum_cols_energy_j(df, c_win_loss) / max(dt_s, 1e-9)

    # Opaque conduction (average face): split gain/loss by sign and by category
    c_cond = cols_matching(df.columns, "Surface Average Face Conduction Heat Transfer Energy [J](Hourly)")
    columns_used["Conduction average face (all)"] = c_cond

    for cat in ("wall", "roof", "ground", "other"):
        components[f"in_transmission_{cat}_gain_W"] = 0.0
        components[f"out_transmission_{cat}_loss_W"] = 0.0

    for c in c_cond:
        s_name = c.split(":", 1)[0].strip()
        cat = classify_conduction_surface(s_name)
        if cat is None:
            continue
        s_j = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        # Convention observed in this CSV: negative = heat loss from zones.
        gain_w = s_j.clip(lower=0.0) / max(dt_s, 1e-9)
        loss_w = (-s_j.clip(upper=0.0)) / max(dt_s, 1e-9)
        components[f"in_transmission_{cat}_gain_W"] += gain_w
        components[f"out_transmission_{cat}_loss_W"] += loss_w
        columns_used.setdefault(f"Conduction {cat}", []).append(c)

    # Internal lights meter (monthly): distribute uniformly by month to get hourly W.
    c_lights = [c for c in df.columns if "interiorlights:electricity [j](monthly)" in c.lower()]
    columns_used["Internal lights meter (monthly)"] = c_lights
    if c_lights:
        components["in_internal_lights_W"] = _build_lights_hourly_from_monthly_meter(df, c_lights[0], dt_s)
    else:
        components["in_internal_lights_W"] = 0.0

    # sanitize
    for col in components.columns:
        components[col] = pd.to_numeric(components[col], errors="coerce").fillna(0.0).clip(lower=0.0)

    return components, columns_used


def annual_wh(series_w: pd.Series, dt_s: float) -> float:
    return float(series_w.sum() * dt_s / 3600.0)


def main() -> None:
    args = parse_args()

    ep_csv = Path(args.energyplus_csv).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not ep_csv.exists():
        raise FileNotFoundError(f"CSV EnergyPlus non trovato: {ep_csv}")

    df = pd.read_csv(ep_csv)
    if "Date/Time" not in df.columns:
        raise KeyError("Nel CSV EnergyPlus manca la colonna 'Date/Time'.")

    df.index = parse_energyplus_datetime(df["Date/Time"], year=args.year)
    df = df.loc[~df.index.duplicated(keep="first")].sort_index()

    dt_s = infer_timestep_seconds(df.index, default=3600.0)

    comp, columns_used = build_balance_components(df, dt_s)

    in_cols = [c for c in comp.columns if c.startswith("in_")]
    out_cols = [c for c in comp.columns if c.startswith("out_")]

    inputs_wh = {c.removeprefix("in_").replace("_W", ""): annual_wh(comp[c], dt_s) for c in in_cols}
    outputs_wh = {c.removeprefix("out_").replace("_W", ""): annual_wh(comp[c], dt_s) for c in out_cols}

    total_in = float(sum(inputs_wh.values()))
    total_out = float(sum(outputs_wh.values()))
    storage_wh = total_in - total_out

    sankey_data = {
        "inputs": {
            "Heating": inputs_wh.get("heating", 0.0),
            "Internal lights": inputs_wh.get("internal_lights", 0.0),
            "Window heat gains": inputs_wh.get("window_gain", 0.0),
            "Infiltration gains": inputs_wh.get("infiltration_gain", 0.0),
            "Transmission gain wall": inputs_wh.get("transmission_wall_gain", 0.0),
            "Transmission gain roof": inputs_wh.get("transmission_roof_gain", 0.0),
            "Transmission gain ground": inputs_wh.get("transmission_ground_gain", 0.0),
            "Transmission gain other": inputs_wh.get("transmission_other_gain", 0.0),
        },
        "outputs": {
            "Cooling (extracted energy)": outputs_wh.get("cooling", 0.0),
            "Infiltration losses": outputs_wh.get("infiltration_loss", 0.0),
            "Window losses": outputs_wh.get("window_loss", 0.0),
            "Transmission loss wall": outputs_wh.get("transmission_wall_loss", 0.0),
            "Transmission loss roof": outputs_wh.get("transmission_roof_loss", 0.0),
            "Transmission loss ground": outputs_wh.get("transmission_ground_loss", 0.0),
            "Transmission loss other": outputs_wh.get("transmission_other_loss", 0.0),
        },
        "energy_accumulated_zone": storage_wh,
    }

    # Remove exact-zero branches for readability
    sankey_data["inputs"] = {k: v for k, v in sankey_data["inputs"].items() if abs(v) > 1e-9}
    sankey_data["outputs"] = {k: v for k, v in sankey_data["outputs"].items() if abs(v) > 1e-9}

    fig = plot_sankey_building(sankey_data)
    fig.update_layout(title="EnergyPlus annual balance — Sankey", font_size=12)

    out_html = out_dir / f"{args.out_prefix}.html"
    out_summary = out_dir / f"{args.out_prefix}_summary.csv"
    out_hourly = out_dir / f"{args.out_prefix}_hourly_components.csv"
    out_cols_json = out_dir / f"{args.out_prefix}_columns_used.json"
    out_sankey_json = out_dir / f"{args.out_prefix}_sankey_data.json"

    fig.write_html(out_html, include_plotlyjs="cdn")
    comp.to_csv(out_hourly)

    rows = []
    for k, v in sankey_data["inputs"].items():
        rows.append({"side": "input", "component": k, "energy_Wh": float(v), "energy_kWh": float(v) / 1000.0})
    for k, v in sankey_data["outputs"].items():
        rows.append({"side": "output", "component": k, "energy_Wh": float(v), "energy_kWh": float(v) / 1000.0})
    rows.append({"side": "storage", "component": "energy_accumulated_zone", "energy_Wh": float(storage_wh), "energy_kWh": float(storage_wh) / 1000.0})
    rows.append({"side": "check", "component": "total_inputs_Wh", "energy_Wh": total_in, "energy_kWh": total_in / 1000.0})
    rows.append({"side": "check", "component": "total_outputs_Wh", "energy_Wh": total_out, "energy_kWh": total_out / 1000.0})
    pd.DataFrame(rows).to_csv(out_summary, index=False)

    with out_cols_json.open("w", encoding="utf-8") as f:
        json.dump(columns_used, f, indent=2)
    with out_sankey_json.open("w", encoding="utf-8") as f:
        json.dump(sankey_data, f, indent=2)

    residual_rel = (storage_wh / total_in * 100.0) if abs(total_in) > 1e-9 else 0.0
    print(f"[ok] Sankey HTML: {out_html}")
    print(f"[ok] Summary CSV: {out_summary}")
    print(f"[ok] Hourly components CSV: {out_hourly}")
    print(f"[ok] Columns used JSON: {out_cols_json}")
    print(f"[ok] Sankey data JSON: {out_sankey_json}")
    print(f"[check] total_in={total_in:.1f} Wh, total_out={total_out:.1f} Wh, storage/residual={storage_wh:.1f} Wh ({residual_rel:.3f}%)")


if __name__ == "__main__":
    main()
