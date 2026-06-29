"""M3 D4 — wiki query tests."""

from __future__ import annotations

from pathlib import Path

from agent_platform.wiki.contracts import WikiIngestRequest, WikiQueryRequest
from agent_platform.wiki.query import (
    build_answer,
    run_query,
    search_index,
    search_ripgrep,
    tokenize_query,
)
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.store import ensure_store


def test_tokenize_query_cjk():
    assert "mcp" in tokenize_query("MCP 架构")


def test_search_index_finds_entry(tmp_path: Path):
    root = tmp_path / "store"
    lay = ensure_store(root)
    idx = lay.index_path.read_text(encoding="utf-8")
    lay.index_path.write_text(
        idx.replace(
            "_(none yet)_",
            "- [[wiki/concepts/demo|Demo]] — A demonstration concept.",
            1,
        ),
        encoding="utf-8",
    )
    hits = search_index(lay, "demonstration", limit=5)
    assert len(hits) == 1
    assert "demo" in hits[0].path.lower()


def test_search_ripgrep_finds_page(tmp_path: Path):
    root = tmp_path / "store"
    lay = ensure_store(root)
    page = lay.concepts_dir / "unique-term-xyz.md"
    page.write_text("# Unique\n\nunique-term-xyz appears here.\n", encoding="utf-8")
    hits = search_ripgrep(lay, "unique-term-xyz", limit=5)
    assert any("unique-term-xyz" in h.path for h in hits)


def test_run_query_after_ingest(tmp_path: Path):
    root = tmp_path / "store"
    ensure_store(root)
    svc = WikiService(store_root=root)
    (root / "raw" / "articles" / "mcp.md").write_text(
        "# MCP\n\nModel Context Protocol for tools.\n",
        encoding="utf-8",
    )
    svc.ingest(WikiIngestRequest(source_path="raw/articles/mcp.md", topic="MCP"))
    result = svc.query(WikiQueryRequest(query="Model Context Protocol"))
    assert result.hits
    assert result.answer
    assert "MCP" in result.answer or "mcp" in result.hits[0].path.lower()


def test_build_answer_empty(tmp_path: Path):
    lay = ensure_store(tmp_path / "s")
    assert build_answer(lay, "q", []) is None
