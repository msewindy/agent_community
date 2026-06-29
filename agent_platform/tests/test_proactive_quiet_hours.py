"""M5 — quiet hours."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agent_platform.proactive.quiet_hours import in_quiet_hours


def test_overnight_quiet():
    tz = ZoneInfo("Asia/Shanghai")
    assert in_quiet_hours(
        datetime(2026, 5, 20, 23, 0, tzinfo=tz),
        start="22:00",
        end="07:00",
        timezone="Asia/Shanghai",
    )
    assert in_quiet_hours(
        datetime(2026, 5, 21, 6, 30, tzinfo=tz),
        start="22:00",
        end="07:00",
        timezone="Asia/Shanghai",
    )
    assert not in_quiet_hours(
        datetime(2026, 5, 21, 12, 0, tzinfo=tz),
        start="22:00",
        end="07:00",
        timezone="Asia/Shanghai",
    )
