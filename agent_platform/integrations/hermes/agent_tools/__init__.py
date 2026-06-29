"""Hermes plugin: agent-tools — MCP + L0–L2 draft gate (M6 D2)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    from agent_platform.integrations.hermes.tools_mcp import register_tools_hermes_tools

    register_tools_hermes_tools(ctx)
    logger.info(
        "agent-tools plugin: agent_tool_status, invoke, list_drafts, approve_draft, reject_draft"
    )
