"""
Steps 3 and 4 acceptance tests, against the final engine and real weather.

Step 3 — ground contact
    * apt 305 (Level 3, nothing touching the ground): ground loss and gain must
      both be exactly 0 for the full year.
    * A minimal ground-floor dictionary must still produce a non-zero ground
      term, matching an independent ISO 13370 hand calculation. Without this
      second case the fix could be a blanket "always return 0" and every other
      assertion would still pass.

Step 4 — hemisphere
    * On that same ground-floor building at Melbourne's latitude, the ground
      temperature must peak in the southern summer and trough in the southern
      winter, and must invert when the latitude is forced positive.

Both drive a worktree of ``claude/coldest-month-hemisphere-fix`` — the tip of
the correction chain — in a subprocess, since this branch carries main's engine.
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
BRANCH = "claude/coldest-month-hemisphere-fix"

# ISO 13370 reference case, computed independently in the test below.
SLAB_AREA_M2 = 56.25
PERIMETER_M = 30.0

PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
EPW = sys.argv[3]

import numpy as np
from apt305_building import build_bui
from pybuildingenergy.source.utils import ISO52016, _ground_contact_area
from pybuildingenergy.source.check_input import sanitize_and_validate_BUI

out = {}

# --- apt 305: no ground contact anywhere -------------------------------------
bui, _ = sanitize_and_validate_BUI(build_bui(), fix=True)
res = ISO52016.Temperature_and_Energy_needs_calculation(
    bui, weather_source="epw", path_weather_file=EPW)
ann = res[1]
def col(k):
    return float(ann[k].iloc[0]) if k in ann.columns else float("nan")
out["apt305"] = {
    "ground_contact_area": _ground_contact_area(bui),
    "ground_loss_kWh": col("Q_ground_loss_kWh"),
    "ground_gain_kWh": col("Q_ground_gain_kWh"),
    "heating_kWh": col("Q_H_annual_kWh"),
}

# --- minimal ground-floor building -------------------------------------------
def ground_floor(latitude):
    return {
        "building": {"net_floor_area": 56.25, "exposed_perimeter": 30.0,
                     "height": 2.7, "wall_thickness": 0.20,
                     "latitude": latitude, "longitude": 144.97},
        "building_surface": [{
            "name": "slab", "type": "opaque", "area": 56.25,
            "sky_view_factor": 0.0, "boundary": "GROUND",
            "orientation": {"azimuth": 0.0, "tilt": 0.0}, "name_adj_zone": None,
        }],
        "building_parameters": {"temperature_setpoints": {
            "heating_setpoint": 20.0, "cooling_setpoint": 26.0}},
    }

for label, lat in (("south", -37.8), ("north", 45.5)):
    b = ground_floor(lat)
    tg = ISO52016.Temp_calculation_of_ground(b, path_weather_file=EPW, weather_source="epw")
    T = np.asarray(tg.Theta_gr_ve, dtype=float)
    out[f"ground_floor_{label}"] = {
        "area": _ground_contact_area(b),
        "R_gr_ve": float(tg.R_gr_ve),
        "coldest_month": int(b["building_parameters"]["coldest_month"]),
        "peak_month": int(np.argmax(T)) + 1,
        "trough_month": int(np.argmin(T)) + 1,
        "profile": [float(x) for x in T],
    }

print("PROBE_JSON " + json.dumps(out))
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    epws = sorted(WEATHER_DIR.glob("*.epw"))
    if not epws:
        pytest.skip("no EPW in weather_cache/")

    tmp = Path(tempfile.mkdtemp(prefix="aib-ground-test-"))
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


# ---------------------------------------------------------------------------
# Step 3
# ---------------------------------------------------------------------------

def test_apt305_has_no_ground_contact(probe):
    assert probe["apt305"]["ground_contact_area"] == 0.0


def test_apt305_ground_loss_and_gain_are_exactly_zero(probe):
    """The step 3 acceptance criterion, over the full year."""
    assert probe["apt305"]["ground_loss_kWh"] == pytest.approx(0.0, abs=1e-12)
    assert probe["apt305"]["ground_gain_kWh"] == pytest.approx(0.0, abs=1e-12)


def test_a_real_ground_floor_still_gets_a_ground_term(probe):
    """Guards against the fix being a blanket 'always return 0'."""
    gf = probe["ground_floor_south"]
    assert gf["area"] == pytest.approx(SLAB_AREA_M2)
    assert gf["R_gr_ve"] > 0.0


def test_ground_resistance_matches_an_iso13370_hand_calculation(probe):
    """
    Independent recomputation of ISO 13370 §8.1-8.2 for this slab:

        d_t   = w + lambda*(R_f + R_se)
        B'    = A / (0.5*P)
        U_sog = lambda / (0.457*B' + d_t)          (well-insulated branch, d_t >= B')
        R_gr_ve = 1/U_sog - R_si - R_f - R_gr

    with the engine's own defaults: lambda = 2.0, R_si = 0.17, R_se = 0.04,
    R_f = 5.3, R_gr = 0.5/lambda, wall thickness 0.20 m.
    """
    import math

    lam, R_si, R_se, R_f, w = 2.0, 0.17, 0.04, 5.3, 0.20
    R_gr = 0.5 / lam
    d_t = w + lam * (R_f + R_se)
    B_prime = SLAB_AREA_M2 / (0.5 * PERIMETER_M)
    assert d_t >= B_prime, "expected the well-insulated branch for this geometry"
    U_sog = lam / (0.457 * B_prime + d_t)
    expected = 1.0 / U_sog - R_si - R_f - R_gr

    assert B_prime == pytest.approx(3.750)
    assert U_sog == pytest.approx(0.15881, abs=1e-5)
    assert probe["ground_floor_south"]["R_gr_ve"] == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# Step 4
# ---------------------------------------------------------------------------

def test_southern_site_resolves_coldest_month_to_july(probe):
    assert probe["ground_floor_south"]["coldest_month"] == 7
    assert probe["ground_floor_north"]["coldest_month"] == 1


def test_ground_temperature_peaks_in_southern_summer(probe):
    """
    Melbourne's air temperature peaks in Jan-Feb and troughs in Jul-Aug. The
    ground profile must follow it, not oppose it.

    Peak lands in February rather than January because the ISO 13370 external
    term carries a one-month lag (b_tl = 1): ground lags air, which is the point
    of the model. The assertion is therefore on the southern-summer window, not
    on a single month.
    """
    gf = probe["ground_floor_south"]
    assert gf["peak_month"] in (1, 2, 3), gf["peak_month"]
    assert gf["trough_month"] in (7, 8, 9), gf["trough_month"]


def test_forcing_the_northern_hemisphere_inverts_the_profile(probe):
    """Same building, same weather, latitude sign flipped — six months apart."""
    south, north = probe["ground_floor_south"], probe["ground_floor_north"]
    assert (north["peak_month"] - south["peak_month"]) % 12 == 6
    assert (north["trough_month"] - south["trough_month"]) % 12 == 6
    # Amplitude is unchanged; only the phase moves.
    assert max(north["profile"]) == pytest.approx(max(south["profile"]), rel=1e-9)
    assert min(north["profile"]) == pytest.approx(min(south["profile"]), rel=1e-9)
