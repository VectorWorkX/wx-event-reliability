from __future__ import annotations
from typing import Dict, Any
from datetime import datetime, date, timedelta
import re
import dateparser
from google.adk.tools import FunctionTool

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}

def _to_date(d: datetime) -> date:
    return d.date()

def _last_weekend(ref: date) -> tuple[date, date]:
    # Most recent Sat–Sun before or including today
    dow = ref.weekday()  # Mon=0
    saturday = ref - timedelta(days=(dow - 5) % 7)
    sunday = saturday + timedelta(days=1)
    if ref < sunday:
        # bump back one week if we're before Sunday in current week
        saturday -= timedelta(days=7)
        sunday -= timedelta(days=7)
    return saturday, sunday

def _clamp_window(s: date, e: date, max_days: int = 31) -> tuple[date, date, str | None]:
    if (e - s).days + 1 > max_days:
        new_e = s + timedelta(days=max_days - 1)
        note = f"Truncated long window to {max_days} days ({s}..{new_e})."
        return s, new_e, note
    return s, e, None

_TIME_HINT = re.compile(r"\b(\d{1,2}(:\d{2})?\s*(am|pm))|\b(\d{1,2}:\d{2})\b|\bnoon\b|\bmidnight\b", re.I)

@FunctionTool
def infer_time_window(user_query: str, tz: str | None = None, country: str | None = None, lat: float | None = None) -> Dict[str, Any]:
    """
    Parse natural-language time expressions into start_date, end_date, granularity.
    Supports: explicit dates/ranges, "yesterday", "past 3 days", "last weekend",
              named weekdays ("between last Monday and Thursday"), week-of-month,
              seasons (north/south via lat), "monsoon <year>" heuristic (Jun–Sep).
    """
    now = datetime.utcnow().date()
    q = user_query.lower()

    # Explicit range with separators
    range_sep = re.search(r"\b(?:from|between)\s+(.+?)\s+(?:to|and|-)\s+(.+)", q)
    if range_sep:
        d1 = dateparser.parse(range_sep.group(1))
        d2 = dateparser.parse(range_sep.group(2))
        if d1 and d2:
            s, e = sorted((_to_date(d1), _to_date(d2)))
        else:
            s = e = now
    else:
        # relative phrases
        if "yesterday" in q:
            s = e = now - timedelta(days=1)
        elif "tomorrow" in q:
            s = e = now + timedelta(days=1)
        elif m := re.search(r"\bpast\s+(\d+)\s+day", q):
            n = int(m.group(1))
            s, e = now - timedelta(days=n-1), now
        elif "last weekend" in q:
            s, e = _last_weekend(now)
        elif m := re.search(r"first week of\s+([a-z]+)\s+(\d{4})", q):
            month = dateparser.parse(m.group(1) + " 1 " + m.group(2))
            s, e = _to_date(month), _to_date(month) + timedelta(days=6)
        elif m := re.search(r"third week of\s+([a-z]+)\s+(\d{4})", q):
            month = dateparser.parse(m.group(1) + " 15 " + m.group(2))
            s, e = _to_date(month), _to_date(month) + timedelta(days=6)
        elif m := re.search(r"(spring|summer|autumn|fall|winter)\s+(\d{4})", q):
            season, yr = m.group(1), int(m.group(2))
            nh = True if (lat is None or lat >= 0) else False
            if season in ("autumn", "fall"):
                season = "autumn"
            # simple seasonal windows
            if season == "spring":
                s, e = date(yr, 3, 1), date(yr, 5, 31)
            elif season == "summer":
                s, e = date(yr, 6, 1), date(yr, 8, 31)
            elif season == "autumn":
                s, e = date(yr, 9, 1), date(yr, 11, 30)
            else:  # winter
                s, e = date(yr, 12, 1), date(yr+1, 2, 28)
            if not nh:  # flip for southern hemisphere
                year = yr
                if season == "spring":
                    s, e = date(yr, 9, 1), date(yr, 11, 30)
                elif season == "summer":
                    s, e = date(yr, 12, 1), date(yr+1, 2, 28)
                elif season == "autumn":
                    s, e = date(yr, 3, 1), date(yr, 5, 31)
                else:
                    s, e = date(yr, 6, 1), date(yr, 8, 31)
        elif m := re.search(r"monsoon\s+(\d{4})", q):
            yr = int(m.group(1))
            s, e = date(yr, 6, 1), date(yr, 9, 30)
        else:
            # single explicit date or "last Tuesday", etc.
            parsed = dateparser.parse(user_query, settings={"RELATIVE_BASE": datetime.utcnow()})
            s = e = _to_date(parsed) if parsed else now

    # Granularity: hourly if any clock time hint
    granularity = "hourly" if _TIME_HINT.search(user_query) else "daily"

    s, e, note = _clamp_window(s, e, max_days=31)
    expl = f"Window: {s}..{e} (granularity={granularity})."
    if note:
        expl += f" {note}"
    return {"start_date": s.isoformat(), "end_date": e.isoformat(), "granularity": granularity, "explanation": expl}


