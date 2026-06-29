"""Behavior profile contracts — US-3 后半 (M7)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class Verbosity(str, Enum):
    short = "short"
    medium = "medium"
    long = "long"


class Tone(str, Enum):
    direct = "direct"
    neutral = "neutral"
    warm = "warm"


class _BehaviorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BehaviorProfile(_BehaviorModel):
    """「它的设定」行为档 — 弱人格、强一致。"""

    tone: Tone = Tone.direct
    verbosity: Verbosity = Verbosity.short
    language: str = Field(default="zh-CN", max_length=16)
    rules: list[str] = Field(default_factory=list)
    custom_notes: str = ""
    updated_at: Optional[datetime] = None

    def touch(self) -> BehaviorProfile:
        self.updated_at = datetime.now(timezone.utc)
        return self


class BehaviorProfileUpdate(_BehaviorModel):
    tone: Optional[Tone] = None
    verbosity: Optional[Verbosity] = None
    language: Optional[str] = None
    rules: Optional[list[str]] = None
    custom_notes: Optional[str] = None


class DriftReport(_BehaviorModel):
    drift_score: float = Field(ge=0.0, le=1.0)
    drifted: bool = False
    violations: list[str] = Field(default_factory=list)
    reinforcement: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
