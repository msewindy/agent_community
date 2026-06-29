"""Hermes tools — tool_service / MCP + L0–L2 draft gate (M6 D2)."""

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


def _session_id(args: dict, kwargs: dict) -> Optional[str]:
    return args.get("session_id") or kwargs.get("current_session_id")


def _session_trace_id(kwargs: dict) -> Optional[str]:
    sid = kwargs.get("current_session_id") or kwargs.get("session_id")
    if not sid:
        return None
    return f"hermes-{sid}"


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        return json.loads(text)
    return _tool_error("arguments must be object or JSON string")  # type: ignore[return-value]


def _get_tool_service():
    bootstrap_agent_platform()
    from agent_platform.tools.service import ToolService

    return ToolService()


def check_tools_available() -> bool:
    try:
        bootstrap_agent_platform()
        from agent_platform.tools.service import ToolService

        ToolService()
        return True
    except Exception as e:
        logger.debug("tools not available: %s", e)
        return False


def _result_payload(result) -> dict[str, Any]:
    level = result.level.value if hasattr(result.level, "value") else result.level
    status = result.status.value if hasattr(result.status, "value") else result.status
    return {
        "success": status != "error",
        "status": status,
        "level": level,
        "server": result.server,
        "tool": result.tool,
        "output": result.output,
        "draft_id": result.draft_id,
        "message": result.message,
        "trace_id": result.trace_id,
    }


def agent_tool_status(args: dict, **kwargs) -> str:
    try:
        svc = _get_tool_service()
        st = svc.status()
        sid = _session_id(args, kwargs)
        if sid:
            pending = svc.list_pending_drafts(str(sid))
            st["session_pending_drafts"] = len(pending)
        return _tool_result({"success": True, **st})
    except Exception as e:
        logger.exception("agent_tool_status failed")
        return _tool_error(str(e))


def agent_tool_invoke(args: dict, **kwargs) -> str:
    """Invoke MCP tool via governance; L2 returns draft_id for approval."""
    server = (args.get("server") or "").strip()
    tool = (args.get("tool") or "").strip()
    if not server or not tool:
        return _tool_error("Missing required: server, tool")

    try:
        from agent_platform.tools.contracts import ToolInvokeRequest

        sid = _session_id(args, kwargs)
        if not sid:
            return _tool_error("Missing session_id (or Hermes current_session_id)")

        arguments = _parse_arguments(args.get("arguments"))
        if isinstance(arguments, str):
            return arguments

        req_kw: dict[str, Any] = {
            "server": server,
            "tool": tool,
            "arguments": arguments,
            "session_id": str(sid),
        }
        tid = args.get("trace_id") or _session_trace_id(kwargs)
        if tid:
            req_kw["trace_id"] = tid
        if args.get("draft_id"):
            req_kw["draft_id"] = str(args["draft_id"])

        svc = _get_tool_service()
        result = svc.invoke(ToolInvokeRequest(**req_kw))
        payload = _result_payload(result)
        if result.status.value == "draft_pending":
            panel_port = 8766
            try:
                from agent_platform.tools._config import load_mcp_config

                panel_port = int((load_mcp_config().get("panel") or {}).get("port", 8766))
            except Exception:
                pass
            payload["hint"] = (
                "L2 action blocked — show preview to user, open draft panel "
                f"http://127.0.0.1:{panel_port}/ for approve/reject, or call "
                "agent_tool_approve_draft after explicit confirmation."
            )
            payload["panel_url"] = f"http://127.0.0.1:{panel_port}/"
        return _tool_result(payload)
    except json.JSONDecodeError as e:
        return _tool_error(f"Invalid arguments JSON: {e}")
    except Exception as e:
        logger.exception("agent_tool_invoke failed")
        return _tool_error(str(e))


def agent_tool_list_drafts(args: dict, **kwargs) -> str:
    try:
        svc = _get_tool_service()
        sid = _session_id(args, kwargs)
        pending = svc.list_pending_drafts(str(sid) if sid else None)
        drafts = [
            {
                "draft_id": d.draft_id,
                "server": d.server,
                "tool": d.tool,
                "preview": d.preview,
                "level": d.level.value if hasattr(d.level, "value") else d.level,
                "created_at": d.created_at.isoformat(),
            }
            for d in pending
        ]
        return _tool_result({"success": True, "drafts": drafts, "count": len(drafts)})
    except Exception as e:
        logger.exception("agent_tool_list_drafts failed")
        return _tool_error(str(e))


def agent_tool_approve_draft(args: dict, **kwargs) -> str:
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _tool_error("Missing required: draft_id")

    try:
        from agent_platform.tools.contracts import DraftApproveRequest

        sid = _session_id(args, kwargs)
        req_kw: dict[str, Any] = {"draft_id": draft_id}
        if sid:
            req_kw["session_id"] = str(sid)
        tid = args.get("trace_id") or _session_trace_id(kwargs)
        if tid:
            req_kw["trace_id"] = tid

        svc = _get_tool_service()
        result = svc.approve_draft(DraftApproveRequest(**req_kw))
        return _tool_result(_result_payload(result))
    except (KeyError, PermissionError, ValueError) as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("agent_tool_approve_draft failed")
        return _tool_error(str(e))


def agent_tool_reject_draft(args: dict, **kwargs) -> str:
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _tool_error("Missing required: draft_id")

    try:
        from agent_platform.tools.contracts import DraftRejectRequest

        svc = _get_tool_service()
        rec = svc.reject_draft(
            DraftRejectRequest(draft_id=draft_id, reason=str(args.get("reason", "")))
        )
        return _tool_result(
            {
                "success": True,
                "draft_id": rec.draft_id,
                "status": rec.status.value if hasattr(rec.status, "value") else rec.status,
            }
        )
    except KeyError as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("agent_tool_reject_draft failed")
        return _tool_error(str(e))


TOOL_STATUS_SCHEMA: dict[str, Any] = {
    "name": "agent_tool_status",
    "description": (
        "MCP tool gateway status: sandbox root, enabled servers, tool catalog, "
        "optional pending draft count for session."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Hermes session id."},
        },
    },
}

TOOL_INVOKE_SCHEMA: dict[str, Any] = {
    "name": "agent_tool_invoke",
    "description": (
        "Invoke filesystem/fetch/obsidian MCP tool through L0–L2 governance. "
        "L0/L1 execute immediately. L2 (write/delete/append) returns draft_pending + draft_id — "
        "must call agent_tool_approve_draft after user confirms."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "server": {
                "type": "string",
                "enum": ["filesystem", "fetch", "obsidian"],
                "description": "MCP server name.",
            },
            "tool": {
                "type": "string",
                "description": "Tool name, e.g. read_file, write_file, fetch, search.",
            },
            "arguments": {
                "type": "object",
                "description": "Tool arguments object (or JSON string).",
            },
            "session_id": {"type": "string"},
            "draft_id": {
                "type": "string",
                "description": "Execute previously approved draft (internal).",
            },
        },
        "required": ["server", "tool"],
    },
}

TOOL_LIST_DRAFTS_SCHEMA: dict[str, Any] = {
    "name": "agent_tool_list_drafts",
    "description": "List pending L2 tool drafts awaiting user confirmation.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
        },
    },
}

TOOL_APPROVE_DRAFT_SCHEMA: dict[str, Any] = {
    "name": "agent_tool_approve_draft",
    "description": (
        "After user explicitly confirms an L2 action, approve draft and execute the tool. "
        "Use only when user said yes/确认/好的 to the preview."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "draft_id": {"type": "string"},
            "session_id": {"type": "string"},
        },
        "required": ["draft_id"],
    },
}

TOOL_REJECT_DRAFT_SCHEMA: dict[str, Any] = {
    "name": "agent_tool_reject_draft",
    "description": "Reject/cancel a pending L2 tool draft.",
    "parameters": {
        "type": "object",
        "properties": {
            "draft_id": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["draft_id"],
    },
}


def register_tools_hermes_tools(ctx) -> None:
    ctx.register_tool(
        name="agent_tool_status",
        toolset="agent_tools",
        schema=TOOL_STATUS_SCHEMA,
        handler=lambda args, **kw: agent_tool_status(args, **kw),
        check_fn=check_tools_available,
        emoji="🧰",
    )
    ctx.register_tool(
        name="agent_tool_invoke",
        toolset="agent_tools",
        schema=TOOL_INVOKE_SCHEMA,
        handler=lambda args, **kw: agent_tool_invoke(args, **kw),
        check_fn=check_tools_available,
        emoji="🔧",
    )
    ctx.register_tool(
        name="agent_tool_list_drafts",
        toolset="agent_tools",
        schema=TOOL_LIST_DRAFTS_SCHEMA,
        handler=lambda args, **kw: agent_tool_list_drafts(args, **kw),
        check_fn=check_tools_available,
        emoji="📋",
    )
    ctx.register_tool(
        name="agent_tool_approve_draft",
        toolset="agent_tools",
        schema=TOOL_APPROVE_DRAFT_SCHEMA,
        handler=lambda args, **kw: agent_tool_approve_draft(args, **kw),
        check_fn=check_tools_available,
        emoji="✅",
    )
    ctx.register_tool(
        name="agent_tool_reject_draft",
        toolset="agent_tools",
        schema=TOOL_REJECT_DRAFT_SCHEMA,
        handler=lambda args, **kw: agent_tool_reject_draft(args, **kw),
        check_fn=check_tools_available,
        emoji="🚫",
    )
