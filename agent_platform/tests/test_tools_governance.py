"""M6 — tool level governance."""

from __future__ import annotations

from agent_platform.tools.contracts import ToolLevel
from agent_platform.tools.governance import requires_draft, resolve_tool_level


def test_resolve_levels():
    m = {
        "filesystem.read_file": "L0",
        "filesystem.write_file": "L2",
    }
    assert resolve_tool_level("filesystem", "read_file", {}, level_map=m) == ToolLevel.L0
    assert resolve_tool_level("filesystem", "write_file", {}, level_map=m) == ToolLevel.L2
    assert resolve_tool_level("fetch", "fetch", {}, level_map=m, default_level="L1") == ToolLevel.L1


def test_requires_draft():
    assert requires_draft(ToolLevel.L2, draft_enabled=True)
    assert not requires_draft(ToolLevel.L0, draft_enabled=True)
    assert not requires_draft(ToolLevel.L2, draft_enabled=False)
