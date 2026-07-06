"""Student Jarvis learning contracts — StudentContext (Phase 1)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0.0"


class PipelineStage(str, Enum):
    onboarding = "onboarding"
    learning = "learning"
    practice = "practice"
    remediation = "remediation"
    review = "review"
    exam_prep = "exam_prep"


class _LearningModel(BaseModel):
    model_config = ConfigDict(
        use_enum_values=False,
        str_strip_whitespace=True,
        extra="forbid",
    )


class Curriculum(_LearningModel):
    grade: str
    subject: str
    unit_id: str
    unit_title: str
    textbook_ref: Optional[str] = None
    grade_level: Optional[int] = Field(default=None, ge=1, le=6)
    updated_by: Optional[Literal["jarvis", "parent", "onboarding"]] = None


class ContextFocus(_LearningModel):
    top_gap_ids: list[str] = Field(default_factory=list, max_length=3)
    queue_head_question_ids: list[str] = Field(default_factory=list, max_length=5)
    active_plan_id: Optional[str] = None

    @field_validator("top_gap_ids")
    @classmethod
    def _max_gaps(cls, v: list[str]) -> list[str]:
        return v[:3]

    @field_validator("queue_head_question_ids")
    @classmethod
    def _max_queue(cls, v: list[str]) -> list[str]:
        return v[:5]


class LearningGoal(_LearningModel):
    label: Optional[str] = None
    exam_at: Optional[datetime] = None
    target_mastery_pct: Optional[float] = Field(default=None, ge=0, le=100)


class SessionStats(_LearningModel):
    last_activity_at: Optional[datetime] = None
    attempts_today: int = Field(default=0, ge=0)
    correct_rate_7d: Optional[float] = Field(default=None, ge=0, le=1)


class ContextFlags(_LearningModel):
    do_not_disturb: bool = False
    teacher_review_pending: bool = False


class StudentContext(_LearningModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    student_id: str
    updated_at: datetime
    curriculum: Curriculum
    pipeline_stage: PipelineStage
    focus: ContextFocus = Field(default_factory=ContextFocus)
    goal: Optional[LearningGoal] = None
    session_stats: Optional[SessionStats] = None
    flags: ContextFlags = Field(default_factory=ContextFlags)
    trace_id: Optional[str] = None


class StudentContextPatch(_LearningModel):
    curriculum: Optional[Curriculum] = None
    pipeline_stage: Optional[PipelineStage] = None
    focus: Optional[ContextFocus] = None
    goal: Optional[LearningGoal] = None
    session_stats: Optional[SessionStats] = None
    flags: Optional[ContextFlags] = None


class StudentContextInit(_LearningModel):
    curriculum: Curriculum
    pipeline_stage: PipelineStage = PipelineStage.onboarding
    goal: Optional[LearningGoal] = None
    flags: Optional[ContextFlags] = None


class AnswerType(str, Enum):
    exact = "exact"
    numeric = "numeric"


class Question(_LearningModel):
    question_id: str
    unit_id: str
    knowledge_point_id: str
    stem: str
    answer_type: AnswerType
    expected_answer: str
    explanation: str
    default_error_code: str
    numeric_tolerance: Optional[float] = Field(default=None, gt=0)


class GradeResult(_LearningModel):
    correct: bool
    answer_normalized: str
    expected_answer: str
    explanation: str
    error_code: Optional[str] = None


class AttemptRecord(_LearningModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    attempt_id: str
    student_id: str
    question_id: str
    unit_id: str
    submitted_at: datetime
    answer_raw: str
    answer_normalized: str
    correct: bool
    expected_answer: str
    explanation: str
    error_code: Optional[str] = None
    knowledge_point_id: str
    trace_id: str
    source: str = "bank"  # "bank"=题库题+确定性grader；"freeform"=真实题+LLM判分


class GapStatus(str, Enum):
    active = "active"
    improving = "improving"
    mastered = "mastered"
    dormant = "dormant"


class GapTrend(str, Enum):
    up = "up"
    down = "down"
    flat = "flat"
    unknown = "unknown"


class GapStats(_LearningModel):
    total_wrong: int = Field(default=0, ge=0)
    wrong_7d: int = Field(default=0, ge=0)
    total_attempts: int = Field(default=0, ge=0)
    first_seen_at: Optional[datetime] = None
    last_wrong_at: Optional[datetime] = None


class GapMastery(_LearningModel):
    streak_correct: int = Field(default=0, ge=0)
    required_streak: int = Field(default=3, ge=1)
    mastered_at: Optional[datetime] = None


class GapEntry(_LearningModel):
    gap_id: str
    knowledge_point_id: str
    title: str
    status: GapStatus
    stats: GapStats
    mastery: GapMastery
    error_code: Optional[str] = None  # 以知识点为主轴后降为「代表性/可选错因」；明细见 error_breakdown
    error_breakdown: dict[str, int] = Field(default_factory=dict)  # 该知识点下各错因类型的累计次数
    trend: GapTrend = GapTrend.unknown
    last_attempt_id: Optional[str] = None
    last_seen_at: datetime
    evidence_attempt_ids: list[str] = Field(default_factory=list, max_length=20)
    notes: Optional[str] = None

    @field_validator("evidence_attempt_ids")
    @classmethod
    def _max_evidence(cls, v: list[str]) -> list[str]:
        return v[:20]


class GapMap(_LearningModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    student_id: str
    updated_at: datetime
    unit_id: str
    gaps: list[GapEntry] = Field(default_factory=list)
    taxonomy_version: Optional[str] = None


class TaxonomyEntry(_LearningModel):
    error_code: str
    title: str
    knowledge_point_id: str
    gap_id: str


class PushReason(str, Enum):
    gap_remediation = "gap_remediation"
    unit_practice = "unit_practice"


class PushQueueItem(_LearningModel):
    question_id: str
    gap_id: Optional[str] = None
    knowledge_point_id: str
    priority: int = Field(default=0, ge=0)
    reason: PushReason


class PushQueue(_LearningModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    student_id: str
    updated_at: datetime
    unit_id: str
    items: list[PushQueueItem] = Field(default_factory=list)
    batch_size_min: int = Field(default=3, ge=1)
    batch_size_max: int = Field(default=5, ge=1)


class QuestionFetchResult(_LearningModel):
    question_ids: list[str]
    questions: list[Question]
    gap_ids: list[Optional[str]]


class RemediationSkill(_LearningModel):
    skill_id: str
    title: str
    duration_min: int = Field(ge=1)
    error_codes: list[str] = Field(default_factory=list)
    procedure: str


class StudyPlanStep(_LearningModel):
    order: int = Field(ge=1)
    title: str
    duration_min: int = Field(ge=1)
    skill_id: str
    gap_id: Optional[str] = None
    instructions: str


class StudyPlan(_LearningModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    plan_id: str
    student_id: str
    created_at: datetime
    duration_min: int = Field(ge=1)
    gap_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    steps: list[StudyPlanStep] = Field(default_factory=list)


class LearningProactiveEventType(str, Enum):
    attempt_summary = "attempt_summary"
    gap_recurrence = "gap_recurrence"
    exam_prep = "exam_prep"


class LearningProactiveMessage(_LearningModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    event_id: str
    event_type: LearningProactiveEventType
    student_id: str
    created_at: datetime
    message: str
    gap_id: Optional[str] = None
    attempt_id: Optional[str] = None
    delivered: bool = True
    suppressed: bool = False


class AttemptSubmitResult(_LearningModel):
    attempt_id: str
    correct: bool
    explanation: str
    error_code: Optional[str] = None
    expected_answer: str
    session_stats: SessionStats
    proactive: list[LearningProactiveMessage] = Field(default_factory=list)
    skill_promotions: list["SkillPromotionResult"] = Field(default_factory=list)


class SkillPromotionResult(_LearningModel):
    gap_id: str
    error_code: str
    skill_name: str
    promoted: bool
    reason: str
    confidence: float


class GapSnapshot(_LearningModel):
    gap_id: str
    wrong_7d: int
    status: GapStatus
    recorded_at: datetime


class LearningKpiReport(_LearningModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    student_id: str
    period_days: int
    generated_at: datetime
    attempts_total: int
    correct_rate: Optional[float] = None
    re_error_rate: Optional[float] = None
    queue_completion_rate: Optional[float] = None
    gaps_mastered: int = 0
    gaps_active: int = 0


class StudentSelfAssessment(_LearningModel):
    math_level: Optional[str] = None
    chinese_level: Optional[str] = None
    habit_careless: bool = False
    habit_rushing: bool = False
    notes: Optional[str] = None


class StudentOnboardingProfile(_LearningModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    student_id: str
    updated_at: datetime
    grade: str
    grade_level: int = Field(ge=1, le=6)
    primary_subject: str = "数学"
    active_unit_id: str
    preferred_name: Optional[str] = None
    self_assessment: StudentSelfAssessment = Field(default_factory=StudentSelfAssessment)


class DimensionScore(_LearningModel):
    dimension_id: str
    title: str
    score: float = Field(ge=0, le=1)
    signal_count: int = Field(default=0, ge=0)


class ParentReportEvidence(_LearningModel):
    label: str
    attempt_id: Optional[str] = None
    gap_id: Optional[str] = None


class SubjectVolume(_LearningModel):
    subject: str
    attempts: int = 0
    correct_rate: Optional[float] = None


class UnitPracticeSummary(_LearningModel):
    unit_id: str
    unit_title: str
    subject: str
    grade: int
    attempts: int = 0
    correct_rate: Optional[float] = None


class ReportVolume(_LearningModel):
    attempts_total: int = 0
    active_days: int = 0
    correct_rate: Optional[float] = None
    by_subject: list[SubjectVolume] = Field(default_factory=list)
    units_practiced: list[UnitPracticeSummary] = Field(default_factory=list)
    gaps_mastered_period: int = 0
    gaps_active: int = 0


class ReportEvaluation(_LearningModel):
    headline: str = ""
    mastered: list[str] = Field(default_factory=list)
    needs_work: list[str] = Field(default_factory=list)
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    behavior_notes: list[str] = Field(default_factory=list)


class ReportRecommendation(_LearningModel):
    text: str
    basis: str = ""


class ParentWeeklyReport(_LearningModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    student_id: str
    audience: Literal["parent"] = "parent"
    period_days: int
    generated_at: datetime
    grade: str
    subject: str
    unit_title: str
    summary: str
    knowledge_highlights: list[str] = Field(default_factory=list)
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    behavior_notes: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    evidence: list[ParentReportEvidence] = Field(default_factory=list)
    attempts_total: int = 0
    correct_rate: Optional[float] = None
    volume: Optional[ReportVolume] = None
    evaluation: Optional[ReportEvaluation] = None
    recommendations: list[ReportRecommendation] = Field(default_factory=list)


class SafetyCheckResult(_LearningModel):
    allowed: bool
    reason_code: str
    redirect_message: Optional[str] = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
