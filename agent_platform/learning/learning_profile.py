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


class LearningProfileOut(BaseModel):
    student_id: str
    gaps: list[GapEntry] = Field(default_factory=list)
    pending_items: list[TriageEntry] = Field(
        default_factory=list,
        description="尚未归类的题（学情的一部分，非独立收件箱）",
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
        catalog: Optional[KpCatalogService] = None,
    ) -> None:
        self._gap = gap_svc or GapMapService(data_root=data_root)
        self._triage = triage_svc or PhotoTriageService(data_root=data_root)
        self._catalog = catalog or KpCatalogService()

    def get_profile(self, student_id: str, *, gap_limit: int = 50) -> LearningProfileOut:
        gap_map = self._gap.get(student_id)
        gaps = sorted(gap_map.gaps, key=lambda g: (-g.stats.total_wrong, g.gap_id))[:gap_limit]
        pending = self._triage.inbox_list(student_id, status="pending")
        cands = self._triage.candidates(student_id)
        kp_choices = [
            {"kp_id": c.kp_id, "title": c.title, "subject": c.subject}
            for c in cands
        ]
        return LearningProfileOut(
            student_id=student_id,
            gaps=gaps,
            pending_items=pending,
            kp_choices=kp_choices,
        )
