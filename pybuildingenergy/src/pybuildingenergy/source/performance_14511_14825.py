"""Heat-pump product rating data according to EN 14511 and EN 14825.

The module normalizes manufacturer or example rating data into the capacity and
COP/EER maps used by the generation calculators. It also exposes the EN 14825
part-load degradation factor used by water-based heat pumps and chillers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


_EPS = 1e-12


@dataclass
class HeatPumpPerformanceDataResult:
    """Normalized product-performance data for heat-pump calculations."""

    rating_points: pd.DataFrame
    heating_map: pd.DataFrame
    cooling_map: pd.DataFrame
    summary: dict[str, float]
    inputs: dict[str, Any]


class HeatPumpPerformanceDataCalculator:
    """Prepare EN 14511 rating and EN 14825 part-load performance data.

    Parameters
    ----------
    input_data:
        Dictionary with ``heating_rating_points`` and/or
        ``cooling_rating_points``. Rating points can provide either
        ``capacity_kW`` plus ``cop``/``eer`` or ``capacity_kW`` plus
        ``input_power_kW``. Optional ``part_load_ratio`` and design-load values
        are used to calculate EN 14825 ``COPbin``/``EERbin`` inspection values.
    """

    def __init__(self, input_data: dict[str, Any] | None = None):
        self.input_data = dict(input_data or {})
        self.unit_type = str(self.input_data.get("unit_type", "air-to-water")).lower()
        self.capacity_control = str(self.input_data.get("capacity_control", "fixed")).lower()
        self.heating_design_load_kW = _optional_float(
            self.input_data.get("heating_design_load_kW")
        )
        self.cooling_design_load_kW = _optional_float(
            self.input_data.get("cooling_design_load_kW")
        )
        self.heating_degradation_coefficient = _coefficient(
            self.input_data.get("heating_degradation_coefficient", 0.9),
            "heating_degradation_coefficient",
        )
        self.cooling_degradation_coefficient = _coefficient(
            self.input_data.get("cooling_degradation_coefficient", 0.9),
            "cooling_degradation_coefficient",
        )

    def run(self) -> HeatPumpPerformanceDataResult:
        """Return normalized rating points, maps and an aggregate summary."""

        heating = self._normalize_points(
            self.input_data.get("heating_rating_points", []),
            mode="heating",
            performance_column="cop",
            design_load_kW=self.heating_design_load_kW,
            degradation_coefficient=self.heating_degradation_coefficient,
        )
        cooling = self._normalize_points(
            self.input_data.get("cooling_rating_points", []),
            mode="cooling",
            performance_column="eer",
            design_load_kW=self.cooling_design_load_kW,
            degradation_coefficient=self.cooling_degradation_coefficient,
        )
        rating_points = pd.concat([heating, cooling], ignore_index=True)
        heating_map = _map_from_points(heating, "cop")
        cooling_map = _map_from_points(cooling, "eer")
        summary = self._summarize(rating_points)
        return HeatPumpPerformanceDataResult(
            rating_points=rating_points,
            heating_map=heating_map,
            cooling_map=cooling_map,
            summary=summary,
            inputs=dict(self.input_data),
        )

    def _normalize_points(
        self,
        rows: Any,
        mode: str,
        performance_column: str,
        design_load_kW: float | None,
        degradation_coefficient: float,
    ) -> pd.DataFrame:
        df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
        columns = [
            "mode",
            "rating_condition",
            "source_temperature_C",
            "sink_temperature_C",
            "capacity_kW",
            performance_column,
            "input_power_kW",
            "part_load_ratio",
            "reference_load_kW",
            "capacity_ratio",
            "degradation_coefficient",
            "part_load_factor",
            "performance_at_part_load",
            "test_standard",
        ]
        if df.empty:
            return pd.DataFrame(columns=columns)

        df = _rename_aliases(df, performance_column)
        required = ["source_temperature_C", "sink_temperature_C", "capacity_kW"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"{mode}_rating_points are missing required columns: {missing}.")
        if performance_column not in df.columns and "input_power_kW" not in df.columns:
            raise ValueError(
                f"{mode}_rating_points must include {performance_column} or input_power_kW."
            )

        for col in ["source_temperature_C", "sink_temperature_C", "capacity_kW"]:
            df.loc[:, col] = pd.to_numeric(df[col], errors="coerce")
        if "input_power_kW" in df.columns:
            df.loc[:, "input_power_kW"] = pd.to_numeric(df["input_power_kW"], errors="coerce")
        if performance_column in df.columns:
            df.loc[:, performance_column] = pd.to_numeric(
                df[performance_column], errors="coerce"
            )
        else:
            df.loc[:, performance_column] = np.nan
        if "input_power_kW" not in df.columns:
            df.loc[:, "input_power_kW"] = np.nan

        missing_perf = df[performance_column].isna()
        df.loc[missing_perf, performance_column] = (
            df.loc[missing_perf, "capacity_kW"]
            / df.loc[missing_perf, "input_power_kW"].replace(0.0, np.nan)
        )
        missing_power = df["input_power_kW"].isna()
        df.loc[missing_power, "input_power_kW"] = (
            df.loc[missing_power, "capacity_kW"]
            / df.loc[missing_power, performance_column].replace(0.0, np.nan)
        )

        if "part_load_ratio" in df.columns:
            df.loc[:, "part_load_ratio"] = pd.to_numeric(
                df["part_load_ratio"], errors="coerce"
            ).fillna(1.0)
        else:
            df.loc[:, "part_load_ratio"] = 1.0
        df.loc[:, "part_load_ratio"] = df["part_load_ratio"].clip(lower=0.0)

        if "reference_load_kW" in df.columns:
            df.loc[:, "reference_load_kW"] = pd.to_numeric(
                df["reference_load_kW"], errors="coerce"
            )
        elif design_load_kW is not None:
            df.loc[:, "reference_load_kW"] = df["part_load_ratio"] * design_load_kW
        else:
            df.loc[:, "reference_load_kW"] = df["capacity_kW"]
        df.loc[:, "reference_load_kW"] = df["reference_load_kW"].fillna(df["capacity_kW"])

        if "degradation_coefficient" in df.columns:
            df.loc[:, "degradation_coefficient"] = pd.to_numeric(
                df["degradation_coefficient"], errors="coerce"
            ).fillna(degradation_coefficient)
        else:
            df.loc[:, "degradation_coefficient"] = degradation_coefficient
        df.loc[:, "degradation_coefficient"] = df["degradation_coefficient"].clip(
            lower=0.0, upper=1.0
        )

        df.loc[:, "capacity_ratio"] = (
            df["reference_load_kW"] / df["capacity_kW"].replace(0.0, np.nan)
        ).clip(lower=0.0, upper=1.0)
        df.loc[:, "capacity_ratio"] = df["capacity_ratio"].fillna(1.0)
        df.loc[:, "part_load_factor"] = [
            en14825_part_load_factor(
                capacity_ratio=cr,
                degradation_coefficient=cd,
                unit_type=self.unit_type,
            )
            for cr, cd in zip(df["capacity_ratio"], df["degradation_coefficient"])
        ]
        if self.capacity_control not in {"fixed", "on-off", "on_off"}:
            close_to_load = df["capacity_ratio"] >= 0.9
            df.loc[close_to_load, "part_load_factor"] = 1.0
        df.loc[:, "performance_at_part_load"] = (
            df[performance_column] * df["part_load_factor"]
        )
        df.loc[:, "mode"] = mode
        if "rating_condition" not in df.columns:
            df.loc[:, "rating_condition"] = ""
        if "test_standard" not in df.columns:
            df.loc[:, "test_standard"] = "EN 14511-2 / EN 14825"

        keep = columns
        out = df[keep].copy()
        out = out.replace([np.inf, -np.inf], np.nan).dropna(
            subset=["source_temperature_C", "sink_temperature_C", "capacity_kW", performance_column]
        )
        if (out["capacity_kW"] < 0).any() or (out[performance_column] <= 0).any():
            raise ValueError(f"{mode}_rating_points contain invalid capacity or performance values.")
        return out

    def _summarize(self, rating_points: pd.DataFrame) -> dict[str, float]:
        if rating_points.empty:
            return {}

        heating = rating_points[rating_points["mode"] == "heating"]
        cooling = rating_points[rating_points["mode"] == "cooling"]
        summary = {
            "rating_point_count": float(len(rating_points)),
            "heating_rating_point_count": float(len(heating)),
            "cooling_rating_point_count": float(len(cooling)),
            "heating_design_load_kW": float(self.heating_design_load_kW or 0.0),
            "cooling_design_load_kW": float(self.cooling_design_load_kW or 0.0),
            "heating_degradation_coefficient": self.heating_degradation_coefficient,
            "cooling_degradation_coefficient": self.cooling_degradation_coefficient,
        }
        if not heating.empty:
            summary.update(
                {
                    "heating_capacity_min_kW": float(heating["capacity_kW"].min()),
                    "heating_capacity_max_kW": float(heating["capacity_kW"].max()),
                    "heating_cop_declared_mean": float(heating["cop"].mean()),
                    "heating_cop_part_load_mean": float(
                        heating["performance_at_part_load"].mean()
                    ),
                }
            )
        if not cooling.empty:
            summary.update(
                {
                    "cooling_capacity_min_kW": float(cooling["capacity_kW"].min()),
                    "cooling_capacity_max_kW": float(cooling["capacity_kW"].max()),
                    "cooling_eer_declared_mean": float(cooling["eer"].mean()),
                    "cooling_eer_part_load_mean": float(
                        cooling["performance_at_part_load"].mean()
                    ),
                }
            )
        return summary


def en14825_part_load_factor(
    capacity_ratio: float,
    degradation_coefficient: float = 0.9,
    unit_type: str = "air-to-water",
) -> float:
    """Return the EN 14825 part-load correction multiplier.

    For air-to-water, water-to-water and DX-to-water systems this implements the
    water-based formula used in EN 14825:2022, 5.7.2.2 and 7.7.2.2. For air-to-air
    style systems the linear formula of 5.7.2.1 and 7.7.2.1 is available by
    passing ``unit_type="air-to-air"``.
    """

    cr = float(np.clip(capacity_ratio, 0.0, 1.0))
    cd = float(np.clip(degradation_coefficient, 0.0, 1.0))
    unit = str(unit_type).lower()
    if cr <= 0.0:
        return 0.0
    if unit in {"air-to-air", "water-to-air", "brine-to-air"}:
        return float(max(1.0 - cd * (1.0 - cr), _EPS))
    denominator = cd * cr + (1.0 - cd)
    return float(cr / max(denominator, _EPS))


def _map_from_points(points: pd.DataFrame, performance_column: str) -> pd.DataFrame:
    if points.empty:
        return pd.DataFrame(
            columns=["source_temperature_C", "sink_temperature_C", "capacity_kW", performance_column]
        )
    return (
        points[
            [
                "source_temperature_C",
                "sink_temperature_C",
                "capacity_kW",
                performance_column,
            ]
        ]
        .astype(float)
        .groupby(["source_temperature_C", "sink_temperature_C"], as_index=False)
        .mean()
    )


def _rename_aliases(df: pd.DataFrame, performance_column: str) -> pd.DataFrame:
    aliases = {
        "source_temperature_C": [
            "source_temperature_C",
            "source_temp_C",
            "T_source_C",
            "T_ext",
            "outdoor_temperature_C",
            "outdoor_air_temperature_C",
        ],
        "sink_temperature_C": [
            "sink_temperature_C",
            "sink_temp_C",
            "T_sink_C",
            "supply_temperature_C",
            "outlet_temperature_C",
            "leaving_water_temperature_C",
        ],
        "capacity_kW": [
            "capacity_kW",
            "declared_capacity_kW",
            "rated_capacity_kW",
            "heating_capacity_kW",
            "cooling_capacity_kW",
            "Pdh_kW",
            "Pdc_kW",
        ],
        "input_power_kW": [
            "input_power_kW",
            "effective_power_input_kW",
            "power_input_kW",
            "declared_input_power_kW",
            "P_el_kW",
            "PCon_kW",
        ],
        performance_column: [
            performance_column,
            performance_column.upper(),
            f"{performance_column}_d",
            f"{performance_column.upper()}d",
            f"declared_{performance_column}",
            f"rated_{performance_column}",
        ],
    }
    renamed: dict[str, str] = {}
    for canonical, names in aliases.items():
        for name in names:
            if name in df.columns and canonical not in df.columns:
                renamed[name] = canonical
                break
    return df.rename(columns=renamed)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _coefficient(value: Any, name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if out < 0.0 or out > 1.0:
        raise ValueError(f"{name} must be between 0 and 1.")
    return out
