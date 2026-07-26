#!/usr/bin/env python3
"""Plot zone-by-zone heating and temperatures (EP vs multizone V1)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd

from compare_energyplus_multizone_temperatures import (
    _extract_annual_energy_j_optional,
    _extract_energyplus_hourly_power,
    _infer_timestep_seconds,
    detect_energyplus_temperature_columns,
    detect_multizone_temperature_columns,
    detect_multizone_time_column,
    parse_energyplus_datetime,
    parse_zone_map,
    rebase_datetime_year,
    resolve_multizone_csv,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera un HTML con due grafici per zona: "
            "temperature aria (EP vs multizone + esterna) "
            "e consumi heating (EP vs multizone metodo 1)."
        )
    )
    parser.add_argument(
        "--energyplus-csv",
        default=str(SCRIPT_DIR / "two_zone_ideal_24_2_fixedout.csv"),
        help="Percorso CSV EnergyPlus.",
    )
    parser.add_argument(
        "--multizone-csv",
        default="",
        help=(
            "Percorso CSV multizone V1. Se omesso: examples/multizone_v1_hourly.csv "
            "oppure result_test/multizone_v1_hourly.csv."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2020,
        help="Anno base usato per interpretare Date/Time EnergyPlus.",
    )
    parser.add_argument(
        "--no-ep-shift",
        action="store_true",
        help=(
            "Disabilita lo shift di -1h su Date/Time EnergyPlus "
            "(utile se i timestamp sono gia in inizio intervallo)."
        ),
    )
    parser.add_argument(
        "--multizone-time-column",
        default="",
        help="Nome colonna tempo nel CSV multizone (default: autodetect).",
    )
    parser.add_argument(
        "--zone-map",
        nargs="*",
        default=[],
        metavar="MZ=EP",
        help=(
            "Mappa zone esplicita. Esempio: --zone-map Z1=ZONEA_LIVING Z2=ZONEB_BEDROOM. "
            "Se omesso, mappatura automatica per ordinamento."
        ),
    )
    parser.add_argument(
        "--out-html",
        default=str(SCRIPT_DIR / "energyplus_vs_multizone_consumi_temperatures.html"),
        help="Percorso file HTML output.",
    )
    return parser.parse_args()


def detect_outdoor_temperature_column(columns: Iterable[str]) -> str:
    candidates = [
        "Environment:Site Outdoor Air Drybulb Temperature [C](Hourly)",
        "Site Outdoor Air Drybulb Temperature [C](Hourly)",
        "Outdoor Dry Bulb [C](Hourly)",
        "Outdoor Air Drybulb Temperature [C](Hourly)",
    ]
    cols = list(columns)
    for candidate in candidates:
        if candidate in cols:
            return candidate

    for col in cols:
        name = col.lower()
        if "outdoor" in name and "drybulb" in name and "temperature" in name:
            return col
    raise KeyError(
        "Nel CSV EnergyPlus non trovo una colonna di temperatura esterna drybulb."
    )


def detect_multizone_hvac_columns(columns: Iterable[str]) -> Dict[str, str]:
    hvac_cols: Dict[str, str] = {}
    for col in columns:
        if col.startswith("Q_HVAC_"):
            hvac_cols[col.removeprefix("Q_HVAC_")] = col
    return hvac_cols


def extract_energyplus_zone_hvac_power(
    df_ep: pd.DataFrame,
    zone_name: str,
    service: str,
    dt_s: float,
) -> tuple[pd.Series | None, str | None]:
    service_token = "heating" if service == "heating" else "cooling"
    zone_token = zone_name.lower()

    patterns = [
        [zone_token, "ideal loads", service_token, "[w]", "(hourly)"],
        [zone_token, "ideal loads", service_token, "[j]", "(hourly)"],
        [zone_token, "air system sensible", service_token, "[w]", "(hourly)"],
        [zone_token, "air system sensible", service_token, "[j]", "(hourly)"],
        [zone_token, "zone", service_token, "rate", "[w]", "(hourly)"],
        [zone_token, "zone", service_token, "energy", "[j]", "(hourly)"],
    ]

    for pattern in patterns:
        for col in df_ep.columns:
            name = col.lower()
            if all(token in name for token in pattern):
                values = pd.to_numeric(df_ep[col], errors="coerce").fillna(0.0)
                if "[j]" in name:
                    values = values / dt_s
                values = values.abs().astype(float)
                return values, col

    return None, None


def save_html_plot(
    out_path: Path,
    df_ep: pd.DataFrame,
    df_mz: pd.DataFrame,
    zone_map: Dict[str, str],
    ep_air_cols: Dict[str, str],
    mz_air_cols: Dict[str, str],
    mz_hvac_cols: Dict[str, str],
    outdoor_col: str,
) -> bool:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception:
        print("[warn] plotly non disponibile, salto output HTML.")
        return False

    dt_s = _infer_timestep_seconds(df_ep.index)
    ep_heat_annual_j = _extract_annual_energy_j_optional(df_ep.reset_index(), "heating")
    ep_heat_w_total, _, _ = _extract_energyplus_hourly_power(
        df_ep, "heating", dt_s, ep_heat_annual_j
    )

    ep_zone_heat: Dict[str, pd.Series] = {}
    ep_zone_source_cols: Dict[str, str] = {}
    for mz_zone, ep_zone in zone_map.items():
        heat_series, heat_col = extract_energyplus_zone_hvac_power(
            df_ep, ep_zone, "heating", dt_s
        )
        if heat_series is not None:
            ep_zone_heat[mz_zone] = heat_series
        ep_zone_source_cols[mz_zone] = heat_col if heat_col is not None else ""

    zone_items = list(zone_map.items())
    if not zone_items:
        raise ValueError("Mappatura zone vuota.")

    fig = make_subplots(
        rows=len(zone_items),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        specs=[[{"secondary_y": True}] for _ in zone_items],
        subplot_titles=[
            f"{mz_zone} vs {ep_zone} | temperature + heating"
            for mz_zone, ep_zone in zone_items
        ],
    )

    outdoor_series = pd.to_numeric(df_ep[outdoor_col], errors="coerce")
    zone_palette = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]
    used_fallback_zones: List[str] = []

    for row, (mz_zone, ep_zone) in enumerate(zone_items, start=1):
        color = zone_palette[(row - 1) % len(zone_palette)]
        t_mz = pd.to_numeric(df_mz[mz_air_cols[mz_zone]], errors="coerce")
        t_ep = pd.to_numeric(df_ep[ep_air_cols[ep_zone]], errors="coerce")
        q_mz_heat = (
            pd.to_numeric(df_mz[mz_hvac_cols[mz_zone]], errors="coerce")
            .fillna(0.0)
            .clip(lower=0.0)
        )

        q_ep_heat = ep_zone_heat.get(mz_zone)
        if q_ep_heat is None:
            q_ep_heat = ep_heat_w_total
            used_fallback_zones.append(mz_zone)

        fig.add_trace(
            go.Scatter(
                x=df_mz.index,
                y=t_mz.to_numpy(),
                mode="lines",
                name=f"T air multizone {mz_zone}",
                legendgroup=f"temp_{mz_zone}",
                line={"color": color, "width": 1.7},
            ),
            row=row,
            col=1,
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=df_ep.index,
                y=t_ep.to_numpy(),
                mode="lines",
                name=f"T air EnergyPlus {ep_zone}",
                legendgroup=f"temp_{mz_zone}",
                line={"color": color, "dash": "dash", "width": 1.7},
            ),
            row=row,
            col=1,
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=df_ep.index,
                y=outdoor_series.to_numpy(),
                mode="lines",
                name=f"T esterna ({ep_zone})",
                legendgroup="t_out",
                showlegend=(row == 1),
                line={"color": "#111111", "width": 1.4},
            ),
            row=row,
            col=1,
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=df_mz.index,
                y=q_mz_heat.to_numpy(),
                mode="lines",
                name=f"Heating multizone metodo 1 {mz_zone}",
                legendgroup=f"heat_{mz_zone}",
                line={"color": color, "width": 2.2},
            ),
            row=row,
            col=1,
            secondary_y=True,
        )
        fig.add_trace(
            go.Scatter(
                x=df_ep.index,
                y=q_ep_heat.to_numpy(),
                mode="lines",
                name=(
                    f"Heating EnergyPlus {ep_zone}"
                    if mz_zone not in used_fallback_zones
                    else f"Heating EnergyPlus totale (fallback) {mz_zone}"
                ),
                legendgroup=f"heat_{mz_zone}",
                line={"color": color, "dash": "dot", "width": 2.2},
            ),
            row=row,
            col=1,
            secondary_y=True,
        )

    fig.update_layout(
        title=(
            "Confronto per zona: temperature interne/esterna e consumi heating "
            "(EnergyPlus vs multizone metodo 1)"
        ),
        template="plotly_white",
        hovermode="x unified",
        height=max(760, 460 * len(zone_items)),
    )
    for row in range(1, len(zone_items) + 1):
        fig.update_yaxes(title_text="Temperature [C]", row=row, col=1, secondary_y=False)
        fig.update_yaxes(title_text="Heating [W]", row=row, col=1, secondary_y=True)
    fig.update_xaxes(title_text="Time", row=len(zone_items), col=1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(out_path, include_plotlyjs="cdn")
    print("EnergyPlus heating columns by zone:")
    for mz_zone, ep_zone in zone_map.items():
        col = ep_zone_source_cols.get(mz_zone, "")
        if col:
            print(f"  - {mz_zone} ({ep_zone}): {col}")
        else:
            print(f"  - {mz_zone} ({ep_zone}): not found -> fallback total heating")
    if used_fallback_zones:
        print(
            "Heating fallback (total EnergyPlus) used for zones: "
            f"{sorted(set(used_fallback_zones))}"
        )

    return True


def main() -> None:
    args = parse_args()
    ep_path = Path(args.energyplus_csv).expanduser().resolve()
    mz_path = resolve_multizone_csv(args.multizone_csv)
    out_path = Path(args.out_html).expanduser().resolve()

    if not ep_path.exists():
        raise FileNotFoundError(f"CSV EnergyPlus non trovato: {ep_path}")

    df_ep_raw = pd.read_csv(ep_path)
    if "Date/Time" not in df_ep_raw.columns:
        raise KeyError("Colonna 'Date/Time' non trovata nel CSV EnergyPlus.")

    outdoor_col = detect_outdoor_temperature_column(df_ep_raw.columns)
    ep_air_cols, _ = detect_energyplus_temperature_columns(df_ep_raw.columns)
    if not ep_air_cols:
        raise ValueError(
            "Nel CSV EnergyPlus non trovo colonne 'Zone Mean Air Temperature'."
        )

    df_ep_raw["timestamp"] = parse_energyplus_datetime(
        df_ep_raw["Date/Time"], year=args.year, shift_interval_end=not args.no_ep_shift
    )
    df_ep = df_ep_raw.set_index("timestamp").sort_index()

    df_mz_raw = pd.read_csv(mz_path)
    mz_time_col = detect_multizone_time_column(df_mz_raw, args.multizone_time_column)
    df_mz_raw["timestamp"] = pd.to_datetime(df_mz_raw[mz_time_col], errors="coerce")
    if df_mz_raw["timestamp"].isna().all():
        raise ValueError("Timestamp multizone non parseabili.")

    mz_ts_valid = pd.DatetimeIndex(df_mz_raw["timestamp"].dropna())
    if len(mz_ts_valid) > 0:
        mz_years = sorted(set(int(y) for y in mz_ts_valid.year))
        if len(mz_years) == 1 and mz_years[0] != int(args.year):
            rebased = rebase_datetime_year(df_mz_raw["timestamp"], int(args.year))
            if float(rebased.notna().mean()) >= 0.9:
                df_mz_raw["timestamp"] = rebased

    mz_air_cols, _ = detect_multizone_temperature_columns(df_mz_raw.columns)
    mz_hvac_cols = detect_multizone_hvac_columns(df_mz_raw.columns)
    if not mz_air_cols:
        raise ValueError("Nel CSV multizone non trovo colonne 'T_air_*'.")
    if not mz_hvac_cols:
        raise ValueError("Nel CSV multizone non trovo colonne 'Q_HVAC_*'.")

    zone_map = parse_zone_map(
        args.zone_map, list(mz_air_cols.keys()), list(ep_air_cols.keys())
    )

    missing_hvac = [zone for zone in zone_map if zone not in mz_hvac_cols]
    if missing_hvac:
        raise ValueError(
            "Mancano colonne Q_HVAC_* per zone multizone: "
            f"{sorted(missing_hvac)}"
        )

    df_mz = df_mz_raw.set_index("timestamp").sort_index()
    common_index = df_ep.index.intersection(df_mz.index)
    if len(common_index) == 0:
        raise ValueError("Nessun timestamp comune tra CSV EnergyPlus e multizone.")

    df_ep = df_ep.loc[common_index]
    df_mz = df_mz.loc[common_index]

    html_ok = save_html_plot(
        out_path=out_path,
        df_ep=df_ep,
        df_mz=df_mz,
        zone_map=zone_map,
        ep_air_cols=ep_air_cols,
        mz_air_cols=mz_air_cols,
        mz_hvac_cols=mz_hvac_cols,
        outdoor_col=outdoor_col,
    )

    print(f"EnergyPlus CSV: {ep_path}")
    print(f"Multizone V1 CSV: {mz_path}")
    print(f"Timestamp comuni: {len(common_index)}")
    print("Zone mapping:")
    for mz_zone, ep_zone in zone_map.items():
        print(f"  - {mz_zone} -> {ep_zone}")
    print(f"Outdoor temperature column: {outdoor_col}")
    if html_ok:
        print(f"Saved HTML plot: {out_path}")


if __name__ == "__main__":
    main()
    # test
