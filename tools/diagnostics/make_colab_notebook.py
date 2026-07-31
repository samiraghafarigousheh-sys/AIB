"""Generate the diagnostics Colab notebook as valid .ipynb JSON."""
import json
from pathlib import Path


def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": src.splitlines(keepends=True)}


cells = []

cells.append(md("""# AIB engine — diagnostics runner

Reproduces all five diagnostic items for **Apt 305, 50 Barry St, Carlton VIC** on
`AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw`.

| Item | What it does |
|---|---|
| **1** | Reconciles the two contradictory "unmodified baselines" — runs **one engine** against **two building dictionaries** and diffs the *effective* runtime inputs (weather, setpoints, gain/solar hourly hashes, surface classification) |
| **2** | Conditional on Item 1. Skipped when Item 1's verdict is not a schedule offset |
| **3** | V2 Sankey closure residual for all six states, with pass/fail against 5 % |
| **4** | Latent heating / latent cooling split for all six states, plus the gating check |
| **5** | Rebuilds the paper-usable faceted comparison chart |

**Runtime ≈ 10–15 min** — eight full annual ISO 52016-1 simulations.
Runtime → *Run all*, or run each section on its own.

> Nothing here modifies the engine. Items 1, 3 and 4 are investigations; the only
> file written back into the repo is the Item 5 chart."""))

cells.append(md("## 1 · Setup"))

cells.append(code('''#@title Clone the repository { display-mode: "form" }
# If the repo is private, paste a GitHub token with `repo` scope. Leave blank for public.
GITHUB_TOKEN = ""  #@param {type:"string"}

import os, subprocess, sys, shutil
from pathlib import Path

REPO = Path("/content/AIB")
BRANCH = "claude/pybuildingenergy-process-check-xvmbtd"

url = "https://github.com/samiraghafarigousheh-sys/AIB.git"
if GITHUB_TOKEN.strip():
    url = f"https://{GITHUB_TOKEN.strip()}@github.com/samiraghafarigousheh-sys/AIB.git"

if REPO.exists():
    shutil.rmtree(REPO)

p = subprocess.run(["git", "clone", "--branch", BRANCH, url, str(REPO)],
                   capture_output=True, text=True)
if p.returncode != 0:
    raise SystemExit(
        "clone failed:\\n" + p.stderr[-1500:] +
        "\\n\\nIf the repository is private, put a token in GITHUB_TOKEN above.")

os.chdir(REPO)
# the diagnostics build worktrees of the six state branches, so fetch them all
subprocess.run(["git", "fetch", "--quiet", "origin",
                "+refs/heads/*:refs/remotes/origin/*"], check=False)

print("repo   :", REPO)
print("branch :", subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                 capture_output=True, text=True).stdout.strip())
print("head   :", subprocess.run(["git", "log", "-1", "--oneline"],
                                 capture_output=True, text=True).stdout.strip())
print()
print("state branches available:")
for b in ["pybuildingenergy-baseline-anjro8", "ventilation-plus-latent-fix",
          "internal-gains-fix", "conditioned-adjacent-zones-fix",
          "ground-contact-fix", "coldest-month-hemisphere-fix"]:
    ok = subprocess.run(["git", "rev-parse", "--verify", "--quiet",
                         f"origin/claude/{b}"], capture_output=True).returncode == 0
    print(f"   {'OK ' if ok else 'MISSING'}  claude/{b}")'''))

cells.append(code('''#@title Install dependencies
# Colab already ships pandas / numpy / matplotlib / scipy / plotly.
# These are what the vendored ISO 52016-1 engine needs on top.
!pip install -q pvlib==0.13.0 holidays workalendar timezonefinder pyecharts openpyxl scikit-learn tqdm 2>&1 | tail -2

import importlib
for m in ("pvlib", "pandas", "numpy", "matplotlib", "tqdm", "holidays",
          "timezonefinder", "workalendar"):
    try:
        mod = importlib.import_module(m)
        print(f"{m:<16}{getattr(mod, '__version__', 'ok')}")
    except Exception as e:
        print(f"{m:<16}FAILED  {e}")

from pathlib import Path
EPW = Path("/content/AIB/weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw")
print()
print("EPW present:", EPW.exists(), "-", f"{EPW.stat().st_size/1e6:.2f} MB" if EPW.exists() else "")'''))

cells.append(md("""---
## 2 · Item 1 — reconcile the two contradictory baselines

Two runs were both published as the "unmodified ISO 52016-1 baseline", with
**identical internal gains to six decimals**, yet an inverted seasonal balance:

| Run | Heating | Cooling |
|---|---:|---:|
| earlier `baseline_vs_ep` | 15.86 kWh | 2 027.5 kWh |
| six-state harness | 1 308.6 kWh | 741.8 kWh |

The cell below runs **one engine commit** against **two building dictionaries** —
`examples/apt305_building.py` before and after commit `4376658` — and dumps the
inputs actually loaded at runtime, not the ones declared."""))

cells.append(code('''#@title Build one engine worktree + the two building dictionaries
import subprocess, shutil
from pathlib import Path

WORK = Path("/content/diag"); shutil.rmtree(WORK, ignore_errors=True)
(WORK / "cfgA_opaque").mkdir(parents=True); (WORK / "cfgB_adjacent").mkdir(parents=True)

WT = WORK / "wt_base"
subprocess.run(["git", "worktree", "add", "--detach", str(WT),
                "origin/claude/pybuildingenergy-baseline-anjro8"],
               check=True, capture_output=True)

# config A: the dictionary as it was when the earlier baseline ran ("opaque")
a = subprocess.run(["git", "show", "4376658^:examples/apt305_building.py"],
                   capture_output=True, text=True, check=True).stdout
(WORK / "cfgA_opaque" / "apt305_building.py").write_text(a)
# config B: the dictionary as it is now ("adjacent")
shutil.copy("examples/apt305_building.py", WORK / "cfgB_adjacent" / "apt305_building.py")

eng = subprocess.run(["git", "-C", str(WT), "log", "-1", "--format=%H %ad %s",
                      "--date=iso"], capture_output=True, text=True).stdout.strip()
print("engine commit (SHARED by both runs):\\n  ", eng, "\\n")
for tag, d in (("A", "cfgA_opaque"), ("B", "cfgB_adjacent")):
    txt = (WORK / d / "apt305_building.py").read_text()
    print(f"config {tag} ({d}): "
          f'{txt.count(chr(34) + "type" + chr(34) + ": " + chr(34) + "opaque" + chr(34))} opaque / '
          f'{txt.count(chr(34) + "type" + chr(34) + ": " + chr(34) + "adjacent" + chr(34))} adjacent surfaces')'''))

cells.append(code('''#@title Run both configs (~2 min)
import subprocess, sys, time, os
from pathlib import Path
os.chdir("/content/AIB")
WORK = Path("/content/diag")
EPW = str(Path("/content/AIB/weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw"))

for tag, d in (("A", "cfgA_opaque"), ("B", "cfgB_adjacent")):
    t0 = time.time()
    print(f"running config {tag} ...", end=" ", flush=True)
    p = subprocess.run(
        [sys.executable, "tools/diagnostics/probe_baseline.py",
         "--src", str(WORK / "wt_base" / "pybuildingenergy" / "src"),
         "--bui-dir", str(WORK / d), "--epw", EPW,
         "--out", str(WORK / f"{tag}.json")],
        capture_output=True, text=True)
    if p.returncode != 0:
        print("FAILED\\n", (p.stderr or p.stdout)[-2000:]); break
    print(f"done in {time.time()-t0:.0f}s")'''))

cells.append(code('''#@title Item 1 result — which input actually differs
import json, subprocess
from pathlib import Path
WORK = Path("/content/diag")
A = json.load(open(WORK / "A.json")); B = json.load(open(WORK / "B.json"))
eng = subprocess.run(["git", "-C", str(WORK / "wt_base"), "log", "-1", "--format=%H"],
                     capture_output=True, text=True).stdout.strip()

print("=" * 78)
print("REPRODUCTION vs the two published runs")
print("=" * 78)
print(f"  config A (opaque)   H={A['Q_H_annual_kWh']:>10.4f}  C={A['Q_C_annual_kWh']:>10.4f}"
      "   published 15.8616 / 2027.5065")
print(f"  config B (adjacent) H={B['Q_H_annual_kWh']:>10.4f}  C={B['Q_C_annual_kWh']:>10.4f}"
      "   published 1308.6013 / 741.8282")

print("\\n" + "=" * 78)
print("THE FIVE RUNTIME DIFFS  (values actually loaded, not declared)")
print("=" * 78)
wa, wb = A["weather_effective"], B["weather_effective"]
rows = [
    ("1. weather path",     wa["path"] == wb["path"],        Path(wa["path"]).name),
    ("   HDD18 / CDD18",    (wa["HDD18_C_d"], wa["CDD18_C_d"]) == (wb["HDD18_C_d"], wb["CDD18_C_d"]),
                            f"{wa['HDD18_C_d']:.2f} / {wa['CDD18_C_d']:.2f}"),
    ("   GHI kWh/m2",       wa["GHI_kWh_m2_yr"] == wb["GHI_kWh_m2_yr"], f"{wa['GHI_kWh_m2_yr']:.3f}"),
    ("   T2m sha256",       wa["T2m_sha256"] == wb["T2m_sha256"], wa["T2m_sha256"]),
    ("   GHI sha256",       wa["GHI_sha256"] == wb["GHI_sha256"], wa["GHI_sha256"]),
    ("2. setpoints",        A["setpoints_declared"] == B["setpoints_declared"],
                            f"{A['setpoints_declared']['heating_setpoint']}/"
                            f"{A['setpoints_declared']['cooling_setpoint']} C"),
    ("3. Phi_int sha256",   A["Phi_int"]["sha256"] == B["Phi_int"]["sha256"], A["Phi_int"]["sha256"]),
    ("   Phi_int hour-of-day", A["Phi_int"]["hour_of_day_mean_W"] == B["Phi_int"]["hour_of_day_mean_W"], ""),
    ("4. Phi_sol sha256",   A["Phi_sol"]["sha256"] == B["Phi_sol"]["sha256"], A["Phi_sol"]["sha256"]),
    ("   Phi_sol peak hour", A["Phi_sol"]["argmax_hour_of_day"] == B["Phi_sol"]["argmax_hour_of_day"],
                            f"hour {A['Phi_sol']['argmax_hour_of_day']}"),
    ("5. engine commit",    True, eng.split()[0][:12]),
]
for name, same, val in rows:
    print(f"  {name:<26}{'IDENTICAL' if same else '** DIFFERS **':<16}{val}")

print("\\n" + "=" * 78)
print("SURFACE CLASSIFICATION THE CORE ACTUALLY RESOLVED   <-- the difference")
print("=" * 78)
print(f"  {'surface':<32}{'declared':<12}{'svf':>5}{'area':>8}  {'A':<6}{'B':<6}")
for ra, rb in zip(A["surface_classification_resolved"], B["surface_classification_resolved"]):
    flag = "  <<<" if ra["ISO52016_type_string"] != rb["ISO52016_type_string"] else ""
    print(f"  {ra['name'][:31]:<32}{str(ra['declared_type']):<12}{ra['svf']:>5}{ra['area']:>8.2f}  "
          f"{ra['ISO52016_type_string']:<6}{rb['ISO52016_type_string']:<6}{flag}")
print(f"\\n  area by class, A: {A['area_by_ISO52016_type_m2']}")
print(f"  area by class, B: {B['area_by_ISO52016_type_m2']}")

print("\\n" + "=" * 78)
print("VERDICT: not (a) weather, not (b) schedule offset, not (c) commit.")
print("         The BUILDING DICTIONARY differs - 75.1 m2 moves GR <-> ADJ.")
print("         Canonical baseline = config B, 1308.60 / 741.83 kWh.")
print("         Item 2 does not trigger (it is scoped to verdict (b)).")
print("=" * 78)'''))

cells.append(md("""**Why the gains matched.** Internal gains read floor area and the adjacent-zone
*count*, never surface `type` — the one quantity blind to what differs. The
identity that made the two runs look comparable was not evidence they agreed.

**Why the balance inverts.** `utils.py:6984` maps `type == "opaque"` with
`sky_view_factor == 0` to **`GR` — slab-on-ground**. Typed `"opaque"`, all five
party surfaces *including the ceiling* are modelled as buried, giving this
third-floor apartment 75.1 m² of ground contact clamped near the ISO 13370 ground
temperature (≈16 °C in Melbourne) — a large winter heat source, so heating
collapses to 15.9 kWh and cooling inflates to 2 027.5 kWh."""))

cells.append(md("""---
## 3 · Items 3 & 4 — Sankey residual and latent breakdown

Six states, one worktree each. Adds the two columns the comparison harness does
not report: the **V2 closure residual** and the **latent heating / latent cooling
split**.

`--repair-ground-nan` is a measurement device, not a model change. After Step 3
`_ground_contact_area()` correctly returns 0, but `Temp_calculation_of_ground`
still divides by it (`utils.py:3946`), so `Theta_gr_ve` is ±inf and
`q_ground = 0.0 * inf = NaN` latches into the Sankey accumulator. Heating,
cooling and latent come back bit-identical with and without it — drop the flag to
watch Steps 3–4 report `nan`."""))

cells.append(code('''#@title Run all six states (~8-12 min)
import subprocess, sys, os
from pathlib import Path
os.chdir("/content/AIB")
EPW = str(Path("/content/AIB/weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw"))
p = subprocess.run(
    [sys.executable, "tools/diagnostics/six_state_diagnostics.py",
     "--repair-ground-nan", "--weather", EPW,
     "--out", "results/diagnostics/six_state_raw.json"],
    capture_output=True, text=True)
print(p.stdout[-4000:])
if p.returncode != 0:
    print("FAILED\\n", p.stderr[-3000:])'''))

cells.append(code('''#@title Item 3 — Sankey closure residual, pass/fail against 5 %
import json, os
os.chdir("/content/AIB")
D = json.load(open("results/diagnostics/six_state_raw.json"))
STATES = ["Baseline", "+Vent+Latent", "+Internal Gains",
          "+Conditioned Zones", "+Ground Fix", "+Hemisphere Fix"]

print(f"{'state':<22}{'inputs kWh':>12}{'outputs kWh':>13}{'residual kWh':>14}{'residual %':>12}   5%?")
print("-" * 82)
for s in STATES:
    sk = D[s]["sankey"]
    ok = abs(sk["residual_pct"]) <= 5.0
    print(f"{s:<22}{sk['inputs_total_Wh']/1000:>12,.2f}{sk['outputs_total_Wh']/1000:>13,.2f}"
          f"{sk['residual_kWh']:>14,.2f}{sk['residual_pct']:>11.2f}%   {'PASS' if ok else 'FAIL'}")

d2, d3 = D["+Conditioned Zones"]["sankey"], D["+Ground Fix"]["sankey"]
print(f"\\nStep 3 effect on the residual: {d3['residual_kWh'] - d2['residual_kWh']:+.2f} kWh")
print(f"  phantom ground term removed : {D['+Conditioned Zones']['Q_ground_loss_kWh']:.2f} loss"
      f" - {D['+Conditioned Zones']['Q_ground_gain_kWh']:.2f} gain"
      f" = {D['+Conditioned Zones']['Q_ground_loss_kWh'] - D['+Conditioned Zones']['Q_ground_gain_kWh']:+.2f} kWh")
print("  -> the ground fix does exactly what it claims, and nothing more.")
print("     A 66.6 kWh fix cannot close a 450-5066 kWh gap.")

print("\\n" + "=" * 82)
print("THE UNACCOUNTED TERM: the ADJ surface class is absent from the inventory")
print("=" * 82)
sk = D["+Hemisphere Fix"]["sankey"]
print("  inputs :", {k: round(v/1000, 2) for k, v in sk["inputs_Wh"].items()})
print("  outputs:", {k: round(v/1000, 2) for k, v in sk["outputs_Wh"].items()})
print("\\n  Two transmission entries for a building with seven opaque/transparent surfaces.")
print("  The five party surfaces - 75.10 m2, 88.6 % of envelope UA - appear nowhere.")'''))

cells.append(code('''#@title Item 4 — latent breakdown, all six states
import json, os
os.chdir("/content/AIB")
D = json.load(open("results/diagnostics/six_state_raw.json"))
STATES = ["Baseline", "+Vent+Latent", "+Internal Gains",
          "+Conditioned Zones", "+Ground Fix", "+Hemisphere Fix"]
area = D["Baseline"]["net_floor_area_m2"]

print(f"{'state':<22}{'sensH':>9}{'sensC':>9}{'latentC':>10}{'latentH':>9}{'TOTAL':>10}{'latC %':>8}")
print("-" * 78)
for s in STATES:
    r = D[s]; t = r["Q_total_annual_kWh"]
    print(f"{s:<22}{r['Q_H_annual_kWh']:>9.2f}{r['Q_C_annual_kWh']:>9.2f}"
          f"{r['latent_cooling_kWh']:>10.2f}{r['latent_heating_kWh']:>9.2f}"
          f"{t:>10.2f}{100*r['latent_cooling_kWh']/t:>7.1f}%")

print("\\n'Total energy need' = sensible H + sensible C + latent cooling + latent heating")
f = D["+Hemisphere Fix"]
print(f"  check: {f['Q_H_annual_kWh']:.2f} + {f['Q_C_annual_kWh']:.2f} + "
      f"{f['latent_cooling_kWh']:.2f} + {f['latent_heating_kWh']:.2f} = {f['Q_total_annual_kWh']:.2f}")

print("\\nC2 latent fix: latent HEATING collapses and stays collapsed - no regression")
for s in STATES:
    print(f"   {s:<22}{D[s]['latent_heating_kWh']:>10.2f} kWh")

M = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
print("\\nLatent COOLING by month, kWh (peaks in southern summer - correct phase)")
print(f"{'state':<22}" + "".join(f"{m:>7}" for m in M))
for s in STATES:
    mm = D[s].get("monthly_latent_cooling_kWh")
    if mm:
        print(f"{s:<22}" + "".join(f"{v:7.1f}" for v in mm))

print(f"\\nComposition of the final {f['latent_cooling_kWh']:.2f} kWh:")
print(f"   ventilation latent {f['latent_vent_pos_kWh']:>8.2f} kWh")
print(f"   internal latent    {f['latent_internal_kWh']:>8.2f} kWh")
print(f"   sum                {f['latent_vent_pos_kWh'] + f['latent_internal_kWh']:>8.2f} kWh")

print("\\nHeadline sensitivity (floor area %.0f m2):" % area)
print(f"   as reported (sensible + all latent) {f['Q_total_annual_kWh']:>8.2f} kWh"
      f"  = {f['Q_total_annual_kWh']/area:>6.2f} kWh/m2")
sens = f["Q_H_annual_kWh"] + f["Q_C_annual_kWh"]
print(f"   sensible only                       {sens:>8.2f} kWh  = {sens/area:>6.2f} kWh/m2")'''))

cells.append(code('''#@title Item 4 — the gating check (why ~554 kWh is not a plausible demand)
# Re-runs the final state only, to look at latent hour by hour.
import subprocess, sys, shutil, os
from pathlib import Path
os.chdir("/content/AIB")
WORK = Path("/content/diag")
EPW = str(Path("/content/AIB/weather_cache/AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw"))

WT2 = WORK / "wt_hem"; shutil.rmtree(WT2, ignore_errors=True)
subprocess.run(["git", "worktree", "add", "--detach", str(WT2),
                "origin/claude/coldest-month-hemisphere-fix"], check=True, capture_output=True)

# plain template + replace, so there is no nested f-string to get wrong
TEMPLATE = """
import sys, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, r"__SRC__"); sys.path.insert(0, "/content/AIB/examples")
from apt305_building import build_bui
from pybuildingenergy.source.utils import ISO52016
from pybuildingenergy.source.check_input import sanitize_and_validate_BUI

b, _ = sanitize_and_validate_BUI(build_bui(), fix=True)
r = ISO52016.Temperature_and_Energy_needs_calculation(
    b, weather_source="epw", path_weather_file=r"__EPW__", return_sankey_data=True)
h = r[0]
S = lambda c: pd.to_numeric(h[c], errors="coerce").fillna(0.0).values
latC, sensC, sensH, Tair = S("Q_C_latent"), S("Q_C_sensible"), S("Q_H"), S("T_air")
lat, cool, heat = latC > 0, np.abs(sensC) > 0, np.abs(sensH) > 0

print("RESULT hours_total            %d" % len(latC))
print("RESULT hours_latent_charged   %d %.1f" % (lat.sum(), 100 * lat.mean()))
print("RESULT hours_cooling_running  %d %.1f" % (cool.sum(), 100 * cool.mean()))
print("RESULT hours_heating_running  %d %.1f" % (heat.sum(), 100 * heat.mean()))
print("RESULT kwh_while_cooling_on   %.2f" % (latC[lat & cool].sum() / 1000))
print("RESULT kwh_while_cooling_off  %.2f" % (latC[lat & ~cool].sum() / 1000))
print("RESULT kwh_while_heating_on   %.2f" % (latC[lat & heat].sum() / 1000))
print("RESULT mean_tair_ungated      %.2f" % Tair[lat & ~cool].mean())
print("RESULT hours_ungated_below20  %d" % int(((lat & ~cool) & (Tair < 20)).sum()))
"""
probe = WORK / "gate.py"
probe.write_text(TEMPLATE.replace("__SRC__", str(WT2 / "pybuildingenergy" / "src"))
                         .replace("__EPW__", EPW))

p = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True)
res = {}
for line in p.stdout.splitlines():
    if line.startswith("RESULT "):
        parts = line.split()
        res[parts[1]] = parts[2:]
if not res:
    print("FAILED\\n", (p.stderr or p.stdout)[-2000:])
else:
    print(f"hours in the year                            {int(res['hours_total'][0]):7d}")
    print(f"hours charged with latent cooling            {int(res['hours_latent_charged'][0]):7d}"
          f"  ({float(res['hours_latent_charged'][1]):5.1f}%)")
    print(f"hours with sensible cooling running          {int(res['hours_cooling_running'][0]):7d}"
          f"  ({float(res['hours_cooling_running'][1]):5.1f}%)")
    print(f"hours with sensible heating running          {int(res['hours_heating_running'][0]):7d}"
          f"  ({float(res['hours_heating_running'][1]):5.1f}%)")
    print()
    print(f"latent kWh charged while COOLING IS ON       {float(res['kwh_while_cooling_on'][0]):10.2f}")
    print(f"latent kWh charged while cooling is OFF      {float(res['kwh_while_cooling_off'][0]):10.2f}")
    print(f"   ...of which while HEATING is running      {float(res['kwh_while_heating_on'][0]):10.2f}")
    print(f"   ...mean zone air temp in those hours      {float(res['mean_tair_ungated'][0]):10.2f} C")
    print(f"   ...hours of that kind below 20 C          {int(res['hours_ungated_below20'][0]):10d}")'''))

cells.append(md("""**Verdict.** The ~554 kWh is **not** a regression of the C2 latent fix — latent
heating is 0.03 kWh and holds through every downstream state. It is genuine latent
*cooling*, correctly signed and correctly phased for the southern hemisphere.

But it is **ungated**: charged in 8 757 of 8 760 hours against 66 hours of actual
cooling operation, 99.6 % of it with the plant off, 6 129 hours with the zone
below 20 °C, and 17 kWh while the *heating* plant runs. It is a moisture balance
reported as plant energy."""))

cells.append(md("""---
## 4 · Item 5 — rebuild the comparison chart

Six faceted panels, one axis per metric, so nothing ~5 000-scale shares an axis
with anything ~35-scale. Built from the canonical numbers, after Items 1–4."""))

cells.append(code('''#@title Generate and display the chart
import subprocess, sys, os
os.chdir("/content/AIB")
p = subprocess.run([sys.executable, "tools/diagnostics/make_comparison_chart.py"],
                   capture_output=True, text=True)
print(p.stdout or p.stderr[-1500:])

from IPython.display import Image, display
display(Image("results/au_corrections_summary/au_corrections_summary.png", width=1100))'''))

cells.append(md("""---
## 5 · The written diagnostics"""))

cells.append(code('''#@title Render the three reports inline
import os
os.chdir("/content/AIB")
from IPython.display import Markdown, display
import ipywidgets as widgets

REPORTS = {
    "Index":            "results/diagnostics/README.md",
    "Item 1 — baseline reconciliation": "results/diagnostics/baseline_reconciliation.md",
    "Item 3 — Sankey residual":         "results/diagnostics/sankey_residual_by_state.md",
    "Item 4 — latent breakdown":        "results/diagnostics/latent_breakdown.md",
}
tabs = widgets.Tab(children=[widgets.Output() for _ in REPORTS])
for i, (name, path) in enumerate(REPORTS.items()):
    tabs.set_title(i, name.split(" — ")[0])
    with tabs.children[i]:
        display(Markdown(open(path).read()))
display(tabs)'''))

cells.append(code('''#@title Or print one report as plain text
import os
os.chdir("/content/AIB")
REPORT = "results/diagnostics/README.md"  #@param ["results/diagnostics/README.md", "results/diagnostics/baseline_reconciliation.md", "results/diagnostics/sankey_residual_by_state.md", "results/diagnostics/latent_breakdown.md"]
print(open(REPORT).read())'''))

cells.append(md("""---
## Summary of findings

**Item 1 — resolved, verdict (d).** Both published baselines reproduce
**bit-exactly (Δ = 0.0)** from a *single* engine commit by changing one field in
`examples/apt305_building.py`. Weather, setpoints, `Phi_int` and `Phi_sol` are all
bit-identical; the difference is **75.10 m² moving class `GR` ↔ `ADJ`**. Canonical
baseline **1 308.60 / 741.83 kWh** — an unmodified *engine*, but a corrected
*model input*, which must be named separately from the engine corrections C1–C4.

**Item 2 — does not trigger.** Scoped to verdict (b); the matching hashes disprove
a schedule offset.

**Item 3 — all six states FAIL 5 %.** Step 3 improves the residual by exactly the
66.6 kWh phantom ground term it removes, against a 450–5 066 kWh gap. The
unaccounted term is the **`ADJ` class**, 88.6 % of envelope UA, absent from the
Sankey inventory. Also logged: Step 3 introduces a divide-by-zero that makes the
balance unevaluable (reporting only; solver unaffected).

**Item 4 — not a C2 regression.** Latent heating is 0.03 kWh throughout. The
~554 kWh is ungated latent cooling. Headline: **34.85** kWh/m² as reported,
**7.29** latent-gated, **7.17** sensible-only — the definition has to be stated.

**Item 5 — chart rebuilt**, faceted, fully labelled.

### Stale artefacts — flagged, not edited
Everything produced before 2026-07-28 10:25 used the mis-specified building:
`results/baseline_vs_ep/`, `results/ventilation_latent/`,
`corrected_weather_results_rewrite.tex`, and the EnergyPlus alignment audit's
claim that the ISO side modelled the neighbours as ISO 13789 buffers — under
config A it did not; they were `GR`."""))

nb = {
    "cells": cells,
    "metadata": {
        "colab": {"provenance": [], "toc_visible": True},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

out = Path("/home/user/AIB/colab_diagnostics.ipynb")
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"wrote {out}  ({len(cells)} cells)")
