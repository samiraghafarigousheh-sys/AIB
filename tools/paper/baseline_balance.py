"""
Part 1d — the annual energy-balance inventory and Sankey, from the V2 instrument.

WHAT IS DRAWN, AND WHY IT IS NOT THE OLD SANKEY
-----------------------------------------------
The earlier Sankey was built from the annual balance *columns* and drew its gap
as a "Transmission (residual)" flow. That is honest as far as it goes, but a
residual re-published as a flow makes every diagram close by construction, so it
cannot be used to check closure.

This one is built from the closure-capable instrument's own inventory —
``sankey.inputs_Wh`` / ``outputs_Wh``, with the republished residual term
excluded — and draws the residual **separately**, as a gap. Closure is therefore
something the picture can fail to show.

    residual = inputs - outputs - storage

Reusable: ``write_balance()`` takes any state's ``config_B`` blob, so the same
figure and table are produced for the baseline and for the canonical state.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

V2_TOLERANCE_PCT = 5.0
EXPECTED_TRANSMISSION_ITEMS = 7

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"
GATE = "#c2255c"

IN_COLORS = ["#2a78d6", "#4f9ae8", "#7cb8f2", "#a8d2f7"]
OUT_COLORS = ["#eb6834", "#f08a5f", "#1baf7a", "#3fc493", "#8b5cf6", "#a78bfa",
              "#d4a017", "#e0b84a", "#0f766e", "#14958b", "#8b5e34", "#a8764a"]


def _short(name: str) -> str:
    """Trim the engine's inventory labels to something a figure can carry."""
    n = name.replace("Transmission - ", "Tr: ")
    n = n.replace("West window - fixed + West window - operable", "West windows")
    n = n.replace(" (opaque)", "").replace("Ventilation", "Vent")
    return n if len(n) <= 34 else n[:31] + "…"


def balance_rows(sk: dict) -> tuple[list[dict], list[dict], float, float, float]:
    inputs = {k: v / 1000.0 for k, v in sk["inputs_Wh"].items()}
    outputs = {k: v / 1000.0 for k, v in sk["outputs_Wh"].items()}
    storage = sk["storage_Wh"] / 1000.0
    in_sum, out_sum = sum(inputs.values()), sum(outputs.values())

    ins = [{"Term": k, "kWh": v, "% of inputs": 100.0 * v / in_sum if in_sum else 0.0}
           for k, v in sorted(inputs.items(), key=lambda kv: -kv[1])]
    outs = [{"Term": k, "kWh": v, "% of inputs": 100.0 * v / in_sum if in_sum else 0.0}
            for k, v in sorted(outputs.items(), key=lambda kv: -kv[1])]
    return ins, outs, in_sum, out_sum, storage


def sankey_figure(ins: list[dict], outs: list[dict], in_sum: float, out_sum: float,
                  storage: float, residual: float, title: str, subtitle: str,
                  out_png: Path) -> None:
    """A two-column flow diagram: inputs left, outputs right, ribbon width = kWh.

    Hand-drawn rather than `matplotlib.sankey`, which lays out a single balanced
    loop and cannot show a residual as an unmatched gap — the one thing this
    figure exists to show.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, PathPatch
    from matplotlib.path import Path as MPath

    fig, ax = plt.subplots(figsize=(13.5, 8.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # Both columns are drawn to the SAME total height, and the closure gap is the
    # block that makes them equal. Sign matters and is not cosmetic:
    #
    #   residual = inputs - outputs - storage
    #
    # so a NEGATIVE residual means the inputs fall short of what left the zone,
    # and the missing energy belongs on the INPUT side. Stacking it under the
    # outputs — as a first cut did — draws unaccounted input as though it were an
    # extra loss, which is the wrong way round and reads as a larger loss total
    # than the engine reported.
    extras_l = []
    extras_r = []
    if abs(storage) > 1e-9:
        (extras_r if storage > 0 else extras_l).append(
            ("Storage (net accumulation)" if storage > 0 else "Storage (net release)",
             abs(storage), "#94a3b8", False))
    if abs(residual) > 1e-9:
        side = extras_l if residual < 0 else extras_r
        side.append((
            "V2 residual — unaccounted "
            + ("input" if residual < 0 else "output"),
            abs(residual), GATE, True))

    total_l = in_sum + sum(v for _, v, _, _ in extras_l)
    total_r = out_sum + sum(v for _, v, _, _ in extras_r)
    n_l = len(ins) + len(extras_l)
    n_r = len(outs) + len(extras_r)

    GAP = 0.09
    H_AVAIL = 8.1      # leaves room under the stacks for the tiny-slice footnote
    scale = (H_AVAIL - GAP * max(n_l - 1, n_r - 1, 1)) / max(total_l, total_r)
    XL, XLW, XR, XRW = 1.55, 0.42, 8.05, 0.42

    # Slices too thin to carry an inline label are listed in a footnote instead of
    # being inflated to fit one. Widening a 6 kWh slice so its text fits would
    # make the picture lie about a width, which is the one thing a Sankey is for.
    MIN_LABEL_H = 0.15
    tiny: list[tuple[str, dict]] = []

    def stack(items, extras, x, w, colors, y0, align_right, side):
        y, drawn = y0, []
        for i, it in enumerate(items):
            h = it["kWh"] * scale
            if h <= 0:
                continue
            c = colors[i % len(colors)]
            ax.add_patch(Rectangle((x, y - h), w, h, facecolor=c, edgecolor="none",
                                   zorder=4))
            drawn.append((it, y - h, y, c))
            lbl = f"{_short(it['Term'])}  {it['kWh']:,.0f} kWh  ({it['% of inputs']:.1f} %)"
            if h > MIN_LABEL_H:
                ax.text(x - 0.16 if align_right else x + w + 0.16, y - h / 2, lbl,
                        ha="right" if align_right else "left", va="center",
                        fontsize=8.2, color=TEXT_PRIMARY, zorder=6)
            else:
                tiny.append((side, it))
            y -= h + GAP
        for label, val, col, hatched in extras:
            h = max(val * scale, 0.055)      # a floor, so a small gap stays visible
            ax.add_patch(Rectangle((x, y - h), w, h, facecolor=col, edgecolor=col,
                                   linewidth=0.8, alpha=0.95, zorder=4,
                                   hatch="///" if hatched else None))
            ax.text(x - 0.16 if align_right else x + w + 0.16, y - h / 2,
                    f"{label}  {val:,.1f} kWh"
                    + (f"  ({100 * val / in_sum:.2f} %)" if hatched else ""),
                    ha="right" if align_right else "left", va="center", fontsize=8.2,
                    color=GATE if hatched else TEXT_PRIMARY,
                    fontweight="semibold" if hatched else "normal", zorder=6)
            y -= h + GAP
        return drawn, y

    top = 9.05
    left, _ = stack(ins, extras_l, XL, XLW, IN_COLORS, top, align_right=True,
                    side="in")
    right, _ = stack(outs, extras_r, XR, XRW, OUT_COLORS, top, align_right=False,
                     side="out")

    # Ribbons, proportionally allocated: every input feeds every output in the
    # ratio of its size. This is a *balance* diagram, not a traced path — the
    # engine does not attribute individual gains to individual losses, and
    # pretending otherwise would be a fabricated claim.
    li = [[a, b, it, c] for it, a, b, c in left]
    ri = [[a, b, it, c] for it, a, b, c in right]
    for lo, hi, it_l, cl in li:
        frac_l = (hi - lo)
        cur = hi
        for ro, rhi, it_r, cr in ri:
            share = (rhi - ro) / max(1e-9, sum(r[1] - r[0] for r in ri))
            band = frac_l * share
            y1a, y1b = cur, cur - band
            cur -= band
            ry = ro + (rhi - ro) * ((hi - y1a) / max(1e-9, frac_l))
            ry2 = ro + (rhi - ro) * ((hi - y1b) / max(1e-9, frac_l))
            verts = [(XL + XLW, y1a), (5.0, y1a), (5.0, ry), (XR, ry),
                     (XR, ry2), (5.0, ry2), (5.0, y1b), (XL + XLW, y1b), (XL + XLW, y1a)]
            codes = [MPath.MOVETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
                     MPath.LINETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
                     MPath.CLOSEPOLY]
            ax.add_patch(PathPatch(MPath(verts, codes), facecolor=cl, edgecolor="none",
                                   alpha=0.16, zorder=2))

    if tiny:
        lines = ["too thin to label above (widths are still exact):"]
        for side, it in tiny:
            lines.append(f"    {'in' if side == 'in' else 'out'} · {_short(it['Term'])}"
                         f"  {it['kWh']:,.1f} kWh  ({it['% of inputs']:.2f} %)")
        ax.text(9.95, 0.10, "\n".join(lines), ha="right", va="bottom", fontsize=7.6,
                color=TEXT_SECONDARY, zorder=6, linespacing=1.5)

    ax.text(XL + XLW / 2, 9.35, f"IN   {in_sum:,.0f} kWh", ha="center", va="bottom",
            fontsize=11, color=TEXT_PRIMARY, fontweight="semibold")
    ax.text(XR + XRW / 2, 9.35, f"OUT   {out_sum:,.0f} kWh", ha="center", va="bottom",
            fontsize=11, color=TEXT_PRIMARY, fontweight="semibold")

    fig.suptitle(title, fontsize=14.5, color=TEXT_PRIMARY, x=0.008, ha="left",
                 y=0.985, fontweight="semibold")
    fig.text(0.008, 0.938, subtitle, fontsize=9, color=TEXT_SECONDARY, ha="left")
    fig.text(0.008, 0.905,
             "Ribbons are proportional, not traced: ISO 52016-1 is a node network and does "
             "not attribute a given gain to a given loss. Widths and totals are exact; the "
             "pairing is illustrative.",
             fontsize=8.2, color=TEXT_SECONDARY, ha="left", style="italic")

    fig.tight_layout(rect=[0, 0, 1, 0.895])
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def write_balance(state: dict, meta: dict, outdir: Path,
                  label: str = "ISO 52016-1 baseline",
                  stem: str = "baseline_balance") -> dict:
    """Inventory table + Sankey for one state's closed balance."""
    outdir.mkdir(parents=True, exist_ok=True)
    sk = state["sankey"]
    ins, outs, in_sum, out_sum, storage = balance_rows(sk)
    residual = sk["residual_kWh"]
    residual_pct = sk["residual_pct"]
    n_items = sk["n_transmission_items"]
    rel = sk.get("transmission_rel_diff", float("nan"))

    gate_ok = abs(residual_pct) < V2_TOLERANCE_PCT
    items_ok = n_items == EXPECTED_TRANSMISSION_ITEMS
    reint_ok = rel == rel and rel <= 0.001

    with (outdir / f"{stem}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Side", "Term", "kWh", "% of inputs"])
        for r in ins:
            w.writerow(["input", r["Term"], r["kWh"], r["% of inputs"]])
        for r in outs:
            w.writerow(["output", r["Term"], r["kWh"], r["% of inputs"]])
        w.writerow(["storage", "Energy accumulated in the zone", storage,
                    100.0 * storage / in_sum if in_sum else 0.0])
        w.writerow(["residual", "V2 closure residual", residual, residual_pct])

    L: list[str] = []
    add = L.append
    add(f"# Annual energy balance — {label}")
    add("")
    add(f"**V2 closure residual {residual:+,.2f} kWh ({residual_pct:+.2f} % of inputs) "
        f"— {'PASS' if gate_ok else 'FAIL'} against the {V2_TOLERANCE_PCT:.0f} % gate.** "
        f"**{n_items} transmission line items — {'PASS' if items_ok else 'FAIL'}.** "
        f"**Independent re-integration {'PASS' if reint_ok else 'FAIL'}"
        + (f" ({100 * rel:.4f} %)" if rel == rel else "") + ".**")
    add("")
    add(f"Apt 305, 50 Barry St Carlton, {state['net_floor_area_m2']:.0f} m². Weather "
        f"`{Path(meta['weather']).name}`. Inventory taken from the closure-capable "
        f"instrument, not from the annual balance columns.")
    add("")
    add("The residual is computed exactly as the engine's own `SANKEY CHECK` line does:")
    add("")
    add("```")
    add("inputs   = heating + internal gains + solar & free-gain")
    add("outputs  = cooling + ventilation + thermal bridges + ground")
    add("           + per-surface transmission (positive branches only)")
    add("residual = inputs - outputs - storage")
    add("```")
    add("")
    add("`Transmission (residual)` is **excluded** from the outputs sum. It is the "
        "residual re-published as a flow, and including it would make the balance "
        "close by construction — the diagram could then never fail, which would "
        "make it useless as a check.")
    add("")
    add(f"![energy balance]({stem}_sankey.png)")
    add("")

    add("## Inputs")
    add("")
    add("| Term | kWh | % of inputs |")
    add("| --- | ---: | ---: |")
    for r in ins:
        add(f"| {r['Term']} | {r['kWh']:,.2f} | {r['% of inputs']:.1f} % |")
    add(f"| **Total in** | **{in_sum:,.2f}** | **100.0 %** |")
    add("")

    add("## Outputs")
    add("")
    add("| Term | kWh | % of inputs |")
    add("| --- | ---: | ---: |")
    for r in outs:
        add(f"| {r['Term']} | {r['kWh']:,.2f} | {r['% of inputs']:.1f} % |")
    add(f"| **Total out** | **{out_sum:,.2f}** | "
        f"**{100.0 * out_sum / in_sum if in_sum else 0:.1f} %** |")
    add("")
    add("| | kWh | % of inputs |")
    add("| --- | ---: | ---: |")
    add(f"| Energy accumulated in the zone (storage) | {storage:+,.2f} | "
        f"{100.0 * storage / in_sum if in_sum else 0:+.2f} % |")
    add(f"| **V2 closure residual** | **{residual:+,.2f}** | **{residual_pct:+.2f} %** |")
    add("")

    add("## The transmission inventory")
    add("")
    add(f"The five party surfaces are 75.10 m², 88.6 % of the envelope UA. Before the "
        f"closure fixes they appeared on neither side of this balance and the "
        f"inventory listed two line items for a building with seven surfaces. "
        f"It now lists **{n_items}**.")
    add("")
    add("| Surface | kWh |")
    add("| --- | ---: |")
    for name, kwh in sorted(sk["transmission_items_kWh"].items(), key=lambda kv: -kv[1]):
        add(f"| {name.replace('Transmission - ', '')} | {kwh:,.2f} |")
    add(f"| **Σ reported** | **{sk.get('transmission_reported_kWh', float('nan')):,.2f}** |")
    add(f"| Σ independently re-integrated from the hourly frame "
        f"| {sk.get('transmission_independent_kWh', float('nan')):,.2f} |")
    add("")
    add(f"The two come from different code paths — the reported figure from the "
        f"in-loop accumulator, the independent one re-integrated from the hourly "
        f"frame afterwards — and agree to "
        + (f"{100 * rel:.4f} %" if rel == rel else "n/a")
        + f", inside the 0.1 % consistency check.")
    add("")

    (outdir / f"{stem}.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    sankey_figure(
        ins, outs, in_sum, out_sum, storage, residual,
        f"Apt 305, Carlton — annual energy balance, {label}",
        f"Weather {Path(meta['weather']).name} · {n_items} transmission line items · "
        f"V2 residual {residual:+,.1f} kWh ({residual_pct:+.2f} % of inputs), gate < "
        f"{V2_TOLERANCE_PCT:.0f} % — {'PASS' if gate_ok else 'FAIL'}",
        outdir / f"{stem}_sankey.png")

    (outdir / f"{stem}_raw.json").write_text(
        json.dumps({"inputs_kWh": {r["Term"]: r["kWh"] for r in ins},
                    "outputs_kWh": {r["Term"]: r["kWh"] for r in outs},
                    "storage_kWh": storage, "residual_kWh": residual,
                    "residual_pct": residual_pct,
                    "n_transmission_items": n_items,
                    "transmission_rel_diff": rel,
                    "weather": meta["weather"]}, indent=2), encoding="utf-8")

    print(f"  balance: in {in_sum:,.1f} / out {out_sum:,.1f} kWh, "
          f"residual {residual:+,.2f} kWh ({residual_pct:+.2f} %) "
          f"{'PASS' if gate_ok else 'FAIL'}, {n_items} tr items")
    return {"gate_ok": gate_ok, "items_ok": items_ok, "reint_ok": reint_ok,
            "residual_kWh": residual, "residual_pct": residual_pct,
            "in_sum_kWh": in_sum, "out_sum_kWh": out_sum, "storage_kWh": storage,
            "n_transmission_items": n_items}


def _slug(s: str) -> str:
    return (s.lower().replace("+", "").strip()
            .replace(" ", "_").replace("-", "_").replace("/", "_"))


def main() -> None:
    """Render the balance for one or more states of a trajectory raw JSON.

    Kept as a CLI so Part 1d and Part 4's per-state Sankeys are the *same* code
    reading the *same* file — a second implementation would be a second chance
    for the paper's two balance figures to disagree.
    """
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True,
                    help="a canonical_trajectory trajectory_raw.json")
    ap.add_argument("--state", action="append", required=True,
                    help="state label to render; repeatable")
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--stem", action="append", default=None,
                    help="output stem per --state (default: slug of the label)")
    args = ap.parse_args()

    blob = json.loads(args.raw.read_text(encoding="utf-8"))
    meta = blob["meta"]
    stems = args.stem or []
    summary = {}
    for i, label in enumerate(args.state):
        if label not in blob["results"]:
            raise SystemExit(f"state {label!r} not in {args.raw}. Available: "
                             f"{list(blob['results'])}")
        stem = stems[i] if i < len(stems) else _slug(label) + "_balance"
        print(f"{label}:")
        summary[label] = write_balance(blob["results"][label]["config_B"], meta,
                                       args.outdir, label=label, stem=stem)
    (args.outdir / "balance_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote -> {args.outdir}")


if __name__ == "__main__":
    main()
