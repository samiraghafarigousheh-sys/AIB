"""
Melbourne weather resolution for the Apt 305 reference case.

WHY THIS MODULE EXISTS
----------------------
The engine takes its solar geometry from two *different* places depending on the
weather source, and getting this wrong is silent:

* ``weather_source="epw"``  -> latitude/longitude come from the **EPW header**.
  The ``latitude`` in the building dictionary is ignored. Hand it a Milan file
  and you have simulated the apartment in Milan, with no warning.
* ``weather_source="pvgis"`` -> latitude/longitude come from the **building
  dictionary**, so the TMY is fetched for the building's own coordinates.

So for a Melbourne building, PVGIS is site-correct by construction, while an EPW
is site-correct only if the file really is Melbourne. This module enforces that:
it will not let a wrong-city EPW through silently.

Resolution order
----------------
1. An explicit ``--weather`` EPW, **validated** against the building coordinates.
2. The canonical cached EPW (``CANONICAL_EPW``) under ``weather_cache/``.
3. Any other cached Melbourne EPW under ``weather_cache/``.
4. Download a Melbourne EPW from a list of mirrors.
5. PVGIS TMY at the building's own lat/lon (needs network; site-correct).

If none is available the caller is told plainly, rather than being handed some
other city's climate.

THE WIND COLUMN IS SCREENED, NOT ASSUMED
----------------------------------------
Site-correctness is necessary and was never sufficient. The Melbourne Regional
Office file this case study previously used sits 0.008 deg from the building --
it passed every check here -- and four whole months of its wind column were
identically 0.0 m/s, because the station's record ends in 2014. Correction C2
(``h_ce = 4v + 4``) collapses to 4 W/(m2 K) at v = 0, so those fabricated calms
tripled sensible cooling.

So resolution now also runs the wind-column preflight in
``tools/diagnostics/weather_integrity.py``, and a file with a dead-calm month is
refused outright rather than silently producing an indefensible cooling figure.
The canonical station is Essendon Fields (WMO 958660, ~8 km NW of the building,
complete continuous record); the RO file is deliberately kept in
``weather_cache/`` so the before/after contrast can still be drawn, and the
preflight is what stops it being picked up by accident.
"""

from __future__ import annotations

import io
import math
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "weather_cache"

# The case-study weather file. Named rather than discovered, because
# ``weather_cache/`` also holds the superseded Melbourne Regional Office file and
# "whichever EPW sorts first" is not a provenance anyone can defend in a paper.
CANONICAL_EPW = "AUS_VIC_Melbourne-Essendon.Fields.958660_TMYx.2011-2025.epw"

# The file CANONICAL_EPW replaces, kept for the wind before/after contrast.
SUPERSEDED_EPW = "AUS_VIC_Melbourne.RO.948680_TMYx.2011-2025.epw"

# Apt 305, 50 Barry St, Carlton
MELBOURNE_LAT = -37.800
MELBOURNE_LON = 144.968

# How far an EPW may sit from the building before it is the wrong climate.
#
# Two bands, because "wrong city" and "wrong continent" deserve different
# answers. Inside WARN it is greater-Melbourne and silent. Between WARN and MAX
# it is a regional Victorian station — a different climate (inland stations run
# hotter in summer and colder in winter than the coast), so it is accepted but
# announced, and the station name is carried into every chart label. Beyond MAX
# it is another region entirely and is refused.
WARN_SITE_OFFSET_DEG = 1.5
MAX_SITE_OFFSET_DEG = 2.5

# climate.onebuilding.org directory holding every Victorian TMY. Scraping the
# index is deliberate: TMYx filenames carry a year range that changes with each
# release (…_TMYx.2009-2023.zip today), so a hardcoded URL rots. Listing the
# directory and matching AUS_VIC_Melbourne*.zip survives that.
ONEBUILDING_VIC_INDEX = (
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/"
    "AUS_Australia/VIC_Victoria/"
)

# Tried before scraping, in order. Both .zip and bare .epw are handled.
MELBOURNE_EPW_MIRRORS = [
    ONEBUILDING_VIC_INDEX + "AUS_VIC_Melbourne.Regional.Office.948680_TMYx.2009-2023.zip",
    ONEBUILDING_VIC_INDEX + "AUS_VIC_Melbourne.Olympic.Park.948656_TMYx.2009-2023.zip",
    ONEBUILDING_VIC_INDEX + "AUS_VIC_Melbourne.Airport.948660_TMYx.2009-2023.zip",
    ONEBUILDING_VIC_INDEX + "AUS_VIC_Melbourne.Regional.Office.948680_TMYx.2007-2021.zip",
    ONEBUILDING_VIC_INDEX + "AUS_VIC_Melbourne.Regional.Office.948680_TMYx.zip",
    "https://energyplus-weather.s3.amazonaws.com/southwest_pacific_wmo_region_5/AUS/"
    "AUS_Melbourne.948660_IWEC/AUS_Melbourne.948660_IWEC.epw",
]


def discover_melbourne_urls(timeout: int = 60) -> list[str]:
    """
    Scrape the Victoria directory index for Melbourne TMY archives.

    Returns candidate URLs newest-looking first. Any failure returns [] so the
    caller just falls through to the hardcoded list.
    """
    import re
    import requests

    try:
        resp = requests.get(ONEBUILDING_VIC_INDEX, timeout=timeout)
        if resp.status_code != 200:
            return []
        hrefs = re.findall(r'href=["\']([^"\']+\.zip)["\']', resp.text, flags=re.I)
    except Exception:
        return []

    names = []
    for h in hrefs:
        base = h.split("/")[-1]
        if re.match(r"AUS_VIC_Melbourne", base, flags=re.I):
            names.append(base)
    # Prefer TMYx over older TMY/IWEC, and later year ranges first.
    names.sort(key=lambda n: ("TMYx" not in n, n), reverse=False)
    names.sort(key=lambda n: re.findall(r"(\d{4})-(\d{4})", n) or [("0", "0")], reverse=True)
    return [ONEBUILDING_VIC_INDEX + n for n in dict.fromkeys(names)]


class WeatherUnavailable(RuntimeError):
    """Raised when no Melbourne-correct weather source can be reached."""


def read_epw_site(epw_path: Path) -> tuple[float, float, str]:
    """
    Return (latitude, longitude, city) from an EPW LOCATION header.

    LOCATION,City,State,Country,Source,WMO,Lat,Lon,TZ,Elevation
    """
    with open(epw_path, "r", encoding="utf-8", errors="replace") as fh:
        first = fh.readline()
    parts = [p.strip() for p in first.split(",")]
    if len(parts) < 8 or parts[0].upper() != "LOCATION":
        raise ValueError(f"{epw_path} does not start with an EPW LOCATION header")
    return float(parts[6]), float(parts[7]), parts[1]


def site_offset_deg(lat: float, lon: float,
                    ref_lat: float = MELBOURNE_LAT, ref_lon: float = MELBOURNE_LON) -> float:
    """Great-circle-ish offset in degrees, good enough for a sanity gate."""
    dlat = lat - ref_lat
    dlon = (lon - ref_lon) * math.cos(math.radians((lat + ref_lat) / 2.0))
    return math.hypot(dlat, dlon)


def validate_epw_site(epw_path: Path, strict: bool = True) -> tuple[float, float, str]:
    """
    Check an EPW really is the building's site.

    This is the guard that the previous version of this example lacked: an EPW
    from another city overrides the building's own latitude without complaint,
    so the run silently stops being about Melbourne.
    """
    lat, lon, city = read_epw_site(epw_path)
    offset = site_offset_deg(lat, lon)
    if offset > MAX_SITE_OFFSET_DEG:
        msg = (
            f"\nEPW site mismatch:\n"
            f"  file    : {epw_path.name}\n"
            f"  station : {city} at lat {lat:.3f}, lon {lon:.3f}\n"
            f"  building: Melbourne at lat {MELBOURNE_LAT:.3f}, lon {MELBOURNE_LON:.3f}\n"
            f"  offset  : {offset:.1f} deg (limit {MAX_SITE_OFFSET_DEG})\n\n"
            f"With weather_source='epw' the engine takes latitude from the EPW header,\n"
            f"NOT from the building dictionary, so this run would not be Melbourne.\n"
            f"Pass --allow-site-mismatch to accept it anyway (results are then for the\n"
            f"EPW's own location, and must be labelled as such)."
        )
        if strict:
            raise WeatherUnavailable(msg)
        print(f"  WARNING {msg}")
    elif offset > WARN_SITE_OFFSET_DEG:
        print(f"  NOTE  {city} is {offset:.1f} deg from central Melbourne — a regional "
              f"Victorian station,\n        not a coastal Melbourne one. Accepted, and "
              f"labelled '{city}' on every output.")
    return lat, lon, city


def _extract_epw_from_zip(blob: bytes, dest_dir: Path) -> Path | None:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".epw")]
        if not names:
            return None
        name = names[0]
        dest = dest_dir / Path(name).name
        dest.write_bytes(zf.read(name))
        return dest


def download_melbourne_epw(dest_dir: Path = CACHE_DIR, timeout: int = 90) -> Path:
    """
    Fetch a Melbourne TMY EPW from the first reachable mirror.

    Raises WeatherUnavailable listing what was tried, so a blocked network gives
    a diagnosable message instead of a silent fallback to the wrong city.
    """
    import requests

    dest_dir.mkdir(parents=True, exist_ok=True)
    failures = []

    # Known URLs first (cheap), then whatever the directory index actually holds.
    candidates = list(MELBOURNE_EPW_MIRRORS)
    discovered = discover_melbourne_urls()
    if discovered:
        print(f"  found {len(discovered)} Melbourne archive(s) in the onebuilding index")
        candidates = discovered + [u for u in candidates if u not in discovered]

    for url in candidates:
        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code != 200 or not resp.content:
                failures.append(f"  {resp.status_code}  {url}")
                continue
            if url.lower().endswith(".zip"):
                path = _extract_epw_from_zip(resp.content, dest_dir)
                if path is None:
                    failures.append(f"  no .epw inside zip  {url}")
                    continue
            else:
                path = dest_dir / Path(url).name
                path.write_bytes(resp.content)
            validate_epw_site(path, strict=True)
            print(f"  downloaded {path.name}")
            return path
        except Exception as exc:  # network error, bad zip, wrong site
            failures.append(f"  {type(exc).__name__}: {str(exc)[:120]}  {url}")

    raise WeatherUnavailable(
        "Could not download a Melbourne EPW. Tried:\n" + "\n".join(failures)
        + "\n\nOptions:\n"
          "  * run with --weather-source pvgis (fetches a TMY for the building's own\n"
          "    coordinates; needs access to re.jrc.ec.europa.eu)\n"
          "  * download a Melbourne EPW manually and pass it with --weather"
    )


def wind_screen(path: Path, quiet: bool = False):
    """Run the EPW wind-column preflight. Raises on a degenerate column.

    Imported lazily and by path: ``tools/`` is not a package and this module is
    imported by scripts run from several working directories.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "aib_weather_integrity",
        REPO_ROOT / "tools" / "diagnostics" / "weather_integrity.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.assert_usable(path, quiet=quiet)


def find_cached_epw(dest_dir: Path = CACHE_DIR) -> Path | None:
    """Return a cached EPW that passes the site *and* wind-column checks.

    ``CANONICAL_EPW`` is tried first by name. Falling back to "whichever file
    sorts first" is kept only so a fresh clone with a downloaded file still
    works -- but a file whose wind column is degenerate is skipped rather than
    returned, which is what keeps the superseded RO file (still present, for the
    before/after contrast) from being picked up silently.
    """
    if not dest_dir.is_dir():
        return None
    candidates = sorted(dest_dir.glob("*.epw"),
                        key=lambda p: (p.name != CANONICAL_EPW, p.name))
    for path in candidates:
        try:
            validate_epw_site(path, strict=True)
            wind_screen(path, quiet=True)
            return path
        except Exception as exc:
            print(f"  skipping cached {path.name}: {str(exc).strip().splitlines()[0]}")
            continue
    return None


PVGIS_TMY_URL = "https://re.jrc.ec.europa.eu/api/tmy"


def pvgis_reachable(timeout: int = 25) -> tuple[bool, str]:
    """
    Probe PVGIS before committing to it.

    Without this the run would fail deep inside the first engine invocation,
    after minutes of setup, with a bare proxy error.
    """
    import requests
    try:
        resp = requests.get(
            PVGIS_TMY_URL,
            params={"lat": MELBOURNE_LAT, "lon": MELBOURNE_LON,
                    "outputformat": "json", "browser": 1},
            timeout=timeout,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:160]}"
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}"
    return True, "ok"


def _pvgis_or_raise(context: str) -> tuple[str, None, str]:
    ok, why = pvgis_reachable()
    if not ok:
        raise WeatherUnavailable(
            f"{context}\nPVGIS is also unreachable ({why}).\n\n"
            f"No Melbourne weather source is available from this machine.\n"
            f"Options:\n"
            f"  * run somewhere with open network (e.g. Google Colab) — see the\n"
            f"    Colab notebook in notebooks/\n"
            f"  * download a Melbourne TMY EPW manually from\n"
            f"    https://climate.onebuilding.org (WMO Region 5 > AUS > VIC)\n"
            f"    and pass it with --weather path/to/file.epw\n"
            f"  * place it in {CACHE_DIR}/ and it will be picked up automatically\n\n"
            f"This example deliberately refuses to substitute another city's weather:\n"
            f"with weather_source='epw' the engine reads latitude from the EPW header,\n"
            f"so a stand-in file silently relocates the building."
        )
    return ("pvgis", None,
            f"PVGIS TMY at lat {MELBOURNE_LAT}, lon {MELBOURNE_LON} (Melbourne)")


def resolve(weather: str | None, weather_source: str,
            allow_site_mismatch: bool = False,
            screen_wind: bool = True) -> tuple[str, str | None, str]:
    """
    Decide how this run gets its weather.

    Returns (weather_source, path_or_None, human_readable_label).

    ``screen_wind`` runs the wind-column preflight on an explicitly-passed EPW
    and refuses a degenerate one. Set it False only to *study* a bad file (the
    wind diagnostic's before/after contrast), never to produce a result.
    """
    if weather_source == "pvgis":
        return _pvgis_or_raise("PVGIS was requested explicitly.")

    if weather:
        path = Path(weather).resolve()
        if not path.is_file():
            raise WeatherUnavailable(f"weather file not found: {path}")
        lat, lon, city = validate_epw_site(path, strict=not allow_site_mismatch)
        if screen_wind:
            wind_screen(path)
        return ("epw", str(path), f"{path.name} — {city} (lat {lat:.2f}, lon {lon:.2f})")

    cached = find_cached_epw()
    if cached is not None:
        lat, lon, city = read_epw_site(cached)
        print(f"  using cached {cached.name}")
        return ("epw", str(cached), f"{cached.name} — {city} (lat {lat:.2f}, lon {lon:.2f})")

    print("  no Melbourne EPW cached; attempting download…")
    try:
        path = download_melbourne_epw()
        lat, lon, city = read_epw_site(path)
        return ("epw", str(path), f"{path.name} — {city} (lat {lat:.2f}, lon {lon:.2f})")
    except WeatherUnavailable as exc:
        print("  EPW mirrors unreachable; trying PVGIS…")
        return _pvgis_or_raise(f"EPW download failed:\n{exc}")


def resolve_and_record(weather: str | None, weather_source: str,
                       allow_site_mismatch: bool, outdir: Path,
                       require_epw: bool = False,
                       screen_wind: bool = True) -> tuple[str, str | None, str]:
    """
    Resolve the weather AND record what was chosen next to the results.

    THIS IS THE FIX FOR THE HARNESS-DISAGREEMENT BUG. ``resolve()`` falls back
    (cached EPW -> download -> PVGIS), so two scripts run minutes apart could
    legitimately return different sources — one on a Melbourne EPW, one on a
    PVGIS TMY — and nothing downstream said so. The two baselines then differed
    by a factor of three on heating while both charts claimed to be "the
    baseline engine on the same building", which they were: same engine, same
    building, *different weather*.

    Every run now drops ``run_meta.json`` beside its outputs, so two result
    directories can be compared and any weather mismatch is immediately visible
    instead of being argued about from the charts.

    ``require_epw`` refuses a PVGIS fallback outright, for callers (EnergyPlus,
    or any run that must be comparable with an EnergyPlus run) that cannot use
    it or must not silently diverge from one.
    """
    import json

    source, path, label = resolve(weather, weather_source, allow_site_mismatch,
                                  screen_wind=screen_wind)
    if require_epw and source != "epw":
        raise WeatherUnavailable(
            "This run requires an EPW file and PVGIS was selected instead.\n"
            "EnergyPlus cannot read PVGIS, and an ISO run on PVGIS is not\n"
            "comparable with an EnergyPlus run on an EPW — that mismatch is\n"
            "exactly what made the two baseline charts disagree.\n\n"
            "Pass --weather path/to/Melbourne.epw, or place one in "
            f"{CACHE_DIR}/."
        )

    outdir.mkdir(parents=True, exist_ok=True)
    meta = {"weather_source": source, "weather_path": path, "weather_label": label}
    if path:
        lat, lon, city = read_epw_site(Path(path))
        meta.update(station=city, latitude=lat, longitude=lon,
                    site_offset_deg=round(site_offset_deg(lat, lon), 3))
        # The wind column is part of the provenance, not a detail: the previous
        # canonical run was site-correct and still unusable.
        try:
            w = wind_screen(Path(path), quiet=True)
            meta["wind"] = {
                "mean_ms": round(w["mean_wind_ms"], 3),
                "pct_hours_exactly_zero": round(w["pct_hours_exactly_zero"], 3),
                "pct_hours_above_4ms": round(w["pct_hours_above_pivot"], 3),
                "dead_calm_months": w["degenerate_months"],
                "screened": True,
            }
        except Exception as exc:
            meta["wind"] = {"screened": False, "error": str(exc).strip().splitlines()[0]}
    (outdir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return source, path, label


if __name__ == "__main__":
    import sys
    try:
        src, path, label = resolve(None, "auto")
    except WeatherUnavailable as exc:
        print(f"\nNo Melbourne weather available here.\n\n{exc}")
        sys.exit(1)
    print(f"source={src}  path={path}\nlabel ={label}")
