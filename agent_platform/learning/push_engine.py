"""Push engine — gap-driven question queue (Phase 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import (
    AttemptRecord,
    GapEntry,
    GapMap,
    GapStatus,
    PipelineStage,
    PushQueue,
    PushQueueItem,
    PushReason,
    Question,
    QuestionFetchResult,
    utc_now,
)
from agent_platform.learning.gap_map import GapMapService, top_gap_ids, _priority_key
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.store import (
    layout_for,
    list_attempt_paths,
    load_attempt,
    load_push_queue,
    save_push_queue,
)
from agent_platform.learning.student_context import StudentContextService

MAX_QUEUE_SIZE = 10
RECENT_ATTEMPT_EXCLUDE = 5
PER_GAP_LIMIT = 4
FOCUS_HEAD_LIMIT = 5


def _eligible_gaps(gap_map: GapMap) -> list[GapEntry]:
    gaps = [g for g in gap_map.gaps if g.status in (GapStatus.active, GapStatus.improving)]
    return sorted(gaps, key=_priority_key)


def _recent_question_ids(attempts: list[AttemptRecord], limit: int = RECENT_ATTEMPT_EXCLUDE) -> set[str]:
    """Exclude recently mastered (correct) questions so wrong items stay pushable."""
    ordered = sorted(attempts, key=lambda a: a.submitted_at, reverse=True)
    excluded: list[str] = []
    for att in ordered:
        if att.correct:
            excluded.append(att.question_id)
        if len(excluded) >= limit:
            break
    return set(excluded)


def build_push_queue(
    *,
    student_id: str,
    unit_id: str,
    gap_map: GapMap,
    bank: QuestionBankService,
    attempts: list[AttemptRecord],
    batch_min: int = 3,
    batch_max: int = 5,
    student_grade_level: Optional[int] = None,
    catalog: Optional[KpCatalogService] = None,
    pipeline_stage: Optional[PipelineStage] = None,
    now=None,
) -> PushQueue:
    now = now or utc_now()
    recent = _recent_question_ids(attempts)
    gaps = _eligible_gaps(gap_map)
    items: list[PushQueueItem] = []
    seen: set[str] = set()

    allowed_unit_ids: Optional[set[str]] = None
    if student_grade_level is not None:
        cat = catalog or KpCatalogService()
        allowed_unit_ids = {u.unit_id for u in cat.list_units(grade_level=student_grade_level)}

    prioritize_new_unit = pipeline_stage == PipelineStage.learning

    def _add_unit_practice(max_items: int) -> None:
        nonlocal items
        for q in bank.list_questions(unit_id):
            if q.question_id in recent or q.question_id in seen:
                continue
            items.append(
                PushQueueItem(
                    question_id=q.question_id,
                    gap_id=None,
                    knowledge_point_id=q.knowledge_point_id,
                    priority=len(items),
                    reason=PushReason.unit_practice,
                )
            )
            seen.add(q.question_id)
            if len(items) >= max_items:
                break

    if prioritize_new_unit:
        _add_unit_practice(MAX_QUEUE_SIZE)

    for gap in gaps[:3]:
        candidates = bank.list_for_gap_kp(
            gap.knowledge_point_id,
            gap.error_code,
            allowed_unit_ids=allowed_unit_ids,
            prefer_unit_id=unit_id,
        )
        if not candidates:
            candidates = bank.list_for_gap(unit_id, gap.knowledge_point_id, gap.error_code or "")
        added = 0
        for q in candidates:
            if q.question_id in recent or q.question_id in seen:
                continue
            items.append(
                PushQueueItem(
                    question_id=q.question_id,
                    gap_id=gap.gap_id,
                    knowledge_point_id=q.knowledge_point_id,
                    priority=len(items),
                    reason=PushReason.gap_remediation,
                )
            )
            seen.add(q.question_id)
            added += 1
            if added >= PER_GAP_LIMIT or len(items) >= MAX_QUEUE_SIZE:
                break
        if len(items) >= MAX_QUEUE_SIZE:
            break

    if not items:
        _add_unit_practice(MAX_QUEUE_SIZE)

    return PushQueue(
        student_id=student_id,
        updated_at=now,
        unit_id=unit_id,
        items=items,
        batch_size_min=batch_min,
        batch_size_max=batch_max,
    )


def dominant_gap_id(queue: PushQueue) -> Optional[str]:
    remediation = [i for i in queue.items if i.reason == PushReason.gap_remediation and i.gap_id]
    if not remediation:
        return None
    counts: dict[str, int] = {}
    for item in remediation[:5]:
        assert item.gap_id is not None
        counts[item.gap_id] = counts.get(item.gap_id, 0) + 1
    return max(counts, key=counts.get)


class PushEngineService:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        bank: Optional[QuestionBankService] = None,
        gap_svc: Optional[GapMapService] = None,
        context_svc: Optional[StudentContextService] = None,
    ) -> None:
        cfg = load_student_learning_config()
        push_cfg = cfg.get("push") or {}
        self._batch_min = int(push_cfg.get("batch_size_min", 3))
        self._batch_max = int(push_cfg.get("batch_size_max", 5))
        self._data_root = data_root
        self._bank = bank or QuestionBankService()
        self._gaps = gap_svc or GapMapService(data_root=data_root)
        self._ctx = context_svc or StudentContextService(data_root=data_root)

    def _layout(self, student_id: str):
        return layout_for(student_id, self._data_root)

    def _load_attempts(self, student_id: str) -> list[AttemptRecord]:
        lay = self._layout(student_id)
        return [load_attempt(p) for p in list_attempt_paths(lay.attempts_dir)]

    def rebuild(
        self,
        student_id: str,
        gap_map: Optional[GapMap] = None,
        sync_focus: bool = True,
    ) -> PushQueue:
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")

        ctx = self._ctx.get(student_id)
        gap_map = gap_map or self._gaps.get(student_id)
        attempts = self._load_attempts(student_id)
        grade_level = ctx.curriculum.grade_level
        queue = build_push_queue(
            student_id=student_id,
            unit_id=ctx.curriculum.unit_id,
            gap_map=gap_map,
            bank=self._bank,
            attempts=attempts,
            batch_min=self._batch_min,
            batch_max=self._batch_max,
            student_grade_level=grade_level,
            pipeline_stage=ctx.pipeline_stage,
        )
        lay = self._layout(student_id)
        lay.ensure_student_dir()
        save_push_queue(lay.push_queue_path, queue)

        if sync_focus:
            head = [i.question_id for i in queue.items[:FOCUS_HEAD_LIMIT]]
            self._ctx.merge_focus(
                student_id,
                top_gap_ids=top_gap_ids(gap_map.gaps),
                queue_head_question_ids=head,
                active_plan_id=ctx.focus.active_plan_id,
            )
        return queue

    def get_queue(self, student_id: str) -> PushQueue:
        lay = self._layout(student_id)
        if not lay.push_queue_path.is_file():
            return self.rebuild(student_id)
        return load_push_queue(lay.push_queue_path)

    def peek(self, student_id: str, limit: int = 5) -> list[PushQueueItem]:
        queue = self.get_queue(student_id)
        return queue.items[:limit]

    def fetch(self, student_id: str, count: Optional[int] = None) -> QuestionFetchResult:
        queue = self.get_queue(student_id)
        if not queue.items:
            return QuestionFetchResult(question_ids=[], questions=[], gap_ids=[])
        n = count if count is not None else queue.batch_size_min
        n = min(max(1, n), queue.batch_size_max, len(queue.items))
        batch = queue.items[:n]
        questions = [self._bank.get(i.question_id) for i in batch]
        return QuestionFetchResult(
            question_ids=[q.question_id for q in questions],
            questions=questions,
            gap_ids=[i.gap_id for i in batch],
        )
