"""F8 -- The latent gate."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

import figstyle as F

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SUMMER = {0, 1, 11}          # Dec-Feb, the austral summer
WINTER = {5, 6, 7}           # Jun-Aug

# The audit axis: full scale is 0.001 kWh, under 0.1 % of the canonical gated
# total, so a leak of even a thousandth of the annual charge would be off-scale.
AUDIT_FULL_SCALE_KWH = 1.0e-3


def build() -> dict:
    traj = F.load_trajectory()
    st = traj["states"]
    gated = [st[s]["Q_C_lat_gated"] for s in F.STATES]
    ungated = [st[s]["Q_C_lat_ungated"] for s in F.STATES]
    can = st[F.CANONICAL_STATE]
    can_i = F.STATES.index(F.CANONICAL_STATE)

    removed_pct = 100.0 * (1.0 - can["Q_C_lat_gated"] / can["Q_C_lat_ungated"])
    # 99.75 % at the +Wind profile canonical state: 1.5091 kWh gated of 597.86 kWh
    # ungated. The previous published value was 99.81 % at +Closure fixes
    # (1.1396 of 600.11). The gate moved because the wind profile raises the
    # cooling load, and with it the hours the plant runs and so the hours latent
    # is charged in -- the gate itself is unchanged. The claim is now 99.7 %, not
    # 99.8 %; retained set at results/paper_pre_wind_profile/.
    if abs(removed_pct - 99.75) > 0.05:
        raise F.MissingQuantity(
            f"F8: the gate removes {removed_pct:.2f} % at the canonical state, "
            "the paper states 99.75 %")

    monthly = can["monthly_latent_cooling_kWh"]
    summer = sum(monthly[i] for i in SUMMER)
    winter = sum(monthly[i] for i in WINTER)
    # 1.30 kWh in Dec-Feb at the +Wind profile canonical state, against 1.07 at
    # +Closure fixes: the same seasonal concentration on a larger gated total.
    # Jun-Aug must stay EXACTLY zero -- that is the gate working, not a
    # measurement, so it keeps a machine-precision tolerance.
    if abs(summer - 1.30) > 0.01 or abs(winter) > 1e-9:
        raise F.MissingQuantity(
            f"F8: Dec–Feb is {summer:.4f} kWh and Jun–Aug is {winter:.4f} kWh, "
            "the paper states 1.30 and 0.00")

    off = [st[s]["latent_kWh_with_cooling_off"] for s in F.STATES]
    while_heat = [st[s]["latent_kWh_while_heating"] for s in F.STATES]
    if any(v != 0.0 for v in off + while_heat):
        raise F.MissingQuantity(
            "F8: the gating audit is not exactly zero on every state — "
            f"plant-off {off}, while-heating {while_heat}")

    fig = plt.figure(figsize=(13.4, 12.6))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.18, 1.0, 1.0], hspace=0.62,
                      left=0.055, right=0.945, top=0.905, bottom=0.055)
    p1 = fig.add_subplot(gs[0])
    p2 = fig.add_subplot(gs[1])
    p3 = fig.add_subplot(gs[2])

    x = np.arange(len(F.STATES))

    # ---- 1. gated against ungated, all thirteen states ----------------------
    p1b = p1.twinx()
    p1b.set_zorder(1)
    p1.set_zorder(2)
    p1.patch.set_visible(False)
    p1b.grid(False)
    p1b.bar(x, ungated, 0.86, color=F.MUTED_FILL, edgecolor="none", zorder=1)
    p1b.set_ylim(0, max(ungated) * 1.85)
    p1b.set_ylabel("Ungated zone moisture balance (kWh)", color="#6E6E6E")
    p1b.tick_params(axis="y", colors="#6E6E6E")

    p1.bar(x, gated, 0.46, color=[F.STATE_COLOR[s] for s in F.STATES],
           edgecolor="white", linewidth=0.5, zorder=3)
    p1.set_ylim(0, max(gated) * 1.85)
    p1.set_ylabel("Gated latent cooling (kWh)")
    p1.set_title("1 — Gated latent cooling against the ungated zone moisture balance, "
                 "all thirteen states", loc="left", pad=7)
    p1.set_xlim(-0.7, len(F.STATES) - 0.3)
    F.state_ticks(p1, rotation=58)
    for t in p1.get_xticklabels():
        t.set_fontsize(7.2)
    F.mark_infiltration_group(p1)
    p1.legend(handles=[
        Patch(facecolor=F.GROUP_BASE["defect"], edgecolor="white",
              label="Gated (left axis)"),
        Patch(facecolor=F.MUTED_FILL, label="Ungated (right axis)"),
    ], loc="upper left", fontsize=7.4)
    p1.annotate(
        "The two series need independent axes: the ungated balance is up to\n"
        f"{max(u / g for u, g in zip(ungated, gated)):.0f}× the gated charge.\n"
        f"At the canonical state the gate removes "
        f"$\\bf{{{can['Q_C_lat_ungated']:,.2f} → {can['Q_C_lat_gated']:.2f}}}$ kWh, "
        f"$\\bf{{{removed_pct:.1f}\\ \\%}}$ of the raw balance.",
        xy=(0.985, 0.965), xycoords="axes fraction", ha="right", va="top",
        fontsize=8.2, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )

    # ---- 2. monthly gated latent at the canonical state ---------------------
    mx = np.arange(12)
    cols = [F.STATE_COLOR[F.CANONICAL_STATE] if i in SUMMER
            else (F.GROUP_BASE["literature"] if i in WINTER else F.MUTED_FILL)
            for i in range(12)]
    p2.bar(mx, monthly, 0.66, color=cols, edgecolor="white", linewidth=0.5, zorder=3)
    p2.set_xticks(mx)
    p2.set_xticklabels(MONTHS)
    p2.set_xlabel("Month")
    p2.set_ylabel("Gated latent cooling (kWh)")
    p2.set_ylim(0, max(monthly) * 1.60)
    p2.set_title("2 — Monthly gated latent cooling at the canonical state: "
                 "the austral-summer phase", loc="left", pad=7)
    for xi, v in zip(mx, monthly):
        p2.annotate(f"{v:.2f}", (xi, v), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7.6, color=F.INK)
    p2.annotate(
        f"$\\bf{{Dec–Feb\\ {summer:.2f}\\ kWh}}$ against "
        f"$\\bf{{Jun–Aug\\ {winter:.2f}\\ kWh}}$.\n"
        f"The load sits in the austral summer, which is the phase check —\n"
        f"the annual total is {sum(monthly):.2f} kWh.",
        xy=(0.985, 0.965), xycoords="axes fraction", ha="right", va="top",
        fontsize=8.2, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )
    p2.legend(handles=[
        Patch(facecolor=F.STATE_COLOR[F.CANONICAL_STATE], label="Dec–Feb (austral summer)"),
        Patch(facecolor=F.GROUP_BASE["literature"], label="Jun–Aug (austral winter)"),
        Patch(facecolor=F.MUTED_FILL, label="shoulder months"),
    ], loc="upper left", fontsize=7.4)

    # ---- 3. the gating audit -------------------------------------------------
    w = 0.38
    p3.bar(x - w / 2, off, w, color=F.GROUP_BASE["defect"], edgecolor="white",
           linewidth=0.5, zorder=3, label="Latent charged with the cooling plant OFF")
    p3.bar(x + w / 2, while_heat, w, color=F.GROUP_BASE["literature"], edgecolor="white",
           linewidth=0.5, zorder=3, label="Latent charged while the HEATING plant runs")
    p3.axhline(0, color="#7A7A7A", lw=1.0, zorder=4)
    p3.set_ylim(0, AUDIT_FULL_SCALE_KWH)
    p3.set_ylabel("Latent cooling charged (kWh)")
    p3.set_xlim(-0.7, len(F.STATES) - 0.3)
    p3.set_title("3 — The gating audit: latent charged with the plant off, and while heating",
                 loc="left", pad=7)
    F.state_ticks(p3, rotation=58)
    for t in p3.get_xticklabels():
        t.set_fontsize(7.2)
    F.mark_infiltration_group(p3)
    p3.ticklabel_format(axis="y", style="sci", scilimits=(0, 0), useMathText=True)
    p3.legend(loc="upper left", fontsize=7.6)
    for xi in x:
        p3.annotate("0", (xi, 0), xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=7.0, color="#6E6E6E")
    p3.annotate(
        "$\\bf{All\\ 26\\ values\\ are\\ exactly\\ 0.000000\\ kWh.}$\n"
        f"The axis is deliberately scaled to {AUDIT_FULL_SCALE_KWH:.0e} kWh full scale — "
        f"{100.0 * AUDIT_FULL_SCALE_KWH / can['Q_C_lat_gated']:.2f} % of the canonical\n"
        f"gated total of {can['Q_C_lat_gated']:.2f} kWh — so a leak of even a thousandth "
        "of the annual charge would be off-scale.\n"
        f"Latent heating is {st[F.CANONICAL_STATE]['Q_H_lat']:.4f} kWh at the canonical "
        "state, so no humidification is charged either.",
        xy=(0.5, 0.62), xycoords="axes fraction", ha="center", va="top",
        fontsize=8.2, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#EAF6F1",
                  edgecolor="#009E73", linewidth=0.9),
    )

    fig.suptitle("F8 — The latent gate: latent cooling is charged only in hours "
                 "the cooling plant actually runs",
                 fontsize=13.5, fontweight="bold", y=0.998)
    fig.text(0.5, 0.972,
             "Source: results/paper/trajectory_v2/trajectory_raw.json (per-state "
             "config_B) and comparison.md §6. The ungated column is the zone moisture "
             "balance before the plant-on gate;\nit is a diagnostic contrast only and is "
             "never part of a total.",
             ha="center", va="top", fontsize=8.4, color="#4D4D4D", linespacing=1.45)

    files = F.save(fig, "F8_latent_gate")

    return {
        "id": "F8",
        "title": "The latent gate",
        "files": files,
        "sources": [
            "results/paper/trajectory_v2/trajectory_raw.json",
            "results/paper/trajectory_v2/comparison.md §6 (the same numbers, for cross-check)",
        ],
        "numbers": [
            "Gated latent by state (kWh): "
            + ", ".join(f"{F.SHORT_PLAIN[s]} {g:.2f}" for s, g in zip(F.STATES, gated)),
            "Ungated moisture balance by state (kWh): "
            + ", ".join(f"{F.SHORT_PLAIN[s]} {u:.2f}" for s, u in zip(F.STATES, ungated)),
            f"Canonical state: the gate removes {can['Q_C_lat_ungated']:.2f} → "
            f"{can['Q_C_lat_gated']:.2f} kWh, {removed_pct:.1f} % of the raw balance",
            "Monthly gated latent at the canonical state (kWh): "
            + ", ".join(f"{m} {v:.2f}" for m, v in zip(MONTHS, monthly))
            + f"; Dec–Feb {summer:.2f} against Jun–Aug {winter:.2f}",
            "Gating audit: latent charged with the cooling plant off = 0.000000 kWh and "
            "latent charged while the heating plant runs = 0.000000 kWh, on all thirteen "
            f"states; audit axis full scale {AUDIT_FULL_SCALE_KWH:.0e} kWh",
            f"Cooling-plant hours at the canonical state: {can['n_steps_cooling_on']} of "
            f"{can['n_steps']:,}; latent charged in {can['n_steps_latent_charged']} hours",
        ],
        "note": (
            "Panel 3's y-limit is set to 1e-3 kWh so that any non-zero value would be "
            "visible; the script also asserts that all 26 audited values are exactly zero "
            "and refuses to draw otherwise."
        ),
        "placement": "main",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build()["files"])
