"""Cooling-system operating conditions according to EN 16798-9:2017.

The module covers the water-based cooling-system hand-off calculations from
EN 16798-9, Modules M4-1 and M4-4. It is intentionally small: emission,
distribution, storage and generation are calculated by their own modules, while
this calculator supplies the required chilled-water temperatures, volume flow
and generation-side cooling request used to connect those modules.

Implemented clauses:

* 6.4.2 / 7.4.2: required generation outlet and distribution flow
  temperatures for constant or outdoor-compensated control;
* 7.4.2.3 and 7.4.2.4: distribution volume flow and return temperature;
* 7.4.3.1 and 7.4.3.2: cooling request passed towards storage/generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


_KWH_EPS = 1e-12
_WATER_HEAT_CAPACITY_DENSITY_KWH_M3K = 1.16


@dataclass
class CoolingSystemSimulationResult:
    """Container returned by :class:`CoolingSystemCalculator`."""

    timeseries: pd.DataFrame
    summary: dict[str, float]
    inputs: dict[str, Any]


class CoolingSystemCalculator:
    """EN 16798-9:2017 water-based cooling-system connector."""

    def __init__(self, input_data: dict[str, Any] | None = None):
        self.input_data: dict[str, Any] = dict(input_data or {})
        self._load_options()

    def run_timeseries(self, data: pd.DataFrame) -> CoolingSystemSimulationResult:
        """Run the cooling-system operating-condition calculation."""

        prepared = self._prepare_timeseries(data)
        results = self._simulate(prepared)
        summary = self._summarize(results)
        return CoolingSystemSimulationResult(
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

        self.system_type = str(cfg.get("system_type", "water")).lower()
        if self.system_type not in {"water", "dx", "air"}:
            raise ValueError("system_type must be 'water', 'dx' or 'air'.")

        self.generator_temperature_control = str(
            cfg.get("generator_temperature_control", "VARIABLE")
        ).upper()
        self.distribution_temperature_control = str(
            cfg.get("distribution_temperature_control", "CONST")
        ).upper()
        self.distribution_flow_control = str(
            cfg.get("distribution_flow_control", "VARIABLE")
        ).upper()

        allowed_temp = {"CONST", "ODA_COMP", "MAX_TMP"}
        if self.distribution_temperature_control not in allowed_temp:
            raise ValueError(
                "distribution_temperature_control must be CONST, ODA_COMP or MAX_TMP."
            )
        if self.distribution_flow_control not in {"CONST", "VARIABLE"}:
            raise ValueError("distribution_flow_control must be CONST or VARIABLE.")

        self.theta_C_gen_out_set_C = float(cfg.get("theta_C_gen_out_set_C", 7.0))
        self.theta_C_dis_flw_set_C = float(
            cfg.get("theta_C_dis_flw_set_C", cfg.get("supply_temperature_C", 7.0))
        )
        self.theta_C_dis_flw_set_min_C = float(
            cfg.get("theta_C_dis_flw_set_min_C", 6.0)
        )
        self.theta_C_dis_flw_set_max_C = float(
            cfg.get("theta_C_dis_flw_set_max_C", 18.0)
        )
        self.outdoor_compensation_slope = float(
            cfg.get("outdoor_compensation_slope", cfg.get("f_e", 0.0))
        )
        self.outdoor_compensation_offset_K = float(
            cfg.get("outdoor_compensation_offset_K", cfg.get("delta_theta_off_K", 7.0))
        )
        self.design_deltaT_K = _positive_float(
            cfg.get("design_deltaT_K", 5.0), "design_deltaT_K"
        )
        self.design_flow_m3_h = max(float(cfg.get("design_flow_m3_h", 0.0)), 0.0)
        self.design_cooling_load_kW = max(
            float(cfg.get("design_cooling_load_kW", cfg.get("nominal_power_kW", 0.0))),
            0.0,
        )
        self.f_wat_C_aux_dis = _fraction(
            cfg.get("f_wat_C_aux_dis", cfg.get("cooling_aux_to_water_fraction", 0.0)),
            "f_wat_C_aux_dis",
        )
        self.simplified_distribution_loss_factor = _fraction(
            cfg.get("f_C_ls_dis", cfg.get("simplified_distribution_loss_factor", 0.0)),
            "f_C_ls_dis",
        )
        self.simplified_auxiliary_factor = _fraction(
            cfg.get("f_C_aux_dis", cfg.get("simplified_auxiliary_factor", 0.0)),
            "f_C_aux_dis",
        )

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
        out.loc[:, "T_op_C"] = _series_from_aliases(
            df, ["T_op", "operative_temperature_C", "T_zone_C"], default=np.nan
        ).astype(float)
        q_hc = _series_from_aliases(df, ["Q_HC"], default=0.0).astype(float)
        out.loc[:, "Q_C_dis_out_tot_req_kWh"] = self._demand_from_columns(
            df,
            kwh_aliases=[
                "Q_C_dis_out_tot_req_kWh",
                "Q_C_dis_out_kWh",
                "Q_C_em_in_kWh",
                "Q_C_kWh",
                "QC_kWh",
                "cooling_kWh",
                "space_cooling_kWh",
            ],
            raw_aliases=["Q_C", "Cooling_needs"],
            fallback=np.maximum(-q_hc, 0.0),
        )
        if self.system_type in {"dx", "air"}:
            out.loc[:, "theta_C_int_inc_C"] = _series_from_aliases(
                df, ["theta_C_int_inc_C", "cooling_setpoint_C"], default=26.0
            ).astype(float)
            out.loc[:, "theta_SUP_C_req_C"] = _series_from_aliases(
                df, ["theta_SUP_C_req_C", "supply_air_temperature_C"], default=14.0
            ).astype(float)
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

    def _simulate(self, prepared: pd.DataFrame) -> pd.DataFrame:
        out = prepared.copy(deep=True)

        if self.system_type == "dx":
            out.loc[:, "theta_C_gen_out_req_C"] = out["theta_C_int_inc_C"]
            out.loc[:, "theta_C_dis_in_flw_req_C"] = np.nan
            out.loc[:, "theta_C_dis_out_ret_req_C"] = np.nan
            out.loc[:, "q_V_C_dis_m3_h"] = 0.0
        elif self.system_type == "air":
            out.loc[:, "theta_C_gen_out_req_C"] = out["theta_SUP_C_req_C"]
            out.loc[:, "theta_C_dis_in_flw_req_C"] = np.nan
            out.loc[:, "theta_C_dis_out_ret_req_C"] = np.nan
            out.loc[:, "q_V_C_dis_m3_h"] = 0.0
        else:
            flow_temp = self._distribution_flow_temperature(out)
            out.loc[:, "theta_C_dis_in_flw_req_C"] = flow_temp
            if self.generator_temperature_control == "CONST":
                gen_out = pd.Series(self.theta_C_gen_out_set_C, index=out.index)
            else:
                gen_out = flow_temp
            out.loc[:, "theta_C_gen_out_req_C"] = gen_out
            out.loc[:, "q_V_C_dis_m3_h"] = self._volume_flow(out)
            out.loc[:, "theta_C_dis_out_ret_req_C"] = self._return_temperature(out)

        useful = out["Q_C_dis_out_tot_req_kWh"]
        out.loc[:, "Q_C_dis_ls_simplified_kWh"] = (
            useful * self.simplified_distribution_loss_factor
        )
        out.loc[:, "W_C_aux_dis_simplified_kWh"] = useful * self.simplified_auxiliary_factor
        out.loc[:, "Q_C_gen_in_req_kWh"] = (
            useful
            + out["Q_C_dis_ls_simplified_kWh"]
            + self.f_wat_C_aux_dis * out["W_C_aux_dis_simplified_kWh"]
        )

        out.loc[:, "theta_C_dis_supply_C"] = out["theta_C_dis_in_flw_req_C"]
        out.loc[:, "theta_C_dis_return_C"] = out["theta_C_dis_out_ret_req_C"]
        out.loc[:, "T_C_supply_C"] = out["theta_C_dis_in_flw_req_C"]
        out.loc[:, "T_C_return_C"] = out["theta_C_dis_out_ret_req_C"]
        out.loc[:, "T_C_sink_C"] = out["theta_C_gen_out_req_C"]
        return out

    def _distribution_flow_temperature(self, df: pd.DataFrame) -> pd.Series:
        if self.distribution_temperature_control == "CONST":
            return pd.Series(self.theta_C_dis_flw_set_C, index=df.index)
        if self.distribution_temperature_control == "ODA_COMP":
            raw = (
                self.outdoor_compensation_slope * df["T_ext_C"].astype(float)
                + self.outdoor_compensation_offset_K
            )
            return raw.clip(
                lower=self.theta_C_dis_flw_set_min_C,
                upper=self.theta_C_dis_flw_set_max_C,
            )
        return pd.Series(self.theta_C_dis_flw_set_C, index=df.index)

    def _volume_flow(self, df: pd.DataFrame) -> pd.Series:
        q = df["Q_C_dis_out_tot_req_kWh"].astype(float)
        hours = df["hours"].replace(0.0, np.nan).astype(float)
        load_kW = q / hours

        if self.distribution_flow_control == "CONST" and self.design_flow_m3_h > _KWH_EPS:
            return pd.Series(self.design_flow_m3_h, index=df.index).where(q > _KWH_EPS, 0.0)

        if self.design_flow_m3_h > _KWH_EPS and self.design_cooling_load_kW > _KWH_EPS:
            flow = self.design_flow_m3_h * load_kW / self.design_cooling_load_kW
            return flow.replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(
                lower=0.0,
                upper=self.design_flow_m3_h,
            )

        flow = q / (
            _WATER_HEAT_CAPACITY_DENSITY_KWH_M3K * self.design_deltaT_K * hours
        )
        return flow.replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(lower=0.0)

    def _return_temperature(self, df: pd.DataFrame) -> pd.Series:
        q = df["Q_C_dis_out_tot_req_kWh"].astype(float)
        hours = df["hours"].replace(0.0, np.nan).astype(float)
        flow = df["q_V_C_dis_m3_h"].replace(0.0, np.nan).astype(float)
        delta = q / (_WATER_HEAT_CAPACITY_DENSITY_KWH_M3K * flow * hours)
        delta = delta.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return df["theta_C_dis_in_flw_req_C"].astype(float) + delta

    def _summarize(self, results: pd.DataFrame) -> dict[str, float]:
        q = results["Q_C_dis_out_tot_req_kWh"]
        weights = q + _KWH_EPS
        summary = {
            "hours": float(results["hours"].sum()),
            "QC_dis_out_tot_req_kWh": float(q.sum()),
            "QC_gen_in_req_simplified_kWh": float(results["Q_C_gen_in_req_kWh"].sum()),
            "QC_dis_ls_simplified_kWh": float(
                results["Q_C_dis_ls_simplified_kWh"].sum()
            ),
            "WC_aux_dis_simplified_kWh": float(
                results["W_C_aux_dis_simplified_kWh"].sum()
            ),
            "theta_C_gen_out_req_mean_C": _weighted_mean(
                results["theta_C_gen_out_req_C"], weights
            ),
            "theta_C_dis_supply_mean_C": _weighted_mean(
                results["theta_C_dis_in_flw_req_C"], weights
            ),
            "theta_C_dis_return_mean_C": _weighted_mean(
                results["theta_C_dis_out_ret_req_C"], weights
            ),
            "q_V_C_dis_mean_m3_h": _weighted_mean(results["q_V_C_dis_m3_h"], weights),
            "q_V_C_dis_max_m3_h": float(results["q_V_C_dis_m3_h"].max()),
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
