"""Parent-facing weekly learning report (P0)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import (
    GapStatus,
    ParentReportEvidence,
    ParentWeeklyReport,
    utc_now,
)
from agent_platform.learning.dimension_model import DimensionModelService
from agent_platform.learning.gap_map import GapMapService
from agent_platform.learning.kpi_report import LearningKpiService
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
    ) -> None:
        self._cfg = load_student_learning_config()
        self._data_root = data_root
        self._ctx = context_svc or StudentContextService(data_root=data_root)
        self._gaps = gap_svc or GapMapService(data_root=data_root)
        self._kpi = kpi_svc or LearningKpiService(data_root=data_root)
        self._dims = dimension_svc or DimensionModelService()

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

    def build_weekly_report(self, student_id: str, period_days: Optional[int] = None) -> ParentWeeklyReport:
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")

        rep_cfg = self._cfg.get("parent_report") or {}
        period_days = period_days or int(rep_cfg.get("default_period_days", 7))
        ctx = self._ctx.get(student_id)
        gap_map = self._gaps.get(student_id)
        attempts = self._load_attempts(student_id, period_days)
        kpi = self._kpi.build_report(student_id, period_days=period_days)
        dim_scores = self._dims.score_from_attempts(attempts, gap_map=gap_map)
        top_dims = self._dims.top_dimensions(dim_scores, limit=2)

        mastered = [g for g in gap_map.gaps if g.status == GapStatus.mastered]
        active = [g for g in gap_map.gaps if g.status in (GapStatus.active, GapStatus.improving)]

        knowledge_highlights: list[str] = []
        if mastered:
            knowledge_highlights.append(f"已掌握：{', '.join(g.title for g in mastered[:3])}")
        if active:
            knowledge_highlights.append(f"正在加强：{', '.join(g.title for g in active[:3])}")
        if not knowledge_highlights:
            knowledge_highlights.append("本周刚开始练习，继续加油。")

        behavior_notes: list[str] = []
        careless = next((d for d in dim_scores if d.dimension_id == "carelessness" and d.signal_count > 0), None)
        if careless:
            behavior_notes.append(f"粗心/计算失误信号 {careless.signal_count} 次，建议做完验算一遍。")
        reading = next((d for d in dim_scores if d.dimension_id == "reading_care" and d.signal_count > 0), None)
        if reading:
            behavior_notes.append("审题需要多留意题目里的数字和问法。")
        if not behavior_notes:
            behavior_notes.append("暂未发现明显行为习惯问题，保持当前节奏即可。")

        next_steps: list[str] = []
        if active:
            next_steps.append(f"优先练「{active[0].title}」相关题目 15～20 分钟。")
        if top_dims and top_dims[0].signal_count > 0:
            next_steps.append(f"加强「{top_dims[0].title}」维度练习。")
        next_steps.append("可在学习报告页查看具体错题证据。")

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

        rate_pct = f"{kpi.correct_rate * 100:.0f}%" if kpi.correct_rate is not None else "—"
        summary = (
            f"{ctx.curriculum.grade}{ctx.curriculum.subject}「{ctx.curriculum.unit_title}」"
            f"本周练习 {kpi.attempts_total} 次，正确率 {rate_pct}。"
        )

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
