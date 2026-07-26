"""
Unit tests for the dynamic window properties added in change 1.

These sit outside the vendored tree so the upstream test suite stays untouched.

Run with:
    python -m pytest tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pybuildingenergy" / "src"))

from pybuildingenergy.source import utils as U  # noqa: E402

WINDOW = {"type": "transparent"}


# --------------------------------------------------------------------------
# Karlsson-Roos angular factor
# --------------------------------------------------------------------------

@pytest.mark.parametrize("panes", [1, 2, 3])
def test_angular_factor_endpoints(panes):
    """F(0) = 1 exactly, F(90) = 0 exactly (guaranteed by a + b + c = 1)."""
    coeffs = U._WINDOW_ANGULAR_COEFFS_DEFAULT[panes]
    assert U.karlsson_roos_direct_factor(0.0, coeffs) == pytest.approx(1.0, abs=1e-12)
    assert U.karlsson_roos_direct_factor(90.0, coeffs) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("panes", [1, 2, 3])
def test_angular_factor_is_monotone_decreasing(panes):
    """Transmittance must fall away as the beam moves off the normal."""
    coeffs = U._WINDOW_ANGULAR_COEFFS_DEFAULT[panes]
    f = U.karlsson_roos_direct_factor(np.linspace(0.0, 90.0, 91), coeffs)
    assert np.all(np.diff(f) <= 1e-12)


@pytest.mark.parametrize("panes", [1, 2, 3])
def test_angular_factor_bounded(panes):
    coeffs = U._WINDOW_ANGULAR_COEFFS_DEFAULT[panes]
    f = U.karlsson_roos_direct_factor(np.linspace(-10.0, 190.0, 401), coeffs)
    assert np.all(f >= 0.0) and np.all(f <= 1.0)


def test_more_panes_reject_more_at_steep_incidence():
    """Each extra glass-air interface adds reflection loss off-normal."""
    f = [
        float(U.karlsson_roos_direct_factor(70.0, U._WINDOW_ANGULAR_COEFFS_DEFAULT[p]))
        for p in (1, 2, 3)
    ]
    assert f[0] > f[1] > f[2]


def test_defaults_reproduce_fresnel_reference():
    """
    The shipped coefficients are a fit to a Fresnel + Beer-Lambert curve. Guard
    the fit quality so a future edit to the coefficients cannot silently drift
    away from the physics they were derived from.
    """
    n_glass, thickness, k_ext = 1.52, 0.004, 26.0
    theta = np.linspace(0.0, 90.0, 181)
    rad = np.radians(theta)
    theta_r = np.arcsin(np.clip(np.sin(rad) / n_glass, -1.0, 1.0))
    cos_i, cos_r = np.cos(rad), np.cos(theta_r)

    with np.errstate(divide="ignore", invalid="ignore"):
        r_s = ((cos_i - n_glass * cos_r) / (cos_i + n_glass * cos_r)) ** 2
        r_p = ((cos_r - n_glass * cos_i) / (cos_r + n_glass * cos_i)) ** 2
    r_s = np.where(cos_i <= 1e-12, 1.0, r_s)
    r_p = np.where(cos_i <= 1e-12, 1.0, r_p)
    tau_a = np.exp(-k_ext * thickness / np.maximum(cos_r, 1e-12))

    def slab(r):
        denom = np.maximum(1.0 - (r ** 2) * (tau_a ** 2), 1e-12)
        tau = ((1.0 - r) ** 2) * tau_a / denom
        return tau, r * (1.0 + tau * tau_a)

    tau_s, rho_s = slab(r_s)
    tau_p, rho_p = slab(r_p)
    tau1, rho1 = 0.5 * (tau_s + tau_p), 0.5 * (rho_s + rho_p)

    for panes in (1, 2, 3):
        tau, rho = tau1.copy(), rho1.copy()
        for _ in range(panes - 1):
            denom = np.maximum(1.0 - rho * rho1, 1e-12)
            tau, rho = tau * tau1 / denom, rho + (tau ** 2) * rho1 / denom
        reference = tau / tau[0]
        fitted = U.karlsson_roos_direct_factor(theta, U._WINDOW_ANGULAR_COEFFS_DEFAULT[panes])
        assert np.max(np.abs(fitted - reference)) < 0.01, f"{panes}-pane fit drifted"


def test_diffuse_factor_is_hemispherical_average_of_direct_curve():
    """F_W,diff must be the cosine-weighted hemispherical mean of F_W,dir."""
    theta = np.linspace(0.0, 90.0, 4001)
    rad = np.radians(theta)
    for panes in (1, 2, 3):
        f = U.karlsson_roos_direct_factor(theta, U._WINDOW_ANGULAR_COEFFS_DEFAULT[panes])
        expected = 2.0 * np.trapezoid(f * np.cos(rad) * np.sin(rad), rad)
        assert U._WINDOW_ANGULAR_DIFFUSE_DEFAULT[panes] == pytest.approx(expected, abs=1e-4)


def test_single_pane_diffuse_factor_matches_iso_constant():
    """
    Sanity anchor: ISO 13790 / ISO 52016 use a constant 0.9 for the
    non-scattered-radiation correction. The single-pane hemispherical average
    landing on ~0.907 is an independent check that the curve is calibrated.
    """
    assert U._WINDOW_ANGULAR_DIFFUSE_DEFAULT[1] == pytest.approx(0.9, abs=0.01)


# --------------------------------------------------------------------------
# Combined F_W weighting
# --------------------------------------------------------------------------

def test_fw_pure_diffuse_equals_diffuse_factor():
    assert U.window_solar_correction_factor(WINDOW, 45.0, 100.0, 0.0, 1.0) == pytest.approx(
        U._WINDOW_ANGULAR_DIFFUSE_DEFAULT[2]
    )


def test_fw_pure_normal_direct_is_unity():
    assert U.window_solar_correction_factor(WINDOW, 0.0, 0.0, 100.0, 1.0) == pytest.approx(1.0)


def test_fw_fully_shaded_direct_collapses_onto_diffuse():
    """
    A beam that obstacles block never reaches the glazing, so it must carry no
    weight in the average -- otherwise the shaded direct term would drag F_W
    towards its steep-angle value for radiation that is not actually admitted.
    """
    got = U.window_solar_correction_factor(WINDOW, 80.0, 100.0, 900.0, 0.0)
    assert got == pytest.approx(U._WINDOW_ANGULAR_DIFFUSE_DEFAULT[2])


def test_fw_is_irradiance_weighted():
    theta = 60.0
    f_dir = float(U.karlsson_roos_direct_factor(theta, U._WINDOW_ANGULAR_COEFFS_DEFAULT[2]))
    f_dif = U._WINDOW_ANGULAR_DIFFUSE_DEFAULT[2]
    got = U.window_solar_correction_factor(WINDOW, theta, 300.0, 100.0, 1.0)
    expected = (f_dif * 300.0 + f_dir * 100.0) / 400.0
    assert got == pytest.approx(expected)


def test_fw_zero_irradiance_stays_bounded():
    got = U.window_solar_correction_factor(WINDOW, 90.0, 0.0, 0.0, 1.0)
    assert 0.0 <= got <= 1.0


def test_fw_model_switches():
    assert U.window_solar_correction_factor(WINDOW, 80.0, 0.0, 100.0, 1.0, model="none") == 1.0
    assert U.window_solar_correction_factor(WINDOW, 80.0, 0.0, 100.0, 1.0, model="constant") == 0.9


def test_fw_never_exceeds_unity():
    """F_W is a reduction factor; it must never admit more than the rated g."""
    rng = np.random.default_rng(0)
    for _ in range(500):
        got = U.window_solar_correction_factor(
            WINDOW,
            float(rng.uniform(0.0, 180.0)),
            float(rng.uniform(0.0, 900.0)),
            float(rng.uniform(0.0, 900.0)),
            float(rng.uniform(0.0, 1.0)),
        )
        assert 0.0 <= got <= 1.0


def test_per_surface_coefficient_override():
    """Published coefficients for a specific product must win over defaults."""
    surf = {"type": "transparent", "window_angular_coefficients": (0.0, 0.0, 1.0, 4.0, 2.0, 1.0)}
    # With a=b=0, c=1, gamma=1 the curve is the straight line 1 - theta/90.
    assert U.karlsson_roos_direct_factor(45.0, U._window_angular_coefficients(surf)) == pytest.approx(0.5)
    # And the diffuse factor must be re-integrated from the override, not read
    # off the table. For F = 1 - 2u/pi the cosine-weighted hemispherical mean
    #     2 * int_0^{pi/2} (1 - 2u/pi) cos(u) sin(u) du = 1 - 1/2 = 1/2
    # (note this is the cosine-weighted mean, not the plain average over angle).
    assert U._window_angular_diffuse_factor(surf) == pytest.approx(0.5, abs=1e-3)


def test_glazing_panes_hint_selects_coefficient_set():
    assert U._window_angular_coefficients({"type": "transparent", "glazing_panes": 3}) == (
        U._WINDOW_ANGULAR_COEFFS_DEFAULT[3]
    )
    # Out-of-range values are clamped rather than raising.
    assert U._window_angular_coefficients({"type": "transparent", "glazing_panes": 9}) == (
        U._WINDOW_ANGULAR_COEFFS_DEFAULT[3]
    )


# --------------------------------------------------------------------------
# Wind-dependent external film
# --------------------------------------------------------------------------

def test_simplecombined_reduces_to_iso_constant_at_4ms():
    """
    The whole change hinges on this: h_ce = 4 + 4v must return exactly the
    ISO 13789 constant of 20 W/(m2 K) at the 4 m/s the standard freezes in,
    so a run forced to 4 m/s reproduces baseline results.
    """
    h = U._dynamic_external_convection_h(
        surface={"type": "transparent"},
        T_surf_C=10.0,
        T_air_C=10.0,
        u_wind_ms=4.0,
        model="simplecombined",
        h_min=2.0,
        fallback_h_ce=20.0,
    )
    assert h == pytest.approx(20.0)


@pytest.mark.parametrize("wind,expected", [(0.0, 4.0), (2.0, 12.0), (4.0, 20.0), (10.0, 44.0)])
def test_simplecombined_is_linear_in_wind(wind, expected):
    h = U._dynamic_external_convection_h(
        surface={"type": "transparent"},
        T_surf_C=10.0,
        T_air_C=10.0,
        u_wind_ms=wind,
        model="simplecombined",
        h_min=2.0,
        fallback_h_ce=20.0,
    )
    assert h == pytest.approx(max(2.0, expected))


def test_table_model_is_inert():
    """Selecting 'table' must return the constant untouched."""
    h = U._dynamic_external_convection_h(
        surface={"type": "transparent"},
        T_surf_C=-5.0,
        T_air_C=25.0,
        u_wind_ms=17.0,
        model="table",
        h_min=2.0,
        fallback_h_ce=20.0,
    )
    assert h == pytest.approx(20.0)


# --------------------------------------------------------------------------
# Option resolution
# --------------------------------------------------------------------------

def test_dynamic_window_properties_defaults_on():
    assert U._resolve_dynamic_window_properties({}) is True


def test_dynamic_window_properties_can_be_switched_off():
    bui = {"building_parameters": {"dynamic_window_properties": False}}
    assert U._resolve_dynamic_window_properties(bui) is False
    assert U._resolve_dynamic_window_properties({}, override=False) is False
    # Strings from config files must work too.
    assert U._resolve_dynamic_window_properties(
        {"building_parameters": {"dynamic_window_properties": "false"}}
    ) is False


def test_window_convection_model_defaults_to_simplecombined():
    assert U._resolve_window_convection_model({}) == "simplecombined"


def test_window_angular_model_aliases():
    assert U._resolve_window_angular_model({}) == "karlsson_roos"
    assert U._resolve_window_angular_model({}, override="off") == "none"
    assert U._resolve_window_angular_model({}, override="ISO") == "constant"
    with pytest.raises(ValueError):
        U._resolve_window_angular_model({}, override="not_a_model")
