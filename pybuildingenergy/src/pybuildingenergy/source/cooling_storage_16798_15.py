"""Cooling storage calculation according to EN 16798-15:2017.

The module implements the hourly chilled-water storage balance for Module M4-7.
It is designed to sit between cooling distribution and cooling generation:
users provide the cooling energy required by the distribution side and the
calculator returns the cooling energy that must be removed by the generator,
including storage heat gains and storage pump auxiliary energy.

Implemented clauses:

* 6.5.2: required storage inlet temperature;
* 6.5.3.4: heat gains from the generator loop, distribution loop and storage
  vessel;
* 6.5.3.6: storage pump auxiliary energy from transferred cooling energy;
* 6.5.3.7: recoverable thermal losses, with the cooling sign convention used by
  EN 16798-15.

Latent ice/PCM state tracking is outside this first implementation. The
``storage_type`` input is retained for audit visibility, and the numerical
calculation represents a chilled-water buffer tank with steady hourly losses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


_KWH_EPS = 1e-12
_WATER_HEAT_CAPACITY_DENSITY_KWH_M3K = 1.16


@dataclass
class CoolingStorageSimulationResult:
    """Container returned by :class:`CoolingStorageSystemCalculator`."""

    timeseries: pd.DataFrame
    summary: dict[str, float]
    inputs: dict[str, Any]


class CoolingStorageSystemCalculator:
    """EN 16798-15:2017 chilled-water storage calculator."""

    def __init__(self, input_data: dict[str, Any] | None = None):
        self.input_data: dict[str, Any] = dict(input_data or {})
        self._load_options()

    def run_timeseries(self, data: pd.DataFrame) -> CoolingStorageSimulationResult:
        """Run the hourly cooling-storage calculation."""

        prepared = self._prepare_timeseries(data)
        results = self._simulate(prepared)
        summary = self._summarize(results)
        return CoolingStorageSimulationResult(
            timeseries=results,
            summary=summary,
            inputs=dict(self.input_data),
        )

    def _load_options(self) -> None:
        cfg = self.input_data
        self.default_time_step_h = _positive_float(
            cfg.get("time_step_hours", 1.0), "time_step_hours"
        )
        self.demand_unit = str(cfg.get("demand_unit", "kWh")).lower()
        if self.demand_unit not in {"wh", "kwh"}:
            raise ValueError("demand_unit must be 'Wh' or 'kWh'.")

        self.enabled = bool(cfg.get("enabled", True))
        self.storage_type = str(cfg.get("storage_type", "STO_TYPE_CW")).upper()
        if self.storage_type not in {"STO_TYPE_CW", "STO_TYPE_ICE", "STO_TYPE_PCM"}:
            raise ValueError(
                "storage_type must be STO_TYPE_CW, STO_TYPE_ICE or STO_TYPE_PCM."
            )
        self.location = str(cfg.get("location", cfg.get("CLG_STO_LOC", "NC"))).upper()
        self.theta_C_sto_C = float(cfg.get("theta_C_sto_C", cfg.get("storage_temperature_C", 7.0)))
        self.theta_C_gen_out_C = float(
            cfg.get("theta_C_gen_out_C", cfg.get("generator_outlet_temperature_C", 7.0))
        )
        self.theta_C_sto_out_C = float(
            cfg.get("theta_C_sto_out_C", cfg.get("storage_output_temperature_C", 7.0))
        )
        self.theta_C_sto_return_C = float(
            cfg.get("theta_C_sto_return_C", cfg.get("storage_return_temperature_C", 12.0))
        )
        self.delta_theta_C_sto_gen_flw_K = float(
            cfg.get("delta_theta_C_sto_gen_flw_K", 2.0)
        )
        self.ambient_temperature_C = float(cfg.get("ambient_temperature_C", 20.0))
        self.conditioned_ambient_temperature_C = float(
            cfg.get("conditioned_ambient_temperature_C", 26.0)
        )
        self.storage_volume_l = max(float(cfg.get("storage_volume_l", 100.0)), 0.0)

        h_default = 0.01 * self.storage_volume_l
        self.H_C_sto_tot_ls_W_K = max(
            float(cfg.get("H_C_sto_tot_ls_W_K", cfg.get("standby_loss_coefficient_W_K", h_default))),
            0.0,
        )
        self.H_C_sto_out_ls_W_K = max(
            float(
                cfg.get(
                    "H_C_sto_out_ls_W_K",
                    cfg.get("generator_loop_loss_coefficient_W_K", 0.3 * self.H_C_sto_tot_ls_W_K),
                )
            ),
            0.0,
        )
        self.H_C_sto_in_ls_W_K = max(
            float(
                cfg.get(
                    "H_C_sto_in_ls_W_K",
                    cfg.get("distribution_loop_loss_coefficient_W_K", 0.3 * self.H_C_sto_tot_ls_W_K),
                )
            ),
            0.0,
        )

        self.f_C_sto_ls_rbl = _fraction(
            cfg.get("f_C_sto_ls_rbl", cfg.get("thermal_loss_recoverable_fraction", 0.0)),
            "f_C_sto_ls_rbl",
        )
        self.f_C_aux_ls_rbl = _fraction(
            cfg.get("f_C_aux_ls_rbl", cfg.get("auxiliary_loss_recoverable_fraction", 0.75)),
            "f_C_aux_ls_rbl",
        )
        self.auxiliary_to_medium_fraction = _fraction(
            cfg.get("auxiliary_to_medium_fraction", 1.0),
            "auxiliary_to_medium_fraction",
        )

        self.input_pump_power_kW = max(float(cfg.get("input_pump_power_kW", 0.0)), 0.0)
        self.input_pump_flow_m3_h = max(float(cfg.get("input_pump_flow_m3_h", 0.0)), 0.0)
        self.input_pump_deltaT_K = _positive_float(
            cfg.get("input_pump_deltaT_K", 5.0), "input_pump_deltaT_K"
        )
        self.output_pump_power_kW = max(float(cfg.get("output_pump_power_kW", 0.0)), 0.0)
        self.output_pump_flow_m3_h = max(float(cfg.get("output_pump_flow_m3_h", 0.0)), 0.0)
        self.output_pump_deltaT_K = _positive_float(
            cfg.get("output_pump_deltaT_K", 5.0), "output_pump_deltaT_K"
        )
        self.operation_mode = str(cfg.get("operation_mode", "demand")).lower()
        self.control_mode = str(cfg.get("control_mode", cfg.get("CLG_STO_CTRL", "CONT"))).upper()
        if self.control_mode not in {"CONT", "TIME", "TEMP", "LOAD_PRED"}:
            raise ValueError("control_mode must be CONT, TIME, TEMP or LOAD_PRED.")

    def _prepare_timeseries(self, data: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(data, pd.DataFrame):
            raise TypeError("data must be a pandas DataFrame.")
        if data.empty:
            raise ValueError("data must contain at least one row.")

        df = data.copy()
        out = pd.DataFrame(index=df.index)
        out.loc[:, "hours"] = self._time_step_hours(df)
        out.loc[:, "T_ext_C"] = _series_from_aliases(
            df, ["T_ext", "theta_ext", "outdoor_temperature_C", "T_external_C"], default=np.nan
        ).astype(float)
        q_hc = _series_from_aliases(df, ["Q_HC"], default=0.0).astype(float)
        out.loc[:, "Q_C_sto_out_kWh"] = self._demand_from_columns(
            df,
            kwh_aliases=[
                "Q_C_sto_out_kWh",
                "Q_C_dis_in_kWh",
                "Q_C_kWh",
                "QC_kWh",
                "cooling_kWh",
                "space_cooling_kWh",
            ],
            raw_aliases=["Q_C", "Cooling_needs"],
            fallback=np.maximum(-q_hc, 0.0),
        )
        out.loc[:, "theta_C_dis_in_req_C"] = _series_from_aliases(
            df,
            ["theta_C_dis_in_flw_req_C", "theta_C_dis_supply_C", "T_C_sink_C"],
            default=self.theta_C_sto_out_C,
        ).astype(float)
        out.loc[:, "theta_C_gen_out_C"] = _series_from_aliases(
            df,
            ["theta_C_gen_out_C", "theta_C_gen_out_req_C", "T_C_sink_C"],
            default=self.theta_C_gen_out_C,
        ).astype(float)
        out.loc[:, "theta_C_sto_out_C"] = _series_from_aliases(
            df,
            ["theta_C_sto_out_C", "theta_C_dis_supply_C", "T_C_sink_C"],
            default=self.theta_C_sto_out_C,
        ).astype(float)
        out.loc[:, "theta_C_sto_return_C"] = _series_from_aliases(
            df,
            ["theta_C_sto_return_C", "theta_C_dis_return_C", "T_C_return_C"],
            default=self.theta_C_sto_return_C,
        ).astype(float)
        out.loc[:, "theta_C_sto_C"] = _series_from_aliases(
            df, ["theta_C_sto_C", "storage_temperature_C"], default=self.theta_C_sto_C
        ).astype(float)
        out.loc[:, "theta_C_sto_amb_C"] = self._ambient_temperature(df, out)
        return out

    def _demand_from_columns(
        self,
        df: pd.DataFrame,
        kwh_aliases: list[str],
        raw_aliases: list[str],
        fallback: pd.Series | np.ndarray | float,
    ) -> pd.Series:
        series = _series_from_aliases(df, kwh_aliases, default=None)
        if series is not None:
            return series.astype(float).clip(lower=0.0)

        raw = _series_from_aliases(df, raw_aliases, default=None)
        if raw is not None:
            values = raw.astype(float)
            if self.demand_unit == "wh":
                values = values / 1000.0
            return values.clip(lower=0.0)

        if isinstance(fallback, pd.Series):
            return fallback.reindex(df.index).astype(float).clip(lower=0.0)
        return pd.Series(fallback, index=df.index, dtype=float).clip(lower=0.0)

    def _ambient_temperature(self, source: pd.DataFrame, prepared: pd.DataFrame) -> pd.Series:
        direct = _series_from_aliases(
            source, ["theta_C_sto_amb_C", "cooling_storage_ambient_temperature_C"], default=None
        )
        if direct is not None:
            return direct.astype(float)
        if self.location in {"EXT", "CLG_STO_LOC_EXT", "EXTERNAL", "OUTDOOR"}:
            return prepared["T_ext_C"].fillna(self.ambient_temperature_C).astype(float)
        if self.location in {"CND", "CLG_STO_LOC_CND", "CONDITIONED"}:
            return pd.Series(self.conditioned_ambient_temperature_C, index=source.index)
        return pd.Series(self.ambient_temperature_C, index=source.index)

    def _simulate(self, prepared: pd.DataFrame) -> pd.DataFrame:
        out = prepared.copy(deep=True)
        q_out = out["Q_C_sto_out_kWh"].astype(float)

        if not self.enabled:
            out.loc[:, "theta_C_sto_in_req_C"] = out["theta_C_dis_in_req_C"]
            out.loc[:, "Q_C_sto_out_ls_kWh"] = 0.0
            out.loc[:, "Q_C_sto_in_ls_kWh"] = 0.0
            out.loc[:, "Q_C_sto_ls_kWh"] = 0.0
            out.loc[:, "Q_C_sto_ls_tot_kWh"] = 0.0
            out.loc[:, "W_C_sto_aux_in_kWh"] = 0.0
            out.loc[:, "W_C_sto_aux_out_kWh"] = 0.0
            out.loc[:, "W_C_sto_aux_kWh"] = 0.0
            out.loc[:, "Q_C_sto_aux_rvd_kWh"] = 0.0
            out.loc[:, "Q_C_sto_aux_ls_rbl_kWh"] = 0.0
            out.loc[:, "Q_C_sto_ls_tot_rbl_kWh"] = 0.0
            out.loc[:, "Q_C_sto_in_kWh"] = q_out
            out.loc[:, "t_C_sto_pmp_in_h"] = 0.0
            out.loc[:, "t_C_sto_pmp_out_h"] = 0.0
            out.loc[:, "V_C_sto_l"] = self.storage_volume_l
            out.loc[:, "H_C_sto_tot_ls_W_K"] = 0.0
            return out

        out.loc[:, "theta_C_sto_in_req_C"] = out["theta_C_dis_in_req_C"].where(
            q_out >= 0.0,
            out["theta_C_sto_C"] - self.delta_theta_C_sto_gen_flw_K,
        )

        hours = out["hours"].astype(float)
        ambient = out["theta_C_sto_amb_C"].astype(float)
        gen_temp = out["theta_C_gen_out_C"].astype(float)
        out_temp = out["theta_C_sto_out_C"].astype(float)
        storage_temp = out["theta_C_sto_C"].astype(float)

        out.loc[:, "Q_C_sto_out_ls_kWh"] = (
            self.H_C_sto_out_ls_W_K * (ambient - gen_temp).clip(lower=0.0) * hours / 1000.0
        )
        out.loc[:, "Q_C_sto_in_ls_kWh"] = (
            self.H_C_sto_in_ls_W_K * (ambient - out_temp).clip(lower=0.0) * hours / 1000.0
        )
        out.loc[:, "Q_C_sto_ls_kWh"] = (
            self.H_C_sto_tot_ls_W_K
            * (ambient - storage_temp).clip(lower=0.0)
            * hours
            / 1000.0
        )
        out.loc[:, "Q_C_sto_ls_tot_kWh"] = (
            out["Q_C_sto_out_ls_kWh"]
            + out["Q_C_sto_in_ls_kWh"]
            + out["Q_C_sto_ls_kWh"]
        )

        t_out = self._pump_runtime(q_out, hours, self.output_pump_flow_m3_h, self.output_pump_deltaT_K)
        q_to_generator = q_out + out["Q_C_sto_ls_tot_kWh"]
        t_in = self._pump_runtime(
            q_to_generator,
            hours,
            self.input_pump_flow_m3_h,
            self.input_pump_deltaT_K,
        )
        out.loc[:, "t_C_sto_pmp_in_h"] = t_in
        out.loc[:, "t_C_sto_pmp_out_h"] = t_out
        out.loc[:, "W_C_sto_aux_in_kWh"] = t_in * self.input_pump_power_kW
        out.loc[:, "W_C_sto_aux_out_kWh"] = t_out * self.output_pump_power_kW
        out.loc[:, "W_C_sto_aux_kWh"] = out["W_C_sto_aux_in_kWh"] + out["W_C_sto_aux_out_kWh"]

        aux_to_fluid = out["W_C_sto_aux_kWh"] * self.auxiliary_to_medium_fraction
        out.loc[:, "Q_C_sto_aux_rvd_kWh"] = -aux_to_fluid
        out.loc[:, "Q_C_sto_aux_ls_rbl_kWh"] = -out["W_C_sto_aux_kWh"] * self.f_C_aux_ls_rbl
        out.loc[:, "Q_C_sto_ls_tot_rbl_kWh"] = (
            -out["Q_C_sto_ls_tot_kWh"] * self.f_C_sto_ls_rbl
            + out["Q_C_sto_aux_ls_rbl_kWh"]
        )
        out.loc[:, "Q_C_sto_in_kWh"] = (q_out + out["Q_C_sto_ls_tot_kWh"] + aux_to_fluid).clip(lower=0.0)
        out.loc[:, "V_C_sto_l"] = self.storage_volume_l
        out.loc[:, "H_C_sto_tot_ls_W_K"] = self.H_C_sto_tot_ls_W_K
        out.loc[:, "H_C_sto_out_ls_W_K"] = self.H_C_sto_out_ls_W_K
        out.loc[:, "H_C_sto_in_ls_W_K"] = self.H_C_sto_in_ls_W_K
        out.loc[:, "T_C_sink_C"] = out["theta_C_sto_in_req_C"]
        return out

    def _pump_runtime(
        self,
        q_kWh: pd.Series,
        hours: pd.Series,
        flow_m3_h: float,
        deltaT_K: float,
    ) -> pd.Series:
        if flow_m3_h <= _KWH_EPS:
            return pd.Series(0.0, index=q_kWh.index)
        if self.operation_mode == "continuous":
            return hours
        power_kW = _WATER_HEAT_CAPACITY_DENSITY_KWH_M3K * flow_m3_h * deltaT_K
        runtime = q_kWh / power_kW
        return runtime.replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(
            lower=0.0,
            upper=hours,
        )

    def _summarize(self, results: pd.DataFrame) -> dict[str, float]:
        q = results["Q_C_sto_out_kWh"]
        weights = q + _KWH_EPS
        summary = {
            "hours": float(results["hours"].sum()),
            "QC_sto_out_kWh": float(results["Q_C_sto_out_kWh"].sum()),
            "QC_sto_in_kWh": float(results["Q_C_sto_in_kWh"].sum()),
            "QC_sto_ls_kWh": float(results["Q_C_sto_ls_kWh"].sum()),
            "QC_sto_out_ls_kWh": float(results["Q_C_sto_out_ls_kWh"].sum()),
            "QC_sto_in_ls_kWh": float(results["Q_C_sto_in_ls_kWh"].sum()),
            "QC_sto_ls_tot_kWh": float(results["Q_C_sto_ls_tot_kWh"].sum()),
            "QC_sto_ls_tot_rbl_kWh": float(results["Q_C_sto_ls_tot_rbl_kWh"].sum()),
            "WC_sto_aux_kWh": float(results["W_C_sto_aux_kWh"].sum()),
            "QC_sto_aux_rvd_kWh": float(results["Q_C_sto_aux_rvd_kWh"].sum()),
            "theta_C_sto_mean_C": _weighted_mean(results["theta_C_sto_C"], weights),
            "theta_C_sto_amb_mean_C": _weighted_mean(results["theta_C_sto_amb_C"], weights),
            "e_C_sto": _ratio(
                float(results["Q_C_sto_in_kWh"].sum()),
                float(results["Q_C_sto_out_kWh"].sum()),
            ),
        }
        return summary

    def _time_step_hours(self, df: pd.DataFrame) -> pd.Series:
        step = _series_from_aliases(df, ["time_step_hours", "dt_h"], default=np.nan)
        if not step.isna().all():
            return step.astype(float).clip(lower=0.0)

        if isinstance(df.index, pd.DatetimeIndex) and len(df.index) > 1:
            diffs = df.index.to_series().diff().dt.total_seconds().dropna() / 3600.0
            if not diffs.empty and np.isfinite(diffs.median()) and diffs.median() > 0:
                return pd.Series(float(diffs.median()), index=df.index)

        return pd.Series(self.default_time_step_h, index=df.index)


def _series_from_aliases(
    df: pd.DataFrame,
    aliases: list[str],
    default: float | None,
) -> pd.Series | None:
    for alias in aliases:
        if alias in df.columns:
            return df[alias]
    if default is None:
        return None
    return pd.Series(default, index=df.index, dtype=float)


def _positive_float(value: Any, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive number.")
    return result


def _fraction(value: Any, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result < 0.0 or result > 1.0:
        raise ValueError(f"{name} must be between 0 and 1.")
    return result


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    v = values.astype(float)
    w = weights.astype(float)
    mask = v.notna() & w.notna() & (w > 0)
    if not mask.any():
        return float("nan")
    return float(np.average(v[mask], weights=w[mask]))


def _ratio(numerator: float, denominator: float) -> float:
    if abs(denominator) <= _KWH_EPS:
        return float("nan")
    return numerator / denominator
