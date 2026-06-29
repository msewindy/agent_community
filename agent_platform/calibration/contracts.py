"""Calibration contracts — US-6 (M7)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class _CalibModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CalibrateRequest(_CalibModel):
    """LLM 输出进入校准器前的请求。"""

    text: str = Field(min_length=1)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    has_tool_source: bool = False
    memory_backed: bool = False
    trace_id: Optional[str] = None


class CalibratedResponse(_CalibModel):
    text: str
    confidence_level: ConfidenceLevel
    confidence_score: float = Field(ge=0.0, le=1.0)
    rewritten: bool = False
    flags: list[str] = Field(default_factory=list)
    original_text: Optional[str] = None


class UserCorrectionRequest(_CalibModel):
    """用户指出 Agent 记错 → 道歉 + supersede。"""

    record_id: str
    old_value: str = Field(min_length=1)
    new_value: str = Field(min_length=1)
    reason: str = "user_correction"
    trace_id: Optional[str] = None
    device_id: Optional[str] = None


class CorrectionResult(_CalibModel):
    success: bool
    apology_text: str
    old_record_id: str
    new_record_id: Optional[str] = None
    tombstoned: bool = False
    trace_id: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
