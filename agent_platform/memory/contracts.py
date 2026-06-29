"""Memory contracts — MemoryPort protocol and Pydantic schemas (M2)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"


class MemoryKind(str, Enum):
    fact = "fact"
    preference = "preference"
    episode = "episode"
    note = "note"


class MemoryCategory(str, Enum):
    """产品侧分类，与 MemVerse 内部分层解耦。"""

    user_profile = "user_profile"
    preference = "preference"
    project = "project"
    episode = "episode"
    other = "other"


class MemoryStatus(str, Enum):
    active = "active"
    tombstoned = "tombstoned"


class ObserveSource(str, Enum):
    cli = "cli"
    chat = "chat"
    voice = "voice"
    demo = "demo"
    reachy = "reachy"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _MemoryModel(BaseModel):
    model_config = ConfigDict(
        use_enum_values=False,
        str_strip_whitespace=True,
        extra="forbid",
    )


class ObserveEvent(_MemoryModel):
    """观测事件 — 进入记忆管道前的统一输入（阶段 A 最小字段）。"""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    ts: datetime = Field(default_factory=utc_now)
    source: ObserveSource = ObserveSource.chat
    modality: list[str] = Field(default_factory=lambda: ["text"])
    text: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: Optional[str] = None
    entities: list[str] = Field(default_factory=list)
    scene: Optional[str] = None
    raw_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_content(self) -> ObserveEvent:
        if not (self.text or self.payload):
            raise ValueError("ObserveEvent requires text or payload")
        return self

    def to_write_request(
        self,
        *,
        device_id: str,
        category: MemoryCategory = MemoryCategory.episode,
        kind: MemoryKind = MemoryKind.episode,
    ) -> MemoryWriteRequest:
        content = self.text
        if content is None and self.payload:
            content = json.dumps(self.payload, ensure_ascii=False)
        return MemoryWriteRequest(
            content=content or "",
            device_id=self.device_id or device_id,
            category=category,
            kind=kind,
            trace_id=self.trace_id,
            source_event_id=self.event_id,
            metadata={
                "source": self.source.value,
                "modality": self.modality,
                "scene": self.scene,
            },
        )


class MemoryRecord(_MemoryModel):
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: str = Field(min_length=1, max_length=128)
    ts: datetime = Field(default_factory=utc_now)
    category: MemoryCategory = MemoryCategory.other
    kind: MemoryKind = MemoryKind.fact
    content: str = Field(min_length=1)
    content_hash: Optional[str] = None
    status: MemoryStatus = MemoryStatus.active
    supersedes: Optional[str] = None
    trace_id: Optional[str] = None
    source_event_id: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == MemoryStatus.active

    @classmethod
    def from_write_request(cls, req: MemoryWriteRequest, *, record_id: Optional[str] = None) -> MemoryRecord:
        return cls(
            record_id=record_id or str(uuid4()),
            device_id=req.device_id,
            category=req.category,
            kind=req.kind,
            content=req.content.strip(),
            trace_id=req.trace_id,
            source_event_id=req.source_event_id,
            confidence=req.confidence,
            metadata=dict(req.metadata),
        )

    def as_tombstone(self, *, reason: str = "") -> MemoryRecord:
        return self.model_copy(
            update={
                "status": MemoryStatus.tombstoned,
                "metadata": {**self.metadata, "tombstone_reason": reason},
            }
        )

    def as_superseded_by(self, new_record_id: str) -> MemoryRecord:
        return self.model_copy(
            update={
                "status": MemoryStatus.tombstoned,
                "supersedes": new_record_id,
            }
        )


class MemoryWriteRequest(_MemoryModel):
    content: str = Field(min_length=1)
    device_id: str = Field(min_length=1, max_length=128)
    category: MemoryCategory = MemoryCategory.other
    kind: MemoryKind = MemoryKind.fact
    trace_id: Optional[str] = None
    source_event_id: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("content must not be empty")
        return s


class MemorySearchRequest(_MemoryModel):
    query: str = Field(min_length=1)
    device_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    category: Optional[MemoryCategory] = None
    limit: int = Field(default=10, ge=1, le=100)
    trace_id: Optional[str] = None

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("query must not be empty")
        return s


class MemoryHit(_MemoryModel):
    record_id: str
    content: str = Field(min_length=1)
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    device_id: Optional[str] = None
    category: Optional[MemoryCategory] = None
    kind: Optional[MemoryKind] = None
    ts: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearchResult(_MemoryModel):
    hits: list[MemoryHit] = Field(default_factory=list)
    raw: Optional[dict[str, Any]] = None


class MemoryCorrectRequest(_MemoryModel):
    """纠正：对旧记录 tombstone，并可选写入新事实。"""

    record_id: str = Field(min_length=1)
    reason: str = ""
    replacement: Optional[MemoryWriteRequest] = None
    trace_id: Optional[str] = None


class GateDecision(_MemoryModel):
    allowed: bool
    reason_code: str = "ok"
    details: dict[str, Any] = Field(default_factory=dict)


# Models exported as JSON Schema (TS / OpenAPI 可共用)
SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    ObserveEvent,
    MemoryRecord,
    MemoryWriteRequest,
    MemorySearchRequest,
    MemoryHit,
    MemorySearchResult,
    MemoryCorrectRequest,
    GateDecision,
)


def export_json_schemas() -> dict[str, Any]:
    """Return {ModelName: json_schema} for all public memory contracts."""
    bundle: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "agent_platform.memory",
        "version": SCHEMA_VERSION,
        "definitions": {},
    }
    for model in SCHEMA_MODELS:
        bundle["definitions"][model.__name__] = model.model_json_schema()
    return bundle


def write_json_schemas(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(export_json_schemas(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


@runtime_checkable
class MemoryPort(Protocol):
    """Adapter 必须实现的端口；Mock / MemVerse 可配置切换。"""

    def write(self, req: MemoryWriteRequest) -> MemoryRecord: ...

    def search(self, req: MemorySearchRequest) -> MemorySearchResult: ...

    def correct(self, req: MemoryCorrectRequest) -> MemoryRecord: ...

    def list_records(
        self,
        *,
        device_id: Optional[str] = None,
        category: Optional[MemoryCategory] = None,
        limit: int = 100,
    ) -> list[MemoryRecord]: ...
