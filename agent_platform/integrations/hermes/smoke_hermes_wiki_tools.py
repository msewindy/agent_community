#!/usr/bin/env python3
"""M3 D7 — smoke Hermes wiki_* tool handlers."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from agent_platform.integrations.hermes.tools import bootstrap_agent_platform
from agent_platform.integrations.hermes import wiki_tools as wt


def main() -> int:
    bootstrap_agent_platform()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        cfg = {
            "store": {"root": str(root), "auto_init": True},
            "precipitate": {"min_assistant_turns": 2, "min_user_chars_total": 10},
        }
        from agent_platform.wiki.service import WikiService

        svc = WikiService(config=cfg, store_root=root)
        wt._get_wiki_service = lambda: svc  # type: ignore[attr-defined]

        raw = root / "raw" / "articles" / "hermes-wiki.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(
            "# Hermes Wiki Tool\n\nTool smoke test for wiki_ingest and wiki_query.\n",
            encoding="utf-8",
        )

        ing = json.loads(
            wt.wiki_ingest(
                {"source_path": "raw/articles/hermes-wiki.md", "topic": "Hermes Wiki"},
                current_session_id="smoke-wiki",
            )
        )
        assert ing.get("success"), ing
        assert ing.get("count", 0) >= 1, ing

        q = json.loads(wt.wiki_query({"query": "Hermes wiki ingest"}, current_session_id="smoke-wiki"))
        assert q.get("success") and q.get("count", 0) >= 1, q
        assert q.get("answer"), q

        prec = json.loads(
            wt.wiki_precipitate_evaluate(
                {"session_id": "smoke-wiki", "message": "/沉淀", "role": "user"},
            )
        )
        assert prec.get("offer") is True, prec

    print("smoke_hermes_wiki_tools: OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"smoke_hermes_wiki_tools: FAIL — {e}", file=sys.stderr)
        raise
