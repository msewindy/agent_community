"""Voice ↔ perception orchestrator bridge (M4 D4)."""

from __future__ import annotations

from typing import Any, Optional

from agent_platform.perception.orchestrate import OrchestratedTurn, PerceptionOrchestrator


def load_voice_perception_config(voice_cfg: dict) -> dict:
    """Merge voice.yaml perception section into orchestrator flags."""
    pc = voice_cfg.get("perception") or {}
    return {
        "enabled": bool(pc.get("enabled", False)),
        "auto_enable_camera_in_session": bool(pc.get("auto_enable_camera_in_session", True)),
        "memory_observe": bool(pc.get("memory_observe", False)),
    }


class VoicePerceptionBridge:
    def __init__(
        self,
        *,
        enabled: bool = True,
        auto_enable_camera_in_session: bool = True,
        memory_observe: bool = False,
        orchestrator: Optional[PerceptionOrchestrator] = None,
    ) -> None:
        self.enabled = enabled
        self._orch = orchestrator
        self._orch_kwargs = {
            "auto_enable_camera_in_session": auto_enable_camera_in_session,
            "memory_observe": memory_observe,
        }

    @classmethod
    def from_voice_config(cls, voice_cfg: dict) -> VoicePerceptionBridge:
        flags = load_voice_perception_config(voice_cfg)
        return cls(
            enabled=flags["enabled"],
            auto_enable_camera_in_session=flags["auto_enable_camera_in_session"],
            memory_observe=flags["memory_observe"],
        )

    def _get_orch(self) -> PerceptionOrchestrator:
        if self._orch is None:
            self._orch = PerceptionOrchestrator(**self._orch_kwargs)
        return self._orch

    def pre_turn(
        self,
        user_text: str,
        *,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> OrchestratedTurn:
        if not self.enabled:
            return OrchestratedTurn(session_id=session_id, trace_id=trace_id or "")
        return self._get_orch().handle_message(
            user_text,
            session_id=session_id,
            trace_id=trace_id,
        )

    def apply_to_hermes_prompt(self, user_text: str, turn: OrchestratedTurn) -> str:
        if turn.prompt_prefix:
            return f"{turn.prompt_prefix}\n\n用户说：{user_text}"
        return user_text

    def turn_metadata(self, turn: OrchestratedTurn) -> dict[str, Any]:
        return {
            "perception_handled": turn.handled,
            "vision_intent": turn.vision_intent,
            "perception_reply_override": turn.reply_override is not None,
            "perception_trace_id": turn.trace_id or None,
            "perception_model": turn.meta.get("model"),
            "perception_latency_ms": turn.meta.get("latency_ms"),
            "perception_reason": turn.meta.get("reason"),
        }
