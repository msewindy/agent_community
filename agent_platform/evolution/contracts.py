"""Evolution layer contracts — experiences (L1) and skills (L2)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ExperienceComplexity(str, Enum):
    trivial = "trivial"
    moderate = "moderate"
    complex = "complex"


class SkillStatus(str, Enum):
    unverified = "unverified"
    active = "active"
    deprecated = "deprecated"


class ExperienceRecord(BaseModel):
    experience_id: str = Field(default_factory=lambda: str(uuid4()))
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_message: str
    assistant_message: str
    summary: str = ""
    topic: str = "general"
    keywords: list[str] = Field(default_factory=list)
    task_success: bool = True
    complexity: ExperienceComplexity = ExperienceComplexity.moderate
    user_intent: str = ""
    successful_strategy: Optional[str] = None
    failure_recovery: Optional[str] = None
    source_experience_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillRecord(BaseModel):
    skill_id: str = Field(default_factory=lambda: str(uuid4()))
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    name: str
    description: str = ""
    topic: str = "general"
    triggers: list[str] = Field(default_factory=list)
    procedure: str = ""
    guardrails: str = ""
    success_criteria: str = ""
    confidence: float = 0.5
    status: SkillStatus = SkillStatus.unverified
    source_experience_ids: list[str] = Field(default_factory=list)
    usage_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurriculumKind(str, Enum):
    gap = "gap"              # need more experiences to synthesize skill
    verify = "verify"        # skill exists but unverified / unused
    reinforce = "reinforce"  # active skill worth practicing
    recover = "recover"      # after user correction


class CurriculumItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: CurriculumKind
    topic: str
    title: str
    rationale: str
    suggested_prompt: str
    priority: float = 0.5
    related_skill: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurriculumPlan(BaseModel):
    items: list[CurriculumItem] = Field(default_factory=list)
    generated_by: str = "rules"


class CurriculumLogSource(str, Enum):
    pre_llm = "pre_llm"
    tool = "tool"


class CurriculumLogEntry(BaseModel):
    log_id: str = Field(default_factory=lambda: str(uuid4()))
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: CurriculumLogSource
    user_query: str = ""
    injected: bool = False
    generated_by: str = "rules"
    item_count: int = 0
    items: list[CurriculumItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
