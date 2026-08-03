"""
Acceptance tests for the closed energy balance (Defect A).

Two things are asserted here, against one real annual run of the canonical
apt 305 dictionary on this branch's engine:

1.  **The ADJ surfaces are in the inventory.** All five party surfaces --
    75.10 m2, 88.6 % of the envelope UA -- must each carry their own
    transmission line item. Before the fix the Sankey listed two transmission
    entries for a building with seven opaque/transparent/party surfaces, and the
    party surfaces appeared nowhere.

2.  **The reported inventory is arithmetically consistent and the balance
    closes.** The sum of the Sankey's transmission line items must equal the sum
    of the per-surface conductive flows integrated independently from the hourly
    frame, to within 0.1 %; and the V2 closure residual must be under 5 %.

A second, minimal ground-floor building guards the GR path: with a slab present
the ground term must be non-zero and must be counted exactly once -- the
per-surface element tally and the lumped ``h_ground`` term must not both fire.

One annual simulation per building, so this module is slow (~40 s) by design.
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

from weather_melbourne import CANONICAL_EPW  # noqa: E402

# The case-study weather file, named in one place (``examples/weather_melbourne.py``)
# so a test can never quietly run on the superseded Melbourne Regional Office
# file, whose wind column has four dead-calm months.
EPW = str(REPO_ROOT / "weather_cache" / CANONICAL_EPW)

RESIDUAL_KEY = "Transmission (residual)"
V2_TOLERANCE_PCT = 5.0

# The five party surfaces, by the name each carries in the building dictionary.
PARTY_SURFACES = [
    "North wall to Apt 306",
    "South wall to Apt 304",
    "East wall to corridor",
    "Floor to Apt 205",
    "Ceiling to Apt 405",
]
PARTY_AREA_M2 = 10.8 + 10.8 + 13.5 + 20.0 + 20.0  # 75.10


def _run(raw: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    building, _ = sanitize_and_validate_BUI(raw, fix=True)
    hourly, annual, sankey = ISO52016.Temperature_and_Energy_needs_calculation(
        building, weather_source="epw", path_weather_file=EPW, return_sankey_data=True
    )
    return hourly, annual, sankey


@pytest.fixture(scope="module")
def apt305():
    hourly, annual, sankey = _run(build_bui())
    return {"hourly": hourly, "annual": annual, "sankey": sankey}


def _transmission_items(sankey: dict) -> dict[str, float]:
    return {
        k: float(v)
        for k, v in sankey["outputs"].items()
        if k.startswith("Transmission - ")
    }


def _v2_residual_pct(sankey: dict) -> float:
    """Residual exactly as the six-state harness computes it.

    ``Transmission (residual)`` is excluded from the outputs sum: it is the
    residual re-published as a flow, and including it would close the balance by
    construction.
    """
    inputs = sum(float(v) for v in sankey["inputs"].values())
    outputs = sum(
        float(v) for k, v in sankey["outputs"].items() if k != RESIDUAL_KEY
    )
    storage = float(sankey.get("energy_accumulated_zone", 0.0))
    return 100.0 * (inputs - outputs - storage) / max(1.0, inputs)


# ---------------------------------------------------------------------------
# 1. The ADJ surfaces are in the inventory
# ---------------------------------------------------------------------------

def test_every_party_surface_has_a_transmission_line_item(apt305):
    items = _transmission_items(apt305["sankey"])
    missing = [
        name for name in PARTY_SURFACES
        if not any(name in key for key in items)
    ]
    assert not missing, (
        f"{PARTY_AREA_M2:.2f} m2 of party surface still missing from the Sankey "
        f"inventory: {missing}. Present: {sorted(items)}"
    )


def test_party_surfaces_are_typed_adj_not_ground(apt305):
    types = apt305["sankey"]["closure"]["surface_iso_types"]
    for name in PARTY_SURFACES:
        matched = [t for k, t in types.items() if name in k]
        assert matched, f"{name!r} absent from the surface type map: {sorted(types)}"
        assert all(t == "ADJ" for t in matched), (
            f"{name!r} classified {matched} -- a party surface is never ground contact"
        )


def test_adjacent_transmission_is_non_zero_and_signed_both_ways(apt305):
    """A conditioned neighbour is not a zero-flow boundary.

    Held at 20 C against a zone that floats between the 18 C heating setpoint and
    the 26 C cooling setpoint, the party surfaces carry heat in both directions;
    both branches must be non-zero, which also rules out a hard-zeroed term.
    """
    annual = apt305["annual"]

    def col(name):
        return float(pd.to_numeric(annual[name], errors="coerce").iloc[0])

    assert col("Q_tr_adjacent_loss_kWh") > 0.0
    assert col("Q_tr_adjacent_gain_kWh") > 0.0


# ---------------------------------------------------------------------------
# 2. The inventory is arithmetically consistent and the balance closes
# ---------------------------------------------------------------------------

def test_sankey_transmission_matches_independent_per_surface_integration(apt305):
    """Regression guard required by the plan: the two aggregation paths agree.

    The Sankey line items come from a per-timestep accumulator inside the solve
    loop. The comparison is built the other way round -- from the hourly frame,
    integrated after the fact with pandas -- so a surface dropped from one path
    and not the other cannot pass.
    """
    hourly = apt305["hourly"]
    annual = apt305["annual"]
    dt_h = float(pd.to_numeric(annual["time_step_h"], errors="coerce").iloc[0])

    sankey_total_kWh = sum(_transmission_items(apt305["sankey"]).values()) / 1000.0

    surface_cols = [c for c in hourly.columns if c.startswith("Q_tr_surface_")]
    assert surface_cols, "no per-surface transmission columns in the hourly frame"
    independent_total_kWh = sum(
        float(
            pd.to_numeric(hourly[c], errors="coerce").fillna(0.0).clip(lower=0.0).sum()
        )
        * dt_h
        / 1000.0
        for c in surface_cols
    )

    assert sankey_total_kWh > 0.0
    rel = abs(sankey_total_kWh - independent_total_kWh) / sankey_total_kWh
    assert rel < 1e-3, (
        f"transmission line items {sankey_total_kWh:.4f} kWh vs independent "
        f"per-surface integration {independent_total_kWh:.4f} kWh "
        f"({100 * rel:.4f} % apart, tolerance 0.1 %)"
    )


def test_v2_residual_under_tolerance(apt305):
    pct = _v2_residual_pct(apt305["sankey"])
    assert abs(pct) < V2_TOLERANCE_PCT, (
        f"V2 closure residual {pct:.3f} % exceeds the {V2_TOLERANCE_PCT} % gate"
    )


def test_engine_reported_closure_matches_recomputation(apt305):
    """The engine's own ``closure`` block must not disagree with the recomputation."""
    reported = float(apt305["sankey"]["closure"]["residual_pct"])
    assert reported == pytest.approx(_v2_residual_pct(apt305["sankey"]), abs=1e-6)


def test_no_republished_residual_flow(apt305):
    """Below 1 % the engine folds the residual into storage; above it, it
    republishes it as a pseudo-flow. A closed balance does neither."""
    assert RESIDUAL_KEY not in apt305["sankey"]["outputs"]


# ---------------------------------------------------------------------------
# 3. The GR path: counted once, and not zero
# ---------------------------------------------------------------------------

def _ground_floor_building() -> dict:
    """A one-zone slab-on-ground box, minimal but complete enough to simulate."""
    bui = build_bui()
    bui["building"]["name"] = "ground_floor_probe"
    bui["building"]["exposed_perimeter"] = 18.0
    bui["building"]["adj_zones_present"] = False
    bui["building"]["number_adj_zone"] = 0
    bui.pop("adjacent_zones", None)
    surfaces = []
    for surf in bui["building_surface"]:
        if surf["type"] == "adjacent":
            if surf["name"] != "Floor to Apt 205":
                continue
            surf = dict(surf)
            surf["name"] = "Slab on ground"
            surf["type"] = "opaque"
            surf["boundary"] = "GROUND"
            surf["name_adj_zone"] = None
        surfaces.append(surf)
    bui["building_surface"] = surfaces
    return bui


@pytest.fixture(scope="module")
def ground_floor():
    hourly, annual, sankey = _run(_ground_floor_building())
    return {"hourly": hourly, "annual": annual, "sankey": sankey}


def test_ground_floor_reports_a_non_zero_ground_flow(ground_floor):
    """Without this the ADJ fix could be a blanket 'ground is always zero'."""
    items = _transmission_items(ground_floor["sankey"])
    slab = [v for k, v in items.items() if "Slab on ground" in k]
    lumped = float(ground_floor["sankey"]["outputs"].get("Ground", 0.0))
    assert slab, f"slab absent from the inventory: {sorted(items)}"
    assert slab[0] + lumped > 0.0, "a slab-on-ground box reported no ground flow at all"


def test_ground_is_not_counted_twice(ground_floor):
    """With a GR element present the lumped ``h_ground`` term must be suppressed."""
    assert float(ground_floor["sankey"]["outputs"].get("Ground", 0.0)) == 0.0


def test_ground_floor_balance_also_closes(ground_floor):
    pct = _v2_residual_pct(ground_floor["sankey"])
    assert abs(pct) < V2_TOLERANCE_PCT, (
        f"ground-floor V2 closure residual {pct:.3f} % exceeds the "
        f"{V2_TOLERANCE_PCT} % gate"
    )
