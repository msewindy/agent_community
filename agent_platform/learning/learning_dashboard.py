"""Parent learning dashboard — grade-wide subject overview (no period filter)."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import GapMap, GapStatus
from agent_platform.learning.dimension_model import DimensionModelService
from agent_platform.learning.gap_map import GapMapService
from agent_platform.learning.kp_catalog import KpCatalogService, UnitCatalogEntry
from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.store import layout_for, list_attempt_paths, load_attempt
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.student_identity import resolve_student_display_name


class UnitProgressOut(BaseModel):
    unit_id: str
    unit_title: str
    kp_total: int = 0
    kp_mastered: int = 0
    kp_weak: int = 0
    kp_unstarted: int = 0
    attempts: int = 0
    correct_rate: Optional[float] = None
    progress_label: str = ""


class SubjectAttentionOut(BaseModel):
    kind: Literal["knowledge_gap", "dimension", "repeat_error"]
    title: str
    detail: str
    unit_id: Optional[str] = None
    unit_title: Optional[str] = None
    grade: Optional[int] = None
    is_historical: bool = False


class SubjectCardOut(BaseModel):
    subject: str
    grade_level: int
    units_total: int = 0
    units_with_practice: int = 0
    attempts_total: int = 0
    correct_rate: Optional[float] = None
    kp_total: int = 0
    kp_mastered: int = 0
    kp_weak: int = 0
    historical_weak_count: int = 0
    summary: str = ""
    units: list[UnitProgressOut] = Field(default_factory=list)
    attention_items: list[SubjectAttentionOut] = Field(default_factory=list)


class LearningDashboardOut(BaseModel):
    student_id: str
    display_name: str
    grade: str
    grade_level: int
    subjects: list[SubjectCardOut] = Field(default_factory=list)
    catalog_subjects: list[str] = Field(default_factory=list)


class LearningDashboardService:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        context_svc: Optional[StudentContextService] = None,
        catalog: Optional[KpCatalogService] = None,
        gap_svc: Optional[GapMapService] = None,
        dimension_svc: Optional[DimensionModelService] = None,
        onboarding_svc: Optional[OnboardingService] = None,
        config: Optional[dict] = None,
        memory_svc=None,
    ) -> None:
        self._cfg = config or load_student_learning_config()
        self._ctx = context_svc or StudentContextService(data_root=data_root, config=self._cfg)
        self._catalog = catalog or KpCatalogService(config=self._cfg)
        self._gaps = gap_svc or GapMapService(data_root=data_root)
        self._dims = dimension_svc or DimensionModelService(self._cfg)
        self._onboarding = onboarding_svc or OnboardingService(
            data_root=data_root, context_svc=self._ctx, catalog=self._catalog
        )
        self._memory = memory_svc
        self._data_root = data_root
        self._kp_units = self._catalog.kp_index()

    def _grade_level(self, student_id: str) -> int:
        ctx = self._ctx.get(student_id)
        if ctx.curriculum.grade_level is not None:
            return int(ctx.curriculum.grade_level)
        try:
            return self._onboarding.load_profile(student_id).grade_level
        except FileNotFoundError:
            return self._catalog.resolve_grade_level(ctx.curriculum.grade)

    def _load_all_attempts(self, student_id: str):
        lay = layout_for(student_id, self._data_root)
        out = []
        for path in list_attempt_paths(lay.attempts_dir):
            out.append(load_attempt(path))
        return out

    def _unit_for_gap(self, gap) -> Optional[UnitCatalogEntry]:
        return self._kp_units.get(gap.knowledge_point_id)

    def _unit_progress(
        self,
        unit: UnitCatalogEntry,
        *,
        gaps_by_kp: dict,
        unit_attempts: list,
    ) -> UnitProgressOut:
        kp_ids = [kp.knowledge_point_id for kp in unit.knowledge_points]
        mastered = weak = unstarted = 0
        for kp_id in kp_ids:
            g = gaps_by_kp.get(kp_id)
            if g is None or g.status == GapStatus.dormant:
                if not any(a.knowledge_point_id == kp_id for a in unit_attempts):
                    unstarted += 1
                continue
            if g.status == GapStatus.mastered:
                mastered += 1
            elif g.status in (GapStatus.active, GapStatus.improving):
                weak += 1
            else:
                unstarted += 1

        attempts = len(unit_attempts)
        rate = None
        if unit_attempts:
            rate = round(sum(1 for a in unit_attempts if a.correct) / len(unit_attempts), 3)

        if attempts == 0 and weak == 0 and mastered == 0:
            label = "未开始"
        elif weak > 0:
            label = f"需加强 · {weak} 个薄弱点"
        elif mastered >= len(kp_ids) and kp_ids:
            label = "已掌握"
        elif attempts > 0:
            label = "练习中"
        else:
            label = "待练习"

        return UnitProgressOut(
            unit_id=unit.unit_id,
            unit_title=unit.unit_title,
            kp_total=len(kp_ids),
            kp_mastered=mastered,
            kp_weak=weak,
            kp_unstarted=unstarted,
            attempts=attempts,
            correct_rate=rate,
            progress_label=label,
        )

    def _subject_summary(
        self,
        *,
        subject: str,
        units: list[UnitProgressOut],
        weak_kp: int,
        attempts_total: int,
        correct_rate: Optional[float],
    ) -> str:
        practiced = sum(1 for u in units if u.attempts > 0)
        if attempts_total == 0:
            return f"{subject}尚未开始本年级系统练习，可从第一个单元学起。"
        rate_txt = f"，总正确率 {round(correct_rate * 100)}%" if correct_rate is not None else ""
        if weak_kp == 0:
            return (
                f"本年级 {len(units)} 个单元中已练习 {practiced} 个，"
                f"暂无薄弱知识点{rate_txt}，整体掌握良好。"
            )
        weak_units = [u for u in units if u.kp_weak > 0]
        focus = weak_units[0].unit_title if weak_units else ""
        return (
            f"本年级已练习 {practiced}/{len(units)} 个单元，"
            f"有 {weak_kp} 个知识点需加强{rate_txt}。"
            + (f"建议优先关注「{focus}」。" if focus else "")
        )

    def _attempts_for_subject(
        self,
        attempts: list,
        subject: str,
        *,
        grade_level: Optional[int] = None,
        below_grade: bool = False,
    ) -> list:
        out = []
        for att in attempts:
            try:
                u = self._catalog.get_unit(att.unit_id)
            except KeyError:
                continue
            if u.subject != subject:
                continue
            if grade_level is not None:
                if below_grade:
                    if u.grade >= grade_level:
                        continue
                elif u.grade != grade_level:
                    continue
            out.append(att)
        return out

    def _gaps_for_subject(self, gap_map, subject: str) -> list:
        out = []
        for g in gap_map.gaps:
            unit = self._unit_for_gap(g)
            if unit is not None and unit.subject == subject:
                out.append((g, unit))
        return out

    def _gap_map_slice(self, gap_map, gaps: list) -> GapMap:
        return gap_map.model_copy(update={"gaps": gaps})

    def _dimension_items(
        self,
        *,
        attempts: list,
        gap_slice: GapMap,
        is_historical: bool,
    ) -> list[SubjectAttentionOut]:
        items: list[SubjectAttentionOut] = []
        for d in self._dims.score_from_attempts(attempts, gap_map=gap_slice):
            if d.signal_count <= 0:
                continue
            detail = f"累计 {d.signal_count} 次相关失误"
            if d.dimension_id == "reading_care":
                detail += "，建议做题前圈画已知条件"
            elif d.dimension_id == "carelessness":
                detail += "，建议做完验算一遍"
            items.append(
                SubjectAttentionOut(
                    kind="dimension",
                    title=d.title,
                    detail=detail,
                    is_historical=is_historical,
                    grade=None,
                )
            )
        return items

    def _repeat_error_item(
        self, attempts: list, *, is_historical: bool
    ) -> Optional[SubjectAttentionOut]:
        wrong = [a for a in attempts if not a.correct and a.error_code]
        if len(wrong) < 2:
            return None
        codes = [a.error_code for a in wrong if a.error_code]
        if not codes:
            return None
        top_code, top_n = Counter(codes).most_common(1)[0]
        if top_n < 2:
            return None
        return SubjectAttentionOut(
            kind="repeat_error",
            title="重复犯错",
            detail=f"错因「{top_code}」出现 {top_n} 次",
            is_historical=is_historical,
        )

    def _subject_attention(
        self,
        *,
        subject: str,
        grade_level: int,
        gap_map,
        all_attempts: list,
    ) -> list[SubjectAttentionOut]:
        """Per-subject attention: current grade first, then historical (lower grades)."""
        current: list[SubjectAttentionOut] = []
        historical: list[SubjectAttentionOut] = []

        subject_gap_pairs = self._gaps_for_subject(gap_map, subject)
        current_gap_ids = {
            g.gap_id
            for g, u in subject_gap_pairs
            if u.grade == grade_level
            and g.status in (GapStatus.active, GapStatus.improving)
        }
        current_gaps_only = [g for g, _ in subject_gap_pairs if g.gap_id in current_gap_ids]
        hist_gaps_only = [
            g
            for g, u in subject_gap_pairs
            if u.grade < grade_level and g.status in (GapStatus.active, GapStatus.improving)
        ]

        cur_attempts = self._attempts_for_subject(
            all_attempts, subject, grade_level=grade_level
        )
        hist_attempts = self._attempts_for_subject(
            all_attempts, subject, grade_level=grade_level, below_grade=True
        )

        current.extend(
            self._dimension_items(
                attempts=cur_attempts,
                gap_slice=self._gap_map_slice(gap_map, current_gaps_only),
                is_historical=False,
            )
        )
        hist_dim = self._dimension_items(
            attempts=hist_attempts,
            gap_slice=self._gap_map_slice(gap_map, hist_gaps_only),
            is_historical=True,
        )
        current_dim_ids = {f"dimension:{i.title}" for i in current if i.kind == "dimension"}
        for item in hist_dim:
            key = f"dimension:{item.title}"
            if key not in current_dim_ids:
                historical.append(item)

        rep_cur = self._repeat_error_item(cur_attempts, is_historical=False)
        if rep_cur:
            current.append(rep_cur)
        rep_hist = self._repeat_error_item(hist_attempts, is_historical=True)
        if rep_hist and (not rep_cur or rep_hist.detail != rep_cur.detail):
            historical.append(rep_hist)

        active_gaps = sorted(
            [
                (g, u)
                for g, u in subject_gap_pairs
                if g.status in (GapStatus.active, GapStatus.improving)
            ],
            key=lambda pair: (-pair[0].stats.total_wrong, -pair[0].stats.wrong_7d),
        )
        for g, unit in active_gaps:
            item = SubjectAttentionOut(
                kind="knowledge_gap",
                title=g.title,
                detail=f"错题 {g.stats.total_wrong} 次",
                unit_id=unit.unit_id,
                unit_title=unit.unit_title,
                grade=unit.grade,
                is_historical=unit.grade < grade_level,
            )
            if unit.grade == grade_level:
                current.append(item)
            elif unit.grade < grade_level:
                historical.append(item)

        merged = current + historical
        return merged[:8]

    def build(self, student_id: str) -> LearningDashboardOut:
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")

        ctx = self._ctx.get(student_id)
        grade_level = self._grade_level(student_id)
        display_name = resolve_student_display_name(
            student_id,
            self._cfg,
            ctx=ctx,
            memory_svc=self._memory,
            data_root=self._data_root,
        )
        all_attempts = self._load_all_attempts(student_id)
        gap_map = self._gaps.get(student_id)
        gaps_by_kp = {g.knowledge_point_id: g for g in gap_map.gaps}
        catalog_subjects = self._catalog.list_subjects()

        attempts_by_unit: dict[str, list] = defaultdict(list)
        for att in all_attempts:
            try:
                u = self._catalog.get_unit(att.unit_id)
            except KeyError:
                continue
            if u.grade == grade_level:
                attempts_by_unit[att.unit_id].append(att)

        subject_cards: list[SubjectCardOut] = []
        for subject in catalog_subjects:
            grade_units = self._catalog.list_units(
                grade_level=grade_level, subject=subject, exact_grade=True
            )
            subject_attempts = []
            for att in all_attempts:
                try:
                    u = self._catalog.get_unit(att.unit_id)
                except KeyError:
                    continue
                if u.subject == subject and u.grade == grade_level:
                    subject_attempts.append(att)

            unit_rows = [
                self._unit_progress(
                    unit,
                    gaps_by_kp=gaps_by_kp,
                    unit_attempts=attempts_by_unit.get(unit.unit_id, []),
                )
                for unit in grade_units
            ]

            kp_total = sum(u.kp_total for u in unit_rows)
            kp_mastered = sum(u.kp_mastered for u in unit_rows)
            kp_weak = sum(u.kp_weak for u in unit_rows)
            attempts_total = len(subject_attempts)
            correct_rate = None
            if subject_attempts:
                correct_rate = round(
                    sum(1 for a in subject_attempts if a.correct) / len(subject_attempts), 3
                )

            historical_weak = sum(
                1
                for g in gap_map.gaps
                if g.status in (GapStatus.active, GapStatus.improving)
                and (u := self._unit_for_gap(g)) is not None
                and u.subject == subject
                and u.grade < grade_level
            )

            attention = self._subject_attention(
                subject=subject,
                grade_level=grade_level,
                gap_map=gap_map,
                all_attempts=all_attempts,
            )

            subject_cards.append(
                SubjectCardOut(
                    subject=subject,
                    grade_level=grade_level,
                    units_total=len(grade_units),
                    units_with_practice=sum(1 for u in unit_rows if u.attempts > 0),
                    attempts_total=attempts_total,
                    correct_rate=correct_rate,
                    kp_total=kp_total,
                    kp_mastered=kp_mastered,
                    kp_weak=kp_weak,
                    historical_weak_count=historical_weak,
                    summary=self._subject_summary(
                        subject=subject,
                        units=unit_rows,
                        weak_kp=kp_weak,
                        attempts_total=attempts_total,
                        correct_rate=correct_rate,
                    ),
                    units=unit_rows,
                    attention_items=attention,
                )
            )

        return LearningDashboardOut(
            student_id=student_id,
            display_name=display_name,
            grade=ctx.curriculum.grade,
            grade_level=grade_level,
            subjects=subject_cards,
            catalog_subjects=catalog_subjects,
        )
