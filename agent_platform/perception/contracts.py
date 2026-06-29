"""Perception contracts — events aligned with memory ObserveEvent (M4)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent_platform.memory.contracts import ObserveEvent, ObserveSource, utc_now

SCHEMA_VERSION = "1.0.0"


class PerceptionBackend(str, Enum):
    mock = "mock"
    reachy_sdk = "reachy_sdk"


class PerceptionModality(str, Enum):
    vision = "vision"
    audio = "audio"
    proprioception = "proprioception"


class _PerceptionModel(BaseModel):
    model_config = ConfigDict(
        use_enum_values=False,
        str_strip_whitespace=True,
        extra="forbid",
    )


class PerceptionPolicy(_PerceptionModel):
    """User switches — camera/mic not always-on (US-2)."""

    camera_enabled: bool = False
    microphone_enabled: bool = False
    updated_at: datetime = Field(default_factory=utc_now)


class PerceptionStatus(_PerceptionModel):
    backend: PerceptionBackend
    connected: bool = False
    reachable: bool = False
    sdk_available: bool = False
    camera_enabled: bool = False
    microphone_enabled: bool = False
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class CaptureRequest(_PerceptionModel):
    """Request one perception capture → ObserveEvent."""

    modality: PerceptionModality = PerceptionModality.vision
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: Optional[str] = None
    scene: Optional[str] = None
    save_frame: bool = True
    force: bool = False


class SavedFrame(_PerceptionModel):
    """Persisted JPEG + metadata (M4 D2)."""

    image_path: str
    meta_path: str
    width: int
    height: int
    sha256: str
    format: str = "jpeg"
    captured_at: datetime = Field(default_factory=utc_now)
    backend: str = ""


class CaptureResult(_PerceptionModel):
    allowed: bool
    reason_code: str = "ok"
    event: Optional[ObserveEvent] = None
    frame_path: Optional[str] = None
    saved_frame: Optional[SavedFrame] = None
    message: str = ""


class DescribeRequest(_PerceptionModel):
    """On-demand VLM Q&A (M4 D3 / US-2) — capture then describe, not always-on."""

    question: str
    scene: Optional[str] = "desk"
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: Optional[str] = None
    session_id: Optional[str] = None
    frame_path: Optional[str] = None
    force: bool = False


class DescribeResult(_PerceptionModel):
    allowed: bool
    reason_code: str = "ok"
    description: Optional[str] = None
    event: Optional[ObserveEvent] = None
    frame_path: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    message: str = ""


class PerceptionStoreLayout(_PerceptionModel):
    root: Path
    policy_path: Path
    captures_dir: Path
    events_log_path: Path

    model_config = ConfigDict(arbitrary_types_allowed=True)


SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    PerceptionPolicy,
    PerceptionStatus,
    CaptureRequest,
    CaptureResult,
    SavedFrame,
    DescribeRequest,
    DescribeResult,
    PerceptionStoreLayout,
)


def export_json_schemas() -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "agent_platform.perception",
        "version": SCHEMA_VERSION,
        "definitions": {},
    }
    for model in SCHEMA_MODELS:
        schema = model.model_json_schema()
        if model is PerceptionStoreLayout:
            for prop in ("root", "policy_path", "captures_dir", "events_log_path"):
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


def capture_to_observe_event(
    *,
    text: str,
    trace_id: str,
    device_id: str,
    scene: Optional[str],
    frame_path: Optional[str],
    modality: PerceptionModality,
    extra: Optional[dict[str, Any]] = None,
) -> ObserveEvent:
    payload: dict[str, Any] = {
        "modality": modality.value,
        "frame_path": frame_path,
    }
    if extra:
        payload.update(extra)
    raw_refs = [frame_path] if frame_path else []
    return ObserveEvent(
        source=ObserveSource.reachy,
        modality=[modality.value],
        text=text,
        payload=payload,
        trace_id=trace_id,
        device_id=device_id,
        scene=scene,
        raw_refs=raw_refs,
    )


@runtime_checkable
class PerceptionPort(Protocol):
    def probe(self) -> PerceptionStatus: ...

    def capture(self, req: CaptureRequest, policy: PerceptionPolicy) -> CaptureResult: ...
