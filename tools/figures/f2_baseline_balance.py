"""F2 -- Baseline energy-balance decomposition (Sankey)."""

from __future__ import annotations

import figstyle as F
import sankey


def build() -> dict:
    traj = F.load_trajectory()
    s = traj["states"]["Baseline"]["sankey"]

    inputs_kWh = {k: v / 1000.0 for k, v in s["inputs_Wh"].items()}
    outputs_kWh = {k: v / 1000.0 for k, v in s["outputs_Wh"].items()}
    in_total = sum(inputs_kWh.values())
    out_total = sum(outputs_kWh.values())
    residual = s["residual_kWh"]
    residual_pct = s["residual_pct"]

    ig_share = 100.0 * inputs_kWh["Internal gains"] / in_total
    party = sum(outputs_kWh[k] for k in F.PARTY_SURFACES)
    party_share = 100.0 * party / out_total

    # The two quantities the diagnostic argument rests on.
    if abs(ig_share - 64.5) > 0.05:
        raise F.MissingQuantity(
            f"F2: internal gains are {ig_share:.2f} % of input, the paper states 64.5 %")
    if abs(residual - (-96.72)) > 0.01 or abs(residual_pct - (-1.164)) > 0.002:
        raise F.MissingQuantity(
            f"F2: residual is {residual:.2f} kWh / {residual_pct:.3f} %, "
            f"the paper states -96.7 kWh / -1.16 %")

    fig = sankey.draw(
        s,
        fig_id="F2",
        title="F2 — Baseline annual energy balance, ISO 52016-1 as vendored",
        subtitle=(
            "Apt 305, 50 Barry St Carlton · "
            "AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011–2025 · "
            "all seven transmission line items resolved\n"
            f"Inputs {in_total:,.1f} kWh · outputs {out_total:,.1f} kWh · "
            f"residual {residual:,.1f} kWh ({residual_pct:+.2f} % of inputs) — "
            "drawn as an unmatched gap, not as a flow"
        ),
        callouts=[
            {
                "xy": (0.175, 0.150),
                "text": (
                    "$\\bf{Internal}$ $\\bf{gains}$ dominate the input\n"
                    f"{inputs_kWh['Internal gains']:,.0f} kWh of {in_total:,.0f} kWh = "
                    f"$\\bf{{{ig_share:.1f}\\ \\%}}$ of everything\n"
                    "entering the balance — more than heating\n"
                    "and solar together."
                ),
                "fc": "#FFF4E0", "ec": "#E69F00",
            },
            {
                "xy": (0.500, 0.150),
                "text": (
                    "The $\\bf{five}$ $\\bf{party}$ $\\bf{surfaces}$ dominate the loss\n"
                    f"{party:,.0f} kWh, {party_share:.1f} % of all output. They are\n"
                    "75.10 m² and 88.6 % of the envelope UA, and\n"
                    "they face conditioned neighbours, not outdoors."
                ),
                "fc": "#EEF2FB", "ec": "#4C72B0",
            },
            {
                "xy": (0.840, 0.150),
                "text": (
                    "$\\bf{The}$ $\\bf{unmatched}$ $\\bf{gap}$\n"
                    f"Outputs exceed inputs by {-residual:,.1f} kWh\n"
                    f"({residual_pct:+.2f} % of inputs). Nothing supplies it,\n"
                    "so it is drawn hatched and emits no ribbon —\n"
                    "never absorbed into a transmission item."
                ),
                "fc": "#FDEDED", "ec": sankey.F.RESIDUAL_COLOR,
            },
        ],
        scale_note="shared vertical\nscale, F2 and F5",
        footer=(
            "Ribbon pairings are $\\it{proportional}$, not traced: ISO 52016-1 is a node network "
            "and does not attribute a given gain to a given loss.\n"
            "The vertical scale is shared with F5, so the two balances can be compared directly. "
            "Source: results/paper/trajectory_v2/trajectory_raw.json → Baseline → config_B → sankey."
        ),
    )
    files = F.save(fig, "F2_baseline_energy_balance_sankey")

    return {
        "id": "F2",
        "title": "Baseline energy-balance decomposition (Sankey)",
        "files": files,
        "sources": ["results/paper/trajectory_v2/trajectory_raw.json (Baseline → config_B → sankey)"],
        "numbers": [
            f"Inputs {in_total:,.1f} kWh; outputs {out_total:,.1f} kWh; "
            f"residual {residual:,.2f} kWh ({residual_pct:+.2f} %)",
            f"Internal gains {inputs_kWh['Internal gains']:,.1f} kWh = {ig_share:.1f} % of input",
            f"Heating {inputs_kWh['Heating']:,.1f} kWh; "
            f"solar & free-gain {inputs_kWh['Solar & free-gain']:,.1f} kWh",
            f"Five party surfaces (ADJ) {party:,.1f} kWh = {party_share:.1f} % of output — dominant loss",
            "Seven transmission line items resolved: "
            + "; ".join(f"{F.SANKEY_SHORT[k]} {v:,.1f} kWh"
                        for k, v in outputs_kWh.items() if k.startswith("Transmission")),
            f"Ventilation (losses) {outputs_kWh['Ventilation (losses)']:,.1f} kWh; "
            f"cooling {outputs_kWh['Cooling (extracted energy)']:,.1f} kWh; "
            f"ground {outputs_kWh['Ground']:,.1f} kWh; "
            f"thermal bridges {outputs_kWh['Thermal bridges']:,.1f} kWh",
        ],
        "note": (
            "The residual is drawn as a hatched, unfilled band on the input side — the side "
            "that is short — and is never folded into a transmission item. The source record "
            "carries `republished_residual_Wh = 0.0`, which the renderer asserts before drawing."
        ),
        "placement": "main",
    }


if __name__ == "__main__":
    F.apply_style()
    print(build()["files"])
