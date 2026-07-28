"""
Step 4 unit tests — hemisphere-aware coldest month.

``coldest_month`` sets the phase of every ISO 13370 ground sinusoid: the
internal-temperature estimate and the two periodic ground heat-flow terms. It
was hardcoded to January, six months out of phase for any southern-hemisphere
site — the model put peak ground temperature in July for Melbourne.

``Temp_calculation_of_ground``'s own docstring already specified the correct
behaviour ("the default values: 1 for northern hemisphere or 7 in southern
hemisphere are used"). Only the code disagreed.

Self-contained. The phase check on a real annual ground-temperature profile
lives with the harness, where the EPW is.
"""

from __future__ import annotations

import pytest

from pybuildingenergy.source.utils import (
    COLDEST_MONTH_NORTHERN,
    COLDEST_MONTH_SOUTHERN,
    _resolve_coldest_month,
)


def _bui(latitude=None, coldest_month=None):
    building = {}
    if latitude is not None:
        building["latitude"] = latitude
    params = {}
    if coldest_month is not None:
        params["coldest_month"] = coldest_month
    return {"building": building, "building_parameters": params}


@pytest.mark.parametrize("lat", [-37.8, -0.001, -90.0, -12.5])
def test_southern_latitudes_get_july(lat):
    assert _resolve_coldest_month(_bui(latitude=lat)) == COLDEST_MONTH_SOUTHERN == 7


@pytest.mark.parametrize("lat", [45.5, 0.0, 0.001, 89.9])
def test_northern_latitudes_get_january(lat):
    """The equator itself resolves north — it has to go somewhere, and 0.0 is
    not a southern latitude."""
    assert _resolve_coldest_month(_bui(latitude=lat)) == COLDEST_MONTH_NORTHERN == 1


def test_melbourne_resolves_to_july():
    """apt 305's own latitude, which is what this fix exists for."""
    assert _resolve_coldest_month(_bui(latitude=-37.800)) == 7


@pytest.mark.parametrize("month", [1, 6, 7, 12])
def test_explicit_coldest_month_wins(month):
    """A site with a known local minimum can override the hemisphere default."""
    assert _resolve_coldest_month(_bui(latitude=-37.8, coldest_month=month)) == month


@pytest.mark.parametrize("bad", [0, 13, -1, "July", None, float("nan")])
def test_unusable_explicit_value_falls_back_to_the_hemisphere(bad):
    assert _resolve_coldest_month(_bui(latitude=-37.8, coldest_month=bad)) == 7


def test_float_month_is_accepted_and_truncated():
    assert _resolve_coldest_month(_bui(latitude=-37.8, coldest_month=7.0)) == 7


@pytest.mark.parametrize("bad", [None, "south", float("nan"), float("inf")])
def test_missing_or_unusable_latitude_keeps_the_previous_behaviour(bad):
    """
    Deliberately conservative: silently flipping a building's ground phase on
    the strength of an absent input would be worse than leaving it alone, so a
    missing latitude keeps the historical January.
    """
    assert _resolve_coldest_month(_bui(latitude=bad)) == COLDEST_MONTH_NORTHERN


def test_non_dict_input_does_not_raise():
    assert _resolve_coldest_month(None) == COLDEST_MONTH_NORTHERN
    assert _resolve_coldest_month({}) == COLDEST_MONTH_NORTHERN


def test_resolution_is_idempotent():
    """
    Temp_calculation_of_ground writes the resolved value back into the
    dictionary, so a second call reads its own output. That must not drift.
    """
    bui = _bui(latitude=-37.8)
    first = _resolve_coldest_month(bui)
    bui["building_parameters"]["coldest_month"] = first
    assert _resolve_coldest_month(bui) == first == 7
