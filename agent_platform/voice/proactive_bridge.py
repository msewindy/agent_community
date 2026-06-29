"""Voice ↔ proactive_service bridge (M5 D4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_platform.proactive.contracts import ProactiveEvaluateRequest, ProactiveFeedbackRequest
from agent_platform.proactive.intent import parse_work_minutes_from_text
from agent_platform.proactive.service import ProactiveService


@dataclass
class VoiceProactiveTurn:
    """Outcome of proactive hooks on a voice/chat turn."""

    handled: bool = False
    reply_override: Optional[str] = None
    dismiss_feedback: bool = False
    work_minutes_reported: Optional[float] = None
    proactive_nudge: Optional[str] = None
    proactive_allowed: bool = False
    reason_code: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def load_voice_proactive_config(voice_cfg: dict) -> dict:
    pc = voice_cfg.get("proactive") or {}
    return {
        "enabled": bool(pc.get("enabled", True)),
        "auto_feedback_on_dismiss": bool(pc.get("auto_feedback_on_dismiss", True)),
        "auto_parse_work_minutes": bool(pc.get("auto_parse_work_minutes", True)),
        "nudge_after_work_report": bool(pc.get("nudge_after_work_report", False)),
    }


class VoiceProactiveBridge:
    def __init__(
        self,
        *,
        enabled: bool = True,
        auto_feedback_on_dismiss: bool = True,
        auto_parse_work_minutes: bool = True,
        nudge_after_work_report: bool = False,
        service: Optional[ProactiveService] = None,
    ) -> None:
        self.enabled = enabled
        self._auto_feedback = auto_feedback_on_dismiss
        self._auto_work = auto_parse_work_minutes
        self._nudge_after_work = nudge_after_work_report
        self._svc = service

    @classmethod
    def from_voice_config(cls, voice_cfg: dict) -> VoiceProactiveBridge:
        flags = load_voice_proactive_config(voice_cfg)
        return cls(**flags)

    def _get_svc(self) -> ProactiveService:
        if self._svc is None:
            self._svc = ProactiveService()
        return self._svc

    def on_user_message(
        self,
        user_text: str,
        *,
        session_id: Optional[str] = None,
    ) -> VoiceProactiveTurn:
        """US-5: dismiss → snooze+memory; work hours → report; optional nudge."""
        if not self.enabled or not session_id:
            return VoiceProactiveTurn()

        svc = self._get_svc()
        turn = VoiceProactiveTurn(handled=True)
        text = (user_text or "").strip()

        if self._auto_feedback:
            fb = svc.record_feedback(
                ProactiveFeedbackRequest(
                    session_id=session_id,
                    user_message=text,
                    write_memory=True,
                )
            )
            if fb.dismissed:
                turn.dismiss_feedback = True
                turn.handled = True
                if fb.session_snoozed:
                    turn.reply_override = (
                        "好的，本会话内我不会再主动打扰你。"
                        if not fb.memory_error
                        else "好的，本会话内我不会再主动打扰你。（偏好记入记忆时出现问题）"
                    )
                turn.meta["memory_written"] = fb.memory_written
                turn.meta["memory_deduped"] = fb.memory_deduped
                return turn

        work_m: Optional[float] = None
        if self._auto_work:
            work_m = parse_work_minutes_from_text(text)
            if work_m is not None:
                svc.report_work_minutes(session_id, work_m)
                turn.work_minutes_reported = work_m
                turn.meta["work_reported"] = True

        if self._nudge_after_work and work_m is not None and work_m >= 120:
            nudge = self.maybe_proactive_nudge(
                session_id=session_id,
                work_minutes=work_m,
                natural_pause=True,
            )
            if nudge.proactive_nudge:
                turn.proactive_nudge = nudge.proactive_nudge
                turn.reply_override = nudge.proactive_nudge

        return turn

    def maybe_proactive_nudge(
        self,
        *,
        session_id: str,
        work_minutes: Optional[float] = None,
        natural_pause: bool = True,
    ) -> VoiceProactiveTurn:
        """Agent-initiated proactive speech check (before TTS)."""
        if not self.enabled:
            return VoiceProactiveTurn(reason_code="disabled")

        svc = self._get_svc()
        result = svc.evaluate(
            ProactiveEvaluateRequest(
                session_id=session_id,
                work_minutes=work_minutes,
                natural_pause=natural_pause,
            )
        )
        out = VoiceProactiveTurn(
            handled=True,
            proactive_allowed=result.allowed,
            reason_code=result.reason_code,
            meta={"message": result.message},
        )
        if result.allowed and result.proposal:
            out.proactive_nudge = result.proposal.message
        elif result.reason_code == "quiet_hours":
            out.reply_override = None
            out.meta["blocked"] = "quiet_hours"
        elif result.reason_code == "session_snoozed":
            out.meta["blocked"] = "session_snoozed"
        return out

    def turn_metadata(self, turn: VoiceProactiveTurn) -> dict[str, Any]:
        return {
            "proactive_handled": turn.handled,
            "proactive_dismiss": turn.dismiss_feedback,
            "proactive_work_minutes": turn.work_minutes_reported,
            "proactive_nudge": turn.proactive_nudge is not None,
            "proactive_reason": turn.reason_code or None,
        }
