"""M3 D1 — wiki contract schema tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_platform.wiki.contracts import (
    SCHEMA_MODELS,
    SCHEMA_VERSION,
    WikiIngestRequest,
    WikiPageKind,
    WikiPageRef,
    WikiQueryRequest,
    WikiQueryResult,
    WikiStoreLayout,
    export_json_schemas,
    write_json_schemas,
)


def test_wiki_ingest_request():
    req = WikiIngestRequest(
        source_path="raw/articles/note.md",
        topic="MCP",
        trace_id="t-1",
    )
    assert req.source_path.endswith(".md")
    assert req.topic == "MCP"


def test_wiki_ingest_rejects_empty_path():
    with pytest.raises(ValidationError):
        WikiIngestRequest(source_path="   ")


def test_wiki_query_request_limit_bounds():
    with pytest.raises(ValidationError):
        WikiQueryRequest(query="x", limit=0)
    q = WikiQueryRequest(query="MCP 架构", limit=5)
    assert q.limit == 5


def test_wiki_page_ref_kind():
    ref = WikiPageRef(
        path="wiki/concepts/mcp.md",
        title="MCP",
        kind=WikiPageKind.concept,
        score=0.9,
    )
    assert ref.kind == WikiPageKind.concept


def test_export_json_schemas_bundle():
    bundle = export_json_schemas()
    assert bundle["version"] == SCHEMA_VERSION
    assert len(bundle["definitions"]) == len(SCHEMA_MODELS)
    assert "WikiIngestRequest" in bundle["definitions"]


def test_write_json_schemas(tmp_path: Path):
    out = tmp_path / "wiki_bundle.json"
    write_json_schemas(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["definitions"]["WikiQueryRequest"]["type"] == "object"
