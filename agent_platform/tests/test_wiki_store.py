"""M3 D1 — wiki store layout tests."""

from __future__ import annotations

from pathlib import Path

from agent_platform.wiki.store import ensure_store, layout_for, validate_store


def test_ensure_store_creates_skeleton(tmp_path: Path):
    root = tmp_path / "wiki_store"
    lay = ensure_store(root, domain_note="pytest")
    assert lay.root == root.resolve()
    assert lay.schema_path.is_file()
    assert lay.index_path.is_file()
    assert lay.log_path.is_file()
    assert lay.entities_dir.is_dir()
    assert (lay.raw_dir / "articles").is_dir()
    assert validate_store(root) == []


def test_ensure_store_idempotent(tmp_path: Path):
    root = tmp_path / "wiki_store"
    ensure_store(root)
    index_before = (root / "index.md").read_text(encoding="utf-8")
    ensure_store(root)
    index_after = (root / "index.md").read_text(encoding="utf-8")
    assert index_before == index_after


def test_layout_for_paths(tmp_path: Path):
    lay = layout_for(tmp_path / "w")
    assert lay.wiki_dir.name == "wiki"
    assert lay.concepts_dir == lay.wiki_dir / "concepts"
