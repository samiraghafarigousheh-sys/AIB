"""Heat-pump generation according to EN 15316-4-2 bin-method logic.

The module implements the case-specific bin approach described in
EN 15316-4-2:2008 for heat-pump generation systems. It is intended to sit
after the building/distribution calculations: users provide the thermal energy
requirements for space heating, domestic hot water and, for reversible heat
pumps, space cooling. Product performance data are supplied as COP/EER and
capacity maps as a function of source and sink temperatures.

The cooling mode is treated as a reversible heat-pump extension using the same
temperature-bin and product-map structure. EN 15316-4-2 itself is a heating/DHW
generation standard, so the cooling results are reported separately as EER/SEER
style outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .performance_14511_14825 import en14825_part_load_factor


_KWH_EPS = 1e-12


@dataclass
class HeatPumpSimulationResult:
    """Container returned by :class:`HeatPumpSystemCalculator`.

    Attributes
    ----------
    bins:
        One row per outdoor-temperature bin with service loads, operating
        temperatures, product-map values and energy balances.
    summary:
        Aggregated annual or period totals and seasonal performance factors.
    inputs:
        Normalized configuration used by the calculator.
    """

    bins: pd.DataFrame
    summary: dict[str, float]
    inputs: dict[str, Any]


def _build_pivot_arrays_hp(
    performance_map: "pd.DataFrame | None",
    column: str,
) -> "tuple[np.ndarray, np.ndarray, np.ndarray] | None":
    """Pre-build sorted pivot arrays for _bilinear_or_linear.
    Returns None if map is absent or pivot contains NaN (IDW fallback).
    """
    if performance_map is None:
        return None
    pivot = performance_map.pivot_table(
        index="source_temperature_C",
        columns="sink_temperature_C",
        values=column,
        aggfunc="mean",
    ).sort_index().sort_index(axis=1)
    if pivot.isna().any().any():
        return None
    return (
        pivot.index.to_numpy(dtype=float),
        pivot.columns.to_numpy(dtype=float),
        pivot.to_numpy(dtype=float),
    )

class HeatPumpSystemCalculator:
    """Case-specific heat-pump generation calculator.

    The implementation follows the EN 15316-4-2 detailed/bin-method sequence:

    1. Create temperature bins from hourly or sub-hourly outdoor/source data.
    2. Allocate heating and DHW thermal requirements to each bin.
    3. Interpolate heat-pump capacity and COP/EER for source/sink conditions.
    4. Check runtime, operating-temperature and backup limits.
    5. Calculate heat-pump input energy, auxiliary energy, losses and SPF.

    Parameters
    ----------
    input_data:
        Dictionary with product maps, operating temperatures and system options.
        See ``Readme.md`` for a compact example.
    """

    def __init__(self, input_data: dict[str, Any] | None = None):
        self.input_data: dict[str, Any] = dict(input_data or {})
        self._load_options()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def simulate(self, data: pd.DataFrame) -> HeatPumpSimulationResult:
        """Run the bin-method simulation for a time-series input table."""

        prepared = self._prepare_timeseries(data)
        bins = self._simulate_bins(prepared)
        summary = self._summarize(bins)
        return HeatPumpSimulationResult(bins=bins, summary=summary, inputs=dict(self.input_data))

    def run_timeseries(self, data: pd.DataFrame) -> HeatPumpSimulationResult:
        """Alias for :meth:`simulate`, matching the package naming style."""

        return self.simulate(data)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def _load_options(self) -> None:
        cfg = self.input_data

        self.bin_width_C = _positive_float(cfg.get("bin_width_C", 1.0), "bin_width_C")
        self.default_time_step_h = _positive_float(
            cfg.get("time_step_hours", 1.0), "time_step_hours"
        )
        self.demand_unit = str(cfg.get("demand_unit", "Wh")).lower()
        if self.demand_unit not in {"wh", "kwh"}:
            raise ValueError("demand_unit must be 'Wh' or 'kWh'.")

        self.heating_enabled = bool(cfg.get("heating_enabled", True))
        self.cooling_enabled = bool(cfg.get("cooling_enabled", True))
        self.dhw_enabled = bool(cfg.get("dhw_enabled", True))

        self.source_type = str(cfg.get("source_type", "air")).lower()
        self.ground_source_temperature_C = float(cfg.get("ground_source_temperature_C", 10.0))
        self.water_source_temperature_C = float(cfg.get("water_source_temperature_C", 10.0))
        self.exhaust_air_temperature_C = float(cfg.get("exhaust_air_temperature_C", 20.0))

        self.design_outdoor_temperature_C = float(cfg.get("design_outdoor_temperature_C", -7.0))
        self.heating_cutoff_temperature_C = float(cfg.get("heating_cutoff_temperature_C", 16.0))
        self.heating_sink_temp_at_design_C = float(
            cfg.get("heating_sink_temp_at_design_C", 45.0)
        )
        self.heating_sink_temp_at_cutoff_C = float(
            cfg.get("heating_sink_temp_at_cutoff_C", 30.0)
        )
        self.heating_deltaT_K = _positive_float(cfg.get("heating_deltaT_K", 5.0), "heating_deltaT_K")

        self.dhw_target_temperature_C = float(cfg.get("dhw_target_temperature_C", 60.0))
        self.dhw_cold_water_temperature_C = float(cfg.get("dhw_cold_water_temperature_C", 10.0))
        hp_limit_for_dhw_default = cfg.get("hp_operating_limit_C", 55.0)
        if hp_limit_for_dhw_default is None:
            hp_limit_for_dhw_default = self.dhw_target_temperature_C
        self.dhw_sink_temperature_C = float(
            cfg.get(
                "dhw_sink_temperature_C",
                min(self.dhw_target_temperature_C, float(hp_limit_for_dhw_default)),
            )
        )

        self.cooling_sink_temperature_C = float(cfg.get("cooling_sink_temperature_C", 7.0))
        self.cooling_max_source_temperature_C = _optional_float(
            cfg.get("cooling_max_source_temperature_C")
        )

        self.hp_operating_limit_C = _optional_float(cfg.get("hp_operating_limit_C", 55.0))
        self.hp_min_source_temperature_C = _optional_float(cfg.get("hp_min_source_temperature_C"))
        self.hp_cutoff_temperature_C = _optional_float(cfg.get("hp_cutoff_temperature_C"))
        self.bivalent_temperature_C = _optional_float(cfg.get("bivalent_temperature_C"))

        self.backup_mode = str(cfg.get("backup_mode", "parallel")).lower()
        if self.backup_mode not in {"none", "parallel", "alternative", "part_parallel"}:
            raise ValueError(
                "backup_mode must be one of 'none', 'parallel', 'alternative', 'part_parallel'."
            )

        self.heating_backup_efficiency = _positive_float(
            cfg.get("heating_backup_efficiency", cfg.get("backup_efficiency", 1.0)),
            "heating_backup_efficiency",
        )
        self.dhw_backup_efficiency = _positive_float(
            cfg.get("dhw_backup_efficiency", cfg.get("backup_efficiency", 1.0)),
            "dhw_backup_efficiency",
        )
        self.cooling_backup_eer = _optional_float(cfg.get("cooling_backup_eer"))

        self.part_load_performance_method = str(
            cfg.get("part_load_performance_method", "simple")
        ).lower()
        if self.part_load_performance_method not in {"simple", "en14825"}:
            raise ValueError("part_load_performance_method must be 'simple' or 'en14825'.")
        self.part_load_unit_type = str(cfg.get("part_load_unit_type", "air-to-water")).lower()
        default_cd = cfg.get("part_load_degradation_coefficient", 0.9)
        self.heating_part_load_degradation_coefficient = _fraction(
            cfg.get("heating_part_load_degradation_coefficient", default_cd),
            "heating_part_load_degradation_coefficient",
        )
        self.dhw_part_load_degradation_coefficient = _fraction(
            cfg.get("dhw_part_load_degradation_coefficient", default_cd),
            "dhw_part_load_degradation_coefficient",
        )
        self.cooling_part_load_degradation_coefficient = _fraction(
            cfg.get("cooling_part_load_degradation_coefficient", default_cd),
            "cooling_part_load_degradation_coefficient",
        )
        default_min_cr = cfg.get("part_load_minimum_capacity_ratio", 0.0)
        self.heating_part_load_minimum_capacity_ratio = _fraction(
            cfg.get("heating_part_load_minimum_capacity_ratio", default_min_cr),
            "heating_part_load_minimum_capacity_ratio",
        )
        self.dhw_part_load_minimum_capacity_ratio = _fraction(
            cfg.get("dhw_part_load_minimum_capacity_ratio", default_min_cr),
            "dhw_part_load_minimum_capacity_ratio",
        )
        self.cooling_part_load_minimum_capacity_ratio = _fraction(
            cfg.get("cooling_part_load_minimum_capacity_ratio", default_min_cr),
            "cooling_part_load_minimum_capacity_ratio",
        )

        self.combined_operation = str(cfg.get("combined_operation", "alternative")).lower()
        if self.combined_operation not in {"alternative", "independent"}:
            raise ValueError("combined_operation must be 'alternative' or 'independent'.")
        self.dhw_priority = bool(cfg.get("dhw_priority", True))
        self.utility_cutoff_hours_per_day = max(
            0.0, min(float(cfg.get("utility_cutoff_hours_per_day", 0.0)), 24.0)
        )

        self.external_auxiliary_power_W = max(float(cfg.get("external_auxiliary_power_W", 0.0)), 0.0)
        self.standby_power_W = max(float(cfg.get("standby_power_W", 0.0)), 0.0)
        self.auxiliary_loss_to_ambient_fraction = _fraction(
            cfg.get("auxiliary_loss_to_ambient_fraction", 1.0),
            "auxiliary_loss_to_ambient_fraction",
        )
        self.auxiliary_recovered_fraction = _fraction(
            cfg.get("auxiliary_recovered_fraction", 0.0),
            "auxiliary_recovered_fraction",
        )
        self.auxiliary_location_b_factor = _fraction(
            cfg.get("auxiliary_location_b_factor", 0.0), "auxiliary_location_b_factor"
        )

        self.heating_storage_loss_kWh_per_day = max(
            float(cfg.get("heating_storage_loss_kWh_per_day", 0.0)), 0.0
        )
        self.dhw_storage_loss_kWh_per_day = max(
            float(cfg.get("dhw_storage_loss_kWh_per_day", 0.0)), 0.0
        )
        self.storage_test_deltaT_K = _positive_float(
            cfg.get("storage_test_deltaT_K", 45.0), "storage_test_deltaT_K"
        )
        self.storage_ambient_temperature_C = float(
            cfg.get("storage_ambient_temperature_C", 20.0)
        )
        self.storage_location_b_factor = _fraction(
            cfg.get("storage_location_b_factor", 0.0), "storage_location_b_factor"
        )

        self.heating_performance_map = _coerce_performance_map(
            cfg.get("heating_performance_map", cfg.get("performance_map")),
            performance_column="cop",
            service_name="heating",
        )
        self.dhw_performance_map = _coerce_performance_map(
            cfg.get("dhw_performance_map", cfg.get("heating_performance_map", cfg.get("performance_map"))),
            performance_column="cop",
            service_name="dhw",
        )
        self.cooling_performance_map = _coerce_performance_map(
            cfg.get("cooling_performance_map"),
            performance_column="eer",
            service_name="cooling",
            required=False,
        )
        # --- Commit-2B: pre-build pivot arrays (one pivot_table call per map/column) ---
        self._h_perf_pivot = _build_pivot_arrays_hp(self.heating_performance_map, "cop")
        self._h_cap_pivot  = _build_pivot_arrays_hp(self.heating_performance_map, "capacity_kW")
        self._dhw_perf_pivot = _build_pivot_arrays_hp(self.dhw_performance_map, "cop")
        self._dhw_cap_pivot  = _build_pivot_arrays_hp(self.dhw_performance_map, "capacity_kW")
        self._c_perf_pivot = _build_pivot_arrays_hp(self.cooling_performance_map, "eer")
        self._c_cap_pivot  = _build_pivot_arrays_hp(self.cooling_performance_map, "capacity_kW")
        # -----------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Time-series preparation
    # ------------------------------------------------------------------
    def _prepare_timeseries(self, data: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(data, pd.DataFrame):
            raise TypeError("data must be a pandas DataFrame.")
        if data.empty:
            raise ValueError("data must contain at least one row.")

        df = data.copy()
        out = pd.DataFrame(index=df.index)

        out["hours"] = self._time_step_hours(df)
        out["T_ext_C"] = _series_from_aliases(
            df,
            ["T_ext", "theta_ext", "outdoor_temperature_C", "T_external_C"],
            default=None,
        )
        if out["T_ext_C"].isna().any():
            raise ValueError("Outdoor temperature is required. Provide 'T_ext' or 'theta_ext'.")
        out = out.assign(T_ext_C=out["T_ext_C"].astype(float))

        q_hc = _series_from_aliases(df, ["Q_HC"], default=0.0)
        out["Q_H_gen_out_kWh"] = self._demand_from_columns(
            df,
            kwh_aliases=["Q_H_kWh", "QH_kWh", "heating_kWh", "space_heating_kWh"],
            raw_aliases=["Q_H", "Q_h", "Heating_needs"],
            fallback=np.maximum(q_hc.astype(float), 0.0),
        )
        out["Q_C_gen_out_kWh"] = self._demand_from_columns(
            df,
            kwh_aliases=["Q_C_kWh", "QC_kWh", "cooling_kWh", "space_cooling_kWh"],
            raw_aliases=["Q_C", "Cooling_needs"],
            fallback=np.maximum(-q_hc.astype(float), 0.0),
        )
        out["Q_W_gen_out_kWh"] = self._demand_from_columns(
            df,
            kwh_aliases=[
                "Q_W_kWh",
                "Q_DHW_kWh",
                "DHW_kWh",
                "dhw_kWh",
                "domestic_hot_water_kWh",
            ],
            raw_aliases=["Q_W", "Q_DHW"],
            fallback=0.0,
            raw_default_unit="kwh",
        )

        if not self.heating_enabled:
            out["Q_H_gen_out_kWh"] = 0.0
        if not self.cooling_enabled:
            out["Q_C_gen_out_kWh"] = 0.0
        if not self.dhw_enabled:
            out["Q_W_gen_out_kWh"] = 0.0

        out = out.assign(
            T_H_source_C=self._source_temperature(df, out["T_ext_C"], "H"),
            T_W_source_C=self._source_temperature(df, out["T_ext_C"], "W"),
            T_C_source_C=self._source_temperature(df, out["T_ext_C"], "C"),
            T_H_sink_C=_series_from_aliases(
                df,
                ["T_H_sink_C", "theta_H_supply_C", "heating_supply_temperature_C"],
                default=np.nan,
            ).astype(float),
        )
        missing_h_sink = out["T_H_sink_C"].isna()
        out.loc[missing_h_sink, "T_H_sink_C"] = self._heating_sink_temperature(
            out.loc[missing_h_sink, "T_ext_C"]
        )

        out["T_H_return_C"] = _series_from_aliases(
            df,
            ["T_H_return_C", "theta_H_return_C", "heating_return_temperature_C"],
            default=np.nan,
        ).astype(float)
        missing_h_return = out["T_H_return_C"].isna()
        out.loc[missing_h_return, "T_H_return_C"] = (
            out.loc[missing_h_return, "T_H_sink_C"] - self.heating_deltaT_K
        )

        out["T_W_sink_C"] = _series_from_aliases(
            df,
            ["T_W_sink_C", "dhw_sink_temperature_C", "dhw_tank_temperature_C"],
            default=self.dhw_sink_temperature_C,
        ).astype(float)
        out["T_W_target_C"] = _series_from_aliases(
            df,
            ["T_W_target_C", "dhw_target_temperature_C", "dhw_delivery_temperature_C"],
            default=self.dhw_target_temperature_C,
        ).astype(float)
        out["T_W_cold_C"] = _series_from_aliases(
            df,
            ["T_W_cold_C", "dhw_cold_water_temperature_C", "cold_water_temperature_C"],
            default=self.dhw_cold_water_temperature_C,
        ).astype(float)

        out["T_C_sink_C"] = _series_from_aliases(
            df,
            ["T_C_sink_C", "cooling_sink_temperature_C", "chilled_water_temperature_C"],
            default=self.cooling_sink_temperature_C,
        ).astype(float)

        for col in ["Q_H_gen_out_kWh", "Q_C_gen_out_kWh", "Q_W_gen_out_kWh"]:
            out = out.assign(**{col: out[col].fillna(0.0).clip(lower=0.0)})

        return out

    def _time_step_hours(self, df: pd.DataFrame) -> pd.Series:
        step = _series_from_aliases(df, ["time_step_hours", "dt_h"], default=np.nan)
        if not step.isna().all():
            return step.astype(float).clip(lower=0.0)

        if isinstance(df.index, pd.DatetimeIndex) and len(df.index) > 1:
            diffs = df.index.to_series().diff().dt.total_seconds().dropna() / 3600.0
            if not diffs.empty and np.isfinite(diffs.median()) and diffs.median() > 0:
                return pd.Series(float(diffs.median()), index=df.index)

        return pd.Series(self.default_time_step_h, index=df.index)

    def _demand_from_columns(
        self,
        df: pd.DataFrame,
        kwh_aliases: list[str],
        raw_aliases: list[str],
        fallback: float | pd.Series,
        raw_default_unit: str | None = None,
    ) -> pd.Series:
        kwh = _series_from_aliases(df, kwh_aliases, default=None)
        if kwh is not None:
            return kwh.astype(float)

        raw = _series_from_aliases(df, raw_aliases, default=None)
        if raw is None:
            if isinstance(fallback, pd.Series):
                raw = fallback.astype(float)
                unit = self.demand_unit
            else:
                return pd.Series(float(fallback), index=df.index)
        else:
            raw = raw.astype(float)
            unit = raw_default_unit or self.demand_unit

        if unit == "wh":
            return raw / 1000.0
        return raw

    def _source_temperature(
        self, df: pd.DataFrame, outdoor_temperature: pd.Series, service_prefix: str
    ) -> pd.Series:
        service_aliases = {
            "H": ["T_H_source_C", "heating_source_temperature_C"],
            "W": ["T_W_source_C", "dhw_source_temperature_C"],
            "C": ["T_C_source_C", "cooling_source_temperature_C"],
        }[service_prefix]
        source = _series_from_aliases(
            df, service_aliases + ["T_source_C", "source_temperature_C"], default=None
        )
        if source is not None:
            return source.astype(float)

        if self.source_type in {"air", "outdoor_air", "outside_air"}:
            return outdoor_temperature.astype(float)
        if self.source_type in {"ground", "brine", "ground_brine"}:
            return pd.Series(self.ground_source_temperature_C, index=df.index)
        if self.source_type in {"water", "groundwater", "surface_water"}:
            return pd.Series(self.water_source_temperature_C, index=df.index)
        if self.source_type in {"exhaust_air", "exhaust"}:
            return pd.Series(self.exhaust_air_temperature_C, index=df.index)
        raise ValueError(
            "source_type must be air, ground, water or exhaust_air when no source "
            "temperature column is provided."
        )

    def _heating_sink_temperature(self, outdoor_temperature: pd.Series) -> pd.Series:
        if self.heating_cutoff_temperature_C == self.design_outdoor_temperature_C:
            return pd.Series(self.heating_sink_temp_at_cutoff_C, index=outdoor_temperature.index)

        slope = (
            self.heating_sink_temp_at_cutoff_C - self.heating_sink_temp_at_design_C
        ) / (self.heating_cutoff_temperature_C - self.design_outdoor_temperature_C)
        values = self.heating_sink_temp_at_design_C + slope * (
            outdoor_temperature.astype(float) - self.design_outdoor_temperature_C
        )
        lo = min(self.heating_sink_temp_at_design_C, self.heating_sink_temp_at_cutoff_C)
        hi = max(self.heating_sink_temp_at_design_C, self.heating_sink_temp_at_cutoff_C)
        return values.clip(lower=lo, upper=hi)

    # ------------------------------------------------------------------
    # Bin simulation
    # ------------------------------------------------------------------
    def _simulate_bins(self, prepared: pd.DataFrame) -> pd.DataFrame:
        df = prepared.copy()
        bin_low = np.floor(df["T_ext_C"].astype(float) / self.bin_width_C) * self.bin_width_C
        df = df.assign(
            bin_lower_C=bin_low,
            bin_upper_C=bin_low + self.bin_width_C,
            bin_center_C=bin_low + self.bin_width_C / 2.0,
        )

        rows: list[dict[str, float]] = []
        for (lower, upper, center), group in df.groupby(
            ["bin_lower_C", "bin_upper_C", "bin_center_C"], sort=True
        ):
            row = self._simulate_one_bin(float(lower), float(upper), float(center), group)
            rows.append(row)

        if not rows:
            return pd.DataFrame()

        bins = pd.DataFrame(rows).sort_values("bin_lower_C").reset_index(drop=True)
        return bins

    def _simulate_one_bin(
        self, lower: float, upper: float, center: float, group: pd.DataFrame
    ) -> dict[str, float]:
        hours = float(group["hours"].sum())
        effective_hours = hours * (24.0 - self.utility_cutoff_hours_per_day) / 24.0
        effective_hours = max(effective_hours, 0.0)

        row: dict[str, float] = {
            "bin_lower_C": lower,
            "bin_upper_C": upper,
            "bin_center_C": center,
            "hours": hours,
            "effective_hours": effective_hours,
            "T_ext_mean_C": _weighted_mean(group["T_ext_C"], group["hours"]),
        }

        heating = self._service_load_and_performance(group, "H", effective_hours)
        dhw = self._service_load_and_performance(group, "W", effective_hours)
        cooling = self._service_load_and_performance(group, "C", effective_hours)

        self._allocate_heating_and_dhw_runtime(heating, dhw, effective_hours)
        self._allocate_cooling_runtime(cooling, effective_hours)

        row.update(_prefix_dict(heating, "H"))
        row.update(_prefix_dict(dhw, "W"))
        row.update(_prefix_dict(cooling, "C"))

        hp_active_hours_hw = heating["hp_runtime_h"] + dhw["hp_runtime_h"]
        standby_hours_hw = max(hours - hp_active_hours_hw, 0.0)
        aux_active_hw = self.external_auxiliary_power_W * hp_active_hours_hw / 1000.0
        aux_standby_hw = self.standby_power_W * standby_hours_hw / 1000.0
        aux_hw = aux_active_hw + aux_standby_hw

        hp_active_hours_c = cooling["hp_runtime_h"]
        standby_hours_c = max(hours - hp_active_hours_c, 0.0)
        aux_active_c = self.external_auxiliary_power_W * hp_active_hours_c / 1000.0
        aux_standby_c = self.standby_power_W * standby_hours_c / 1000.0
        aux_c = aux_active_c + aux_standby_c

        aux_loss_hw = aux_hw * self.auxiliary_loss_to_ambient_fraction
        aux_loss_c = aux_c * self.auxiliary_loss_to_ambient_fraction
        aux_recovered_hw = aux_hw * self.auxiliary_recovered_fraction
        aux_recovered_c = aux_c * self.auxiliary_recovered_fraction
        aux_recoverable_hw = aux_loss_hw * (1.0 - self.auxiliary_location_b_factor)
        aux_recoverable_c = aux_loss_c * (1.0 - self.auxiliary_location_b_factor)

        storage_loss_hw = heating["Q_gen_ls_kWh"] + dhw["Q_gen_ls_kWh"]
        storage_recoverable_hw = storage_loss_hw * (1.0 - self.storage_location_b_factor)

        row.update(
            {
                "W_HW_gen_aux_kWh": aux_hw,
                "W_HW_gen_aux_active_kWh": aux_active_hw,
                "W_HW_gen_aux_standby_kWh": aux_standby_hw,
                "Q_HW_gen_aux_recovered_kWh": aux_recovered_hw,
                "Q_HW_gen_aux_ls_kWh": aux_loss_hw,
                "Q_HW_gen_aux_ls_rbl_kWh": aux_recoverable_hw,
                "Q_HW_gen_ls_tot_kWh": storage_loss_hw + aux_loss_hw,
                "Q_HW_gen_ls_rbl_tot_kWh": storage_recoverable_hw + aux_recoverable_hw,
                "W_C_gen_aux_kWh": aux_c,
                "W_C_gen_aux_active_kWh": aux_active_c,
                "W_C_gen_aux_standby_kWh": aux_standby_c,
                "Q_C_gen_aux_recovered_kWh": aux_recovered_c,
                "Q_C_gen_aux_ls_kWh": aux_loss_c,
                "Q_C_gen_aux_ls_rbl_kWh": aux_recoverable_c,
            }
        )
        return row

    def _service_load_and_performance(
        self, group: pd.DataFrame, service: str, effective_hours: float
    ) -> dict[str, float]:
        if service == "H":
            demand_col = "Q_H_gen_out_kWh"
            source_col = "T_H_source_C"
            sink_col = "T_H_sink_C"
            return_col = "T_H_return_C"
            perf_map = self.heating_performance_map
            perf_col = "cop"
        elif service == "W":
            demand_col = "Q_W_gen_out_kWh"
            source_col = "T_W_source_C"
            sink_col = "T_W_sink_C"
            return_col = "T_W_cold_C"
            perf_map = self.dhw_performance_map
            perf_col = "cop"
        else:
            demand_col = "Q_C_gen_out_kWh"
            source_col = "T_C_source_C"
            sink_col = "T_C_sink_C"
            return_col = "T_C_sink_C"
            perf_map = self.cooling_performance_map
            perf_col = "eer"

        demand = float(group[demand_col].sum())
        load_hours = float(group.loc[group[demand_col] > _KWH_EPS, "hours"].sum())
        if service == "H" and demand > _KWH_EPS:
            storage_loss = self._storage_loss(
                group,
                loss_kWh_per_day=self.heating_storage_loss_kWh_per_day,
                temperature_col=sink_col,
            )
        elif service == "W" and self.dhw_enabled:
            storage_loss = self._storage_loss(
                group,
                loss_kWh_per_day=self.dhw_storage_loss_kWh_per_day,
                temperature_col=sink_col,
            )
        else:
            storage_loss = 0.0

        source = _weighted_mean(group[source_col], group["hours"])
        sink = _weighted_mean(group[sink_col], group[demand_col] + _KWH_EPS)
        return_or_cold = _weighted_mean(group[return_col], group[demand_col] + _KWH_EPS)
        load_with_losses = demand + storage_loss

        op_limit_fraction = self._operating_limit_backup_fraction(
            service=service,
            sink_temperature_C=sink,
            return_or_cold_temperature_C=return_or_cold,
            group=group,
        )
        backup_operating_kWh = load_with_losses * op_limit_fraction
        unmet_operating_kWh = 0.0
        if service in {"H", "W"} and self.backup_mode == "none":
            unmet_operating_kWh = backup_operating_kWh
            backup_operating_kWh = 0.0
        hp_requested_kWh = max(load_with_losses - backup_operating_kWh - unmet_operating_kWh, 0.0)

        available = self._hp_available(service, source)
        performance = np.nan
        capacity_kW = 0.0
        if hp_requested_kWh > _KWH_EPS and available:
            if perf_map is None:
                raise ValueError(
                    f"{service} demand is present, but no performance map was provided."
                )
            # Use pre-built pivot grids when available (avoids per-call pivot_table)
            if service == "H":
                _perf_grid = self._h_perf_pivot
                _cap_grid  = self._h_cap_pivot
            elif service == "W":
                _perf_grid = self._dhw_perf_pivot
                _cap_grid  = self._dhw_cap_pivot
            else:
                _perf_grid = self._c_perf_pivot
                _cap_grid  = self._c_cap_pivot
            if _perf_grid is not None:
                performance = _bilinear_or_linear(*_perf_grid, source, sink)
                capacity_kW = _bilinear_or_linear(*_cap_grid, source, sink)
            else:
                performance = _interpolate_performance(perf_map, source, sink, perf_col)
                capacity_kW = _interpolate_performance(perf_map, source, sink, "capacity_kW")
            performance = max(float(performance), _KWH_EPS)
            capacity_kW = max(float(capacity_kW), 0.0)

        required_runtime_h = (
            hp_requested_kWh / capacity_kW if capacity_kW > _KWH_EPS else np.inf
        )
        if hp_requested_kWh <= _KWH_EPS:
            required_runtime_h = 0.0
        if not available:
            required_runtime_h = np.inf if hp_requested_kWh > _KWH_EPS else 0.0

        return {
            "service": service,
            "Q_gen_out_kWh": demand,
            "load_hours": load_hours,
            "Q_gen_ls_kWh": storage_loss,
            "Q_total_required_kWh": load_with_losses,
            "Q_backup_operating_kWh": backup_operating_kWh,
            "Q_hp_requested_kWh": hp_requested_kWh,
            "T_source_C": source,
            "T_sink_C": sink,
            "T_return_or_cold_C": return_or_cold,
            "performance": performance,
            "performance_full_load": performance,
            "capacity_kW": capacity_kW,
            "required_runtime_h": required_runtime_h,
            "part_load_ratio": 0.0,
            "part_load_ratio_for_performance": 0.0,
            "part_load_factor": 1.0,
            "part_load_degradation_coefficient": self._part_load_degradation_coefficient(service),
            "hp_available": 1.0 if available else 0.0,
            "hp_runtime_h": 0.0,
            "Q_hp_out_kWh": 0.0,
            "Q_backup_capacity_kWh": 0.0,
            "Q_backup_out_kWh": backup_operating_kWh,
            "Q_unmet_operating_kWh": unmet_operating_kWh,
            "Q_unmet_kWh": unmet_operating_kWh,
            "E_hp_in_kWh": 0.0,
            "E_backup_in_kWh": 0.0,
            "Q_environment_in_kWh": 0.0,
            "Q_rejected_kWh": 0.0,
        }

    def _allocate_heating_and_dhw_runtime(
        self, heating: dict[str, float], dhw: dict[str, float], effective_hours: float
    ) -> None:
        if self.combined_operation == "independent":
            self._allocate_single_heating_service(heating, effective_hours, "H")
            self._allocate_single_heating_service(dhw, effective_hours, "W")
            return

        if self.dhw_priority:
            first = dhw
            second = heating
        else:
            first = heating
            second = dhw

        remaining = max(effective_hours, 0.0)
        self._allocate_single_heating_service(first, remaining, "W" if self.dhw_priority else "H")
        remaining = max(remaining - first["hp_runtime_h"], 0.0)
        self._allocate_single_heating_service(second, remaining, "H" if self.dhw_priority else "W")

    def _allocate_single_heating_service(
        self, service_result: dict[str, float], available_hours: float, service: str
    ) -> None:
        requested = service_result["Q_hp_requested_kWh"]
        capacity = service_result["capacity_kW"]
        backup_eff = (
            self.heating_backup_efficiency if service == "H" else self.dhw_backup_efficiency
        )

        if requested <= _KWH_EPS:
            self._finalize_heating_service(service_result, backup_eff)
            return

        if service_result["hp_available"] < 0.5 or capacity <= _KWH_EPS:
            hp_out = 0.0
            runtime = 0.0
        else:
            hp_out = min(requested, capacity * max(available_hours, 0.0))
            runtime = hp_out / capacity if capacity > _KWH_EPS else 0.0

        missing_capacity = max(requested - hp_out, 0.0)
        if self.backup_mode == "none":
            backup_capacity = 0.0
            unmet = missing_capacity
        else:
            backup_capacity = missing_capacity
            unmet = 0.0

        initial_unmet = service_result.get("Q_unmet_operating_kWh", 0.0)
        service_result["hp_runtime_h"] = runtime
        service_result["Q_hp_out_kWh"] = hp_out
        part_load_hours = self._part_load_reference_hours(service_result, available_hours, runtime)
        service_result["part_load_ratio"] = _ratio(
            hp_out,
            capacity * part_load_hours,
        )
        service_result["Q_backup_capacity_kWh"] = backup_capacity
        service_result["Q_backup_out_kWh"] += backup_capacity
        service_result["Q_unmet_kWh"] = initial_unmet + unmet
        self._finalize_heating_service(service_result, backup_eff)

    def _finalize_heating_service(
        self, service_result: dict[str, float], backup_efficiency: float
    ) -> None:
        self._apply_part_load_performance(service_result)
        perf = service_result["performance"]
        hp_out = service_result["Q_hp_out_kWh"]
        service_result["E_hp_in_kWh"] = hp_out / perf if hp_out > _KWH_EPS and perf > 0 else 0.0
        service_result["E_backup_in_kWh"] = (
            service_result["Q_backup_out_kWh"] / backup_efficiency
            if service_result["Q_backup_out_kWh"] > _KWH_EPS
            else 0.0
        )
        service_result["Q_environment_in_kWh"] = max(
            service_result["Q_hp_out_kWh"] - service_result["E_hp_in_kWh"], 0.0
        )

    def _allocate_cooling_runtime(
        self, cooling: dict[str, float], effective_hours: float
    ) -> None:
        requested = cooling["Q_hp_requested_kWh"]
        capacity = cooling["capacity_kW"]
        if requested <= _KWH_EPS:
            return

        if cooling["hp_available"] < 0.5 or capacity <= _KWH_EPS:
            hp_out = 0.0
            runtime = 0.0
        else:
            hp_out = min(requested, capacity * max(effective_hours, 0.0))
            runtime = hp_out / capacity if capacity > _KWH_EPS else 0.0

        missing_capacity = max(requested - hp_out, 0.0)
        if self.cooling_backup_eer is None:
            backup_capacity = 0.0
            unmet = missing_capacity
        else:
            backup_capacity = missing_capacity
            unmet = 0.0

        cooling["hp_runtime_h"] = runtime
        cooling["Q_hp_out_kWh"] = hp_out
        part_load_hours = self._part_load_reference_hours(cooling, effective_hours, runtime)
        cooling["part_load_ratio"] = _ratio(
            hp_out,
            capacity * part_load_hours,
        )
        cooling["Q_backup_capacity_kWh"] = backup_capacity
        cooling["Q_backup_out_kWh"] += backup_capacity
        cooling["Q_unmet_kWh"] = unmet
        self._apply_part_load_performance(cooling)
        perf = cooling["performance"]
        cooling["E_hp_in_kWh"] = hp_out / perf if hp_out > _KWH_EPS and perf > 0 else 0.0
        cooling["E_backup_in_kWh"] = (
            backup_capacity / self.cooling_backup_eer
            if self.cooling_backup_eer and backup_capacity > _KWH_EPS
            else 0.0
        )
        cooling["Q_rejected_kWh"] = cooling["Q_hp_out_kWh"] + cooling["E_hp_in_kWh"]

    def _part_load_reference_hours(
        self,
        service_result: dict[str, float],
        available_hours: float,
        runtime: float,
    ) -> float:
        demand_hours = max(service_result.get("load_hours", 0.0), 0.0)
        if demand_hours > _KWH_EPS:
            return max(min(demand_hours, max(available_hours, 0.0)), runtime, _KWH_EPS)
        return max(runtime, _KWH_EPS)

    def _part_load_degradation_coefficient(self, service: str) -> float:
        if service == "C":
            return self.cooling_part_load_degradation_coefficient
        if service == "W":
            return self.dhw_part_load_degradation_coefficient
        return self.heating_part_load_degradation_coefficient

    def _apply_part_load_performance(self, service_result: dict[str, float]) -> None:
        full_load_performance = service_result.get("performance_full_load", np.nan)
        service_result["performance"] = full_load_performance
        service_result["part_load_factor"] = 1.0
        service_result["part_load_ratio_for_performance"] = service_result.get(
            "part_load_ratio", 0.0
        )
        if self.part_load_performance_method != "en14825":
            return
        if not np.isfinite(full_load_performance) or full_load_performance <= 0:
            return
        if service_result.get("Q_hp_out_kWh", 0.0) <= _KWH_EPS:
            return
        part_load_ratio = service_result.get("part_load_ratio", 1.0)
        minimum_ratio = self._part_load_minimum_capacity_ratio(service_result)
        performance_ratio = max(part_load_ratio, minimum_ratio)
        coefficient = service_result.get("part_load_degradation_coefficient", 0.9)
        factor = en14825_part_load_factor(
            capacity_ratio=performance_ratio,
            degradation_coefficient=coefficient,
            unit_type=self.part_load_unit_type,
        )
        service_result["part_load_ratio_for_performance"] = performance_ratio
        service_result["part_load_factor"] = factor
        service_result["performance"] = max(full_load_performance * factor, _KWH_EPS)

    def _part_load_minimum_capacity_ratio(self, service_result: dict[str, float]) -> float:
        service = service_result.get("service")
        if service == "C":
            return self.cooling_part_load_minimum_capacity_ratio
        if service == "W":
            return self.dhw_part_load_minimum_capacity_ratio
        return self.heating_part_load_minimum_capacity_ratio

    def _storage_loss(
        self, group: pd.DataFrame, loss_kWh_per_day: float, temperature_col: str
    ) -> float:
        if loss_kWh_per_day <= 0:
            return 0.0
        hours = float(group["hours"].sum())
        avg_temp = _weighted_mean(group[temperature_col], group["hours"])
        delta = max(avg_temp - self.storage_ambient_temperature_C, 0.0)
        return loss_kWh_per_day * (delta / self.storage_test_deltaT_K) * (hours / 24.0)

    def _operating_limit_backup_fraction(
        self,
        service: str,
        sink_temperature_C: float,
        return_or_cold_temperature_C: float,
        group: pd.DataFrame,
    ) -> float:
        if self.hp_operating_limit_C is None:
            return 0.0

        limit = self.hp_operating_limit_C
        if service == "W":
            target = _weighted_mean(group["T_W_target_C"], group["Q_W_gen_out_kWh"] + _KWH_EPS)
            cold = _weighted_mean(group["T_W_cold_C"], group["Q_W_gen_out_kWh"] + _KWH_EPS)
            if target <= limit:
                return 0.0
            return _fraction((target - limit) / max(target - cold, _KWH_EPS), "dhw limit")

        if service == "H" and sink_temperature_C > limit:
            return _fraction(
                (sink_temperature_C - limit)
                / max(sink_temperature_C - return_or_cold_temperature_C, _KWH_EPS),
                "heating limit",
            )

        return 0.0

    def _hp_available(self, service: str, source_temperature_C: float) -> bool:
        if service == "C":
            if self.cooling_max_source_temperature_C is not None:
                return source_temperature_C <= self.cooling_max_source_temperature_C
            return True

        if self.hp_min_source_temperature_C is not None:
            if source_temperature_C < self.hp_min_source_temperature_C:
                return False

        if self.backup_mode == "alternative" and self.bivalent_temperature_C is not None:
            return source_temperature_C >= self.bivalent_temperature_C

        if self.backup_mode == "part_parallel" and self.hp_cutoff_temperature_C is not None:
            return source_temperature_C >= self.hp_cutoff_temperature_C

        return True

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _summarize(self, bins: pd.DataFrame) -> dict[str, float]:
        if bins.empty:
            return {}

        def s(col: str) -> float:
            return float(bins[col].sum()) if col in bins else 0.0

        q_h = s("H_Q_gen_out_kWh")
        q_w = s("W_Q_gen_out_kWh")
        q_c = s("C_Q_gen_out_kWh")

        e_h_hp = s("H_E_hp_in_kWh")
        e_w_hp = s("W_E_hp_in_kWh")
        e_c_hp = s("C_E_hp_in_kWh")
        e_h_backup = s("H_E_backup_in_kWh")
        e_w_backup = s("W_E_backup_in_kWh")
        e_c_backup = s("C_E_backup_in_kWh")
        aux_hw = s("W_HW_gen_aux_kWh")
        aux_c = s("W_C_gen_aux_kWh")

        e_hw_gen = e_h_hp + e_w_hp + e_h_backup + e_w_backup
        e_c_gen = e_c_hp + e_c_backup
        q_hw = q_h + q_w
        q_hw_hp = s("H_Q_hp_out_kWh") + s("W_Q_hp_out_kWh")
        e_hw_hp = e_h_hp + e_w_hp

        spf_hw_gen = _ratio(q_hw, e_hw_gen + aux_hw)
        spf_hw_hp = _ratio(q_hw_hp, e_hw_hp + aux_hw)
        seer_c_gen = _ratio(q_c, e_c_gen + aux_c)

        return {
            "QH_gen_out_kWh": q_h,
            "QW_gen_out_kWh": q_w,
            "QC_gen_out_kWh": q_c,
            "QHW_gen_out_kWh": q_hw,
            "QH_hp_out_kWh": s("H_Q_hp_out_kWh"),
            "QW_hp_out_kWh": s("W_Q_hp_out_kWh"),
            "QC_hp_out_kWh": s("C_Q_hp_out_kWh"),
            "QHW_hp_out_kWh": q_hw_hp,
            "QHW_backup_out_kWh": s("H_Q_backup_out_kWh") + s("W_Q_backup_out_kWh"),
            "QC_backup_out_kWh": s("C_Q_backup_out_kWh"),
            "QHW_unmet_kWh": s("H_Q_unmet_kWh") + s("W_Q_unmet_kWh"),
            "QC_unmet_kWh": s("C_Q_unmet_kWh"),
            "EH_hp_in_kWh": e_h_hp,
            "EW_hp_in_kWh": e_w_hp,
            "EC_hp_in_kWh": e_c_hp,
            "EHW_backup_in_kWh": e_h_backup + e_w_backup,
            "EC_backup_in_kWh": e_c_backup,
            "EHW_gen_in_kWh": e_hw_gen,
            "EC_gen_in_kWh": e_c_gen,
            "WHW_gen_aux_kWh": aux_hw,
            "WC_gen_aux_kWh": aux_c,
            "E_total_electricity_kWh": e_hw_gen + aux_hw + e_c_gen + aux_c,
            "QHW_gen_ls_tot_kWh": s("Q_HW_gen_ls_tot_kWh"),
            "QHW_gen_ls_rbl_tot_kWh": s("Q_HW_gen_ls_rbl_tot_kWh"),
            "QHW_environment_in_kWh": s("H_Q_environment_in_kWh") + s("W_Q_environment_in_kWh"),
            "QC_rejected_kWh": s("C_Q_rejected_kWh"),
            "SPF_HW_gen": spf_hw_gen,
            "SPF_HW_hp": spf_hw_hp,
            "e_HW_gen": _ratio(1.0, spf_hw_gen),
            "SEER_C_gen": seer_c_gen,
            "H_part_load_factor_mean": _weighted_mean(
                bins["H_part_load_factor"], bins["H_Q_hp_out_kWh"] + _KWH_EPS
            ),
            "W_part_load_factor_mean": _weighted_mean(
                bins["W_part_load_factor"], bins["W_Q_hp_out_kWh"] + _KWH_EPS
            ),
            "C_part_load_factor_mean": _weighted_mean(
                bins["C_part_load_factor"], bins["C_Q_hp_out_kWh"] + _KWH_EPS
            ),
        }


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _coerce_performance_map(
    data: Any,
    performance_column: str,
    service_name: str,
    required: bool = True,
) -> pd.DataFrame | None:
    if data is None:
        if required:
            return None
        return None

    df = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if df.empty:
        if required:
            raise ValueError(f"{service_name}_performance_map is empty.")
        return None

    aliases = {
        "source_temperature_C": [
            "source_temperature_C",
            "source_temp_C",
            "T_source_C",
            "T_ext",
            "outdoor_temperature_C",
        ],
        "sink_temperature_C": [
            "sink_temperature_C",
            "sink_temp_C",
            "T_sink_C",
            "supply_temperature_C",
            "T_supply_C",
        ],
        "capacity_kW": [
            "capacity_kW",
            "heating_capacity_kW",
            "cooling_capacity_kW",
            "thermal_capacity_kW",
            "power_kW",
        ],
        performance_column: [performance_column, performance_column.upper()],
    }

    renamed: dict[str, str] = {}
    for canonical, names in aliases.items():
        for name in names:
            if name in df.columns:
                renamed[name] = canonical
                break

    df = df.rename(columns=renamed)
    required_columns = ["source_temperature_C", "sink_temperature_C", "capacity_kW", performance_column]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"{service_name}_performance_map is missing required columns: {missing}."
        )

    df = df[required_columns].astype(float).dropna()
    if df.empty:
        raise ValueError(f"{service_name}_performance_map has no numeric rows.")
    if (df["capacity_kW"] < 0).any() or (df[performance_column] <= 0).any():
        raise ValueError(
            f"{service_name}_performance_map must use non-negative capacity and positive "
            f"{performance_column.upper()} values."
        )
    return df


def _interpolate_performance(
    performance_map: pd.DataFrame, source_temperature_C: float, sink_temperature_C: float, column: str
) -> float:
    pivot = performance_map.pivot_table(
        index="source_temperature_C",
        columns="sink_temperature_C",
        values=column,
        aggfunc="mean",
    ).sort_index().sort_index(axis=1)

    if not pivot.isna().any().any():
        sources = pivot.index.to_numpy(dtype=float)
        sinks = pivot.columns.to_numpy(dtype=float)
        values = pivot.to_numpy(dtype=float)
        return _bilinear_or_linear(
            sources,
            sinks,
            values,
            float(source_temperature_C),
            float(sink_temperature_C),
        )

    # Fallback for scattered maps: inverse-distance interpolation with clamped
    # temperature scaling so a nearly matching point dominates.
    points = performance_map[
        ["source_temperature_C", "sink_temperature_C", column]
    ].to_numpy(dtype=float)
    src_range = max(float(np.ptp(points[:, 0])), 1.0)
    sink_range = max(float(np.ptp(points[:, 1])), 1.0)
    distances = np.sqrt(
        ((points[:, 0] - source_temperature_C) / src_range) ** 2
        + ((points[:, 1] - sink_temperature_C) / sink_range) ** 2
    )
    exact = distances < 1e-12
    if exact.any():
        return float(points[exact, 2][0])
    weights = 1.0 / np.maximum(distances, 1e-12) ** 2
    return float(np.sum(weights * points[:, 2]) / np.sum(weights))


def _bilinear_or_linear(
    xs: np.ndarray, ys: np.ndarray, values: np.ndarray, x: float, y: float
) -> float:
    if len(xs) == 1 and len(ys) == 1:
        return float(values[0, 0])
    if len(xs) == 1:
        return float(np.interp(y, ys, values[0, :]))
    if len(ys) == 1:
        return float(np.interp(x, xs, values[:, 0]))

    x1_i, x2_i = _bracket_indices(xs, x)
    y1_i, y2_i = _bracket_indices(ys, y)
    x1, x2 = xs[x1_i], xs[x2_i]
    y1, y2 = ys[y1_i], ys[y2_i]

    q11 = values[x1_i, y1_i]
    q21 = values[x2_i, y1_i]
    q12 = values[x1_i, y2_i]
    q22 = values[x2_i, y2_i]

    tx = 0.0 if x2 == x1 else (x - x1) / (x2 - x1)
    ty = 0.0 if y2 == y1 else (y - y1) / (y2 - y1)
    tx = float(np.clip(tx, 0.0, 1.0))
    ty = float(np.clip(ty, 0.0, 1.0))

    return float(
        q11 * (1 - tx) * (1 - ty)
        + q21 * tx * (1 - ty)
        + q12 * (1 - tx) * ty
        + q22 * tx * ty
    )


def _bracket_indices(values: np.ndarray, target: float) -> tuple[int, int]:
    if target <= values[0]:
        return 0, 1
    if target >= values[-1]:
        return len(values) - 2, len(values) - 1
    upper = int(np.searchsorted(values, target, side="right"))
    return upper - 1, upper


def _series_from_aliases(
    df: pd.DataFrame, aliases: list[str], default: Any | None
) -> pd.Series | None:
    for name in aliases:
        if name in df.columns:
            return df[name]
    if default is None:
        return None
    if isinstance(default, pd.Series):
        return default.reindex(df.index)
    return pd.Series(default, index=df.index)


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    v = pd.Series(values, dtype=float)
    w = pd.Series(weights, dtype=float).clip(lower=0.0)
    mask = v.notna() & w.notna()
    if not mask.any() or float(w[mask].sum()) <= _KWH_EPS:
        return float(v[mask].mean()) if mask.any() else 0.0
    return float(np.average(v[mask], weights=w[mask]))


def _prefix_dict(values: dict[str, float], prefix: str) -> dict[str, float]:
    return {
        f"{prefix}_{key}": value
        for key, value in values.items()
        if key != "service"
    }


def _positive_float(value: Any, name: str) -> float:
    value = float(value)
    if value <= 0:
        raise ValueError(f"{name} must be positive.")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _fraction(value: Any, name: str) -> float:
    try:
        fraction = float(value)
    except Exception as exc:  # pragma: no cover - defensive type context
        raise ValueError(f"{name} must be a fraction between 0 and 1.") from exc
    return float(np.clip(fraction, 0.0, 1.0))


def _ratio(numerator: float, denominator: float) -> float:
    if abs(denominator) <= _KWH_EPS:
        return float("nan")
    return float(numerator / denominator)
