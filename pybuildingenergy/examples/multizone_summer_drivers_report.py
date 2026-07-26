#!/usr/bin/env python3
"""Build an HTML summer-driver report for multizone simulation outputs.

The report helps explain high summer daily oscillations without active cooling
by plotting, per zone:
- temperatures (air, operative, outdoor),
- key heat-flow drivers [W]:
  internal gains, window solar, opaque-surface solar forcing,
  ventilation exchange, thermal bridges, ground exchange, HVAC load.
"""

from __future__ import annotations

import argparse
import ast
import copy
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

import sys

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pybuildingenergy.source.utils import ISO52016  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera report HTML con driver termici estivi per zona "
            "a partire dai risultati multizona."
        )
    )
    parser.add_argument(
        "--hourly-csv",
        default=str(PROJECT_ROOT / "result_test" / "multizone_v1_hourly.csv"),
        help="CSV orario multizona (es. multizone_v1_hourly.csv).",
    )
    parser.add_argument(
        "--example-py",
        default=str(SCRIPT_DIR / "multizone_free_floating_example.py"),
        help="Script che contiene building_object.",
    )
    parser.add_argument(
        "--weather-source",
        choices=["epw", "pvgis"],
        default="epw",
        help="Sorgente meteo usata per ricostruire forcing.",
    )
    parser.add_argument(
        "--weather-file",
        default=str(SCRIPT_DIR / "2020_Milan.epw"),
        help="EPW usato quando --weather-source=epw.",
    )
    parser.add_argument(
        "--date-from",
        default="2020-06-01",
        help="Inizio periodo report (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--date-to",
        default="2020-08-31",
        help="Fine periodo report (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "result_test"),
        help="Cartella output.",
    )
    parser.add_argument(
        "--out-prefix",
        default="multizone_summer_drivers",
        help="Prefisso output.",
    )
    return parser.parse_args()


def infer_timestep_hours(index: pd.DatetimeIndex, default: float = 1.0) -> float:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return float(default)
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
        return float(default)
    return float(dt_h.median())


def detect_time_column(df: pd.DataFrame) -> str:
    for candidate in ("time(local)", "time", "timestamp", "datetime", "Date/Time"):
        if candidate in df.columns:
            return candidate
    for c in df.columns:
        cl = str(c).lower()
        if "time" in cl or "date" in cl:
            return c
    raise KeyError("Impossibile rilevare colonna tempo nel CSV.")


def load_building_object_from_python(path_py: Path) -> dict:
    src = path_py.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    assignment_code = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "building_object":
                if node.end_lineno is None:
                    raise RuntimeError("Impossibile estrarre assegnazione building_object.")
                assignment_code = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                break
        if assignment_code is not None:
            break
    if assignment_code is None:
        raise KeyError(f"'building_object' non trovato in {path_py}")

    ns = {"np": np, "pd": pd}
    exec(assignment_code, ns, ns)
    return copy.deepcopy(ns["building_object"])


def _orientation_string(surf: dict) -> str:
    ori_existing = str(surf.get("ISO52016_orientation_string", "")).upper()
    if ori_existing in {"HOR", "NV", "EV", "SV", "WV", "HR", "HF"}:
        return ori_existing

    ori = surf.get("orientation", {}) or {}
    az = ori.get("azimuth", None)
    tilt = ori.get("tilt", None)
    try:
        az_f = float(az) % 360.0
        tilt_f = float(tilt)
    except Exception:
        return "SV"

    if abs(tilt_f) < 1e-6:
        return "HOR"
    if abs(tilt_f - 180.0) < 1e-6:
        return "HF"
    if abs(tilt_f - 90.0) < 1e-6:
        candidates = np.array([0.0, 90.0, 180.0, 270.0], dtype=float)
        labels = np.array(["NV", "EV", "SV", "WV"], dtype=object)
        diffs = np.abs(((az_f - candidates + 180.0) % 360.0) - 180.0)
        return str(labels[int(np.argmin(diffs))])
    return "HOR" if tilt_f < 45.0 else "SV"


def _build_shading_components_by_zone_orientation(building_object: dict, zone_names: list[str]) -> dict:
    default_zone = zone_names[0] if zone_names else "main"
    out = {}
    for surf in building_object.get("building_surface", []):
        if str(surf.get("type", "")).lower() != "transparent":
            continue
        if str(surf.get("boundary", "OUTDOORS")).upper() != "OUTDOORS":
            continue
        win_name = str(surf.get("name", "")).strip()
        if not win_name:
            continue
        try:
            win_area = float(surf.get("area", 0.0))
        except Exception:
            continue
        if not np.isfinite(win_area) or win_area <= 0.0:
            continue

        zname = surf.get("zone", default_zone)
        if zname not in zone_names:
            zname = default_zone
        ori = _orientation_string(surf)
        key = (zname, ori)
        out.setdefault(key, []).append((win_name, win_area))
    return out


def build_drivers(
    building_object: dict,
    hourly_df: pd.DataFrame,
    weather_source: str,
    weather_file: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    zones = building_object.get("zones", [])
    if not zones:
        zones = [{"name": "main", "net_floor_area": float(building_object["building"]["net_floor_area"])}]
    zone_names = [z["name"] for z in zones]
    z_set = set(zone_names)
    default_zone = zone_names[0]

    # Weather forcing used by ISO52016
    weather_kwargs = {"weather_source": weather_source}
    if weather_source == "epw":
        weather_kwargs["path_weather_file"] = weather_file
    sim_df = ISO52016().Weather_data_bui(copy.deepcopy(building_object), **weather_kwargs).simulation_df
    sim_df = sim_df.copy()
    sim_df.index = pd.DatetimeIndex(sim_df.index)
    sim_df = sim_df.loc[~sim_df.index.duplicated(keep="first")].sort_index()

    hourly = hourly_df.copy()
    hourly.index = pd.DatetimeIndex(hourly.index)
    hourly = hourly.loc[~hourly.index.duplicated(keep="first")].sort_index()

    idx = hourly.index.intersection(sim_df.index)
    if len(idx) == 0:
        raise ValueError("Nessun timestamp comune tra hourly multizona e forcing meteo.")
    hourly = hourly.reindex(idx)
    sim_df = sim_df.reindex(idx)

    t_out = pd.to_numeric(sim_df["T2m"], errors="coerce").interpolate(limit_direction="both")
    dt_h = infer_timestep_hours(idx, default=1.0)

    # Ground and thermal bridges
    t_Th = ISO52016().Temp_calculation_of_ground(
        copy.deepcopy(building_object),
        path_weather_file=weather_file,
        weather_source=weather_source,
    )
    theta_gr_monthly = np.asarray(t_Th.Theta_gr_ve, dtype=float)
    R_gr = float(t_Th.R_gr_ve) if float(t_Th.R_gr_ve) != 0.0 else 1e9
    h_gr_elem = 1.0 / R_gr

    zone_area = {z["name"]: float(z.get("net_floor_area", 0.0)) for z in zones}
    area_tot = float(sum(max(0.0, a) for a in zone_area.values())) or 1.0
    h_tb_tot = float(t_Th.thermal_bridge_heat)
    h_tb_zone = {zn: h_tb_tot * (max(0.0, zone_area.get(zn, 0.0)) / area_tot) for zn in zone_names}

    windows_by_zone = {zn: [] for zn in zone_names}
    opaque_out_by_zone = {zn: [] for zn in zone_names}
    n_ground_by_zone = {zn: 0 for zn in zone_names}

    for surf in building_object.get("building_surface", []):
        zname = surf.get("zone", default_zone)
        if zname not in z_set:
            zname = default_zone
        bnd = str(surf.get("boundary", "OUTDOORS")).upper()
        typ = str(surf.get("type", "")).lower()
        ori = _orientation_string(surf)
        surf["ISO52016_orientation_string"] = ori

        if typ == "transparent" and bnd == "OUTDOORS":
            windows_by_zone[zname].append(surf)
        elif typ == "opaque" and bnd == "OUTDOORS":
            opaque_out_by_zone[zname].append(surf)
        elif typ == "opaque" and bnd == "GROUND":
            n_ground_by_zone[zname] += 1

    shading_components = _build_shading_components_by_zone_orientation(building_object, zone_names)

    out = pd.DataFrame(index=idx)
    out["T_out_C"] = t_out

    for zn in zone_names:
        t_air_col = f"T_air_{zn}"
        t_op_col = f"T_op_{zn}"
        q_hvac_col = f"Q_HVAC_{zn}"
        phi_int_col = f"Phi_int_{zn}"
        h_ve_col = f"H_ve_{zn}"

        if t_air_col not in hourly.columns:
            continue

        t_air = pd.to_numeric(hourly[t_air_col], errors="coerce").interpolate(limit_direction="both")
        t_op = (
            pd.to_numeric(hourly[t_op_col], errors="coerce").interpolate(limit_direction="both")
            if t_op_col in hourly.columns else t_air.copy()
        )
        q_hvac = (
            pd.to_numeric(hourly[q_hvac_col], errors="coerce").fillna(0.0)
            if q_hvac_col in hourly.columns else pd.Series(0.0, index=idx)
        )
        phi_int = (
            pd.to_numeric(hourly[phi_int_col], errors="coerce").fillna(0.0)
            if phi_int_col in hourly.columns else pd.Series(0.0, index=idx)
        )
        h_ve = (
            pd.to_numeric(hourly[h_ve_col], errors="coerce").fillna(0.0).clip(lower=0.0)
            if h_ve_col in hourly.columns else pd.Series(0.0, index=idx)
        )

        q_vent = h_ve * (t_air - t_out)
        q_tb = float(h_tb_zone.get(zn, 0.0)) * (t_air - t_out)

        h_gr_zone = float(n_ground_by_zone.get(zn, 0)) * h_gr_elem
        t_gr = pd.Series([float(theta_gr_monthly[int(ts.month) - 1]) for ts in idx], index=idx, dtype=float)
        q_ground = h_gr_zone * (t_air - t_gr)

        q_solar_window = pd.Series(0.0, index=idx, dtype=float)
        for surf in windows_by_zone.get(zn, []):
            ori = str(surf.get("ISO52016_orientation_string", "SV")).upper()
            col = f"I_sol_tot_{ori}"
            if col not in sim_df.columns:
                continue
            try:
                g_val = float(surf.get("g_value", 0.0))
                area = float(surf.get("area", 0.0))
            except Exception:
                continue
            i_tot = pd.to_numeric(sim_df[col], errors="coerce").fillna(0.0)
            f_sh = np.array(
                [
                    ISO52016._surface_shading_factor_from_timeseries(
                        sim_df=sim_df,
                        tstep=i,
                        surface=surf,
                        shading_components_by_zone_orientation=shading_components,
                        default_zone=default_zone,
                    )
                    for i in range(len(idx))
                ],
                dtype=float,
            )
            q_solar_window += np.maximum(0.0, g_val * area * i_tot.to_numpy() * f_sh)

        q_solar_opaque_ext = pd.Series(0.0, index=idx, dtype=float)
        for surf in opaque_out_by_zone.get(zn, []):
            ori = str(surf.get("ISO52016_orientation_string", "SV")).upper()
            col = f"I_sol_tot_{ori}"
            if col not in sim_df.columns:
                continue
            try:
                alpha = float(surf.get("solar_absorptance", 0.0))
                area = float(surf.get("area", 0.0))
            except Exception:
                continue
            i_tot = pd.to_numeric(sim_df[col], errors="coerce").fillna(0.0)
            q_solar_opaque_ext += np.maximum(0.0, alpha * area * i_tot.to_numpy())

        out[f"T_air_{zn}_C"] = t_air
        out[f"T_op_{zn}_C"] = t_op
        out[f"Q_HVAC_{zn}_W"] = q_hvac
        out[f"Phi_int_{zn}_W"] = phi_int
        out[f"H_ve_{zn}_W_K"] = h_ve
        out[f"q_vent_{zn}_W"] = q_vent
        out[f"q_tb_{zn}_W"] = q_tb
        out[f"q_ground_{zn}_W"] = q_ground
        out[f"q_solar_window_{zn}_W"] = q_solar_window
        out[f"q_solar_opaque_ext_{zn}_W"] = q_solar_opaque_ext

    # Summary per zone
    rows = []
    for zn in zone_names:
        t_air_col = f"T_air_{zn}_C"
        if t_air_col not in out.columns:
            continue
        t_air = pd.to_numeric(out[t_air_col], errors="coerce")
        t_op = pd.to_numeric(out[f"T_op_{zn}_C"], errors="coerce")
        q_hvac = pd.to_numeric(out[f"Q_HVAC_{zn}_W"], errors="coerce").fillna(0.0)
        phi_int = pd.to_numeric(out[f"Phi_int_{zn}_W"], errors="coerce").fillna(0.0)
        q_vent = pd.to_numeric(out[f"q_vent_{zn}_W"], errors="coerce").fillna(0.0)
        q_tb = pd.to_numeric(out[f"q_tb_{zn}_W"], errors="coerce").fillna(0.0)
        q_ground = pd.to_numeric(out[f"q_ground_{zn}_W"], errors="coerce").fillna(0.0)
        q_sol_w = pd.to_numeric(out[f"q_solar_window_{zn}_W"], errors="coerce").fillna(0.0)
        q_sol_o = pd.to_numeric(out[f"q_solar_opaque_ext_{zn}_W"], errors="coerce").fillna(0.0)

        day_range = (t_air.resample("D").max() - t_air.resample("D").min()).dropna()

        rows.append(
            {
                "zone": zn,
                "T_air_min_C": float(t_air.min()),
                "T_air_max_C": float(t_air.max()),
                "T_air_range_C": float(t_air.max() - t_air.min()),
                "T_air_daily_range_mean_C": float(day_range.mean()) if len(day_range) else np.nan,
                "T_op_min_C": float(t_op.min()),
                "T_op_max_C": float(t_op.max()),
                "E_internal_kWh": float(phi_int.sum() * dt_h / 1000.0),
                "E_solar_window_kWh": float(q_sol_w.sum() * dt_h / 1000.0),
                "E_solar_opaque_ext_kWh": float(q_sol_o.sum() * dt_h / 1000.0),
                "E_vent_loss_kWh": float(q_vent.clip(lower=0.0).sum() * dt_h / 1000.0),
                "E_vent_gain_kWh": float((-q_vent.clip(upper=0.0)).sum() * dt_h / 1000.0),
                "E_tb_loss_kWh": float(q_tb.clip(lower=0.0).sum() * dt_h / 1000.0),
                "E_tb_gain_kWh": float((-q_tb.clip(upper=0.0)).sum() * dt_h / 1000.0),
                "E_ground_loss_kWh": float(q_ground.clip(lower=0.0).sum() * dt_h / 1000.0),
                "E_ground_gain_kWh": float((-q_ground.clip(upper=0.0)).sum() * dt_h / 1000.0),
                "E_HVAC_heat_kWh": float(q_hvac.clip(lower=0.0).sum() * dt_h / 1000.0),
                "E_HVAC_cool_kWh": float((-q_hvac.clip(upper=0.0)).sum() * dt_h / 1000.0),
            }
        )
    summary = pd.DataFrame(rows)
    return out, summary


def build_html_report(
    out_html: Path,
    drivers: pd.DataFrame,
    summary: pd.DataFrame,
    zone_names: list[str],
) -> None:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:
        raise RuntimeError(f"plotly non disponibile: {exc}") from exc

    rows = max(1, 2 * len(zone_names))
    titles = []
    for zn in zone_names:
        titles.append(f"{zn} - Temperature [C]")
        titles.append(f"{zn} - Heat-flow Drivers [W]")

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        subplot_titles=titles,
    )

    r = 1
    for zn in zone_names:
        ta = f"T_air_{zn}_C"
        to = f"T_op_{zn}_C"
        if ta not in drivers.columns:
            continue

        fig.add_trace(go.Scatter(x=drivers.index, y=drivers[ta], mode="lines", name=f"T_air {zn}", line={"width": 1.3}), row=r, col=1)
        fig.add_trace(go.Scatter(x=drivers.index, y=drivers[to], mode="lines", name=f"T_op {zn}", line={"width": 1.1, "dash": "dash"}), row=r, col=1)
        fig.add_trace(go.Scatter(x=drivers.index, y=drivers["T_out_C"], mode="lines", name="T_out", line={"width": 1.0, "color": "#666"}), row=r, col=1)

        rq = r + 1
        for col, name, style in [
            (f"q_solar_window_{zn}_W", f"q_solar_window {zn}", {}),
            (f"q_solar_opaque_ext_{zn}_W", f"q_solar_opaque_ext {zn}", {"dash": "dot"}),
            (f"Phi_int_{zn}_W", f"Phi_int {zn}", {}),
            (f"q_vent_{zn}_W", f"q_vent {zn}", {}),
            (f"q_tb_{zn}_W", f"q_tb {zn}", {}),
            (f"q_ground_{zn}_W", f"q_ground {zn}", {}),
            (f"Q_HVAC_{zn}_W", f"Q_HVAC {zn}", {"width": 1.6}),
        ]:
            if col in drivers.columns:
                line = {"width": 1.1}
                line.update(style)
                fig.add_trace(
                    go.Scatter(x=drivers.index, y=drivers[col], mode="lines", name=name, line=line),
                    row=rq,
                    col=1,
                )
        r += 2

    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        height=max(700, 360 * len(zone_names)),
        title="Multizone Summer Drivers (Hourly)",
    )
    fig.update_yaxes(title_text="C", row=1, col=1)
    for rr in range(2, rows + 1, 2):
        fig.update_yaxes(title_text="W", row=rr, col=1)

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Multizone Summer Drivers</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;}"
        "table{border-collapse:collapse;}th,td{padding:6px 8px;border:1px solid #ddd;}"
        "th{background:#f5f5f5;}</style></head><body>"
        "<h1>Multizone Summer Drivers Report</h1>"
        + fig.to_html(include_plotlyjs="cdn", full_html=False)
        + "<h2>Summary (selected period)</h2>"
        + summary.to_html(index=False, border=0)
        + "</body></html>"
    )
    out_html.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()

    hourly_csv = Path(args.hourly_csv).expanduser().resolve()
    example_py = Path(args.example_py).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not hourly_csv.exists():
        raise FileNotFoundError(f"CSV hourly non trovato: {hourly_csv}")
    if not example_py.exists():
        raise FileNotFoundError(f"File example non trovato: {example_py}")
    if args.weather_source == "epw":
        wf = Path(args.weather_file).expanduser().resolve()
        if not wf.exists():
            raise FileNotFoundError(f"EPW non trovato: {wf}")
        weather_file = str(wf)
    else:
        weather_file = None

    df_hourly = pd.read_csv(hourly_csv)
    tcol = detect_time_column(df_hourly)
    idx = pd.to_datetime(df_hourly[tcol], errors="coerce")
    df_hourly = df_hourly.loc[idx.notna()].copy()
    df_hourly.index = pd.DatetimeIndex(idx[idx.notna()])
    df_hourly = df_hourly.loc[~df_hourly.index.duplicated(keep="first")].sort_index()

    date_from = pd.Timestamp(args.date_from)
    date_to = pd.Timestamp(args.date_to) + pd.Timedelta(hours=23)
    df_hourly = df_hourly.loc[(df_hourly.index >= date_from) & (df_hourly.index <= date_to)].copy()
    if df_hourly.empty:
        raise ValueError("Nessun dato hourly nel periodo selezionato.")

    building_object = load_building_object_from_python(example_py)
    drivers, summary = build_drivers(
        building_object=building_object,
        hourly_df=df_hourly,
        weather_source=args.weather_source,
        weather_file=weather_file,
    )

    zone_names = [z["name"] for z in building_object.get("zones", [])]
    if not zone_names:
        zone_names = ["main"]

    out_hourly = out_dir / f"{args.out_prefix}_hourly.csv"
    out_summary = out_dir / f"{args.out_prefix}_summary.csv"
    out_html = out_dir / f"{args.out_prefix}.html"

    drivers.to_csv(out_hourly)
    summary.to_csv(out_summary, index=False)
    build_html_report(out_html, drivers, summary, zone_names)

    print(f"[ok] Hourly drivers CSV: {out_hourly}")
    print(f"[ok] Summary CSV: {out_summary}")
    print(f"[ok] HTML report: {out_html}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()

