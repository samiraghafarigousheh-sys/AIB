"""F5 -- Corrected-state (canonical) energy balance, drawn to F2's conventions."""

from __future__ import annotations

import figstyle as F
import sankey


def build() -> dict:
    traj = F.load_trajectory()
    s = traj["states"][F.CANONICAL_STATE]["sankey"]
    base = traj["states"]["Baseline"]["sankey"]

    inputs_kWh = {k: v / 1000.0 for k, v in s["inputs_Wh"].items()}
    outputs_kWh = {k: v / 1000.0 for k, v in s["outputs_Wh"].items()}
    in_total = sum(inputs_kWh.values())
    out_total = sum(outputs_kWh.values())
    residual = s["residual_kWh"]
    residual_pct = s["residual_pct"]

    if abs(residual) > 1e-6:
        raise F.MissingQuantity(
            f"F5: canonical residual is {residual!r} kWh, expected machine zero")

    party = sum(outputs_kWh[k] for k in F.PARTY_SURFACES)
    party_share = 100.0 * party / out_total
    base_party = sum(base["outputs_Wh"][k] / 1000.0 for k in F.PARTY_SURFACES)

    fig = sankey.draw(
        s,
        fig_id="F5",
        title="F5 — Corrected-state annual energy balance, canonical model (+Closure fixes)",
        subtitle=(
            "Same building, same weather, same conventions and same vertical scale as F2 · "
            "all seven transmission line items resolved\n"
            f"Inputs {in_total:,.1f} kWh · outputs {out_total:,.1f} kWh · "
            f"residual {residual:.3e} kWh ({residual_pct:.2e} % of inputs) — "
            "the balance closes to machine precision"
        ),
        callouts=[
            {
                "xy": (0.175, 0.150),
                "text": (
                    "$\\bf{The}$ $\\bf{balance}$ $\\bf{closes}$\n"
                    f"Inputs and outputs agree to {abs(residual):.1e} kWh —\n"
                    "machine zero. There is no gap to draw, and\n"
                    "no residual re-published as a flow. Compare\n"
                    f"F2, where {abs(base['residual_kWh']):,.1f} kWh had no source."
                ),
                "fc": "#EAF6F1", "ec": "#009E73",
            },
            {
                "xy": (0.500, 0.150),
                "text": (
                    "$\\bf{The}$ $\\bf{five}$ $\\bf{party}$ $\\bf{surfaces}$ $\\bf{are}$ $\\bf{now}$ $\\bf{inventoried}$\n"
                    f"{party:,.0f} kWh, {party_share:.1f} % of output, on both sides of\n"
                    "the balance. In F2 the same five carried\n"
                    f"{base_party:,.0f} kWh against an open residual; here they\n"
                    "are resolved and the balance answers for them."
                ),
                "fc": "#EEF2FB", "ec": "#4C72B0",
            },
            {
                "xy": (0.840, 0.150),
                "text": (
                    "$\\bf{Read}$ $\\bf{F2}$ $\\bf{and}$ $\\bf{F5}$ $\\bf{together}$\n"
                    f"The whole balance is {in_total:,.0f} kWh here against\n"
                    f"{sum(base['inputs_Wh'].values()) / 1000.0:,.0f} kWh in F2, drawn at the same\n"
                    "kWh per unit height. The columns are shorter\n"
                    "because the model moved, not the drawing."
                ),
                "fc": "#F6F0F8", "ec": "#CC79A7",
            },
        ],
        scale_note="shared vertical\nscale, F2 and F5",
        ghost=(sum(base["outputs_Wh"].values()) / 1000.0,
               "dashed outline: the extent of F2's columns "
               f"({sum(base['outputs_Wh'].values()) / 1000.0:,.0f} kWh) at this same scale"),
        footer=(
            "Ribbon pairings are $\\it{proportional}$, not traced: ISO 52016-1 is a node network "
            "and does not attribute a given gain to a given loss.\n"
            "Band order, colour and vertical scale are identical to F2. "
            "Source: results/paper/trajectory_v2/trajectory_raw.json → +Closure fixes → config_B → sankey."
        ),
    )
    files = F.save(fig, "F5_corrected_energy_balance_sankey")

    return {
        "id": "F5",
        "title": "Corrected-state energy balance (Sankey), canonical state",
        "files": files,
        "sources": [
            "results/paper/trajectory_v2/trajectory_raw.json (+Closure fixes → config_B → sankey)"
        ],
        "numbers": [
            f"Inputs {in_total:,.1f} kWh; outputs {out_total:,.1f} kWh; "
            f"residual {residual:.3e} kWh ({residual_pct:.2e} %) — machine zero",
            f"Heating {inputs_kWh['Heating']:,.1f} kWh; "
            f"internal gains {inputs_kWh['Internal gains']:,.1f} kWh; "
            f"solar & free-gain {inputs_kWh['Solar & free-gain']:,.1f} kWh",
            f"Five party surfaces (ADJ) {party:,.1f} kWh = {party_share:.1f} % of output",
            "Seven transmission line items resolved: "
            + "; ".join(f"{F.SANKEY_SHORT[k]} {v:,.1f} kWh"
                        for k, v in outputs_kWh.items() if k.startswith("Transmission")),
            f"Ventilation (losses) {outputs_kWh['Ventilation (losses)']:,.1f} kWh; "
            f"cooling {outputs_kWh['Cooling (extracted energy)']:,.1f} kWh; "
            f"ground {outputs_kWh['Ground']:,.1f} kWh (the phantom slab term is gone); "
            f"thermal bridges {outputs_kWh['Thermal bridges']:,.1f} kWh",
        ],
        "note": (
            "Drawn by the same renderer as F2 with the same band order, colour map and "
            "kWh-per-unit-height, so the two figures are directly comparable. The corrected "
            "state has no residual band because there is no residual."
        ),
        "placement": "main",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build()["files"])
