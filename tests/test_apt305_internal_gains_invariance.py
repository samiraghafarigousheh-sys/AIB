"""
Step 1 acceptance test against the real apt 305 dictionary.

The engine-branch tests (``tests/test_internal_gains_adjacency.py`` on
``claude/internal-gains-fix``) prove the function is invariant to neighbour
count using synthetic inputs. This one closes the loop on the actual building:
it takes apt 305's own ``building_type_class``, ``net_floor_area`` and the
``b_ztu`` / ``F_ztc_ztu_m`` its five real neighbours produce, and sweeps
``number_adj_zone`` over 0, 1 and 5.

It has to drive the engine from a worktree rather than from ``sys.path``,
because the harness branch carries main's engine (window + h_ce), not the
step-1 engine. The sweep is on ``internal_gains()`` only -- no annual
simulation -- so it costs a worktree checkout and about a second, not a minute.
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
BRANCH = "claude/internal-gains-fix"

# Runs inside the worktree's engine. Emits one JSON blob on stdout.
PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])   # <worktree>/pybuildingenergy/src
sys.path.insert(0, sys.argv[2])   # <repo>/examples

from apt305_building import build_bui
from pybuildingenergy.source.utils import ISO52016
from pybuildingenergy.source.ventilation import VentilationInternalGains
from pybuildingenergy.source.table_iso_16798_1 import internal_gains_occupants

bui = build_bui()
bt = bui["building"]["building_type_class"]
a_use = float(bui["building"]["net_floor_area"])
zones = bui["adjacent_zones"]

# The b_ztu / F_ztc_ztu_m each real neighbour produces, in dictionary order --
# the old code used whichever one the caller's loop left behind, i.e. the last.
coeffs = []
for z in zones:
    H, b, F = ISO52016().transmission_heat_transfer_coefficient_ISO13789(z)
    coeffs.append({"name": z["name"], "H_ztu": float(H),
                   "b_ztu": float(b), "F_ztc_ztu_m": float(F)})

vig = VentilationInternalGains(bui)

def gains(n, b, F):
    return vig.internal_gains(
        building_type_class=bt, a_use=a_use,
        unconditioned_zones_nearby=n > 0,
        list_adj_zones=n if n > 0 else None,
        Fztc_ztu_m=F, b_ztu=b,
    )

trailing = coeffs[-1]
sweep = {str(n): gains(n, trailing["b_ztu"], trailing["F_ztc_ztu_m"])
         for n in (0, 1, 5)}
per_zone = {c["name"]: gains(5, c["b_ztu"], c["F_ztc_ztu_m"]) for c in coeffs}

row = internal_gains_occupants[bt]
def finite(x):
    x = float(x)
    return x if x == x else 0.0
table_w = (finite(row.get("occupants", 0.0)) + finite(row.get("appliances", 0.0))
           + finite(row.get("lighting", 0.0))) * a_use

print(json.dumps({
    "building_type_class": bt, "a_use": a_use, "n_zones": len(zones),
    "coeffs": coeffs, "sweep": sweep, "per_zone": per_zone,
    "table_w": table_w,
}))
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="aib-ig-test-"))
    wt = tmp / "engine"
    last = ""
    for ref in (BRANCH, f"origin/{BRANCH}"):
        p = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "worktree", "add", "--detach", str(wt), ref],
            capture_output=True, text=True,
        )
        if p.returncode == 0:
            break
        last = p.stderr.strip()
    else:
        pytest.skip(f"branch {BRANCH} not available in this clone: {last}")

    try:
        script = tmp / "probe.py"
        script.write_text(PROBE, encoding="utf-8")
        run = subprocess.run(
            [sys.executable, str(script),
             str(wt / "pybuildingenergy" / "src"), str(EXAMPLES_DIR)],
            capture_output=True, text=True,
        )
        if run.returncode != 0:
            tail = "\n".join((run.stderr or run.stdout).strip().splitlines()[-15:])
            pytest.fail(f"probe failed:\n{tail}")
        return json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        subprocess.run(["git", "-C", str(REPO_ROOT), "worktree", "remove",
                        "--force", str(wt)], check=False, capture_output=True)


def test_apt305_has_five_neighbours(probe):
    assert probe["n_zones"] == 5
    assert probe["building_type_class"] == "Residential_apartment"
    assert probe["a_use"] == pytest.approx(20.0)


def test_gains_identical_for_zero_one_and_five_neighbours(probe):
    """The acceptance criterion, on the real building."""
    s = probe["sweep"]
    assert s["0"] == pytest.approx(s["1"], rel=0, abs=0)
    assert s["0"] == pytest.approx(s["5"], rel=0, abs=0)


def test_gains_match_the_iso_table_value(probe):
    """Within 5 % of the ISO 16798-1 table value — in fact exact."""
    expected = probe["table_w"]
    assert expected == pytest.approx(144.0, abs=1e-9)   # (4.2 + 3.0) W/m2 * 20 m2
    for n, got in probe["sweep"].items():
        assert got == pytest.approx(expected, rel=1e-12), f"n_adj={n}"


def test_neighbour_ordering_no_longer_changes_the_answer(probe):
    """
    Each neighbour has a different b_ztu, and the old code silently used the
    last one in the list for all five. Reordering the dictionary used to change
    the building's internal gains; it must not any more.
    """
    vals = list(probe["per_zone"].values())
    assert len(set(f"{v:.12e}" for v in vals)) == 1, probe["per_zone"]
    assert vals[0] == pytest.approx(probe["table_w"], rel=1e-12)


def test_the_old_inflation_factor_is_reproduced_by_the_recorded_coefficients(probe):
    """
    Pin the size of what was removed, using apt 305's real coefficients rather
    than a remembered number: 1 + 5*(1 + (1-b_ztu)*F) with the trailing zone's
    b_ztu is 7.335, which is exactly the ratio the harness reports between the
    +Vent+Latent and +Internal Gains internal-gain columns.
    """
    trailing = probe["coeffs"][-1]
    n = probe["n_zones"]
    old_factor = 1 + n * (1 + (1 - trailing["b_ztu"]) * trailing["F_ztc_ztu_m"])
    assert old_factor == pytest.approx(7.335, abs=5e-3)
    assert probe["sweep"]["5"] == pytest.approx(probe["table_w"], rel=1e-12)
