"""
Unit tests for the wind-dependent surface heat transfer coefficients added in
change 2 (extension of change 1 from windows to all air-exposed surfaces).

Run with:
    python -m pytest tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pybuildingenergy" / "src"))

from pybuildingenergy.source import utils as U  # noqa: E402

OPAQUE = {"type": "opaque", "ISO52016_type_string": "OP"}


def _h(model, wind, surface=None, t_surf=10.0, t_air=10.0, fallback=20.0):
    return U._dynamic_external_convection_h(
        surface=surface if surface is not None else OPAQUE,
        T_surf_C=t_surf,
        T_air_C=t_air,
        u_wind_ms=wind,
        model=model,
        h_min=2.0,
        fallback_h_ce=fallback,
    )


# --------------------------------------------------------------------------
# The anchor: the ISO constant is 4*v + 4 at the standard 4 m/s
# --------------------------------------------------------------------------

def test_iso_constant_is_recovered_at_standard_wind_speed():
    """
    EN ISO 13789 section 9.5 gives h_ce = 20 W/(m2 K) for opaque external
    surfaces. That number is 4*v + 4 evaluated at the standard's frozen
    v = 4 m/s. If this identity ever breaks, the change stops being a
    refinement and starts being an offset.
    """
    assert _h("simplecombined", 4.0) == pytest.approx(20.0)
    assert U._TABLE25_SURFACE_HEAT_TRANSFER_DEFAULTS.external_outdoor_air.convective == pytest.approx(20.0)


def test_below_standard_wind_gives_lower_h_ce():
    """Calm air means a thicker boundary layer, so less convective coupling."""
    assert _h("simplecombined", 0.0) < _h("simplecombined", 2.0) < 20.0


def test_above_standard_wind_gives_higher_h_ce():
    assert _h("simplecombined", 8.0) > 20.0


def test_h_min_floor_is_enforced():
    """The floor stops a dead-calm hour producing a near-zero coupling."""
    assert _h("simplecombined", 0.0) >= 2.0


# --------------------------------------------------------------------------
# Model selection
# --------------------------------------------------------------------------

@pytest.mark.parametrize("model", ["doe2", "mowitt", "blast", "simplecombined"])
def test_all_dynamic_models_respond_to_wind(model):
    calm, windy = _h(model, 0.5), _h(model, 12.0)
    assert windy > calm, f"{model} did not increase with wind"


@pytest.mark.parametrize("model", ["doe2", "mowitt", "blast", "simplecombined"])
def test_all_dynamic_models_return_finite_positive(model):
    for wind in (0.0, 1.0, 4.0, 10.0, 30.0):
        h = _h(model, wind)
        assert h > 0.0 and h == h and h < 1e4


def test_table_model_ignores_wind_entirely():
    assert _h("table", 0.0) == pytest.approx(20.0)
    assert _h("table", 25.0) == pytest.approx(20.0)


def test_unknown_model_rejected():
    with pytest.raises(ValueError):
        U._normalize_external_convection_model("hurricane")


# --------------------------------------------------------------------------
# Option resolution for change 2
# --------------------------------------------------------------------------

def test_dynamic_surface_heat_transfer_defaults_on():
    assert U._resolve_dynamic_surface_heat_transfer({}) is True


def test_dynamic_surface_heat_transfer_can_be_switched_off():
    """Switching this off must recover change-1-only behaviour."""
    assert U._resolve_dynamic_surface_heat_transfer({}, override=False) is False
    assert U._resolve_dynamic_surface_heat_transfer(
        {"building_parameters": {"dynamic_surface_heat_transfer": False}}
    ) is False
    assert U._resolve_dynamic_surface_heat_transfer(
        {"building_parameters": {"dynamic_surface_heat_transfer": "off"}}
    ) is False


def test_opaque_model_defaults_to_simplecombined():
    assert U._resolve_opaque_convection_model({}) == "simplecombined"


def test_explicit_opaque_model_wins_over_default():
    """A configured value must not be silently overridden by the new default."""
    bui = {"building_parameters": {"external_convection_model": "doe2"}}
    assert U._resolve_opaque_convection_model(bui) == "doe2"
    assert U._resolve_opaque_convection_model({}, override="mowitt") == "mowitt"
    # And 'table' must remain selectable, to pin ISO behaviour on opaque only.
    assert U._resolve_opaque_convection_model(
        {"building_parameters": {"external_convection_model": "table"}}
    ) == "table"


def test_opaque_model_reads_simulation_options_first():
    """
    simulation_options is nested inside building_parameters (see
    _get_simulation_options) and takes precedence over the flat key.
    """
    bui = {
        "building_parameters": {
            "simulation_options": {"external_convection_model": "blast"},
            "external_convection_model": "doe2",
        },
    }
    assert U._resolve_opaque_convection_model(bui) == "blast"


def test_window_and_opaque_models_are_independent():
    """
    The two selectors must not collide, otherwise change 1 and change 2 could
    not be measured separately.
    """
    bui = {
        "building_parameters": {
            "window_convection_model": "mowitt",
            "external_convection_model": "table",
        }
    }
    assert U._resolve_window_convection_model(bui) == "mowitt"
    assert U._resolve_opaque_convection_model(bui) == "table"
