"""Pure helper — add N business days (Mon-Fri) to a datetime in the operator's timezone.

Weekend arithmetic:
- If the base date falls on Sat/Sun, the "start" is interpreted as the next Monday.
- Only Mon-Fri days count toward the offset.
- The returned datetime preserves the base date's time-of-day, expressed in the same timezone.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def business_days_add(base: datetime, days: int, tz: str) -> datetime:
    if days < 0:
        raise ValueError("business_days_add expects a non-negative day count.")

    zone = ZoneInfo(tz)
    local = base.astimezone(zone) if base.tzinfo else base.replace(tzinfo=zone)

    remaining = days
    current = local
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0..Fri=4
            remaining -= 1
    return current
