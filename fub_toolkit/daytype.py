"""
Pick today's day type from Google Calendar events.

Karan's BCLDB shifts are calendar events titled "BCLDB Shift". Rules:

* a "BCLDB" event starting today           -> ``shift``
* ...that was added less than 24h before it -> ``minimum`` (called in last minute)
* otherwise                                  -> ``office``

The morning routine reads today's events with the Google Calendar connector,
saves them as JSON (the Calendar API's own shape), and passes them here.
"""

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .models import LOCAL_TZ, parse_dt

SHIFT_KEYWORD = "bcldb"
CALLED_IN_HOURS = 24


def _start(event: Dict[str, Any]) -> Optional[datetime]:
    start = event.get("start") or {}
    if isinstance(start, str):
        return parse_dt(start)
    if start.get("dateTime"):
        return parse_dt(start["dateTime"])
    if start.get("date"):
        d = date.fromisoformat(start["date"])
        return datetime(d.year, d.month, d.day, tzinfo=LOCAL_TZ)
    return None


def day_type_for(events: List[Dict[str, Any]], today: date) -> str:
    """Return "office", "shift" or "minimum" for ``today``."""
    kind = "office"
    for event in events:
        if event.get("status") == "cancelled":
            continue
        if SHIFT_KEYWORD not in str(event.get("summary") or "").lower():
            continue
        start = _start(event)
        if start is None or start.astimezone(LOCAL_TZ).date() != today:
            continue
        created = parse_dt(event.get("created"))
        if created is not None and start - created < timedelta(hours=CALLED_IN_HOURS):
            return "minimum"
        kind = "shift"
    return kind


def load_events(path: str) -> List[Dict[str, Any]]:
    """Read events saved from Google Calendar (a list, or {"events": [...]})."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("events") or data.get("items") or []
    return [e for e in data if isinstance(e, dict)]
