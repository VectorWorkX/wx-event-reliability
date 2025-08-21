# tools/date_parse.py
from __future__ import annotations
from typing import Dict, Any, Tuple
from datetime import datetime, date, timedelta
import re
import dateparser
from google.adk.tools import FunctionTool

# ---------- regex & helpers ----------
_TIME_HINT = re.compile(
    r"\b(\d{1,2}(:\d{2})?\s*(am|pm))\b|\b(\d{1,2}:\d{2})\b|\bnoon\b|\bmidnight\b",
    re.I
)

def _to_date(d: datetime) -> date:
    return d.date()

def _last_weekend(ref: date) -> Tuple[date, date]:
    """Most recent Sat–Sun fully in the past relative to ref."""
    prev_day = ref - timedelta(days=1)
    saturday = prev_day - timedelta(days=(prev_day.weekday() - 5) % 7)
    sunday = saturday + timedelta(days=1)
    return saturday, sunday

def _this_weekend(ref: date) -> Tuple[date, date]:
    """The upcoming Sat–Sun containing/after ref."""
    saturday = ref + timedelta(days=(5 - ref.weekday()) % 7)
    sunday = saturday + timedelta(days=1)
    return saturday, sunday

def _this_week(ref: date) -> Tuple[date, date]:
    """Monday..Sunday of the current week (Mon-first)."""
    start = ref - timedelta(days=ref.weekday())
    end = start + timedelta(days=6)
    return start, end

def _next_week(ref: date) -> Tuple[date, date]:
    """Monday..Sunday of the week AFTER the current week."""
    start_this = ref - timedelta(days=ref.weekday())
    start_next = start_this + timedelta(days=7)
    end_next = start_next + timedelta(days=6)
    return start_next, end_next

def _clamp_window(s: date, e: date, max_days: int = 31) -> Tuple[date, date, str]:
    if (e - s).days + 1 > max_days:
        new_e = s + timedelta(days=max_days - 1)
        return s, new_e, f"Truncated long window to {max_days} days ({s}..{new_e})."
    return s, e, ""

def _season_window(season: str, yr: int, lat: float) -> Tuple[date, date]:
    """Simple meteorological seasons; flip for SH (lat<0)."""
    nh = True if lat >= 0.0 else False  # treat equator as NH by default
    s = season.lower()
    if s in ("fall", "autumn"):
        s = "autumn"

    # NH defaults
    if s == "spring":
        nh_s, nh_e = date(yr, 3, 1), date(yr, 5, 31)
    elif s == "summer":
        nh_s, nh_e = date(yr, 6, 1), date(yr, 8, 31)
    elif s == "autumn":
        nh_s, nh_e = date(yr, 9, 1), date(yr, 11, 30)
    else:  # winter
        nh_s, nh_e = date(yr, 12, 1), date(yr + 1, 2, 28)

    if nh:
        return nh_s, nh_e
    # SH flip
    if s == "spring":
        return date(yr, 9, 1), date(yr, 11, 30)
    if s == "summer":
        return date(yr, 12, 1), date(yr + 1, 2, 28)
    if s == "autumn":
        return date(yr, 3, 1), date(yr, 5, 31)
    return date(yr, 6, 1), date(yr, 8, 31)

# ---------- main tool ----------
@FunctionTool
def infer_time_window(
    user_query: str,
    tz: str = "",       # keep params primitive (no Optional) for ADK auto-calling
    country: str = "",
    lat: float = 0.0
) -> Dict[str, Any]:
    """
    Parse natural-language time expressions into:
      - start_date, end_date (YYYY-MM-DD)
      - granularity: 'hourly' if clock-time present, else 'daily'
      - time_mode:  'hindcast' | 'forecast' | 'mixed'
      - snap_hint:  {'now_utc': ISO8601, 'prefer_latest_model_run': bool}
      - explanation

    Key: Anchors relative phrases (e.g., 'tomorrow') to *now* via dateparser RELATIVE_BASE to avoid wrong years.
    """
    # Anchor all relative parsing to "now"
    now_dt = datetime.utcnow()
    today = now_dt.date()
    q = user_query.strip().lower()

    # --- explicit range: "from/between ... to/and/ -" ---
    m = re.search(r"\b(?:from|between)\s+(.+?)\s+(?:to|and|-)\s+(.+)", q)
    if m:
        d1 = dateparser.parse(m.group(1), settings={"RELATIVE_BASE": now_dt})
        d2 = dateparser.parse(m.group(2), settings={"RELATIVE_BASE": now_dt})
        if d1 and d2:
            s, e = sorted((_to_date(d1), _to_date(d2)))
        else:
            s = e = today

    else:
        # --- common relative phrases (explicitly handled first) ---
        if "yesterday" in q:
            s = e = today - timedelta(days=1)

        elif "tomorrow" in q:
            s = e = today + timedelta(days=1)

        elif re.search(r"\bpast\s+(\d+)\s+day", q):
            n = int(re.search(r"\bpast\s+(\d+)\s+day", q).group(1))
            s, e = today - timedelta(days=n - 1), today

        elif "last weekend" in q:
            s, e = _last_weekend(today)

        elif "this weekend" in q or "coming weekend" in q:
            s, e = _this_weekend(today)

        elif "this week" in q:
            s, e = _this_week(today)

        elif "next week" in q:
            s, e = _next_week(today)

        # week-of-month: "first/second/third/fourth week of Month YYYY"
        elif m := re.search(r"(first|second|third|fourth)\s+week\s+of\s+([a-z]+)\s+(\d{4})", q):
            which, mon, yr = m.group(1), m.group(2), int(m.group(3))
            base = dateparser.parse(f"{mon} 1 {yr}", settings={"RELATIVE_BASE": now_dt})
            start = _to_date(base) if base else date(yr, 1, 1)
            add_weeks = {"first": 0, "second": 1, "third": 2, "fourth": 3}[which]
            s = start + timedelta(days=add_weeks * 7)
            e = s + timedelta(days=6)

        # seasons / monsoon
        elif m := re.search(r"(spring|summer|autumn|fall|winter)\s+(\d{4})", q):
            s, e = _season_window(m.group(1), int(m.group(2)), lat)

        elif m := re.search(r"monsoon\s+(\d{4})", q):
            yr = int(m.group(1))
            s, e = date(yr, 6, 1), date(yr, 9, 30)

        # fallback: single explicit date / "last Tuesday" etc.
        else:
            parsed = dateparser.parse(user_query, settings={"RELATIVE_BASE": now_dt})
            s = e = _to_date(parsed) if parsed else today

    # Ensure s <= e
    if e < s:
        s, e = e, s

    # granularity: hourly if any clock-time hint
    granularity = "hourly" if _TIME_HINT.search(user_query) else "daily"

    # clamp long windows
    s, e, note = _clamp_window(s, e, max_days=31)

    # classify time intent for downstream fetch logic
    if e < today:
        time_mode = "hindcast"     # strictly past → archive
    elif s > today:
        time_mode = "forecast"     # strictly future → latest-model forecast
    else:
        time_mode = "mixed"        # spans today → split archive+forecast

    snap_hint = {
        "now_utc": now_dt.isoformat(),
        "prefer_latest_model_run": (time_mode != "hindcast"),
    }

    expl = f"Window: {s}..{e} (granularity={granularity}, mode={time_mode})."
    if note:
        expl += f" {note}"

    return {
        "start_date": s.isoformat(),
        "end_date": e.isoformat(),
        "granularity": granularity,
        "time_mode": time_mode,
        "snap_hint": snap_hint,
        "explanation": expl,
    }

