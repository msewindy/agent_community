"""M5 D4 — VoiceProactiveBridge."""

from __future__ import annotations

from pathlib import Path

from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.service import MemoryService
from agent_platform.proactive.service import ProactiveService
from agent_platform.voice.proactive_bridge import VoiceProactiveBridge, load_voice_proactive_config


def _bridge(root: Path) -> VoiceProactiveBridge:
    cfg = {
        "enabled": True,
        "quiet_hours": {"enabled": False},
        "triggers": {"work_break": {"enabled": True, "work_minutes_threshold": 120}},
        "session": {"snooze_rest_of_session": True},
        "memory": {"write_dismiss_preference": True},
        "store": {"root": str(root)},
    }
    mem = MemoryService(
        adapter=MockMemAdapter(),
        config={"backend": "mock", "gate": {"enabled": False}},
    )
    svc = ProactiveService(config=cfg, store_root=root, memory_service=mem)
    return VoiceProactiveBridge(
        nudge_after_work_report=True,
        service=svc,
    )


def test_load_voice_proactive_config():
    flags = load_voice_proactive_config(
        {"proactive": {"enabled": False, "nudge_after_work_report": True}}
    )
    assert flags["enabled"] is False
    assert flags["nudge_after_work_report"] is True


def test_dismiss_snooze(tmp_path: Path):
    b = _bridge(tmp_path)
    turn = b.on_user_message("别打扰", session_id="t1")
    assert turn.reply_override
    nudge = b.maybe_proactive_nudge(session_id="t1", work_minutes=200)
    assert not nudge.proactive_allowed


def test_work_report_nudge(tmp_path: Path):
    b = _bridge(tmp_path)
    turn = b.on_user_message("连续工作2小时", session_id="t2")
    assert turn.work_minutes_reported == 120.0
    assert turn.reply_override and "休息" in turn.reply_override
