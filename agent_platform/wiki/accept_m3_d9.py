#!/usr/bin/env python3
"""M3 D9 — accept M2+M3 combined recall demo."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from agent_platform.integrations.demo_recall_m2_m3 import run_demo
from agent_platform.integrations.hermes.recall_tools import agent_combined_recall
from agent_platform.integrations.hermes.tools import bootstrap_agent_platform
from agent_platform.integrations.recall import combined_recall
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService
from agent_platform.wiki.contracts import WikiIngestRequest
from agent_platform.wiki.service import WikiService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def accept_combined_api(root: Path) -> bool:
    mem_cfg = {
        "backend": "mock",
        "device": {"default_id": "d9-device"},
        "gate": {"enabled": False},
        "audit": {"enabled": False},
    }
    wiki_cfg = {"store": {"root": str(root), "auto_init": True}}
    mem = MemoryService(config=mem_cfg)
    wiki = WikiService(config=wiki_cfg, store_root=root)

    mem.write("偏好简短", category=MemoryCategory.preference)
    (root / "raw" / "articles" / "topic.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "raw" / "articles" / "topic.md").write_text(
        "# Reachy\n\nReachy Mini robot desktop companion.\n", encoding="utf-8"
    )
    wiki.ingest(WikiIngestRequest(source_path="raw/articles/topic.md", topic="Reachy"))

    r = combined_recall(
        "Reachy 机器人 简短 偏好",
        memory_service=mem,
        wiki_service=wiki,
    )
    if not r.memory_items or not r.wiki_items:
        _fail(f"combined_recall counts mem={len(r.memory_items)} wiki={len(r.wiki_items)}")
        return False
    if "记忆层" not in r.prompt_context or "Wiki" not in r.prompt_context:
        _fail("prompt_context missing section headers")
        return False
    _ok("combined_recall API (memory + wiki + prompt_context)")
    return True


def accept_hermes_tool(root: Path) -> bool:
    bootstrap_agent_platform()
    mem_cfg = {
        "backend": "mock",
        "device": {"default_id": "d9-hermes"},
        "gate": {"enabled": False},
        "audit": {"enabled": False},
    }
    wiki_cfg = {"store": {"root": str(root), "auto_init": True}}
    mem = MemoryService(config=mem_cfg)
    wiki = WikiService(config=wiki_cfg, store_root=root)
    mem.write("Hermes路径：用户偏好回复简短", category=MemoryCategory.preference)
    (root / "raw" / "articles" / "h.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "raw" / "articles" / "h.md").write_text("# Wiki\n\nCombined recall hermes.\n", encoding="utf-8")
    wiki.ingest(WikiIngestRequest(source_path="raw/articles/h.md", topic="Wiki"))

    import agent_platform.integrations.hermes.tools as mt
    import agent_platform.integrations.hermes.wiki_tools as wt

    mt._get_service = lambda: mem  # type: ignore[attr-defined]
    wt._get_wiki_service = lambda: wiki  # type: ignore[attr-defined]

    out = json.loads(
        agent_combined_recall(
            {"query": "Reachy 简短 偏好"},
            current_session_id="d9-recall",
        )
    )
    if not out.get("success") or not out.get("memory_count") or not out.get("wiki_count"):
        _fail(f"agent_combined_recall: {out}")
        return False
    if "prompt_context" not in out:
        _fail("agent_combined_recall missing prompt_context")
        return False
    _ok("agent_combined_recall Hermes tool")
    return True


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory(prefix="m3_d9_") as td:
        root = Path(td) / "store"
        if run_demo(root) != 0:
            ok = False
        if not accept_combined_api(root):
            ok = False
        if not accept_hermes_tool(root):
            ok = False

    print()
    if ok:
        print("accept_m3_d9: PASS — M2+M3 combined recall OK")
        return 0
    print("accept_m3_d9: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
