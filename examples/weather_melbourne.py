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
2. A cached Melbourne EPW under ``weather_cache/``.
3. Download a Melbourne EPW from a list of mirrors.
4. PVGIS TMY at the building's own lat/lon (needs network; site-correct).

If none is available the caller is told plainly, rather than being handed some
other city's climate.
"""

from __future__ import annotations

import io
import math
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "weather_cache"

# Apt 305, 50 Barry St, Carlton
MELBOURNE_LAT = -37.800
MELBOURNE_LON = 144.968

# How far an EPW may sit from the building before it is the wrong climate.
# ~1.5 deg is roughly greater-Melbourne; beyond that the site is different.
MAX_SITE_OFFSET_DEG = 1.5

# Public Melbourne TMY mirrors, tried in order. Both zip and bare .epw are
# handled. These hosts are reachable from Colab; some sandboxes block them.
MELBOURNE_EPW_MIRRORS = [
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/AUS_Australia/VIC_Victoria/"
    "AUS_VIC_Melbourne.Regional.Office.948680_TMYx.2009-2023.zip",
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/AUS_Australia/VIC_Victoria/"
    "AUS_VIC_Melbourne.Regional.Office.948680_TMYx.zip",
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/AUS_Australia/VIC_Victoria/"
    "AUS_VIC_Melbourne.Airport.948660_TMYx.2009-2023.zip",
    "https://energyplus-weather.s3.amazonaws.com/southwest_pacific_wmo_region_5/AUS/"
    "AUS_Melbourne.948660_IWEC/AUS_Melbourne.948660_IWEC.epw",
]


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
    for url in MELBOURNE_EPW_MIRRORS:
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


def find_cached_epw(dest_dir: Path = CACHE_DIR) -> Path | None:
    """Return a cached EPW that passes the site check, if one exists."""
    if not dest_dir.is_dir():
        return None
    for path in sorted(dest_dir.glob("*.epw")):
        try:
            validate_epw_site(path, strict=True)
            return path
        except Exception:
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
            allow_site_mismatch: bool = False) -> tuple[str, str | None, str]:
    """
    Decide how this run gets its weather.

    Returns (weather_source, path_or_None, human_readable_label).
    """
    if weather_source == "pvgis":
        return _pvgis_or_raise("PVGIS was requested explicitly.")

    if weather:
        path = Path(weather)
        if not path.is_file():
            raise WeatherUnavailable(f"weather file not found: {path}")
        lat, lon, city = validate_epw_site(path, strict=not allow_site_mismatch)
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


if __name__ == "__main__":
    import sys
    try:
        src, path, label = resolve(None, "auto")
    except WeatherUnavailable as exc:
        print(f"\nNo Melbourne weather available here.\n\n{exc}")
        sys.exit(1)
    print(f"source={src}  path={path}\nlabel ={label}")
