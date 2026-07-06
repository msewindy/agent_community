"""学情统一视图：知识点掌握档 + 尚未归类的题（S-C）。

待归类不是独立「收件箱」产品概念，而是学情的一部分——家长在同一页查看与处理。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from agent_platform.learning.contracts import GapEntry
from agent_platform.learning.gap_map import GapMapService
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.photo_triage import PhotoTriageService, TriageEntry
from agent_platform.learning.question_inbox import QuestionInboxEntry, QuestionInboxService


class LearningProfileOut(BaseModel):
    student_id: str
    gaps: list[GapEntry] = Field(default_factory=list)
    pending_items: list[TriageEntry] = Field(
        default_factory=list,
        description="拍照后尚未归类的题",
    )
    pending_questions: list[QuestionInboxEntry] = Field(
        default_factory=list,
        description="课本/批量上传待审习题（补答案后导入题库）",
    )
    kp_choices: list[dict] = Field(
        default_factory=list,
        description="家长归类时可选的 KP 列表（闭集）",
    )


class LearningProfileService:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        gap_svc: Optional[GapMapService] = None,
        triage_svc: Optional[PhotoTriageService] = None,
        question_inbox_svc: Optional[QuestionInboxService] = None,
        catalog: Optional[KpCatalogService] = None,
    ) -> None:
        self._gap = gap_svc or GapMapService(data_root=data_root)
        self._triage = triage_svc or PhotoTriageService(data_root=data_root)
        self._question_inbox = question_inbox_svc or QuestionInboxService(data_root=data_root)
        self._catalog = catalog or KpCatalogService()

    def get_profile(
        self,
        student_id: str,
        *,
        gap_limit: int = 50,
        unit_id: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[int] = None,
        include_pending: bool = True,
    ) -> LearningProfileOut:
        gap_map = self._gap.get(student_id)
        gaps = sorted(gap_map.gaps, key=lambda g: (-g.stats.total_wrong, g.gap_id))
        kp_index = self._catalog.kp_index()

        if unit_id:
            unit = self._catalog.get_unit(unit_id)
            kp_ids = {kp.knowledge_point_id for kp in unit.knowledge_points}
            gaps = [g for g in gaps if g.knowledge_point_id in kp_ids]
        else:
            if subject or grade is not None:
                filtered: list = []
                for g in gaps:
                    u = kp_index.get(g.knowledge_point_id)
                    if u is None:
                        continue
                    if subject and u.subject != subject:
                        continue
                    if grade is not None and u.grade != grade:
                        continue
                    filtered.append(g)
                gaps = filtered

        gaps = gaps[:gap_limit]
        pending = self._triage.inbox_list(student_id, status="pending") if include_pending else []
        pending_questions = (
            self._question_inbox.list_pending() if include_pending else []
        )
        cands = self._triage.candidates(student_id)
        kp_choices = [
            {"kp_id": c.kp_id, "title": c.title, "subject": c.subject}
            for c in cands
        ]
        return LearningProfileOut(
            student_id=student_id,
            gaps=gaps,
            pending_items=pending,
            pending_questions=pending_questions,
            kp_choices=kp_choices,
        )
