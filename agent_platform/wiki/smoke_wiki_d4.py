#!/usr/bin/env python3
"""M3 D4 smoke — wiki_service.query."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_platform.wiki.contracts import WikiIngestRequest, WikiQueryRequest
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.store import ensure_store


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki_smoke"
        ensure_store(root, domain_note="smoke_d4")
        (root / "raw" / "articles" / "reachy.md").write_text(
            "# Reachy Mini\n\nReachy is a desktop robot with camera and mic.\n",
            encoding="utf-8",
        )
        svc = WikiService(store_root=root)
        svc.ingest(
            WikiIngestRequest(
                source_path="raw/articles/reachy.md",
                topic="Reachy Mini",
                trace_id="smoke-d4-ingest",
            )
        )
        result = svc.query(WikiQueryRequest(query="Reachy robot camera", trace_id="smoke-d4"))
        if not result.hits:
            print("FAIL: no query hits")
            return 1
        if not any("reachy" in h.path.lower() for h in result.hits):
            print("FAIL: expected reachy page in hits", [h.path for h in result.hits])
            return 1
        if not result.answer or "Reachy" not in result.answer:
            print("FAIL: answer missing content")
            return 1
        log = (root / "log.md").read_text(encoding="utf-8")
        if "smoke-d4" not in log or "query" not in log:
            print("FAIL: log missing query entry")
            return 1
        print(f"smoke_wiki_d4: PASS hits={len(result.hits)} top={result.hits[0].path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
