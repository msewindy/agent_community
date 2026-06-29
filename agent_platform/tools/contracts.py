"""Tool / MCP contracts — L0–L2 governance (M6)."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent_platform.memory.contracts import utc_now

SCHEMA_VERSION = "1.0.0"


class ToolLevel(str, Enum):
    L0 = "L0"  # 只读 / 低风险，直接执行
    L1 = "L1"  # 低风险写，直接执行
    L2 = "L2"  # 外发 / 破坏性，需草稿确认


class ToolInvokeStatus(str, Enum):
    executed = "executed"
    draft_pending = "draft_pending"
    denied = "denied"
    error = "error"


class DraftStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class _ToolsModel(BaseModel):
    model_config = ConfigDict(use_enum_values=False, str_strip_whitespace=True, extra="forbid")


class ToolInvokeRequest(_ToolsModel):
    """Invoke MCP tool through governance + optional draft gate."""

    server: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str = "default"
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    draft_id: Optional[str] = None
    force_execute: bool = False


class ToolInvokeResult(_ToolsModel):
    status: ToolInvokeStatus
    level: ToolLevel
    server: str
    tool: str
    output: Any = None
    draft_id: Optional[str] = None
    message: str = ""
    trace_id: str = ""


class DraftRecord(_ToolsModel):
    draft_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    trace_id: str
    server: str
    tool: str
    arguments: dict[str, Any]
    level: ToolLevel = ToolLevel.L2
    status: DraftStatus = DraftStatus.pending
    preview: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class DraftApproveRequest(_ToolsModel):
    draft_id: str
    session_id: Optional[str] = None
    trace_id: str = Field(default_factory=lambda: str(uuid4()))


class DraftRejectRequest(_ToolsModel):
    draft_id: str
    reason: str = ""


class ToolsStoreLayout(_ToolsModel):
    root: Path
    sandbox_root: Path
    drafts_dir: Path
    events_log_path: Path

    model_config = ConfigDict(arbitrary_types_allowed=True)


def export_json_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "agent_platform.tools",
        "version": SCHEMA_VERSION,
        "ToolInvokeRequest": ToolInvokeRequest.model_json_schema(),
        "ToolInvokeResult": ToolInvokeResult.model_json_schema(),
        "DraftRecord": DraftRecord.model_json_schema(),
    }


def schema_bundle_json() -> str:
    return json.dumps(export_json_schema(), ensure_ascii=False, indent=2)
