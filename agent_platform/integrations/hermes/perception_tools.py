"""Hermes tools — perception_service describe (M4 D3 / US-2)."""

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


def _get_perception_service():
    bootstrap_agent_platform()
    from agent_platform.perception.service import PerceptionService

    return PerceptionService()


def check_perception_available() -> bool:
    try:
        bootstrap_agent_platform()
        from agent_platform.perception.service import PerceptionService

        PerceptionService()
        return True
    except Exception as e:
        logger.debug("perception not available: %s", e)
        return False


def agent_perception_describe(args: dict, **kwargs) -> str:
    question = (args.get("question") or "").strip()
    if not question:
        return _tool_error("Missing required parameter: question")

    try:
        from agent_platform.perception.contracts import DescribeRequest

        svc = _get_perception_service()
        if args.get("enable_camera"):
            svc.set_policy(camera_enabled=True)

        req_kw: dict[str, Any] = {
            "question": question,
            "scene": args.get("scene") or "desk",
            "force": bool(args.get("force", False)),
        }
        tid = args.get("trace_id")
        if not tid:
            sid = kwargs.get("current_session_id") or kwargs.get("session_id")
            if sid:
                tid = f"hermes-{sid}"
        if tid:
            req_kw["trace_id"] = tid
        sid = kwargs.get("current_session_id") or kwargs.get("session_id")
        if sid:
            req_kw["session_id"] = str(sid)
        if args.get("frame_path"):
            req_kw["frame_path"] = args["frame_path"]

        result = svc.describe(DescribeRequest(**req_kw))
        if not result.allowed:
            return _tool_result(
                {
                    "success": False,
                    "reason_code": result.reason_code,
                    "message": result.message,
                    "camera_enabled": svc.policy.camera_enabled,
                }
            )
        return _tool_result(
            {
                "success": True,
                "description": result.description,
                "frame_path": result.frame_path,
                "model": result.model,
                "latency_ms": result.latency_ms,
                "trace_id": result.event.trace_id if result.event else None,
                "message": "Reachy capture + VLM describe (on-demand).",
            }
        )
    except Exception as e:
        logger.exception("agent_perception_describe failed")
        return _tool_error(f"Describe failed: {e}")


def agent_perception_policy(args: dict, **kwargs) -> str:
    try:
        svc = _get_perception_service()
        cam = args.get("camera")
        if cam is not None:
            svc.set_policy(camera_enabled=str(cam).lower() in ("on", "true", "1", "yes"))
        pol = svc.policy
        st = svc.status()
        return _tool_result(
            {
                "success": True,
                "camera_enabled": pol.camera_enabled,
                "microphone_enabled": pol.microphone_enabled,
                "vision_enabled": svc.vision_enabled(),
                "backend": st.backend.value,
                "reachable": st.reachable,
            }
        )
    except Exception as e:
        logger.exception("agent_perception_policy failed")
        return _tool_error(str(e))


PERCEPTION_DESCRIBE_SCHEMA: dict[str, Any] = {
    "name": "agent_perception_describe",
    "description": (
        "US-2 co-presence vision: capture one frame from Reachy (if camera on) and "
        "describe with on-demand VLM (Qwen2-VL). NOT always-on. "
        "If camera is off, returns camera_disabled — tell the user to enable camera. "
        "Use when user asks what is on the desk, book title, etc."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "User vision question in Chinese or English."},
            "scene": {"type": "string", "default": "desk"},
            "enable_camera": {
                "type": "boolean",
                "default": False,
                "description": "Set true to turn camera on for this call.",
            },
            "force": {"type": "boolean", "default": False},
            "frame_path": {
                "type": "string",
                "description": "Reuse existing captures/*.jpg instead of new capture.",
            },
        },
        "required": ["question"],
    },
}

PERCEPTION_POLICY_SCHEMA: dict[str, Any] = {
    "name": "agent_perception_policy",
    "description": "Read or set Reachy camera/microphone policy switches (US-2).",
    "parameters": {
        "type": "object",
        "properties": {
            "camera": {
                "type": "string",
                "enum": ["on", "off"],
                "description": "If set, update camera switch.",
            },
        },
    },
}


def register_perception_hermes_tools(ctx) -> None:
    ctx.register_tool(
        name="agent_perception_describe",
        toolset="agent_perception",
        schema=PERCEPTION_DESCRIBE_SCHEMA,
        handler=lambda args, **kw: agent_perception_describe(args, **kw),
        check_fn=check_perception_available,
        emoji="👁",
    )
    ctx.register_tool(
        name="agent_perception_policy",
        toolset="agent_perception",
        schema=PERCEPTION_POLICY_SCHEMA,
        handler=lambda args, **kw: agent_perception_policy(args, **kw),
        check_fn=check_perception_available,
        emoji="📷",
    )
