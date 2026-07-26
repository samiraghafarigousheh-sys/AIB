"""
Run one ISO 52016-1 reference case and dump the annual results as JSON.

The point of this harness is branch-to-branch comparison: it takes the engine
source directory as an argument, so the *same* case can be run against the
baseline engine and against a modified engine, and the difference attributed to
the change rather than to a difference in inputs.

The building is the ``BUI`` dictionary from ``examples/new_building.py``
(Archetype_ITA_SFH_2010, 8 surfaces of which 2 are transparent). It is read out
of the example file rather than duplicated here, so it stays in sync.

Weather comes from a bundled EPW so runs are offline and deterministic; the
default PVGIS path in the example needs network access.

Usage
-----
    python tools/run_case.py --src pybuildingenergy/src --out result.json
    python tools/run_case.py --src pybuildingenergy/src --out off.json \
        --option dynamic_window_properties=false
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = REPO_ROOT / "pybuildingenergy" / "src"
DEFAULT_EXAMPLE = REPO_ROOT / "pybuildingenergy" / "examples" / "new_building.py"
DEFAULT_WEATHER = REPO_ROOT / "pybuildingenergy" / "examples" / "2020_Milan.epw"


def load_building(example_path: Path) -> dict:
    """
    Pull the BUI literal out of the example module without importing it.

    Importing new_building.py is not an option: at the pinned upstream commit it
    imports pybuildingenergy.source.example_inputs, which does not exist in the
    repository. Parsing the assignment keeps this harness independent of that.
    """
    tree = ast.parse(example_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "BUI":
                    return ast.literal_eval(node.value)
    raise RuntimeError(f"No BUI assignment found in {example_path}")


def parse_option(text: str):
    """Parse a --option KEY=VALUE pair into a typed (key, value)."""
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"--option must be KEY=VALUE, got {text!r}")
    key, _, raw = text.partition("=")
    key, raw = key.strip(), raw.strip()
    low = raw.lower()
    if low in {"true", "false"}:
        return key, low == "true"
    # NB: "none" is deliberately NOT mapped to Python None. Several engine
    # options take the literal string "none" as a model name, and the resolvers
    # read None as "not overridden" — mapping it would silently select the
    # default instead of disabling the model.
    if low == "null":
        return key, None
    try:
        return key, int(raw)
    except ValueError:
        pass
    try:
        return key, float(raw)
    except ValueError:
        pass
    return key, raw


def summarize(hourly, annual, building) -> dict:
    """Reduce engine output to a small, stable, comparable set of numbers."""
    import numpy as np
    import pandas as pd

    out: dict = {}

    area = None
    try:
        area = float(building["building"]["treated_floor_area"])
    except Exception:
        pass
    out["treated_floor_area_m2"] = area

    if isinstance(annual, pd.DataFrame):
        # Flatten whatever the annual frame carries, so column renames upstream
        # do not silently drop a metric from the comparison.
        for col in annual.columns:
            try:
                vals = pd.to_numeric(annual[col], errors="coerce").dropna()
                if len(vals):
                    out[f"annual::{col}"] = float(vals.iloc[0]) if len(vals) == 1 else float(vals.sum())
            except Exception:
                continue

    if isinstance(hourly, pd.DataFrame):
        out["n_timesteps"] = int(len(hourly))
        for col in hourly.columns:
            low = str(col).lower()
            if not any(k in low for k in ("q_h", "q_c", "need", "phi", "theta", "solar", "t_op", "t_air")):
                continue
            try:
                vals = pd.to_numeric(hourly[col], errors="coerce")
            except Exception:
                continue
            arr = vals.to_numpy(dtype=float)
            arr = arr[np.isfinite(arr)]
            if arr.size == 0:
                continue
            out[f"hourly::{col}::sum"] = float(arr.sum())
            out[f"hourly::{col}::mean"] = float(arr.mean())
            out[f"hourly::{col}::max"] = float(arr.max())
            out[f"hourly::{col}::min"] = float(arr.min())

    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="engine source dir to put on sys.path")
    ap.add_argument("--example", type=Path, default=DEFAULT_EXAMPLE, help="file holding the BUI dict")
    ap.add_argument("--weather", type=Path, default=DEFAULT_WEATHER, help="EPW weather file")
    ap.add_argument("--out", type=Path, required=True, help="where to write the JSON summary")
    ap.add_argument("--label", default=None, help="label recorded in the JSON")
    ap.add_argument(
        "--option",
        action="append",
        default=[],
        type=parse_option,
        metavar="KEY=VALUE",
        help="extra kwarg passed to the engine; repeatable",
    )
    ap.add_argument(
        "--force-wind",
        type=float,
        default=None,
        metavar="MS",
        help=(
            "overwrite the WS10m column with a constant wind speed. Forcing 4.0 "
            "reproduces the wind speed EN ISO 13789 assumes, so a wind-dependent "
            "h_ce must collapse back onto the ISO constant and reproduce baseline "
            "results exactly."
        ),
    )
    args = ap.parse_args()

    sys.path.insert(0, str(args.src.resolve()))

    from pybuildingenergy.source import utils as _utils
    from pybuildingenergy.source.utils import ISO52016
    from pybuildingenergy.source.check_input import sanitize_and_validate_BUI

    if args.force_wind is not None:
        # Patch the weather pipeline rather than the engine, so this validation
        # hook cannot itself perturb the physics under test.
        _orig = _utils.Calculation_ISO_52010

        def _patched(building_object, path_weather_file, weather_source="pvgis"):
            res = _orig(building_object, path_weather_file, weather_source=weather_source)
            res.sim_df["WS10m"] = float(args.force_wind)
            return res

        _utils.Calculation_ISO_52010 = _patched

    building = load_building(args.example)
    building, _report = sanitize_and_validate_BUI(building, fix=True)

    kwargs = {"weather_source": "epw", "path_weather_file": str(args.weather)}
    kwargs.update(dict(args.option))

    result = ISO52016.Temperature_and_Energy_needs_calculation(building, **kwargs)
    if isinstance(result, tuple):
        hourly, annual = result[0], result[1]
    else:
        hourly, annual = result, None

    summary = summarize(hourly, annual, building)
    summary["_label"] = args.label or str(args.src)
    summary["_options"] = {k: v for k, v in dict(args.option).items()}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {args.out}  ({len(summary)} metrics)")


if __name__ == "__main__":
    main()
