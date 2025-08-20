from __future__ import annotations
from typing import Dict, Any, List
import re
from google.adk.tools import FunctionTool

# Map explicit AND implicit language to Open-Meteo variables
_VAR_MAP = [
    (r"\b(temp|temperature|hot|cold|colder|warmer|cooler|heatwave)\b", "temperature_2m"),
    (r"\b(wind|breezy|gust|gusty)\b", "wind_speed_10m"),
    (r"\b(precip|precipitation|rain|showers|storm|rainfall)\b", "precipitation"),
    (r"\b(humid|humidity|muggy|dry air)\b", "relative_humidity_2m"),
    (r"\b(cloud|overcast|clear)\b", "cloud_cover")
]

_THRESH_RE = re.compile(r"(>=|<=|>|<)\s*([\d\.]+)\s*(mm|cm|m/s|ms|°c|c|%|in)?", re.I)
_STAT_RE = re.compile(r"\b(max(imum)?|min(imum)?|average|avg|mean|median|quantile\s*p?(\d{1,2}))\b", re.I)

def _infer_variables(q: str) -> List[str]:
    picks: List[str] = []
    for pat, var in _VAR_MAP:
        if re.search(pat, q):
            picks.append(var)
    return sorted(set(picks)) or ["temperature_2m"]

@FunctionTool
def pick_variables(user_query: str) -> Dict[str, Any]:
    """
    Return chosen variables and any statistical/threshold intent inferred from the query.
    Example return:
      {"variables":["temperature_2m"], "stats":{"max":True}, "threshold":{"op":">","value":30,"unit":"°C"}}
    """
    q = user_query.lower()
    variables = _infer_variables(q)

    stats: Dict[str, Any] = {}
    if m := _STAT_RE.search(q):
        token = m.group(1).lower()
        if token.startswith("max"):
            stats["max"] = True
        elif token.startswith("min"):
            stats["min"] = True
        elif token in ("average", "avg", "mean"):
            stats["mean"] = True
        elif token.startswith("median"):
            stats["median"] = True
        elif "quantile" in token:
            stats["quantile"] = m.group(4)

    threshold = None
    if m := _THRESH_RE.search(q):
        op, val, unit = m.groups()
        threshold = {"op": op, "value": float(val), "unit": (unit or "").strip()}

    return {"variables": variables, "stats": stats, "threshold": threshold}



