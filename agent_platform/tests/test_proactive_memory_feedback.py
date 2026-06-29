"""M5 D2 — dismiss memory write + dedup."""

from __future__ import annotations

from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.service import MemoryService
from agent_platform.proactive.contracts import ProactiveFeedbackRequest
from agent_platform.proactive.memory_feedback import build_dismiss_content, write_dismiss_preference
from agent_platform.proactive.service import ProactiveService


def test_build_dismiss_content():
    c = build_dismiss_content(
        template="用户不希望主动提醒",
        user_message="我在做正事，别打扰",
        session_id="s1",
    )
    assert "别打扰" in c
    assert "用户不希望" in c


def test_dedup_on_second_write():
    mem = MemoryService(adapter=MockMemAdapter(), config={"backend": "mock", "gate": {"enabled": False}})
    content = "用户不希望主动提醒（US-5）"
    r1 = write_dismiss_preference(
        mem, content=content, device_id="dev", trace_id="t1"
    )
    assert r1.written
    r2 = write_dismiss_preference(
        mem, content=content, device_id="dev", trace_id="t2"
    )
    assert r2.deduped
    assert not r2.written


def test_service_feedback_dedup(tmp_path):
    root = tmp_path / "p"
    mem = MemoryService(adapter=MockMemAdapter(), config={"backend": "mock", "gate": {"enabled": False}})
    cfg = {
        "memory": {"write_dismiss_preference": True, "dedup_enabled": True},
        "session": {"snooze_rest_of_session": True},
        "store": {"root": str(root)},
    }
    svc = ProactiveService(config=cfg, store_root=root, memory_service=mem)
    svc.record_feedback(ProactiveFeedbackRequest(session_id="a", user_message="别打扰"))
    r2 = svc.record_feedback(ProactiveFeedbackRequest(session_id="b", user_message="不要打扰"))
    assert r2.memory_deduped
