#!/usr/bin/env python3
"""Compare infiltration sensible heat exchange: EnergyPlus vs ISO multizone output.

Outputs:
- hourly CSV [W] (zone + total, loss/gain, deltas)
- monthly CSV [kWh]
- summary CSV [kWh]
- HTML interactive report
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Confronta perdite/guadagni sensibili per infiltrazione tra "
            "EnergyPlus (two_zone_ideal_24_2_fixedout.csv) e ISO multizona."
        )
    )
    parser.add_argument(
        "--energyplus-csv",
        default=str(SCRIPT_DIR / "two_zone_ideal_24_2_fixedout.csv"),
        help="CSV output EnergyPlus.",
    )
    parser.add_argument(
        "--iso-hourly-csv",
        default=str(PROJECT_ROOT / "result_test" / "multizone_v1_hourly.csv"),
        help="CSV output orario ISO multizone (es. multizone_v1_hourly.csv).",
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
        help="Cartella output.",
    )
    parser.add_argument(
        "--out-prefix",
        default="infiltration_eplus_vs_iso_multizone",
        help="Prefisso file output.",
    )
    return parser.parse_args()


def parse_energyplus_datetime(series: pd.Series, *, year: int) -> pd.DatetimeIndex:
    raw = series.astype(str).str.strip()
    parts = raw.str.extract(
        r"(?P<month>\d{1,2})/(?P<day>\d{1,2})\s+"
        r"(?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})"
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
    # Hourly EnergyPlus values are usually end-of-interval.
    return pd.DatetimeIndex(ts - pd.Timedelta(hours=1))


def infer_timestep_seconds(index: pd.DatetimeIndex, default: float = 3600.0) -> float:
    if len(index) < 2:
        return float(default)
    dt_s = (
        pd.Series(index)
        .diff()
        .dt.total_seconds()
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    dt_s = dt_s[dt_s > 0]
    if dt_s.empty:
        return float(default)
    return float(dt_s.median())


def rebase_datetime_year(series: pd.Series, target_year: int) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    rebased = pd.to_datetime(
        {
            "year": target_year,
            "month": ts.dt.month,
            "day": ts.dt.day,
            "hour": ts.dt.hour,
            "minute": ts.dt.minute,
            "second": ts.dt.second,
        },
        errors="coerce",
    )
    return pd.Series(rebased, index=series.index)


def detect_iso_time_column(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    for candidate in (
        "time(local)",
        "time",
        "timestamp",
        "datetime",
        "Date/Time",
        "Unnamed: 0",
        "index",
    ):
        if candidate in cols:
            return candidate
    for c in cols:
        lc = str(c).lower()
        if "time" in lc or "date" in lc:
            return c

    # Fallback: pick the column mostly parseable as datetime.
    best_col = None
    best_ratio = -1.0
    for c in cols:
        parsed = pd.to_datetime(df[c], errors="coerce")
        ratio = float(parsed.notna().mean())
        if ratio > best_ratio:
            best_ratio = ratio
            best_col = c
    if best_col is not None and best_ratio >= 0.8:
        return best_col

    raise KeyError("Impossibile rilevare colonna tempo nel CSV ISO.")


def _find_infiltration_zones_ep(columns) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for c in columns:
        cl = c.lower()
        if "zone infiltration sensible heat loss energy [j](hourly)" in cl:
            zone = c.split(":", 1)[0].strip()
            out.setdefault(zone, {})["loss"] = c
        elif "zone infiltration sensible heat gain energy [j](hourly)" in cl:
            zone = c.split(":", 1)[0].strip()
            out.setdefault(zone, {})["gain"] = c
    return out


def build_report(
    out_html: Path,
    hourly: pd.DataFrame,
    monthly: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:
        raise RuntimeError(f"plotly non disponibile: {exc}") from exc

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "Infiltration losses [W] — Total",
            "Infiltration gains [W] — Total",
            "Delta losses ISO - EnergyPlus [W] — Total",
        ),
    )

    fig.add_trace(
        go.Scatter(
            x=hourly.index,
            y=hourly["EP_loss_tot_W"],
            mode="lines",
            name="EP loss tot",
            line={"width": 1.2},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=hourly.index,
            y=hourly["ISO_loss_tot_W"],
            mode="lines",
            name="ISO loss tot",
            line={"width": 1.2, "dash": "dash"},
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=hourly.index,
            y=hourly["EP_gain_tot_W"],
            mode="lines",
            name="EP gain tot",
            line={"width": 1.2},
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=hourly.index,
            y=hourly["ISO_gain_tot_W"],
            mode="lines",
            name="ISO gain tot",
            line={"width": 1.2, "dash": "dash"},
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=hourly.index,
            y=hourly["delta_loss_tot_W_ISO_minus_EP"],
            mode="lines",
            name="Delta loss (ISO-EP)",
            line={"width": 1.2, "color": "#C2185B"},
        ),
        row=3,
        col=1,
    )

    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        title="Confronto infiltrazione sensibile: EnergyPlus vs ISO multizona",
        height=1040,
    )
    fig.update_yaxes(title_text="W")

    fig_month = go.Figure()
    fig_month.add_trace(
        go.Bar(x=monthly.index, y=monthly["EP_loss_tot_W"], name="EP loss [kWh]")
    )
    fig_month.add_trace(
        go.Bar(x=monthly.index, y=monthly["ISO_loss_tot_W"], name="ISO loss [kWh]")
    )
    fig_month.update_layout(
        template="plotly_white",
        barmode="group",
        title="Energia mensile infiltrazione - perdite [kWh]",
        xaxis_title="Mese",
        yaxis_title="kWh",
        height=460,
    )

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Infiltration EP vs ISO</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;}"
        "table{border-collapse:collapse;}th,td{padding:6px 8px;border:1px solid #ddd;}"
        "th{background:#f5f5f5;}</style></head><body>"
        "<h1>Confronto infiltrazione sensibile (EnergyPlus vs ISO multizona)</h1>"
        + fig.to_html(include_plotlyjs="cdn", full_html=False)
        + fig_month.to_html(include_plotlyjs=False, full_html=False)
        + "<h2>Riepilogo annuale [kWh]</h2>"
        + summary.to_html(index=False, border=0)
        + "<h2>Riepilogo mensile [kWh]</h2>"
        + monthly.reset_index().rename(columns={"index": "month"}).to_html(index=False, border=0)
        + "</body></html>"
    )
    out_html.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()

    ep_csv = Path(args.energyplus_csv).expanduser().resolve()
    iso_csv = Path(args.iso_hourly_csv).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not ep_csv.exists():
        raise FileNotFoundError(f"CSV EnergyPlus non trovato: {ep_csv}")
    if not iso_csv.exists():
        raise FileNotFoundError(f"CSV ISO non trovato: {iso_csv}")

    df_ep = pd.read_csv(ep_csv)
    if "Date/Time" not in df_ep.columns:
        raise KeyError("Nel CSV EnergyPlus manca la colonna 'Date/Time'.")
    df_ep.index = parse_energyplus_datetime(df_ep["Date/Time"], year=args.year)
    df_ep = df_ep.loc[~df_ep.index.duplicated(keep="first")].sort_index()
    dt_s = infer_timestep_seconds(df_ep.index, default=3600.0)

    ep_infil_cols = _find_infiltration_zones_ep(df_ep.columns)
    if len(ep_infil_cols) == 0:
        raise KeyError("Nessuna colonna infiltrazione trovata nel CSV EnergyPlus.")

    df_iso = pd.read_csv(iso_csv)
    time_col = detect_iso_time_column(df_iso)
    idx_iso = pd.to_datetime(df_iso[time_col], errors="coerce")
    df_iso = df_iso.loc[idx_iso.notna()].copy()
    df_iso.index = pd.DatetimeIndex(idx_iso[idx_iso.notna()])
    if len(df_iso.index) > 0:
        iso_years = sorted(set(int(y) for y in df_iso.index.year))
        if len(iso_years) == 1 and iso_years[0] != int(args.year):
            rebased = rebase_datetime_year(pd.Series(df_iso.index, index=df_iso.index), int(args.year))
            if float(rebased.notna().mean()) >= 0.9:
                df_iso.index = pd.DatetimeIndex(rebased.values)
    df_iso = df_iso.loc[~df_iso.index.duplicated(keep="first")].sort_index()

    # Map EP zones to ISO zones by sorted order (same count expected for this benchmark).
    iso_zones = sorted([c.removeprefix("T_air_") for c in df_iso.columns if c.startswith("T_air_")])
    ep_zones = sorted(ep_infil_cols.keys())
    if len(iso_zones) == 0:
        raise KeyError("Nel CSV ISO non trovo colonne T_air_<zona>.")
    if len(ep_zones) != len(iso_zones):
        raise ValueError(
            f"Numero zone EP ({len(ep_zones)}) diverso da ISO ({len(iso_zones)}). "
            "Aggiorna la mappatura zone nello script."
        )
    zone_map = dict(zip(ep_zones, iso_zones))

    out_temp_col = "Environment:Site Outdoor Air Drybulb Temperature [C](Hourly)"
    if out_temp_col not in df_ep.columns:
        raise KeyError(f"Nel CSV EnergyPlus manca '{out_temp_col}'.")
    t_out_ep = pd.to_numeric(df_ep[out_temp_col], errors="coerce")

    common_idx = df_ep.index.intersection(df_iso.index)
    if len(common_idx) == 0:
        raise ValueError("Nessun timestamp comune tra CSV EnergyPlus e CSV ISO.")
    df_ep = df_ep.reindex(common_idx)
    df_iso = df_iso.reindex(common_idx)
    t_out = pd.to_numeric(t_out_ep.reindex(common_idx), errors="coerce").interpolate(limit_direction="both")

    hourly = pd.DataFrame(index=common_idx)

    for ep_zone, iso_zone in zone_map.items():
        c_loss = ep_infil_cols[ep_zone].get("loss")
        c_gain = ep_infil_cols[ep_zone].get("gain")
        ep_loss = (
            pd.to_numeric(df_ep[c_loss], errors="coerce").fillna(0.0) / max(dt_s, 1e-9)
            if c_loss is not None else pd.Series(0.0, index=common_idx)
        )
        ep_gain = (
            pd.to_numeric(df_ep[c_gain], errors="coerce").fillna(0.0) / max(dt_s, 1e-9)
            if c_gain is not None else pd.Series(0.0, index=common_idx)
        )

        t_air_col = f"T_air_{iso_zone}"
        h_ve_col = f"H_ve_{iso_zone}"
        if t_air_col not in df_iso.columns or h_ve_col not in df_iso.columns:
            raise KeyError(f"Nel CSV ISO mancano colonne richieste: '{t_air_col}' o '{h_ve_col}'.")

        t_air = pd.to_numeric(df_iso[t_air_col], errors="coerce").interpolate(limit_direction="both")
        h_ve = pd.to_numeric(df_iso[h_ve_col], errors="coerce").fillna(0.0).clip(lower=0.0)
        q_vent = h_ve * (t_air - t_out)
        iso_loss = q_vent.clip(lower=0.0)
        iso_gain = (-q_vent.clip(upper=0.0))

        hourly[f"EP_loss_{iso_zone}_W"] = ep_loss
        hourly[f"ISO_loss_{iso_zone}_W"] = iso_loss
        hourly[f"EP_gain_{iso_zone}_W"] = ep_gain
        hourly[f"ISO_gain_{iso_zone}_W"] = iso_gain
        hourly[f"delta_loss_{iso_zone}_W_ISO_minus_EP"] = iso_loss - ep_loss
        hourly[f"delta_gain_{iso_zone}_W_ISO_minus_EP"] = iso_gain - ep_gain

    hourly["EP_loss_tot_W"] = hourly[[c for c in hourly.columns if c.startswith("EP_loss_") and c.endswith("_W")]].sum(axis=1)
    hourly["ISO_loss_tot_W"] = hourly[[c for c in hourly.columns if c.startswith("ISO_loss_") and c.endswith("_W")]].sum(axis=1)
    hourly["EP_gain_tot_W"] = hourly[[c for c in hourly.columns if c.startswith("EP_gain_") and c.endswith("_W")]].sum(axis=1)
    hourly["ISO_gain_tot_W"] = hourly[[c for c in hourly.columns if c.startswith("ISO_gain_") and c.endswith("_W")]].sum(axis=1)
    hourly["delta_loss_tot_W_ISO_minus_EP"] = hourly["ISO_loss_tot_W"] - hourly["EP_loss_tot_W"]
    hourly["delta_gain_tot_W_ISO_minus_EP"] = hourly["ISO_gain_tot_W"] - hourly["EP_gain_tot_W"]

    def annual_kwh(series_w: pd.Series) -> float:
        return float(series_w.sum() * dt_s / 3.6e6)

    rows = []
    iso_zone_list = sorted(iso_zones)
    for z in iso_zone_list + ["tot"]:
        suf = "tot" if z == "tot" else z
        rows.append(
            {
                "zone": z,
                "EP_loss_kWh": annual_kwh(hourly[f"EP_loss_{suf}_W"]),
                "ISO_loss_kWh": annual_kwh(hourly[f"ISO_loss_{suf}_W"]),
                "delta_loss_kWh_ISO_minus_EP": annual_kwh(hourly[f"ISO_loss_{suf}_W"] - hourly[f"EP_loss_{suf}_W"]),
                "EP_gain_kWh": annual_kwh(hourly[f"EP_gain_{suf}_W"]),
                "ISO_gain_kWh": annual_kwh(hourly[f"ISO_gain_{suf}_W"]),
                "delta_gain_kWh_ISO_minus_EP": annual_kwh(hourly[f"ISO_gain_{suf}_W"] - hourly[f"EP_gain_{suf}_W"]),
            }
        )
    summary = pd.DataFrame(rows)

    monthly = (hourly[["EP_loss_tot_W", "ISO_loss_tot_W", "EP_gain_tot_W", "ISO_gain_tot_W"]] * dt_s / 3.6e6).resample("ME").sum()
    monthly["delta_loss_kWh_ISO_minus_EP"] = monthly["ISO_loss_tot_W"] - monthly["EP_loss_tot_W"]
    monthly["delta_gain_kWh_ISO_minus_EP"] = monthly["ISO_gain_tot_W"] - monthly["EP_gain_tot_W"]

    out_hourly = out_dir / f"{args.out_prefix}_hourly.csv"
    out_summary = out_dir / f"{args.out_prefix}_summary_kwh.csv"
    out_monthly = out_dir / f"{args.out_prefix}_monthly_kwh.csv"
    out_html = out_dir / f"{args.out_prefix}.html"

    hourly.to_csv(out_hourly)
    summary.to_csv(out_summary, index=False)
    monthly.to_csv(out_monthly)
    build_report(out_html, hourly, monthly, summary)

    print(f"[ok] Hourly CSV: {out_hourly}")
    print(f"[ok] Summary CSV: {out_summary}")
    print(f"[ok] Monthly CSV: {out_monthly}")
    print(f"[ok] HTML: {out_html}")
    print("[summary]")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
