"""
Unit tests for the terrain/height local-wind profile (change 2b).

The defect these guard against is not an arithmetic slip. It is a *missing
input* that silently resolved to "the site is the same as the weather station",
which put the whole of correction C2 on the wrong side of its own pivot. So the
tests here are about the identity case being exact, the required input actually
being required, and the height term being applied in both directions.

Run with:
    python -m pytest tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pybuildingenergy" / "src"))
sys.path.insert(0, str(REPO_ROOT / "examples"))

from pybuildingenergy.source import utils as U  # noqa: E402

PIVOT_MS = 4.0   # 4u + 4 == 20 W/(m2 K), the ISO 13789 constant


# --------------------------------------------------------------------------
# The coefficients themselves
# --------------------------------------------------------------------------

def test_ashrae_table_is_the_published_one():
    """
    ASHRAE Handbook -- Fundamentals (2021), Chapter 24 "Airflow Around
    Buildings", Table 1. These are also exactly what EnergyPlus derives from
    the Terrain field of its Building object, which is what allows the two
    engines to be driven by the same wind.
    """
    assert U._ASHRAE_TERRAIN_PARAMETERS == {
        "flat_open":    (0.10, 210.0),
        "open_country": (0.14, 270.0),
        "suburban":     (0.22, 370.0),
        "city_centre":  (0.33, 460.0),
    }


@pytest.mark.parametrize("spelling,expected", [
    ("Ocean", "flat_open"), ("offshore", "flat_open"),
    ("Country", "open_country"), ("airport", "open_country"),
    ("Suburbs", "suburban"), ("Urban", "suburban"), ("suburban", "suburban"),
    ("City", "city_centre"), ("city-centre", "city_centre"),
])
def test_energyplus_terrain_spellings_resolve(spelling, expected):
    """An IDF and a building dictionary must be statable in the same words."""
    assert U._normalize_terrain_class(spelling) == expected


def test_unknown_terrain_names_the_four_choices():
    with pytest.raises(ValueError) as exc:
        U._normalize_terrain_class("windy")
    msg = str(exc.value)
    for cls in ("flat_open", "open_country", "suburban", "city_centre"):
        assert cls in msg


# --------------------------------------------------------------------------
# The primary regression test: the identity case
# --------------------------------------------------------------------------

def test_identity_case_is_exact():
    """
    A site declaring the station's own terrain at the station's own sensor
    height must return the station wind unchanged. If this drifts, every
    result the profile touches carries a silent offset.
    """
    f = U.local_wind_speed_factor("open_country", 10.0)
    assert f == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("terrain", ["flat_open", "open_country", "suburban", "city_centre"])
def test_identity_holds_for_any_station_terrain(terrain):
    """The identity is a property of the profile, not of one terrain class."""
    f = U.local_wind_speed_factor(
        terrain, 10.0, weather_station_terrain=terrain,
        weather_station_sensor_height_m=10.0)
    assert f == pytest.approx(1.0, abs=1e-12)


def test_as_measured_is_exactly_one():
    """The explicit opt-out returns the station wind untouched."""
    assert U.local_wind_speed_factor("as_measured", 6.75) == 1.0


# --------------------------------------------------------------------------
# The required input
# --------------------------------------------------------------------------

def test_terrain_class_has_no_silent_default():
    """
    A building that omits the terrain class must raise, not quietly behave as
    if the site were the weather station. That silent default is the defect.
    """
    with pytest.raises(ValueError) as exc:
        U._resolve_site_terrain_class({"building": {"height": 2.7}})
    msg = str(exc.value)
    for cls in ("flat_open", "open_country", "suburban", "city_centre"):
        assert cls in msg
    assert "as_measured" in msg   # the escape is named, so it is discoverable


def test_the_escape_is_explicit_and_works():
    off = {"site": {"wind_profile": False}}
    f, audit = U.resolve_local_wind_factor(off)
    assert f == 1.0 and audit["enabled"] is False

    named = {"site": {"terrain_class": "as_measured", "floor_level": 20}}
    f2, _ = U.resolve_local_wind_factor(named)
    assert f2 == 1.0


# --------------------------------------------------------------------------
# Height
# --------------------------------------------------------------------------

def test_height_from_floor_number_is_the_zone_mid_height():
    z, basis = U._resolve_surface_height_m(
        {"building": {"height": 2.7}, "site": {"floor_level": 3}})
    assert z == pytest.approx((3 - 0.5) * 2.7)
    assert "level 3" in basis


def test_single_storey_gives_the_mid_height_of_its_one_zone():
    z, _ = U._resolve_surface_height_m({"building": {"height": 2.7}})
    assert z == pytest.approx(1.35)


def test_explicit_surface_height_wins():
    z, basis = U._resolve_surface_height_m(
        {"building": {"height": 2.7}, "site": {"floor_level": 3, "surface_height_m": 42.0}})
    assert z == pytest.approx(42.0)
    assert "declared" in basis


def test_height_floor_is_a_guard_that_does_not_bind_on_habitable_storeys():
    """
    The floor exists because the power law sends u -> 0 as z -> 0. It must not
    reach up into any real building: the shallowest habitable case is a 2.4 m
    ceiling, mid-height 1.2 m.
    """
    assert U._SURFACE_HEIGHT_FLOOR_M < 1.2
    unclamped = U.local_wind_speed_factor("suburban", 1.2)
    assert unclamped == pytest.approx(
        U.local_wind_speed_factor("suburban", 1.2, height_floor_m=0.0))
    # ... but a zero or nonsense height is caught rather than returning 0.
    assert U.local_wind_speed_factor("suburban", 0.0) > 0.0
    assert U.local_wind_speed_factor("suburban", 0.0) == pytest.approx(
        U.local_wind_speed_factor("suburban", U._SURFACE_HEIGHT_FLOOR_M))


def test_factor_rises_with_height_and_falls_with_roughness():
    assert (U.local_wind_speed_factor("suburban", 2.0)
            < U.local_wind_speed_factor("suburban", 20.0)
            < U.local_wind_speed_factor("suburban", 100.0))
    z = 10.0
    assert (U.local_wind_speed_factor("city_centre", z)
            < U.local_wind_speed_factor("suburban", z)
            < U.local_wind_speed_factor("open_country", z)
            < U.local_wind_speed_factor("flat_open", z))


def test_the_correction_is_not_one_directional():
    """
    A building high enough projects into faster-moving air and sees MORE wind
    than the 10 m station, in every terrain class. If the implementation only
    ever reduced wind, the height term would not be being applied at all --
    which is the failure this asserts against.

    The crossing heights, from the ASHRAE coefficients: flat_open 2.1 m,
    open_country 10.0 m (the identity, by construction), suburban 45.4 m,
    city_centre 113.6 m. Note the last one: a level-20 city-centre apartment at
    z = 58 m is still BELOW 1.0 (0.80). The crossover for the roughest class is
    roughly level 38, not level 20.
    """
    crossings = {"flat_open": 2.08, "open_country": 10.0,
                 "suburban": 45.43, "city_centre": 113.64}
    for cls, z_cross in crossings.items():
        assert U.local_wind_speed_factor(cls, z_cross) == pytest.approx(1.0, abs=2e-3)
        assert U.local_wind_speed_factor(cls, z_cross * 2.0) > 1.0
        assert U.local_wind_speed_factor(cls, z_cross * 0.5) < 1.0
    # And the specific tall case, reported rather than assumed:
    assert U.local_wind_speed_factor("city_centre", 58.0) == pytest.approx(0.801, abs=1e-3)
    assert U.local_wind_speed_factor("suburban", 58.0) > 1.0
    assert U.local_wind_speed_factor("suburban", 6.75) < 1.0


# --------------------------------------------------------------------------
# The case study
# --------------------------------------------------------------------------

def test_apt305_declares_a_terrain_class_and_a_level():
    from apt305_building import build_bui
    site = build_bui()["site"]
    assert site["terrain_class"] == "suburban"
    assert site["floor_level"] == 3


def test_apt305_resolves_to_the_documented_height_and_factor():
    from apt305_building import build_bui
    f, audit = U.resolve_local_wind_factor(build_bui())
    assert audit["surface_height_m"] == pytest.approx(6.75)
    assert audit["exponent_a"] == 0.22
    assert audit["boundary_layer_delta_m"] == 370.0
    assert f == pytest.approx(0.6574, abs=5e-4)
    assert audit["height_floor_binds"] is False


def test_apt305_local_wind_crosses_the_pivot():
    """
    The substantive claim: the station mean sits above the 4 m/s pivot and the
    local mean sits below it, which is what reverses the sign of C2. Stated as
    a test so it cannot quietly stop being true.
    """
    from apt305_building import build_bui
    station_mean = 4.840331050228311    # Essendon TMYx 2011-2025, WS10m column
    f, _ = U.resolve_local_wind_factor(build_bui())
    assert station_mean > PIVOT_MS
    assert station_mean * f < PIVOT_MS


# --------------------------------------------------------------------------
# Scope: h_ce only
# --------------------------------------------------------------------------

def test_infiltration_does_not_consume_the_terrain_class():
    """
    The stack/wind modulation stays on the meteorological wind: its shelter is
    already carried by the LBL N = 20 divisor, and its normalisation is
    anchored to a station-referenced 4 m/s. Changing the terrain class must
    therefore leave the infiltration conductance untouched.
    """
    from apt305_building import build_bui
    from pybuildingenergy.source.check_input import sanitize_and_validate_BUI

    values = []
    for terrain in ("flat_open", "open_country", "suburban", "city_centre"):
        bui = build_bui()
        bui["site"]["terrain_class"] = terrain
        b, _ = sanitize_and_validate_BUI(bui, fix=True)
        values.append(U._infiltration_h_ve_inf_w_k(b, 20.0, 8.0, 6.0))
    assert values[0] == pytest.approx(values[1])
    assert values[0] == pytest.approx(values[2])
    assert values[0] == pytest.approx(values[3])
    assert values[0] > 0.0


def test_infiltration_reference_wind_is_the_station_four_metres_per_second():
    """The normalisation anchor is unchanged, and is a met-station speed."""
    assert U._INF_U_REF == 4.0
    assert U._INF_DT_REF == 10.0
    assert U._LBL_N_DIVISOR == 20.0
