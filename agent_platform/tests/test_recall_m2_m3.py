"""M3 D9 — combined M2+M3 recall tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from agent_platform.integrations.recall import combined_recall, format_prompt_context
from agent_platform.integrations.hermes.recall_tools import agent_combined_recall
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService
from agent_platform.wiki.contracts import WikiIngestRequest
from agent_platform.wiki.service import WikiService


@pytest.fixture
def seeded_services(tmp_path):
    root = tmp_path / "w"
    mem = MemoryService(
        config={
            "backend": "mock",
            "device": {"default_id": "t"},
            "gate": {"enabled": False},
            "audit": {"enabled": False},
        }
    )
    wiki = WikiService(
        config={"store": {"root": str(root), "auto_init": True}},
        store_root=root,
    )
    mem.write("like short replies", category=MemoryCategory.preference)
    raw = root / "raw" / "articles" / "a.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("# Alpha\n\nAlpha topic knowledge here.\n", encoding="utf-8")
    wiki.ingest(WikiIngestRequest(source_path="raw/articles/a.md", topic="Alpha"))
    return mem, wiki


def test_combined_recall_both_layers(seeded_services):
    mem, wiki = seeded_services
    r = combined_recall("Alpha short replies", memory_service=mem, wiki_service=wiki)
    assert r.memory_items
    assert r.wiki_items
    assert "记忆层" in r.prompt_context
    assert "Wiki" in r.prompt_context


def test_format_prompt_context_order():
    from agent_platform.integrations.recall import RecallItem

    text = format_prompt_context(
        [RecallItem("memory", "pref", "short", ref="r1")],
        [RecallItem("wiki", "Alpha", "facts", ref="wiki/x.md")],
    )
    assert text.index("记忆层") < text.index("Wiki")


def test_agent_combined_recall_tool(seeded_services, tmp_path):
    mem, wiki = seeded_services
    import agent_platform.integrations.hermes.tools as mt
    import agent_platform.integrations.hermes.wiki_tools as wt

    mt._get_service = lambda: mem  # type: ignore[attr-defined]
    wt._get_wiki_service = lambda: wiki  # type: ignore[attr-defined]

    out = json.loads(agent_combined_recall({"query": "Alpha short replies"}))
    assert out["success"]
    assert out["memory_count"] >= 1
    assert out["wiki_count"] >= 1
