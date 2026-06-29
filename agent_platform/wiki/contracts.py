"""Wiki contracts — WikiPort protocol and Pydantic schemas (M3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0.0"


class WikiPageKind(str, Enum):
    entity = "entity"
    concept = "concept"
    synthesis = "synthesis"
    comparison = "comparison"
    archived_query = "archived_query"


class WikiSearchBackend(str, Enum):
    ripgrep = "ripgrep"
    qmd = "qmd"


class _WikiModel(BaseModel):
    model_config = ConfigDict(
        use_enum_values=False,
        str_strip_whitespace=True,
        extra="forbid",
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WikiIngestRequest(_WikiModel):
    """Ingest raw material into the wiki store (D2+ 实现)."""

    source_path: str = Field(
        min_length=1,
        description="Path under raw/ or absolute path within store_root",
    )
    topic: Optional[str] = None
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    source_event_id: Optional[str] = None
    device_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_path")
    @classmethod
    def _non_empty_path(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_path must be non-empty")
        return v.strip()


class WikiQueryRequest(_WikiModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=8, ge=1, le=50)
    trace_id: Optional[str] = None


class WikiPageRef(_WikiModel):
    path: str
    title: str = ""
    summary: str = ""
    kind: Optional[WikiPageKind] = None
    score: float = Field(default=1.0, ge=0.0, le=1.0)


class WikiQueryResult(_WikiModel):
    hits: list[WikiPageRef] = Field(default_factory=list)
    answer: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


class WikiLintStubResult(_WikiModel):
    """v1 仅占位；自动化 lint 属 v2。"""

    ok: bool = True
    message: str = "lint_stub: not implemented in M3 v1"
    issues: list[str] = Field(default_factory=list)


class WikiStoreLayout(_WikiModel):
    """Resolved paths for a wiki store (M3 D1)."""

    root: Path
    schema_path: Path
    index_path: Path
    log_path: Path
    raw_dir: Path
    wiki_dir: Path
    entities_dir: Path
    concepts_dir: Path
    comparisons_dir: Path
    queries_dir: Path

    model_config = ConfigDict(arbitrary_types_allowed=True)


# Models exported as JSON Schema
SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    WikiIngestRequest,
    WikiQueryRequest,
    WikiPageRef,
    WikiQueryResult,
    WikiLintStubResult,
    WikiStoreLayout,
)


def export_json_schemas() -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "agent_platform.wiki",
        "version": SCHEMA_VERSION,
        "definitions": {},
    }
    for model in SCHEMA_MODELS:
        schema = model.model_json_schema()
        if model is WikiStoreLayout:
            # Path → string in JSON Schema consumers
            for prop in ("root", "schema_path", "index_path", "log_path", "raw_dir", "wiki_dir",
                         "entities_dir", "concepts_dir", "comparisons_dir", "queries_dir"):
                if prop in schema.get("properties", {}):
                    schema["properties"][prop] = {"type": "string"}
        bundle["definitions"][model.__name__] = schema
    return bundle


def write_json_schemas(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(export_json_schemas(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


@runtime_checkable
class WikiPort(Protocol):
    def ingest(self, req: WikiIngestRequest) -> list[WikiPageRef]: ...

    def query(self, req: WikiQueryRequest) -> WikiQueryResult: ...

    def lint_stub(self) -> WikiLintStubResult: ...
