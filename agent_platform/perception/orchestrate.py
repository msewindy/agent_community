"""Voice / chat turn orchestration — vision intent → describe → event bus (M4 D4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from agent_platform.memory.contracts import ObserveEvent
from agent_platform.memory.trace import trace_from_session
from agent_platform.perception.bus import EventBus, get_event_bus, wire_default_subscribers
from agent_platform.perception.contracts import DescribeRequest, DescribeResult
from agent_platform.perception.service import PerceptionService
from agent_platform.perception.session import SessionVisionContext, format_session_prompt_prefix
from agent_platform.perception.vision_intent import is_vision_intent

_CAMERA_OFF_REPLY = "摄像头当前关闭，无法完成视觉问答。你可以在设置中开启摄像头后再试。"


@dataclass
class OrchestratedTurn:
    """Result of pre-processing a user message before Hermes."""

    handled: bool = False
    vision_intent: bool = False
    describe: Optional[DescribeResult] = None
    reply_override: Optional[str] = None
    prompt_prefix: Optional[str] = None
    observe_events: list[ObserveEvent] = field(default_factory=list)
    trace_id: str = ""
    session_id: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)


class PerceptionOrchestrator:
    """M4 D4: route vision questions → describe → bus; else pass-through."""

    def __init__(
        self,
        service: Optional[PerceptionService] = None,
        bus: Optional[EventBus] = None,
        *,
        auto_enable_camera_in_session: bool = False,
        memory_observe: bool = False,
    ) -> None:
        self._svc = service or PerceptionService()
        cfg = self._svc._cfg  # noqa: SLF001 — orchestrator needs bus config
        bus_cfg = cfg.get("bus") or {}
        self._auto_camera = auto_enable_camera_in_session or bool(
            bus_cfg.get("auto_enable_camera_in_session", False)
        )
        self._bus = bus
        if self._bus is None:
            self._bus = get_event_bus()
            if not bus_cfg.get("skip_default_wire"):
                wire_default_subscribers(
                    self._bus,
                    store_root=self._svc.store_root,
                    memory_observe=memory_observe or bool(bus_cfg.get("memory_observe", False)),
                )

    @property
    def service(self) -> PerceptionService:
        return self._svc

    @property
    def bus(self) -> EventBus:
        return self._bus

    def _resolve_trace(self, session_id: Optional[str], trace_id: Optional[str]) -> str:
        if trace_id:
            return trace_id
        if session_id:
            return trace_from_session(session_id)
        return str(uuid4())

    def handle_message(
        self,
        user_text: str,
        *,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        scene: str = "desk",
    ) -> OrchestratedTurn:
        text = (user_text or "").strip()
        tid = self._resolve_trace(session_id, trace_id)
        turn = OrchestratedTurn(
            trace_id=tid,
            session_id=session_id,
            vision_intent=is_vision_intent(text),
        )
        if not turn.vision_intent:
            return turn

        turn.handled = True
        if not self._svc.vision_enabled():
            turn.reply_override = "视觉描述功能未启用。"
            turn.meta["reason"] = "vision_disabled"
            return turn

        if self._auto_camera and not self._svc.policy.camera_enabled:
            self._svc.set_policy(camera_enabled=True)

        if not self._svc.policy.camera_enabled:
            turn.reply_override = _CAMERA_OFF_REPLY
            turn.meta["reason"] = "camera_disabled"
            self._publish_system_observe(
                tid,
                session_id,
                text=_CAMERA_OFF_REPLY,
                scene=scene,
                extra={"reason": "camera_disabled", "question": text},
            )
            return turn

        result = self._svc.describe(
            DescribeRequest(
                question=text,
                scene=scene,
                trace_id=tid,
                device_id=self._svc.default_device_id,
                session_id=session_id,
            )
        )
        turn.describe = result
        if not result.allowed:
            turn.reply_override = result.message or "视觉问答失败。"
            turn.meta["reason"] = result.reason_code
            return turn

        if result.event:
            turn.observe_events.append(result.event)
            ctx = SessionVisionContext(
                description=result.description or result.event.text or "",
                trace_id=tid,
                frame_path=result.frame_path,
                question=text,
            )
            turn.prompt_prefix = format_session_prompt_prefix(ctx, user_question=text)
        turn.meta["model"] = result.model
        turn.meta["latency_ms"] = result.latency_ms
        return turn

    def _publish_system_observe(
        self,
        trace_id: str,
        session_id: Optional[str],
        *,
        text: str,
        scene: str,
        extra: dict[str, Any],
    ) -> None:
        from agent_platform.memory.contracts import ObserveSource

        ev = ObserveEvent(
            source=ObserveSource.reachy,
            modality=["vision"],
            text=text,
            payload={"scene": scene, **extra, "system": True},
            trace_id=trace_id,
            device_id=self._svc.default_device_id,
            scene=scene,
        )
        self._bus.publish(
            "perception.policy_denied",
            ev,
            meta={"session_id": session_id},
        )
