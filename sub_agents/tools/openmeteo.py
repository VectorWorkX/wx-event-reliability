from __future__ import annotations
from typing import Dict, Any, List
from datetime import date
import requests
from google.adk.tools import FunctionTool

_FORECAST = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE  = "https://archive-api.open-meteo.com/v1/archive"

def _endpoint_for(start_iso: str, end_iso: str) -> str:
    today = date.today().isoformat()
    # If the entire window is in the past: archive; else forecast
    return _ARCHIVE if end_iso < today else _FORECAST

@FunctionTool
def fetch_openmeteo(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    variables: List[str],
    granularity: str = "daily"
) -> Dict[str, Any]:
    """
    Fetch Open-Meteo time series for the given window/variables.
    Returns:
      {"source": "...", "params": {...}, "data": <json>}
    """
    if not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
        return {"error": "Invalid coordinates"}

    endpoint = _endpoint_for(start_date, end_date)
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "UTC",
        "start_date": start_date,
        "end_date": end_date,
    }
    key = "hourly" if granularity == "hourly" else "daily"
    params[key] = ",".join(variables)

    r = requests.get(endpoint, params=params, timeout=40)
    r.raise_for_status()
    data = r.json()

    # Extract available units (hourly_units/daily_units)
    units = data.get(f"{key}_units", {})
    return {"source": endpoint, "params": params, "units": units, "data": data}




