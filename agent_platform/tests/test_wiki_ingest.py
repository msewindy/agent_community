"""M3 D2 — wiki ingest tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.wiki.contracts import WikiIngestRequest, WikiPageKind
from agent_platform.wiki.ingest import WikiIngestError, ingest_one, resolve_raw_path, slugify
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.store import ensure_store, layout_for


def test_slugify():
    assert slugify("Model Context Protocol") == "model-context-protocol"
    assert slugify("MCP 架构") == "mcp-架构"


def test_resolve_raw_path(tmp_path: Path):
    root = tmp_path / "store"
    ensure_store(root)
    raw = root / "raw" / "articles" / "note.md"
    raw.write_text("hello", encoding="utf-8")
    abs_p, rel = resolve_raw_path(root, "raw/articles/note.md")
    assert abs_p == raw.resolve()
    assert rel == "raw/articles/note.md"


def test_resolve_rejects_outside_raw(tmp_path: Path):
    root = tmp_path / "store"
    ensure_store(root)
    bad = root / "wiki" / "x.md"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(WikiIngestError, match="raw"):
        resolve_raw_path(root, "wiki/x.md")


def test_ingest_one_creates_concept_page(tmp_path: Path):
    root = tmp_path / "store"
    lay = ensure_store(root)
    raw = root / "raw" / "articles" / "demo.md"
    raw.write_text(
        "# Demo Topic\n\nThis is a demonstration paragraph for ingest.\n",
        encoding="utf-8",
    )
    ref = ingest_one(
        WikiIngestRequest(source_path="raw/articles/demo.md", topic="Demo Topic"),
        lay,
        default_kind=WikiPageKind.concept,
    )
    page = root / ref.path
    assert page.is_file()
    body = page.read_text(encoding="utf-8")
    assert "title: Demo Topic" in body
    assert "raw/articles/demo.md" in body
    assert ref.kind == WikiPageKind.concept
    index = (root / "index.md").read_text(encoding="utf-8")
    log = (root / "log.md").read_text(encoding="utf-8")
    assert ref.path in index or "demo" in index.lower()
    assert "ingest" in log
    assert "raw/articles/demo.md" in log


def test_wiki_service_ingest(tmp_path: Path):
    root = tmp_path / "store"
    ensure_store(root)
    (root / "raw" / "articles" / "svc.md").write_text("# Svc\n\nBody text.\n", encoding="utf-8")
    svc = WikiService(store_root=root)
    refs = svc.ingest(WikiIngestRequest(source_path="raw/articles/svc.md"))
    assert len(refs) == 1
    assert (root / refs[0].path).exists()


def test_wiki_service_query_empty_store(tmp_path: Path):
    root = tmp_path / "store"
    ensure_store(root)
    svc = WikiService(store_root=root)
    from agent_platform.wiki.contracts import WikiQueryRequest

    result = svc.query(WikiQueryRequest(query="nonexistent-topic-xyz"))
    assert result.hits == []
