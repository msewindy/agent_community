"""Hermes tools — calibration + behavior profile (M7)."""

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


def _get_calibration_service():
    bootstrap_agent_platform()
    from agent_platform.calibration.service import CalibrationService

    return CalibrationService()


def _get_behavior_service():
    bootstrap_agent_platform()
    from agent_platform.behavior.service import BehaviorService

    return BehaviorService()


def check_m7_available() -> bool:
    try:
        bootstrap_agent_platform()
        from agent_platform.calibration.service import CalibrationService
        from agent_platform.behavior.service import BehaviorService

        CalibrationService()
        BehaviorService()
        return True
    except Exception as e:
        logger.debug("m7 not available: %s", e)
        return False


def agent_calibrate_output(args: dict, **kwargs) -> str:
    try:
        from agent_platform.calibration.contracts import CalibrateRequest

        text = (args.get("text") or "").strip()
        if not text:
            return _tool_error("Missing required parameter: text")

        req = CalibrateRequest(
            text=text,
            confidence=args.get("confidence"),
            has_tool_source=bool(args.get("has_tool_source")),
            memory_backed=bool(args.get("memory_backed")),
            trace_id=args.get("trace_id") or _session_trace_id(kwargs),
        )
        svc = _get_calibration_service()
        result = svc.calibrate(req)
        return _tool_result(
            {
                "success": True,
                "text": result.text,
                "confidence_level": result.confidence_level.value,
                "confidence_score": result.confidence_score,
                "rewritten": result.rewritten,
                "flags": result.flags,
            }
        )
    except Exception as e:
        logger.exception("agent_calibrate_output failed")
        return _tool_error(str(e))


def agent_handle_correction(args: dict, **kwargs) -> str:
    try:
        from agent_platform.calibration.contracts import UserCorrectionRequest

        rid = (args.get("record_id") or "").strip()
        old_v = (args.get("old_value") or "").strip()
        new_v = (args.get("new_value") or "").strip()
        if not rid or not old_v or not new_v:
            return _tool_error("Missing record_id, old_value, or new_value")

        req = UserCorrectionRequest(
            record_id=rid,
            old_value=old_v,
            new_value=new_v,
            reason=args.get("reason") or "user_correction",
            trace_id=args.get("trace_id") or _session_trace_id(kwargs),
            device_id=args.get("device_id"),
        )
        svc = _get_calibration_service()
        result = svc.correct(req)
        try:
            from agent_platform.evolution.bridge import bridge_enabled, forward_m7_correction

            if bridge_enabled():
                forward_m7_correction(req, result)
        except Exception:
            pass
        return _tool_result(
            {
                "success": result.success,
                "apology_text": result.apology_text,
                "old_record_id": result.old_record_id,
                "new_record_id": result.new_record_id,
                "trace_id": result.trace_id,
            }
        )
    except Exception as e:
        logger.exception("agent_handle_correction failed")
        return _tool_error(str(e))


def agent_behavior_status(args: dict, **kwargs) -> str:
    try:
        svc = _get_behavior_service()
        profile = svc.get_profile()
        return _tool_result(
            {
                "success": True,
                "enabled": svc.enabled,
                "tone": profile.tone.value,
                "verbosity": profile.verbosity.value,
                "language": profile.language,
                "rules": profile.rules,
                "panel_url": svc.panel_url(),
            }
        )
    except Exception as e:
        logger.exception("agent_behavior_status failed")
        return _tool_error(str(e))


def agent_behavior_get_prompt(args: dict, **kwargs) -> str:
    try:
        svc = _get_behavior_service()
        block = svc.system_prompt_block()
        return _tool_result({"success": True, "system_prompt": block, "panel_url": svc.panel_url()})
    except Exception as e:
        logger.exception("agent_behavior_get_prompt failed")
        return _tool_error(str(e))


def agent_behavior_update(args: dict, **kwargs) -> str:
    try:
        from agent_platform.behavior.contracts import BehaviorProfileUpdate, Tone, Verbosity

        patch_kw: dict[str, Any] = {}
        if args.get("tone"):
            patch_kw["tone"] = Tone(args["tone"])
        if args.get("verbosity"):
            patch_kw["verbosity"] = Verbosity(args["verbosity"])
        if args.get("language"):
            patch_kw["language"] = args["language"]
        if args.get("rules") is not None:
            rules = args["rules"]
            if isinstance(rules, str):
                rules = [r.strip() for r in rules.split("\n") if r.strip()]
            patch_kw["rules"] = rules
        if args.get("custom_notes") is not None:
            patch_kw["custom_notes"] = args["custom_notes"]
        if args.get("preference_text"):
            svc = _get_behavior_service()
            profile = svc.apply_preference_hint(str(args["preference_text"]))
            return _tool_result(
                {
                    "success": True,
                    "tone": profile.tone.value,
                    "verbosity": profile.verbosity.value,
                    "rules": profile.rules,
                    "panel_url": svc.panel_url(),
                }
            )

        if not patch_kw:
            return _tool_error("No fields to update")

        svc = _get_behavior_service()
        profile = svc.update_profile(BehaviorProfileUpdate(**patch_kw))
        return _tool_result(
            {
                "success": True,
                "tone": profile.tone.value,
                "verbosity": profile.verbosity.value,
                "rules": profile.rules,
                "panel_url": svc.panel_url(),
            }
        )
    except Exception as e:
        logger.exception("agent_behavior_update failed")
        return _tool_error(str(e))


def agent_behavior_check_drift(args: dict, **kwargs) -> str:
    try:
        text = (args.get("text") or "").strip()
        if not text:
            return _tool_error("Missing required parameter: text")
        svc = _get_behavior_service()
        report = svc.check_drift(text)
        return _tool_result({"success": True, **report.model_dump()})
    except Exception as e:
        logger.exception("agent_behavior_check_drift failed")
        return _tool_error(str(e))


CALIBRATE_SCHEMA: dict[str, Any] = {
    "name": "agent_calibrate_output",
    "description": "Post-process assistant text: expose low confidence, hedge unsourced claims (US-6).",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "confidence": {"type": "number"},
            "has_tool_source": {"type": "boolean", "default": False},
            "memory_backed": {"type": "boolean", "default": False},
            "trace_id": {"type": "string"},
        },
        "required": ["text"],
    },
}

CORRECTION_SCHEMA: dict[str, Any] = {
    "name": "agent_handle_correction",
    "description": "User correction → apology + supersede memory (US-6).",
    "parameters": {
        "type": "object",
        "properties": {
            "record_id": {"type": "string"},
            "old_value": {"type": "string"},
            "new_value": {"type": "string"},
            "reason": {"type": "string"},
            "device_id": {"type": "string"},
            "trace_id": {"type": "string"},
        },
        "required": ["record_id", "old_value", "new_value"],
    },
}

BEHAVIOR_STATUS_SCHEMA: dict[str, Any] = {
    "name": "agent_behavior_status",
    "description": "Get behavior profile + settings panel URL (US-3).",
    "parameters": {"type": "object", "properties": {}},
}

BEHAVIOR_PROMPT_SCHEMA: dict[str, Any] = {
    "name": "agent_behavior_get_prompt",
    "description": "System prompt block for 它的设定 injection.",
    "parameters": {"type": "object", "properties": {}},
}

BEHAVIOR_UPDATE_SCHEMA: dict[str, Any] = {
    "name": "agent_behavior_update",
    "description": "Update behavior profile or apply preference hint.",
    "parameters": {
        "type": "object",
        "properties": {
            "tone": {"type": "string", "enum": ["direct", "neutral", "warm"]},
            "verbosity": {"type": "string", "enum": ["short", "medium", "long"]},
            "language": {"type": "string"},
            "rules": {"type": "array", "items": {"type": "string"}},
            "custom_notes": {"type": "string"},
            "preference_text": {"type": "string"},
        },
    },
}

BEHAVIOR_DRIFT_SCHEMA: dict[str, Any] = {
    "name": "agent_behavior_check_drift",
    "description": "Detect persona drift vs behavior profile.",
    "parameters": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}


def register_m7_hermes_tools(ctx) -> None:
    ctx.register_tool(
        name="agent_calibrate_output",
        toolset="agent_calibration",
        schema=CALIBRATE_SCHEMA,
        handler=lambda args, **kw: agent_calibrate_output(args, **kw),
        check_fn=check_m7_available,
        emoji="🎯",
    )
    ctx.register_tool(
        name="agent_handle_correction",
        toolset="agent_calibration",
        schema=CORRECTION_SCHEMA,
        handler=lambda args, **kw: agent_handle_correction(args, **kw),
        check_fn=check_m7_available,
        emoji="🙏",
    )
    ctx.register_tool(
        name="agent_behavior_status",
        toolset="agent_behavior",
        schema=BEHAVIOR_STATUS_SCHEMA,
        handler=lambda args, **kw: agent_behavior_status(args, **kw),
        check_fn=check_m7_available,
        emoji="📋",
    )
    ctx.register_tool(
        name="agent_behavior_get_prompt",
        toolset="agent_behavior",
        schema=BEHAVIOR_PROMPT_SCHEMA,
        handler=lambda args, **kw: agent_behavior_get_prompt(args, **kw),
        check_fn=check_m7_available,
        emoji="📜",
    )
    ctx.register_tool(
        name="agent_behavior_update",
        toolset="agent_behavior",
        schema=BEHAVIOR_UPDATE_SCHEMA,
        handler=lambda args, **kw: agent_behavior_update(args, **kw),
        check_fn=check_m7_available,
        emoji="✏️",
    )
    ctx.register_tool(
        name="agent_behavior_check_drift",
        toolset="agent_behavior",
        schema=BEHAVIOR_DRIFT_SCHEMA,
        handler=lambda args, **kw: agent_behavior_check_drift(args, **kw),
        check_fn=check_m7_available,
        emoji="📐",
    )
