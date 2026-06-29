#!/usr/bin/env python3
"""M3 D2 smoke — wiki_service.ingest one raw → one page."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_platform.wiki.contracts import WikiIngestRequest
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.store import ensure_store


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki_smoke"
        ensure_store(root, domain_note="smoke_d2")
        raw = root / "raw" / "articles" / "mcp-intro.md"
        raw.write_text(
            "# Model Context Protocol\n\n"
            "MCP connects LLM apps to external tools via a standard interface.\n",
            encoding="utf-8",
        )
        svc = WikiService(store_root=root)
        refs = svc.ingest(
            WikiIngestRequest(
                source_path="raw/articles/mcp-intro.md",
                topic="MCP",
                trace_id="smoke-d2",
            )
        )
        if len(refs) != 1:
            print("FAIL: expected 1 page ref")
            return 1
        page = root / refs[0].path
        if not page.is_file():
            print(f"FAIL: page missing {page}")
            return 1
        text = page.read_text(encoding="utf-8")
        if "Model Context Protocol" not in text or "raw/articles/mcp-intro.md" not in text:
            print("FAIL: page content")
            return 1
        print(f"smoke_wiki_d2: PASS page={refs[0].path} title={refs[0].title!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
