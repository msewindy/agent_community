"""L0–L2 tool risk classification (M6)."""

from __future__ import annotations

from typing import Any

from agent_platform.tools.contracts import ToolLevel


def tool_key(server: str, tool: str) -> str:
    return f"{server}.{tool}"


def resolve_tool_level(
    server: str,
    tool: str,
    arguments: dict[str, Any] | None,
    *,
    level_map: dict[str, str],
    default_level: str = "L1",
) -> ToolLevel:
    """Map server+tool to L0/L1/L2; arguments reserved for future heuristics."""
    _ = arguments
    raw = level_map.get(tool_key(server, tool))
    if raw is None:
        raw = default_level
    try:
        return ToolLevel(raw.upper())
    except ValueError:
        return ToolLevel.L1


def requires_draft(level: ToolLevel, *, draft_enabled: bool) -> bool:
    return draft_enabled and level == ToolLevel.L2
