"""Proactive behavior contracts — US-5 (M5)."""

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


class ProactiveLevel(str, Enum):
    L0 = "L0"
    L1 = "L1"


class ProactiveReason(str, Enum):
    ok = "ok"
    disabled = "disabled"
    quiet_hours = "quiet_hours"
    session_snoozed = "session_snoozed"
    cooldown = "cooldown"
    no_trigger = "no_trigger"
    dismissed_feedback = "dismissed_feedback"


class _ProactiveModel(BaseModel):
    model_config = ConfigDict(use_enum_values=False, str_strip_whitespace=True, extra="forbid")


class QuietHoursPolicy(_ProactiveModel):
    enabled: bool = True
    start: str = "22:00"
    end: str = "07:00"
    timezone: str = "Asia/Shanghai"


class ProactiveEvaluateRequest(_ProactiveModel):
    """Whether the agent may speak proactively now."""

    session_id: str
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: Optional[str] = None
    work_minutes: Optional[float] = None
    natural_pause: bool = False
    now: Optional[datetime] = None


class ProactiveProposal(_ProactiveModel):
    message: str
    level: ProactiveLevel = ProactiveLevel.L0
    trigger: str = "work_break"
    trace_id: str = ""


class ProactiveEvaluateResult(_ProactiveModel):
    allowed: bool
    reason_code: str = ProactiveReason.no_trigger.value
    proposal: Optional[ProactiveProposal] = None
    message: str = ""


class ProactiveFeedbackRequest(_ProactiveModel):
    """User says do not disturb — snooze session + optional memory."""

    session_id: str
    user_message: str
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    device_id: Optional[str] = None
    write_memory: bool = True


class ProactiveFeedbackResult(_ProactiveModel):
    session_snoozed: bool
    memory_written: bool
    memory_record_id: Optional[str] = None
    memory_deduped: bool = False
    memory_error: Optional[str] = None
    dismissed: bool = False
    message: str = ""


class ProactiveStoreLayout(_ProactiveModel):
    root: Path
    sessions_dir: Path
    events_log_path: Path

    model_config = ConfigDict(arbitrary_types_allowed=True)


SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    QuietHoursPolicy,
    ProactiveEvaluateRequest,
    ProactiveProposal,
    ProactiveEvaluateResult,
    ProactiveFeedbackRequest,
    ProactiveFeedbackResult,
    ProactiveStoreLayout,
)


def export_json_schemas() -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "agent_platform.proactive",
        "version": SCHEMA_VERSION,
        "definitions": {},
    }
    for model in SCHEMA_MODELS:
        schema = model.model_json_schema()
        if model is ProactiveStoreLayout:
            for prop in ("root", "sessions_dir", "events_log_path"):
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
