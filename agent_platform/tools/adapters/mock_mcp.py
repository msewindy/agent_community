"""Mock MCP servers — filesystem / fetch / obsidian (M6 D1, CI-friendly)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_MOCK_FETCH: dict[str, str] = {
    "https://example.com": "<html><title>Example</title><body>Example Domain</body></html>",
    "https://modelcontextprotocol.io": "<html><title>MCP</title><body>Model Context Protocol</body></html>",
}


class MockMcpAdapter:
    """In-process stand-in for MCP filesystem + fetch + obsidian tools."""

    def __init__(self, sandbox_root: Path) -> None:
        self._sandbox = sandbox_root.resolve()

    def _safe_path(self, raw: str) -> Path:
        rel = (raw or ".").lstrip("/")
        target = (self._sandbox / rel).resolve()
        if not str(target).startswith(str(self._sandbox)):
            raise PermissionError(f"path outside sandbox: {raw}")
        return target

    def invoke(self, server: str, tool: str, arguments: dict[str, Any]) -> Any:
        key = f"{server}.{tool}"
        if key == "filesystem.list_directory":
            p = self._safe_path(str(arguments.get("path", ".")))
            if not p.is_dir():
                raise FileNotFoundError(str(p))
            names = sorted(x.name for x in p.iterdir())
            return {"entries": names, "path": str(p.relative_to(self._sandbox))}

        if key == "filesystem.read_file":
            p = self._safe_path(str(arguments["path"]))
            if not p.is_file():
                raise FileNotFoundError(str(p))
            return {"content": p.read_text(encoding="utf-8"), "path": arguments["path"]}

        if key == "filesystem.write_file":
            p = self._safe_path(str(arguments["path"]))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(arguments.get("content", "")), encoding="utf-8")
            return {"written": True, "path": arguments["path"], "bytes": len(str(arguments.get("content", "")))}

        if key == "filesystem.delete_file":
            p = self._safe_path(str(arguments["path"]))
            if p.is_file():
                p.unlink()
            return {"deleted": True, "path": arguments["path"]}

        if key == "fetch.fetch":
            url = str(arguments.get("url", ""))
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError("only http(s) URLs supported in mock fetch")
            body = _MOCK_FETCH.get(url)
            if body is None:
                body = f"<html><title>Mock</title><body>mock fetch for {url}</body></html>"
            return {"url": url, "content": body, "content_type": "text/html"}

        if key == "obsidian.search":
            q = str(arguments.get("query", ""))
            return {
                "hits": [
                    {"path": "notes/demo.md", "snippet": f"mock hit for {q[:80]}"},
                ]
            }

        if key == "obsidian.append_note":
            note = self._sandbox / "obsidian" / str(arguments.get("path", "note.md")).lstrip("/")
            note.parent.mkdir(parents=True, exist_ok=True)
            existing = note.read_text(encoding="utf-8") if note.is_file() else ""
            note.write_text(existing + str(arguments.get("content", "")), encoding="utf-8")
            return {"appended": True, "path": str(note.relative_to(self._sandbox))}

        raise KeyError(f"unknown mock tool: {key}")

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"server": "filesystem", "tool": "list_directory", "description": "List sandbox directory"},
            {"server": "filesystem", "tool": "read_file", "description": "Read file in sandbox"},
            {"server": "filesystem", "tool": "write_file", "description": "Write file in sandbox (L2)"},
            {"server": "filesystem", "tool": "delete_file", "description": "Delete file in sandbox (L2)"},
            {"server": "fetch", "tool": "fetch", "description": "HTTP GET (mock)"},
            {"server": "obsidian", "tool": "search", "description": "Search vault (mock)"},
            {"server": "obsidian", "tool": "append_note", "description": "Append note (L2 mock)"},
        ]
