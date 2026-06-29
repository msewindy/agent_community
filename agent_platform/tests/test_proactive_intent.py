"""M5 D3 — work minutes intent parsing."""

from __future__ import annotations

from agent_platform.proactive.intent import parse_work_minutes_from_text


def test_parse_hours_zh():
    assert parse_work_minutes_from_text("我连续工作了2小时") == 120.0
    assert parse_work_minutes_from_text("已经干了 1.5 个小时") == 90.0


def test_parse_hours_en():
    assert parse_work_minutes_from_text("I worked for 2 hours today") == 120.0


def test_parse_invalid_or_empty():
    assert parse_work_minutes_from_text("") is None
    assert parse_work_minutes_from_text("你好") is None
    assert parse_work_minutes_from_text("工作了30小时") is None
