"""
Step 3 unit tests — ground-contact area must not be inferred from thin air.

``_ground_contact_area()`` used to fall back to ``building.net_floor_area``
whenever no surface was tagged, so every unclassified building got a
full-footprint slab-on-ground and a non-zero ground flux every hour of the year.
Absence of a ground surface now means **no ground contact**.

Self-contained: no weather, no ``examples/``. The ISO 13370 hand-calculation
check and the apt 305 end-to-end assertion live with the harness, where the EPW
and the building dictionary are.
"""

from __future__ import annotations

import numpy as np
import pytest

from pybuildingenergy.source.utils import (
    _ground_contact_area,
    _ground_conductance_w_per_k,
    temp_ground,
)
from pybuildingenergy.source.check_input import sanitize_and_validate_BUI


def _surf(name, area, **kw):
    s = {"name": name, "type": "opaque", "area": area, "sky_view_factor": 0.5,
         "orientation": {"azimuth": 270.0, "tilt": 90.0}, "name_adj_zone": None}
    s.update(kw)
    return s


def _bui(surfaces, net_floor_area=100.0, **building):
    b = {"net_floor_area": net_floor_area, "exposed_perimeter": 40.0, "height": 2.7}
    b.update(building)
    return {"building": b, "building_surface": surfaces}


# ---------------------------------------------------------------------------
# The fix: no ground tag means no ground
# ---------------------------------------------------------------------------

def test_untagged_building_has_zero_ground_contact():
    """
    The headline change. This used to return net_floor_area (100.0), giving a
    third-floor apartment a slab the size of its floor plate.
    """
    bui = _bui([_surf("wall", 50.0), _surf("window", 5.0, type="transparent")])
    assert _ground_contact_area(bui) == 0.0


def test_no_exception_when_nothing_is_tagged():
    """It used to raise when net_floor_area was also missing. 0.0 is the answer."""
    assert _ground_contact_area({"building": {}, "building_surface": []}) == 0.0
    assert _ground_contact_area({}) == 0.0


def test_net_floor_area_is_never_consulted():
    """Even a huge floor area must not manufacture ground contact."""
    bui = _bui([_surf("wall", 50.0)], net_floor_area=10_000.0)
    assert _ground_contact_area(bui) == 0.0


# ---------------------------------------------------------------------------
# What still counts as ground
# ---------------------------------------------------------------------------

def test_explicit_boundary_ground_is_summed():
    bui = _bui([_surf("wall", 50.0),
                _surf("slab_a", 30.0, boundary="GROUND"),
                _surf("slab_b", 26.25, boundary="ground")])
    assert _ground_contact_area(bui) == pytest.approx(56.25)


def test_iso_type_gr_is_summed():
    bui = _bui([_surf("wall", 50.0), _surf("slab", 42.0, ISO52016_type_string="GR")])
    assert _ground_contact_area(bui) == pytest.approx(42.0)


@pytest.mark.parametrize("area", [0.0, -5.0, float("nan"), float("inf"), "big"])
def test_unusable_areas_are_skipped(area):
    bui = _bui([_surf("slab", area, boundary="GROUND"), _surf("ok", 12.0, boundary="GROUND")])
    assert _ground_contact_area(bui) == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# Legacy sky-view/tilt inference: opt-in only
# ---------------------------------------------------------------------------

def _legacy_floor(**kw):
    return _surf("floor", 56.25, sky_view_factor=0.0,
                 orientation={"azimuth": 0.0, "tilt": 0.0}, **kw)


def test_legacy_inference_is_off_by_default():
    assert _ground_contact_area(_bui([_legacy_floor()])) == 0.0


def test_legacy_inference_can_be_opted_into():
    bui = _bui([_legacy_floor()], legacy_ground_inference=True)
    assert _ground_contact_area(bui) == pytest.approx(56.25)


@pytest.mark.parametrize("tilt", [0.0, 180.0, 175.0, None])
def test_legacy_inference_accepts_horizontal_under_either_convention(tilt):
    """
    This codebase documents 0 = horizontal, 90 = vertical. The old threshold
    (`tilt > 170`) assumed 0 = up / 180 = down, so it matched nothing here and
    fell straight through to the net-floor-area fallback.
    """
    surf = _surf("floor", 20.0, sky_view_factor=0.0,
                 orientation={"azimuth": 0.0, "tilt": tilt})
    assert _ground_contact_area(_bui([surf], legacy_ground_inference=True)) \
        == pytest.approx(20.0)


def test_legacy_inference_rejects_a_slab_over_another_zone():
    """
    A floor over another zone is a party slab, never ground. Under the
    0 = horizontal convention tilt cannot tell a floor from a ceiling, so this
    is the condition that does the disambiguating.
    """
    bui = _bui([_legacy_floor(name_adj_zone="apt_below")], legacy_ground_inference=True)
    assert _ground_contact_area(bui) == 0.0


def test_legacy_inference_rejects_a_sky_exposed_surface():
    surf = _surf("roof", 20.0, sky_view_factor=1.0,
                 orientation={"azimuth": 0.0, "tilt": 0.0})
    assert _ground_contact_area(_bui([surf], legacy_ground_inference=True)) == 0.0


def test_explicit_tag_wins_over_legacy_inference():
    bui = _bui([_surf("slab", 10.0, boundary="GROUND"), _legacy_floor()],
               legacy_ground_inference=True)
    assert _ground_contact_area(bui) == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Downstream: zero area must produce zero coupling, not a NaN
# ---------------------------------------------------------------------------

def test_zero_area_gives_zero_conductance():
    tg = temp_ground(R_gr_ve=0.5769, Theta_gr_ve=np.full(12, 15.0),
                     thermal_bridge_heat=2.0, ground_contact_area=0.0)
    assert _ground_conductance_w_per_k(0.0, tg) == 0.0


def test_nonzero_area_gives_the_expected_conductance():
    tg = temp_ground(R_gr_ve=0.5769, Theta_gr_ve=np.full(12, 15.0),
                     thermal_bridge_heat=2.0, ground_contact_area=56.25)
    assert _ground_conductance_w_per_k(56.25, tg) == pytest.approx(56.25 / 0.5769)


# ---------------------------------------------------------------------------
# check_input coherence warning
# ---------------------------------------------------------------------------

def _issues(building_extra, surfaces):
    """
    Only the ground-coherence warning. Filtering by path alone would also catch
    the pre-existing "exposed_perimeter was 0; set to 1.0" fixer message, which
    shares the path and fires on exactly the case this check must stay quiet on.
    """
    bui = {"building": dict({"net_floor_area": 100.0, "height": 2.7}, **building_extra),
           "building_surface": surfaces, "adjacent_zones": []}
    _clean, issues = sanitize_and_validate_BUI(bui, fix=True)
    return [i for i in issues
            if i["path"] == "building.exposed_perimeter" and 'boundary="GROUND"' in i["msg"]]


def test_perimeter_without_ground_tag_warns():
    """Self-contradictory: a slab edge implies a slab."""
    got = _issues({"exposed_perimeter": 40.0}, [_surf("wall", 50.0)])
    assert len(got) == 1 and got[0]["level"] == "WARN", got


def test_zero_perimeter_without_ground_tag_is_silent():
    """
    An intermediate-floor apartment declares exposed_perimeter = 0 and has no
    ground. That is coherent, and must not warn -- note the check reads the
    ORIGINAL value, because the building-level fixer rewrites 0 to 1.0.
    """
    assert _issues({"exposed_perimeter": 0.0}, [_surf("wall", 50.0)]) == []


def test_perimeter_with_ground_tag_is_silent():
    assert _issues({"exposed_perimeter": 40.0},
                   [_surf("wall", 50.0), _surf("slab", 56.25, boundary="GROUND")]) == []


def test_legacy_opt_in_suppresses_the_warning():
    got = _issues({"exposed_perimeter": 40.0, "legacy_ground_inference": True},
                  [_legacy_floor()])
    assert got == [], got
