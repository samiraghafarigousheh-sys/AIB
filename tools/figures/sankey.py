"""
Shared Sankey renderer for F2 (baseline balance) and F5 (corrected-state balance).

Both figures come out of this one function, at one fixed kWh-per-unit-height
scale, with one fixed band order and one fixed colour map. The two can therefore
be read side by side: any difference between them is the model, not the drawing.

Ribbon pairings are PROPORTIONAL, not traced. ISO 52016-1 is a node network and
does not attribute a given gain to a given loss, so the ribbon from input i to
output j is drawn at in_i * out_j / total -- the only allocation that conserves
both ends without inventing an attribution the method does not make.

The closure residual is never folded into a transmission line item. Where the
balance does not close, the shortfall is drawn on the side that is short, as its
own hatched, unfilled, red-edged band that emits no ribbon at all: a dead end,
which is what an unaccounted term is.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch, Rectangle

import figstyle as F

# One scale for both figures: the baseline's larger column fills the frame, and
# the corrected state is drawn at the same kWh per unit height.
SHARED_FULL_SCALE_KWH = 8402.3
COL_TOP = 0.980
COL_SPAN = 0.695          # height, in axes units, of SHARED_FULL_SCALE_KWH

X_IN = (0.313, 0.353)
X_OUT = (0.647, 0.687)
ELBOW = 0.050
LABEL_LO = 0.205          # labels stay above the callout strip
GAP_PAD_KWH = 26.0        # blank gap between stacked bands, in kWh-equivalent

RESIDUAL_LABEL = "Unaccounted (residual)"


def _h(kwh: float) -> float:
    return COL_SPAN * kwh / SHARED_FULL_SCALE_KWH


def _ribbon(ax, x0, x1, y0a, y0b, y1a, y1b, color, alpha):
    cx0 = x0 + 0.42 * (x1 - x0)
    cx1 = x0 + 0.58 * (x1 - x0)
    verts = [
        (x0, y0a),
        (cx0, y0a), (cx1, y1a), (x1, y1a),
        (x1, y1b),
        (cx1, y1b), (cx0, y0b), (x0, y0b),
        (x0, y0a),
    ]
    codes = [
        MPath.MOVETO,
        MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
        MPath.LINETO,
        MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
        MPath.CLOSEPOLY,
    ]
    ax.add_patch(PathPatch(MPath(verts, codes), facecolor=color,
                           edgecolor="none", alpha=alpha, zorder=1))


def _place_labels(centres: list[float], min_gap: float, lo: float, hi: float) -> list[float]:
    """Push label anchors apart so thin bands still get a readable, ordered label."""
    ys = list(centres)
    order = sorted(range(len(ys)), key=lambda i: -ys[i])   # top to bottom
    prev = hi
    for i in order:
        ys[i] = min(ys[i], prev - min_gap)
        prev = ys[i]
    prev = lo
    for i in reversed(order):
        ys[i] = max(ys[i], prev + min_gap)
        prev = ys[i]
    return ys


def draw(sankey: dict, *, fig_id: str, title: str, subtitle: str,
         callouts: list[dict], footer: str, scale_note: str,
         ghost: tuple[float, str] | None = None) -> plt.Figure:
    inputs = {k: sankey["inputs_Wh"][k] / 1000.0 for k in F.SANKEY_INPUT_ORDER}
    outputs = {k: sankey["outputs_Wh"][k] / 1000.0 for k in F.SANKEY_OUTPUT_ORDER}

    unknown = (set(sankey["inputs_Wh"]) - set(inputs)) | (set(sankey["outputs_Wh"]) - set(outputs))
    if unknown:
        raise F.MissingQuantity(
            f"{fig_id}: the balance carries terms the figure does not draw: {sorted(unknown)}")
    if sankey["republished_residual_Wh"] != 0.0:
        raise F.MissingQuantity(
            f"{fig_id}: the source re-publishes the residual as a flow "
            f"({sankey['republished_residual_Wh']} Wh); the figure will not draw that.")
    if sankey["n_transmission_items"] != 7:
        raise F.MissingQuantity(
            f"{fig_id}: expected 7 resolved transmission line items, "
            f"found {sankey['n_transmission_items']}")

    in_total = sum(inputs.values())
    out_total = sum(outputs.values())
    residual = in_total - out_total        # negative => outputs exceed inputs
    gap = max(0.0, -residual)              # the input side is short by this much

    in_bands = list(inputs.items())
    if gap > 0.5:
        in_bands.append((RESIDUAL_LABEL, gap))

    fig, ax = plt.subplots(figsize=(11.6, 8.6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.grid(False)

    # ---- ghost: how far the columns of the companion figure reached ------
    if ghost is not None:
        g_kwh, g_label = ghost
        g_bottom = COL_TOP - _h(g_kwh)
        for xr in (X_IN, X_OUT):
            ax.add_patch(Rectangle(
                (xr[0], g_bottom), xr[1] - xr[0], _h(g_kwh),
                facecolor="none", edgecolor="#A8A8A8", linestyle=(0, (4, 3)),
                linewidth=0.9, zorder=0,
            ))
        ax.text((X_IN[1] + X_OUT[0]) / 2, g_bottom - 0.020, g_label,
                ha="center", va="top", fontsize=7.8, color="#7A7A7A",
                style="italic", linespacing=1.35)

    pad = _h(GAP_PAD_KWH)

    def stack(bands):
        out, y = [], COL_TOP
        for name, kwh in bands:
            h = _h(kwh)
            out.append((name, kwh, y - h, y))
            y -= h + pad
        return out

    in_stack = stack(in_bands)
    out_stack = stack(list(outputs.items()))

    # ---- ribbons: proportional allocation, and none at all from the gap ----
    src_cursor = {name: top for name, _, _, top in in_stack}
    dst_cursor = {name: top for name, _, _, top in out_stack}
    total = sum(kwh for _, kwh in in_bands)

    for s_name, s_kwh in in_bands:
        if s_name == RESIDUAL_LABEL:
            continue                      # a dead end: the gap emits nothing
        for d_name, d_kwh in outputs.items():
            flow = s_kwh * d_kwh / total
            if flow <= 0:
                continue
            fh = _h(flow)
            y0a, y0b = src_cursor[s_name], src_cursor[s_name] - fh
            y1a, y1b = dst_cursor[d_name], dst_cursor[d_name] - fh
            src_cursor[s_name] -= fh
            dst_cursor[d_name] -= fh
            _ribbon(ax, X_IN[1], X_OUT[0], y0a, y0b, y1a, y1b,
                    F.SANKEY_INPUT_COLOR[s_name], 0.45)

    # ---- bands -----------------------------------------------------------
    def band(x, y0, y1, color, hatch=None, edge=None):
        ax.add_patch(Rectangle(
            (x[0], y0), x[1] - x[0], max(y1 - y0, 0.0015),
            facecolor="none" if hatch else color,
            edgecolor=edge if edge else "white",
            hatch=hatch, linewidth=1.1 if edge else 0.5, zorder=3,
        ))

    for name, kwh, y0, y1 in in_stack:
        if name == RESIDUAL_LABEL:
            band(X_IN, y0, y1, None, hatch="/////", edge=F.RESIDUAL_COLOR)
        else:
            band(X_IN, y0, y1, F.SANKEY_INPUT_COLOR[name])
    for name, kwh, y0, y1 in out_stack:
        band(X_OUT, y0, y1, F.SANKEY_OUTPUT_COLOR[name])

    # ---- labels with leader lines ----------------------------------------
    def label_side(stack_, x_edge, side, shortfn, denom, min_gap):
        sign = -1 if side == "left" else 1
        centres = [(y0 + y1) / 2 for _, _, y0, y1 in stack_]
        anchors = _place_labels(centres, min_gap=min_gap, lo=LABEL_LO, hi=COL_TOP)
        for (name, kwh, y0, y1), ay in zip(stack_, anchors):
            cy = (y0 + y1) / 2
            xa = x_edge + sign * 0.016
            xb = x_edge + sign * ELBOW
            is_gap = name == RESIDUAL_LABEL
            lc = F.RESIDUAL_COLOR if is_gap else "#9A9A9A"
            ax.plot([x_edge, xa, xb], [cy, ay, ay], color=lc,
                    lw=1.0 if is_gap else 0.8, zorder=4, solid_capstyle="round")
            if is_gap:
                txt = (f"{RESIDUAL_LABEL}\n{gap:,.1f} kWh "
                       f"({100.0 * residual / in_total:+.2f} % of inputs)\n"
                       "— emits nothing: a dead end")
            else:
                txt = f"{shortfn(name)}\n{kwh:,.1f} kWh  ({100.0 * kwh / denom:.1f} %)"
            ax.text(
                xb + sign * 0.010, ay, txt,
                ha="right" if side == "left" else "left", va="center",
                fontsize=8.0, linespacing=1.35, zorder=5,
                color=F.RESIDUAL_COLOR if is_gap else F.INK,
                fontweight="bold" if is_gap else "normal",
            )

    label_side(in_stack, X_IN[0], "left", lambda n: n, in_total, 0.062)
    label_side(out_stack, X_OUT[1], "right", lambda n: F.SANKEY_SHORT[n], out_total, 0.044)

    # ---- column headers ---------------------------------------------------
    ax.text((X_IN[0] + X_IN[1]) / 2, COL_TOP + 0.012,
            f"INPUTS   {in_total:,.1f} kWh", ha="center", va="bottom",
            fontsize=9.5, fontweight="bold", color=F.INK)
    ax.text((X_OUT[0] + X_OUT[1]) / 2, COL_TOP + 0.012,
            f"OUTPUTS   {out_total:,.1f} kWh", ha="center", va="bottom",
            fontsize=9.5, fontweight="bold", color=F.INK)

    # ---- shared scale bar --------------------------------------------------
    bar_kwh = 2000.0
    bx, by = 0.030, COL_TOP - _h(bar_kwh) - 0.02
    ax.plot([bx, bx], [by, by + _h(bar_kwh)], color=F.INK, lw=1.8,
            solid_capstyle="butt", zorder=5)
    for yy in (by, by + _h(bar_kwh)):
        ax.plot([bx - 0.009, bx + 0.009], [yy, yy], color=F.INK, lw=1.3, zorder=5)
    ax.text(bx + 0.016, by + _h(bar_kwh) / 2,
            f"{bar_kwh:,.0f} kWh\n\n{scale_note}",
            ha="left", va="center", fontsize=7.6, color=F.INK, linespacing=1.35)

    # ---- callout strip along the bottom ------------------------------------
    for c in callouts:
        ax.annotate(
            c["text"], xy=c["xy"], xycoords="axes fraction",
            ha=c.get("ha", "center"), va=c.get("va", "top"),
            fontsize=c.get("fontsize", 8.2), color=F.INK, linespacing=1.45,
            bbox=dict(boxstyle="round,pad=0.55", facecolor=c.get("fc", "#F2F6FA"),
                      edgecolor=c.get("ec", "#7FA6C4"), linewidth=0.9),
            zorder=6,
        )

    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.997)
    fig.text(0.5, 0.968, subtitle, ha="center", va="top", fontsize=8.3,
             color="#4D4D4D", linespacing=1.4)
    fig.text(0.5, 0.010, footer, ha="center", va="bottom", fontsize=7.6,
             color="#4D4D4D", linespacing=1.4)
    fig.subplots_adjust(left=0.005, right=0.995, top=0.910, bottom=0.050)
    return fig
