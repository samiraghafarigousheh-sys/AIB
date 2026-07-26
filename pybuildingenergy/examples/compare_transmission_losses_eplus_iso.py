
#!/usr/bin/env python3
"""Compare transmission losses (walls/roof/ground/windows) between EnergyPlus and ISO multizone.

Outputs:
- hourly CSV with transmission loss power [W]
- monthly CSV with transmission loss energy [kWh]
- annual CSV summary [kWh]
- HTML report with interactive plots
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pybuildingenergy.source.utils import ISO52016  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Confronta le perdite per trasmissione (muri, tetto, terreno, finestre) "
            "tra output EnergyPlus e modello ISO multizone."
        )
    )
    parser.add_argument(
        "--energyplus-csv",
        default=str(SCRIPT_DIR / "two_zone_ideal_24_2_fixedout.csv"),
        help="Percorso CSV output EnergyPlus.",
    )
    parser.add_argument(
        "--iso-csv",
        default=str(PROJECT_ROOT / "result_test" / "multizone_v1_hourly.csv"),
        help="Percorso CSV hourly ISO multizone.",
    )
    parser.add_argument(
        "--epw-path",
        default=str(SCRIPT_DIR / "2020_Milan.epw"),
        help="Percorso EPW usato per il run.",
    )
    parser.add_argument(
        "--multizone-example-py",
        default=str(SCRIPT_DIR / "multizone_free_floating_example.py"),
        help="Script Python che contiene il building_object multizone.",
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
        default="transmission_losses_eplus_vs_iso",
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

    # Hourly E+ output is typically end-of-interval. Shift to interval start.
    ts = ts - pd.Timedelta(hours=1)
    return pd.DatetimeIndex(ts)


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


def read_epw_drybulb(epw_path: Path, year: int = 2020) -> pd.Series:
    rows: List[Tuple[pd.Timestamp, float]] = []
    with epw_path.open("r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i < 8:
                continue
            vals = [v.strip() for v in line.strip().split(",")]
            if len(vals) < 7:
                continue
            try:
                month = int(vals[1])
                day = int(vals[2])
                hour = int(vals[3])  # 1..24 end-of-hour
                dry_bulb = float(vals[6])
            except Exception:
                continue
            hour0 = 0 if hour == 24 else hour
            ts = pd.Timestamp(year=year, month=month, day=day, hour=hour0)
            if hour == 24:
                ts = ts + pd.Timedelta(days=1)
            ts = ts - pd.Timedelta(hours=1)
            rows.append((ts, dry_bulb))

    if not rows:
        raise ValueError(f"Impossibile leggere T esterna da EPW: {epw_path}")

    out = pd.Series([v for _, v in rows], index=pd.DatetimeIndex([t for t, _ in rows]), name="T_out_C")
    out = out[~out.index.duplicated(keep="first")].sort_index()
    return out


def detect_multizone_time_column(columns: Iterable[str]) -> str:
    cols = list(columns)
    for candidate in ("time(local)", "time", "datetime", "timestamp", "Date/Time"):
        if candidate in cols:
            return candidate
    for c in cols:
        cl = c.lower()
        if "time" in cl or "date" in cl:
            return c
    raise KeyError("Impossibile rilevare la colonna tempo nel CSV ISO.")


def load_building_object(example_py: Path) -> dict:
    spec = importlib.util.spec_from_file_location("multizone_example", str(example_py))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Impossibile caricare modulo: {example_py}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "building_object"):
        raise AttributeError(f"{example_py} non espone 'building_object'.")

    bui = copy.deepcopy(module.building_object)

    if hasattr(module, "apply_energyplus_infiltration_equivalence"):
        try:
            module.apply_energyplus_infiltration_equivalence(bui)
        except Exception:
            pass

    return bui


def classify_eplus_surface(surface_name: str) -> Optional[str]:
    s = surface_name.upper()
    if "_INT" in s:
        return None
    if "ROOF" in s:
        return "roof"
    if "FLOOR" in s:
        return "ground"
    if "WALL" in s:
        return "wall"
    return None


def classify_iso_surface(surf: dict) -> Optional[str]:
    typ = str(surf.get("type", "")).lower()
    bnd = str(surf.get("boundary", "")).upper()

    if typ == "transparent" and bnd == "OUTDOORS":
        return "window"
    if typ != "opaque":
        return None

    name = str(surf.get("name", "")).upper()
    ori = surf.get("orientation", {}) or {}
    tilt = ori.get("tilt", None)
    tilt_f = None
    try:
        tilt_f = float(tilt) if tilt is not None else None
    except Exception:
        tilt_f = None

    if bnd == "GROUND":
        return "ground"
    if bnd != "OUTDOORS":
        return None

    if "ROOF" in name:
        return "roof"
    if "WALL" in name:
        return "wall"
    if tilt_f is not None:
        if abs(tilt_f) < 45.0:
            return "roof"
        if abs(tilt_f - 90.0) < 20.0:
            return "wall"
    return None


def classify_iso_surface_token(surface_token: str) -> Optional[str]:
    s = str(surface_token).lower()
    if "roof" in s:
        return "roof"
    if "floor" in s or "slab" in s or "ground" in s:
        return "ground"
    if "wall" in s:
        return "wall"
    return None


def build_eplus_transmission_losses(df_ep: pd.DataFrame, dt_s: float) -> pd.DataFrame:
    cols = [
        c
        for c in df_ep.columns
        if "Surface Inside Face Conduction Heat Transfer Energy [J](Hourly)" in c
    ]
    if not cols:
        raise ValueError("Nel CSV EnergyPlus non trovo colonne 'Surface Inside Face Conduction Heat Transfer Energy'.")

    out = pd.DataFrame(index=df_ep.index)
    out["eplus_wall_W"] = 0.0
    out["eplus_roof_W"] = 0.0
    out["eplus_ground_W"] = 0.0
    out["eplus_window_W"] = 0.0

    for c in cols:
        surface = c.split(":", 1)[0].strip()
        cat = classify_eplus_surface(surface)
        if cat is None:
            continue
        s_j = pd.to_numeric(df_ep[c], errors="coerce").fillna(0.0)
        # On inside-face conduction outputs, negative indicates zone heat loss.
        loss_w = (-s_j / max(dt_s, 1e-9)).clip(lower=0.0)
        out[f"eplus_{cat}_W"] += loss_w

    # Window transmission losses are available directly as loss energy [J].
    win_loss_cols = [
        c for c in df_ep.columns
        if "surface window heat loss energy [j](hourly)" in c.lower()
    ]
    for c in win_loss_cols:
        s_j = pd.to_numeric(df_ep[c], errors="coerce").fillna(0.0)
        out["eplus_window_W"] += (s_j / max(dt_s, 1e-9)).clip(lower=0.0)

    return out


def build_iso_transmission_losses(
    df_iso: pd.DataFrame,
    building_object: dict,
    t_out: pd.Series,
    theta_gr_monthly: np.ndarray,
) -> pd.DataFrame:
    out = pd.DataFrame(index=df_iso.index)
    out["iso_wall_W"] = 0.0
    out["iso_roof_W"] = 0.0
    out["iso_ground_W"] = 0.0
    out["iso_window_W"] = 0.0

    t_out_al = pd.to_numeric(t_out.reindex(df_iso.index), errors="coerce").interpolate(limit_direction="both")
    t_gr_series = pd.Series(
        [float(theta_gr_monthly[int(ts.month) - 1]) for ts in df_iso.index],
        index=df_iso.index,
        dtype=float,
    )

    exported_opaque_categories = set()
    opaque_inside_cols = [c for c in df_iso.columns if c.startswith("Q_opaque_inside_surface_")]
    for c in opaque_inside_cols:
        token = c.removeprefix("Q_opaque_inside_surface_")
        cat = classify_iso_surface_token(token)
        if cat not in {"wall", "roof", "ground"}:
            continue
        q_in_w = pd.to_numeric(df_iso[c], errors="coerce").fillna(0.0)
        out[f"iso_{cat}_W"] += (-q_in_w).clip(lower=0.0)
        exported_opaque_categories.add(cat)

    surfaces = building_object.get("building_surface", [])
    for surf in surfaces:
        cat = classify_iso_surface(surf)
        if cat is None:
            continue
        if cat in exported_opaque_categories and cat != "window":
            continue

        zone = str(surf.get("zone", "")).strip()
        t_air_col = f"T_air_{zone}"
        if t_air_col not in df_iso.columns:
            continue

        try:
            ua = float(surf.get("u_value", 0.0)) * float(surf.get("area", 0.0))
        except Exception:
            ua = 0.0
        if not np.isfinite(ua) or ua <= 0.0:
            continue

        t_air = pd.to_numeric(df_iso[t_air_col], errors="coerce").interpolate(limit_direction="both")
        if cat == "ground":
            d_t = t_air - t_gr_series
        else:
            d_t = t_air - t_out_al

        loss_w = (ua * d_t).clip(lower=0.0)
        out[f"iso_{cat}_W"] += loss_w

    return out


def monthly_kwh(df_w: pd.DataFrame, dt_s: float) -> pd.DataFrame:
    return (df_w.resample("ME").sum() * dt_s / 3.6e6)


def annual_kwh(df_w: pd.DataFrame, dt_s: float) -> pd.Series:
    return (df_w.sum() * dt_s / 3.6e6)


def write_html_report(
    out_html: Path,
    hourly: pd.DataFrame,
    monthly: pd.DataFrame,
    annual: pd.DataFrame,
) -> None:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:
        raise RuntimeError(f"plotly non disponibile: {exc}")

    fig_h = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=(
            "Muri - Perdite per trasmissione [W]",
            "Tetto - Perdite per trasmissione [W]",
            "Terreno - Perdite per trasmissione [W]",
            "Finestre - Perdite per trasmissione [W]",
        ),
    )

    categories = ["wall", "roof", "ground", "window"]
    row = 1
    for cat in categories:
        fig_h.add_trace(
            go.Scatter(
                x=hourly.index,
                y=hourly[f"eplus_{cat}_W"],
                name=f"EnergyPlus {cat}",
                mode="lines",
                line={"width": 1.3},
                legendgroup=f"{cat}",
                showlegend=(row == 1),
            ),
            row=row,
            col=1,
        )
        fig_h.add_trace(
            go.Scatter(
                x=hourly.index,
                y=hourly[f"iso_{cat}_W"],
                name=f"ISO {cat}",
                mode="lines",
                line={"width": 1.3, "dash": "dash"},
                legendgroup=f"{cat}",
                showlegend=(row == 1),
            ),
            row=row,
            col=1,
        )
        row += 1

    fig_h.update_layout(
        template="plotly_white",
        hovermode="x unified",
        height=1220,
        title="Confronto orario perdite per trasmissione: EnergyPlus vs ISO",
    )
    fig_h.update_yaxes(title_text="W")

    fig_m = go.Figure()
    for cat in categories:
        fig_m.add_trace(
            go.Bar(
                x=monthly.index,
                y=monthly[f"eplus_{cat}_W"],
                name=f"EnergyPlus {cat}",
            )
        )
        fig_m.add_trace(
            go.Bar(
                x=monthly.index,
                y=monthly[f"iso_{cat}_W"],
                name=f"ISO {cat}",
            )
        )
    fig_m.update_layout(
        template="plotly_white",
        barmode="group",
        title="Energia mensile perdite per trasmissione [kWh]",
        xaxis_title="Mese",
        yaxis_title="kWh",
        height=560,
    )

    sections: List[str] = []
    sections.append("<h1>Confronto Perdite per Trasmissione (EnergyPlus vs ISO)</h1>")
    sections.append(
        "<p><i>ISO uses directly exported inside-face opaque fluxes when available; otherwise it falls back to a U*A*DeltaT reconstruction.</i></p>"
    )
    sections.append(fig_h.to_html(include_plotlyjs="cdn", full_html=False))
    sections.append(fig_m.to_html(include_plotlyjs=False, full_html=False))
    sections.append("<h2>Riepilogo Annuale [kWh]</h2>")
    sections.append(annual.to_html(index=False, border=0))
    sections.append("<h2>Riepilogo Mensile [kWh]</h2>")
    sections.append(monthly.reset_index().rename(columns={"index": "month"}).to_html(index=False, border=0))

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Transmission Losses E+ vs ISO</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;}"
        "table{border-collapse:collapse;}th,td{padding:6px 8px;border:1px solid #ddd;}"
        "th{background:#f5f5f5;}</style></head><body>"
        + "".join(sections)
        + "</body></html>"
    )
    out_html.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ep_csv = Path(args.energyplus_csv).expanduser().resolve()
    iso_csv = Path(args.iso_csv).expanduser().resolve()
    epw_path = Path(args.epw_path).expanduser().resolve()
    example_py = Path(args.multizone_example_py).expanduser().resolve()

    if not ep_csv.exists():
        raise FileNotFoundError(f"CSV EnergyPlus non trovato: {ep_csv}")
    if not iso_csv.exists():
        raise FileNotFoundError(f"CSV ISO non trovato: {iso_csv}")
    if not epw_path.exists():
        raise FileNotFoundError(f"EPW non trovato: {epw_path}")
    if not example_py.exists():
        raise FileNotFoundError(f"Script example non trovato: {example_py}")

    df_ep = pd.read_csv(ep_csv)
    if "Date/Time" not in df_ep.columns:
        raise KeyError("Nel CSV EnergyPlus manca la colonna 'Date/Time'.")
    df_ep.index = parse_energyplus_datetime(df_ep["Date/Time"], year=args.year)
    df_ep = df_ep.loc[~df_ep.index.duplicated(keep="first")].sort_index()
    dt_ep_s = infer_timestep_seconds(df_ep.index, default=3600.0)

    df_iso = pd.read_csv(iso_csv)
    time_col = detect_multizone_time_column(df_iso.columns)
    idx_iso = pd.to_datetime(df_iso[time_col], errors="coerce")
    df_iso = df_iso.loc[idx_iso.notna()].copy()
    df_iso.index = pd.DatetimeIndex(idx_iso[idx_iso.notna()])
    df_iso = df_iso.loc[~df_iso.index.duplicated(keep="first")].sort_index()

    common_idx = df_ep.index.intersection(df_iso.index)
    if len(common_idx) == 0:
        raise ValueError("Nessun timestamp comune tra EnergyPlus e ISO.")

    df_ep = df_ep.reindex(common_idx)
    df_iso = df_iso.reindex(common_idx)

    t_out = read_epw_drybulb(epw_path, year=args.year).reindex(common_idx)

    bui = load_building_object(example_py)
    t_Th = ISO52016().Temp_calculation_of_ground(
        bui,
        path_weather_file=str(epw_path),
        weather_source="epw",
    )
    theta_gr_monthly = np.asarray(t_Th.Theta_gr_ve, dtype=float)

    eplus_losses = build_eplus_transmission_losses(df_ep, dt_s=dt_ep_s)
    iso_losses = build_iso_transmission_losses(
        df_iso,
        building_object=bui,
        t_out=t_out,
        theta_gr_monthly=theta_gr_monthly,
    )

    hourly = pd.concat([eplus_losses, iso_losses], axis=1)
    hourly = hourly.loc[common_idx]

    monthly = monthly_kwh(hourly, dt_s=dt_ep_s)
    annual = annual_kwh(hourly, dt_s=dt_ep_s)
    annual_df = pd.DataFrame(
        {
            "metric": annual.index,
            "annual_kWh": annual.values,
        }
    )

    out_hourly = out_dir / f"{args.out_prefix}_hourly.csv"
    out_monthly = out_dir / f"{args.out_prefix}_monthly_kwh.csv"
    out_annual = out_dir / f"{args.out_prefix}_annual_kwh.csv"
    out_html = out_dir / f"{args.out_prefix}.html"

    hourly.to_csv(out_hourly)
    monthly.to_csv(out_monthly)
    annual_df.to_csv(out_annual, index=False)
    write_html_report(out_html, hourly, monthly, annual_df)

    print(f"[ok] HTML: {out_html}")
    print(f"[ok] CSV hourly: {out_hourly}")
    print(f"[ok] CSV monthly: {out_monthly}")
    print(f"[ok] CSV annual: {out_annual}")


if __name__ == "__main__":
    main()
