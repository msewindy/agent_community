"""proactive_service facade — evaluate + feedback (M5)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_platform.proactive._config import load_proactive_config, resolve_store_root
from agent_platform.proactive.memory_feedback import build_dismiss_content, write_dismiss_preference
from agent_platform.proactive.contracts import (
    ProactiveEvaluateRequest,
    ProactiveEvaluateResult,
    ProactiveFeedbackRequest,
    ProactiveFeedbackResult,
    ProactiveLevel,
    QuietHoursPolicy,
)
from agent_platform.proactive.engine import EngineConfig, ProactiveEngine
from agent_platform.proactive.session import (
    SessionProactiveState,
    is_dismiss_message,
    load_session,
    save_session,
)
from agent_platform.proactive.store import append_event_log, ensure_store


def _engine_config(cfg: dict) -> EngineConfig:
    q = cfg.get("quiet_hours") or {}
    t = (cfg.get("triggers") or {}).get("work_break") or {}
    level_str = (cfg.get("level") or "L0").upper()
    level = ProactiveLevel.L0 if level_str == "L0" else ProactiveLevel.L1
    return EngineConfig(
        enabled=bool(cfg.get("enabled", True)),
        level=level,
        quiet=QuietHoursPolicy(
            enabled=bool(q.get("enabled", True)),
            start=str(q.get("start", "22:00")),
            end=str(q.get("end", "07:00")),
            timezone=str(q.get("timezone", "Asia/Shanghai")),
        ),
        work_break_enabled=bool(t.get("enabled", True)),
        work_minutes_threshold=float(t.get("work_minutes_threshold", 120)),
        work_break_message=str(t.get("message", "已经 2 小时了，要不要休息一下？")),
    )


class ProactiveService:
    def __init__(
        self,
        config: Optional[dict] = None,
        store_root: Optional[Path] = None,
        memory_service: Optional[object] = None,
    ) -> None:
        self._cfg = config or load_proactive_config()
        self._layout = ensure_store(store_root or resolve_store_root(self._cfg))
        self._engine = ProactiveEngine(_engine_config(self._cfg))
        self._memory = memory_service

    @property
    def store_root(self) -> Path:
        return self._layout.root

    def _resolve_device_id(self, device_id: Optional[str]) -> str:
        if device_id:
            return device_id
        mem = self._memory
        if mem is not None:
            return getattr(mem, "default_device_id", "proactive-device")
        return "proactive-device"

    def status(self) -> dict:
        ec = _engine_config(self._cfg)
        return {
            "enabled": ec.enabled,
            "level": ec.level.value,
            "quiet_hours": ec.quiet.model_dump(),
            "work_break_threshold_min": ec.work_minutes_threshold,
        }

    def _session(self, session_id: str) -> SessionProactiveState:
        return load_session(self._layout.sessions_dir, session_id)

    def evaluate(self, req: ProactiveEvaluateRequest) -> ProactiveEvaluateResult:
        session = self._session(req.session_id)
        if req.work_minutes is not None:
            session.work_minutes_reported = float(req.work_minutes)
            save_session(self._layout.sessions_dir, session)

        result = self._engine.evaluate(req, session)
        line = f"evaluate {result.reason_code} session={req.session_id} allowed={result.allowed}"
        append_event_log(self._layout, line)

        if result.allowed and result.proposal:
            session.proposals_sent += 1
            session.last_proposal_trace = req.trace_id
            save_session(self._layout.sessions_dir, session)

        return result

    def record_feedback(self, req: ProactiveFeedbackRequest) -> ProactiveFeedbackResult:
        sess_cfg = self._cfg.get("session") or {}
        phrases = list(sess_cfg.get("dismiss_phrases") or [])
        snooze_on = bool(sess_cfg.get("snooze_rest_of_session", True))

        session = self._session(req.session_id)
        dismissed = is_dismiss_message(req.user_message, phrases)
        memory_id: Optional[str] = None
        memory_written = False
        memory_deduped = False
        memory_error: Optional[str] = None

        if dismissed and snooze_on:
            session.snoozed = True
            session.snooze_reason = "用户要求本会话内不要主动打扰"
            save_session(self._layout.sessions_dir, session)

        mem_cfg = self._cfg.get("memory") or {}
        if dismissed and req.write_memory and bool(mem_cfg.get("write_dismiss_preference", True)):
            content = build_dismiss_content(
                template=str(mem_cfg.get("dismiss_template", "")),
                user_message=req.user_message,
                session_id=req.session_id,
            )
            mem_svc = self._get_memory()
            dm = write_dismiss_preference(
                mem_svc,
                content=content,
                device_id=self._resolve_device_id(req.device_id),
                trace_id=req.trace_id,
                category=str(mem_cfg.get("dismiss_category", "preference")),
                dedup_enabled=bool(mem_cfg.get("dedup_enabled", True)),
                dedup_query=str(mem_cfg.get("dedup_search_query", "不希望主动提醒")),
            )
            memory_written = dm.written
            memory_deduped = dm.deduped
            memory_id = dm.record_id
            memory_error = dm.error

        append_event_log(
            self._layout,
            f"feedback dismissed={dismissed} session={req.session_id} snooze={session.snoozed} "
            f"mem={memory_written} dedup={memory_deduped}",
        )
        msg = "feedback recorded" if dismissed else "not a dismiss phrase"
        if memory_deduped:
            msg = "dismiss preference already in memory (deduped)"
        elif memory_error:
            msg = f"snooze ok but memory write failed: {memory_error}"

        return ProactiveFeedbackResult(
            session_snoozed=session.snoozed,
            memory_written=memory_written,
            memory_record_id=memory_id,
            memory_deduped=memory_deduped,
            memory_error=memory_error,
            dismissed=dismissed,
            message=msg,
        )

    def _get_memory(self):
        if self._memory is None:
            from agent_platform.memory.service import MemoryService

            self._memory = MemoryService()
        return self._memory

    def report_work_minutes(self, session_id: str, work_minutes: float) -> SessionProactiveState:
        """Persist user-reported work duration for L0 triggers (M5 D2)."""
        session = self._session(session_id)
        session.work_minutes_reported = float(work_minutes)
        save_session(self._layout.sessions_dir, session)
        append_event_log(
            self._layout,
            f"work_report session={session_id} minutes={work_minutes}",
        )
        return session
