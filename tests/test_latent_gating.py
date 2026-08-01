"""
Acceptance tests for Defect B — latent cooling gated to plant-on hours.

Before the fix the latent term was a *moisture balance* of the zone reported as
plant energy: charged in 8 758 of 8 760 hours against a handful of hours of
actual cooling-plant operation, 99.6 % of it with the plant off and part of it
while the heating plant was running. Summed into a single "total energy need" it
inflated the apt 305 headline roughly five-fold.

What is asserted here, on one real annual run of the canonical dictionary:

  * latent cooling is charged only in hours the cooling plant operates;
  * the "plant off" and "while heating runs" components are exactly zero;
  * the southern-hemisphere phase of the monthly profile survives the gate;
  * latent heating stays at ~0 (the C2 fix does not regress);
  * the reported total need carries an explicit sensible/latent split, and the
    ungated moisture balance is still published for audit rather than discarded.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pybuildingenergy" / "src"))
sys.path.insert(0, str(REPO_ROOT / "examples"))

from apt305_building import build_bui  # noqa: E402
from pybuildingenergy.source.check_input import sanitize_and_validate_BUI  # noqa: E402
from pybuildingenergy.source.utils import ISO52016  # noqa: E402

EPW = str(REPO_ROOT / "weather_cache" / "AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw")

# Southern-hemisphere cooling season. The gated profile must still put its
# maximum here, not in the northern-hemisphere summer.
SOUTHERN_SUMMER = {12, 1, 2, 3}


@pytest.fixture(scope="module")
def run():
    building, _ = sanitize_and_validate_BUI(build_bui(), fix=True)
    hourly, annual, _ = ISO52016.Temperature_and_Energy_needs_calculation(
        building, weather_source="epw", path_weather_file=EPW, return_sankey_data=True
    )
    dt_h = float(pd.to_numeric(annual["time_step_h"], errors="coerce").iloc[0])
    return {"hourly": hourly, "annual": annual, "dt_h": dt_h}


def _arr(run, col):
    return pd.to_numeric(run["hourly"][col], errors="coerce").fillna(0.0).to_numpy(float)


def _kwh(run, values):
    return float(np.clip(np.asarray(values, float), 0.0, None).sum() * run["dt_h"] / 1000.0)


def _ann(run, key):
    return float(pd.to_numeric(run["annual"][key], errors="coerce").iloc[0])


def test_latent_cooling_only_in_plant_on_hours(run):
    lat_c = _arr(run, "Q_latent_W")
    cooling_on = _arr(run, "Q_C") > 0.0
    charged = lat_c > 0.0
    assert charged.sum() > 0, "the gate zeroed the latent term entirely"
    assert not (charged & ~cooling_on).any(), (
        f"{int((charged & ~cooling_on).sum())} timesteps charge latent cooling "
        "with the cooling plant off"
    )


def test_latent_charged_with_cooling_off_is_zero(run):
    lat_c = _arr(run, "Q_latent_W")
    cooling_on = _arr(run, "Q_C") > 0.0
    assert _kwh(run, lat_c * ~cooling_on) == pytest.approx(0.0, abs=1e-9)


def test_no_latent_cooling_while_the_heating_plant_runs(run):
    """Physically incoherent, and worth its own assertion: heating and cooling
    are mutually exclusive here, so a non-zero result would mean the gate was
    keyed off something other than plant state."""
    lat_c = _arr(run, "Q_latent_W")
    heating_on = _arr(run, "Q_H") > 0.0
    assert _kwh(run, lat_c * heating_on) == pytest.approx(0.0, abs=1e-9)


def test_gate_actually_removed_the_bulk_of_the_ungated_term(run):
    """Guard against a no-op: the ungated series must still be much larger."""
    gated = _kwh(run, _arr(run, "Q_latent_W"))
    ungated = _kwh(run, _arr(run, "Q_latent_W_ungated"))
    assert ungated > 10.0 * max(gated, 1e-9), (
        f"gated {gated:.3f} kWh vs ungated {ungated:.3f} kWh -- the gate did nothing"
    )
    assert _ann(run, "Q_C_latent_ungated_kWh") == pytest.approx(ungated, rel=1e-9)


def test_monthly_latent_cooling_keeps_southern_hemisphere_phase(run):
    idx = pd.DatetimeIndex(run["hourly"].index)
    monthly = (
        pd.Series(_arr(run, "Q_latent_W"), index=idx)
        .clip(lower=0.0)
        .groupby(idx.month)
        .sum()
    )
    assert float(monthly.sum()) > 0.0
    assert int(monthly.idxmax()) in SOUTHERN_SUMMER, (
        f"latent cooling peaks in month {int(monthly.idxmax())}; the gate has "
        "inverted the southern-hemisphere phase"
    )


def test_latent_heating_stays_negligible(run):
    """The C2 fix took latent heating from 789 kWh to ~0. It must stay there."""
    assert _kwh(run, _arr(run, "Q_H_latent_W")) < 0.1
    assert _ann(run, "Q_H_latent_ungated_kWh") < 0.1


def test_total_need_is_reported_with_an_explicit_split(run):
    h_s = _ann(run, "Q_H_sensible_kWh")
    c_s = _ann(run, "Q_C_sensible_kWh")
    h_l = _ann(run, "Q_H_latent_kWh")
    c_l = _ann(run, "Q_C_latent_kWh")
    assert _ann(run, "Q_sensible_total_kWh") == pytest.approx(h_s + c_s, rel=1e-9)
    assert _ann(run, "Q_latent_total_kWh") == pytest.approx(h_l + c_l, rel=1e-9)
    assert _ann(run, "Q_need_total_kWh") == pytest.approx(h_s + c_s + h_l + c_l, rel=1e-9)
    # and the sensible part must still be the sensible part, unchanged by the gate
    assert h_s == pytest.approx(_ann(run, "Q_H_annual_kWh"), rel=1e-12)
    assert c_s == pytest.approx(_ann(run, "Q_C_annual_kWh"), rel=1e-12)


def test_annual_latent_matches_the_gated_hourly_series(run):
    assert _ann(run, "Q_latent_annual_kWh") == pytest.approx(
        _kwh(run, _arr(run, "Q_latent_W")), rel=1e-9
    )
