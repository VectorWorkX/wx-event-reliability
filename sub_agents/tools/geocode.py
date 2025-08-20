from __future__ import annotations
from typing import Dict, Any
import re
import requests
from timezonefinder import TimezoneFinder
from google.adk.tools import FunctionTool

_IATA_RE = re.compile(r"^[A-Z]{3}$")
_LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")

def _tz_from_latlon(lat: float, lon: float) -> str | None:
    try:
        tf = TimezoneFinder()
        return tf.timezone_at(lat=lat, lng=lon)
    except Exception:
        return None

@FunctionTool
def geocode_place(query: str) -> Dict[str, Any]:
    """
    Resolve a place description into coordinates + country + local tz.
    Accepts: "San Francisco", "Denver, CO", "37.77,-122.42", or IATA like "SFO".
    Returns:
      {"name": str, "lat": float, "lon": float, "country": str, "tz": str}
    """
    q = query.strip()

    # lat,lon direct
    m = _LATLON_RE.match(q)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        tz = _tz_from_latlon(lat, lon) or "UTC"
        return {"name": f"{lat:.4f},{lon:.4f}", "lat": lat, "lon": lon, "country": "", "tz": tz}

    # naive IATA detection (optional convenience)
    if _IATA_RE.match(q):
        # Use Open-Meteo geocoding like any other string; many IATAs resolve as city names
        name = q

    # Open-Meteo Geocoding (no key)
    url = "https://geocoding-api.open-meteo.com/v1/search"
    r = requests.get(url, params={"name": q, "count": 1, "language": "en"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("results"):
        return {"error": f"Could not geocode '{query}'. Please specify 'City, Country' or lat,lon."}

    top = data["results"][0]
    lat, lon = float(top["latitude"]), float(top["longitude"])
    country = top.get("country", "") or ""
    name = f"{top.get('name')}" + (f", {country}" if country else "")
    tz = _tz_from_latlon(lat, lon) or "UTC"
    return {"name": name, "lat": lat, "lon": lon, "country": country, "tz": tz}

