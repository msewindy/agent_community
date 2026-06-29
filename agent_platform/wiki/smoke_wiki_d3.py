#!/usr/bin/env python3
"""M3 D3 smoke — ingest updates index.md and log.md."""

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
        ensure_store(root, domain_note="smoke_d3")
        (root / "raw" / "articles" / "wiki-pattern.md").write_text(
            "# LLM Wiki Pattern\n\nPersistent markdown knowledge base.\n",
            encoding="utf-8",
        )
        svc = WikiService(store_root=root)
        refs = svc.ingest(
            WikiIngestRequest(
                source_path="raw/articles/wiki-pattern.md",
                topic="LLM Wiki",
                trace_id="smoke-d3",
            )
        )
        index = (root / "index.md").read_text(encoding="utf-8")
        log = (root / "log.md").read_text(encoding="utf-8")
        if "[[wiki/concepts/" not in index or "LLM Wiki" not in index:
            print("FAIL: index.md missing entry")
            return 1
        if "Total pages:" not in index:
            print("FAIL: index header stats")
            return 1
        if "smoke-d3" not in log or "wiki-pattern" not in log:
            print("FAIL: log.md missing ingest line")
            return 1
        print(f"smoke_wiki_d3: PASS page={refs[0].path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
