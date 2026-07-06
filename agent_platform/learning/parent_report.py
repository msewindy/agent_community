"""Parent-facing weekly learning report (P0) — volume / evaluation / recommendations."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import (
    GapStatus,
    ParentReportEvidence,
    ParentWeeklyReport,
    ReportEvaluation,
    ReportRecommendation,
    ReportVolume,
    SubjectVolume,
    UnitPracticeSummary,
    utc_now,
)
from agent_platform.learning.dimension_model import DimensionModelService
from agent_platform.learning.gap_map import GapMapService
from agent_platform.learning.kpi_report import LearningKpiService
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.photo_triage import PhotoTriageService
from agent_platform.learning.store import layout_for, list_attempt_paths, load_attempt
from agent_platform.learning.student_context import StudentContextService


class ParentReportService:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        context_svc: Optional[StudentContextService] = None,
        gap_svc: Optional[GapMapService] = None,
        kpi_svc: Optional[LearningKpiService] = None,
        dimension_svc: Optional[DimensionModelService] = None,
        catalog: Optional[KpCatalogService] = None,
        triage_svc: Optional[PhotoTriageService] = None,
    ) -> None:
        self._cfg = load_student_learning_config()
        self._data_root = data_root
        self._ctx = context_svc or StudentContextService(data_root=data_root)
        self._gaps = gap_svc or GapMapService(data_root=data_root)
        self._kpi = kpi_svc or LearningKpiService(data_root=data_root)
        self._dims = dimension_svc or DimensionModelService()
        self._catalog = catalog or KpCatalogService()
        self._triage = triage_svc or PhotoTriageService(data_root=data_root)

    def _load_attempts(self, student_id: str, period_days: int):
        lay = layout_for(student_id, self._data_root)
        cutoff = utc_now() - timedelta(days=period_days)
        out = []
        for path in list_attempt_paths(lay.attempts_dir):
            att = load_attempt(path)
            if att.submitted_at >= cutoff:
                out.append(att)
        out.sort(key=lambda a: a.submitted_at)
        return out

    def _grade_level(self, student_id: str) -> int:
        ctx = self._ctx.get(student_id)
        if ctx.curriculum.grade_level is not None:
            return int(ctx.curriculum.grade_level)
        return self._catalog.resolve_grade_level(ctx.curriculum.grade)

    def build_weekly_report(self, student_id: str, period_days: Optional[int] = None) -> ParentWeeklyReport:
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")

        rep_cfg = self._cfg.get("parent_report") or {}
        period_days = period_days or int(rep_cfg.get("default_period_days", 7))
        ctx = self._ctx.get(student_id)
        grade_level = self._grade_level(student_id)
        gap_map = self._gaps.get(student_id)
        attempts = self._load_attempts(student_id, period_days)
        kpi = self._kpi.build_report(student_id, period_days=period_days)
        dim_scores = self._dims.score_from_attempts(attempts, gap_map=gap_map)
        top_dims = self._dims.top_dimensions(dim_scores, limit=2)
        pending_count = len(self._triage.inbox_list(student_id, status="pending"))

        active_days = len({a.submitted_at.date() for a in attempts})
        by_subject_map: dict[str, list] = defaultdict(list)
        unit_attempts: dict[str, list] = defaultdict(list)
        for att in attempts:
            try:
                unit = self._catalog.get_unit(att.unit_id)
            except KeyError:
                continue
            by_subject_map[unit.subject].append(att)
            if unit.grade == grade_level:
                unit_attempts[att.unit_id].append(att)

        by_subject = []
        for subject in self._catalog.list_subjects():
            rows = by_subject_map.get(subject, [])
            rate = None
            if rows:
                rate = round(sum(1 for a in rows if a.correct) / len(rows), 3)
            by_subject.append(
                SubjectVolume(subject=subject, attempts=len(rows), correct_rate=rate)
            )

        units_practiced: list[UnitPracticeSummary] = []
        for unit_id, rows in sorted(unit_attempts.items(), key=lambda x: -len(x[1])):
            unit = self._catalog.get_unit(unit_id)
            rate = round(sum(1 for a in rows if a.correct) / len(rows), 3) if rows else None
            units_practiced.append(
                UnitPracticeSummary(
                    unit_id=unit.unit_id,
                    unit_title=unit.unit_title,
                    subject=unit.subject,
                    grade=unit.grade,
                    attempts=len(rows),
                    correct_rate=rate,
                )
            )

        mastered = [g for g in gap_map.gaps if g.status == GapStatus.mastered]
        active = [g for g in gap_map.gaps if g.status in (GapStatus.active, GapStatus.improving)]
        mastered_period = sum(1 for g in mastered if g.mastery.mastered_at and g.mastery.mastered_at >= utc_now() - timedelta(days=period_days))

        volume = ReportVolume(
            attempts_total=len(attempts),
            active_days=active_days,
            correct_rate=kpi.correct_rate,
            by_subject=by_subject,
            units_practiced=units_practiced,
            gaps_mastered_period=mastered_period,
            gaps_active=len(active),
        )

        mastered_labels = [g.title for g in mastered[:3]]
        needs_work = [f"{g.title}（错 {g.stats.total_wrong} 次）" for g in active[:3]]

        behavior_notes: list[str] = []
        careless = next((d for d in dim_scores if d.dimension_id == "carelessness" and d.signal_count > 0), None)
        if careless:
            behavior_notes.append(
                f"粗心/计算失误信号 {careless.signal_count} 次，建议做完验算一遍。"
            )
        reading = next((d for d in dim_scores if d.dimension_id == "reading_care" and d.signal_count > 0), None)
        if reading:
            behavior_notes.append("审题需要多留意题目里的数字和问法。")
        logic = next((d for d in dim_scores if d.dimension_id == "logic_reasoning" and d.signal_count > 0), None)
        if logic:
            behavior_notes.append(f"逻辑推理相关失误 {logic.signal_count} 次，建议画图或分步列式。")
        if not behavior_notes:
            behavior_notes.append("本周未发现明显行为习惯问题，保持当前节奏即可。")

        rate_pct = f"{kpi.correct_rate * 100:.0f}%" if kpi.correct_rate is not None else "—"
        subject_bits = " · ".join(
            f"{s.subject} {s.attempts}次"
            + (f"/{s.correct_rate * 100:.0f}%" if s.correct_rate is not None else "")
            for s in by_subject
            if s.attempts > 0
        )
        headline = (
            f"本周共练习 {volume.attempts_total} 次（活跃 {active_days} 天），"
            f"总正确率 {rate_pct}。"
        )
        if subject_bits:
            headline += f" 分学科：{subject_bits}。"
        if active:
            headline += f" 主要薄弱：{active[0].title}。"
        if top_dims and top_dims[0].signal_count > 0:
            headline += f" {top_dims[0].title}需留意。"

        evaluation = ReportEvaluation(
            headline=headline,
            mastered=mastered_labels,
            needs_work=needs_work,
            dimension_scores=dim_scores,
            behavior_notes=behavior_notes,
        )

        knowledge_highlights: list[str] = []
        if mastered_labels:
            knowledge_highlights.append(f"已掌握：{', '.join(mastered_labels)}")
        if needs_work:
            knowledge_highlights.append(f"正在加强：{', '.join(needs_work)}")
        if not knowledge_highlights:
            knowledge_highlights.append("本周刚开始练习，继续加油。")

        recommendations: list[ReportRecommendation] = []
        if active:
            recommendations.append(
                ReportRecommendation(
                    text=f"优先巩固「{active[0].title}」相关题目 15～20 分钟。",
                    basis="gap",
                )
            )
        if top_dims and top_dims[0].signal_count > 0:
            recommendations.append(
                ReportRecommendation(
                    text=f"加强「{top_dims[0].title}」：{behavior_notes[0] if behavior_notes else ''}",
                    basis="dimension",
                )
            )
        if pending_count:
            recommendations.append(
                ReportRecommendation(
                    text=f"处理 {pending_count} 道待归类拍照题。",
                    basis="inbox",
                )
            )
        if ctx.curriculum.unit_title:
            recommendations.append(
                ReportRecommendation(
                    text=f"可让孩子对 Jarvis 说「练几道{ctx.curriculum.unit_title}」。",
                    basis="unit",
                )
            )
        recommendations.append(
            ReportRecommendation(text="在学情详情查看具体知识点与错题分布。", basis="nav")
        )

        next_steps = [r.text for r in recommendations]

        evidence: list[ParentReportEvidence] = []
        for g in active[:2]:
            if g.evidence_attempt_ids:
                evidence.append(
                    ParentReportEvidence(
                        label=f"漏洞：{g.title}",
                        gap_id=g.gap_id,
                        attempt_id=g.evidence_attempt_ids[0],
                    )
                )

        summary = headline

        return ParentWeeklyReport(
            student_id=student_id,
            period_days=period_days,
            generated_at=utc_now(),
            grade=ctx.curriculum.grade,
            subject=ctx.curriculum.subject,
            unit_title=ctx.curriculum.unit_title,
            summary=summary,
            knowledge_highlights=knowledge_highlights,
            dimension_scores=dim_scores,
            behavior_notes=behavior_notes,
            next_steps=next_steps,
            evidence=evidence,
            attempts_total=kpi.attempts_total,
            correct_rate=kpi.correct_rate,
            volume=volume,
            evaluation=evaluation,
            recommendations=recommendations,
        )

    def save_report(self, report: ParentWeeklyReport) -> Path:
        lay = layout_for(report.student_id, self._data_root)
        lay.parent_reports_dir.mkdir(parents=True, exist_ok=True)
        ts = report.generated_at.strftime("%Y%m%d")
        path = lay.parent_reports_dir / f"parent-weekly-{ts}.json"
        import json

        path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path
