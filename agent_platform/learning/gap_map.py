"""Gap map service and updater (Phase 3)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import (
    AttemptRecord,
    GapEntry,
    GapMap,
    GapMastery,
    GapStats,
    GapStatus,
    GapTrend,
    utc_now,
)
from agent_platform.learning.store import layout_for, load_gap_map, save_gap_map
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.taxonomy import TaxonomyService, gap_id_for_kp


def _priority_key(gap: GapEntry) -> tuple:
    status_rank = {
        GapStatus.active: 0,
        GapStatus.improving: 1,
        GapStatus.dormant: 2,
        GapStatus.mastered: 3,
    }
    last_wrong = gap.stats.last_wrong_at or gap.last_seen_at
    return (
        status_rank.get(gap.status, 9),
        -gap.stats.wrong_7d,
        -gap.stats.total_wrong,
        last_wrong.timestamp() if last_wrong else 0,
    )


def top_gap_ids(gaps: list[GapEntry], limit: int = 3) -> list[str]:
    eligible = [g for g in gaps if g.status in (GapStatus.active, GapStatus.improving)]
    ranked = sorted(eligible, key=_priority_key)
    return [g.gap_id for g in ranked[:limit]]


def _compute_trend(wrong_current: int, wrong_previous: int) -> GapTrend:
    if wrong_current > wrong_previous:
        return GapTrend.up
    if wrong_current < wrong_previous:
        return GapTrend.down
    if wrong_current == 0 and wrong_previous == 0:
        return GapTrend.unknown
    return GapTrend.flat


class GapMapUpdater:
    def __init__(
        self,
        taxonomy: Optional[TaxonomyService] = None,
        required_streak: Optional[int] = None,
        context_svc: Optional[StudentContextService] = None,
        data_root: Optional[Path] = None,
    ) -> None:
        cfg = load_student_learning_config()
        self._taxonomy = taxonomy or TaxonomyService(cfg)
        default_streak = (cfg.get("mastery") or {}).get("required_streak", 3)
        self._required_streak = int(required_streak if required_streak is not None else default_streak)
        self._ctx = context_svc
        self._data_root = data_root
        self._kp_titles: dict[str, str] = {}
        try:
            from agent_platform.learning.kp_catalog import KpCatalogService

            catalog = KpCatalogService(config=cfg)
            for unit in catalog.catalog.units:
                for kp in unit.knowledge_points:
                    self._kp_titles[kp.knowledge_point_id] = kp.title
        except Exception:
            # 目录不可用时退化为 kp_id 作标题（best-effort，不阻塞学情）
            self._kp_titles = {}

    def _gap_title(self, knowledge_point_id: str, error_code: Optional[str]) -> str:
        title = self._kp_titles.get(knowledge_point_id)
        if title:
            return title
        if error_code:
            try:
                return self._taxonomy.lookup(error_code).title
            except KeyError:
                pass
        return knowledge_point_id

    def rebuild(
        self,
        student_id: str,
        attempts: list[AttemptRecord],
        unit_id: str,
        now=None,
    ) -> GapMap:
        now = now or utc_now()
        window_start = now - timedelta(days=7)
        prev_window_start = now - timedelta(days=14)

        gaps_by_id: dict[str, GapEntry] = {}
        sorted_attempts = sorted(attempts, key=lambda a: a.submitted_at)

        for att in sorted_attempts:
            # 知识点为主轴：错题只要挂得上知识点即入学情（错因码可选，作为明细）
            if not att.correct and att.knowledge_point_id:
                kp_id = att.knowledge_point_id
                gap_id = gap_id_for_kp(kp_id)
                existing = gaps_by_id.get(gap_id)
                if existing is None:
                    existing = GapEntry(
                        gap_id=gap_id,
                        knowledge_point_id=kp_id,
                        error_code=att.error_code,
                        title=self._gap_title(kp_id, att.error_code),
                        status=GapStatus.active,
                        stats=GapStats(),
                        mastery=GapMastery(required_streak=self._required_streak),
                        last_seen_at=att.submitted_at,
                    )
                    gaps_by_id[gap_id] = existing

                existing.stats.total_wrong += 1
                existing.stats.total_attempts += 1
                if existing.stats.first_seen_at is None:
                    existing.stats.first_seen_at = att.submitted_at
                existing.stats.last_wrong_at = att.submitted_at
                existing.last_seen_at = att.submitted_at
                existing.last_attempt_id = att.attempt_id
                existing.mastery.streak_correct = 0
                existing.mastery.mastered_at = None
                existing.status = GapStatus.active
                if att.error_code:
                    existing.error_breakdown[att.error_code] = (
                        existing.error_breakdown.get(att.error_code, 0) + 1
                    )
                    if existing.error_code is None:
                        existing.error_code = att.error_code
                evidence = [att.attempt_id] + [
                    e for e in existing.evidence_attempt_ids if e != att.attempt_id
                ]
                existing.evidence_attempt_ids = evidence[:20]
                continue

            if att.correct:
                for gap in gaps_by_id.values():
                    if gap.knowledge_point_id != att.knowledge_point_id:
                        continue
                    if gap.status == GapStatus.mastered:
                        continue
                    gap.stats.total_attempts += 1
                    gap.last_seen_at = att.submitted_at
                    gap.last_attempt_id = att.attempt_id
                    gap.mastery.streak_correct += 1
                    if gap.mastery.streak_correct >= gap.mastery.required_streak:
                        gap.status = GapStatus.mastered
                        gap.mastery.mastered_at = att.submitted_at
                    elif gap.stats.wrong_7d == 0 and gap.mastery.streak_correct > 0:
                        gap.status = GapStatus.improving

        for gap in gaps_by_id.values():
            related_wrong = [
                a
                for a in sorted_attempts
                if not a.correct and a.knowledge_point_id == gap.knowledge_point_id
            ]
            gap.stats.wrong_7d = sum(1 for a in related_wrong if a.submitted_at >= window_start)
            wrong_prev = sum(
                1
                for a in related_wrong
                if prev_window_start <= a.submitted_at < window_start
            )
            gap.trend = _compute_trend(gap.stats.wrong_7d, wrong_prev)

            if gap.mastery.streak_correct >= gap.mastery.required_streak:
                gap.status = GapStatus.mastered
            elif gap.mastery.streak_correct > 0 and gap.stats.wrong_7d == 0:
                gap.status = GapStatus.improving
            elif gap.stats.wrong_7d > 0 or gap.mastery.streak_correct < gap.mastery.required_streak:
                if gap.status != GapStatus.mastered:
                    gap.status = GapStatus.active

        return GapMap(
            student_id=student_id,
            updated_at=now,
            unit_id=unit_id,
            taxonomy_version=self._taxonomy.version,
            gaps=sorted(gaps_by_id.values(), key=lambda g: g.gap_id),
        )

    def apply_after_attempt(
        self,
        student_id: str,
        attempts: list[AttemptRecord],
        unit_id: str,
        queue_head_question_ids: Optional[list[str]] = None,
        sync_focus: bool = True,
    ) -> GapMap:
        now = utc_now()
        gap_map = self.rebuild(student_id, attempts, unit_id, now)
        lay = layout_for(student_id, self._data_root)
        save_gap_map(lay.gap_map_path, gap_map)

        if sync_focus and self._ctx is not None:
            top = top_gap_ids(gap_map.gaps)
            current = self._ctx.get(student_id)
            self._ctx.merge_focus(
                student_id,
                top_gap_ids=top,
                queue_head_question_ids=queue_head_question_ids
                or list(current.focus.queue_head_question_ids),
                active_plan_id=current.focus.active_plan_id,
            )
        return gap_map


class GapMapService:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        taxonomy: Optional[TaxonomyService] = None,
    ) -> None:
        self._data_root = data_root
        self._taxonomy = taxonomy or TaxonomyService()

    def _layout(self, student_id: str):
        return layout_for(student_id, self._data_root)

    def get(self, student_id: str) -> GapMap:
        lay = self._layout(student_id)
        if not lay.gap_map_path.is_file():
            ctx_svc = StudentContextService(data_root=self._data_root)
            unit_id = "unknown"
            if ctx_svc.exists(student_id):
                unit_id = ctx_svc.get(student_id).curriculum.unit_id
            return GapMap(
                student_id=student_id,
                updated_at=utc_now(),
                unit_id=unit_id,
                taxonomy_version=self._taxonomy.version,
                gaps=[],
            )
        return load_gap_map(lay.gap_map_path)

    def query(self, student_id: str, limit: int = 10) -> list[GapEntry]:
        gap_map = self.get(student_id)
        ranked = sorted(gap_map.gaps, key=_priority_key)
        return ranked[:limit]

    def get_gap(self, student_id: str, gap_id: str) -> GapEntry:
        for gap in self.get(student_id).gaps:
            if gap.gap_id == gap_id:
                return gap
        raise KeyError(f"gap not found: {gap_id}")
