"""M5 — proactive service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.service import MemoryService
from agent_platform.proactive.contracts import ProactiveEvaluateRequest, ProactiveFeedbackRequest
from agent_platform.proactive.service import ProactiveService


def _svc(root: Path) -> ProactiveService:
    cfg = {
        "enabled": True,
        "quiet_hours": {"enabled": True, "start": "22:00", "end": "07:00", "timezone": "UTC"},
        "triggers": {"work_break": {"enabled": True, "work_minutes_threshold": 120}},
        "session": {"snooze_rest_of_session": True},
        "memory": {"write_dismiss_preference": True},
        "store": {"root": str(root)},
    }
    mem = MemoryService(adapter=MockMemAdapter(), config={"backend": "mock", "gate": {"enabled": False}})
    return ProactiveService(config=cfg, store_root=root, memory_service=mem)


def test_work_break_and_snooze(tmp_path: Path):
    svc = _svc(tmp_path)
    r = svc.evaluate(
        ProactiveEvaluateRequest(session_id="x", work_minutes=130, natural_pause=True)
    )
    assert r.allowed
    assert r.proposal
    fb = svc.record_feedback(
        ProactiveFeedbackRequest(session_id="x", user_message="别打扰")
    )
    assert fb.session_snoozed
    r2 = svc.evaluate(
        ProactiveEvaluateRequest(session_id="x", work_minutes=200, natural_pause=True)
    )
    assert not r2.allowed
    assert r2.reason_code == "session_snoozed"


def test_quiet_hours_block(tmp_path: Path):
    svc = _svc(tmp_path)
    r = svc.evaluate(
        ProactiveEvaluateRequest(
            session_id="q",
            now=datetime(2026, 1, 1, 23, 0, tzinfo=ZoneInfo("UTC")),
        )
    )
    assert not r.allowed
    assert r.reason_code == "quiet_hours"
