#!/usr/bin/env python3
"""Compare indoor temperatures from EnergyPlus and multizone simulation output.

Expected inputs:
- EnergyPlus CSV (default: examples/two_zone_ideal_24_2_fixedout.csv)
- Multizone CSV V1 from multizone_free_floating_example.py
  (default fallback: examples/multizone_v1_hourly.csv, then result_test/multizone_v1_hourly.csv)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Confronta temperature interne (aria e operative, se disponibili) "
            "tra EnergyPlus e risultati multizone."
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
            "Percorso CSV multizone V1 (temperature + consumi). "
            "Se omesso: examples/multizone_v1_hourly.csv "
            "oppure result_test/multizone_v1_hourly.csv."
        ),
    )
    parser.add_argument(
        "--multizone-hybrid-csv",
        default="",
        help=(
            "Percorso CSV multizone V2 hybrid. "
            "Se omesso: examples/multizone_v2_hybrid_hourly.csv "
            "oppure result_test/multizone_v2_hybrid_hourly.csv, se presenti."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2020,
        help="Anno base usato per interpretare la colonna Date/Time di EnergyPlus.",
    )
    parser.add_argument(
        "--no-ep-shift",
        action="store_true",
        help=(
            "Disabilita lo shift di -1h su Date/Time EnergyPlus "
            "(utile se i timestamp sono gia' in inizio intervallo)."
        ),
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
        "--multizone-time-column",
        default="",
        help="Nome colonna tempo nel CSV multizone (default: autodetect).",
    )
    parser.add_argument(
        "--multizone-hybrid-time-column",
        default="",
        help="Nome colonna tempo nel CSV multizone V2 hybrid (default: autodetect).",
    )
    parser.add_argument(
        "--out-dir",
        default=str(SCRIPT_DIR),
        help="Cartella output.",
    )
    parser.add_argument(
        "--out-prefix",
        default="energyplus_vs_multizone_temperatures",
        help="Prefisso file output.",
    )
    return parser.parse_args()


def _resolve_csv_path(
    path_arg: str,
    default_candidates: List[Path],
    *,
    required: bool,
    label: str,
) -> Path | None:
    if path_arg:
        path = Path(path_arg).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"{label} non trovato: {path}")
        return path

    for cand in default_candidates:
        if cand.exists():
            return cand.resolve()
    if required:
        raise FileNotFoundError(
            f"{label} non trovato. Fornisci il percorso esplicitamente."
        )
    return None


def resolve_multizone_csv(path_arg: str) -> Path:
    path = _resolve_csv_path(
        path_arg,
        [
            SCRIPT_DIR / "multizone_v1_hourly.csv",
            PROJECT_ROOT / "result_test" / "multizone_v1_hourly.csv",
        ],
        required=True,
        label="CSV multizone V1",
    )
    assert path is not None
    return path


def resolve_multizone_hybrid_csv(path_arg: str) -> Path | None:
    return _resolve_csv_path(
        path_arg,
        [
            SCRIPT_DIR / "multizone_v2_hybrid_hourly.csv",
            PROJECT_ROOT / "result_test" / "multizone_v2_hybrid_hourly.csv",
        ],
        required=False,
        label="CSV multizone V2 hybrid",
    )


def parse_energyplus_datetime(
    series: pd.Series, *, year: int, shift_interval_end: bool
) -> pd.DatetimeIndex:
    raw = series.astype(str).str.strip()
    parts = raw.str.extract(
        r"(?P<month>\d{1,2})/(?P<day>\d{1,2})\s+(?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})"
    )
    if parts.isna().any().any():
        bad = raw[parts.isna().any(axis=1)].head(5).tolist()
        raise ValueError(
            "Formato Date/Time EnergyPlus non riconosciuto. Esempi non parseabili: "
            f"{bad}"
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
        # E+ tipicamente salva il valore a fine ora; qui lo riportiamo a inizio intervallo.
        ts = ts - pd.Timedelta(hours=1)
    return pd.DatetimeIndex(ts)


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


def detect_energyplus_temperature_columns(
    columns: Iterable[str],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    air_cols: Dict[str, str] = {}
    op_cols: Dict[str, str] = {}
    for col in columns:
        if ":Zone Mean Air Temperature" in col:
            zone = col.split(":", 1)[0].strip()
            air_cols[zone] = col
        elif ":Zone Operative Temperature" in col:
            zone = col.split(":", 1)[0].strip()
            op_cols[zone] = col
    return air_cols, op_cols


def detect_energyplus_outdoor_temperature_column(columns: Iterable[str]) -> str | None:
    for col in columns:
        c = str(col).strip().lower()
        if "environment:site outdoor air drybulb temperature" in c and "[c]" in c:
            return col
    for col in columns:
        c = str(col).strip().lower()
        if "outdoor" in c and "drybulb" in c and "[c]" in c:
            return col
    return None


def detect_multizone_temperature_columns(
    columns: Iterable[str],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    air_cols: Dict[str, str] = {}
    op_cols: Dict[str, str] = {}
    for col in columns:
        if col.startswith("T_air_"):
            air_cols[col.removeprefix("T_air_")] = col
        elif col.startswith("T_air_core_"):
            air_cols[col.removeprefix("T_air_core_")] = col
        elif col.startswith("T_op_"):
            op_cols[col.removeprefix("T_op_")] = col
        elif col.startswith("T_op_core_"):
            op_cols[col.removeprefix("T_op_core_")] = col
        elif col.startswith("Theta_op_"):
            op_cols[col.removeprefix("Theta_op_")] = col
    return air_cols, op_cols


def detect_multizone_time_column(df: pd.DataFrame, preferred: str) -> str:
    columns = list(df.columns)

    if preferred:
        if preferred not in columns:
            raise KeyError(f"Colonna tempo multizone non trovata: {preferred}")
        return preferred

    for candidate in (
        "time(local)",
        "time",
        "datetime",
        "timestamp",
        "Date/Time",
        "Unnamed: 0",
        "index",
    ):
        if candidate in columns:
            return candidate

    for col in columns:
        if "time" in col.lower() or "date" in col.lower():
            return col

    # Fallback: detect a column that is mostly parseable as datetime
    best_col = None
    best_ratio = -1.0
    for col in columns:
        parsed = pd.to_datetime(df[col], errors="coerce")
        ratio = float(parsed.notna().mean())
        if ratio > best_ratio:
            best_ratio = ratio
            best_col = col
    if best_col is not None and best_ratio >= 0.8:
        return best_col

    raise KeyError("Impossibile rilevare automaticamente la colonna tempo multizone.")


def parse_zone_map(
    pairs: List[str], mz_zones: List[str], ep_zones: List[str]
) -> Dict[str, str]:
    if pairs:
        mapping: Dict[str, str] = {}
        for item in pairs:
            if "=" not in item:
                raise ValueError(f"Mappa zona non valida '{item}', formato atteso MZ=EP.")
            mz_zone, ep_zone = [v.strip() for v in item.split("=", 1)]
            mapping[mz_zone] = ep_zone
        unknown_mz = sorted(set(mapping) - set(mz_zones))
        unknown_ep = sorted(set(mapping.values()) - set(ep_zones))
        if unknown_mz:
            raise ValueError(f"Zone multizone non trovate: {unknown_mz}")
        if unknown_ep:
            raise ValueError(f"Zone EnergyPlus non trovate: {unknown_ep}")
        return mapping

    if len(mz_zones) != len(ep_zones):
        raise ValueError(
            "Numero zone diverso tra multizone ed EnergyPlus; "
            "usa --zone-map per mappatura esplicita."
        )
    return dict(zip(sorted(mz_zones), sorted(ep_zones)))


def build_hourly_comparison(
    df_mz: pd.DataFrame,
    df_ep: pd.DataFrame,
    zone_map: Dict[str, str],
    mz_air: Dict[str, str],
    mz_op: Dict[str, str],
    ep_air: Dict[str, str],
    ep_op: Dict[str, str],
    ep_outdoor_col: str | None,
    method_label: str,
) -> pd.DataFrame:
    rows = []
    t_outdoor = (
        pd.to_numeric(df_ep[ep_outdoor_col], errors="coerce").to_numpy()
        if ep_outdoor_col is not None and ep_outdoor_col in df_ep.columns
        else np.full(len(df_ep.index), np.nan, dtype=float)
    )
    for mz_zone, ep_zone in zone_map.items():
        pairs = [
            ("air", mz_air.get(mz_zone), ep_air.get(ep_zone)),
            ("operative", mz_op.get(mz_zone), ep_op.get(ep_zone)),
        ]
        for variable, mz_col, ep_col in pairs:
            if mz_col is None or ep_col is None:
                continue
            tmp = pd.DataFrame(
                {
                    "timestamp": df_mz.index,
                    "multizone_method": method_label,
                    "multizone_zone": mz_zone,
                    "energyplus_zone": ep_zone,
                    "variable": variable,
                    "T_multizone_C": df_mz[mz_col].to_numpy(),
                    "T_energyplus_C": df_ep[ep_col].to_numpy(),
                    "T_outdoor_C": t_outdoor,
                }
            )
            tmp["delta_C"] = tmp["T_multizone_C"] - tmp["T_energyplus_C"]
            rows.append(tmp)

    if not rows:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "multizone_method",
                "multizone_zone",
                "energyplus_zone",
                "variable",
                "T_multizone_C",
                "T_energyplus_C",
                "T_outdoor_C",
                "delta_C",
            ]
        )
    return pd.concat(rows, ignore_index=True)


def build_metrics(hourly: pd.DataFrame) -> pd.DataFrame:
    summary = (
        hourly.groupby(
            ["multizone_method", "multizone_zone", "energyplus_zone", "variable"],
            as_index=False,
        )
        .agg(
            n=("delta_C", "size"),
            mae_C=("delta_C", lambda s: float(np.mean(np.abs(s)))),
            rmse_C=("delta_C", lambda s: float(np.sqrt(np.mean(np.square(s))))),
            bias_C=("delta_C", "mean"),
            max_abs_C=("delta_C", lambda s: float(np.max(np.abs(s)))),
        )
        .sort_values(["multizone_method", "variable", "multizone_zone"])
        .reset_index(drop=True)
    )
    return summary


def build_monthly_evaluation(hourly: pd.DataFrame) -> pd.DataFrame:
    tmp = hourly.copy()
    tmp["timestamp"] = pd.to_datetime(tmp["timestamp"], errors="coerce")
    tmp = tmp.loc[tmp["timestamp"].notna()].copy()
    tmp["month"] = tmp["timestamp"].dt.month
    tmp["month_start"] = tmp["timestamp"].dt.to_period("M").dt.to_timestamp()

    monthly = (
        tmp.groupby(
            [
                "multizone_method",
                "multizone_zone",
                "energyplus_zone",
                "variable",
                "month",
                "month_start",
            ],
            as_index=False,
        )
        .agg(
            n=("delta_C", "size"),
            mae_C=("delta_C", lambda s: float(np.mean(np.abs(s)))),
            rmse_C=("delta_C", lambda s: float(np.sqrt(np.mean(np.square(s))))),
            bias_C=("delta_C", "mean"),
            max_abs_C=("delta_C", lambda s: float(np.max(np.abs(s)))),
            mean_T_multizone_C=("T_multizone_C", "mean"),
            mean_T_energyplus_C=("T_energyplus_C", "mean"),
        )
        .sort_values(["multizone_method", "variable", "multizone_zone", "month"])
        .reset_index(drop=True)
    )
    return monthly


def build_annual_evaluation(hourly: pd.DataFrame) -> pd.DataFrame:
    annual = (
        hourly.groupby(
            ["multizone_method", "multizone_zone", "energyplus_zone", "variable"],
            as_index=False,
        )
        .agg(
            n=("delta_C", "size"),
            mae_C=("delta_C", lambda s: float(np.mean(np.abs(s)))),
            rmse_C=("delta_C", lambda s: float(np.sqrt(np.mean(np.square(s))))),
            bias_C=("delta_C", "mean"),
            max_abs_C=("delta_C", lambda s: float(np.max(np.abs(s)))),
            mean_T_multizone_C=("T_multizone_C", "mean"),
            mean_T_energyplus_C=("T_energyplus_C", "mean"),
        )
        .sort_values(["multizone_method", "variable", "multizone_zone"])
        .reset_index(drop=True)
    )
    return annual


def _find_first_column(columns: Iterable[str], patterns: List[str]) -> str | None:
    cols = list(columns)
    for col in cols:
        c = col.strip()
        if all(p.lower() in c.lower() for p in patterns):
            return col
    return None


def _extract_annual_energy_j(df_ep: pd.DataFrame, service: str) -> float:
    if service == "heating":
        patterns = ["heating:energytransfer", "[j]", "(annual)"]
    elif service == "cooling":
        patterns = ["cooling:energytransfer", "[j]", "(annual)"]
    else:
        raise ValueError(service)

    col = _find_first_column(df_ep.columns, patterns)
    if col is None:
        raise KeyError(
            f"Colonna EnergyPlus annuale non trovata per {service}. "
            f"Pattern: {patterns}"
        )
    s = pd.to_numeric(df_ep[col], errors="coerce").dropna()
    if s.empty:
        raise ValueError(f"Colonna EnergyPlus {col} senza valori numerici.")
    return float(s.iloc[-1])


def _extract_annual_energy_j_optional(df_ep: pd.DataFrame, service: str) -> float:
    try:
        return float(_extract_annual_energy_j(df_ep, service))
    except Exception:
        return float("nan")


def _infer_timestep_seconds(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 3600.0
    delta_s = np.diff(index.view("i8")) / 1e9
    delta_s = delta_s[np.isfinite(delta_s) & (delta_s > 0)]
    if len(delta_s) == 0:
        return 3600.0
    return float(np.median(delta_s))


def _find_columns_all_substrings(
    columns: Iterable[str], include: List[str], exclude: List[str] | None = None
) -> List[str]:
    exclude = exclude or []
    out: List[str] = []
    for col in columns:
        c = col.strip().lower()
        if all(token.lower() in c for token in include) and not any(
            token.lower() in c for token in exclude
        ):
            out.append(col)
    return out


def _sum_numeric_columns(df: pd.DataFrame, cols: List[str]) -> pd.Series:
    if not cols:
        return pd.Series(0.0, index=df.index, dtype=float)
    return df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)


def _find_surface_metric_columns(
    columns: Iterable[str],
    *,
    metric_tokens: List[str],
    include_surface_tokens: List[str],
    exclude_surface_tokens: List[str] | None = None,
) -> List[str]:
    exclude_surface_tokens = exclude_surface_tokens or []
    out: List[str] = []
    for col in columns:
        c = str(col).strip().lower()
        if not all(token.lower() in c for token in metric_tokens):
            continue
        surface_name = c.split(":", 1)[0]
        if not any(token.lower() in surface_name for token in include_surface_tokens):
            continue
        if any(token.lower() in surface_name for token in exclude_surface_tokens):
            continue
        out.append(col)
    return out


def _annual_kwh_from_power(power_w: pd.Series, dt_s: float) -> float:
    power = pd.to_numeric(power_w, errors="coerce").fillna(0.0)
    return float(power.sum() * dt_s / 3.6e6)


def _annual_kwh_from_energy_j(energy_j: pd.Series) -> float:
    energy = pd.to_numeric(energy_j, errors="coerce").fillna(0.0)
    return float(energy.sum() / 3.6e6)


def _series_summary_row(
    *,
    model: str,
    vector: str,
    annual_positive_kwh: float,
    annual_negative_kwh: float = 0.0,
    positive_label: str = "loss",
    negative_label: str = "gain",
    columns_used: List[str] | None = None,
    note: str = "",
) -> Dict[str, object]:
    pos = max(0.0, float(annual_positive_kwh))
    neg = max(0.0, float(annual_negative_kwh))
    dominant_is_positive = pos >= neg
    dominant_kwh = pos if dominant_is_positive else neg
    net_kwh = pos - neg
    return {
        "model": model,
        "vector": vector,
        "direction": positive_label if dominant_is_positive else negative_label,
        "annual_kWh": dominant_kwh,
        "annual_net_kWh": net_kwh,
        "annual_positive_kWh": pos,
        "annual_negative_kWh": neg,
        "columns_used": " | ".join(columns_used or []),
        "note": note,
    }


def build_consumption_driver_summary(
    df_mz: pd.DataFrame,
    df_ep: pd.DataFrame,
    ep_outdoor_col: str | None,
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    dt_s = _infer_timestep_seconds(df_ep.index)
    dt_h = dt_s / 3600.0

    # EnergyPlus vectors directly exported in the CSV.
    ep_infiltration_loss_cols = _find_columns_all_substrings(
        df_ep.columns,
        include=["zone infiltration sensible heat loss energy", "[j]", "(hourly)"],
    )
    if ep_infiltration_loss_cols:
        rows.append(
            _series_summary_row(
                model="EnergyPlus",
                vector="Infiltration sensible loss",
                annual_positive_kwh=_annual_kwh_from_energy_j(
                    _sum_numeric_columns(df_ep, ep_infiltration_loss_cols)
                ),
                positive_label="loss",
                columns_used=ep_infiltration_loss_cols,
            )
        )

    ep_infiltration_gain_cols = _find_columns_all_substrings(
        df_ep.columns,
        include=["zone infiltration sensible heat gain energy", "[j]", "(hourly)"],
    )
    if ep_infiltration_gain_cols:
        rows.append(
            _series_summary_row(
                model="EnergyPlus",
                vector="Infiltration sensible gain",
                annual_positive_kwh=_annual_kwh_from_energy_j(
                    _sum_numeric_columns(df_ep, ep_infiltration_gain_cols)
                ),
                positive_label="gain",
                columns_used=ep_infiltration_gain_cols,
            )
        )

    ep_window_gain_cols = _find_columns_all_substrings(
        df_ep.columns,
        include=["surface window heat gain energy", "[j]", "(hourly)"],
    )
    if ep_window_gain_cols:
        rows.append(
            _series_summary_row(
                model="EnergyPlus",
                vector="Window heat gain",
                annual_positive_kwh=_annual_kwh_from_energy_j(
                    _sum_numeric_columns(df_ep, ep_window_gain_cols)
                ),
                positive_label="gain",
                columns_used=ep_window_gain_cols,
            )
        )

    ep_window_loss_cols = _find_columns_all_substrings(
        df_ep.columns,
        include=["surface window heat loss energy", "[j]", "(hourly)"],
    )
    if ep_window_loss_cols:
        rows.append(
            _series_summary_row(
                model="EnergyPlus",
                vector="Window heat loss",
                annual_positive_kwh=_annual_kwh_from_energy_j(
                    _sum_numeric_columns(df_ep, ep_window_loss_cols)
                ),
                positive_label="loss",
                columns_used=ep_window_loss_cols,
            )
        )

    ep_ground_cols = _find_surface_metric_columns(
        df_ep.columns,
        metric_tokens=["surface inside face conduction heat transfer energy", "[j]", "(hourly)"],
        include_surface_tokens=["floor"],
    )
    if ep_ground_cols:
        ground_j = _sum_numeric_columns(df_ep, ep_ground_cols)
        rows.append(
            _series_summary_row(
                model="EnergyPlus",
                vector="Ground transmission",
                annual_positive_kwh=_annual_kwh_from_energy_j(ground_j.clip(lower=0.0)),
                annual_negative_kwh=_annual_kwh_from_energy_j((-ground_j.clip(upper=0.0))),
                positive_label="gain from ground",
                negative_label="loss to ground",
                columns_used=ep_ground_cols,
                note="EnergyPlus inside-face conduction; positive means heat enters the zone.",
            )
        )

    ep_opaque_ext_cols = _find_surface_metric_columns(
        df_ep.columns,
        metric_tokens=["surface inside face conduction heat transfer energy", "[j]", "(hourly)"],
        include_surface_tokens=["wall", "roof"],
        exclude_surface_tokens=["_int", "win", "window"],
    )
    if ep_opaque_ext_cols:
        opaque_j = _sum_numeric_columns(df_ep, ep_opaque_ext_cols)
        rows.append(
            _series_summary_row(
                model="EnergyPlus",
                vector="Opaque envelope transmission",
                annual_positive_kwh=_annual_kwh_from_energy_j(opaque_j.clip(lower=0.0)),
                annual_negative_kwh=_annual_kwh_from_energy_j((-opaque_j.clip(upper=0.0))),
                positive_label="gain inward",
                negative_label="loss outward",
                columns_used=ep_opaque_ext_cols,
                note="EnergyPlus inside-face conduction; positive means heat enters the zone.",
            )
        )

    # ISO 52016 multizone vectors available in the exported CSV.
    iso_phi_cols = [c for c in df_mz.columns if c.startswith("Phi_int_")]
    if iso_phi_cols:
        phi_w = _sum_numeric_columns(df_mz, iso_phi_cols)
        rows.append(
            _series_summary_row(
                model="ISO 52016",
                vector="Internal gains",
                annual_positive_kwh=_annual_kwh_from_power(phi_w, dt_s),
                positive_label="gain",
                columns_used=iso_phi_cols,
                note="Directly exported by the multizone solver.",
            )
        )

    iso_opaque_inside_cols = [c for c in df_mz.columns if c.startswith("Q_opaque_inside_surface_")]
    iso_opaque_envelope_cols = [
        c for c in iso_opaque_inside_cols if any(token in c.lower() for token in ("wall", "roof"))
    ]
    if iso_opaque_envelope_cols:
        q_opaque_in_w = _sum_numeric_columns(df_mz, iso_opaque_envelope_cols)
        rows.append(
            _series_summary_row(
                model="ISO 52016",
                vector="Opaque envelope transmission",
                annual_positive_kwh=_annual_kwh_from_power(q_opaque_in_w.clip(lower=0.0), dt_s),
                annual_negative_kwh=_annual_kwh_from_power((-q_opaque_in_w.clip(upper=0.0)), dt_s),
                positive_label="gain inward",
                negative_label="loss outward",
                columns_used=iso_opaque_envelope_cols,
                note="Directly exported by the multizone solver as inside-face conduction.",
            )
        )

    iso_ground_inside_cols = [
        c for c in iso_opaque_inside_cols if any(token in c.lower() for token in ("floor", "slab", "ground"))
    ]
    if iso_ground_inside_cols:
        q_ground_w = _sum_numeric_columns(df_mz, iso_ground_inside_cols)
        rows.append(
            _series_summary_row(
                model="ISO 52016",
                vector="Ground transmission",
                annual_positive_kwh=_annual_kwh_from_power(q_ground_w.clip(lower=0.0), dt_s),
                annual_negative_kwh=_annual_kwh_from_power((-q_ground_w.clip(upper=0.0)), dt_s),
                positive_label="gain from ground",
                negative_label="loss to ground",
                columns_used=iso_ground_inside_cols,
                note="Directly exported by the multizone solver as inside-face conduction.",
            )
        )
    else:
        iso_ground_cols = [c for c in df_mz.columns if c.startswith("Q_ground_surface_")]
        if not iso_ground_cols:
            iso_ground_cols = [c for c in df_mz.columns if c.startswith("Q_ground_")]
        if iso_ground_cols:
            q_ground_w = _sum_numeric_columns(df_mz, iso_ground_cols)
            rows.append(
                _series_summary_row(
                    model="ISO 52016",
                    vector="Ground transmission",
                    annual_positive_kwh=_annual_kwh_from_power(q_ground_w.clip(lower=0.0), dt_s),
                    annual_negative_kwh=_annual_kwh_from_power((-q_ground_w.clip(upper=0.0)), dt_s),
                    positive_label="loss to ground",
                    negative_label="gain from ground",
                    columns_used=iso_ground_cols,
                    note="Positive sign means building -> ground.",
                )
            )

    if ep_outdoor_col is not None and ep_outdoor_col in df_ep.columns:
        t_out = pd.to_numeric(df_ep[ep_outdoor_col], errors="coerce").reindex(df_mz.index)
        vent_power = pd.Series(0.0, index=df_mz.index, dtype=float)
        vent_terms: List[str] = []
        for h_col in [c for c in df_mz.columns if c.startswith("H_ve_")]:
            zone = h_col.removeprefix("H_ve_")
            t_col = f"T_air_{zone}"
            if t_col not in df_mz.columns:
                continue
            h_ve = pd.to_numeric(df_mz[h_col], errors="coerce").fillna(0.0)
            t_air = pd.to_numeric(df_mz[t_col], errors="coerce").fillna(np.nan)
            term = h_ve * (t_air - t_out)
            vent_power = vent_power.add(term.fillna(0.0), fill_value=0.0)
            vent_terms.append(f"{h_col}*(T_air_{zone}-T_out)")
        if vent_terms:
            rows.append(
                _series_summary_row(
                    model="ISO 52016",
                    vector="Ventilation sensible exchange",
                    annual_positive_kwh=_annual_kwh_from_power(vent_power.clip(lower=0.0), dt_s),
                    annual_negative_kwh=_annual_kwh_from_power((-vent_power.clip(upper=0.0)), dt_s),
                    positive_label="loss to outdoor",
                    negative_label="gain from outdoor",
                    columns_used=vent_terms,
                    note="Derived from exported H_ve and indoor/outdoor temperatures.",
                )
            )

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    return summary.sort_values(["model", "annual_kWh"], ascending=[True, False]).reset_index(drop=True)


def _dominant_sign_magnitude_sum(df: pd.DataFrame) -> pd.Series:
    pos = df.clip(lower=0.0).sum(axis=1)
    neg = (-df.clip(upper=0.0)).sum(axis=1)
    return pos if float(pos.sum()) >= float(neg.sum()) else neg


def _extract_energyplus_hourly_power(
    df_ep: pd.DataFrame, service: str, dt_s: float, annual_default_j: float
) -> Tuple[pd.Series, str, List[str]]:
    if service not in {"heating", "cooling"}:
        raise ValueError(service)

    service_token = "heating" if service == "heating" else "cooling"

    # Preferred explicit columns:
    # Heating:EnergyTransfer [J](Hourly)
    # Cooling:EnergyTransfer [J](Hourly)
    preferred_energytransfer_col = _find_first_column(
        df_ep.columns,
        patterns=[f"{service_token}:energytransfer", "[j]", "(hourly)"],
    )
    if preferred_energytransfer_col is not None:
        data_j = pd.to_numeric(df_ep[preferred_energytransfer_col], errors="coerce").fillna(0.0)
        power_w = data_j / dt_s
        return power_w, "hourly_energytransfer_J_preferred", [preferred_energytransfer_col]

    energytransfer_cols = _find_columns_all_substrings(
        df_ep.columns,
        include=[service_token, "energytransfer", "(hourly)", "[j]"],
    )
    if energytransfer_cols:
        data_j = df_ep[energytransfer_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        power_w = _dominant_sign_magnitude_sum(data_j) / dt_s
        return power_w, "hourly_energytransfer_J", energytransfer_cols

    rate_cols = _find_columns_all_substrings(
        df_ep.columns,
        include=[service_token, "(hourly)", "[w]"],
        exclude=["setpoint", "temperature"],
    )
    if rate_cols:
        data = df_ep[rate_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        return _dominant_sign_magnitude_sum(data), "hourly_rate_W", rate_cols

    energy_cols = _find_columns_all_substrings(
        df_ep.columns,
        include=[service_token, "(hourly)", "[j]"],
        exclude=["setpoint", "temperature"],
    )
    if energy_cols:
        data_j = df_ep[energy_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        power_w = _dominant_sign_magnitude_sum(data_j) / dt_s
        return power_w, "hourly_energy_J", energy_cols

    if len(df_ep.index) == 0 or dt_s <= 0:
        power_const = 0.0
    elif np.isfinite(annual_default_j):
        power_const = annual_default_j / (len(df_ep.index) * dt_s)
    else:
        power_const = 0.0
    fallback = pd.Series(power_const, index=df_ep.index, dtype=float)
    source = "annual_distributed_constant_W" if np.isfinite(annual_default_j) else "no_hourly_column_zero_fallback"
    return fallback, source, []


def _extract_iso_multizone_hourly_power(
    df_iso: pd.DataFrame,
    preferred_prefixes: List[str],
) -> Tuple[pd.Series, pd.Series, str, List[str]]:
    q_cols: List[str] = []
    source = ""
    for pref in preferred_prefixes:
        cols = [c for c in df_iso.columns if c.startswith(pref)]
        if cols:
            q_cols = cols
            source = pref
            break

    if not q_cols:
        raise ValueError(
            f"Nel CSV ISO non trovo colonne potenza con prefissi: {preferred_prefixes}"
        )

    q_df = df_iso[q_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    p_heat_w = q_df.clip(lower=0.0).sum(axis=1)
    p_cool_w = (-q_df.clip(upper=0.0)).sum(axis=1)
    return p_heat_w, p_cool_w, source, q_cols


def build_ideal_consumption_comparison(
    df_mz_methods: Dict[str, pd.DataFrame],
    df_ep: pd.DataFrame,
    df_ep_raw: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, str]]:
    dt_s = _infer_timestep_seconds(df_ep.index)
    common_index = df_ep.index

    e_ep_heat_j = _extract_annual_energy_j_optional(df_ep_raw, "heating")
    e_ep_cool_j = _extract_annual_energy_j_optional(df_ep_raw, "cooling")

    ep_heat_w, source_heat, cols_heat = _extract_energyplus_hourly_power(
        df_ep, "heating", dt_s, e_ep_heat_j
    )
    ep_cool_w, source_cool, cols_cool = _extract_energyplus_hourly_power(
        df_ep, "cooling", dt_s, e_ep_cool_j
    )

    hourly = pd.DataFrame(
        {
            "timestamp": common_index,
            "P_heat_energyplus_W": ep_heat_w.reindex(common_index).fillna(0.0).to_numpy(),
            "P_cool_energyplus_W": ep_cool_w.reindex(common_index).fillna(0.0).to_numpy(),
        }
    )

    def _to_energy_j(power_w: pd.Series) -> float:
        return float(np.nansum(power_w.to_numpy()) * dt_s)

    e_ep_heat_from_hourly_j = _to_energy_j(hourly["P_heat_energyplus_W"])
    e_ep_cool_from_hourly_j = _to_energy_j(hourly["P_cool_energyplus_W"])

    rows = []
    meta = {
        "ep_heating_source": source_heat,
        "ep_cooling_source": source_cool,
        "ep_heating_cols": " | ".join(cols_heat),
        "ep_cooling_cols": " | ".join(cols_cool),
    }

    method_specs = [
        ("ISO_V1", ["Q_HVAC_"]),
        ("ISO_V2_HYBRID", ["Q_HC_hybrid_"]),
    ]
    for method_name, prefixes in method_specs:
        df_method = df_mz_methods.get(method_name)
        if df_method is None:
            continue
        p_heat_w, p_cool_w, source_name, source_cols = _extract_iso_multizone_hourly_power(
            df_method.reindex(common_index).fillna(0.0),
            preferred_prefixes=prefixes,
        )
        col_key = method_name.lower()
        hourly[f"P_heat_{col_key}_W"] = p_heat_w.reindex(common_index).fillna(0.0).to_numpy()
        hourly[f"P_cool_{col_key}_W"] = p_cool_w.reindex(common_index).fillna(0.0).to_numpy()
        hourly[f"delta_heat_{col_key}_minus_ep_W"] = (
            hourly[f"P_heat_{col_key}_W"] - hourly["P_heat_energyplus_W"]
        )
        hourly[f"delta_cool_{col_key}_minus_ep_W"] = (
            hourly[f"P_cool_{col_key}_W"] - hourly["P_cool_energyplus_W"]
        )

        e_heat_j = _to_energy_j(hourly[f"P_heat_{col_key}_W"])
        e_cool_j = _to_energy_j(hourly[f"P_cool_{col_key}_W"])

        for service, e_iso_j, e_ep_j in [
            ("heating", e_heat_j, e_ep_heat_from_hourly_j),
            ("cooling", e_cool_j, e_ep_cool_from_hourly_j),
        ]:
            rows.append(
                {
                    "service": service,
                    "iso_method": method_name,
                    "energyplus_J_from_input": (
                        e_ep_heat_j if service == "heating" else e_ep_cool_j
                    ),
                    "energyplus_J_from_hourly_profile": e_ep_j,
                    "iso_multizone_J": e_iso_j,
                    "delta_J_iso_minus_ep_hourly": e_iso_j - e_ep_j,
                    "delta_pct_iso_minus_ep_hourly": (
                        np.nan if abs(e_ep_j) < 1e-9 else 100.0 * (e_iso_j - e_ep_j) / e_ep_j
                    ),
                    "energyplus_kWh_from_hourly_profile": e_ep_j / 3.6e6,
                    "iso_multizone_kWh": e_iso_j / 3.6e6,
                    "delta_kWh_iso_minus_ep_hourly": (e_iso_j - e_ep_j) / 3.6e6,
                    "iso_integration_timestep_s": dt_s,
                }
            )
        meta[f"{col_key}_source"] = source_name
        meta[f"{col_key}_cols"] = " | ".join(source_cols)

    summary = pd.DataFrame(rows)
    return hourly, summary, meta


def save_html_plot(hourly: pd.DataFrame, out_path: Path) -> bool:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception:
        print("[warn] plotly non disponibile, salto output HTML.")
        return False

    groups = list(
        hourly.groupby(["multizone_zone", "energyplus_zone", "variable"], sort=False)
    )
    fig = make_subplots(
        rows=len(groups),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=[
            f"{var} | {mz_zone} vs {ep_zone}"
            for (mz_zone, ep_zone, var), _ in groups
        ],
    )

    row = 1
    shown_legend_groups: set[str] = set()
    for (_, _, _), group in groups:
        g = group.sort_values("timestamp")
        outdoor_showlegend = "outdoor" not in shown_legend_groups
        fig.add_trace(
            go.Scatter(
                x=g["timestamp"],
                y=g["T_outdoor_C"],
                mode="lines",
                name="Outdoor",
                legendgroup="outdoor",
                showlegend=outdoor_showlegend,
                line={"dash": "dot", "width": 1.2, "color": "#444444"},
            ),
            row=row,
            col=1,
        )
        shown_legend_groups.add("outdoor")
        ep_showlegend = "energyplus" not in shown_legend_groups
        fig.add_trace(
            go.Scatter(
                x=g["timestamp"],
                y=g["T_energyplus_C"],
                mode="lines",
                name="EnergyPlus",
                legendgroup="energyplus",
                showlegend=ep_showlegend,
            ),
            row=row,
            col=1,
        )
        shown_legend_groups.add("energyplus")
        for method_name, gm in g.groupby("multizone_method", sort=False):
            method_showlegend = method_name not in shown_legend_groups
            fig.add_trace(
                go.Scatter(
                    x=gm["timestamp"],
                    y=gm["T_multizone_C"],
                    mode="lines",
                    name=method_name,
                    legendgroup=method_name,
                    showlegend=method_showlegend,
                ),
                row=row,
                col=1,
            )
            shown_legend_groups.add(method_name)
        row += 1

    fig.update_layout(
        title="Confronto temperature interne: EnergyPlus vs Multizone",
        template="plotly_white",
        hovermode="x unified",
        height=max(420, 260 * len(groups)),
    )
    fig.update_yaxes(title_text="Temperatura [C]")
    fig.update_xaxes(title_text="Time")
    fig.write_html(out_path, include_plotlyjs="cdn")
    return True


def _build_consumption_energy_views(
    cons_hourly: pd.DataFrame,
    sources: List[Tuple[str, str, str]],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = cons_hourly.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.loc[df["timestamp"].notna()].sort_values("timestamp").reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    dt_s = _infer_timestep_seconds(pd.DatetimeIndex(df["timestamp"]))
    dt_h = dt_s / 3600.0

    df["month_start"] = df["timestamp"].dt.to_period("M").dt.to_timestamp()
    monthly_rows: List[Dict[str, object]] = []
    annual_rows: List[Dict[str, object]] = []

    for source_name, heat_col, cool_col in sources:
        p_heat = pd.to_numeric(df[heat_col], errors="coerce").fillna(0.0)
        p_cool = pd.to_numeric(df[cool_col], errors="coerce").fillna(0.0)
        e_heat_kwh = p_heat * dt_h / 1000.0
        e_cool_kwh = p_cool * dt_h / 1000.0

        monthly = (
            pd.DataFrame(
                {
                    "month_start": df["month_start"],
                    "E_heat_kWh": e_heat_kwh,
                    "E_cool_kWh": e_cool_kwh,
                }
            )
            .groupby("month_start", as_index=False)
            .sum()
        )
        monthly["source"] = source_name
        monthly_rows.append(monthly)

        annual_rows.append(
            {
                "source": source_name,
                "service": "heating",
                "E_kWh": float(e_heat_kwh.sum()),
            }
        )
        annual_rows.append(
            {
                "source": source_name,
                "service": "cooling",
                "E_kWh": float(e_cool_kwh.sum()),
            }
        )

    monthly_df = (
        pd.concat(monthly_rows, ignore_index=True)
        if monthly_rows
        else pd.DataFrame(columns=["month_start", "E_heat_kWh", "E_cool_kWh", "source"])
    )
    annual_df = pd.DataFrame(annual_rows)
    return monthly_df, annual_df


def save_consumption_html(
    cons_hourly: pd.DataFrame,
    out_path: Path,
    subtitle: str = "",
    sources: List[Tuple[str, str, str]] | None = None,
    driver_summary: pd.DataFrame | None = None,
) -> bool:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception:
        print("[warn] plotly non disponibile, salto output HTML consumi.")
        return False

    if sources is None:
        sources = [
            ("EnergyPlus", "P_heat_energyplus_W", "P_cool_energyplus_W"),
            ("ISO V1", "P_heat_iso_v1_W", "P_cool_iso_v1_W"),
        ]
    monthly_energy, annual_energy = _build_consumption_energy_views(cons_hourly, sources)
    has_driver_summary = driver_summary is not None and not driver_summary.empty

    subplot_titles = [
        "Heating power (hourly)",
        "Cooling power (hourly)",
        "Monthly heating energy",
        "Monthly cooling energy",
        "Annual heating/cooling energy",
    ]
    row_heights = [0.24, 0.24, 0.18, 0.18, 0.16]
    n_rows = 5
    if has_driver_summary:
        subplot_titles.extend(
            [
                "Dominant annual vectors available in EnergyPlus CSV",
                "Dominant annual vectors available in ISO 52016 CSV",
            ]
        )
        row_heights = [0.18, 0.18, 0.14, 0.14, 0.12, 0.12, 0.12]
        n_rows = 7

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.06,
        subplot_titles=tuple(subplot_titles),
        row_heights=row_heights,
    )
    for source_name, heat_col, cool_col in sources:
        if heat_col in cons_hourly.columns:
            fig.add_trace(
                go.Scatter(
                    x=cons_hourly["timestamp"],
                    y=cons_hourly[heat_col],
                    mode="lines",
                    name=f"{source_name} heating",
                    legendgroup=source_name,
                    line={"width": 2.0} if source_name == "EnergyPlus" else None,
                ),
                row=1,
                col=1,
            )
        if cool_col in cons_hourly.columns:
            fig.add_trace(
                go.Scatter(
                    x=cons_hourly["timestamp"],
                    y=cons_hourly[cool_col],
                    mode="lines",
                    name=f"{source_name} cooling",
                    legendgroup=source_name,
                    showlegend=True,
                    line={"width": 2.0} if source_name == "EnergyPlus" else None,
                ),
                row=2,
                col=1,
            )

    if not monthly_energy.empty:
        for source_name, grp in monthly_energy.groupby("source", sort=False):
            g = grp.sort_values("month_start")
            fig.add_trace(
                go.Bar(
                    x=g["month_start"],
                    y=g["E_heat_kWh"],
                    name=f"{source_name} monthly heating",
                    legendgroup=f"{source_name}_monthly",
                    showlegend=False,
                ),
                row=3,
                col=1,
            )
            fig.add_trace(
                go.Bar(
                    x=g["month_start"],
                    y=g["E_cool_kWh"],
                    name=f"{source_name} monthly cooling",
                    legendgroup=f"{source_name}_monthly",
                    showlegend=False,
                ),
                row=4,
                col=1,
            )

    if not annual_energy.empty:
        for source_name, grp in annual_energy.groupby("source", sort=False):
            g = grp.set_index("service")
            fig.add_trace(
                go.Bar(
                    x=["heating", "cooling"],
                    y=[
                        float(g.loc["heating", "E_kWh"]) if "heating" in g.index else 0.0,
                        float(g.loc["cooling", "E_kWh"]) if "cooling" in g.index else 0.0,
                    ],
                    name=f"{source_name} annual",
                    legendgroup=f"{source_name}_annual",
                    showlegend=False,
                ),
                row=5,
                col=1,
            )

    if has_driver_summary:
        color_map = {
            "loss": "#d62728",
            "loss to ground": "#8c564b",
            "loss outward": "#9467bd",
            "loss to outdoor": "#7f7f7f",
            "gain": "#2ca02c",
            "gain from ground": "#17becf",
            "gain inward": "#1f77b4",
            "gain from outdoor": "#bcbd22",
        }
        model_row_map = {"EnergyPlus": 6, "ISO 52016": 7}
        for model_name, row_num in model_row_map.items():
            top = (
                driver_summary.loc[driver_summary["model"] == model_name]
                .sort_values("annual_kWh", ascending=False)
                .head(6)
                .copy()
            )
            if top.empty:
                continue
            top["display"] = top["vector"].astype(str)
            top["color"] = top["direction"].map(color_map).fillna("#636efa")
            top["hover"] = (
                "Vector: "
                + top["vector"].astype(str)
                + "<br>Direction: "
                + top["direction"].astype(str)
                + "<br>Dominant annual energy: "
                + top["annual_kWh"].map(lambda v: f"{float(v):.1f} kWh")
                + "<br>Net annual energy: "
                + top["annual_net_kWh"].map(lambda v: f"{float(v):.1f} kWh")
            )
            fig.add_trace(
                go.Bar(
                    x=top["display"],
                    y=top["annual_kWh"],
                    marker_color=top["color"],
                    text=top["direction"],
                    textposition="outside",
                    name=f"{model_name} dominant vectors",
                    legendgroup=f"{model_name}_drivers",
                    showlegend=False,
                    customdata=np.column_stack(
                        [
                            top["annual_net_kWh"].to_numpy(),
                            top["direction"].to_numpy(),
                        ]
                    ),
                    hovertext=top["hover"],
                    hovertemplate="%{hovertext}<extra></extra>",
                ),
                row=row_num,
                col=1,
            )

    fig.update_layout(
        title=(
            "Confronto consumi ideali (orari, mensili, annuali) "
            "(EnergyPlus vs ISO multizone)"
            + (f"<br><sup>{subtitle}</sup>" if subtitle else "")
        ),
        template="plotly_white",
        hovermode="x unified",
        barmode="group",
        height=1900 if has_driver_summary else 1450,
    )
    fig.update_yaxes(title_text="Potenza [W]", row=1, col=1)
    fig.update_yaxes(title_text="Potenza [W]", row=2, col=1)
    fig.update_yaxes(title_text="Energia [kWh]", row=3, col=1)
    fig.update_yaxes(title_text="Energia [kWh]", row=4, col=1)
    fig.update_yaxes(title_text="Energia [kWh]", row=5, col=1)
    if has_driver_summary:
        fig.update_yaxes(title_text="Energia [kWh]", row=6, col=1)
        fig.update_yaxes(title_text="Energia [kWh]", row=7, col=1)
    fig.update_xaxes(title_text="Time", row=1, col=1)
    fig.update_xaxes(title_text="Time", row=2, col=1)
    fig.update_xaxes(title_text="Month", tickformat="%b", row=3, col=1)
    fig.update_xaxes(title_text="Month", tickformat="%b", row=4, col=1)
    fig.update_xaxes(title_text="Service", row=5, col=1)
    if has_driver_summary:
        fig.update_xaxes(title_text="Vector", row=6, col=1)
        fig.update_xaxes(title_text="Vector", row=7, col=1)

    fig_html = fig.to_html(include_plotlyjs="cdn", full_html=False)
    sections = [fig_html]
    if has_driver_summary:
        display_df = driver_summary.copy()
        display_df = display_df.rename(
            columns={
                "model": "Model",
                "vector": "Vector",
                "direction": "Dominant direction",
                "annual_kWh": "Dominant annual energy [kWh]",
                "annual_net_kWh": "Net annual energy [kWh]",
                "annual_positive_kWh": "Positive-side annual energy [kWh]",
                "annual_negative_kWh": "Negative-side annual energy [kWh]",
                "columns_used": "Columns / derived terms",
                "note": "Note",
            }
        )
        for col in [
            "Dominant annual energy [kWh]",
            "Net annual energy [kWh]",
            "Positive-side annual energy [kWh]",
            "Negative-side annual energy [kWh]",
        ]:
            display_df[col] = pd.to_numeric(display_df[col], errors="coerce").map(
                lambda v: "" if pd.isna(v) else f"{float(v):.1f}"
            )
        sections.append(
            "<h2>Dominant Annual Vectors</h2>"
            "<p>Classifica dei vettori energetici disponibili nei CSV. "
            "Per ISO 52016 il ranking e' limitato alle grandezze esportate dal solver "
            "(ad esempio apporti interni, terreno e ventilazione sensibile ricostruita).</p>"
        )
        sections.append(display_df.to_html(index=False, border=0))

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>EnergyPlus vs ISO Multizone - Consumi ideali</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;margin:20px;}"
        "h2{margin-top:28px;}"
        "table{border-collapse:collapse;width:100%;margin-top:12px;}"
        "th,td{border:1px solid #d9d9d9;padding:6px 8px;font-size:13px;text-align:left;}"
        "th{background:#f5f5f5;}"
        "p{max-width:1100px;line-height:1.45;}"
        "</style></head><body>"
        + "".join(sections)
        + "</body></html>"
    )
    out_path.write_text(html, encoding="utf-8")
    return True


def save_monthly_annual_evaluation_html(
    monthly_eval: pd.DataFrame, annual_eval: pd.DataFrame, out_path: Path
) -> bool:
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception:
        print("[warn] plotly non disponibile, salto output HTML valutazione mensile/annuale.")
        return False

    if monthly_eval.empty or annual_eval.empty:
        return False

    def _label(df: pd.DataFrame) -> pd.Series:
        return (
            df["multizone_method"].astype(str)
            + " | "
            + df["multizone_zone"].astype(str)
            + " vs "
            + df["energyplus_zone"].astype(str)
            + " ("
            + df["variable"].astype(str)
            + ")"
        )

    monthly_plot = monthly_eval.copy()
    monthly_plot["label"] = _label(monthly_plot)
    annual_plot = annual_eval.copy()
    annual_plot["label"] = _label(annual_plot)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.09,
        subplot_titles=(
            "Monthly MAE [C]",
            "Monthly bias [C] (Multizone - EnergyPlus)",
            "Annual metrics [C]",
        ),
    )

    for label, grp in monthly_plot.groupby("label", sort=False):
        g = grp.sort_values("month_start")
        fig.add_trace(
            go.Scatter(
                x=g["month_start"],
                y=g["mae_C"],
                mode="lines+markers",
                name=f"{label} | MAE",
                legendgroup=f"{label}_mae",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=g["month_start"],
                y=g["bias_C"],
                mode="lines+markers",
                name=f"{label} | bias",
                legendgroup=f"{label}_bias",
            ),
            row=2,
            col=1,
        )

    fig.add_trace(
        go.Bar(
            x=annual_plot["label"],
            y=annual_plot["mae_C"],
            name="Annual MAE",
            marker={"color": "#1f77b4"},
        ),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=annual_plot["label"],
            y=annual_plot["rmse_C"],
            name="Annual RMSE",
            marker={"color": "#ff7f0e"},
        ),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=annual_plot["label"],
            y=annual_plot["bias_C"],
            name="Annual bias",
            marker={"color": "#2ca02c"},
        ),
        row=3,
        col=1,
    )

    fig.update_layout(
        title="Valutazione mensile e annuale: confronto EnergyPlus vs Multizone",
        template="plotly_white",
        hovermode="x unified",
        barmode="group",
        height=980,
    )
    fig.update_yaxes(title_text="[C]", row=1, col=1)
    fig.update_yaxes(title_text="[C]", row=2, col=1)
    fig.update_yaxes(title_text="[C]", row=3, col=1)
    fig.update_xaxes(title_text="Month", tickformat="%b", row=1, col=1)
    fig.update_xaxes(title_text="Month", tickformat="%b", row=2, col=1)
    fig.update_xaxes(title_text="Zone / variable", row=3, col=1)

    fig.add_hline(y=0.0, line_dash="dot", line_color="#666666", row=2, col=1)
    fig.add_hline(y=0.0, line_dash="dot", line_color="#666666", row=3, col=1)

    fig.write_html(out_path, include_plotlyjs="cdn")
    return True


def load_multizone_dataframe(
    csv_path: Path,
    preferred_time_column: str,
    target_year: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, str], Dict[str, str]]:
    df_raw = pd.read_csv(csv_path)
    mz_time_col = detect_multizone_time_column(df_raw, preferred_time_column)
    df_raw["timestamp"] = pd.to_datetime(df_raw[mz_time_col], errors="coerce")
    if df_raw["timestamp"].isna().all():
        raise ValueError(f"Timestamp multizone non parseabili in {csv_path}.")
    mz_ts_valid = pd.DatetimeIndex(df_raw["timestamp"].dropna())
    if len(mz_ts_valid) > 0:
        mz_years = sorted(set(int(y) for y in mz_ts_valid.year))
        if len(mz_years) == 1 and mz_years[0] != int(target_year):
            rebased = rebase_datetime_year(df_raw["timestamp"], int(target_year))
            if float(rebased.notna().mean()) >= 0.9:
                df_raw["timestamp"] = rebased

    mz_air, mz_op = detect_multizone_temperature_columns(df_raw.columns)
    if not mz_air and not mz_op:
        raise ValueError(
            f"Nel CSV multizone non trovo colonne temperatura compatibili in {csv_path}."
        )
    df = df_raw.set_index("timestamp").sort_index()
    return df_raw, df, mz_air, mz_op


def main() -> None:
    args = parse_args()
    ep_path = Path(args.energyplus_csv).expanduser().resolve()
    mz_path = resolve_multizone_csv(args.multizone_csv)
    mz_hybrid_path = resolve_multizone_hybrid_csv(args.multizone_hybrid_csv)
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not ep_path.exists():
        raise FileNotFoundError(f"CSV EnergyPlus non trovato: {ep_path}")

    df_ep_raw = pd.read_csv(ep_path)
    date_col = "Date/Time"
    if date_col not in df_ep_raw.columns:
        raise KeyError(f"Colonna '{date_col}' non trovata nel CSV EnergyPlus.")

    ep_air, ep_op = detect_energyplus_temperature_columns(df_ep_raw.columns)
    ep_outdoor_col = detect_energyplus_outdoor_temperature_column(df_ep_raw.columns)
    if not ep_air:
        raise ValueError(
            "Nel CSV EnergyPlus non trovo colonne 'Zone Mean Air Temperature'."
        )

    df_ep_raw["timestamp"] = parse_energyplus_datetime(
        df_ep_raw[date_col], year=args.year, shift_interval_end=not args.no_ep_shift
    )
    df_ep = df_ep_raw.set_index("timestamp").sort_index()

    df_mz_raw, df_mz, mz_air, mz_op = load_multizone_dataframe(
        mz_path, args.multizone_time_column, args.year
    )
    if not mz_air and not mz_op:
        raise ValueError("Nel CSV multizone V1 non trovo colonne temperatura.")
    mz_zones_available = sorted(set(mz_air) | set(mz_op))
    if not mz_zones_available:
        raise ValueError("Nel CSV multizone V1 non trovo zone utili per il confronto.")

    df_mz_hybrid = None
    mz_hybrid_air: Dict[str, str] = {}
    mz_hybrid_op: Dict[str, str] = {}
    if mz_hybrid_path is not None and mz_hybrid_path.exists():
        _, df_mz_hybrid, mz_hybrid_air, mz_hybrid_op = load_multizone_dataframe(
            mz_hybrid_path, args.multizone_hybrid_time_column, args.year
        )

    zone_map = parse_zone_map(
        args.zone_map, mz_zones_available, list(ep_air.keys())
    )

    common_index = df_mz.index.intersection(df_ep.index)
    if df_mz_hybrid is not None:
        common_index = common_index.intersection(df_mz_hybrid.index)
    if len(common_index) == 0:
        raise ValueError("Nessun timestamp comune tra CSV EnergyPlus e multizone.")

    df_mz = df_mz.loc[common_index]
    df_ep = df_ep.loc[common_index]
    if df_mz_hybrid is not None:
        df_mz_hybrid = df_mz_hybrid.loc[common_index]
    common_index_cons = common_index

    hourly_frames = []
    hourly_v1 = build_hourly_comparison(
        df_mz=df_mz,
        df_ep=df_ep,
        zone_map=zone_map,
        mz_air=mz_air,
        mz_op=mz_op,
        ep_air=ep_air,
        ep_op=ep_op,
        ep_outdoor_col=ep_outdoor_col,
        method_label="ISO_V1",
    )
    if hourly_v1.empty:
        raise ValueError(
            "Nessuna coppia di colonne temperatura in comune tra EnergyPlus e CSV multizone V1."
        )
    hourly_frames.append(hourly_v1)
    if df_mz_hybrid is not None and (mz_hybrid_air or mz_hybrid_op):
        hourly_v2 = build_hourly_comparison(
            df_mz=df_mz_hybrid,
            df_ep=df_ep,
            zone_map=zone_map,
            mz_air=mz_hybrid_air,
            mz_op=mz_hybrid_op,
            ep_air=ep_air,
            ep_op=ep_op,
            ep_outdoor_col=ep_outdoor_col,
            method_label="ISO_V2_HYBRID",
        )
        if not hourly_v2.empty:
            hourly_frames.append(hourly_v2)
    hourly = pd.concat(hourly_frames, ignore_index=True)
    summary = build_metrics(hourly)
    monthly_eval = build_monthly_evaluation(hourly)
    annual_eval = build_annual_evaluation(hourly)

    df_mz_methods = {
        "ISO_V1": df_mz.loc[common_index_cons],
    }
    if df_mz_hybrid is not None:
        df_mz_methods["ISO_V2_HYBRID"] = df_mz_hybrid.loc[common_index_cons]
    cons_hourly, cons_summary, cons_meta = build_ideal_consumption_comparison(
        df_mz_methods=df_mz_methods,
        df_ep=df_ep.loc[common_index_cons],
        df_ep_raw=df_ep_raw,
    )
    driver_summary = build_consumption_driver_summary(
        df_mz=df_mz.loc[common_index_cons],
        df_ep=df_ep.loc[common_index_cons],
        ep_outdoor_col=ep_outdoor_col,
    )

    hourly_path = out_dir / f"{args.out_prefix}_hourly.csv"
    summary_path = out_dir / f"{args.out_prefix}_summary.csv"
    html_path = out_dir / f"{args.out_prefix}.html"
    monthly_eval_csv_path = out_dir / f"{args.out_prefix}_monthly_evaluation.csv"
    annual_eval_csv_path = out_dir / f"{args.out_prefix}_annual_evaluation.csv"
    monthly_annual_html_path = out_dir / f"{args.out_prefix}_monthly_annual_evaluation.html"
    cons_hourly_csv_path = out_dir / f"{args.out_prefix}_consumi_ideali_orari.csv"
    cons_summary_csv_path = out_dir / f"{args.out_prefix}_consumi_ideali_summary.csv"
    driver_summary_csv_path = out_dir / f"{args.out_prefix}_consumi_ideali_vettori_dominanti.csv"
    cons_html_path = out_dir / f"{args.out_prefix}_consumi_ideali.html"

    hourly.to_csv(hourly_path, index=False)
    summary.to_csv(summary_path, index=False)
    monthly_eval.to_csv(monthly_eval_csv_path, index=False)
    annual_eval.to_csv(annual_eval_csv_path, index=False)
    cons_hourly.to_csv(cons_hourly_csv_path, index=False)
    cons_summary.to_csv(cons_summary_csv_path, index=False)
    driver_summary.to_csv(driver_summary_csv_path, index=False)
    html_ok = save_html_plot(hourly, html_path)
    monthly_annual_html_ok = save_monthly_annual_evaluation_html(
        monthly_eval, annual_eval, monthly_annual_html_path
    )
    subtitle_parts = [
        f"EP H source: {cons_meta['ep_heating_source']}",
        f"EP C source: {cons_meta['ep_cooling_source']}",
    ]
    source_specs = [
        ("EnergyPlus", "P_heat_energyplus_W", "P_cool_energyplus_W"),
        ("ISO V1", "P_heat_iso_v1_W", "P_cool_iso_v1_W"),
    ]
    if "iso_v1_source" in cons_meta:
        subtitle_parts.append(f"ISO V1 source: {cons_meta['iso_v1_source']}")
    if "iso_v2_hybrid_source" in cons_meta:
        subtitle_parts.append(f"ISO V2 source: {cons_meta['iso_v2_hybrid_source']}")
        source_specs.append(("ISO V2 Hybrid", "P_heat_iso_v2_hybrid_W", "P_cool_iso_v2_hybrid_W"))
    subtitle = " | ".join(subtitle_parts)
    cons_html_ok = save_consumption_html(
        cons_hourly,
        cons_html_path,
        subtitle=subtitle,
        sources=source_specs,
        driver_summary=driver_summary,
    )

    print(f"EnergyPlus CSV: {ep_path}")
    print(f"Multizone V1 CSV : {mz_path}")
    print(f"Multizone V2 CSV : {mz_hybrid_path if mz_hybrid_path is not None else 'not found / not provided'}")
    print(f"Timestamp comuni: {len(common_index)}")
    print(
        "Timestamp comuni consumi (EP / multizone disponibili): "
        f"{len(common_index_cons)}"
    )
    print("Zone mapping:")
    for mz_zone, ep_zone in zone_map.items():
        print(f"  - {mz_zone} -> {ep_zone}")
    consumption_sources = [
        f"EP_H={cons_meta['ep_heating_source']}",
        f"EP_C={cons_meta['ep_cooling_source']}",
    ]
    if "iso_v1_source" in cons_meta:
        consumption_sources.append(f"V1={cons_meta['iso_v1_source']}")
    if "iso_v2_hybrid_source" in cons_meta:
        consumption_sources.append(f"V2={cons_meta['iso_v2_hybrid_source']}")
    print("Consumption sources: " + " | ".join(consumption_sources))
    print(f"Saved hourly comparison: {hourly_path}")
    print(f"Saved summary: {summary_path}")
    print(f"Saved monthly evaluation: {monthly_eval_csv_path}")
    print(f"Saved annual evaluation: {annual_eval_csv_path}")
    print(f"Saved ideal consumptions hourly: {cons_hourly_csv_path}")
    print(f"Saved ideal consumptions summary: {cons_summary_csv_path}")
    print(f"Saved ideal consumptions dominant vectors: {driver_summary_csv_path}")
    if html_ok:
        print(f"Saved HTML plot: {html_path}")
    if monthly_annual_html_ok:
        print(f"Saved HTML monthly/annual evaluation plot: {monthly_annual_html_path}")
    if cons_html_ok:
        print(f"Saved HTML ideal consumptions hourly plot: {cons_html_path}")


if __name__ == "__main__":
    main()
    
