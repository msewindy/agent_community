"""Proactive engine — L0 rules (M5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from agent_platform.memory.contracts import utc_now
from agent_platform.proactive.contracts import (
    ProactiveEvaluateRequest,
    ProactiveEvaluateResult,
    ProactiveLevel,
    ProactiveProposal,
    ProactiveReason,
    QuietHoursPolicy,
)
from agent_platform.proactive.quiet_hours import in_quiet_hours
from agent_platform.proactive.session import SessionProactiveState


@dataclass
class EngineConfig:
    enabled: bool = True
    level: ProactiveLevel = ProactiveLevel.L0
    quiet: QuietHoursPolicy = field(default_factory=lambda: QuietHoursPolicy())
    work_break_enabled: bool = True
    work_minutes_threshold: float = 120.0
    work_break_message: str = "已经 2 小时了，要不要休息一下？"


class ProactiveEngine:
    """L0: quiet hours + session snooze + work_minutes threshold."""

    def __init__(self, config: EngineConfig) -> None:
        self._cfg = config

    def evaluate(
        self,
        req: ProactiveEvaluateRequest,
        session: SessionProactiveState,
    ) -> ProactiveEvaluateResult:
        if not self._cfg.enabled:
            return ProactiveEvaluateResult(
                allowed=False,
                reason_code=ProactiveReason.disabled.value,
                message="proactive disabled in config",
            )

        now = req.now or utc_now()
        if self._cfg.quiet.enabled and in_quiet_hours(
            now,
            start=self._cfg.quiet.start,
            end=self._cfg.quiet.end,
            timezone=self._cfg.quiet.timezone,
        ):
            return ProactiveEvaluateResult(
                allowed=False,
                reason_code=ProactiveReason.quiet_hours.value,
                message="静默时段内不主动发声",
            )

        if session.snoozed:
            return ProactiveEvaluateResult(
                allowed=False,
                reason_code=ProactiveReason.session_snoozed.value,
                message=session.snooze_reason or "本会话已静默主动提醒",
            )

        work_m = req.work_minutes
        if work_m is None and session.work_minutes_reported > 0:
            work_m = session.work_minutes_reported

        if self._cfg.work_break_enabled and work_m is not None:
            if work_m >= self._cfg.work_minutes_threshold:
                if req.natural_pause or self._cfg.level == ProactiveLevel.L0:
                    proposal = ProactiveProposal(
                        message=self._cfg.work_break_message,
                        level=self._cfg.level,
                        trigger="work_break",
                        trace_id=req.trace_id,
                    )
                    return ProactiveEvaluateResult(
                        allowed=True,
                        reason_code=ProactiveReason.ok.value,
                        proposal=proposal,
                        message="work_break trigger",
                    )

        return ProactiveEvaluateResult(
            allowed=False,
            reason_code=ProactiveReason.no_trigger.value,
            message="no proactive trigger matched",
        )
