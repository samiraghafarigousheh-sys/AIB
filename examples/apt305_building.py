"""
Reference case: Apartment 305, 50 Barry St, Carlton (Melbourne, Australia).

A single 20 m2 apartment with one exposed (west) facade and five conditioned
neighbours. Thermal mass is deliberately zeroed so that the RC-network
(ISO 52016-1) and CTF (EnergyPlus) treatments of transient storage cannot
differ, isolating steady-state conduction and radiation physics.

This module holds *only* the building definition, with no engine import, so the
same dictionary can be fed to several different engine versions in the same
comparison run.

SURFACE TYPING
--------------
The five party surfaces carry ``type: "adjacent"``, not ``"opaque"``. This is
load-bearing, not cosmetic: the engine classifies a surface as ADJ purely from
``type``, and a ``name_adj_zone`` on an ``"opaque"`` surface is silently
ignored: ``theta_ztu`` was computed every timestep and never consumed, and the
adjacency pairing checks in ``check_input.py`` (which also key off
``type == "adjacent"``) never ran either.

Worse, the core maps ``type == "opaque"`` with ``sky_view_factor == 0`` to
**GR — slab-on-ground**. Typed ``"opaque"``, all five party surfaces *including
the ceiling* were modelled as buried in the earth, giving this third-floor
apartment 75.1 m² of ground contact. Any figure produced before this was
corrected is for a 20 m² box with 75 m² of slab-on-ground.

Only the *type* changed. Areas, U-values, capacities, orientations and the
adjacent-zone definitions are untouched.
"""

from __future__ import annotations

import numpy as np

# --- Construction U-values & thermal capacity - Australian BCA 2006 minimum-spec ---
U_EXT_WALL = 1.00   # brick veneer / precast w/ R1.0 insulation  [W/m2K]
U_INT_WALL = 2.50   # concrete block + plasterboard, no insulation
U_INT_SLAB = 1.80   # 200 mm concrete intermediate floor
U_WINDOW = 5.40     # aluminium-frame single glazing
G_WINDOW = 0.65     # SHGC of clear single glazing

ABS_EXT_WALL = 0.75  # dark red brick
ABS_INT = 0.0

# Thermal mass zeroed for engine-method-only comparison.
C_EXT_WALL = 0
C_INT_WALL = 0
C_INT_SLAB = 0
C_WINDOW = 0

# --- Geometry ---
LEN_NS = 5.0   # N-S length, m (west facade width, along Barry St)
LEN_EW = 4.0   # E-W depth, m
HEIGHT = 2.7   # ceiling height, m

FLOOR_AREA = LEN_NS * LEN_EW
VOLUME = FLOOR_AREA * HEIGHT

# Temperature the five neighbours are held at, in degC.
#
# All five are marked ``conditioned: True``, which stops the engine running them
# through the ISO 13789 unconditioned-buffer model (b_ztu 0.73-0.93, i.e. mostly
# tracking outdoor air) and holds them here instead. Four of them are occupied
# apartments identical to this one, so that is straightforwardly right.
#
# THE CORRIDOR IS AN ASSUMPTION, NOT A MEASUREMENT. Common corridors in this
# building type are usually tempered, but the actual services at 50 Barry St
# have not been checked. It is the least-insulated neighbour (b_ztu 0.733, the
# lowest of the five) so it carries the most weight of any single zone: if the
# corridor turns out to be unconditioned, set ``conditioned: False`` on that
# entry alone and re-run. Flagged rather than assumed silently.
ADJ_SETPOINT = 20.0

A_WEST_GROSS = LEN_NS * HEIGHT
A_EAST_GROSS = LEN_NS * HEIGHT
A_NORTH_GROSS = LEN_EW * HEIGHT
A_SOUTH_GROSS = LEN_EW * HEIGHT

WIN_WIDTH_FIXED, WIN_HEIGHT_FIXED = 0.9, 0.9
WIN_WIDTH_OPERABLE, WIN_HEIGHT_OPERABLE = 0.9, 0.9
A_WINDOW_FIXED = WIN_WIDTH_FIXED * WIN_HEIGHT_FIXED
A_WINDOW_OPERABLE = WIN_WIDTH_OPERABLE * WIN_HEIGHT_OPERABLE
A_WINDOW_TOTAL = A_WINDOW_FIXED + A_WINDOW_OPERABLE
A_WEST_OPAQUE = A_WEST_GROSS - A_WINDOW_TOTAL


def build_bui() -> dict:
    """Returns a fresh copy of the Apt 305 building dictionary (no shared state)."""
    bui = {
        "building": {
            "name": "Apt_305_50_Barry_St_Carlton",
            "azimuth_relative_to_true_north": 0,
            "latitude": -37.800,
            "longitude": 144.968,
            "exposed_perimeter": 0,
            "height": HEIGHT,
            "wall_thickness": 0.20,
            "n_floors": 1,
            "building_type_class": "Residential_apartment",
            "adj_zones_present": True,
            "number_adj_zone": 5,
            "net_floor_area": FLOOR_AREA,
            "construction_class": "class_iii",
            # Envelope-permeability band for infiltration (q50). The building was
            # COMPLETED in 2006 and was therefore designed and built to the
            # practice PRECEDING that year, so the pre-2006 band "1991-2005" is
            # adopted rather than "2006-today". Under the Australian-calibrated
            # table in utils.py that resolves q50 = 14.0 m3/(h*m2)@50Pa (derived
            # 2006-2015 stock, upper). A measured blower-door result, if one
            # existed, would override this via ventilation.envelope_permeability_q50.
            "construction_year": "1991-2005",
            "country": "Australia",
        },
        "adjacent_zones": [
            {
                "name": "apt_above",
                "orientation_zone": {"azimuth": 270.0},
                "area_facade_elements": np.array(
                    [A_WEST_GROSS, A_NORTH_GROSS, A_EAST_GROSS, A_SOUTH_GROSS, FLOOR_AREA, FLOOR_AREA]
                ),
                "typology_elements": ["OP", "OP", "OP", "OP", "OP", "OP"],
                "transmittance_U_elements": np.array(
                    [U_EXT_WALL, U_INT_WALL, U_INT_WALL, U_INT_WALL, U_INT_SLAB, U_INT_SLAB]
                ),
                "orientation_elements": np.array(["WV", "NV", "EV", "SV", "HOR", "HOR"]),
                "volume": VOLUME,
                "building_type_class": "Residential_apartment",
                "a_use": FLOOR_AREA,
                "conditioned": True,
                "setpoint": ADJ_SETPOINT,
            },
            {
                "name": "apt_below",
                "orientation_zone": {"azimuth": 270.0},
                "area_facade_elements": np.array(
                    [A_WEST_GROSS, A_NORTH_GROSS, A_EAST_GROSS, A_SOUTH_GROSS, FLOOR_AREA, FLOOR_AREA]
                ),
                "typology_elements": ["OP", "OP", "OP", "OP", "OP", "OP"],
                "transmittance_U_elements": np.array(
                    [U_EXT_WALL, U_INT_WALL, U_INT_WALL, U_INT_WALL, U_INT_SLAB, U_INT_SLAB]
                ),
                "orientation_elements": np.array(["WV", "NV", "EV", "SV", "HOR", "HOR"]),
                "volume": VOLUME,
                "building_type_class": "Residential_apartment",
                "a_use": FLOOR_AREA,
                "conditioned": True,
                "setpoint": ADJ_SETPOINT,
            },
            {
                "name": "apt_north",
                "orientation_zone": {"azimuth": 0.0},
                "area_facade_elements": np.array(
                    [A_WEST_GROSS, A_NORTH_GROSS, A_EAST_GROSS, A_SOUTH_GROSS, FLOOR_AREA, FLOOR_AREA]
                ),
                "typology_elements": ["OP", "OP", "OP", "OP", "OP", "OP"],
                "transmittance_U_elements": np.array(
                    [U_INT_WALL, U_INT_WALL, U_INT_WALL, U_INT_WALL, U_INT_SLAB, U_INT_SLAB]
                ),
                "orientation_elements": np.array(["WV", "NV", "EV", "SV", "HOR", "HOR"]),
                "volume": VOLUME,
                "building_type_class": "Residential_apartment",
                "a_use": FLOOR_AREA,
                "conditioned": True,
                "setpoint": ADJ_SETPOINT,
            },
            {
                "name": "apt_south",
                "orientation_zone": {"azimuth": 180.0},
                "area_facade_elements": np.array(
                    [A_WEST_GROSS, A_NORTH_GROSS, A_EAST_GROSS, A_SOUTH_GROSS, FLOOR_AREA, FLOOR_AREA]
                ),
                "typology_elements": ["OP", "OP", "OP", "OP", "OP", "OP"],
                "transmittance_U_elements": np.array(
                    [U_INT_WALL, U_INT_WALL, U_INT_WALL, U_INT_WALL, U_INT_SLAB, U_INT_SLAB]
                ),
                "orientation_elements": np.array(["WV", "NV", "EV", "SV", "HOR", "HOR"]),
                "volume": VOLUME,
                "building_type_class": "Residential_apartment",
                "a_use": FLOOR_AREA,
                "conditioned": True,
                "setpoint": ADJ_SETPOINT,
            },
            {
                "name": "corridor",
                "orientation_zone": {"azimuth": 90.0},
                "area_facade_elements": np.array([81.0, 5.4, 81.0, 5.4, 60.0, 60.0]),
                "typology_elements": ["OP", "OP", "OP", "OP", "OP", "OP"],
                "transmittance_U_elements": np.array([U_INT_WALL] * 6),
                "orientation_elements": np.array(["WV", "NV", "EV", "SV", "HOR", "HOR"]),
                "volume": 162.0,
                "building_type_class": "Residential_apartment",
                "a_use": 60.0,
                # See ADJ_SETPOINT: the corridor is assumed tempered, NOT verified
                # against the building's actual services.
                "conditioned": True,
                "setpoint": ADJ_SETPOINT,
            },
        ],
        "building_surface": [
            {
                "name": "West exterior wall (opaque)", "type": "opaque", "area": A_WEST_OPAQUE,
                "sky_view_factor": 0.5, "u_value": U_EXT_WALL, "solar_absorptance": ABS_EXT_WALL,
                "thermal_capacity": C_EXT_WALL, "orientation": {"azimuth": 270.0, "tilt": 90.0},
                "name_adj_zone": None, "height": HEIGHT, "length": LEN_NS,
            },
            {
                "name": "North wall to Apt 306", "type": "adjacent", "area": A_NORTH_GROSS,
                "sky_view_factor": 0.0, "u_value": U_INT_WALL, "solar_absorptance": ABS_INT,
                "thermal_capacity": C_INT_WALL, "orientation": {"azimuth": 0.0, "tilt": 90.0},
                "name_adj_zone": "apt_north", "height": HEIGHT, "length": LEN_EW,
            },
            {
                "name": "South wall to Apt 304", "type": "adjacent", "area": A_SOUTH_GROSS,
                "sky_view_factor": 0.0, "u_value": U_INT_WALL, "solar_absorptance": ABS_INT,
                "thermal_capacity": C_INT_WALL, "orientation": {"azimuth": 180.0, "tilt": 90.0},
                "name_adj_zone": "apt_south", "height": HEIGHT, "length": LEN_EW,
            },
            {
                "name": "East wall to corridor", "type": "adjacent", "area": A_EAST_GROSS,
                "sky_view_factor": 0.0, "u_value": U_INT_WALL, "solar_absorptance": ABS_INT,
                "thermal_capacity": C_INT_WALL, "orientation": {"azimuth": 90.0, "tilt": 90.0},
                "name_adj_zone": "corridor", "height": HEIGHT, "length": LEN_NS,
            },
            {
                "name": "Floor to Apt 205", "type": "adjacent", "area": FLOOR_AREA,
                "sky_view_factor": 0.0, "u_value": U_INT_SLAB, "solar_absorptance": ABS_INT,
                "thermal_capacity": C_INT_SLAB, "orientation": {"azimuth": 0.0, "tilt": 0.0},
                "name_adj_zone": "apt_below", "height": LEN_NS, "length": LEN_EW,
            },
            {
                "name": "Ceiling to Apt 405", "type": "adjacent", "area": FLOOR_AREA,
                "sky_view_factor": 0.0, "u_value": U_INT_SLAB, "solar_absorptance": ABS_INT,
                "thermal_capacity": C_INT_SLAB, "orientation": {"azimuth": 0.0, "tilt": 0.0},
                "name_adj_zone": "apt_above", "height": LEN_NS, "length": LEN_EW,
            },
            {
                "name": "West window - fixed", "type": "transparent", "area": A_WINDOW_FIXED,
                "sky_view_factor": 0.5, "u_value": U_WINDOW, "solar_absorptance": 0.5,
                "thermal_capacity": C_WINDOW, "orientation": {"azimuth": 270.0, "tilt": 90.0},
                "name_adj_zone": None, "height": WIN_HEIGHT_FIXED, "g_value": G_WINDOW,
                "width": WIN_WIDTH_FIXED, "parapet": 1.0, "shading": True,
                "shading_type": "horizontal_overhang", "width_or_distance_of_shading_elements": 0.05,
                "overhang_proprieties": {"width_of_horizontal_overhangs": 0.25},
            },
            {
                "name": "West window - operable", "type": "transparent", "area": A_WINDOW_OPERABLE,
                "sky_view_factor": 0.5, "u_value": U_WINDOW, "solar_absorptance": 0.5,
                "thermal_capacity": C_WINDOW, "orientation": {"azimuth": 270.0, "tilt": 90.0},
                "name_adj_zone": None, "height": WIN_HEIGHT_OPERABLE, "g_value": G_WINDOW,
                "width": WIN_WIDTH_OPERABLE, "parapet": 1.0, "shading": True,
                "shading_type": "horizontal_overhang", "width_or_distance_of_shading_elements": 0.05,
                "overhang_proprieties": {"width_of_horizontal_overhangs": 0.25},
            },
        ],
        "units": {
            "area": "m²", "u_value": "W/m²K", "thermal_capacity": "J/m²K",
            "azimuth": "degrees (0=N, 90=E, 180=S, 270=W)",
            "tilt": "degrees (0=horizontal, 90=vertical)",
            "internal_gain": "W/m²", "HVAC_profile": "0: off, 1: on",
        },
        "building_parameters": {
            "temperature_setpoints": {
                "heating_setpoint": 18.0,
                "heating_setback": 15.0,
                "cooling_setpoint": 26.0,
                "cooling_setback": 28.0,
                "units": "°C",
            },
            "system_capacities": {
                "heating_capacity": 10_000_000.0,
                "cooling_capacity": 10_000_000.0,
                "units": "W",
            },
            "ventilation": {
                "ventilation_type": "occupancy",
                "flow_rate_per_person": 2.0,
                "units": "l/(s m²)",
                "custom_heat_transfer_coefficient_ventilation": None,
            },
            "internal_gains": [
                {
                    "name": "occupants", "full_load": 8.0,
                    "weekday": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.4, 0.5,
                                0.5, 0.5, 0.4, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0],
                    "weekend": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.8, 0.7, 0.7,
                                0.7, 0.7, 0.5, 0.5, 0.7, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                },
                {
                    "name": "appliances", "full_load": 5.0,
                    "weekday": [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.3, 0.2, 0.2, 0.2, 0.2,
                                0.3, 0.2, 0.2, 0.2, 0.2, 0.3, 0.3, 0.4, 1.0, 0.6, 0.4, 0.2],
                    "weekend": [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.3, 0.4, 0.3, 0.3,
                                0.4, 0.3, 0.3, 0.3, 0.3, 0.4, 0.4, 0.5, 1.0, 0.6, 0.4, 0.2],
                },
                {
                    "name": "lighting", "full_load": 3.0,
                    "weekday": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.3, 0.1, 0.0, 0.0, 0.0,
                                0.0, 0.0, 0.0, 0.0, 0.1, 0.5, 0.8, 0.8, 0.8, 0.7, 0.4, 0.1],
                    "weekend": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.3, 0.3, 0.2, 0.2,
                                0.2, 0.2, 0.2, 0.2, 0.3, 0.5, 0.8, 0.8, 0.8, 0.7, 0.4, 0.1],
                },
            ],
            "construction": {
                "wall_thickness": 0.20,
                "thermal_bridges": 1.5,
                "units": "m (thickness), W/mK (thermal bridges)",
            },
            "climate_parameters": {"coldest_month": 7, "units": "1-12 (January-December)"},
            "heating_profile": {
                "weekday": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0],
                "weekend": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0],
            },
            "cooling_profile": {
                "weekday": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0],
                "weekend": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0,
                            1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0],
            },
            "ventilation_profile": {
                "weekday": [1.0] * 24,
                "weekend": [1.0] * 24,
            },
        },
    }
    return bui


if __name__ == "__main__":
    b = build_bui()
    print(f"Building     : {b['building']['name']}")
    print(f"Floor area   : {b['building']['net_floor_area']} m2")
    print(f"Surfaces     : {len(b['building_surface'])} "
          f"({sum(1 for s in b['building_surface'] if s['type'] == 'transparent')} transparent)")
    print(f"Window area  : {A_WINDOW_TOTAL:.2f} m2 west-facing, U={U_WINDOW}, g={G_WINDOW}")
    print(f"Adjacent zones: {len(b['adjacent_zones'])}")
