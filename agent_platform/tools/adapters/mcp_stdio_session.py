"""Persistent MCP stdio client session (one subprocess per server)."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent_platform.tools.adapters.mcp_result import parse_call_tool_result

logger = logging.getLogger(__name__)


class StdioMcpSession:
    """Run MCP server subprocess in a background thread; sync call_tool from any thread."""

    def __init__(self, server_name: str, params: StdioServerParameters, *, startup_timeout: float = 120.0):
        self.server_name = server_name
        self._params = params
        self._startup_timeout = startup_timeout
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._error: Optional[BaseException] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._session: Optional[ClientSession] = None
        self._thread = threading.Thread(target=self._thread_main, name=f"mcp-{server_name}", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=self._startup_timeout):
            self.close()
            raise TimeoutError(f"MCP server {server_name} failed to start within {self._startup_timeout}s")

    def _thread_main(self) -> None:
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._async_main())
        except BaseException as e:
            self._error = e
            self._ready.set()
            logger.exception("MCP stdio session %s crashed", self.server_name)

    async def _async_main(self) -> None:
        async with stdio_client(self._params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                self._ready.set()
                await asyncio.to_thread(self._stop.wait)

    def call_tool(self, tool: str, arguments: dict[str, Any], *, timeout: float = 120.0) -> Any:
        if self._error is not None:
            raise RuntimeError(f"MCP {self.server_name} not running: {self._error}") from self._error
        if self._session is None or self._loop is None:
            raise RuntimeError(f"MCP {self.server_name} session not ready")

        async def _call():
            assert self._session is not None
            return await self._session.call_tool(tool, arguments)

        fut = asyncio.run_coroutine_threadsafe(_call(), self._loop)
        result = fut.result(timeout=timeout)
        return parse_call_tool_result(result)

    def list_tool_names(self, *, timeout: float = 30.0) -> list[str]:
        if self._session is None or self._loop is None:
            return []

        async def _list():
            assert self._session is not None
            res = await self._session.list_tools()
            return [t.name for t in res.tools]

        fut = asyncio.run_coroutine_threadsafe(_list(), self._loop)
        return fut.result(timeout=timeout)

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)


def build_stdio_params(server_cfg: dict, *, sandbox_root: str | None = None) -> StdioServerParameters:
    command = str(server_cfg.get("command", "npx"))
    args = [str(a) for a in (server_cfg.get("args") or [])]
    resolved: list[str] = []
    for arg in args:
        if "{sandbox_root}" in arg:
            if not sandbox_root:
                raise ValueError("sandbox_root required for this MCP server args template")
            resolved.append(arg.replace("{sandbox_root}", sandbox_root))
        else:
            resolved.append(arg)
    env = server_cfg.get("env")
    return StdioServerParameters(command=command, args=resolved, env=env)
