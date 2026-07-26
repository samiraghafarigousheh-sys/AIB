#!/usr/bin/env python3
"""Compare summer drivers between EnergyPlus and ISO 52016 multizone outputs.

Outputs:
- hourly CSV with reconstructed summer drivers
- monthly CSV with summer monthly energy [kWh]
- total CSV with seasonal totals [kWh]
- HTML report with comparison plots
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

for p in (SCRIPT_DIR, SRC_DIR):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

from pybuildingenergy.source.utils import ISO52016  # noqa: E402
from multizone_summer_drivers_report import (  # noqa: E402
    build_drivers as build_iso_summer_drivers,
    detect_time_column,
    infer_timestep_hours,
    load_building_object_from_python,
)
from compare_transmission_losses_eplus_iso import (  # noqa: E402
    build_eplus_transmission_losses,
    build_iso_transmission_losses,
    infer_timestep_seconds,
    parse_energyplus_datetime,
)
from report_energyplus_ventilation_transmission import (  # noqa: E402
    build_iso_ventilation_estimate,
    build_ventilation_from_energyplus_energy,
    build_ventilation_from_flow,
    detect_columns_by_pattern,
    read_epw_drybulb,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera un report HTML di confronto estivo tra EnergyPlus e ISO 52016 "
            "per apporti interni, apporti solari, perdite per trasmissione e ventilazione."
        )
    )
    parser.add_argument(
        "--energyplus-csv",
        default=str(SCRIPT_DIR / "two_zone_ideal_24_2_fixedout.csv"),
        help="CSV output EnergyPlus.",
    )
    parser.add_argument(
        "--iso-csv",
        default=str(PROJECT_ROOT / "result_test" / "multizone_v1_hourly.csv"),
        help="CSV hourly ISO multizone.",
    )
    parser.add_argument(
        "--example-py",
        default=str(SCRIPT_DIR / "multizone_free_floating_example.py"),
        help="Script Python che contiene building_object.",
    )
    parser.add_argument(
        "--weather-source",
        choices=["epw", "pvgis"],
        default="epw",
        help="Sorgente meteo usata dal solver ISO.",
    )
    parser.add_argument(
        "--weather-file",
        default=str(SCRIPT_DIR / "2020_Athens.epw"),
        help="EPW usato per ricostruire i forcing e i carichi di ventilazione.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2020,
        help="Anno base per interpretare Date/Time EnergyPlus.",
    )
    parser.add_argument(
        "--date-from",
        default="2020-06-01",
        help="Inizio periodo (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--date-to",
        default="2020-08-31",
        help="Fine periodo (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "result_test"),
        help="Cartella output.",
    )
    parser.add_argument(
        "--out-prefix",
        default="summer_drivers_energyplus_vs_iso",
        help="Prefisso output.",
    )
    return parser.parse_args()


def _load_iso_hourly(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    tcol = detect_time_column(df)
    idx = pd.to_datetime(df[tcol], errors="coerce")
    df = df.loc[idx.notna()].copy()
    df.index = pd.DatetimeIndex(idx[idx.notna()])
    return df.loc[~df.index.duplicated(keep="first")].sort_index()


def _load_energyplus_hourly(path: Path, year: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "Date/Time" not in df.columns:
        raise KeyError("Nel CSV EnergyPlus manca la colonna 'Date/Time'.")
    idx = parse_energyplus_datetime(df["Date/Time"], year=year)
    df = df.loc[idx.notna()].copy()
    df.index = pd.DatetimeIndex(idx[idx.notna()])
    return df.loc[~df.index.duplicated(keep="first")].sort_index()


def _filter_period(df: pd.DataFrame, date_from: pd.Timestamp, date_to: pd.Timestamp) -> pd.DataFrame:
    return df.loc[(df.index >= date_from) & (df.index <= date_to)].copy()


def _sum_matching_columns(df: pd.DataFrame, prefixes: list[str]) -> pd.Series:
    cols = [c for c in df.columns if any(str(c).startswith(p) for p in prefixes)]
    if not cols:
        return pd.Series(0.0, index=df.index, dtype=float)
    return df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)


def build_iso_category_frame(
    building_object: dict,
    hourly_iso: pd.DataFrame,
    weather_source: str,
    weather_file: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    drivers_iso, summary_iso = build_iso_summer_drivers(
        building_object=building_object,
        hourly_df=hourly_iso,
        weather_source=weather_source,
        weather_file=weather_file,
    )

    t_Th = ISO52016().Temp_calculation_of_ground(
        building_object.copy(),
        path_weather_file=weather_file,
        weather_source=weather_source,
    )
    theta_gr_monthly = np.asarray(t_Th.Theta_gr_ve, dtype=float)
    t_out = pd.to_numeric(drivers_iso["T_out_C"], errors="coerce").interpolate(limit_direction="both")

    trans_iso = build_iso_transmission_losses(
        hourly_iso.reindex(drivers_iso.index),
        building_object=building_object,
        t_out=t_out,
        theta_gr_monthly=theta_gr_monthly,
    )
    trans_iso_total = trans_iso.sum(axis=1) if not trans_iso.empty else pd.Series(0.0, index=drivers_iso.index)

    vent_iso = build_iso_ventilation_estimate(hourly_iso.reindex(drivers_iso.index), t_out=t_out)
    if vent_iso is None:
        vent_iso_gain = pd.Series(0.0, index=drivers_iso.index, dtype=float)
        vent_iso_loss = pd.Series(0.0, index=drivers_iso.index, dtype=float)
    else:
        vent_iso_gain = pd.to_numeric(vent_iso["Q_vent_gain_total_W"], errors="coerce").fillna(0.0)
        vent_iso_loss = pd.to_numeric(vent_iso["Q_vent_loss_total_W"], errors="coerce").fillna(0.0)

    out = pd.DataFrame(index=drivers_iso.index)
    out["internal_W"] = _sum_matching_columns(drivers_iso, ["Phi_int_"])
    out["solar_window_W"] = _sum_matching_columns(drivers_iso, ["q_solar_window_"])
    out["solar_opaque_ext_W"] = _sum_matching_columns(drivers_iso, ["q_solar_opaque_ext_"])
    out["solar_total_W"] = out["solar_window_W"] + out["solar_opaque_ext_W"]
    out["transmission_loss_W"] = pd.to_numeric(trans_iso_total, errors="coerce").fillna(0.0)
    out["ventilation_gain_W"] = vent_iso_gain
    out["ventilation_loss_W"] = vent_iso_loss
    return out, summary_iso


def _build_energyplus_window_solar(df_ep: pd.DataFrame, dt_s: float) -> pd.Series:
    gain_cols = detect_columns_by_pattern(
        df_ep.columns,
        ["Surface Window Heat Gain Energy [J](Hourly)"],
    )
    if not gain_cols:
        return pd.Series(0.0, index=df_ep.index, dtype=float)
    return (
        df_ep[gain_cols]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .sum(axis=1)
        .div(max(dt_s, 1e-9))
    )


def _detect_ep_outdoor_temperature_column(columns) -> str | None:
    for col in columns:
        cl = str(col).strip().lower()
        if "environment:site outdoor air drybulb temperature" in cl and "[c]" in cl:
            return str(col)
    for col in columns:
        cl = str(col).strip().lower()
        if "outdoor" in cl and "drybulb" in cl and "[c]" in cl:
            return str(col)
    return None


def build_energyplus_category_frame(
    df_ep: pd.DataFrame,
    weather_file: str | None,
    year: int,
    internal_reference: pd.Series,
) -> pd.DataFrame:
    dt_s = infer_timestep_seconds(df_ep.index, default=3600.0)
    dt_h = dt_s / 3600.0

    trans_ep = build_eplus_transmission_losses(df_ep, dt_s=dt_s)
    trans_ep_total = trans_ep.sum(axis=1) if not trans_ep.empty else pd.Series(0.0, index=df_ep.index)

    vent_ep = build_ventilation_from_energyplus_energy(df_ep, dt_h=dt_h)
    if vent_ep is None and weather_file:
        out_col = _detect_ep_outdoor_temperature_column(df_ep.columns)
        if out_col is not None:
            t_out = pd.to_numeric(df_ep[out_col], errors="coerce").interpolate(limit_direction="both")
        else:
            t_out = read_epw_drybulb(Path(weather_file), year=year).reindex(df_ep.index)
        vent_ep = build_ventilation_from_flow(df_ep, t_out=t_out, dt_h=dt_h)

    if vent_ep is None:
        vent_ep_gain = pd.Series(0.0, index=df_ep.index, dtype=float)
        vent_ep_loss = pd.Series(0.0, index=df_ep.index, dtype=float)
    else:
        vent_ep_gain = pd.to_numeric(vent_ep["Q_vent_gain_total_W"], errors="coerce").fillna(0.0)
        vent_ep_loss = pd.to_numeric(vent_ep["Q_vent_loss_total_W"], errors="coerce").fillna(0.0)

    internal_common = pd.to_numeric(
        internal_reference.reindex(df_ep.index),
        errors="coerce",
    ).interpolate(limit_direction="both").fillna(0.0)

    out = pd.DataFrame(index=df_ep.index)
    out["internal_W"] = internal_common
    out["solar_window_W"] = _build_energyplus_window_solar(df_ep, dt_s=dt_s)
    out["solar_opaque_ext_W"] = 0.0
    out["solar_total_W"] = out["solar_window_W"]
    out["transmission_loss_W"] = pd.to_numeric(trans_ep_total, errors="coerce").fillna(0.0)
    out["ventilation_gain_W"] = vent_ep_gain
    out["ventilation_loss_W"] = vent_ep_loss
    return out


def _monthly_kwh(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.Series(dtype=float)
    dt_h = infer_timestep_hours(pd.DatetimeIndex(series.index), default=1.0)
    return series.resample("ME").sum() * dt_h / 1000.0


def build_comparison_tables(df_ep_cat: pd.DataFrame, df_iso_cat: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    categories = [
        "internal_W",
        "solar_window_W",
        "solar_opaque_ext_W",
        "solar_total_W",
        "transmission_loss_W",
        "ventilation_gain_W",
        "ventilation_loss_W",
    ]

    monthly_rows = []
    total_rows = []
    for model_name, df_cat in (("EnergyPlus", df_ep_cat), ("ISO 52016", df_iso_cat)):
        for cat in categories:
            monthly = _monthly_kwh(pd.to_numeric(df_cat[cat], errors="coerce").fillna(0.0))
            for ts, val in monthly.items():
                monthly_rows.append(
                    {
                        "model": model_name,
                        "month": ts.strftime("%Y-%m"),
                        "category": cat.removesuffix("_W"),
                        "energy_kWh": float(val),
                    }
                )
            total_rows.append(
                {
                    "model": model_name,
                    "category": cat.removesuffix("_W"),
                    "energy_kWh": float(monthly.sum()),
                }
            )
    return pd.DataFrame(monthly_rows), pd.DataFrame(total_rows)


def build_html_report(
    out_html: Path,
    monthly_df: pd.DataFrame,
    total_df: pd.DataFrame,
    iso_summary: pd.DataFrame,
) -> None:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:
        raise RuntimeError(f"plotly non disponibile: {exc}") from exc

    category_labels = {
        "internal": "Internal gains",
        "solar_window": "Solar gains - windows",
        "solar_opaque_ext": "Solar gains - opaque ext (ISO only)",
        "solar_total": "Solar gains - total",
        "transmission_loss": "Transmission losses",
        "ventilation_gain": "Ventilation gains",
        "ventilation_loss": "Ventilation losses",
    }

    def _side_by_side_table(df_long: pd.DataFrame, index_cols: list[str]) -> pd.DataFrame:
        if df_long.empty:
            return pd.DataFrame(columns=index_cols + ["EnergyPlus_kWh", "ISO_52016_kWh", "Diff_EP_minus_ISO_kWh"])

        wide = (
            df_long.pivot_table(
                index=index_cols,
                columns="model",
                values="energy_kWh",
                aggfunc="sum",
            )
            .reset_index()
            .rename_axis(columns=None)
        )
        if "EnergyPlus" not in wide.columns:
            wide["EnergyPlus"] = 0.0
        if "ISO 52016" not in wide.columns:
            wide["ISO 52016"] = 0.0
        wide["Diff_EP_minus_ISO"] = wide["EnergyPlus"] - wide["ISO 52016"]
        if "category" in wide.columns:
            wide["category"] = wide["category"].map(lambda v: category_labels.get(str(v), str(v)))
        rename_map = {
            "EnergyPlus": "EnergyPlus_kWh",
            "ISO 52016": "ISO_52016_kWh",
            "Diff_EP_minus_ISO": "Diff_EP_minus_ISO_kWh",
        }
        wide = wide.rename(columns=rename_map)
        energy_cols = ["EnergyPlus_kWh", "ISO_52016_kWh", "Diff_EP_minus_ISO_kWh"]
        for col in energy_cols:
            wide[col] = pd.to_numeric(wide[col], errors="coerce").fillna(0.0).round(3)
        return wide

    total_cmp = _side_by_side_table(total_df, ["category"])
    monthly_cmp = _side_by_side_table(monthly_df, ["month", "category"])

    fig_total = go.Figure()
    for model in ("EnergyPlus", "ISO 52016"):
        dfm = total_df[total_df["model"] == model].copy()
        fig_total.add_trace(
            go.Bar(
                x=[category_labels.get(c, c) for c in dfm["category"]],
                y=dfm["energy_kWh"],
                name=model,
            )
        )
    fig_total.update_layout(
        barmode="group",
        template="plotly_white",
        title="Summer totals by category",
        yaxis_title="kWh",
        height=520,
    )

    monthly_categories = [
        "internal",
        "solar_window",
        "transmission_loss",
        "ventilation_gain",
        "ventilation_loss",
    ]
    fig_monthly = make_subplots(
        rows=3,
        cols=2,
        subplot_titles=[category_labels[c] for c in monthly_categories] + [category_labels["solar_opaque_ext"]],
        vertical_spacing=0.12,
        horizontal_spacing=0.08,
    )
    positions = {
        "internal": (1, 1),
        "solar_window": (1, 2),
        "transmission_loss": (2, 1),
        "ventilation_gain": (2, 2),
        "ventilation_loss": (3, 1),
        "solar_opaque_ext": (3, 2),
    }
    for cat, (r, c) in positions.items():
        cat_df = monthly_df[monthly_df["category"] == cat].copy()
        for model in ("EnergyPlus", "ISO 52016"):
            model_df = cat_df[cat_df["model"] == model].copy()
            if model_df.empty:
                continue
            fig_monthly.add_trace(
                go.Bar(
                    x=model_df["month"],
                    y=model_df["energy_kWh"],
                    name=model,
                    legendgroup=model,
                    showlegend=(cat == "internal"),
                ),
                row=r,
                col=c,
            )
    fig_monthly.update_layout(
        barmode="group",
        template="plotly_white",
        title="Monthly summer comparison",
        height=1100,
    )
    for r in range(1, 4):
        for c in range(1, 3):
            fig_monthly.update_yaxes(title_text="kWh", row=r, col=c)

    notes_html = (
        "<p><b>Notes</b></p>"
        "<ul>"
        "<li>EnergyPlus internal gains are shown using the configured ISO internal-gain input as common reference, because this CSV does not expose direct hourly internal-gain outputs.</li>"
        "<li>EnergyPlus solar gains are based on window heat gains available in the CSV.</li>"
        "<li>ISO transmission losses use directly exported inside-face opaque fluxes when available; otherwise the script falls back to a U*A*DeltaT reconstruction.</li>"
        "<li>ISO solar gains include both window and opaque external absorbed solar; the opaque component is shown separately because no equivalent direct output is available in this EnergyPlus CSV.</li>"
        "</ul>"
    )

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Summer drivers EnergyPlus vs ISO</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;}"
        "table{border-collapse:collapse;}th,td{padding:6px 8px;border:1px solid #ddd;}"
        "th{background:#f5f5f5;}</style></head><body>"
        "<h1>Summer drivers comparison: EnergyPlus vs ISO 52016</h1>"
        + notes_html
        + fig_total.to_html(include_plotlyjs="cdn", full_html=False)
        + fig_monthly.to_html(include_plotlyjs=False, full_html=False)
        + "<h2>ISO summer summary</h2>"
        + iso_summary.to_html(index=False, border=0)
        + "<h2>Summer totals</h2>"
        + total_cmp.to_html(index=False, border=0)
        + "<h2>Monthly totals</h2>"
        + monthly_cmp.to_html(index=False, border=0)
        + "</body></html>"
    )
    out_html.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()

    ep_csv = Path(args.energyplus_csv).expanduser().resolve()
    iso_csv = Path(args.iso_csv).expanduser().resolve()
    example_py = Path(args.example_py).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not ep_csv.exists():
        raise FileNotFoundError(f"CSV EnergyPlus non trovato: {ep_csv}")
    if not iso_csv.exists():
        raise FileNotFoundError(f"CSV ISO non trovato: {iso_csv}")
    if not example_py.exists():
        raise FileNotFoundError(f"File example non trovato: {example_py}")

    weather_file = None
    if args.weather_source == "epw":
        wf = Path(args.weather_file).expanduser().resolve()
        if not wf.exists():
            raise FileNotFoundError(f"EPW non trovato: {wf}")
        weather_file = str(wf)

    date_from = pd.Timestamp(args.date_from)
    date_to = pd.Timestamp(args.date_to) + pd.Timedelta(hours=23)

    building_object = load_building_object_from_python(example_py)
    hourly_iso = _filter_period(_load_iso_hourly(iso_csv), date_from, date_to)
    hourly_ep = _filter_period(_load_energyplus_hourly(ep_csv, year=args.year), date_from, date_to)
    if hourly_iso.empty:
        raise ValueError("Il CSV ISO non contiene dati nel periodo selezionato.")
    if hourly_ep.empty:
        raise ValueError("Il CSV EnergyPlus non contiene dati nel periodo selezionato.")

    iso_cat, iso_summary = build_iso_category_frame(
        building_object=building_object,
        hourly_iso=hourly_iso,
        weather_source=args.weather_source,
        weather_file=weather_file,
    )
    ep_cat = build_energyplus_category_frame(
        df_ep=hourly_ep,
        weather_file=weather_file,
        year=args.year,
        internal_reference=iso_cat["internal_W"],
    )

    monthly_df, total_df = build_comparison_tables(ep_cat, iso_cat)

    out_hourly_iso = out_dir / f"{args.out_prefix}_iso_hourly.csv"
    out_hourly_ep = out_dir / f"{args.out_prefix}_energyplus_hourly.csv"
    out_monthly = out_dir / f"{args.out_prefix}_monthly.csv"
    out_total = out_dir / f"{args.out_prefix}_totals.csv"
    out_html = out_dir / f"{args.out_prefix}.html"

    iso_cat.to_csv(out_hourly_iso)
    ep_cat.to_csv(out_hourly_ep)
    monthly_df.to_csv(out_monthly, index=False)
    total_df.to_csv(out_total, index=False)
    build_html_report(out_html, monthly_df, total_df, iso_summary)

    print(f"[ok] ISO hourly   : {out_hourly_iso}")
    print(f"[ok] EP hourly    : {out_hourly_ep}")
    print(f"[ok] Monthly CSV  : {out_monthly}")
    print(f"[ok] Totals CSV   : {out_total}")
    print(f"[ok] HTML report  : {out_html}")


if __name__ == "__main__":
    main()
