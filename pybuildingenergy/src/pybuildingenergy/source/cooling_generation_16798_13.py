"""Cooling generation calculation according to EN 16798-13:2017.

The module implements the compression cooling-generator path from EN 16798-13,
Module M4-8. It is intended to be used for the cooling side of reversible heat
pumps or chillers after emission, distribution and optional cooling storage have
calculated the cooling energy to be removed.

Implemented clauses:

* 6.4.2.1: condenser/source and generation outlet temperatures;
* 6.4.2.2: optional free-cooling operating factor;
* 6.4.2.3: available cooling extraction and part-load ratio;
* 6.4.3.1 and 6.4.3.2: cooling removed, rejected heat and compressor
  electricity using EER;
* 6.4.3.5: generator auxiliary electricity.

Manufacturer or project-specific performance maps are preferred. If a map is
not provided, the fallback uses a nominal EER with the EN 16798-13 nominal-EER
temperature correction form.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .heat_pump_15316_4_2 import _coerce_performance_map, _interpolate_performance, _bilinear_or_linear
from .performance_14511_14825 import en14825_part_load_factor


_KWH_EPS = 1e-12
_T0_ABS_K = 273.15


@dataclass
class CoolingGenerationSimulationResult:
    """Container returned by :class:`CoolingGenerationSystemCalculator`."""

    timeseries: pd.DataFrame
    summary: dict[str, float]
    inputs: dict[str, Any]


def _build_pivot_arrays(
    performance_map: "pd.DataFrame",
    column: str,
) -> tuple["np.ndarray", "np.ndarray", "np.ndarray"] | None:
    """Build sorted pivot arrays for bilinear interpolation.

    Returns (sources, sinks, values) suitable for _bilinear_or_linear,
    or None if the pivot contains NaN (scattered map â€” use IDW fallback).
    Pre-building once avoids rebuilding the pivot on every timestep.
    """
    pivot = performance_map.pivot_table(
        index="source_temperature_C",
        columns="sink_temperature_C",
        values=column,
        aggfunc="mean",
    ).sort_index().sort_index(axis=1)
    if pivot.isna().any().any():
        return None  # scattered map â€” fall back to per-call _interpolate_performance
    return (
        pivot.index.to_numpy(dtype=float),
        pivot.columns.to_numpy(dtype=float),
        pivot.to_numpy(dtype=float),
    )

class CoolingGenerationSystemCalculator:
    """EN 16798-13:2017 compression cooling-generation calculator."""

    def __init__(self, input_data: dict[str, Any] | None = None):
        self.input_data: dict[str, Any] = dict(input_data or {})
        self._load_options()

    def run_timeseries(self, data: pd.DataFrame) -> CoolingGenerationSimulationResult:
        """Run the hourly cooling-generation calculation."""

        prepared = self._prepare_timeseries(data)
        results = self._simulate(prepared)
        summary = self._summarize(results)
        return CoolingGenerationSimulationResult(
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

        self.generation_type = str(cfg.get("GEN_TYPE", cfg.get("generation_type", "COMP"))).upper()
        if self.generation_type != "COMP":
            raise NotImplementedError("Only compression cooling generators are implemented.")
        self.heat_rejection_type = str(
            cfg.get("HEAT_REJ_TYPE", cfg.get("heat_rejection_type", "AIR_C_COND"))
        ).upper()
        allowed_rejection = {"AIR_C_COND", "DRY", "WET", "HYBRID", "OTHER"}
        if self.heat_rejection_type not in allowed_rejection:
            raise ValueError(
                "heat_rejection_type must be AIR_C_COND, DRY, WET, HYBRID or OTHER."
            )

        self.performance_map = _coerce_performance_map(
            cfg.get("cooling_performance_map", cfg.get("performance_map")),
            performance_column="eer",
            service_name="cooling_generation",
            required=False,
        )
        self.nominal_capacity_kW = max(
            float(cfg.get("nominal_capacity_kW", cfg.get("Phi_C_gen_n_kW", 0.0))),
            0.0,
        )
        self.nominal_eer = _optional_positive_float(
            cfg.get("nominal_eer", cfg.get("EER_n"))
        )
        self.theta_C_gen_out_limit_C = float(
            cfg.get("theta_C_gen_out_limit_C", cfg.get("theta_C_gen_out_lim_C", 5.0))
        )
        self.theta_C_gen_out_set_C = float(
            cfg.get("theta_C_gen_out_set_C", cfg.get("cooling_sink_temperature_C", 7.0))
        )
        self.theta_C_evap_out_nominal_C = float(
            cfg.get("theta_C_evap_out_nominal_C", cfg.get("theta_C_evap_out_n_C", 7.0))
        )
        self.theta_cond_in_nominal_C = float(
            cfg.get("theta_cond_in_nominal_C", cfg.get("theta_cond_in_n_C", 35.0))
        )
        self.free_cooling_enabled = bool(
            cfg.get("free_cooling_enabled", str(cfg.get("FREE_COOL_OP", "NO")).upper() == "YES")
        )
        self.free_cooling_deltaT_K = max(
            float(cfg.get("free_cooling_deltaT_K", cfg.get("delta_theta_fc_K", 4.0))),
            0.0,
        )
        self.heat_rejection_deltaT_K = float(
            cfg.get("heat_rejection_deltaT_K", cfg.get("delta_theta_hr_K", 0.0))
        )
        self.heat_rejection_loop_deltaT_K = float(
            cfg.get("heat_rejection_loop_deltaT_K", cfg.get("delta_theta_ls_dis_hr_K", 0.0))
        )
        self.wet_bulb_offset_K = float(cfg.get("wet_bulb_offset_K", 3.0))
        self.other_sink_temperature_C = float(cfg.get("other_sink_temperature_C", 12.0))
        self.minimum_part_load_ratio = max(
            float(cfg.get("minimum_part_load_ratio", cfg.get("f_C_PL_min", 0.0))),
            0.0,
        )
        self.part_load_performance_method = str(
            cfg.get("part_load_performance_method", "simple")
        ).lower()
        if self.part_load_performance_method not in {"simple", "en14825"}:
            raise ValueError("part_load_performance_method must be 'simple' or 'en14825'.")
        self.part_load_unit_type = str(cfg.get("part_load_unit_type", "air-to-water")).lower()
        self.part_load_degradation_coefficient = _fraction(
            cfg.get("part_load_degradation_coefficient", 0.9),
            "part_load_degradation_coefficient",
        )
        self.part_load_minimum_capacity_ratio = _fraction(
            cfg.get("part_load_minimum_capacity_ratio", 0.0),
            "part_load_minimum_capacity_ratio",
        )
        self.cooling_backup_eer = _optional_positive_float(cfg.get("cooling_backup_eer"))
        self.heat_recovery_fraction = _fraction(
            cfg.get("heat_recovery_fraction", 0.0), "heat_recovery_fraction"
        )
        self.performance_includes_heat_rejection_aux = bool(
            cfg.get("performance_includes_heat_rejection_aux", True)
        )
        self.p_hr_el_dry = max(float(cfg.get("p_hr_el_dry", cfg.get("phr_el_dry", 0.0))), 0.0)
        self.p_hr_el_wet = max(float(cfg.get("p_hr_el_wet", cfg.get("phr_el_wet", 0.0))), 0.0)
        self.p_hr_el_other = max(float(cfg.get("p_hr_el_other", cfg.get("phr_el_other", 0.0))), 0.0)
        self.control_power_kW = max(float(cfg.get("control_power_kW", cfg.get("P_el_C_ctrl_kW", 0.0))), 0.0)
        self.additional_auxiliary_power_kW = max(
            float(cfg.get("additional_auxiliary_power_kW", 0.0)),
            0.0,
        )

        if self.performance_map is None and self.nominal_eer is None:
            self.nominal_eer = _default_nominal_eer(self.nominal_capacity_kW)
        if self.performance_map is None and self.nominal_capacity_kW <= _KWH_EPS:
            raise ValueError(
                "Provide either cooling_performance_map or nominal_capacity_kW for EN 16798-13."
            )
        # --- Commit-2A: pre-build pivot arrays so _capacity_and_eer never
        #     calls pivot_table inside the per-timestep loop.
        if self.performance_map is not None:
            self._cap_pivot = _build_pivot_arrays(self.performance_map, "capacity_kW")
            self._eer_pivot = _build_pivot_arrays(self.performance_map, "eer")
        else:
            self._cap_pivot = None
            self._eer_pivot = None

    def _prepare_timeseries(self, data: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(data, pd.DataFrame):
            raise TypeError("data must be a pandas DataFrame.")
        if data.empty:
            raise ValueError("data must contain at least one row.")

        df = data.copy()
        out = pd.DataFrame(index=df.index)
        out.loc[:, "hours"] = self._time_step_hours(df)
        out.loc[:, "T_ext_C"] = _series_from_aliases(
            df, ["T_ext", "theta_ext", "outdoor_temperature_C", "T_external_C"], default=None
        )
        if out["T_ext_C"].isna().any():
            raise ValueError("Outdoor temperature is required. Provide 'T_ext' or 'theta_ext'.")
        out.loc[:, "T_ext_C"] = out["T_ext_C"].astype(float)
        out.loc[:, "T_ext_wb_C"] = _series_from_aliases(
            df, ["T_ext_wb_C", "theta_ext_wb_C", "wet_bulb_temperature_C"], default=np.nan
        ).astype(float)

        q_hc = _series_from_aliases(df, ["Q_HC"], default=0.0).astype(float)
        out.loc[:, "Q_C_gen_in_req_kWh"] = self._demand_from_columns(
            df,
            kwh_aliases=[
                "Q_C_gen_in_req_kWh",
                "Q_C_sto_in_kWh",
                "Q_C_dis_in_kWh",
                "Q_C_kWh",
                "QC_kWh",
                "cooling_kWh",
                "space_cooling_kWh",
            ],
            raw_aliases=["Q_C", "Cooling_needs"],
            fallback=np.maximum(-q_hc, 0.0),
        )
        out.loc[:, "theta_C_gen_out_req_C"] = _series_from_aliases(
            df,
            ["theta_C_gen_out_req_C", "T_C_sink_C", "cooling_sink_temperature_C"],
            default=self.theta_C_gen_out_set_C,
        ).astype(float)
        out.loc[:, "T_C_source_C"] = _series_from_aliases(
            df,
            ["T_C_source_C", "cooling_source_temperature_C", "source_temperature_C"],
            default=np.nan,
        ).astype(float)
        missing_source = out["T_C_source_C"].isna()
        out.loc[missing_source, "T_C_source_C"] = self._default_source_temperature(
            out.loc[missing_source]
        )
        out.loc[:, "f_op_C"] = _series_from_aliases(
            df, ["f_op_C", "cooling_operation_factor"], default=1.0
        ).astype(float).clip(lower=0.0, upper=1.0)
        out.loc[:, "f_op_ctrl"] = _series_from_aliases(
            df, ["f_op_ctrl", "cooling_control_operation_factor"], default=1.0
        ).astype(float).clip(lower=0.0, upper=1.0)
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

    def _default_source_temperature(self, df: pd.DataFrame) -> pd.Series:
        if df.empty:
            return pd.Series(dtype=float)
        if self.heat_rejection_type == "WET":
            wet = df["T_ext_wb_C"].fillna(df["T_ext_C"] - self.wet_bulb_offset_K)
            return wet + self.heat_rejection_deltaT_K + self.heat_rejection_loop_deltaT_K
        if self.heat_rejection_type == "OTHER":
            return pd.Series(self.other_sink_temperature_C, index=df.index)
        if self.heat_rejection_type in {"DRY", "HYBRID"}:
            return df["T_ext_C"] + self.heat_rejection_deltaT_K + self.heat_rejection_loop_deltaT_K
        return df["T_ext_C"]

    def _simulate(self, prepared: pd.DataFrame) -> pd.DataFrame:
        out = prepared.copy(deep=True)
        out.loc[:, "theta_C_gen_out_C"] = np.maximum(
            out["theta_C_gen_out_req_C"].astype(float),
            self.theta_C_gen_out_limit_C,
        )
        out.loc[:, "theta_cond_in_C"] = out["T_C_source_C"].astype(float)
        out.loc[:, "f_op_fc"] = self._free_cooling_factor(out)

        capacity = []
        eer = []
        for row in out.itertuples(index=False):
            cap, perf = self._capacity_and_eer(
                float(row.T_C_source_C),
                float(row.theta_C_gen_out_C),
            )
            capacity.append(cap)
            eer.append(perf)
        out.loc[:, "Q_C_gen_capacity_kW"] = capacity
        out.loc[:, "EER_C_gen"] = eer

        q_req = out["Q_C_gen_in_req_kWh"].astype(float)
        hours = out["hours"].astype(float)
        max_available = out["Q_C_gen_capacity_kW"] * hours * out["f_op_C"]
        out.loc[:, "Q_C_gen_in_max_kWh"] = max_available

        free_cooling = out["f_op_fc"].astype(float).clip(0.0, 1.0)
        q_free = q_req * free_cooling
        q_mechanical_req = q_req * (1.0 - free_cooling)
        q_mechanical = np.minimum(q_mechanical_req, max_available)
        q_missing = (q_mechanical_req - q_mechanical).clip(lower=0.0)

        if self.cooling_backup_eer is None:
            q_backup = pd.Series(0.0, index=out.index)
            q_unmet = q_missing
        else:
            q_backup = q_missing
            q_unmet = pd.Series(0.0, index=out.index)

        out.loc[:, "Q_C_gen_free_kWh"] = q_free
        out.loc[:, "Q_C_gen_mech_in_kWh"] = q_mechanical
        out.loc[:, "Q_C_gen_backup_in_kWh"] = q_backup
        out.loc[:, "Q_C_gen_unmet_kWh"] = q_unmet
        out.loc[:, "Q_C_gen_in_kWh"] = q_free + q_mechanical + q_backup

        out.loc[:, "f_C_PL"] = _safe_divide(q_mechanical, max_available).clip(0.0, 1.0)
        out.loc[:, "EER_C_gen_full_load"] = out["EER_C_gen"]
        if self.part_load_performance_method == "en14825":
            factors = [
                en14825_part_load_factor(
                    capacity_ratio=max(plr, self.part_load_minimum_capacity_ratio),
                    degradation_coefficient=self.part_load_degradation_coefficient,
                    unit_type=self.part_load_unit_type,
                )
                if load > _KWH_EPS
                else 1.0
                for plr, load in zip(out["f_C_PL"], q_mechanical)
            ]
            out.loc[:, "f_C_PLF"] = factors
            out.loc[:, "f_C_PL_for_performance"] = out["f_C_PL"].clip(
                lower=self.part_load_minimum_capacity_ratio,
                upper=1.0,
            )
            out.loc[:, "part_load_degradation_coefficient"] = (
                self.part_load_degradation_coefficient
            )
            out.loc[:, "EER_C_gen"] = (
                out["EER_C_gen_full_load"] * out["f_C_PLF"]
            ).clip(lower=_KWH_EPS)
        else:
            out.loc[:, "f_C_PLF"] = 1.0
            out.loc[:, "f_C_PL_for_performance"] = out["f_C_PL"]
            out.loc[:, "part_load_degradation_coefficient"] = 0.0
        out.loc[:, "t_C_gen_runtime_h"] = _safe_divide(
            q_mechanical,
            out["Q_C_gen_capacity_kW"].replace(0.0, np.nan),
        ).fillna(0.0).clip(lower=0.0, upper=hours)

        out.loc[:, "E_C_gen_el_in_kWh"] = _safe_divide(
            q_mechanical,
            out["EER_C_gen"].replace(0.0, np.nan),
        ).fillna(0.0)
        out.loc[:, "E_C_backup_in_kWh"] = (
            q_backup / self.cooling_backup_eer
            if self.cooling_backup_eer is not None
            else 0.0
        )
        out.loc[:, "Q_C_gen_out_kWh"] = out["Q_C_gen_in_kWh"] + out["E_C_gen_el_in_kWh"]
        out.loc[:, "Q_C_gen_out_rbl_kWh"] = (
            out["Q_C_gen_out_kWh"] * self.heat_recovery_fraction
        )
        out.loc[:, "theta_C_gen_out_max_C"] = out["theta_cond_in_C"]
        out.loc[:, "W_C_aux_gen_kWh"] = self._auxiliary_energy(out)
        out.loc[:, "E_C_total_kWh"] = (
            out["E_C_gen_el_in_kWh"]
            + out["E_C_backup_in_kWh"]
            + out["W_C_aux_gen_kWh"]
        )
        return out

    def _free_cooling_factor(self, df: pd.DataFrame) -> pd.Series:
        if not self.free_cooling_enabled:
            return pd.Series(0.0, index=df.index)
        if self.heat_rejection_type == "AIR_C_COND":
            return pd.Series(0.0, index=df.index)
        if self.heat_rejection_type == "WET":
            sink = df["T_ext_wb_C"].fillna(df["T_ext_C"] - self.wet_bulb_offset_K)
        elif self.heat_rejection_type == "OTHER":
            sink = pd.Series(self.other_sink_temperature_C, index=df.index)
        else:
            sink = df["T_ext_C"]
        delta = df["theta_C_gen_out_req_C"] - sink
        return pd.Series(1.0, index=df.index).where(
            delta > self.free_cooling_deltaT_K,
            0.0,
        )

    def _capacity_and_eer(self, source_temperature_C: float, sink_temperature_C: float) -> tuple[float, float]:
        if self.performance_map is not None:
            if self._cap_pivot is not None:
                # Fast path: pre-built bilinear grids (the common case)
                cap = _bilinear_or_linear(*self._cap_pivot, source_temperature_C, sink_temperature_C)
                eer = _bilinear_or_linear(*self._eer_pivot, source_temperature_C, sink_temperature_C)
            else:
                # Scattered map fallback: rebuild pivot each call (rare)
                cap = _interpolate_performance(
                    self.performance_map, source_temperature_C, sink_temperature_C, "capacity_kW"
                )
                eer = _interpolate_performance(
                    self.performance_map, source_temperature_C, sink_temperature_C, "eer"
                )
            return max(float(cap), 0.0), max(float(eer), _KWH_EPS)

        capacity = self.nominal_capacity_kW
        nominal_eer = float(self.nominal_eer or _default_nominal_eer(capacity))
        current_lift = max(source_temperature_C - sink_temperature_C, _KWH_EPS)
        nominal_lift = max(
            self.theta_cond_in_nominal_C - self.theta_C_evap_out_nominal_C,
            _KWH_EPS,
        )
        current_carnot = (_T0_ABS_K + sink_temperature_C) / current_lift
        nominal_carnot = (_T0_ABS_K + self.theta_C_evap_out_nominal_C) / nominal_lift
        eer = nominal_eer * current_carnot / max(nominal_carnot, _KWH_EPS)
        return capacity, max(float(eer), _KWH_EPS)

    def _auxiliary_energy(self, df: pd.DataFrame) -> pd.Series:
        active_hours = df["t_C_gen_runtime_h"].astype(float)
        q_rejected = df["Q_C_gen_out_kWh"].astype(float)

        if self.performance_includes_heat_rejection_aux:
            w_hr = pd.Series(0.0, index=df.index)
        elif self.heat_rejection_type == "WET":
            w_hr = q_rejected * self.p_hr_el_wet
        elif self.heat_rejection_type == "OTHER":
            w_hr = q_rejected * self.p_hr_el_other
        elif self.heat_rejection_type == "HYBRID":
            w_hr = q_rejected * self.p_hr_el_dry
        else:
            w_hr = q_rejected * self.p_hr_el_dry

        w_ctrl = active_hours * self.control_power_kW * df["f_op_ctrl"].astype(float)
        w_extra = active_hours * self.additional_auxiliary_power_kW
        return w_hr + w_ctrl + w_extra

    def _summarize(self, results: pd.DataFrame) -> dict[str, float]:
        q_req = float(results["Q_C_gen_in_req_kWh"].sum())
        q_in = float(results["Q_C_gen_in_kWh"].sum())
        e_el = float(results["E_C_gen_el_in_kWh"].sum())
        e_backup = float(results["E_C_backup_in_kWh"].sum())
        w_aux = float(results["W_C_aux_gen_kWh"].sum())
        e_total = e_el + e_backup + w_aux
        weights = results["Q_C_gen_in_kWh"] + _KWH_EPS
        summary = {
            "hours": float(results["hours"].sum()),
            "QC_gen_in_req_kWh": q_req,
            "QC_gen_in_kWh": q_in,
            "QC_gen_free_kWh": float(results["Q_C_gen_free_kWh"].sum()),
            "QC_gen_mech_in_kWh": float(results["Q_C_gen_mech_in_kWh"].sum()),
            "QC_gen_backup_in_kWh": float(results["Q_C_gen_backup_in_kWh"].sum()),
            "QC_gen_unmet_kWh": float(results["Q_C_gen_unmet_kWh"].sum()),
            "QC_gen_in_max_kWh": float(results["Q_C_gen_in_max_kWh"].sum()),
            "QC_gen_out_kWh": float(results["Q_C_gen_out_kWh"].sum()),
            "QC_gen_out_rbl_kWh": float(results["Q_C_gen_out_rbl_kWh"].sum()),
            "EC_gen_el_in_kWh": e_el,
            "EC_backup_in_kWh": e_backup,
            "WC_aux_gen_kWh": w_aux,
            "EC_total_kWh": e_total,
            "SEER_C_gen": _ratio(q_in, e_total),
            "EER_C_gen_mean": _weighted_mean(results["EER_C_gen"], weights),
            "EER_C_gen_full_load_mean": _weighted_mean(
                results["EER_C_gen_full_load"], weights
            )
            if "EER_C_gen_full_load" in results
            else _weighted_mean(results["EER_C_gen"], weights),
            "f_C_PL_mean": _weighted_mean(results["f_C_PL"], weights),
            "f_C_PLF_mean": _weighted_mean(results["f_C_PLF"], weights)
            if "f_C_PLF" in results
            else 1.0,
            "theta_C_gen_out_mean_C": _weighted_mean(results["theta_C_gen_out_C"], weights),
            "theta_cond_in_mean_C": _weighted_mean(results["theta_cond_in_C"], weights),
            "t_C_gen_runtime_h": float(results["t_C_gen_runtime_h"].sum()),
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


def _optional_positive_float(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not np.isfinite(result) or result <= 0:
        raise ValueError("optional positive values must be positive when provided.")
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


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return (numerator / denominator).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _ratio(numerator: float, denominator: float) -> float:
    if abs(denominator) <= _KWH_EPS:
        return float("nan")
    return numerator / denominator


def _default_nominal_eer(capacity_kW: float) -> float:
    if capacity_kW <= 12.0:
        return 2.9
    if capacity_kW <= 100.0:
        return 3.1
    if capacity_kW <= 300.0:
        return 3.2
    if capacity_kW <= 600.0:
        return 3.4
    return 3.5
