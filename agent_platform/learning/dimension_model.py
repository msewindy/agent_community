"""Multi-dimension learning diagnosis v1 (P0)."""

from __future__ import annotations

from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import AttemptRecord, DimensionScore, GapMap


class DimensionModelService:
    def __init__(self, config: Optional[dict] = None) -> None:
        self._cfg = config or load_student_learning_config()

    def score_from_attempts(
        self,
        attempts: list[AttemptRecord],
        gap_map: Optional[GapMap] = None,
    ) -> list[DimensionScore]:
        dims = self._cfg.get("learning_dimensions") or []
        wrong = [a for a in attempts if not a.correct]
        results: list[DimensionScore] = []

        for dim in dims:
            dim_id = str(dim["id"])
            title = str(dim["title"])
            codes = set(dim.get("signal_error_codes") or [])
            tags = set(dim.get("behavior_tags") or [])
            hits = 0
            for att in wrong:
                if att.error_code and att.error_code in codes:
                    hits += 1
            if gap_map and tags:
                tax = self._cfg.get("error_taxonomy") or {}
                for code, meta in (tax.get("codes") or {}).items():
                    code_tags = set(meta.get("behavior_tags") or [])
                    if tags & code_tags:
                        for g in gap_map.gaps:
                            # 知识点主轴后，错因落在 error_breakdown；兼容旧 error_code 字段
                            if code in (g.error_breakdown or {}) or g.error_code == code:
                                hits += g.stats.wrong_7d
            total_signals = max(len(wrong), 1)
            score = min(1.0, hits / total_signals)
            results.append(
                DimensionScore(
                    dimension_id=dim_id,
                    title=title,
                    score=round(score, 2),
                    signal_count=hits,
                )
            )
        return sorted(results, key=lambda d: d.score, reverse=True)

    def top_dimensions(self, scores: list[DimensionScore], limit: int = 2) -> list[DimensionScore]:
        weak = [s for s in scores if s.signal_count > 0]
        return weak[:limit] if weak else scores[:limit]
