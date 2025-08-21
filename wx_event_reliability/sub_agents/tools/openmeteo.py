from __future__ import annotations
from typing import Dict, Any, List, Tuple
from datetime import datetime, date, timedelta
import requests
from google.adk.tools import FunctionTool

# Import the central mapping from variables.py
try:
    from .variables import VARIABLE_CONFIG  # same package
except Exception:
    # Fallback if relative import fails in some runner
    from variables import VARIABLE_CONFIG

_FORECAST = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE  = "https://archive-api.open-meteo.com/v1/archive"

# Max forward horizon the forecast API will honor (var-dependent, 7–16).
# We clamp to 16 days unless caller provides a shorter range.
_FORECAST_MAX_DAYS = 16

def _safe_float(x: Any, lo: float, hi: float) -> bool:
    try:
        fx = float(x)
    except Exception:
        return False
    return lo <= fx <= hi

def _pick_granularity(requested: str, time_hint: str) -> str:
    if requested in {"daily","hourly","minutely_15","current"}:
        return requested
    if time_hint == "quarter_hour":
        return "minutely_15"
    if time_hint == "clock":
        return "hourly"
    # Default to daily to reduce payloads unless the question suggests otherwise
    return "daily"

def _clamp_forecast_range(s: date, e: date, today: date) -> Tuple[date, date]:
    if e > today + timedelta(days=_FORECAST_MAX_DAYS):
        e = today + timedelta(days=_FORECAST_MAX_DAYS)
    return s, e

def _map_vars(canonical: List[str], granularity: str) -> Tuple[str, List[str], List[str]]:
    warnings: List[str] = []
    api_key = granularity if granularity in {"hourly","daily","minutely_15","current"} else "daily"
    out: List[str] = []

    # Use VARIABLE_CONFIG to produce correct parameter names
    for v in (canonical or []):
        cfg = VARIABLE_CONFIG.get(v, {})
        if api_key == "daily":
            params = cfg.get("daily", [])
            if not params:
                # Fall back to hourly if no daily aggregate exists
                api_key = "hourly"
                params = cfg.get("hourly", [])
                if params:
                    warnings.append(f"No daily aggregate for '{v}'. Falling back to hourly.")
            out += params or [v]
        elif api_key == "hourly":
            params = cfg.get("hourly", [])
            if not params and cfg.get("daily"):
                # Rare: only daily exists, fall back with warning
                api_key = "daily"
                params = cfg.get("daily", [])
                warnings.append(f"No hourly variable for '{v}'. Using daily aggregate.")
            out += params or [v]
        else:
            # For 15-min or current, reuse hourly lists when available
            params = cfg.get("hourly", []) or cfg.get("daily", [])
            out += params or [v]

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for p in out:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    # If nothing resolved, keep a safe hourly default
    if not deduped:
        api_key = "hourly"
        deduped = ["temperature_2m"]
        warnings.append("No variables recognized; defaulting to hourly temperature_2m.")

    return api_key, deduped, warnings

def _auto_time_params(start_date: str, end_date: str, api_key: str, now_local: datetime) -> Dict[str, Any]:
    # explicit dates are predictable for both endpoints
    return {"start_date": start_date, "end_date": end_date}

def _merge_series(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    if not a: return b or {}
    if not b: return a or {}
    time_key = "time"
    out: Dict[str, Any] = {}
    out[time_key] = (a.get(time_key) or []) + (b.get(time_key) or [])
    keys = set(a.keys()).union(b.keys())
    keys.discard(time_key)
    for k in keys:
        out[k] = (a.get(k) or []) + (b.get(k) or [])
    return out

@FunctionTool
def fetch_openmeteo(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    variables: List[str],
    granularity: str = "auto",    # 'auto' | 'daily' | 'hourly' | 'minutely_15' | 'current'
    time_mode: str = "",          # 'hindcast' | 'forecast' | 'mixed' | ''
    time_hint: str = "none",      # 'none' | 'clock' | 'quarter_hour'
    tz_mode: str = "auto",        # 'auto' or TZ like 'America/Los_Angeles'
    models: List[str] | None = None,
) -> Dict[str, Any]:
    # Guard coords
    if not (_safe_float(lat, -90, 90) and _safe_float(lon, -180, 180)):
        return {"error": "Invalid coordinates"}

    picked_gran = _pick_granularity(granularity, time_hint)
    api_key, var_list, var_warnings = _map_vars(variables, picked_gran)

    today = date.today()
    s = date.fromisoformat(start_date)
    e = date.fromisoformat(end_date)

    # Decide endpoint(s). If caller didn’t force time_mode, infer:
    if not time_mode:
        if e < today:
            time_mode = "hindcast"     # strictly past → archive
        elif s > today:
            time_mode = "forecast"     # strictly future → forecast
        else:
            time_mode = "mixed"        # spans past↔future → split calls

    tz_value = "auto" if tz_mode == "auto" else tz_mode

    def _call(endpoint: str, s_date: date, e_date: date) -> Dict[str, Any]:
        # Clamp forecast horizon to avoid silent truncation errors
        _s, _e = s_date, e_date
        if endpoint == _FORECAST:
            _s, _e = _clamp_forecast_range(_s, _e, today)

        params = {
            "latitude": float(lat),
            "longitude": float(lon),
            "timezone": tz_value,
        }
        params.update(_auto_time_params(_s.isoformat(), _e.isoformat(), api_key, datetime.utcnow()))
        params[api_key] = ",".join(var_list)
        if models:
            params["models"] = ",".join(models)

        r = requests.get(endpoint, params=params, timeout=30)
        r.raise_for_status()
        js = r.json() if hasattr(r, "json") else {}
        # Pick the block that matches our cadence
        block = js.get(api_key) or {}
        units = js.get(f"{api_key}_units") or {}

        return {"block": block, "units": units, "raw": js, "endpoint": endpoint, "params": params}

    # Perform calls based on time_mode
    units: Dict[str, Any] = {}
    block: Dict[str, Any] = {}
    data: Dict[str, Any] = {}
    sources: List[str] = []

    if time_mode == "hindcast":
        sources = ["archive"]
        a = _call(_ARCHIVE, s, e)
        units.update(a["units"])
        block = a["block"]
        data["archive_raw"] = a["raw"]
    elif time_mode == "forecast":
        sources = ["forecast"]
        b = _call(_FORECAST, s, e)
        units.update(b["units"])
        block = b["block"]
        data["forecast_raw"] = b["raw"]
    else:  # mixed
        sources = ["archive", "forecast"]
        if s < today:
            past_end = min(e, today - timedelta(days=1))
            a = _call(_ARCHIVE, s, past_end)
            units.update(a["units"])
            block = _merge_series(block, a["block"])
            data["archive_raw"] = a["raw"]
        if e >= today:
            fut_start = max(today, s)
            b = _call(_FORECAST, fut_start, e)
            units.update(b["units"])
            block = _merge_series(block, b["block"])
            data["forecast_raw"] = b["raw"]

    # Success payload
    resp: Dict[str, Any] = {
        "source": "+".join(sources),
        "endpoint_mode": time_mode,
        "granularity": api_key,
        "endpoint_urls": {
            "forecast": _FORECAST if "forecast" in sources else "",
            "archive": _ARCHIVE if "archive" in sources else "",
        },
        "request": {
            "latitude": float(lat),
            "longitude": float(lon),
            "start_date": s.isoformat(),
            "end_date": e.isoformat(),
            api_key: ",".join(var_list),
            "timezone": tz_value,
            **({"models": ",".join(models)} if models else {}),
        },
        "units": units,
        "data": {api_key: block, f"{api_key}_units": units},
    }
    if var_warnings:
        resp["warnings"] = var_warnings
    return resp
