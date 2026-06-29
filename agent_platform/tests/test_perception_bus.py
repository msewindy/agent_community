"""M4 D4 — event bus + orchestrator + voice bridge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_platform.perception.bus import EventBus, JsonlAuditSubscriber, reset_event_bus
from agent_platform.perception.orchestrate import PerceptionOrchestrator
from agent_platform.perception.service import PerceptionService
from agent_platform.perception.vision_intent import is_vision_intent
from agent_platform.voice.perception_bridge import VoicePerceptionBridge


def test_vision_intent_bus_offline():
    assert is_vision_intent("看看桌上有什么")


def test_jsonl_audit_subscriber(tmp_path: Path):
    from agent_platform.memory.contracts import ObserveEvent, ObserveSource

    bus = EventBus()
    audit_path = tmp_path / "events.jsonl"
    bus.subscribe_all(JsonlAuditSubscriber(audit_path))
    ev = ObserveEvent(source=ObserveSource.reachy, text="test", modality=["vision"])
    bus.publish("perception.test", ev, meta={"k": 1})
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["topic"] == "perception.test"


def test_orchestrator_camera_off(tmp_path: Path):
    reset_event_bus()
    root = tmp_path / "store"
    cfg = {
        "backend": "mock",
        "store": {"root": str(root)},
        "policy": {"camera_enabled": False},
        "vision": {"enabled": True, "provider": "mock"},
    }
    svc = PerceptionService(config=cfg, store_root=root)
    orch = PerceptionOrchestrator(
        service=svc,
        auto_enable_camera_in_session=False,
    )
    turn = orch.handle_message("看下桌上有什么", session_id="s1")
    assert turn.reply_override
    assert "摄像头" in turn.reply_override
    assert (root / "events.jsonl").is_file()


@pytest.mark.skipif(
    not __import__("agent_platform.perception.frames", fromlist=["opencv_available"]).opencv_available(),
    reason="opencv not installed",
)
def test_orchestrator_describe_publishes_bus(tmp_path: Path):
    reset_event_bus()
    root = tmp_path / "store"
    cfg = {
        "backend": "mock",
        "store": {"root": str(root)},
        "policy": {"camera_enabled": True},
        "vision": {"enabled": True, "provider": "mock"},
    }
    svc = PerceptionService(config=cfg, store_root=root)
    orch = PerceptionOrchestrator(service=svc)
    turn = orch.handle_message("桌上那本书叫什么？", session_id="s2")
    assert turn.prompt_prefix
    assert (root / "sessions" / "s2.jsonl").is_file()
    topics = {
        json.loads(ln)["topic"]
        for ln in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    }
    assert "perception.describe" in topics


def test_voice_bridge_disabled():
    bridge = VoicePerceptionBridge(enabled=False)
    turn = bridge.pre_turn("看下桌上有什么", session_id="x")
    assert not turn.handled
