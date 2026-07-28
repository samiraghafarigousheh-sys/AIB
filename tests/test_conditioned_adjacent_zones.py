"""
Step 2 unit tests — conditioned adjacent zones.

ISO 52016-1 routes every adjacent zone through the ISO 13789 unconditioned
buffer model, which with ``b_ztu`` 0.7-0.95 makes the neighbour track *outdoor*
air. That is right for an attic or a garage and wrong for a party wall shared
with another occupied, conditioned apartment. A zone marked ``conditioned: True``
is now held at its declared ``setpoint`` instead.

Self-contained: no dependency on ``examples/``. The end-to-end assertion that
``theta_ztu`` equals the declared setpoint at every timestep of a real annual
run lives with the harness, where the apt 305 dictionary lives.
"""

from __future__ import annotations

import numpy as np
import pytest

from pybuildingenergy.source.utils import (
    DEFAULT_THETA_ZTU_INIT_C,
    _adjacent_zone_conditioning,
    _init_theta_ztu,
    _theta_ztu_unconditioned,
)
from pybuildingenergy.source.check_input import sanitize_and_validate_BUI


def _bui(zones):
    return {"adjacent_zones": zones}


# ---------------------------------------------------------------------------
# Reading the new fields
# ---------------------------------------------------------------------------

def test_absent_fields_default_to_unconditioned():
    """Existing dictionaries must be unaffected."""
    assert _adjacent_zone_conditioning(_bui([{}, {"name": "attic"}])) == [
        (False, None), (False, None)]


def test_conditioned_and_setpoint_are_read_in_dictionary_order():
    got = _adjacent_zone_conditioning(_bui([
        {"conditioned": True, "setpoint": 20.0},
        {"conditioned": False, "setpoint": 99.0},
        {"conditioned": True},
    ]))
    assert got == [(True, 20.0), (False, 99.0), (True, None)]


@pytest.mark.parametrize("bad", ["", "warm", None, float("nan"), float("inf")])
def test_unusable_setpoint_falls_back_to_none(bad):
    """A setpoint that cannot become a finite float must not reach the solver."""
    got = _adjacent_zone_conditioning(_bui([{"conditioned": True, "setpoint": bad}]))
    assert got == [(True, None)]


def test_integer_setpoint_is_accepted():
    assert _adjacent_zone_conditioning(_bui([{"conditioned": True, "setpoint": 20}])) \
        == [(True, 20.0)]


def test_non_dict_and_missing_zone_lists_are_tolerated():
    assert _adjacent_zone_conditioning(_bui([None, 7])) == [(False, None), (False, None)]
    assert _adjacent_zone_conditioning({}) == []
    assert _adjacent_zone_conditioning(None) == []


# ---------------------------------------------------------------------------
# Seeding theta_ztu
# ---------------------------------------------------------------------------

def test_single_unconditioned_zone_keeps_the_historical_cold_start():
    t = _init_theta_ztu(_bui([{}]), 1, 8)
    assert t.shape == (8,)
    assert t[0] == pytest.approx(DEFAULT_THETA_ZTU_INIT_C)


def test_single_conditioned_zone_starts_at_its_setpoint():
    t = _init_theta_ztu(_bui([{"conditioned": True, "setpoint": 20.0}]), 1, 8)
    assert t[0] == pytest.approx(20.0)


def test_multi_zone_seed_is_per_zone():
    """
    Only the conditioned columns move; the rest keep the 15 C cold start, so a
    mixed building (three apartments + an attic) is seeded correctly.
    """
    zones = [{"conditioned": True, "setpoint": 20.0},
             {"conditioned": True, "setpoint": 22.5},
             {"conditioned": False},
             {}]
    t = _init_theta_ztu(_bui(zones), 4, 6)
    assert t.shape == (6, 4)
    assert list(t[0]) == pytest.approx([20.0, 22.5, DEFAULT_THETA_ZTU_INIT_C,
                                        DEFAULT_THETA_ZTU_INIT_C])
    assert list(t[1]) == pytest.approx([20.0, 22.5, DEFAULT_THETA_ZTU_INIT_C,
                                        DEFAULT_THETA_ZTU_INIT_C])


def test_conditioned_without_setpoint_keeps_the_default_seed():
    """
    Seeding cannot use "this zone's previous operative temperature" -- there
    isn't one yet at t=0 -- so it falls back to the historical default and the
    solver takes over from t=1.
    """
    t = _init_theta_ztu(_bui([{"conditioned": True}]), 1, 4)
    assert t[0] == pytest.approx(DEFAULT_THETA_ZTU_INIT_C)


def test_more_zones_than_entries_does_not_raise():
    t = _init_theta_ztu(_bui([{"conditioned": True, "setpoint": 20.0}]), 3, 4)
    assert t.shape == (4, 3)
    assert t[0, 0] == pytest.approx(20.0)
    assert t[0, 2] == pytest.approx(DEFAULT_THETA_ZTU_INIT_C)


# ---------------------------------------------------------------------------
# The unconditioned formula must be unchanged
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("theta_int,t_ext,b,phi,H", [
    (21.0, 5.0, 0.733, 0.0, 50.0),
    (21.0, 5.0, 0.926, 120.0, 40.0),
    (19.0, 30.0, 0.867, 60.0, 25.0),
    (21.0, -5.0, 0.90, 500.0, 10.0),
])
def test_unconditioned_formula_matches_the_original_expression(theta_int, t_ext, b, phi, H):
    """Extracted verbatim; assert it against the inline expression it replaced."""
    c_max = 1.0
    expected_raw = theta_int - b * (theta_int - t_ext) + (phi / H)
    expected = min(t_ext + c_max * (theta_int - t_ext), expected_raw)
    assert _theta_ztu_unconditioned(theta_int, t_ext, b, phi, H, c_max) \
        == pytest.approx(expected, rel=1e-15)


def test_table_b16_cap_still_binds():
    """A large gain must not push the buffer above the cap."""
    got = _theta_ztu_unconditioned(21.0, 5.0, 0.9, 1e6, 1.0, 1.0)
    assert got == pytest.approx(5.0 + 1.0 * (21.0 - 5.0))


def test_zero_conductance_does_not_divide_by_zero():
    got = _theta_ztu_unconditioned(21.0, 5.0, 0.733, 100.0, 0.0)
    assert np.isfinite(got)


# ---------------------------------------------------------------------------
# check_input validation
# ---------------------------------------------------------------------------

def _validate(zone_extra):
    bui = {
        "building": {"net_floor_area": 20.0, "exposed_perimeter": 0.0, "height": 2.7},
        "building_surface": [],
        "adjacent_zones": [dict({"name": "n", "volume": 50.0}, **zone_extra)],
    }
    _clean, issues = sanitize_and_validate_BUI(bui, fix=True)
    return [i for i in issues if "adjacent_zones[0]" in i["path"]]


def test_valid_conditioned_zone_raises_nothing():
    assert _validate({"conditioned": True, "setpoint": 20.0}) == []


def test_non_bool_conditioned_is_coerced_with_a_warning():
    issues = _validate({"conditioned": 1, "setpoint": 20.0})
    assert any(i["level"] == "WARN" and i["path"].endswith(".conditioned")
               and i["fix_applied"] for i in issues), issues


def test_non_numeric_setpoint_is_an_error():
    issues = _validate({"conditioned": True, "setpoint": "warm"})
    assert any(i["level"] == "ERROR" and i["path"].endswith(".setpoint") for i in issues), issues


@pytest.mark.parametrize("sp", [-10.0, 60.0])
def test_implausible_setpoint_warns(sp):
    issues = _validate({"conditioned": True, "setpoint": sp})
    assert any(i["level"] == "WARN" and i["path"].endswith(".setpoint") for i in issues), issues


def test_conditioned_without_setpoint_warns():
    """'Conditioned to what?' is the question a reviewer should be asking."""
    issues = _validate({"conditioned": True})
    assert any(i["level"] == "WARN" and i["path"].endswith(".setpoint") for i in issues), issues


def test_unconditioned_zone_with_no_new_fields_is_silent():
    assert _validate({}) == []
