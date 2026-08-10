"""F9 -- Closure residual and inventory completeness."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle as F

EXPECTED_ITEMS = 7
PRE_CLOSURE_ITEMS = 2        # results/au_corrections_closed/six_state_closed.md, line 30


def build() -> dict:
    traj = F.load_trajectory()
    st = traj["states"]
    res = [st[s]["residual_pct"] for s in F.STATES]
    items = [st[s]["n_transmission_items"] for s in F.STATES]
    reldiff = [st[s]["transmission_rel_diff"] for s in F.STATES]

    if any(n != EXPECTED_ITEMS for n in items):
        raise F.MissingQuantity(
            f"F9: transmission line-item counts are {items}, expected {EXPECTED_ITEMS} everywhere")
    if any(abs(d) > 1e-12 for d in reldiff):
        raise F.MissingQuantity(
            f"F9: the independent re-integration does not agree to 0.0000 % on every "
            f"state — relative differences {reldiff}")
    if any(abs(r) >= 5.0 for r in res):
        raise F.MissingQuantity(f"F9: a state breaches the ±5 % gate — residuals {res}")

    fig, (a, b) = plt.subplots(2, 1, figsize=(12.6, 10.2))
    x = np.arange(len(F.STATES))

    # ---- A: V2 residual with the +-5 % gate ---------------------------------
    a.axhspan(-5, 5, color=F.GATE_BAND, alpha=0.30, zorder=0, lw=0)
    for edge in (-5, 5):
        a.axhline(edge, color="#B9A600", lw=1.1, ls="--", zorder=2)
    a.axhline(0, color="#7A7A7A", lw=0.9, zorder=2)
    a.bar(x, res, 0.7, color=[F.STATE_COLOR[s] for s in F.STATES],
          edgecolor="white", linewidth=0.5, zorder=3)
    a.set_ylim(-6.8, 6.8)
    a.set_ylabel("V2 Sankey closure residual (% of inputs)")
    a.set_xlim(-0.7, len(F.STATES) - 0.3)
    a.set_title("A — V2 closure residual, all thirteen states, against the ±5 % gate",
                loc="left", pad=7)
    F.state_ticks(a, rotation=58)
    for t in a.get_xticklabels():
        t.set_fontsize(7.6)
    F.mark_infiltration_group(a)
    a.text(-0.4, 5.15, "±5 % gate", ha="left", va="bottom", fontsize=8.4,
           color="#8A7B00", fontweight="bold")
    a.text(-0.4, -5.15, "±5 % gate", ha="left", va="top", fontsize=8.4,
           color="#8A7B00", fontweight="bold")
    for xi, r in zip(x, res):
        a.annotate(f"{r:+.2f}", (xi, r), xytext=(0, -4 if r < 0 else 4),
                   textcoords="offset points", ha="center",
                   va="top" if r < 0 else "bottom", fontsize=7.2, color=F.INK)
    worst = min(res, key=abs) if all(r == 0 for r in res) else min(res)
    worst_i = int(np.argmin(res))
    a.annotate(
        f"Largest excursion $\\bf{{{worst:.2f}\\ \\%}}$ at {F.SHORT[F.STATES[worst_i]]}. "
        "From +Ground contact\nonward the residual is machine zero. "
        "$\\bf{Every\\ state\\ passes\\ the\\ gate.}$",
        xy=(0.985, 0.955), xycoords="axes fraction", ha="right", va="top",
        fontsize=8.4, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )

    # ---- B: resolved transmission line items --------------------------------
    b.bar(x, items, 0.7, color=[F.STATE_COLOR[s] for s in F.STATES],
          edgecolor="white", linewidth=0.5, zorder=3)
    b.axhline(EXPECTED_ITEMS, color="#009E73", lw=1.6, ls="--", zorder=4)
    b.axhline(PRE_CLOSURE_ITEMS, color=F.RESIDUAL_COLOR, lw=1.6, ls=":", zorder=4)
    b.set_ylim(0, EXPECTED_ITEMS * 1.62)
    b.set_yticks(range(0, EXPECTED_ITEMS + 2))
    b.set_ylabel("Resolved transmission line items")
    b.set_xlim(-0.7, len(F.STATES) - 0.3)
    b.set_title("B — Transmission inventory completeness: seven surfaces, seven line items",
                loc="left", pad=7)
    F.state_ticks(b, rotation=58)
    for t in b.get_xticklabels():
        t.set_fontsize(7.6)
    F.mark_infiltration_group(b)
    for xi, n in zip(x, items):
        b.annotate(str(n), (xi, n), xytext=(0, -4), textcoords="offset points",
                   ha="center", va="top", fontsize=9.0, fontweight="bold", color="white")
    b.text(-0.4, EXPECTED_ITEMS + 0.10,
           "expected 7 = 5 party surfaces + west exterior wall + west windows",
           ha="left", va="bottom", fontsize=8.2, color="#00795A", fontweight="bold")
    b.text(-0.4, PRE_CLOSURE_ITEMS + 0.10,
           "the same column read 2 before the closure corrections",
           ha="left", va="bottom", fontsize=8.2, color=F.RESIDUAL_COLOR, fontweight="bold")
    b.annotate(
        "The five party surfaces are 75.10 m² and 88.6 % of the envelope UA. Before the\n"
        "closure fixes they appeared on neither side of the balance, and the inventory\n"
        "listed two line items for a building with seven surfaces.\n"
        "On every state here the independent re-integration agrees to "
        "$\\bf{0.0000\\ \\%}$ — the reported sum\n"
        "comes from the in-loop accumulator, the independent one from the hourly "
        "frame afterwards.",
        xy=(0.985, 0.955), xycoords="axes fraction", ha="right", va="top",
        fontsize=8.2, color=F.INK, linespacing=1.5, zorder=6,
        bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                  edgecolor="#BBBBBB", linewidth=0.8),
    )

    fig.suptitle("F9 — Closure residual and inventory completeness",
                 fontsize=13.5, fontweight="bold", y=0.997)
    fig.text(0.5, 0.958,
             "The instrument is identical across states by construction — the closure commits "
             "are cherry-picked onto each one — which is what makes the states comparable.\n"
             "Sources: results/paper/trajectory_v2/ (residual, line-item count, re-integration); "
             "the pre-closure count of 2 is from "
             "results/au_corrections_closed/six_state_closed.md.",
             ha="center", va="top", fontsize=8.4, color="#4D4D4D", linespacing=1.45)

    fig.tight_layout(rect=(0.005, 0.005, 0.995, 0.930))
    files = F.save(fig, "F9_closure_residual_and_inventory")

    return {
        "id": "F9",
        "title": "Closure residual and inventory completeness",
        "files": files,
        "sources": [
            "results/paper/trajectory_v2/trajectory_raw.json",
            "results/paper/trajectory_v2/comparison.md §4–§5",
            "results/au_corrections_closed/six_state_closed.md "
            "(the pre-closure line-item count of 2)",
        ],
        "numbers": [
            "V2 residual (% of inputs) by state: "
            + ", ".join(f"{F.SHORT_PLAIN[s]} {r:+.2f}" for s, r in zip(F.STATES, res)),
            f"Largest excursion {worst:.2f} % at {F.STATES[worst_i]}; "
            "machine zero from +Ground contact onward; all thirteen inside ±5 %",
            f"Resolved transmission line items: {EXPECTED_ITEMS} on every state "
            "(5 ADJ party surfaces + 1 OP west wall + 1 W west windows)",
            "Independent re-integration agrees with the reported sum to 0.0000 % on "
            "every state",
            f"Pre-closure the same column read {PRE_CLOSURE_ITEMS}, against seven surfaces",
        ],
        "note": (
            "The residual column of the trajectory table carries the same numbers, so this "
            "figure is a visual restatement rather than new information — suitable for the "
            "appendix if the main figure count is constrained."
        ),
        "placement": "supplementary",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build()["files"])
