from __future__ import annotations
from typing import Dict, Any, List, Tuple
import re
from google.adk.tools import FunctionTool

# ---------------------------------------------------------------------------
# Config-driven mapping of canonical variables → valid Open‑Meteo parameters
# Keys are *canonical* feature names that the rest of the agent can use.
# Each entry defines which parameters exist hourly vs daily, and the
# default frequency we prefer when the user didn't state a cadence.
# This central config is consumed by tools/openmeteo.py.
# ---------------------------------------------------------------------------
VARIABLE_CONFIG: Dict[str, Dict[str, Any]] = {
    # Precipitation (NOTE: daily must use precipitation_sum, not "precipitation")
    "precipitation": {
        "hourly": ["precipitation"],
        "daily":  ["precipitation_sum"],
        "default": "daily",
        "synonyms": ["rain", "rainfall", "precip", "wet"]
    },
    "rain": {
        "hourly": ["rain"],
        "daily":  ["rain_sum"],
        "default": "daily",
        "synonyms": []
    },
    "snowfall": {
        "hourly": ["snowfall"],
        "daily":  ["snowfall_sum"],
        "default": "daily",
        "synonyms": ["snow"]
    },
    "precipitation_hours": {
        "hourly": [],
        "daily":  ["precipitation_hours"],
        "default": "daily",
        "synonyms": ["hours of rain"]
    },
    "temperature_2m": {
        "hourly": ["temperature_2m"],
        "daily":  ["temperature_2m_min", "temperature_2m_max", "temperature_2m_mean"],
        "default": "hourly",
        "synonyms": ["temperature", "temp", "cooler", "hotter", "heat", "cold", "warm"]
    },
    "apparent_temperature": {
        "hourly": ["apparent_temperature"],
        "daily":  ["apparent_temperature_min", "apparent_temperature_max", "apparent_temperature_mean"],
        "default": "hourly",
        "synonyms": ["feels like", "feels-like"]
    },
    "relative_humidity_2m": {
        "hourly": ["relative_humidity_2m"],
        "daily":  ["relative_humidity_2m_mean"],
        "default": "hourly",
        "synonyms": ["humidity", "humid"]
    },
    "dew_point_2m": {
        "hourly": ["dew_point_2m"],
        "daily":  [],
        "default": "hourly",
        "synonyms": ["dew point"]
    },
    "cloud_cover": {
        "hourly": ["cloud_cover"],
        "daily":  ["cloud_cover_mean"],
        "default": "hourly",
        "synonyms": ["cloudy", "overcast", "clear", "cloud cover"]
    },
    "uv_index": {
        "hourly": [],
        "daily":  ["uv_index_max", "uv_index_clear_sky_max"],
        "default": "daily",
        "synonyms": ["uv", "uv index", "sunburn"]
    },
    "sunrise_sunset": {
        "hourly": [],
        "daily":  ["sunrise", "sunset"],
        "default": "daily",
        "synonyms": ["sunrise", "sunset"]
    },
    "shortwave_radiation": {
        "hourly": ["shortwave_radiation"],
        "daily":  ["shortwave_radiation_sum"],
        "default": "hourly",
        "synonyms": ["solar radiation", "irradiance"]
    },
    "wind_speed_10m": {
        "hourly": ["wind_speed_10m"],
        "daily":  ["wind_speed_10m_max", "wind_gusts_10m_max"],
        "default": "hourly",
        "synonyms": ["wind", "wind speed", "breeze"]
    },
    "wind_direction_10m": {
        "hourly": ["wind_direction_10m"],
        "daily":  [],
        "default": "hourly",
        "synonyms": ["wind direction"]
    },
    "wind_gusts_10m": {
        "hourly": ["wind_gusts_10m"],
        "daily":  ["wind_gusts_10m_max"],
        "default": "hourly",
        "synonyms": ["wind gust", "gusts"]
    },
    "pressure_msl": {
        "hourly": ["pressure_msl"],
        "daily":  [],
        "default": "hourly",
        "synonyms": ["pressure", "sea level pressure"]
    },
    "surface_pressure": {
        "hourly": ["surface_pressure"],
        "daily":  [],
        "default": "hourly",
        "synonyms": []
    },
    "visibility": {
        "hourly": ["visibility"],
        "daily":  [],
        "default": "hourly",
        "synonyms": ["fog", "haze", "visibility"]
    },
    "weather_code": {
        "hourly": ["weather_code"],
        "daily":  [],
        "default": "hourly",
        "synonyms": ["weather code", "conditions"]
    },
    "et0": {
        "hourly": [],
        "daily":  ["et0_fao_evapotranspiration"],
        "default": "daily",
        "synonyms": ["evapotranspiration"]
    },
}

# Few-shot guidance we can surface to the agent/planner.
FEW_SHOT_DECISIONS: List[Tuple[str, str, str]] = [
    # (Prompt, endpoint, frequency)
    ("Will it rain in Bloomington tomorrow?",            "/v1/forecast", "daily"),
    ("Did it rain in Seattle yesterday?",                "/v1/archive",  "daily"),
    ("Is it raining in San Jose right now?",             "/v1/forecast", "hourly"),
    ("What was the humidity in Sunnyvale for the last 7 days?", "/v1/archive", "hourly"),
    ("Why is San Francisco cooler than San Jose?",       "/v1/forecast", "hourly"),
]

def _detect_granularity(q: str, picked_vars: List[str]) -> str:
    # If the query expresses a specific clock time or "now", prefer hourly.
    if re.search(r"\b(now|right now|currently)\b", q): 
        return "hourly"
    if re.search(r"\b(\d{1,2}(:\d{2})?\s*(am|pm))\b|\b(\d{1,2}:\d{2})\b|\bnoon\b|\bmidnight\b", q):
        return "hourly"

    # Comparative/explanatory with temperature → hourly detail
    if any(word in q for word in ["why", "cooler", "warmer", "hotter", "colder"]) and "temperature_2m" in picked_vars:
        return "hourly"

    # Rain tomorrow / today / next N days → daily sums
    if "precipitation" in picked_vars or "rain" in picked_vars or "snowfall" in picked_vars:
        if re.search(r"\b(today|tomorrow|this (week|weekend)|next)\b", q):
            return "daily"

    # Last/past N days →
    m = re.search(r"\b(last|past)\s+(\d{1,3})\s+day", q)
    if m:
        n = int(m.group(2))
        # Humidity over last N days → hourly
        if "relative_humidity_2m" in picked_vars:
            return "hourly"
        # Otherwise prefer daily aggregates for precipitation-related questions
        if "precipitation" in picked_vars or "rain" in picked_vars or "snowfall" in picked_vars:
            return "daily"

    # Fall back to each variable's default; if mixed, prefer hourly.
    defaults = set(VARIABLE_CONFIG[v]["default"] for v in picked_vars if v in VARIABLE_CONFIG)
    if len(defaults) == 1:
        return list(defaults)[0]
    if "hourly" in defaults:
        return "hourly"
    return "daily"

@FunctionTool
def pick_variables(user_query: str) -> Dict[str, Any]:
    q = user_query.lower()
    picked: List[str] = []

    # 1) Synonym match to pick canonical variables
    for canon, meta in VARIABLE_CONFIG.items():
        if any(syn in q for syn in meta.get("synonyms", [])) or canon in q:
            picked.append(canon)

    # Heuristic fallbacks when nothing obvious is found
    if not picked:
        if any(w in q for w in ["rain", "precip"]):
            picked = ["precipitation"]
        elif "humidity" in q:
            picked = ["relative_humidity_2m"]
        elif any(w in q for w in ["uv", "sunburn"]):
            picked = ["uv_index"]
        elif "wind" in q:
            picked = ["wind_speed_10m", "wind_gusts_10m"]
        else:
            picked = ["temperature_2m"]

    # 2) Granularity inference
    granularity = _detect_granularity(q, picked)

    # 3) Time hints for sub-hour selection
    time_hint = "none"
    if re.search(r"\b(\d{1,2}(:\d{2})?\s*(am|pm))\b|\b(\d{1,2}:\d{2})\b|\bnoon\b|\bmidnight\b", q):
        time_hint = "clock"
    if "every 15 minutes" in q or "15 min" in q or "15-minute" in q:
        time_hint = "quarter_hour"

    # 4) Stat intent (optional signal for summarizers)
    stat_intent = "auto"
    if any(w in q for w in ["sum", "total", "accumulated"]):
        stat_intent = "sum"
    elif any(w in q for w in ["max", "highest", "peak"]):
        stat_intent = "max"
    elif any(w in q for w in ["min", "lowest"]):
        stat_intent = "min"
    elif any(w in q for w in ["avg", "mean", "average"]):
        stat_intent = "mean"

    # 5) Optional endpoint hint from few‑shots (used by planners; fetch_openmeteo still auto-detects)
    endpoint_hint = ""
    for example, endpoint, freq in FEW_SHOT_DECISIONS:
        # extremely light-weight pattern match
        if all(tok in q for tok in re.findall(r"[a-z]+", example.lower())):
            endpoint_hint = endpoint
            granularity = granularity or freq  # nudge if we were "auto"
            break

    return {
        "variables": list(dict.fromkeys(picked)),
        "granularity": granularity or "auto",
        "time_hint": time_hint,
        "stat_intent": stat_intent,
        "endpoint_hint": endpoint_hint,   # advisory; can be ignored by caller
        "few_shot_examples": FEW_SHOT_DECISIONS,
    }
