"""Hermes tools — proactive_service US-5 (M5 D2)."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agent_platform.integrations.hermes.tools import (
    _tool_error,
    _tool_result,
    bootstrap_agent_platform,
)

logger = logging.getLogger(__name__)


def _session_trace_id(kwargs: dict) -> Optional[str]:
    sid = kwargs.get("current_session_id") or kwargs.get("session_id")
    if not sid:
        return None
    return f"hermes-{sid}"


def _get_proactive_service():
    bootstrap_agent_platform()
    from agent_platform.proactive.service import ProactiveService

    return ProactiveService()


def check_proactive_available() -> bool:
    try:
        bootstrap_agent_platform()
        from agent_platform.proactive.service import ProactiveService

        ProactiveService()
        return True
    except Exception as e:
        logger.debug("proactive not available: %s", e)
        return False


def agent_proactive_status(args: dict, **kwargs) -> str:
    try:
        svc = _get_proactive_service()
        st = svc.status()
        sess = args.get("session_id") or kwargs.get("current_session_id")
        if sess:
            s = svc._session(str(sess))  # noqa: SLF001
            st["session_snoozed"] = s.snoozed
            st["session_work_minutes"] = s.work_minutes_reported
        return _tool_result({"success": True, **st})
    except Exception as e:
        logger.exception("agent_proactive_status failed")
        return _tool_error(str(e))


def agent_proactive_evaluate(args: dict, **kwargs) -> str:
    """Check if agent may speak proactively (respect quiet hours + snooze)."""
    try:
        from agent_platform.proactive.contracts import ProactiveEvaluateRequest

        sid = args.get("session_id") or kwargs.get("current_session_id")
        if not sid:
            return _tool_error("Missing session_id (or Hermes current_session_id)")

        req_kw: dict[str, Any] = {
            "session_id": str(sid),
            "natural_pause": bool(args.get("natural_pause", True)),
        }
        if args.get("work_minutes") is not None:
            req_kw["work_minutes"] = float(args["work_minutes"])
        tid = args.get("trace_id") or _session_trace_id(kwargs)
        if tid:
            req_kw["trace_id"] = tid

        svc = _get_proactive_service()
        result = svc.evaluate(ProactiveEvaluateRequest(**req_kw))
        payload: dict[str, Any] = {
            "success": result.allowed,
            "allowed": result.allowed,
            "reason_code": result.reason_code,
            "message": result.message,
        }
        if result.proposal:
            payload["proposal"] = result.proposal.message
            payload["trigger"] = result.proposal.trigger
            payload["level"] = result.proposal.level.value
        return _tool_result(payload)
    except Exception as e:
        logger.exception("agent_proactive_evaluate failed")
        return _tool_error(f"Evaluate failed: {e}")


def agent_proactive_feedback(args: dict, **kwargs) -> str:
    """User dismisses proactive care — snooze session + write memory preference."""
    message = (args.get("message") or args.get("user_message") or "").strip()
    if not message:
        return _tool_error("Missing required parameter: message")

    try:
        from agent_platform.proactive.contracts import ProactiveFeedbackRequest

        sid = args.get("session_id") or kwargs.get("current_session_id")
        if not sid:
            return _tool_error("Missing session_id")

        svc = _get_proactive_service()
        result = svc.record_feedback(
            ProactiveFeedbackRequest(
                session_id=str(sid),
                user_message=message,
                device_id=args.get("device_id"),
                write_memory=not bool(args.get("no_memory", False)),
                trace_id=args.get("trace_id") or _session_trace_id(kwargs) or None,
            )
        )
        return _tool_result(
            {
                "success": True,
                "dismissed": result.dismissed,
                "session_snoozed": result.session_snoozed,
                "memory_written": result.memory_written,
                "memory_deduped": result.memory_deduped,
                "memory_record_id": result.memory_record_id,
                "memory_error": result.memory_error,
                "message": result.message,
            }
        )
    except Exception as e:
        logger.exception("agent_proactive_feedback failed")
        return _tool_error(f"Feedback failed: {e}")


def agent_proactive_report_work(args: dict, **kwargs) -> str:
    """Report work duration for break reminder threshold (US-5 scene 1)."""
    try:
        minutes = args.get("work_minutes")
        if minutes is None:
            return _tool_error("Missing work_minutes")
        sid = args.get("session_id") or kwargs.get("current_session_id")
        if not sid:
            return _tool_error("Missing session_id")

        svc = _get_proactive_service()
        state = svc.report_work_minutes(str(sid), float(minutes))
        return _tool_result(
            {
                "success": True,
                "work_minutes_reported": state.work_minutes_reported,
                "session_snoozed": state.snoozed,
                "message": "Work minutes recorded for proactive L0 trigger.",
            }
        )
    except Exception as e:
        logger.exception("agent_proactive_report_work failed")
        return _tool_error(str(e))


PROACTIVE_STATUS_SCHEMA: dict[str, Any] = {
    "name": "agent_proactive_status",
    "description": "US-5 proactive engine status, quiet hours policy, optional session snooze state.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Hermes session id to include snooze state."},
        },
    },
}

PROACTIVE_EVALUATE_SCHEMA: dict[str, Any] = {
    "name": "agent_proactive_evaluate",
    "description": (
        "Before speaking proactively, check quiet hours and session snooze. "
        "If allowed, returns proposal text (e.g. work-break reminder). "
        "Do NOT speak proactively when reason_code is quiet_hours or session_snoozed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "work_minutes": {
                "type": "number",
                "description": "User-reported continuous work minutes (>=120 triggers L0).",
            },
            "natural_pause": {"type": "boolean", "default": True},
        },
        "required": ["session_id"],
    },
}

PROACTIVE_FEEDBACK_SCHEMA: dict[str, Any] = {
    "name": "agent_proactive_feedback",
    "description": (
        "When user says do not disturb (别打扰/在做正事), snooze proactive speech for this session "
        "and persist preference via agent_memory (deduped). Use instead of generic memory write."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "User message text."},
            "session_id": {"type": "string"},
            "no_memory": {"type": "boolean", "default": False},
        },
        "required": ["message"],
    },
}

PROACTIVE_REPORT_WORK_SCHEMA: dict[str, Any] = {
    "name": "agent_proactive_report_work",
    "description": "Record work duration when user mentions hours worked (US-5).",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "work_minutes": {"type": "number"},
        },
        "required": ["session_id", "work_minutes"],
    },
}


def register_proactive_hermes_tools(ctx) -> None:
    ctx.register_tool(
        name="agent_proactive_status",
        toolset="agent_proactive",
        schema=PROACTIVE_STATUS_SCHEMA,
        handler=lambda args, **kw: agent_proactive_status(args, **kw),
        check_fn=check_proactive_available,
        emoji="🔔",
    )
    ctx.register_tool(
        name="agent_proactive_evaluate",
        toolset="agent_proactive",
        schema=PROACTIVE_EVALUATE_SCHEMA,
        handler=lambda args, **kw: agent_proactive_evaluate(args, **kw),
        check_fn=check_proactive_available,
        emoji="⏸",
    )
    ctx.register_tool(
        name="agent_proactive_feedback",
        toolset="agent_proactive",
        schema=PROACTIVE_FEEDBACK_SCHEMA,
        handler=lambda args, **kw: agent_proactive_feedback(args, **kw),
        check_fn=check_proactive_available,
        emoji="🤫",
    )
    ctx.register_tool(
        name="agent_proactive_report_work",
        toolset="agent_proactive",
        schema=PROACTIVE_REPORT_WORK_SCHEMA,
        handler=lambda args, **kw: agent_proactive_report_work(args, **kw),
        check_fn=check_proactive_available,
        emoji="⏱",
    )
