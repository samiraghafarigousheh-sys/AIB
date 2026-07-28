"""
Step 1 regression tests — internal gains must not scale with neighbour count.

WHAT WAS WRONG
--------------
``VentilationInternalGains.internal_gains()`` used to end with::

    if unconditioned_zones_nearby:
        Phi_int_dir_z_t = q_int_total * a_use
        for zones in range(list_adj_zones):
            Phi_int_z_t += Phi_int_dir_z_t + (1-b_ztu)*Fztc_ztu_m*Phi_int_dir_z_t

``q_int_total`` there is built from *this* zone's ``building_type_class`` and
``a_use``, so the loop transferred nothing from the neighbour — it multiplied the
zone's own gain by ``1 + n*(1 + (1-b_ztu)*F_ztc_ztu_m)``. For apt 305 (5
neighbours, trailing ``b_ztu = 0.733``) that is **7.33×**.

The neighbour's real contribution is modelled elsewhere and exactly once, as
``phi_gn_dir_ztu`` inside the ``theta_ztu`` buffer temperature in ``utils.py``.

These tests are deliberately self-contained: they build their own dictionaries
and import nothing from ``examples/``, so they validate this branch on its own.
The end-to-end counterpart (apt 305 run with ``number_adj_zone`` swept over
0/1/5) lives with the comparison harness, where the apt 305 dictionary lives.
"""

from __future__ import annotations

import numpy as np
import pytest

from pybuildingenergy.source.ventilation import VentilationInternalGains
from pybuildingenergy.source.table_iso_16798_1 import internal_gains_occupants


BT = "Residential_apartment"
A_USE = 20.0  # apt 305 net floor area [m2]

# b_ztu values the apt 305 neighbours actually produce (floor/ceiling, party
# walls, corridor). The old code used whichever of these the caller's loop left
# behind, so the inflation factor depended on adjacent-zone *ordering* too.
B_ZTU_APT305 = [0.926, 0.926, 0.867, 0.867, 0.733]


def _table_gain_w(building_type_class: str, a_use: float,
                  h_occup: float = 1.0, h_app: float = 1.0,
                  h_light: float = 1.0) -> float:
    """The ISO 16798-1 table value for this class and area, in W."""
    row = internal_gains_occupants[building_type_class]

    def _finite(x):
        x = float(x)
        return x if np.isfinite(x) else 0.0

    q = (_finite(row.get("occupants", 0.0)) * h_occup
         + _finite(row.get("appliances", 0.0)) * h_app
         + _finite(row.get("lighting", 0.0)) * h_light)
    return q * a_use


def _gains(n_adj: int, b_ztu: float = 0.733, f_ztc: float = 1.0,
           **profiles) -> float:
    """Drive internal_gains() exactly the way utils.py drives it."""
    vig = VentilationInternalGains({})
    return vig.internal_gains(
        building_type_class=BT,
        a_use=A_USE,
        unconditioned_zones_nearby=n_adj > 0,
        list_adj_zones=n_adj if n_adj > 0 else None,
        Fztc_ztu_m=f_ztc,
        b_ztu=b_ztu,
        **profiles,
    )


# ---------------------------------------------------------------------------
# The acceptance criterion: invariance to the neighbour count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_adj", [0, 1, 5])
def test_gains_independent_of_number_of_adjacent_zones(n_adj):
    """0, 1 and 5 neighbours must all give the same internal gain."""
    assert _gains(n_adj) == pytest.approx(_gains(0), rel=0, abs=0)


def test_gains_equal_iso_table_value():
    """
    Acceptance criterion 1: within 5 % of the ISO 16798-1 table value for the
    declared a_use. It is in fact exact, so assert exactness — a 5 % band would
    let a re-introduced 1-neighbour inflation (+113 %) through only because it
    is large, which is not a test.
    """
    expected = _table_gain_w(BT, A_USE)          # 4.2 + 3.0 W/m2 over 20 m2
    assert expected == pytest.approx(144.0, abs=1e-9)
    assert _gains(5) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("b_ztu", B_ZTU_APT305)
def test_gains_independent_of_b_ztu(b_ztu):
    """
    b_ztu and F_ztc_ztu_m must no longer touch the result.

    This is the ordering bug specifically: the caller loops over adjacent zones
    and leaves the *last* zone's b_ztu in scope, so reordering the neighbour
    list used to change the building's internal gains.
    """
    assert _gains(5, b_ztu=b_ztu) == pytest.approx(_gains(5, b_ztu=1.0), rel=0, abs=0)
    assert _gains(5, f_ztc=0.25) == pytest.approx(_gains(5, f_ztc=1.0), rel=0, abs=0)


def test_old_inflation_factor_is_gone():
    """
    Pin the magnitude of the bug so a re-introduction is unambiguous.

    Old behaviour for apt 305 was 1 + 5*(1 + (1-0.733)*1) = 7.335x.
    """
    n, b, f = 5, 0.733, 1.0
    old_factor = 1 + n * (1 + (1 - b) * f)
    assert old_factor == pytest.approx(7.335, abs=1e-3)

    correct = _table_gain_w(BT, A_USE)
    assert _gains(n, b_ztu=b, f_ztc=f) == pytest.approx(correct, rel=1e-12)
    # and emphatically not the inflated value the engine used to report
    assert _gains(n, b_ztu=b, f_ztc=f) != pytest.approx(correct * old_factor, rel=1e-6)


# ---------------------------------------------------------------------------
# Everything the fix must NOT have broken
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("h_occup,h_app", [(0.0, 0.0), (0.5, 1.0), (1.0, 0.2)])
def test_profiles_still_scale_the_gain(h_occup, h_app):
    """Hourly profile multipliers must still apply, with or without neighbours."""
    expected = _table_gain_w(BT, A_USE, h_occup=h_occup, h_app=h_app)
    for n_adj in (0, 5):
        got = _gains(n_adj, h_occup=h_occup, h_app=h_app)
        assert got == pytest.approx(expected, rel=1e-12)


def test_full_load_override_still_applies():
    """A BUI-level full_load override must still win over the ISO table."""
    bui = {"internal_gains": [{"name": "occupants", "full_load": 10.0},
                              {"name": "appliances", "full_load": 5.0}]}
    vig = VentilationInternalGains(bui)
    got = vig.internal_gains(
        building_type_class=BT, a_use=A_USE,
        unconditioned_zones_nearby=True, list_adj_zones=5, b_ztu=0.733,
    )
    assert got == pytest.approx((10.0 + 5.0) * A_USE, rel=1e-12)


def test_signature_still_accepts_the_adjacency_arguments():
    """
    utils.py passes these at two call sites in each single-zone core, so they
    must remain accepted even though they are now inert.
    """
    vig = VentilationInternalGains({})
    vig.internal_gains(
        building_type_class=BT, a_use=A_USE,
        unconditioned_zones_nearby=True, list_adj_zones=5,
        Fztc_ztu_m=0.4, b_ztu=0.9,
        h_occup=1.0, h_app=1.0, h_light=1.0, h_dhw=1.0, h_hvac=1.0, h_proc=1.0,
    )


def test_nan_lighting_in_table_is_treated_as_zero():
    """Residential_apartment has lighting = NaN in the ISO table."""
    assert not np.isfinite(internal_gains_occupants[BT]["lighting"])
    assert np.isfinite(_gains(5))
