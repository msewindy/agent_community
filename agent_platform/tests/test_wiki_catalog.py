"""M3 D3 — index.md and log.md catalog tests."""

from __future__ import annotations

from pathlib import Path

from agent_platform.wiki.catalog import (
    append_log_entry,
    format_index_entry,
    parse_index,
    record_ingest,
    render_index,
    upsert_index_entry,
)
from agent_platform.wiki.contracts import WikiPageKind, WikiPageRef
from agent_platform.wiki.store import ensure_store, layout_for


def test_format_index_entry():
    line = format_index_entry("wiki/concepts/mcp.md", "MCP", "Protocol for tools.")
    assert "[[wiki/concepts/mcp|MCP]]" in line
    assert "Protocol for tools." in line


def test_parse_and_render_index_roundtrip():
    raw = """# Wiki Index

> catalog

## Concepts

- [[wiki/concepts/a|A]] — first

## Entities

_(none yet)_
"""
    doc = parse_index(raw)
    assert len(doc.sections["Concepts"]) == 1
    out = render_index(doc)
    assert "Total pages:" in out
    assert "[[wiki/concepts/a|A]]" in out


def test_upsert_replaces_existing_entry(tmp_path: Path):
    root = tmp_path / "store"
    lay = ensure_store(root)
    ref1 = WikiPageRef(
        path="wiki/concepts/demo.md",
        title="Demo",
        summary="First summary.",
        kind=WikiPageKind.concept,
    )
    upsert_index_entry(lay, ref1)
    ref2 = WikiPageRef(
        path="wiki/concepts/demo.md",
        title="Demo",
        summary="Updated summary.",
        kind=WikiPageKind.concept,
    )
    upsert_index_entry(lay, ref2)
    text = lay.index_path.read_text(encoding="utf-8")
    assert text.count("wiki/concepts/demo") == 1
    assert "Updated summary." in text
    assert "First summary." not in text


def test_append_log_groups_by_date(tmp_path: Path):
    root = tmp_path / "store"
    lay = ensure_store(root)
    append_log_entry(
        lay,
        action="ingest",
        subject="Test",
        page_path="wiki/concepts/t.md",
        raw_rel="raw/articles/t.md",
        trace_id="tr-1",
    )
    log = lay.log_path.read_text(encoding="utf-8")
    assert "## [" in log
    assert "ingest" in log
    assert "trace=tr-1" in log


def test_record_ingest_updates_both(tmp_path: Path):
    root = tmp_path / "store"
    lay = ensure_store(root)
    ref = WikiPageRef(
        path="wiki/concepts/x.md",
        title="X",
        summary="Summary.",
        kind=WikiPageKind.concept,
    )
    record_ingest(lay, ref, raw_rel="raw/articles/x.md", trace_id="t-x")
    idx = lay.index_path.read_text(encoding="utf-8")
    log = lay.log_path.read_text(encoding="utf-8")
    assert "[[wiki/concepts/x|X]]" in idx
    assert "raw/articles/x.md" in log
