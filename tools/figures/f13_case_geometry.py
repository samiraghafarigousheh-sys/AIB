"""
F13 -- the case-study geometry, and why the adjacent-zone treatment dominates.

No simulation data. This is a drawing, and its only job is to make one claim
immediate: 88.6 % of the envelope conductance faces conditioned neighbours, and
only 13.50 m² of the 88.60 m² envelope sees outdoor air at all. That is why
marking the five party surfaces ``conditioned`` moves heating by 4,018 kWh --
the largest single correction in the paper.

Areas, U-values, orientations and adjacencies are read from
``examples/apt305_building.py`` -- the same dictionary the engine is run on --
rather than restated here, so the drawing cannot drift away from the simulated
case. The conductance share is recomputed from those areas and U-values and
asserted against the 88.6 % the paper states.

Left panel: an axonometric of the box, with the five party surfaces and the one
exposed facade labelled by area and by what lies beyond them. Right panel: the
same six surfaces as area and as conductance, which is where the asymmetry
actually lives -- the west facade is 15 % of the envelope by area but only 11 %
of it by UA.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon

import figstyle as F

EXPOSED_COLOR = "#D55E00"     # Okabe-Ito vermillion: the one outdoor-exposed facade
GLAZING_COLOR = "#56B4E9"     # Okabe-Ito sky blue: the glazing in it
PARTY_COLOR = "#009E73"       # Okabe-Ito bluish green: the five conditioned neighbours
PARTY_FACE = "#CFE9E0"

EXPECTED_PARTY_UA_SHARE = 88.6      # per cent, as the paper states it
EXPECTED_HEATING_MOVE_KWH = -4018.18  # +Conditioned zones step, F4 / the trajectory

# What lies beyond each party surface, for the labels. Keyed by the surface name
# in the building dictionary, so a rename fails loudly rather than mislabelling.
BEYOND = {
    "North wall to Apt 306": "Apt 306",
    "South wall to Apt 304": "Apt 304",
    "East wall to corridor": "corridor",
    "Floor to Apt 205": "Apt 205",
    "Ceiling to Apt 405": "Apt 405",
}

# Axonometric projection: x east, y north, z up, drawn with a simple oblique cast.
AX_DX, AX_DY = 0.52, 0.30


def _project(x, y, z):
    return x + AX_DY * y, z + AX_DX * y


def _face(ax, corners, facecolor, edgecolor, alpha=1.0, lw=1.2, zorder=2, hatch=None):
    pts = [_project(*c) for c in corners]
    ax.add_patch(Polygon(pts, closed=True, facecolor=facecolor, edgecolor=edgecolor,
                         alpha=alpha, linewidth=lw, zorder=zorder, hatch=hatch))
    return np.array(pts)


def _centroid(corners):
    pts = np.array([_project(*c) for c in corners])
    return pts.mean(axis=0)


def _axonometric(ax, geom) -> None:
    w = geom["len_ew"]      # east-west depth, 4.0 m
    d = geom["len_ns"]      # north-south length, 5.0 m (the west facade's width)
    h = geom["height"]      # 2.7 m

    by_name = {s["name"]: s for s in geom["party"] + geom["exposed"]}

    def area(name):
        return by_name[name]["area"]

    def uval(name):
        return by_name[name]["u_value"]

    # x = 0 is the west facade; y runs south (0) to north (d); z runs up.
    floor = [(0, 0, 0), (w, 0, 0), (w, d, 0), (0, d, 0)]
    ceiling = [(0, 0, h), (w, 0, h), (w, d, h), (0, d, h)]
    west = [(0, 0, 0), (0, d, 0), (0, d, h), (0, 0, h)]
    east = [(w, 0, 0), (w, d, 0), (w, d, h), (w, 0, h)]
    south = [(0, 0, 0), (w, 0, 0), (w, 0, h), (0, 0, h)]
    north = [(0, d, 0), (w, d, 0), (w, d, h), (0, d, h)]

    # Party surfaces first, so the exposed facade draws over them.
    for corners, name in ((floor, "Floor to Apt 205"),
                          (east, "East wall to corridor"),
                          (north, "North wall to Apt 306"),
                          (south, "South wall to Apt 304"),
                          (ceiling, "Ceiling to Apt 405")):
        _face(ax, corners, PARTY_FACE, PARTY_COLOR, alpha=0.72, lw=1.1, zorder=2)

    # The one outdoor-exposed facade, and its glazing.
    _face(ax, west, EXPOSED_COLOR, EXPOSED_COLOR, alpha=0.30, lw=1.8, zorder=4)
    win_w, win_h = 0.9, 0.9
    for y0 in (d / 2 - 1.15, d / 2 + 0.25):
        _face(ax, [(0, y0, 0.9), (0, y0 + win_w, 0.9),
                   (0, y0 + win_w, 0.9 + win_h), (0, y0, 0.9 + win_h)],
              GLAZING_COLOR, "#1F6F9B", alpha=0.85, lw=1.0, zorder=5)

    labels = [
        (ceiling, "Ceiling to Apt 405", (0.55, 1.95), "center", "bottom"),
        (north, "North wall to Apt 306", (1.55, 0.55), "left", "center"),
        (east, "East wall to corridor", (1.25, -0.75), "left", "center"),
        (south, "South wall to Apt 304", (1.30, -2.05), "center", "top"),
        (floor, "Floor to Apt 205", (-2.30, -1.55), "right", "center"),
    ]
    for corners, name, (ox, oy), ha, va in labels:
        cx, cy = _centroid(corners)
        ax.annotate(
            f"{name.split(' to ')[0].split(' wall')[0]}\n"
            f"{area(name):.2f} m²  ·  U {uval(name):.2f}\n"
            f"→ {BEYOND[name]} at {geom['adj_setpoint']:.0f} °C",
            xy=(cx, cy), xytext=(cx + ox, cy + oy), ha=ha, va=va,
            fontsize=7.0, color="#00654A", linespacing=1.4,
            arrowprops=dict(arrowstyle="-", color=PARTY_COLOR, lw=0.8,
                            shrinkA=0, shrinkB=2),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor=PARTY_COLOR, linewidth=0.7, alpha=0.95),
        )

    wx, wy = _centroid(west)
    ax.annotate(
        f"West exterior wall (opaque)\n"
        f"{area('West exterior wall (opaque)'):.2f} m²  ·  U "
        f"{uval('West exterior wall (opaque)'):.2f}\n"
        f"→ outdoor air  ·  α = 0.75\n"
        f"West windows {geom['area_exposed'] - area('West exterior wall (opaque)'):.2f} m²  ·  "
        f"U 5.40, g 0.65",
        xy=(wx, wy), xytext=(wx - 3.15, wy + 2.05), ha="center", va="bottom",
        fontsize=7.2, color="#8A3D00", linespacing=1.45, fontweight="bold",
        arrowprops=dict(arrowstyle="-", color=EXPOSED_COLOR, lw=1.0,
                        shrinkA=0, shrinkB=2),
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#FDF1E7",
                  edgecolor=EXPOSED_COLOR, linewidth=1.0),
    )

    ax.text(0.5, 0.005,
            f"Level {geom['floor_level']} of a mid-rise apartment block; "
            f"{geom['len_ns']:.0f} × {geom['len_ew']:.0f} × {geom['height']:.1f} m, "
            f"{geom['floor_area']:.0f} m² net floor area. The exposed facade faces "
            f"270° (west).\nAxonometric, schematic in depth.",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=7.2,
            color="#4D4D4D", linespacing=1.4)

    ax.set_xlim(-6.6, 9.2)
    ax.set_ylim(-4.6, 9.2)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("A  The envelope: one exposed facade, five party surfaces",
                 pad=10, loc="left")


def _bars(ax, geom) -> None:
    items = ([(s["name"], s["area"], s["area"] * s["u_value"], PARTY_COLOR)
              for s in geom["party"]]
             + [("West facade (opaque + glazing)", geom["area_exposed"],
                 geom["UA_exposed"], EXPOSED_COLOR)])
    items.sort(key=lambda r: r[2])

    y = np.arange(len(items), dtype=float)
    areas = np.array([r[1] for r in items])
    uas = np.array([r[2] for r in items])
    colours = [r[3] for r in items]
    total_area = geom["area_exposed"] + geom["area_party"]
    total_ua = geom["UA_exposed"] + geom["UA_party"]

    hgt = 0.36
    ax.barh(y + hgt / 2, 100 * areas / total_area, hgt, color=colours, alpha=0.42,
            edgecolor="white", linewidth=0.5, label="Share of envelope AREA")
    ax.barh(y - hgt / 2, 100 * uas / total_ua, hgt, color=colours,
            edgecolor="white", linewidth=0.5, label="Share of envelope CONDUCTANCE (UA)")

    for i, (name, a, ua, _) in enumerate(items):
        ax.annotate(f"{100 * a / total_area:.1f} %  ({a:.2f} m²)",
                    (100 * a / total_area, y[i] + hgt / 2), xytext=(-5, 0),
                    textcoords="offset points", ha="right", va="center",
                    fontsize=7.0, color=F.INK)
        ax.annotate(f"{100 * ua / total_ua:.1f} %  ({ua:.2f} W/K)",
                    (100 * ua / total_ua, y[i] - hgt / 2), xytext=(-5, 0),
                    textcoords="offset points", ha="right", va="center",
                    fontsize=7.0, fontweight="bold", color="white")

    ax.set_yticks(y)
    ax.set_yticklabels([r[0].replace(" to ", "\n→ ") for r in items])
    ax.set_xlim(0, 30)
    ax.set_xlabel("Share of the 88.60 m² envelope (%)")
    # Value labels sit inside the bars, so the right of the panel is free.
    ax.legend(loc="lower right", ncol=1, fontsize=7.2, framealpha=0.96)
    ax.set_title("B  Where the envelope conductance is", pad=10, loc="left")


def build() -> dict:
    geom = F.load_geometry()

    if abs(geom["party_UA_share_pct"] - EXPECTED_PARTY_UA_SHARE) >= 0.05:
        raise F.MissingQuantity(
            f"party surfaces carry {geom['party_UA_share_pct']:.2f} % of the envelope "
            f"conductance; the paper states {EXPECTED_PARTY_UA_SHARE} %"
        )
    for name in BEYOND:
        if name not in {s["name"] for s in geom["party"]}:
            raise F.MissingQuantity(
                f"the building dictionary no longer has a party surface named {name!r}; "
                "F13's labels would be wrong"
            )
    if abs(geom["area_party"] - 75.10) >= 0.005 or abs(geom["area_exposed"] - 13.50) >= 0.005:
        raise F.MissingQuantity(
            f"envelope areas moved: party {geom['area_party']:.2f} m² (paper 75.10), "
            f"exposed {geom['area_exposed']:.2f} m² (paper 13.50)"
        )

    fig, (axa, axb) = plt.subplots(
        1, 2, figsize=(13.2, 7.2), gridspec_kw={"width_ratios": [1.32, 1.0]})
    fig.subplots_adjust(left=0.005, right=0.978, top=0.782, bottom=0.215, wspace=0.24)

    _axonometric(axa, geom)
    _bars(axb, geom)

    fig.text(
        0.5, 0.985,
        "F13 — Apt 305: one exposed facade, five conditioned neighbours\n"
        f"{geom['party_UA_share_pct']:.1f} % of the envelope conductance faces "
        "conditioned space, which is why the adjacent-zone treatment is the "
        "largest single correction",
        ha="center", va="top", fontsize=11.5, fontweight="bold", linespacing=1.45,
    )
    fig.text(
        0.5, 0.895,
        "Areas, U-values and adjacencies are read from `examples/apt305_building.py`, the same "
        "building dictionary the engine is run on. No simulation data.",
        ha="center", va="top", fontsize=7.8, color="#4D4D4D",
    )

    fig.text(
        0.5, 0.140,
        "$\\bf{Why\\ this\\ geometry\\ decides\\ the\\ result.}$  Typed as unconditioned "
        "buffers, the five party surfaces are driven through the ISO 13789 buffer "
        f"expression and track outdoor air. Held at {geom['adj_setpoint']:.0f} °C instead, "
        f"they see a {geom['adj_setpoint']:.0f} °C boundary\n"
        f"across {geom['party_UA_share_pct']:.1f} % of the envelope conductance. That single "
        f"change moves annual sensible heating by {EXPECTED_HEATING_MOVE_KWH:+,.2f} kWh — "
        "larger than every other correction in the paper combined, and a consequence\n"
        "of the geometry rather than of the method.  "
        f"$\\bf{{Area\\ is\\ not\\ the\\ measure.}}$  The five party surfaces are "
        f"{100 * geom['area_party'] / (geom['area_party'] + geom['area_exposed']):.1f} % of the "
        f"envelope by area but {geom['party_UA_share_pct']:.1f} % of it by conductance; "
        f"the west facade is "
        f"{100 * geom['area_exposed'] / (geom['area_party'] + geom['area_exposed']):.1f} % "
        f"by area and only "
        f"{100 * geom['UA_exposed'] / (geom['UA_party'] + geom['UA_exposed']):.1f} % by UA.",
        ha="center", va="top", fontsize=8.0, color=F.INK, linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#FFF7E6",
                  edgecolor="#E69F00", linewidth=0.9),
    )

    files = F.save(fig, "F13_case_geometry")

    total_area = geom["area_exposed"] + geom["area_party"]
    total_ua = geom["UA_exposed"] + geom["UA_party"]
    numbers = [
        f"West exterior wall (opaque) 11.88 m², U 1.00 W/m²K; west windows 1.62 m², "
        f"U 5.40, g 0.65 — {geom['area_exposed']:.2f} m² outdoor-exposed in total",
    ]
    numbers += [
        f"{s['name']}: {s['area']:.2f} m², U {s['u_value']:.2f} W/m²K → "
        f"{BEYOND[s['name']]} at {geom['adj_setpoint']:.0f} °C"
        for s in geom["party"]
    ]
    numbers += [
        f"Five party surfaces {geom['area_party']:.2f} m² = "
        f"{100 * geom['area_party'] / total_area:.1f} % of the {total_area:.2f} m² envelope "
        f"by area, {geom['UA_party']:.2f} of {total_ua:.3f} W/K = "
        f"{geom['party_UA_share_pct']:.1f} % by conductance",
        f"West facade {100 * geom['area_exposed'] / total_area:.1f} % by area against "
        f"{100 * geom['UA_exposed'] / total_ua:.1f} % by conductance",
        f"Level {geom['floor_level']}, {geom['len_ns']:.0f} × {geom['len_ew']:.0f} × "
        f"{geom['height']:.1f} m, {geom['floor_area']:.0f} m² net floor area",
        f"The +Conditioned zones step moves sensible heating by "
        f"{EXPECTED_HEATING_MOVE_KWH:+,.2f} kWh (F4, the trajectory)",
    ]

    return {
        "id": "F13",
        "title": "The case-study geometry",
        "files": files,
        "sources": [
            "examples/apt305_building.py (areas, U-values, orientations, adjacent zones, site)",
            "results/paper/trajectory_v2/trajectory_raw.json (+Conditioned zones step, quoted in the caption)",
        ],
        "numbers": numbers,
        "note": (
            "**A drawing, not a plot** — no simulation output is read. Every dimension, area, "
            "U-value and adjacency is taken from the building dictionary the engine is run on, "
            "so the figure cannot drift away from the simulated case: renaming a party surface "
            "or changing an area raises `figstyle.MissingQuantity` rather than mislabelling a "
            "face. The 88.6 % conductance share is recomputed from those areas and U-values and "
            "asserted against the figure the paper states.\n\n"
            "The axonometric is schematic in depth and says so on the panel. It replaces the "
            "photograph placeholder in the manuscript, so it does not consume a new figure slot; "
            "if the photograph is retained instead, this figure is the first of the three new "
            "ones to drop."
        ),
        "placement": "main-if-budget",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build())
