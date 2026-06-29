"""Quiet hours — hard block for proactive speech (US-5)."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


def _parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return time(hour=hour, minute=minute)


def in_quiet_hours(
    now: datetime,
    *,
    start: str = "22:00",
    end: str = "07:00",
    timezone: str = "Asia/Shanghai",
) -> bool:
    """True if `now` falls in [start, end) overnight window."""
    tz = ZoneInfo(timezone)
    if now.tzinfo is None:
        local = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    else:
        local = now.astimezone(tz)
    t = local.time()
    start_t = _parse_hhmm(start)
    end_t = _parse_hhmm(end)
    if start_t <= end_t:
        return start_t <= t < end_t
    return t >= start_t or t < end_t
