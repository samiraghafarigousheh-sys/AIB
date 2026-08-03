"""
Upstream acceptance tests — a surface is ground contact only when declared so.

The rule this replaces mapped ``type == "opaque"`` with ``sky_view_factor == 0``
onto ``GR`` (slab-on-ground). Zero sky-view means "not exposed to sky", which is
true of any internal partition, floor or ceiling. On apt 305 it buried all five
party surfaces -- including the ceiling of a third-floor apartment -- as 75.10 m2
of slab clamped near the ISO 13370 ground temperature, collapsing heating to
15.86 kWh and inflating cooling to 2 027.5 kWh. That single field is the whole of
the config-A / config-B contradiction.

Asserted here:

  * the classifier never returns GR without an explicit ground boundary;
  * a zero-sky-view surface naming an adjacent zone classifies ADJ;
  * a zero-sky-view surface that declares neither raises a validator warning
    instead of silently defaulting to ground;
  * config A (party surfaces typed "opaque") and config B (typed "adjacent")
    converge to the same annual result.

The convergence test runs two annual simulations, so it is slow (~30 s).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pybuildingenergy" / "src"))
sys.path.insert(0, str(REPO_ROOT / "examples"))

from apt305_building import build_bui  # noqa: E402
from pybuildingenergy.source.check_input import sanitize_and_validate_BUI  # noqa: E402
from pybuildingenergy.source.utils import (  # noqa: E402
    ISO52016,
    _classify_iso52016_element,
)

from weather_melbourne import CANONICAL_EPW  # noqa: E402

# The case-study weather file, named in one place (``examples/weather_melbourne.py``)
# so a test can never quietly run on the superseded Melbourne Regional Office
# file, whose wind column has four dead-calm months.
EPW = str(REPO_ROOT / "weather_cache" / CANONICAL_EPW)

COMPARE_KEYS = [
    "Q_H_annual_kWh",
    "Q_C_annual_kWh",
    "Q_C_latent_kWh",
    "Q_H_latent_kWh",
    "Q_need_total_kWh",
    "Q_tr_adjacent_loss_kWh",
    "Q_tr_adjacent_gain_kWh",
    "Q_ground_loss_kWh",
]


# ---------------------------------------------------------------------------
# The classifier itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("surf, expected", [
    # zero sky-view, no ground tag, no neighbour: NOT ground
    ({"type": "opaque", "sky_view_factor": 0.0}, "OP"),
    # zero sky-view + a named neighbour: partition
    ({"type": "opaque", "sky_view_factor": 0.0, "name_adj_zone": "apt_north"}, "ADJ"),
    # the explicit tag is the only route to GR
    ({"type": "opaque", "sky_view_factor": 0.0, "boundary": "GROUND"}, "GR"),
    ({"type": "opaque", "sky_view_factor": 0.5, "boundary": "GROUND"}, "GR"),
    # everything else unchanged
    ({"type": "opaque", "sky_view_factor": 0.5}, "OP"),
    ({"type": "transparent", "sky_view_factor": 0.5}, "W"),
    ({"type": "adjacent", "sky_view_factor": 0.0, "name_adj_zone": "corridor"}, "ADJ"),
    ({"type": "adiabatic", "sky_view_factor": 0.0}, "AD"),
    ({"type": "opaque", "sky_view_factor": 0.0, "boundary": "INTERNAL"}, "ADJ"),
    ({"type": "opaque", "sky_view_factor": 0.0, "boundary": "ADIABATIC"}, "AD"),
])
def test_classifier(surf, expected):
    assert _classify_iso52016_element(surf) == expected


def test_zero_sky_view_alone_never_means_ground():
    """The exact defect: an unshaded-but-skyless ceiling is not a slab."""
    ceiling = {
        "name": "Ceiling to Apt 405", "type": "opaque", "sky_view_factor": 0.0,
        "orientation": {"azimuth": 0.0, "tilt": 0.0},
    }
    assert _classify_iso52016_element(ceiling) != "GR"


# ---------------------------------------------------------------------------
# The validator
# ---------------------------------------------------------------------------

def _svf_zero_warnings(report) -> list:
    """``sanitize_and_validate_BUI`` returns a list of
    ``{level, path, msg, fix_applied}`` dicts."""
    return [
        it for it in (report or [])
        if "sky_view_factor" in str(it.get("path", ""))
        and "adjacent zone" in str(it.get("msg", ""))
    ]


def test_validator_warns_on_ambiguous_zero_sky_view_surface():
    bui = build_bui()
    bui["building_surface"].append({
        "name": "Undeclared skyless wall", "type": "opaque", "area": 5.0,
        "sky_view_factor": 0.0, "u_value": 1.0, "solar_absorptance": 0.6,
        "thermal_capacity": 0, "orientation": {"azimuth": 90.0, "tilt": 90.0},
        "name_adj_zone": None, "height": 2.5, "length": 2.0,
    })
    _, report = sanitize_and_validate_BUI(bui, fix=True)
    warns = _svf_zero_warnings(report)
    assert warns, "an svf=0 surface with neither ground nor adjacent zone drew no warning"
    assert any("Undeclared skyless wall" in str(w.get("msg", "")) for w in warns)
    assert all(w.get("level") == "WARN" for w in warns), "must warn, not hard-fail"


def test_validator_is_quiet_for_declared_surfaces():
    """The canonical dictionary declares every party surface, so it must be
    clean -- otherwise the warning is noise rather than a signal."""
    _, report = sanitize_and_validate_BUI(build_bui(), fix=True)
    assert not _svf_zero_warnings(report)


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------

def _config(name: str) -> dict:
    raw = build_bui()
    if name == "A":
        for s in raw["building_surface"]:
            if s["type"] == "adjacent":
                s["type"] = "opaque"
    return raw


def _run(raw: dict) -> dict:
    building, _ = sanitize_and_validate_BUI(raw, fix=True)
    _, annual, sankey = ISO52016.Temperature_and_Energy_needs_calculation(
        building, weather_source="epw", path_weather_file=EPW, return_sankey_data=True
    )
    return {
        "types": dict(sankey["closure"]["surface_iso_types"]),
        "vals": {
            k: float(pd.to_numeric(annual[k], errors="coerce").iloc[0])
            for k in COMPARE_KEYS
        },
    }


@pytest.fixture(scope="module")
def configs():
    return {"A": _run(_config("A")), "B": _run(_config("B"))}


def test_no_surface_is_classified_gr_without_a_ground_boundary(configs):
    for label, res in configs.items():
        gr = [n for n, t in res["types"].items() if t == "GR"]
        assert not gr, f"config {label} still classifies {gr} as slab-on-ground"


def test_config_a_and_config_b_classify_identically(configs):
    assert configs["A"]["types"] == configs["B"]["types"]


def test_config_a_and_config_b_converge(configs):
    for key in COMPARE_KEYS:
        assert configs["A"]["vals"][key] == pytest.approx(
            configs["B"]["vals"][key], abs=1e-6
        ), f"{key} still differs between the two typings"


def test_config_a_no_longer_reproduces_the_buried_slab_result(configs):
    """The specific numbers the misclassification produced: 15.86 / 2027.5."""
    vals = configs["A"]["vals"]
    assert vals["Q_H_annual_kWh"] > 100.0, "config A still collapses heating"
    assert vals["Q_C_annual_kWh"] < 500.0, "config A still inflates cooling"
    assert vals["Q_ground_loss_kWh"] == pytest.approx(0.0, abs=1e-9)
