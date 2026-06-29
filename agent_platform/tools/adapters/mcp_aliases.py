"""Map facade tool names → official MCP server tool names."""

from __future__ import annotations

# Our stable API → MCP server tool name
FILESYSTEM_ALIASES: dict[str, str | None] = {
    "list_directory": "list_directory",
    "read_file": "read_text_file",
    "write_file": "write_file",
    "delete_file": None,  # not in official server; use mock transport
}

FETCH_ALIASES: dict[str, str | None] = {
    "fetch": "fetch",
}

OBSIDIAN_ALIASES: dict[str, str | None] = {
    "search": "search",
    "append_note": "append_note",
}

SERVER_ALIASES: dict[str, dict[str, str | None]] = {
    "filesystem": FILESYSTEM_ALIASES,
    "fetch": FETCH_ALIASES,
    "obsidian": OBSIDIAN_ALIASES,
}


def resolve_mcp_tool_name(server: str, tool: str) -> str:
    aliases = SERVER_ALIASES.get(server, {})
    mapped = aliases.get(tool, tool)
    if mapped is None:
        raise KeyError(
            f"tool {server}.{tool} has no stdio mapping; use transport: mock or a supported tool"
        )
    return mapped
