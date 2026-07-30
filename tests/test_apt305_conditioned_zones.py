"""
Step 2 acceptance test on the real apt 305 building.

The plan's criterion is a direct assertion, not an eyeballed chart: ``theta_ztu``
for each conditioned zone must equal its declared setpoint at **every** timestep.
That is checked here by capturing the array the solver mutates in place, over a
full annual run.

The probe runs in a subprocess against a worktree of the step-2 engine, because
this branch carries main's engine, not that one. One annual simulation, so this
module is slow (~1 min) by design — the point is to check the real run, not a
stub.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
WEATHER_DIR = REPO_ROOT / "weather_cache"
BRANCH = "claude/conditioned-adjacent-zones-fix"

PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])   # <worktree>/pybuildingenergy/src
sys.path.insert(0, sys.argv[2])   # <repo>/examples

import numpy as np
from apt305_building import build_bui
from pybuildingenergy.source import utils as U
from pybuildingenergy.source.utils import ISO52016
from pybuildingenergy.source.check_input import sanitize_and_validate_BUI

raw = build_bui()
names = [z["name"] for z in raw["adjacent_zones"]]
setpoints = [z.get("setpoint") for z in raw["adjacent_zones"]]
conditioned = [bool(z.get("conditioned", False)) for z in raw["adjacent_zones"]]
adj_types = [s.get("type") for s in raw["building_surface"] if s.get("name_adj_zone")]

building, _issues = sanitize_and_validate_BUI(raw, fix=True)

# theta_ztu is allocated once and mutated in place, so holding the returned
# array gives the whole time series after the run.
captured = {}
orig_init = U._init_theta_ztu
def spy_init(bo, n, Tstepn, default_c=U.DEFAULT_THETA_ZTU_INIT_C):
    arr = orig_init(bo, n, Tstepn, default_c)
    captured["theta_ztu"] = arr
    return arr
U._init_theta_ztu = spy_init

# A conditioned zone must never reach the ISO 13789 buffer formula.
calls = {"n": 0}
orig_unc = U._theta_ztu_unconditioned
def spy_unc(*a, **k):
    calls["n"] += 1
    return orig_unc(*a, **k)
U._theta_ztu_unconditioned = spy_unc

res = ISO52016.Temperature_and_Energy_needs_calculation(
    building, weather_source="epw", path_weather_file=sys.argv[3])
annual = res[1]
arr = np.asarray(captured["theta_ztu"])

def col(k):
    return float(annual[k].iloc[0]) if k in annual.columns else float("nan")

print("PROBE_JSON " + json.dumps({
    "names": names, "setpoints": setpoints, "conditioned": conditioned,
    "adjacent_surface_types": adj_types,
    "shape": list(arr.shape),
    "n_timesteps": int(arr.shape[0]),
    "unconditioned_calls": calls["n"],
    "per_zone_max_dev": {names[i]: float(np.nanmax(np.abs(arr[:, i] - setpoints[i])))
                         for i in range(arr.shape[1])},
    "heating_kWh": col("Q_H_annual_kWh"),
    "cooling_kWh": col("Q_C_annual_kWh"),
    "H_attr_transmission_kWh": col("Q_H_attr_transmission_kWh"),
}))
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    epws = sorted(WEATHER_DIR.glob("*.epw"))
    if not epws:
        pytest.skip("no EPW in weather_cache/")

    tmp = Path(tempfile.mkdtemp(prefix="aib-cond-test-"))
    wt = tmp / "engine"
    last = ""
    for ref in (BRANCH, f"origin/{BRANCH}"):
        p = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "worktree", "add", "--detach", str(wt), ref],
            capture_output=True, text=True)
        if p.returncode == 0:
            break
        last = p.stderr.strip()
    else:
        pytest.skip(f"branch {BRANCH} not available: {last}")

    try:
        script = tmp / "probe.py"
        script.write_text(PROBE, encoding="utf-8")
        run = subprocess.run(
            [sys.executable, str(script), str(wt / "pybuildingenergy" / "src"),
             str(EXAMPLES_DIR), str(epws[0])],
            capture_output=True, text=True, timeout=1800)
        line = next((l for l in run.stdout.splitlines() if l.startswith("PROBE_JSON")), None)
        if line is None:
            tail = "\n".join((run.stderr or run.stdout).strip().splitlines()[-20:])
            pytest.fail(f"probe produced no result:\n{tail}")
        return json.loads(line[len("PROBE_JSON "):])
    finally:
        subprocess.run(["git", "-C", str(REPO_ROOT), "worktree", "remove",
                        "--force", str(wt)], check=False, capture_output=True)


def test_party_surfaces_are_typed_adjacent(probe):
    """
    The prerequisite. The engine classifies a surface ADJ purely from ``type``;
    a ``name_adj_zone`` on an ``"opaque"`` surface is silently ignored and the
    surface is modelled as an exterior wall. If this regresses, every assertion
    below still passes while measuring nothing.
    """
    assert probe["adjacent_surface_types"] == ["adjacent"] * 5, \
        probe["adjacent_surface_types"]


def test_all_five_neighbours_are_declared_conditioned(probe):
    assert probe["conditioned"] == [True] * 5
    assert probe["setpoints"] == [20.0] * 5


def test_theta_ztu_equals_the_setpoint_at_every_timestep(probe):
    """The acceptance criterion, asserted rather than eyeballed."""
    assert probe["n_timesteps"] > 8000, probe["shape"]
    for name, dev in probe["per_zone_max_dev"].items():
        assert dev == pytest.approx(0.0, abs=1e-12), f"{name} deviates by {dev} K"


def test_conditioned_zones_never_reach_the_buffer_formula(probe):
    """
    Complementary to the above: with all five conditioned, the ISO 13789
    unconditioned expression must not be evaluated at all. (It is called ~71 000
    times when the same building is run with the neighbours unconditioned.)
    """
    assert probe["unconditioned_calls"] == 0


def test_demand_is_plausible_for_an_apartment_inside_a_block(probe):
    """
    Not a tolerance on a golden number — a plausibility band. One exposed
    facade, five conditioned neighbours: annual demand should be small, and the
    transmission-attributed heating in particular should be a small fraction of
    total heating rather than dominating it.
    """
    heating, cooling = probe["heating_kWh"], probe["cooling_kWh"]
    assert 0.0 < heating < 600.0, heating
    assert 0.0 <= cooling < 300.0, cooling
    assert probe["H_attr_transmission_kWh"] < heating, probe["H_attr_transmission_kWh"]
