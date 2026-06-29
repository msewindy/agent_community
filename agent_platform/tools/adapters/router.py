"""Route tool invocations to mock or stdio MCP adapters (M6 D3)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from agent_platform.tools.adapters.mcp_aliases import resolve_mcp_tool_name
from agent_platform.tools.adapters.mcp_stdio_session import StdioMcpSession, build_stdio_params
from agent_platform.tools.adapters.mock_mcp import MockMcpAdapter

logger = logging.getLogger(__name__)


def mcp_sdk_available() -> bool:
    try:
        import mcp  # noqa: F401

        return True
    except ImportError:
        return False


def stdio_prerequisites_ok(server_cfg: dict) -> tuple[bool, str]:
    cmd = str(server_cfg.get("command", ""))
    if not cmd:
        return False, "missing command"
    if shutil.which(cmd) is None:
        return False, f"command not found: {cmd}"
    return True, ""


class McpRouterAdapter:
    """Per-server transport: mock (in-process) or stdio (subprocess MCP server)."""

    def __init__(self, cfg: dict, sandbox_root: Path) -> None:
        self._cfg = cfg
        self._sandbox = sandbox_root.resolve()
        self._mock = MockMcpAdapter(self._sandbox)
        self._stdio: dict[str, StdioMcpSession] = {}
        servers = cfg.get("servers") or {}

        for name, scfg in servers.items():
            if not (scfg or {}).get("enabled", False):
                continue
            transport = str((scfg or {}).get("transport", "mock")).lower()
            if transport != "stdio":
                continue
            ok, reason = stdio_prerequisites_ok(scfg)
            if not ok:
                logger.warning("MCP server %s stdio skipped: %s", name, reason)
                continue
            if not mcp_sdk_available():
                logger.warning("MCP server %s stdio skipped: mcp package not installed", name)
                continue
            try:
                params = build_stdio_params(
                    scfg,
                    sandbox_root=str(self._sandbox) if name == "filesystem" else None,
                )
                timeout = float(scfg.get("startup_timeout_s", 120))
                self._stdio[name] = StdioMcpSession(name, params, startup_timeout=timeout)
                logger.info("MCP stdio connected: %s", name)
            except Exception as e:
                logger.warning("MCP server %s stdio failed: %s", name, e)

    def close(self) -> None:
        for session in self._stdio.values():
            try:
                session.close()
            except Exception:
                pass
        self._stdio.clear()

    def _server_cfg(self, server: str) -> dict:
        scfg = (self._cfg.get("servers") or {}).get(server)
        if scfg is None:
            return {"enabled": True, "transport": "mock"}
        return scfg

    def _transport(self, server: str) -> str:
        scfg = self._server_cfg(server)
        if not scfg.get("enabled", False):
            raise KeyError(f"server disabled: {server}")
        if server in self._stdio:
            return "stdio"
        return str(scfg.get("transport", "mock")).lower()

    def server_transports(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, scfg in (self._cfg.get("servers") or {}).items():
            if not (scfg or {}).get("enabled", False):
                continue
            try:
                out[name] = self._transport(name)
            except KeyError:
                out[name] = "disabled"
        return out

    def invoke(self, server: str, tool: str, arguments: dict[str, Any]) -> Any:
        transport = self._transport(server)
        if transport == "stdio":
            session = self._stdio.get(server)
            if session is None:
                raise RuntimeError(
                    f"MCP stdio for {server} unavailable; check command/npx/uvx or use transport: mock"
                )
            try:
                mcp_tool = resolve_mcp_tool_name(server, tool)
            except KeyError:
                logger.info("stdio %s.%s unsupported — fallback to mock", server, tool)
                return self._mock.invoke(server, tool, arguments)
            args = dict(arguments)
            if server == "filesystem" and "path" in args:
                p = Path(str(args["path"]))
                if not p.is_absolute():
                    args["path"] = str((self._sandbox / p).resolve())
            return session.call_tool(mcp_tool, args)
        return self._mock.invoke(server, tool, arguments)

    def list_tools(self) -> list[dict[str, str]]:
        tools = list(self._mock.list_tools())
        for name, session in self._stdio.items():
            try:
                for tname in session.list_tool_names():
                    tools.append(
                        {
                            "server": name,
                            "tool": tname,
                            "description": f"stdio:{tname}",
                            "transport": "stdio",
                        }
                    )
            except Exception:
                pass
        return tools
