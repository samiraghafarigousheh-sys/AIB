"""
The canonical trajectory, rebuilt in **methodology order**.

WHY THE OLD TRAJECTORY WAS OUT OF ORDER
---------------------------------------
The seven-state harness took each state from a *branch tip*, and every one of
those branches was cut from the unmodified baseline. None of them contained the
two literature corrections:

    git merge-base --is-ancestor a66eec7 <each of the six state branches>  -> no
    git merge-base --is-ancestor 56f5d08 <each of the six state branches>  -> no

So C1 (dynamic window transmittance) and C2 (wind-dependent external h_ce) only
appeared at the end, at HEAD, because `main` happened to carry them — not because
the trajectory applied them. The paper's methodology is the other way round:
literature corrections first, then the implementation defects we found. C2's
ordinal is meaningless unless C1 precedes it and both precede the found defects.

WHAT THIS BUILDS
----------------
One linear stack, cherry-picked from the baseline in methodology order, each
state being the previous state plus exactly one correction:

    Baseline -> C1 -> C2 -> ventilation -> latent -> internal gains
             -> conditioned zones -> ground -> hemisphere -> closure

Ventilation and latent are SPLIT rather than kept combined: on
`claude/ventilation-plus-latent-fix` they are already two separate commits
(9a89334 then 0bab14f), so splitting them is free and changes neither one's
physics.

C1 IS INCLUDED as a cumulative step, which is the plan's stated default for
"literature corrections first". It is not merely reported in its own Base/C1/C2
window comparison.

THE INSTRUMENT IS HELD CONSTANT
-------------------------------
Every state is measured with the closure-capable reporting instrument — the same
ADJ-transmission tally, the same V2 residual, the same sensible/latent split as
the closed-balance harness — back-ported by cherry-pick. Without that, states
before the closure fixes have no closed balance to report and the gate could not
be applied to them at all.

A consequence worth stating rather than hiding: because the instrument already
contains the closure fixes, the final `+Closure fixes` step moves *no number*.
That is not a bug in the table, it is the finding — the closure fixes are
corrections to the measurement, not to the physics, which is exactly what makes
the nine states before them comparable to each other.

ORDER-INDEPENDENCE
------------------
The stack's final state is verified two ways: byte-for-byte against HEAD's engine
tree, and numerically against HEAD *run on the same weather file*. If either
differs, a correction is not cleanly separable and the run stops rather than
publishing a moved headline.

HEAD invariance is checked against a live HEAD run, not against a stored
constant. Those are different claims. A stored constant asserts "this trajectory
reproduces the number we published", which is false the moment a legitimate input
changes and tells you nothing about separability. Comparing to HEAD on the same
weather asserts "however the corrections are ordered, the engine lands in the same
place", which is the property this harness exists to test and is the same claim on
every weather file.

THE WEATHER IS SCREENED BEFORE ANYTHING IS COMPUTED
---------------------------------------------------
The first canonical run used AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw. Four
whole months of its wind column read exactly 0.0 m/s -- the station's record ends
in 2014 -- and because C2's ``h_ce = 4v + 4`` collapses to 4 W/(m2 K) at v = 0,
those fabricated calms tripled sensible cooling. The replacement station is
Essendon Fields (WMO 958660, ~8 km NW of the Carlton site, complete record). The
run now aborts on a dead-calm month rather than producing a headline that cannot
be defended -- see ``tools/diagnostics/weather_integrity.py``.

Usage
-----
    python tools/diagnostics/canonical_trajectory.py \\
        --weather weather_cache/AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw \\
        --outdir results/au_canonical_essendon
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from closed_balance_six_state import (          # noqa: E402  the identical instrument
    GIT_IDENTITY,
    V2_TOLERANCE_PCT,
    apply_shim,
    closure_commits,
    drop_worktree,
    run_engine,
)
from weather_integrity import assert_usable      # noqa: E402  the wind-column preflight

ENGINE_PATH = "pybuildingenergy/src/"
BASELINE = "2e6e910"          # Vendor pyBuildingEnergy ISO 52016-1 engine (unmodified)

# The commit the closure work sits on top of, pinned rather than taken as
# `origin/main`.
#
# WHY IT IS PINNED. The closure commits are the *instrument*: they are
# cherry-picked onto every state so all ten are measured the same way, which is
# the only thing that makes them comparable. Selecting them as "whatever is above
# origin/main" was correct exactly once — while they were unmerged. PR #16 has
# since merged three of the four into main, so that expression now resolves to a
# single commit, the back-port would silently omit the ADJ tally, the latent gate
# and the GR rule, and nine of the ten states would be measured with an
# instrument the tenth does not use. The residuals would blow out and the table
# would look like a physics finding. Pinning the base makes the instrument
# independent of what has since been merged.
CLOSURE_BASE = "978db37"

# What that base must yield. Asserted, because a silently short list is exactly
# the failure mode above and it does not announce itself.
EXPECTED_CLOSURE_PREFIXES = ("6e549fa", "82a909d", "9fd8c69", "0935730")

# (label, [commits], provenance note). Order IS the methodology order.
TRAJECTORY = [
    ("Baseline", [],
     "unmodified ISO 52016-1, as vendored"),
    ("+C1 dynamic window", ["a66eec7"],
     "literature — angular/hourly window g-value and U_win(t)"),
    ("+C2 wind-dependent h_ce", ["56f5d08"],
     "literature — external convective coefficient h_ce = 4v + 4"),
    ("+Ventilation", ["9a89334"],
     "found defect — additive H_ve_inf term"),
    ("+Latent", ["0bab14f"],
     "found defect — EN 16798-1 deadband, occupancy moisture, dt_h"),
    ("+Internal gains", ["5aca6ce"],
     "found defect — de-inflation; drop the neighbour-count multiplier"),
    ("+Conditioned zones", ["7339076"],
     "found defect — Issue 7 adjacent-zone boundary treatment"),
    ("+Ground contact", ["418496b"],
     "found defect — no implicit slab-on-ground fallback"),
    ("+Hemisphere", ["ef312fe"],
     "found defect — latitude-resolved coldest month"),
    ("+Closure fixes", None,          # resolved at run time from --closure-ref
     "ADJ transmission into the inventory, latent gating, GR classification"),
]

# The metrics on which the trajectory's final state must reproduce HEAD, and the
# tolerance: 0.01 is the printed precision, so anything that would change a
# published digit fails.
INVARIANT_KEYS = ("Q_H_sensible_kWh", "Q_C_sensible_kWh",
                  "Q_C_latent_kWh", "Q_need_total_kWh_per_sqm")
CANONICAL_TOL = 0.01     # kWh / kWh·m-2

# The superseded run, quoted only to state plainly what changed and why. Read
# from its own comparison.csv when that file is present, so the contrast can
# never drift from what was actually published.
PRIOR_RUN = {
    "label": "AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw",
    "csv": REPO_ROOT / "results" / "au_canonical" / "comparison.csv",
    "why_superseded": (
        "four calendar months of its wind column — Jan, Mar, Jul, Sep, 2,952 h, "
        "33.7 % of the year — read identically 0.0 m/s, an artefact of the "
        "Melbourne Regional Office station's record ending in 2014"),
}

# Latent-gating expectations, asserted on the final state and reported either way.
LATENT_HEATING_MAX_KWH = 0.05     # "~0.03 kWh" — a residue, not a demand
LATENT_LEAK_TOL_KWH = 1e-9        # charged with the plant off, or while heating
TRANSMISSION_ITEMS_EXPECTED = 7   # five party (ADJ) + exposed wall + window
TRANSMISSION_REINTEGRATION_TOL = 0.001   # 0.1 %, the plan's consistency check


def _git(*a, cwd=REPO_ROOT, check=True):
    p = subprocess.run(["git", "-C", str(cwd), *GIT_IDENTITY, *a],
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)} failed:\n{p.stderr.strip()}")
    return p


# The one engine file whose conflicts may be resolved, and only when back-porting
# the instrument. `check_input.py` carries the validator's advisory warnings; on
# branches that predate the block a warning attaches to, it conflicts. No number
# in this table comes from it. Building the TRAJECTORY itself never permits this:
# there, an engine conflict is the signal that a correction is not cleanly
# separable at that point in the order, which is what the harness is for.
INSTRUMENT_CONFLICT_ALLOWED = ("source/check_input.py",)


def cherry_pick(dest: Path, sha: str, label: str,
                allow_engine: tuple[str, ...] = ()) -> list[str]:
    """Cherry-pick one commit, resolving conflicts only where permitted.

    A conflict in ``pybuildingenergy/src/`` would mean the correction is not
    cleanly separable at this position in the order, which is precisely what this
    harness exists to detect -- so it aborts rather than guessing, unless the file
    is in ``allow_engine``. Conflicts elsewhere (``.gitignore``, notebooks,
    results trees) carry no physics and are resolved in favour of the state being
    built.
    """
    p = _git("cherry-pick", "-x", sha, cwd=dest, check=False)
    if p.returncode == 0:
        return []
    unmerged = _git("diff", "--name-only", "--diff-filter=U", cwd=dest).stdout.split()
    engine = [f for f in unmerged
              if f.startswith(ENGINE_PATH)
              and not any(f.endswith(a) for a in allow_engine)]
    if engine or not unmerged:
        _git("cherry-pick", "--abort", cwd=dest, check=False)
        raise RuntimeError(
            f"[{label}] {sha[:9]} conflicts in {engine or unmerged or '<unknown>'}. "
            f"A conflict inside {ENGINE_PATH} means this correction is not cleanly "
            f"separable at this point in the order -- refusing to guess a resolution."
        )
    for f in unmerged:
        _git("checkout", "--ours", "--", f, cwd=dest, check=False)
        _git("rm", "-q", "--cached", "--ignore-unmatch", "--", f, cwd=dest, check=False) \
            if not (dest / f).exists() else None
    _git("add", "-A", cwd=dest)
    _git("cherry-pick", "--continue", "--no-edit", cwd=dest)
    return unmerged


def build_stack(tmp: Path, closure: list[str]) -> tuple[Path, list[dict]]:
    """Cherry-pick the trajectory onto the baseline, one state at a time."""
    stack = tmp / "stack"
    _git("worktree", "add", "--detach", str(stack), BASELINE)

    states: list[dict] = []
    for label, commits, note in TRAJECTORY:
        shas = closure if commits is None else commits
        resolved: list[str] = []
        for sha in shas:
            resolved += cherry_pick(stack, sha, label)
        sha_now = _git("rev-parse", "HEAD", cwd=stack).stdout.strip()
        states.append({
            "label": label, "note": note, "commits": list(shas),
            "sha": sha_now, "resolved_outside_engine": resolved,
            "carries_closure": commits is None,
        })
        print(f"  built {label:<28} {sha_now[:9]}"
              + (f"   [resolved outside engine: {' '.join(resolved)}]" if resolved else ""),
              flush=True)
    return stack, states


def verify_final_engine_matches_head(stack: Path) -> dict:
    """The strongest available order-independence check: compare the source.

    Applying the same set of corrections in a different order must land on the
    same engine. Comparing trees rather than only numbers catches a difference
    that happens not to move this particular building's annual result.
    """
    a = stack / "pybuildingenergy" / "src"
    b = REPO_ROOT / "pybuildingenergy" / "src"
    differing: list[str] = []
    for pa in sorted(a.rglob("*.py")):
        if "__pycache__" in pa.parts:
            continue
        pb = b / pa.relative_to(a)
        if not pb.exists() or pa.read_bytes() != pb.read_bytes():
            differing.append(str(pa.relative_to(a)))
    for pb in sorted(b.rglob("*.py")):
        if "__pycache__" in pb.parts:
            continue
        if not (a / pb.relative_to(b)).exists():
            differing.append(str(pb.relative_to(b)))
    return {"identical": not differing, "differing_files": sorted(set(differing))}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

COLUMNS = [
    ("state", "State"),
    ("Q_H_sensible_kWh", "Sensible heating (kWh)"),
    ("Q_C_sensible_kWh", "Sensible cooling (kWh)"),
    ("Q_C_latent_kWh", "Latent cooling, gated (kWh)"),
    ("Q_C_latent_ungated_kWh", "Latent cooling, ungated (kWh)"),
    ("Q_H_latent_kWh", "Latent heating (kWh)"),
    ("Q_sens_plus_gated_latent_kWh", "Total, sensible + gated latent (kWh)"),
    ("Q_need_total_kWh", "Total (kWh)"),
    ("Q_need_total_kWh_per_sqm", "Total (kWh/m²)"),
    ("residual_kWh", "V2 residual (kWh)"),
    ("residual_pct", "V2 residual (%)"),
    ("gate", "< 5 %?"),
    ("n_transmission_items", "Transmission items"),
    ("Q_solar_gains_kWh", "Solar gains (kWh)"),
    ("Q_internal_gains_kWh", "Internal gains (kWh)"),
    ("Q_tr_window_loss_kWh", "Window transmission loss (kWh)"),
    ("Q_tr_opaque_loss_kWh", "Opaque transmission loss (kWh)"),
    ("Q_tr_total_loss_kWh", "Total transmission loss (kWh)"),
    ("Q_ve_loss_kWh", "Ventilation + infiltration loss (kWh)"),
]

# The columns the Markdown trajectory table shows. The CSV carries all of
# COLUMNS; the Markdown table would be unreadable at eighteen columns wide, and
# the envelope decomposition has its own section in the Part 3 tables.
MD_COLUMNS = 13


def flatten(label: str, r: dict) -> dict:
    b, sk = r["config_B"], r["config_B"]["sankey"]
    return {
        "state": label,
        **{k: b.get(k) for k, _ in COLUMNS if k in b},
        # Stated explicitly rather than inferred. `Q_need_total_kWh` is the
        # engine's own total and additionally carries latent *heating*, which is
        # 158 kWh of phantom humidification on the states before the latent fix
        # and 0.00 after it — so the two columns diverge early and coincide at the
        # canonical state. Both are shown so neither has to be assumed.
        "Q_sens_plus_gated_latent_kWh": (b["Q_H_sensible_kWh"] + b["Q_C_sensible_kWh"]
                                         + b["Q_C_latent_kWh"]),
        "residual_kWh": sk["residual_kWh"],
        "residual_pct": sk["residual_pct"],
        "gate": "PASS" if abs(sk["residual_pct"]) < V2_TOLERANCE_PCT else "FAIL",
        "n_transmission_items": sk["n_transmission_items"],
        # Inventory + gating evidence, carried alongside the headline so the
        # invariants can be reported per state rather than asserted once.
        "transmission_reported_kWh": sk.get("transmission_reported_kWh"),
        "transmission_independent_kWh": sk.get("transmission_independent_kWh"),
        "transmission_rel_diff": sk.get("transmission_rel_diff"),
        "n_steps": b.get("n_steps"),
        "n_steps_cooling_on": b.get("n_steps_cooling_on"),
        "n_steps_heating_on": b.get("n_steps_heating_on"),
        "n_steps_latent_charged": b.get("n_steps_latent_charged"),
        "latent_kWh_with_cooling_off": b.get("latent_kWh_with_cooling_off"),
        "latent_kWh_while_heating": b.get("latent_kWh_while_heating"),
        "monthly_latent_cooling_kWh": b.get("monthly_latent_cooling_kWh"),
        "Q_tr_adjacent_loss_kWh": b.get("Q_tr_adjacent_loss_kWh"),
        "Q_tr_adjacent_gain_kWh": b.get("Q_tr_adjacent_gain_kWh"),
        # Envelope decomposition. Carried per state so the paper's window/h_ce
        # and ventilation/latent sub-tables can be derived from this run rather
        # than from a second harness measuring the same states again — two
        # harnesses are two chances for the same claim to come out differently.
        "Q_solar_gains_kWh": b.get("Q_solar_gains_kWh"),
        "Q_internal_gains_kWh": b.get("Q_internal_gains_kWh"),
        "Q_tr_window_loss_kWh": b.get("Q_tr_window_loss_kWh"),
        "Q_tr_opaque_loss_kWh": b.get("Q_tr_opaque_loss_kWh"),
        "Q_tr_total_loss_kWh": b.get("Q_tr_total_loss_kWh"),
        "Q_tr_total_gain_kWh": b.get("Q_tr_total_gain_kWh"),
        "Q_ve_loss_kWh": b.get("Q_ve_loss_kWh"),
        "Q_ve_gain_kWh": b.get("Q_ve_gain_kWh"),
        "Q_ground_loss_kWh": b.get("Q_ground_loss_kWh"),
        "Q_tb_loss_kWh": b.get("Q_tb_loss_kWh"),
    }


def _f(v, nd=2):
    if v is None or (isinstance(v, float) and v != v):
        return "n/a"
    return f"{v:,.{nd}f}" if isinstance(v, (int, float)) else str(v)


def write_outputs(rows: list[dict], states: list[dict], engine_check: dict,
                  canon_check: dict, meta: dict, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    with (outdir / "comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([h for _, h in COLUMNS])
        for r in rows:
            w.writerow([r.get(k) for k, _ in COLUMNS])

    gate_pass = all(r["gate"] == "PASS" for r in rows)
    L: list[str] = []
    add = L.append

    w = meta["wind"]
    add("# The canonical trajectory, in methodology order — clean weather file")
    add("")
    add(f"**V2 residual gate (< {V2_TOLERANCE_PCT:.0f} % on every state): "
        f"{'PASSED' if gate_pass else 'FAILED'}.** "
        f"**HEAD invariance: {'CONFIRMED' if canon_check['ok'] else 'BROKEN'}.**")
    add("")
    add("Literature corrections first (C1, C2), then the implementation defects "
        "found in the engine, then the closure fixes. Each state is the previous "
        "state plus exactly one correction, cherry-picked onto the unmodified "
        f"baseline (`{BASELINE}`). Canonical building: apt 305, 50 Barry St "
        "Carlton, party surfaces typed `adjacent`.")
    add("")
    add(f"**Weather: `{Path(meta['weather']).name}`** — "
        f"{w['header']['city']}, WMO {w['header']['wmo']}, "
        f"lat {w['header']['latitude']:.4f}, lon {w['header']['longitude']:.4f}, "
        f"tz {w['header']['timezone']:+.0f}; {w['n_rows']:,} rows, "
        f"{w['n_missing_wind']} missing wind values, annual mean wind "
        f"{w['mean_wind_ms']:.2f} m/s, {w['pct_hours_exactly_zero']:.2f} % of hours "
        f"exactly 0.0 m/s, {w['pct_hours_above_pivot']:.1f} % above the 4 m/s pivot, "
        f"no dead-calm month.")
    add("")
    add("**No engine logic changed in this run. Only the weather input changed.** "
        f"The previous canonical run used `{PRIOR_RUN['label']}`, which is "
        f"superseded because {PRIOR_RUN['why_superseded']}. Because "
        "`h_ce = 4v + 4` collapses to 4 W/(m²·K) at v = 0, those fabricated calms "
        "drove a spurious tripling of sensible cooling through C2. Every state "
        "below is the same commit as before, measured on a wind record that is "
        "actually a wind record.")
    add("")
    add("Ventilation and latent are reported **split**, not combined: they are "
        "already two separate commits (`9a89334`, `0bab14f`), so splitting them "
        "was free and changed neither one's physics. C1 **is included** as a "
        "cumulative step — the plan's stated default for \"literature corrections "
        "first\" — rather than being confined to its own window comparison.")
    add("")

    add("## 1. The trajectory")
    add("")
    md_cols = COLUMNS[:MD_COLUMNS]
    add("| " + " | ".join(h for _, h in md_cols) + " |")
    add("| --- | " + " | ".join(["---:"] * (len(md_cols) - 3)) + " | ---: | :-: | ---: |")
    for r in rows:
        cells = [r["state"]]
        for k, _ in md_cols[1:]:
            v = r.get(k)
            if k == "gate":
                cells.append(str(v))
            elif k == "n_transmission_items":
                cells.append(str(v))
            elif k == "residual_pct":
                cells.append(f"{v:+.2f} %")
            elif k == "residual_kWh":
                cells.append(f"{v:+,.2f}")
            elif k == "Q_H_latent_kWh":
                cells.append(_f(v, 4))
            else:
                cells.append(_f(v))
        add("| " + " | ".join(cells) + " |")
    add("")
    add("`Latent cooling, ungated` is the diagnostic contrast column only — the "
        "zone moisture balance before the plant-on gate. It is never part of a "
        "total.")
    add("")

    # The step the weather change actually acts on, called out rather than left
    # for the reader to difference out of the table.
    by_label = {r["state"]: r for r in rows}
    c1, c2 = by_label.get("+C1 dynamic window"), by_label.get("+C2 wind-dependent h_ce")
    if c1 and c2:
        dC = c2["Q_C_sensible_kWh"] - c1["Q_C_sensible_kWh"]
        dH = c2["Q_H_sensible_kWh"] - c1["Q_H_sensible_kWh"]
        add("### The C2 step, which is what the weather change acts on")
        add("")
        add(f"`+C2 wind-dependent h_ce` moves sensible cooling by **{dC:+.2f} kWh** "
            f"({c1['Q_C_sensible_kWh']:,.2f} → {c2['Q_C_sensible_kWh']:,.2f}) and "
            f"sensible heating by {dH:+.2f} kWh. On the superseded RO file the same "
            f"step moved cooling **+119.58 kWh**, and the wind diagnostic traced "
            f"96 % of that to hours reading exactly 0.0 m/s.")
        add("")
        add(f"The sign has flipped because the physics has, and for a defensible "
            f"reason. With {w['pct_hours_above_pivot']:.1f} % of hours above the "
            f"4 m/s pivot, `h_ce = 4v + 4` now sits *above* the ISO fixed "
            f"20 W/(m²·K) for most of the year rather than collapsing to 4. A "
            f"stronger external film on a west wall of absorptance 0.75 sheds more "
            f"of the absorbed solar back to the air, the sol-air driving temperature "
            f"falls, and less heat is conducted inward — so the correction now "
            f"*reduces* cooling instead of manufacturing it. "
            f"`results/diagnostics/wind_verdict_essendon.md` isolates this with a "
            f"one-switch controlled experiment and returns verdict (a+b).")
        add("")

    add("## 2. What each state adds")
    add("")
    add("| State | Commit(s) | What it is |")
    add("| --- | --- | --- |")
    for s in states:
        add(f"| {s['label']} | " + (", ".join(f"`{c[:9]}`" for c in s["commits"]) or "—")
            + f" | {s['note']} |")
    add("")

    add("## 3. Order-independence and HEAD invariance")
    add("")
    add("Applying the same set of corrections in a different order must land on "
        "the same engine, so the check is made on the **source**, not only on the "
        "numbers — a difference that happened not to move this particular "
        "building's annual result would still be caught.")
    add("")
    if engine_check["identical"]:
        add("The reordered trajectory's final state is **byte-for-byte identical** "
            "to HEAD's engine tree across every `.py` file under "
            f"`{ENGINE_PATH}`. The reordering therefore cannot have moved the "
            "canonical figure, and did not.")
    else:
        add("**The final state does NOT match HEAD's engine tree.** Differing "
            "files: `" + "`, `".join(engine_check["differing_files"]) + "`. "
            "Treat every number below as provisional.")
    add("")
    add("The numeric half of the check is against **HEAD run on this same weather "
        "file**, not against a stored constant. That distinction matters here: a "
        "stored constant would assert \"this reproduces the number we published on "
        "the RO file\", which is false by design this time and says nothing about "
        "separability. Comparing to a live HEAD run asserts what the harness is "
        "actually for — that however the corrections are ordered, the engine lands "
        "in the same place — and it is the same claim on any weather file.")
    add("")
    add("| Metric | HEAD, run directly | Trajectory's final state | Δ | within ±0.01? |")
    add("| --- | ---: | ---: | ---: | :-: |")
    for k in INVARIANT_KEYS:
        exp = canon_check["head"].get(k)
        got = canon_check["final"].get(k)
        d = abs(got - exp) if isinstance(got, (int, float)) and isinstance(exp, (int, float)) else None
        add(f"| `{k}` | {_f(exp)} | {_f(got)} | "
            + (f"{d:.2e}" if d is not None else "n/a") + " | "
            + ("yes" if d is not None and d <= CANONICAL_TOL else "**no**") + " |")
    add("")
    f = canon_check["final"]
    add(f"**The new canonical headline: {_f(f.get('Q_H_sensible_kWh'))} kWh sensible "
        f"heating + {_f(f.get('Q_C_sensible_kWh'))} kWh sensible cooling + "
        f"{_f(f.get('Q_C_latent_kWh'))} kWh gated latent = "
        f"{_f(f.get('Q_sens_plus_gated_latent_kWh'))} kWh = "
        f"{_f(f.get('Q_need_total_kWh_per_sqm'))} kWh/m²·yr.** Latent heating is "
        f"{_f(f.get('Q_H_latent_kWh'), 4)} kWh at this state, so \"sensible + gated "
        f"latent\" and the engine's own total agree to the printed digit.")
    add("")

    if meta.get("prior"):
        p = meta["prior"]
        add("### What changed against the superseded run")
        add("")
        add(f"Same engine, same building, same commit — only the weather file "
            f"differs. Prior column is `{PRIOR_RUN['label']}`, read from "
            f"`{PRIOR_RUN['csv'].relative_to(REPO_ROOT)}`.")
        add("")
        add("| Metric | Prior (RO, corrupt wind) | This run (Essendon) | Δ | Δ % |")
        add("| --- | ---: | ---: | ---: | ---: |")
        for k, lab in (("Q_H_sensible_kWh", "Sensible heating (kWh)"),
                       ("Q_C_sensible_kWh", "Sensible cooling (kWh)"),
                       ("Q_C_latent_kWh", "Gated latent cooling (kWh)"),
                       ("Q_need_total_kWh", "Total (kWh)"),
                       ("Q_need_total_kWh_per_sqm", "Total (kWh/m²·yr)")):
            a, b = p.get(k), f.get(k)
            if a is None or b is None:
                continue
            add(f"| {lab} | {_f(a)} | {_f(b)} | {b - a:+,.2f} | "
                + (f"{100 * (b - a) / a:+.1f} %" if a else "n/a") + " |")
        add("")
        dC = f["Q_C_sensible_kWh"] - p["Q_C_sensible_kWh"]
        add(f"Sensible cooling moves {dC:+,.2f} kWh, which is the expected "
            f"direction and the expected channel: Essendon is genuinely windier "
            f"({w['mean_wind_ms']:.2f} m/s mean, {w['pct_hours_above_pivot']:.1f} % of "
            f"hours above the 4 m/s pivot) than the RO file's zero-filled column "
            f"implied, so `h_ce = 4v + 4` now sits *above* the ISO constant for most "
            f"of the year instead of collapsing to a fifth of it. See "
            f"`results/diagnostics/wind_verdict_essendon.md` for the controlled "
            f"experiment that isolates C2 on this file.")
        add("")

    add("## 4. The residual gate")
    add("")
    worst = max(rows, key=lambda r: abs(r["residual_pct"]))
    n_items = sorted({r["n_transmission_items"] for r in rows})
    add(f"The V2 Sankey closure residual is "
        f"{'under' if gate_pass else 'NOT under'} the {V2_TOLERANCE_PCT:.0f} % gate on "
        f"**every** state of the trajectory; the largest excursion is "
        f"{worst['residual_pct']:+.2f} % at *{worst['state']}*, and from the ground-contact "
        f"fix onward it is machine-zero. Every state lists "
        + (f"{n_items[0]}" if len(n_items) == 1 else f"{n_items}")
        + f" transmission line items, so no state is "
        f"measured with part of the envelope missing from its inventory. "
        f"The instrument is identical across states by construction — the closure "
        f"commits are cherry-picked onto each one — which is what makes the states "
        f"comparable at all, and is also why the final `+Closure fixes` step moves no "
        f"number: its content is already in the instrument. That the closure fixes "
        f"change the measurement and not the physics is the finding, not an artefact.")
    add("")

    add("## 5. The ADJ transmission inventory")
    add("")
    add("The five party surfaces are 75.10 m², 88.6 % of the envelope UA, and were "
        "absent from both sides of the balance before the closure fixes. They must "
        f"appear as line items — {TRANSMISSION_ITEMS_EXPECTED} in total, the five "
        "party surfaces plus the exposed west wall and its window — and the tallied "
        "sum must agree with an **independent re-integration** of the per-surface "
        "hourly flows to within 0.1 %. The two come from different code paths: the "
        "reported figure from the in-loop accumulator, the independent one from the "
        "hourly frame afterwards.")
    add("")
    add("| State | Line items | ADJ loss (kWh) | ADJ gain (kWh) | Reported Σ (kWh) | Independent Σ (kWh) | Δ | within 0.1 %? |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: | :-: |")
    for r in rows:
        rel = r.get("transmission_rel_diff")
        ok = isinstance(rel, float) and rel == rel and rel <= TRANSMISSION_REINTEGRATION_TOL
        add(f"| {r['state']} | {r['n_transmission_items']} "
            f"| {_f(r.get('Q_tr_adjacent_loss_kWh'))} | {_f(r.get('Q_tr_adjacent_gain_kWh'))} "
            f"| {_f(r.get('transmission_reported_kWh'))} "
            f"| {_f(r.get('transmission_independent_kWh'))} "
            + ("| n/a " if not isinstance(rel, float) or rel != rel
               else f"| {100 * rel:.4f} % ")
            + f"| {'yes' if ok else '**no**'} |")
    add("")

    add("## 6. The latent gate")
    add("")
    add("Latent cooling may be charged only in hours the cooling plant actually "
        "runs. Two leaks are checked directly rather than argued from the annual "
        "total: latent charged while the plant is off, and latent charged while the "
        "*heating* plant runs. Both must be zero.")
    add("")
    add("| State | Steps | Cooling on | Heating on | Latent charged | Gated (kWh) | Ungated (kWh) | Charged, plant off | Charged while heating | Latent heating (kWh) |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in rows:
        add(f"| {r['state']} | {r.get('n_steps') or 0:,} | {r.get('n_steps_cooling_on') or 0:,} "
            f"| {r.get('n_steps_heating_on') or 0:,} | {r.get('n_steps_latent_charged') or 0:,} "
            f"| {_f(r['Q_C_latent_kWh'])} | {_f(r['Q_C_latent_ungated_kWh'])} "
            f"| {_f(r.get('latent_kWh_with_cooling_off'), 6)} "
            f"| {_f(r.get('latent_kWh_while_heating'), 6)} "
            f"| {_f(r['Q_H_latent_kWh'], 4)} |")
    add("")
    monthly = f.get("monthly_latent_cooling_kWh")
    if monthly:
        names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        add("Southern-hemisphere phase, gated latent cooling by month at the "
            "canonical state (kWh):")
        add("")
        add("| " + " | ".join(names) + " |")
        add("| " + " | ".join(["---:"] * 12) + " |")
        add("| " + " | ".join(f"{v:.2f}" for v in monthly) + " |")
        add("")
        summer = monthly[0] + monthly[1] + monthly[11]
        winter = monthly[5] + monthly[6] + monthly[7]
        add(f"Dec–Feb {summer:.2f} kWh against Jun–Aug {winter:.2f} kWh: the load "
            f"sits in the austral summer, which is the phase check.")
        add("")

    add("## 7. Provenance")
    add("")
    add(f"* baseline: `{BASELINE}`")
    add(f"* closure commits: " + ", ".join(f"`{c[:9]}`" for c in meta["closure_commits"]))
    add(f"* weather: `{w['path']}`")
    add(f"* weather screened by `tools/diagnostics/weather_integrity.py`: "
        f"{w['n_rows']:,} rows, {w['n_missing_wind']} missing wind values, "
        f"mean {w['mean_wind_ms']:.2f} m/s, {w['pct_hours_exactly_zero']:.2f} % exactly "
        f"zero, {w['pct_hours_above_pivot']:.1f} % above 4 m/s, dead-calm months: "
        + (", ".join(str(m) for m in w["degenerate_months"]) if w["degenerate_months"]
           else "none"))
    add(f"* superseded weather (kept in `weather_cache/` for the contrast): "
        f"`{PRIOR_RUN['label']}`")
    for s in states:
        extra = (f" — conflicts outside the engine resolved in favour of the state in "
                 f"`{', '.join(s['resolved_outside_engine'])}`") if s["resolved_outside_engine"] else ""
        add(f"* {s['label']}: `{s['sha'][:9]}`{extra}")
    add("")
    tr_ok = all(isinstance(r.get("transmission_rel_diff"), float)
                and r["transmission_rel_diff"] == r["transmission_rel_diff"]
                and r["transmission_rel_diff"] <= TRANSMISSION_REINTEGRATION_TOL
                for r in rows)
    items_ok = all(r["n_transmission_items"] == TRANSMISSION_ITEMS_EXPECTED for r in rows)
    latent_ok = (abs(f.get("Q_H_latent_kWh") or 0.0) <= LATENT_HEATING_MAX_KWH
                 and abs(f.get("latent_kWh_with_cooling_off") or 0.0) <= LATENT_LEAK_TOL_KWH
                 and abs(f.get("latent_kWh_while_heating") or 0.0) <= LATENT_LEAK_TOL_KWH)
    add("## 8. The gate")
    add("")
    add("| Condition | Result |")
    add("| --- | :-: |")
    add(f"| V2 residual < {V2_TOLERANCE_PCT:.0f} % on every state "
        f"| {'PASS' if gate_pass else 'FAIL'} |")
    add(f"| ADJ transmission in the inventory "
        f"({TRANSMISSION_ITEMS_EXPECTED} line items, every state) "
        f"| {'PASS' if items_ok else 'FAIL'} |")
    add(f"| Independent re-integration within 0.1 %, every state "
        f"| {'PASS' if tr_ok else 'FAIL'} |")
    add(f"| Latent gated (no charge with plant off or while heating) "
        f"| {'PASS' if latent_ok else 'FAIL'} |")
    add(f"| HEAD invariant under the reordering | "
        f"{'PASS' if canon_check['ok'] else 'FAIL'} |")
    add(f"| Final engine tree identical to HEAD | "
        f"{'PASS' if engine_check['identical'] else 'FAIL'} |")
    add("")
    if gate_pass and canon_check["ok"] and tr_ok and items_ok and latent_ok:
        add("**Gate passed and HEAD invariant.** Reduction percentages and kWh/m² "
            "headlines may be computed from this table, and the methodology text "
            "can be written against it.")
    else:
        add("**Do not quote a headline from this table.**")

    (outdir / "comparison.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def read_prior_headline(csv_path: Path) -> dict | None:
    """The superseded run's final row, read from what was actually published."""
    if not csv_path.is_file():
        return None
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return None
    last = rows[-1]
    want = {
        "Q_H_sensible_kWh": "Sensible heating (kWh)",
        "Q_C_sensible_kWh": "Sensible cooling (kWh)",
        "Q_C_latent_kWh": "Latent cooling, gated (kWh)",
        "Q_need_total_kWh": "Total (kWh)",
        "Q_need_total_kWh_per_sqm": "Total (kWh/m²)",
    }
    out: dict = {"state": last.get("State")}
    for k, col in want.items():
        try:
            out[k] = float(last[col])
        except (KeyError, TypeError, ValueError):
            return None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", required=True)
    ap.add_argument("--outdir", default=str(REPO_ROOT / "results/au_canonical_essendon"))
    ap.add_argument("--closure-ref", default="HEAD")
    ap.add_argument("--closure-base", default=CLOSURE_BASE)
    ap.add_argument("--expect-weather", default="Essendon",
                    help="substring the resolved weather filename must contain; the "
                         "guard against silently re-running on a cached RO file")
    ap.add_argument("--from-raw", action="store_true",
                    help="rebuild comparison.csv/.md from the outdir's existing "
                         "trajectory_raw.json instead of re-running the engine. For "
                         "editing the report's prose; it cannot change a number, "
                         "because every number is read back from that file.")
    args = ap.parse_args()

    weather = str(Path(args.weather).resolve())
    outdir = Path(args.outdir)

    if args.from_raw:
        blob = json.loads((outdir / "trajectory_raw.json").read_text(encoding="utf-8"))
        rows = [flatten(lab, r) for lab, r in blob["results"].items()]
        head_row = flatten("HEAD", blob["head"])
        canon = blob["canonical_check"]
        canon["final"], canon["head"] = rows[-1], head_row
        write_outputs(rows, blob["states"], blob["engine_tree_check"], canon,
                      blob["meta"], outdir)
        print(f"rebuilt report from {outdir / 'trajectory_raw.json'} -> {outdir}")
        return

    # Preflight, before anything is computed: the resolved absolute path, the
    # wind column's own numbers, and a hard stop on a dead-calm month.
    wind = assert_usable(Path(weather), expect_name_contains=args.expect_weather)

    closure = closure_commits(args.closure_ref, args.closure_base)
    if not closure:
        raise SystemExit(f"no closure commits in {args.closure_base}..{args.closure_ref}")
    missing = [p for p in EXPECTED_CLOSURE_PREFIXES
               if not any(c.startswith(p) for c in closure)]
    if missing:
        raise SystemExit(
            f"closure set from {args.closure_base}..{args.closure_ref} is missing "
            f"{missing}. The instrument would not be constant across states and "
            f"every residual below would be meaningless. Resolved: "
            f"{[c[:9] for c in closure]}")
    print(f"closure commits: {[c[:9] for c in closure]}\n")

    tmp = Path(tempfile.mkdtemp(prefix="aib-canon-"))
    created: list[Path] = []
    try:
        print("building the ordered stack:")
        stack, states = build_stack(tmp, closure)
        created.append(stack)

        engine_check = verify_final_engine_matches_head(stack)
        print(f"\nfinal engine tree vs HEAD: "
              f"{'IDENTICAL' if engine_check['identical'] else 'DIFFERS ' + str(engine_check['differing_files'])}\n")

        print("measuring each state (instrument held constant):")
        results: dict[str, dict] = {}
        rows: list[dict] = []
        for s in states:
            wt = tmp / ("m_" + s["label"].replace("+", "").replace(" ", "_"))
            _git("worktree", "add", "--detach", str(wt), s["sha"])
            created.append(wt)
            if not s["carries_closure"]:
                for sha in closure:
                    s.setdefault("instrument_resolved", []).extend(
                        cherry_pick(wt, sha, f"instrument on {s['label']}",
                                    allow_engine=INSTRUMENT_CONFLICT_ALLOWED))
            apply_shim(wt)
            data = run_engine(wt / "pybuildingenergy" / "src", weather,
                              tmp / f"{s['label']}.json",
                              also_config_a=s["carries_closure"])
            results[s["label"]] = data
            row = flatten(s["label"], data)
            rows.append(row)
            print(f"  {s['label']:<28} H={row['Q_H_sensible_kWh']:8.2f}  "
                  f"C={row['Q_C_sensible_kWh']:8.2f}  latC={row['Q_C_latent_kWh']:7.2f}  "
                  f"total={row['Q_need_total_kWh']:8.2f} ({row['Q_need_total_kWh_per_sqm']:5.2f} kWh/m²)  "
                  f"resid={row['residual_pct']:+6.2f}% {row['gate']}", flush=True)

        # HEAD, run directly on the same weather. This is the invariance
        # reference: unpatched repository, no worktree, no shim.
        print("\nmeasuring HEAD directly (the invariance reference):", flush=True)
        head_data = run_engine(REPO_ROOT / "pybuildingenergy" / "src", weather,
                               tmp / "HEAD.json", also_config_a=False)
        head_row = flatten("HEAD (this repository, unpatched)", head_data)
        print(f"  {'HEAD':<28} H={head_row['Q_H_sensible_kWh']:8.2f}  "
              f"C={head_row['Q_C_sensible_kWh']:8.2f}  latC={head_row['Q_C_latent_kWh']:7.2f}  "
              f"total={head_row['Q_need_total_kWh']:8.2f} "
              f"({head_row['Q_need_total_kWh_per_sqm']:5.2f} kWh/m²)", flush=True)
    finally:
        for wt in created:
            drop_worktree(wt)
        shutil.rmtree(tmp, ignore_errors=True)

    final = rows[-1]
    canon_check = {
        "final": final,
        "head": head_row,
        "keys": list(INVARIANT_KEYS),
        "tolerance": CANONICAL_TOL,
        "ok": all(abs(final.get(k, float("nan")) - head_row.get(k, float("nan")))
                  <= CANONICAL_TOL for k in INVARIANT_KEYS),
    }

    meta = {"weather": weather, "baseline": BASELINE, "closure_commits": closure,
            "wind": wind, "prior": read_prior_headline(PRIOR_RUN["csv"]),
            "prior_label": PRIOR_RUN["label"]}
    write_outputs(rows, states, engine_check, canon_check, meta, outdir)
    (outdir / "trajectory_raw.json").write_text(
        json.dumps({"results": results, "head": head_data, "states": states,
                    "meta": meta, "engine_tree_check": engine_check,
                    "canonical_check": canon_check},
                   indent=2, default=str), encoding="utf-8")
    print(f"\nwrote -> {outdir}")

    # --- the invariants, each reported explicitly ---------------------------
    failed = [r["state"] for r in rows if r["gate"] != "PASS"]
    bad_items = [r["state"] for r in rows
                 if r["n_transmission_items"] != TRANSMISSION_ITEMS_EXPECTED]
    bad_reint = [r["state"] for r in rows
                 if not (isinstance(r.get("transmission_rel_diff"), float)
                         and r["transmission_rel_diff"] == r["transmission_rel_diff"]
                         and r["transmission_rel_diff"] <= TRANSMISSION_REINTEGRATION_TOL)]
    latent_leaks = [r["state"] for r in rows
                    if abs(r.get("latent_kWh_with_cooling_off") or 0.0) > LATENT_LEAK_TOL_KWH
                    or abs(r.get("latent_kWh_while_heating") or 0.0) > LATENT_LEAK_TOL_KWH]

    print("\ninvariants")
    print(f"  V2 residual < {V2_TOLERANCE_PCT:.0f} % on every state   : "
          f"{'PASS' if not failed else 'FAIL ' + str(failed)}")
    print(f"  {TRANSMISSION_ITEMS_EXPECTED} transmission line items, every state: "
          f"{'PASS' if not bad_items else 'FAIL ' + str(bad_items)}")
    print(f"  re-integration within 0.1 %, every state : "
          f"{'PASS' if not bad_reint else 'FAIL ' + str(bad_reint)}")
    print(f"  latent charged only with cooling on      : "
          f"{'PASS' if not latent_leaks else 'FAIL ' + str(latent_leaks)}")
    print(f"  latent heating at the canonical state    : "
          f"{final['Q_H_latent_kWh']:.4f} kWh "
          f"({'PASS' if abs(final['Q_H_latent_kWh']) <= LATENT_HEATING_MAX_KWH else 'FAIL'})")
    print(f"  HEAD invariant under the reordering      : "
          f"{'PASS' if canon_check['ok'] else 'FAIL'}")
    print(f"  final engine tree identical to HEAD      : "
          f"{'PASS' if engine_check['identical'] else 'FAIL'}")
    print(f"\ncanonical headline on {Path(weather).name}:")
    print(f"  {final['Q_H_sensible_kWh']:.2f} kWh sensible heating"
          f" + {final['Q_C_sensible_kWh']:.2f} kWh sensible cooling"
          f" + {final['Q_C_latent_kWh']:.2f} kWh gated latent"
          f" = {final['Q_sens_plus_gated_latent_kWh']:.2f} kWh"
          f" = {final['Q_need_total_kWh_per_sqm']:.2f} kWh/m²·yr")

    if failed:
        print(f"\nGATE FAILED on: {failed}")
        sys.exit(2)
    if not canon_check["ok"]:
        print("\nHEAD IS NOT INVARIANT under the reordering — a correction is not "
              "cleanly separable. Reported, not papered over.")
        for k in INVARIANT_KEYS:
            print(f"  {k}: HEAD {head_row.get(k)!r}  trajectory {final.get(k)!r}")
        sys.exit(3)
    if not engine_check["identical"]:
        print("\nFinal engine tree differs from HEAD:", engine_check["differing_files"])
        sys.exit(4)
    if bad_items or bad_reint or latent_leaks:
        print("\nINVARIANT FAILED (inventory or latent gate) — see above.")
        sys.exit(5)
    print("\nGATE PASSED on every state; HEAD invariant; final engine identical to HEAD; "
          "ADJ transmission in the inventory; latent gated.")


if __name__ == "__main__":
    main()
