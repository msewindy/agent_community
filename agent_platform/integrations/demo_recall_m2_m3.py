#!/usr/bin/env python3
"""M3 D9 — demo M2 memory + M3 wiki combined recall."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from agent_platform.integrations.recall import combined_recall
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService
from agent_platform.wiki.contracts import WikiIngestRequest
from agent_platform.wiki.service import WikiService


def _seed(root: Path) -> tuple[MemoryService, WikiService]:
    mem_cfg = {
        "backend": "mock",
        "device": {"default_id": "demo-recall"},
        "gate": {"enabled": False},
        "audit": {"enabled": False},
    }
    wiki_cfg = {
        "store": {"root": str(root), "auto_init": True},
        "search": {"backend": "ripgrep"},
    }
    mem = MemoryService(config=mem_cfg)
    wiki = WikiService(config=wiki_cfg, store_root=root)

    mem.write(
        "用户偏好：回复风格尽量简短直接",
        category=MemoryCategory.preference,
        trace_id="demo-seed-mem",
    )

    raw = root / "raw" / "articles" / "mcp-demo.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        "# MCP Configuration\n\n"
        "Configure MCP servers in Cursor via mcp.json. Use least privilege.\n",
        encoding="utf-8",
    )
    wiki.ingest(
        WikiIngestRequest(
            source_path="raw/articles/mcp-demo.md",
            topic="MCP",
            trace_id="demo-seed-wiki",
        )
    )
    return mem, wiki


def _run_at_root(root: Path, query: str | None) -> int:
    mem, wiki = _seed(root)
    q = query or "MCP Cursor 配置 回复风格"

    result = combined_recall(
        q,
        memory_service=mem,
        wiki_service=wiki,
        trace_id="demo-recall-m2-m3",
    )

    print(f"query: {q}")
    print(f"trace_id: {result.trace_id}")
    print(f"memory_hits: {len(result.memory_items)}  wiki_hits: {len(result.wiki_items)}")
    print()
    print(result.prompt_context)
    print()

    if not result.memory_items:
        print("FAIL: expected memory hits", file=sys.stderr)
        return 1
    if not result.wiki_items:
        print("FAIL: expected wiki hits", file=sys.stderr)
        return 1
    mem_ok = any(
        k in result.prompt_context for k in ("偏好", "简短", "short", "preference")
    )
    if not mem_ok:
        print("FAIL: prompt missing memory preference", file=sys.stderr)
        return 1
    if "MCP" not in result.prompt_context and "mcp" not in result.prompt_context.lower():
        print("FAIL: prompt missing wiki topic", file=sys.stderr)
        return 1

    print("demo_recall_m2_m3: PASS")
    return 0


def run_demo(root: Path | None = None, query: str | None = None) -> int:
    if root is None:
        with tempfile.TemporaryDirectory(prefix="recall_demo_") as td:
            return _run_at_root(Path(td) / "wiki", query)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return _run_at_root(root, query)


def main() -> int:
    p = argparse.ArgumentParser(description="M2+M3 combined recall demo")
    p.add_argument("--root", type=Path, default=None)
    p.add_argument("--query", type=str, default=None)
    args = p.parse_args()
    return run_demo(args.root, args.query)


if __name__ == "__main__":
    sys.exit(main())
