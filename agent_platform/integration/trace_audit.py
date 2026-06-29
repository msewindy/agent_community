"""M8 — trace_id audit chain across memory + tools (engineering §14)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService
from agent_platform.memory.trace import new_trace_id
from agent_platform.tools.contracts import ToolInvokeRequest, ToolInvokeStatus
from agent_platform.tools.service import ToolService


def accept_trace_chain() -> bool:
    """Single trace_id spans memory write/search + L2 draft gate event."""
    td = tempfile.mkdtemp(prefix="m8_trace_")
    root = Path(td)
    sandbox = root / "sandbox"
    sandbox.mkdir()
    tid = new_trace_id()

    mem_cfg = {
        "backend": "mock",
        "gate": {"enabled": False},
        "audit": {"enabled": True, "db_path": str(root / "mem_audit.db")},
        "mock": {"persist_path": str(root / "mem.json")},
    }
    mem = MemoryService(config=mem_cfg)
    mem.write("trace-chain marker", category=MemoryCategory.preference, trace_id=tid)
    mem.search("marker", trace_id=tid)
    mem_events = mem.audit_trace(tid)
    mem_types = {e.get("event_type") for e in mem_events}
    if "write" not in mem_types or "search" not in mem_types:
        return False

    tools_cfg = {
        "enabled": True,
        "sandbox": {"root": str(sandbox), "auto_init": False},
        "governance": {
            "default_level": "L1",
            "tool_levels": {"filesystem.write_file": "L2"},
        },
        "draft_gate": {"enabled": True},
        "store": {"root": str(root / "tools_store")},
        "servers": {"filesystem": {"enabled": True, "transport": "mock"}},
    }
    tools = ToolService(config=tools_cfg, store_root=root / "tools_store", sandbox_root=sandbox)
    try:
        res = tools.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": "trace.md", "content": "x"},
                session_id="m8-trace",
                trace_id=tid,
            )
        )
        if res.status != ToolInvokeStatus.draft_pending:
            return False
        log_path = root / "tools_store" / "events.log.md"
        if not log_path.is_file():
            return False
        if tid not in log_path.read_text(encoding="utf-8"):
            return False
    finally:
        tools.close()

    return True
