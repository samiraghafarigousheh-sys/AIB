'''
Calculation of DHW energy needs and DHW design sizing according to EN 12831-3.
The aim is to evaluate and demonstrate the calculation proposed by the standard.
This work does not replace the standard; it should be used alongside the EPB standard.

Acknowledgments: The work was developed from the standard and the spreadsheet created by EPB Center.

Authors: Daniele Antonucci, Ulrich Filippi Oberegger
'''

# ======================================================================================================
#                               Energy Need curve
# ======================================================================================================

import pandas as pd
import calendar
from datetime import date
from dataclasses import dataclass
from typing import Any
from typing import Optional


from pybuildingenergy.source.functions import table_B_3, table_B_4, table_B_5_modified
from pybuildingenergy.global_inputs import WATER_DENSITY, WATER_SPECIFIC_HEAT_CAPACITY


_KWH_EPS = 1e-12
_WATER_DENSITY_KG_L = WATER_DENSITY / 1000.0
_WATER_SPECIFIC_HEAT_CAPACITY_KJ_KG_K = WATER_SPECIFIC_HEAT_CAPACITY * 3600.0
_WATER_SPECIFIC_HEAT_CAPACITY_KWH_KG_K = WATER_SPECIFIC_HEAT_CAPACITY


@dataclass
class DHWDesignSimulationResult:
    """Container returned by :class:`DHWDesignLoadCalculator`.

    ``timeseries`` contains the representative design day on a one-minute
    basis. ``summary`` contains design storage, reheating power and supply-curve
    adequacy indicators.
    """

    timeseries: pd.DataFrame
    summary: dict[str, float | str | bool]
    inputs: dict[str, Any]


def _positive_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0.0 else default


def _fraction(value: Any, default: float = 0.0) -> float:
    number = _positive_float(value, default)
    return max(0.0, min(number, 1.0))


def _storage_capacity_kWh(
    volume_l: float,
    theta_hot_C: float,
    theta_cold_C: float,
    loading_factor: float = 1.0,
) -> float:
    """EN 12831-3 Formula (4) expressed with litres and kWh."""

    delta_t = max(float(theta_hot_C) - float(theta_cold_C), 0.0)
    return (
        max(float(volume_l), 0.0)
        * _WATER_DENSITY_KG_L
        * _WATER_SPECIFIC_HEAT_CAPACITY_KWH_KG_K
        * delta_t
        * max(float(loading_factor), 0.0)
    )


def _volume_l_from_energy_kWh(
    energy_kWh: float,
    theta_hot_C: float,
    theta_cold_C: float,
    loading_factor: float = 1.0,
) -> float:
    denominator = (
        _WATER_DENSITY_KG_L
        * _WATER_SPECIFIC_HEAT_CAPACITY_KWH_KG_K
        * max(float(theta_hot_C) - float(theta_cold_C), _KWH_EPS)
        * max(float(loading_factor), _KWH_EPS)
    )
    return max(float(energy_kWh), 0.0) / denominator


def _annex_b_loading_factor(system_type: str, volume_l: float) -> float:
    system = str(system_type or "mixed_storage").lower()
    if system in {"loading_storage", "charging_storage", "layer_charging"}:
        return 1.0
    if volume_l > 400.0:
        return 0.90
    if volume_l > 0.0:
        return 0.96
    return 0.96


def _annex_b_standby_loss_kWh_d(volume_l: float) -> float:
    """Interpolate EN 12831-3 Annex B Table B.8 default standby losses."""

    points = [
        (5.0, 0.35),
        (30.0, 0.60),
        (50.0, 0.78),
        (80.0, 0.98),
        (100.0, 1.10),
        (120.0, 1.20),
        (150.0, 1.35),
        (200.0, 1.56),
        (300.0, 1.91),
        (400.0, 2.20),
        (500.0, 2.46),
        (600.0, 2.69),
        (800.0, 3.11),
        (1000.0, 3.48),
        (1250.0, 3.89),
        (1500.0, 4.26),
        (2000.0, 4.92),
    ]
    volume = max(float(volume_l), 0.0)
    if volume <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if volume <= x1:
            return y0 + (y1 - y0) * (volume - x0) / (x1 - x0)
    x0, y0 = points[-2]
    x1, y1 = points[-1]
    return y1 + (y1 - y0) * (volume - x1) / (x1 - x0)


def _annex_b_heat_generator_lag_min(generator_type: str) -> float:
    generator = str(generator_type or "heat_pump").lower()
    if "pellet" in generator:
        return 30.0
    if "wood" in generator:
        return 45.0
    if "chp" in generator:
        return 6.0
    if "heat" in generator and "pump" in generator:
        return 4.0
    if "aluminium" in generator:
        return 2.0
    return 6.0


class DHWDesignLoadCalculator:
    """EN 12831-3:2017 DHW design heat-load and storage sizing calculator.

    The calculator implements the summation-curve method described in Clause
    6.4.2 and 6.4.3. It converts a representative DHW need day to one-minute
    steps, calculates storage switch points, storage/distribution losses,
    heat-generator time lag, effective reheating power, and checks whether the
    supply curve remains above the needs curve with the required storage margin.

    The implementation supports:
    - mixed storage systems;
    - loading/charging storage systems;
    - direct-flow systems without storage.
    """

    def __init__(self, input_data: dict[str, Any] | None = None):
        self.input_data = dict(input_data or {})
        self._load_options()

    def run_timeseries(self, data: pd.DataFrame | pd.Series) -> DHWDesignSimulationResult:
        if self.system_type == "direct_flow":
            ts, summary = self._simulate_direct_flow(data)
        else:
            ts, summary = self._simulate_storage_system(data)
        return DHWDesignSimulationResult(ts, summary, dict(self.input_data))

    def simulate(self, data: pd.DataFrame | pd.Series) -> DHWDesignSimulationResult:
        return self.run_timeseries(data)

    def _load_options(self) -> None:
        cfg = self.input_data
        self.system_type = str(cfg.get("system_type", "mixed_storage")).lower()
        if self.system_type in {"charging_storage", "layer_charging"}:
            self.system_type = "loading_storage"
        if self.system_type not in {"mixed_storage", "loading_storage", "direct_flow"}:
            raise ValueError(
                "system_type must be 'mixed_storage', 'loading_storage' or 'direct_flow'."
            )

        self.sizing_mode = str(cfg.get("sizing_mode", "size_storage")).lower()
        if self.sizing_mode not in {"check", "size_storage", "size_power", "auto"}:
            raise ValueError("sizing_mode must be 'check', 'size_storage', 'size_power' or 'auto'.")

        self.demand_unit = str(cfg.get("demand_unit", "kWh")).lower()
        if self.demand_unit not in {"kwh", "wh"}:
            raise ValueError("demand_unit must be 'kWh' or 'Wh'.")

        self.theta_draw_C = float(cfg.get("draw_temperature_C", cfg.get("theta_W_draw_C", 42.0)))
        self.theta_cold_C = float(cfg.get("cold_water_temperature_C", cfg.get("theta_W_cold_C", 10.0)))
        self.theta_storage_max_C = float(
            cfg.get("storage_max_temperature_C", cfg.get("theta_W_sto_max_C", 55.0))
        )
        self.theta_ambient_C = float(cfg.get("ambient_temperature_C", 20.0))
        self.theta_charge_C = float(
            cfg.get("charging_temperature_C", max(self.theta_storage_max_C, self.theta_draw_C))
        )
        self.theta_pipe_mean_C = float(cfg.get("pipe_mean_temperature_C", 50.0))

        self.storage_volume_l = max(float(cfg.get("storage_volume_l", cfg.get("V_sto_l", 0.0))), 0.0)
        self.storage_height_m = _positive_float(cfg.get("storage_height_m", 1.2), 1.2)
        sensor_rel = _fraction(cfg.get("sensor_relative_height", 0.5), 0.5)
        self.sensor_height_m = _positive_float(
            cfg.get("sensor_height_m", sensor_rel * self.storage_height_m),
            sensor_rel * self.storage_height_m,
        )
        self.sensor_height_m = min(self.sensor_height_m, self.storage_height_m)
        self.loading_factor = float(
            cfg.get(
                "loading_factor",
                _annex_b_loading_factor(self.system_type, self.storage_volume_l),
            )
        )
        self.additional_storage_connections = max(
            int(cfg.get("additional_storage_connections", 0)),
            0,
        )
        self._explicit_standby_loss_kWh_d = None
        self.storage_standby_loss_source = "EN 12831-3 Annex B Table B.8"
        for key in ("standby_loss_kWh_per_day", "q_sb_sto_kWh_d"):
            if cfg.get(key) is not None:
                self._explicit_standby_loss_kWh_d = max(float(cfg[key]), 0.0)
                self.storage_standby_loss_source = key
                break
        self.storage_standby_loss_kWh_d = self._standby_loss_kWh_d_for_volume(
            self.storage_volume_l
        )

        self.nominal_power_kW = max(float(cfg.get("nominal_power_kW", cfg.get("phi_N_kW", 0.0))), 0.0)
        self.heat_exchanger_power_explicit = (
            "heat_exchanger_power_kW" in cfg or "phi_HE_kW" in cfg
        )
        self.heat_exchanger_power_kW = max(
            float(cfg.get("heat_exchanger_power_kW", cfg.get("phi_HE_kW", self.nominal_power_kW))),
            0.0,
        )
        self.heat_generator_type = str(cfg.get("heat_generator_type", "heat_pump"))
        self.time_lag_min = self._time_lag_min(cfg)
        self.distribution_pipe_sections = list(cfg.get("distribution_pipe_sections", []))
        self.specific_distribution_loss_W_m = max(
            float(cfg.get("specific_distribution_loss_W_m", cfg.get("q_dis_W_m", 11.0))),
            0.0,
        )
        self.distribution_length_m = max(
            float(cfg.get("distribution_length_m", cfg.get("l_dis_m", 0.0))),
            0.0,
        )
        self.direct_design_flow_l_s = max(
            float(cfg.get("design_flow_l_s", cfg.get("V_D_l_s", 0.0))),
            0.0,
        )
        self.representative_day = cfg.get("representative_day")
        self.max_storage_volume_l = max(float(cfg.get("max_storage_volume_l", 3000.0)), 1.0)
        self.max_nominal_power_kW = max(float(cfg.get("max_nominal_power_kW", 100.0)), 0.1)
        self.sizing_tolerance_kWh = max(float(cfg.get("sizing_tolerance_kWh", 0.005)), 0.0)

    def _time_lag_min(self, cfg: dict[str, Any]) -> float:
        direct = cfg.get("time_lag_min", cfg.get("t_lag_min"))
        if direct is not None:
            return max(float(direct), 0.0)

        m_water = max(float(cfg.get("heat_generator_water_mass_kg", 0.0)), 0.0)
        m_generator = max(float(cfg.get("heat_generator_mass_kg", 0.0)), 0.0)
        if m_water > 0.0 or m_generator > 0.0:
            c_water = float(cfg.get("water_specific_heat_kJ_kgK", _WATER_SPECIFIC_HEAT_CAPACITY_KJ_KG_K))
            c_generator = float(cfg.get("generator_specific_heat_kJ_kgK", 0.5))
            f_hg_theta = float(
                cfg.get(
                    "heat_generator_temperature_factor",
                    0.4 if self.heat_generator_type.lower() == "heat_pump" else 0.9,
                )
            )
            f_hg_q = max(float(cfg.get("heat_generator_power_factor", 1.0)), _KWH_EPS)
            numerator = (
                (m_water * c_water + m_generator * c_generator)
                * f_hg_theta
                * max(self.theta_storage_max_C - self.theta_ambient_C, 0.0)
            )
            denominator = 60.0 * max(self.nominal_power_kW, _KWH_EPS) * f_hg_q
            return max(numerator / denominator, 0.0)

        return _annex_b_heat_generator_lag_min(self.heat_generator_type) + max(
            float(cfg.get("distribution_time_lag_min", 0.0)),
            0.0,
        )

    def _simulate_direct_flow(self, data: pd.DataFrame | pd.Series) -> tuple[pd.DataFrame, dict[str, float | str | bool]]:
        minute = self._representative_minute_needs(data)
        volume_l_min = self._volume_from_need(minute)
        design_flow_l_s = self.direct_design_flow_l_s
        if design_flow_l_s <= _KWH_EPS:
            design_flow_l_s = float(volume_l_min.max()) / 60.0
        phi_eff = (
            design_flow_l_s
            * _WATER_DENSITY_KG_L
            * _WATER_SPECIFIC_HEAT_CAPACITY_KJ_KG_K
            * max(self.theta_draw_C - self.theta_cold_C, 0.0)
        )
        need_cum = minute.cumsum()
        ts = pd.DataFrame(
            {
                "Q_W_need_kWh": minute.values,
                "V_W_draw_l": volume_l_min.values,
                "Q_W_need_cum_kWh": need_cum.values,
                "Q_W_supply_cum_kWh": need_cum.values,
                "phi_eff_kW": phi_eff,
            },
            index=minute.index,
        )
        summary = self._base_summary(ts, 0.0, 0.0)
        summary.update(
            {
                "system_type": "direct_flow",
                "sizing_mode": self.sizing_mode,
                "V_sto_input_l": 0.0,
                "V_sto_selected_l": 0.0,
                "Q_sto_max_kWh": 0.0,
                "Q_sto_min_kWh": 0.0,
                "Q_sto_on_kWh": 0.0,
                "Q_sto_off_kWh": 0.0,
                "phi_N_selected_kW": phi_eff,
                "phi_eff_nominal_kW": phi_eff,
                "design_flow_l_s": design_flow_l_s,
                "design_flow_m3_h": design_flow_l_s * 3.6,
                "supply_margin_min_kWh": 0.0,
                "sizing_satisfied": True,
                "switch_on_count": 0,
                "reheat_runtime_min": 0.0,
                "time_lag_min": 0.0,
            }
        )
        return ts, summary

    def _simulate_storage_system(self, data: pd.DataFrame | pd.Series) -> tuple[pd.DataFrame, dict[str, float | str | bool]]:
        minute = self._representative_minute_needs(data)
        start_power = self.nominal_power_kW or self._start_power_kW(minute)
        start_volume = self.storage_volume_l or self._start_volume_l(minute, start_power)

        selected_power = start_power
        selected_volume = start_volume

        if self.sizing_mode == "auto":
            if self.nominal_power_kW <= _KWH_EPS:
                self.sizing_mode = "size_power"
            else:
                self.sizing_mode = "size_storage"

        if self.sizing_mode == "size_storage":
            selected_volume = self._size_storage_volume(minute, start_volume, selected_power)
        elif self.sizing_mode == "size_power":
            selected_power = self._size_nominal_power(minute, selected_volume, start_power)

        ts, summary = self._simulate_supply_curve(
            minute,
            selected_volume,
            selected_power,
        )
        self.storage_standby_loss_kWh_d = float(summary["q_sb_sto_kWh_d"])
        summary["V_sto_input_l"] = self.storage_volume_l
        summary["V_sto_selected_l"] = selected_volume
        summary["phi_N_input_kW"] = self.nominal_power_kW
        summary["phi_N_selected_kW"] = selected_power
        summary["sizing_mode"] = self.sizing_mode
        return ts, summary

    def _representative_minute_needs(self, data: pd.DataFrame | pd.Series) -> pd.Series:
        if isinstance(data, pd.Series):
            series = data.copy()
        else:
            for col in ["Q_W_kWh", "Q_W_nd_kWh", "DHW_kWh", "Q_DHW_kWh", "dhw_kWh"]:
                if col in data:
                    series = data[col].copy()
                    break
            else:
                raise ValueError("DHW design sizing requires a Q_W_kWh/DHW demand column.")

        if not isinstance(series.index, pd.DatetimeIndex):
            base = pd.Timestamp("2001-01-01 00:00:00")
            series.index = pd.date_range(base, periods=len(series), freq="h")
        series = series.sort_index().astype(float).clip(lower=0.0)
        if series.index.has_duplicates:
            series = series.groupby(level=0).sum()
        if self.demand_unit == "wh":
            series = series / 1000.0

        daily = series.resample("D").sum()
        if daily.empty or float(daily.max()) <= _KWH_EPS:
            raise ValueError("DHW design sizing requires non-zero DHW demand.")
        if self.representative_day is not None:
            day = pd.Timestamp(self.representative_day).normalize()
        else:
            day = daily.idxmax().normalize()
        day_hourly = series.loc[(series.index >= day) & (series.index < day + pd.Timedelta(days=1))]
        if day_hourly.empty:
            raise ValueError(f"No DHW demand found for representative day {day.date()}.")
        full_hours = pd.date_range(day, periods=24, freq="h")
        day_hourly = day_hourly.reindex(full_hours, fill_value=0.0)

        minute_values = []
        minute_index = []
        for timestamp, value in day_hourly.items():
            per_minute = float(value) / 60.0
            for offset in range(60):
                minute_index.append(timestamp + pd.Timedelta(minutes=offset))
                minute_values.append(per_minute)
        return pd.Series(minute_values, index=pd.DatetimeIndex(minute_index), name="Q_W_need_kWh")

    def _volume_from_need(self, need: pd.Series) -> pd.Series:
        denominator = (
            _WATER_DENSITY_KG_L
            * _WATER_SPECIFIC_HEAT_CAPACITY_KWH_KG_K
            * max(self.theta_draw_C - self.theta_cold_C, _KWH_EPS)
        )
        return need / denominator

    def _start_power_kW(self, minute_need: pd.Series) -> float:
        return max(float(minute_need.sum()) / 24.0, 0.1)

    def _start_volume_l(self, minute_need: pd.Series, slope_kW: float) -> float:
        elapsed_h = pd.Series(range(len(minute_need)), index=minute_need.index, dtype=float) / 60.0
        transformed = minute_need.cumsum() - slope_kW * elapsed_h
        storage_energy = max(float(transformed.max() - transformed.min()), _KWH_EPS)
        return _volume_l_from_energy_kWh(
            storage_energy,
            self.theta_storage_max_C,
            self.theta_cold_C,
            self.loading_factor,
        )

    def _size_storage_volume(
        self,
        minute_need: pd.Series,
        start_volume_l: float,
        power_kW: float,
    ) -> float:
        low = max(1.0, min(start_volume_l, self.max_storage_volume_l))
        _, summary = self._simulate_supply_curve(minute_need, low, power_kW)
        if bool(summary["sizing_satisfied"]):
            return low

        high = max(low * 1.5, low + 25.0)
        while high < self.max_storage_volume_l:
            _, summary = self._simulate_supply_curve(minute_need, high, power_kW)
            if bool(summary["sizing_satisfied"]):
                break
            high *= 1.5
        high = min(high, self.max_storage_volume_l)

        for _ in range(40):
            mid = 0.5 * (low + high)
            _, summary = self._simulate_supply_curve(minute_need, mid, power_kW)
            if bool(summary["sizing_satisfied"]):
                high = mid
            else:
                low = mid
            if high - low < 0.1:
                break
        return high

    def _size_nominal_power(
        self,
        minute_need: pd.Series,
        volume_l: float,
        start_power_kW: float,
    ) -> float:
        low = max(0.1, min(start_power_kW, self.max_nominal_power_kW))
        _, summary = self._simulate_supply_curve(minute_need, volume_l, low)
        if bool(summary["sizing_satisfied"]):
            return low

        high = max(low * 1.5, low + 0.5)
        while high < self.max_nominal_power_kW:
            _, summary = self._simulate_supply_curve(minute_need, volume_l, high)
            if bool(summary["sizing_satisfied"]):
                break
            high *= 1.5
        high = min(high, self.max_nominal_power_kW)

        for _ in range(40):
            mid = 0.5 * (low + high)
            _, summary = self._simulate_supply_curve(minute_need, volume_l, mid)
            if bool(summary["sizing_satisfied"]):
                high = mid
            else:
                low = mid
            if high - low < 0.001:
                break
        return high

    def _simulate_supply_curve(
        self,
        minute_need: pd.Series,
        storage_volume_l: float,
        nominal_power_kW: float,
    ) -> tuple[pd.DataFrame, dict[str, float | str | bool]]:
        loading_factor = float(
            self.input_data.get(
                "loading_factor",
                _annex_b_loading_factor(self.system_type, storage_volume_l),
            )
        )
        q_max = _storage_capacity_kWh(
            storage_volume_l,
            self.theta_storage_max_C,
            self.theta_cold_C,
            loading_factor,
        )
        sensor_ratio = min(max(self.sensor_height_m / max(self.storage_height_m, _KWH_EPS), 0.0), 1.0)
        q_on = q_max * (1.0 - sensor_ratio)
        if self.system_type == "mixed_storage":
            q_min = _storage_capacity_kWh(
                storage_volume_l,
                self.theta_draw_C,
                self.theta_cold_C,
                loading_factor,
            ) * (1.0 - 0.5 * sensor_ratio)
        else:
            q_min = 0.0
        q_off = q_max
        q_residual = q_max

        q_sb_sto_kWh_d = self._standby_loss_kWh_d_for_volume(storage_volume_l)
        storage_loss_min = self._storage_loss_kWh_min(q_sb_sto_kWh_d)
        distribution_loss_min = self._distribution_loss_kWh_min()
        loss_power_kW = (storage_loss_min + distribution_loss_min) * 60.0
        phi_eff_nominal = max(nominal_power_kW - loss_power_kW, 0.0)

        reheat_on = False
        lag_remaining = 0
        active_minutes = 0
        switch_count = 0
        q_at_switch = q_residual
        theta_at_switch = self._theta_from_storage_energy(q_at_switch, storage_volume_l)

        rows = []
        supply_cum = q_residual
        need_cum = 0.0
        reheat_cum = 0.0
        storage_loss_cum = 0.0
        distribution_loss_cum = 0.0

        for timestamp, need in minute_need.items():
            need = float(need)

            if (not reheat_on) and q_residual <= q_on + _KWH_EPS:
                reheat_on = True
                lag_remaining = int(round(self.time_lag_min))
                active_minutes = 0
                switch_count += 1
                q_at_switch = q_residual
                theta_at_switch = self._theta_from_storage_energy(q_at_switch, storage_volume_l)

            if reheat_on and lag_remaining > 0:
                q_reheat = 0.0
                phi_eff = 0.0
                lag_remaining -= 1
            elif reheat_on:
                phi_eff = self._effective_power_kW(
                    nominal_power_kW,
                    phi_eff_nominal,
                    storage_volume_l,
                    theta_at_switch,
                    active_minutes,
                    loss_power_kW,
                )
                q_reheat = max(phi_eff, 0.0) / 60.0
                active_minutes += 1
            else:
                phi_eff = 0.0
                q_reheat = 0.0

            q_residual = q_residual - need - storage_loss_min - distribution_loss_min + q_reheat
            q_residual = min(q_residual, q_max)
            if reheat_on and q_residual >= q_off - self.sizing_tolerance_kWh:
                reheat_on = False
                lag_remaining = 0
                active_minutes = 0

            need_cum += need
            reheat_cum += q_reheat
            storage_loss_cum += storage_loss_min
            distribution_loss_cum += distribution_loss_min
            supply_cum = q_max + reheat_cum - storage_loss_cum - distribution_loss_cum
            margin = q_residual - q_min

            rows.append(
                {
                    "datetime": timestamp,
                    "Q_W_need_kWh": need,
                    "V_W_draw_l": self._volume_from_need(pd.Series([need])).iloc[0],
                    "Q_W_need_cum_kWh": need_cum,
                    "Q_W_supply_cum_kWh": supply_cum,
                    "Q_W_sto_residual_kWh": q_residual,
                    "Q_W_sto_max_kWh": q_max,
                    "Q_W_sto_min_kWh": q_min,
                    "Q_W_sto_on_kWh": q_on,
                    "Q_W_sto_off_kWh": q_off,
                    "Q_W_storage_loss_kWh": storage_loss_min,
                    "Q_W_distribution_loss_kWh": distribution_loss_min,
                    "Q_W_reheat_effective_kWh": q_reheat,
                    "phi_eff_kW": phi_eff,
                    "reheat_on": reheat_on,
                    "lag_remaining_min": lag_remaining,
                    "supply_margin_kWh": margin,
                }
            )

        ts = pd.DataFrame(rows).set_index("datetime")
        summary = self._base_summary(ts, storage_loss_min, distribution_loss_min)
        summary.update(
            {
                "system_type": self.system_type,
                "Q_sto_max_kWh": q_max,
                "Q_sto_min_kWh": q_min,
                "Q_sto_on_kWh": q_on,
                "Q_sto_off_kWh": q_off,
                "loading_factor": loading_factor,
                "q_sb_sto_kWh_d": q_sb_sto_kWh_d,
                "q_sb_sto_source": self.storage_standby_loss_source,
                "storage_loss_kWh_design_day": float(ts["Q_W_storage_loss_kWh"].sum()),
                "distribution_loss_kWh_design_day": float(ts["Q_W_distribution_loss_kWh"].sum()),
                "phi_eff_nominal_kW": phi_eff_nominal,
                "time_lag_min": self.time_lag_min,
                "switch_on_count": switch_count,
                "reheat_runtime_min": float((ts["Q_W_reheat_effective_kWh"] > 0.0).sum()),
                "supply_margin_min_kWh": float(ts["supply_margin_kWh"].min()),
                "sizing_satisfied": bool(ts["supply_margin_kWh"].min() >= -self.sizing_tolerance_kWh),
                "design_flow_l_s": float(ts["V_W_draw_l"].max()) / 60.0,
                "design_flow_m3_h": float(ts["V_W_draw_l"].max()) / 60.0 * 3.6,
            }
        )
        return ts, summary

    def _effective_power_kW(
        self,
        nominal_power_kW: float,
        phi_eff_nominal_kW: float,
        storage_volume_l: float,
        theta_at_switch_C: float,
        active_minutes: int,
        loss_power_kW: float,
    ) -> float:
        if self.system_type == "loading_storage":
            return phi_eff_nominal_kW

        heat_exchanger_power = (
            self.heat_exchanger_power_kW
            if self.heat_exchanger_power_explicit
            else nominal_power_kW
        )
        tau = self._mixed_storage_time_constant_min(storage_volume_l)
        theta_mean = self.theta_charge_C - (
            self.theta_charge_C - theta_at_switch_C
        ) * pow(2.718281828459045, -max(active_minutes, 0) / max(tau, _KWH_EPS))
        denominator = max(self.theta_charge_C - self.theta_cold_C, _KWH_EPS)
        approach = 1.0 - (theta_mean - self.theta_cold_C) / denominator
        return max(heat_exchanger_power * approach - loss_power_kW, 0.0)

    def _mixed_storage_time_constant_min(self, storage_volume_l: float) -> float:
        ua = max(float(self.input_data.get("heat_exchanger_UA_W_K", 0.0)), 0.0)
        if ua <= _KWH_EPS:
            return max(float(self.input_data.get("mixed_storage_time_constant_min", 45.0)), 1.0)
        mass = storage_volume_l * _WATER_DENSITY_KG_L
        return 0.06 * mass * _WATER_SPECIFIC_HEAT_CAPACITY_KJ_KG_K / ua

    def _theta_from_storage_energy(self, q_kWh: float, storage_volume_l: float) -> float:
        denominator = storage_volume_l * _WATER_DENSITY_KG_L * _WATER_SPECIFIC_HEAT_CAPACITY_KWH_KG_K
        if denominator <= _KWH_EPS:
            return self.theta_cold_C
        return self.theta_cold_C + max(q_kWh, 0.0) / denominator

    def _standby_loss_kWh_d_for_volume(self, storage_volume_l: float) -> float:
        if self._explicit_standby_loss_kWh_d is not None:
            standby_loss = self._explicit_standby_loss_kWh_d
        else:
            standby_loss = _annex_b_standby_loss_kWh_d(max(float(storage_volume_l), 5.0))
        return max(standby_loss, 0.0) + 0.1 * self.additional_storage_connections

    def _storage_loss_kWh_min(self, standby_loss_kWh_d: float | None = None) -> float:
        if standby_loss_kWh_d is None:
            standby_loss_kWh_d = self.storage_standby_loss_kWh_d
        return (
            max(float(standby_loss_kWh_d), 0.0)
            * max(self.theta_storage_max_C - self.theta_ambient_C, 0.0)
            / 45.0
            / 1440.0
        )

    def _distribution_loss_kWh_min(self) -> float:
        if self.distribution_pipe_sections:
            loss_W = 0.0
            for section in self.distribution_pipe_sections:
                length = max(float(section.get("length_m", 0.0)), 0.0)
                psi = max(
                    float(
                        section.get(
                            "linear_thermal_transmittance_W_mK",
                            section.get("U_W_mK", 0.0),
                        )
                    ),
                    0.0,
                )
                ambient = float(section.get("ambient_temperature_C", self.theta_ambient_C))
                theta_m = float(section.get("mean_water_temperature_C", self.theta_pipe_mean_C))
                loss_W += psi * length * max(theta_m - ambient, 0.0)
            return loss_W / 60000.0
        return self.specific_distribution_loss_W_m * self.distribution_length_m / 60000.0

    def _base_summary(
        self,
        ts: pd.DataFrame,
        storage_loss_min: float,
        distribution_loss_min: float,
    ) -> dict[str, float | str | bool]:
        q_design = float(ts["Q_W_need_kWh"].sum())
        volume_l = float(ts["V_W_draw_l"].sum()) if "V_W_draw_l" in ts else 0.0
        representative_day = ts.index[0].date().isoformat() if len(ts.index) else ""
        return {
            "representative_day": representative_day,
            "Q_W_design_day_kWh": q_design,
            "V_W_design_day_l": volume_l,
            "Q_W_peak_minute_kWh": float(ts["Q_W_need_kWh"].max()),
            "V_W_peak_minute_l": float(ts["V_W_draw_l"].max()) if "V_W_draw_l" in ts else 0.0,
            "theta_W_draw_C": self.theta_draw_C,
            "theta_W_cold_C": self.theta_cold_C,
            "theta_W_sto_max_C": self.theta_storage_max_C,
            "theta_W_ambient_C": self.theta_ambient_C,
            "Q_W_storage_loss_kWh_per_min": storage_loss_min,
            "Q_W_distribution_loss_kWh_per_min": distribution_loss_min,
        }

# ================================================================================
#                           CALENDAR RESOLUTION (by nation name)
# ================================================================================

def get_calendar_by_name(nation_name: str):
    """
    Return a Workalendar country instance given a human-readable nation name,
    e.g. 'Italy'. Uses the registry when available; falls back to a small map.
    """
    try:
        from workalendar.registry import registry
        cal_cls = registry.get(nation_name)
        if cal_cls is None:
            raise KeyError(nation_name)
        return cal_cls()
    except Exception:
        # Fallback for common EU countries (extend as needed)
        try:
            from workalendar.europe import Austria, France, Germany, Greece, Italy, Spain, Switzerland
            fallback = {
                "Austria": Austria,
                "France": France,
                "Germany": Germany,
                "Greece": Greece,
                "Italy": Italy,
                "Spain": Spain,
                "Switzerland": Switzerland,
            }
            return fallback[nation_name]()
        except Exception as e:
            raise ValueError(
                f"Cannot resolve calendar for nation '{nation_name}'. "
                "Ensure 'workalendar' is installed and the name is valid."
            ) from e


def generate_daily_calendar(year: int, month: int, country_calendar) -> dict:
    """Generates daily status (Holiday, Working, Non-Working) for a given month/year."""
    daily_calendar = {}
    holidays = [h[0] for h in country_calendar.holidays(year)]
    for day in range(1, 32):
        try:
            current_date = date(year, month, day)
        except ValueError:
            break  # stop when month runs out of days
        if current_date in holidays:
            status = "Holiday"
        elif country_calendar.is_working_day(current_date):
            status = "Working"
        else:
            status = "Non-Working"
        daily_calendar[current_date.strftime("%Y-%m-%d")] = status
    return daily_calendar


def generate_calendar(nation_name: str, year: int) -> pd.DataFrame:
    """
    Create a calendar DataFrame for the full year for a given nation name.
    Returns columns: ['days' (Timestamp), 'values' in {'Working','Non-Working','Holiday'}].
    """
    cal = get_calendar_by_name(nation_name)

    rows = []
    for month in range(1, 13):
        monthly = generate_daily_calendar(year, month, cal)
        for day, val in sorted(monthly.items()):
            rows.append((pd.to_datetime(day), val))

    df = pd.DataFrame(rows, columns=["days", "values"]).dropna(subset=["days"])
    df = df.sort_values("days").drop_duplicates(subset=["days"], keep="last").reset_index(drop=True)

    # Ensure full coverage (if anything missing)
    full_range = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    existing = set(df["days"].dt.normalize())
    missing = [d for d in full_range if d.normalize() not in existing]
    if missing:
        def label_for(d):
            return "Working" if cal.is_working_day(d) else "Holiday"
        add_rows = [(d, label_for(d)) for d in missing]
        df = pd.concat([df, pd.DataFrame(add_rows, columns=["days", "values"])], ignore_index=True)
        df = df.sort_values("days").reset_index(drop=True)
    return df



def calc_V_w_day_through_V_w_p_day(method: Optional[str] = None,
                                  building_area: Optional[float] = None,
                                  building_type: Optional[str] = None,
                                  V_w_p_day: Optional[float] = None):
    '''
    For single-family dwellings and apartment dwellings, V_W_p_day is calculated
    from the number of equivalent persons (adults).

    :param mode: two methods can be used: 
        1) 'number_of_person' providing the number of person' 
        2) 'building_area': providing the area of the building 
        3) 'number_of_units': providing specific units according to Table B.4
    :param method: possible selection: 
        1) 'correlation': using correlation of B.5
        2) 'table': using table of B.5
    :param building_area: useful or habitable floor area [m2]
    :param building_type:  type of building, possible choice: 'Single_family_house', 'Attached_house', 'Dwelling'
    :param num_person: number of person inhabiting the dwelling
    :param V_w_f_day: value taken from the dataframe "table_b_5"
    :param V_w_p_day: value of liters of DHW per person taken from table b_5 modified

    '''

    if building_type in {'Single_family_house', 'Attached_house'}:
        if building_area < 30: 
            n_p_eq_max = 1
        elif 30 <=building_area <= 70:
            n_p_eq_max = 1.775-0.01875*(70-building_area)
        else:
            n_p_eq_max = 0.025*building_area

    elif building_type == 'Dwelling':
        if building_area < 10: 
            n_p_eq_max = 1
        elif 10 <=building_area <= 50:
            n_p_eq_max = 1.775-0.01875*(50-building_area)
        else:
            n_p_eq_max = 0.035*building_area
    else: 
        raise ValueError("Error")

    if n_p_eq_max < 1.75:
        np_eq = n_p_eq_max
    else: 
        np_eq = 1.75+0.3*(n_p_eq_max -1.75)

    if  method == 'correlation':
        # For these residential cases and at the level of one dwelling, requirements can be expressd by :
        V_w_nd_ref = max(40.71, (3.26*building_area/np_eq))/1000 #[m3]
    elif method == 'table':
        V_w_nd_ref = V_w_p_day*np_eq/1000
    else:
        raise ValueError("Invalid method. Choose either 'correlation' or 'table'.")

    return V_w_nd_ref



# ======================================================================
'''
Calculation based on usage and floor area
'''

def get_days(year):
    """Calculate the number of days per month for a given year excluding days from adjoining months represented as '0'.
    
    Args:
    :param: year (int): The year for which to calculate days per month.

    Returns:
        list: A list containing the number of valid days for each month of the specified year.
    """
    days_per_month = []
    for month in range(1, 13):  # Looping through each month (1 to 12)
        # Getting the week list for each month
        month_weeks = calendar.monthcalendar(year, month)
        # Counting days excluding '0' which represents days of the adjoining month
        days_count = sum(day != 0 for week in month_weeks for day in week)
        days_per_month.append(days_count) 

    return days_per_month



def Volume_and_energy_DHW_calculation(
    n_workdays: int,
    n_weekends: int,
    n_holidays: int,
    sum_fractions: pd.DataFrame,
    total_days: int,
    hourly_fractions: pd.DataFrame,
    theta_W_draw: float,
    theta_w_c_ref: float,
    theta_w_h_ref: float,
    theta_W_cold: float,
    mode_calc: str,
    building_type_B3: str,
    building_area: float,
    unit_count: int,
    building_type_B5: str,
    residential_typology: str,
    calculation_method: str,
    year: int,
    country_calendar: pd.DataFrame
    ):
    '''
    Calculate daily, monthly, yearly and calendar-expanded hourly energy and
    volume needs for Domestic Hot Water (DHW) based on the building parameters
    and usage.

    Param
    ------
    :param: n_workdays (int): Number of workdays in the year.
    :param: n_weekends (int): Number of weekend days in the year.
    :param: n_holidays (int): Number of holidays in the year.
    :param: sum_fractions (DataFrame): Sum of hourly usage fractions.
    :param: total_days (int): Total number of days in the year.
    :param: hourly_fractions (DataFrame): Hourly usage fractions for different day types.
    :param: theta_W_draw: Water temperature of the mixed (cold and hot) water drawn at the tap
    :param: theta_w_c_ref:
    :param: theta_w_h_ref:
    :param: theta_W_cold: cold water temperature
    :param: mode (str): calculation mode to be used to get the volume and energy for DHW:
        1. 'Area': using the area of the building
        2. 'number_of_units': number of units according to table B4, B5 
        3. 'volume_type_bui': if the building is 'Single_family_house', 'Attached_house', or 'Dwellings', the calculation
            is based on the number of equivalent persons (adults)
    :param: building_type_B3 (str): Building usage type as defined in table B3.
    :param: building_area (float): Building area in square meters.
    :param: unit_count (int): Number of units (e.g., beds, rooms).
    :param: building_type_B5 (str): Building type as defined in table B5.
    :param: residential_typology (str): Specific residential typology.
    :param: calculation_method (str): Method used for calculations ('correlation', etc.).
    :param: year (int): Year for which the calculations are performed.
    :param: country_calendar (DataFrame): Calendar with 'values' column providing
        'Working', 'Non-Working', or 'Holiday' labels for each day.

    Return
    -------
        tuple: Contains detailed DHW needs calculations. The historical tuple
            order is preserved:
            (yearly_cons, V_W_nd_d, monthly_volume, yearly_volume, Q_W_nd_d,
            V_W_nd_h_i, hourly_cons_volume, hourly_cons_energy), where
            V_W_nd_d and Q_W_nd_d are daily needs and hourly_cons_volume /
            hourly_cons_energy are calendar-expanded hourly annual series.
    '''
    
    if not isinstance(country_calendar, pd.DataFrame) or "values" not in country_calendar.columns:
        raise TypeError("country_calendar must be a DataFrame with a 'values' column.")

    if building_type_B5 in {'Single_family_house', 'Attached_house', 'Dwelling'}:
        selection_B5 = table_B_5_modified.loc[
            table_B_5_modified['type_of_building'] == residential_typology, :
        ]
        if selection_B5.empty:
            raise ValueError(
                f"Residential typology '{residential_typology}' not found in table_B_5_modified."
            )
        if len(selection_B5) > 1:
            raise ValueError(
                f"Multiple entries found for residential typology '{residential_typology}' in table_B_5_modified."
            )
        liters_per_person = float(selection_B5.iloc[0]['liters/person_per_day'])
        V_nd_d_ref = calc_V_w_day_through_V_w_p_day(
            method = calculation_method, 
            building_type = building_type_B5, 
            building_area=building_area, 
            V_w_p_day = liters_per_person
            )

        V_W_nd_d = V_nd_d_ref*(theta_w_h_ref-theta_w_c_ref)/(theta_W_draw-theta_w_c_ref)
        
    elif building_type_B5 in {
            'Accomodation', 'Health establishment wihtout accomodation', 
            'Health establishment without accomodation',
            'Health establishment without accomodation - without laundry',
            'Catering, 2 meals per day. Traditional cusine',
            'Catering, 2 meals per day. Self service', 
            'Catering, 1 meals per day. Tradional cusine', 
            'Catering, 1 meals per day. Self service',
            'Hotel, 1-star without laundry', 'Hotel, 1-star withlaundry', 
            'Hotel, 2-star without laundry', 'Hotel, 2-star withlaundry', 
            'Hotel, 3-star without laundry', 'Hotel, 3-star withlaundry', 
            'Hotel, 4-star and GC without laundry', 'Hotel, 4-star and GC withlaundry', 
            'Sport_establishment'
        }: 
        
        if mode_calc == 'area':
            selection_B3 =  table_B_3.loc[table_B_3['type_of_usage']==building_type_B3, :]
            if selection_B3.empty:
                raise ValueError(f"Building usage '{building_type_B3}' not found in table_B_3.")
            if len(selection_B3) > 1:
                raise ValueError(f"Multiple entries found for usage '{building_type_B3}' in table_B_3.")
            # Area specific in kWh/m2d
            area_specific = float(selection_B3.iloc[0]['Area specific - Wh/m2d'])/1000
            # Q_W_calculation: daily energy need at reference condition
            Q_W_nd_d_ref = area_specific * building_area
            # Daily Volume need at  delivery temperature
            V_W_nd_d = Q_W_nd_d_ref/(WATER_DENSITY*WATER_SPECIFIC_HEAT_CAPACITY*(theta_W_draw-theta_w_c_ref))
        elif mode_calc == 'number_of_units':
            selection_B3 =  table_B_3.loc[table_B_3['type_of_usage']==building_type_B3, :]
            if selection_B3.empty:
                raise ValueError(f"Building usage '{building_type_B3}' not found in table_B_3.")
            if len(selection_B3) > 1:
                raise ValueError(f"Multiple entries found for usage '{building_type_B3}' in table_B_3.")
            energy_need = float(selection_B3.iloc[0]['Usage dependent'])
            Q_W_nd_d_ref = unit_count * energy_need 
            # Daily Volume need at  delivery temperature
            V_W_nd_d = Q_W_nd_d_ref/(WATER_DENSITY*WATER_SPECIFIC_HEAT_CAPACITY*(theta_W_draw-theta_w_c_ref))
        elif mode_calc == 'volume_type_bui':
            
            selection_B4 = table_B_4.loc[table_B_4['type_of_activity']==building_type_B5,:]
            if selection_B4.empty:
                raise ValueError(f"Activity '{building_type_B5}' not found in table_B_4.")
            if len(selection_B4) > 1:
                raise ValueError(f"Multiple entries found for activity '{building_type_B5}' in table_B_4.")
            # Daily volume'
            V_nd_d_ref = (unit_count*float(selection_B4.iloc[0]['V_W_f_day']))/1000
            # Daily volume need at delivery temperature
            V_W_nd_d = V_nd_d_ref*(theta_w_h_ref-theta_w_c_ref)/(theta_W_draw-theta_w_c_ref)
        else: 
            raise ValueError("select the right calculation mode from 'area', 'number_of_units', 'volume_type_bui'")
    else: 
        raise ValueError("select the building typology according to those defined in the table")

    # Daily energy need
    V_W_nd_d = float(V_W_nd_d)
    Q_W_nd_d = float(V_W_nd_d * WATER_DENSITY * WATER_SPECIFIC_HEAT_CAPACITY * (theta_W_draw-theta_W_cold))
    # Q_W = area_specific * building_area * n_day
    
    # Monthly Energy Need Calculation
    monthly_cons = [ days * Q_W_nd_d for days in get_days(year)]
    # Yearly Energy Need total of monthly energy needs
    yearly_cons = sum(monthly_cons)

    # Monthly Volume needs
    monthly_volume = [ days * V_W_nd_d for days in get_days(year)]
    # Yearly Volume needs
    yearly_volume = sum(monthly_volume)

    # Annual fractions for workdays
    fractions_workday = n_workdays*sum_fractions.T['Workday'].values[0]
    # Annual fractions for weekends
    fractions_weekend = n_weekends*sum_fractions.T['Weekend'].values[0]
    # Annual fractions for holidays
    fractions_holiday = n_holidays*sum_fractions.T['Holiday'].values[0]

    tot_fractions = fractions_workday + fractions_weekend + fractions_holiday
    # Average correction factor
    fx_avg = total_days / tot_fractions 
    # Hourly needs, corrected fractions of daily needs
    x_q_h_i_coor = hourly_fractions * fx_avg # dataframe with corrected fraction for workdays weekend and holidays
    
    # Hourly need as a volume at theta_draw
    V_W_nd_h_i = x_q_h_i_coor * V_W_nd_d  # dataframe with corrected fraction for workdays weekend and holidays
    # Hourly need as energy
    Q_W_nd_h_i = x_q_h_i_coor * Q_W_nd_d
    # Calendar-expanded hourly result.
    hourly_cons_volume = []
    hourly_cons_energy = []
    for i, day_type in country_calendar.iterrows():
        if day_type['values'] == 'Working':
            col = 'Workday'
        elif day_type['values'] == 'Non-Working':
            col = 'Weekend'
        else:
            col = 'Holiday'
        for item_V in V_W_nd_h_i[col].values.tolist():
            hourly_cons_volume.append(item_V)
        for item_Q in Q_W_nd_h_i[col].values.tolist():
            hourly_cons_energy.append(item_Q)
    
    return yearly_cons, V_W_nd_d, monthly_volume, yearly_volume, Q_W_nd_d, V_W_nd_h_i, hourly_cons_volume, hourly_cons_energy
