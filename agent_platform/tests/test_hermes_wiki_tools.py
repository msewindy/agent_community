"""M3 D7 — Hermes wiki_* tool handlers."""

from __future__ import annotations

import json

import pytest

from agent_platform.integrations.hermes import wiki_tools as wt


@pytest.fixture
def wiki_svc(tmp_path):
    cfg = {
        "store": {"root": str(tmp_path / "w"), "auto_init": True},
        "search": {"backend": "ripgrep", "limit_default": 5},
    }
    from agent_platform.wiki.service import WikiService

    svc = WikiService(config=cfg, store_root=tmp_path / "w")
    wt._get_wiki_service = lambda: svc  # type: ignore[attr-defined]
    raw = tmp_path / "w" / "raw" / "articles" / "t.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("# Test\n\nWiki tool pytest content.\n", encoding="utf-8")
    return svc


def test_wiki_ingest_and_query(wiki_svc) -> None:
    ing = json.loads(
        wt.wiki_ingest({"source_path": "raw/articles/t.md", "topic": "Test"})
    )
    assert ing["success"]
    assert ing["count"] == 1

    q = json.loads(wt.wiki_query({"query": "Wiki tool pytest"}))
    assert q["success"]
    assert q["count"] >= 1
    assert "answer" in q


def test_wiki_ingest_missing_path() -> None:
    out = json.loads(wt.wiki_ingest({}))
    assert "error" in out or out.get("success") is False


def test_precipitate_explicit(wiki_svc) -> None:
    out = json.loads(
        wt.wiki_precipitate_evaluate(
            {"session_id": "s1", "message": "/沉淀", "role": "user", "record": False}
        )
    )
    assert out["offer"] is True
    assert out["reason_code"] == "explicit_command"
