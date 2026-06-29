"""Off-topic detection + redirect (P0)."""

from __future__ import annotations

import re
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import SafetyCheckResult


class StudentSafetyService:
    def __init__(self, config: Optional[dict] = None) -> None:
        cfg = config or load_student_learning_config()
        self._cfg = cfg.get("student_safety") or {}
        patterns = self._cfg.get("off_topic_patterns") or []
        self._patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self._template = str(
            self._cfg.get(
                "redirect_template",
                "这个我没办法帮你。{empathy}我们继续学{subject}吧，要练几题还是看本周学习报告？",
            )
        )

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("enabled", True))

    def check_user_message(self, text: str, subject: str = "语文或数学") -> SafetyCheckResult:
        if not self.enabled:
            return SafetyCheckResult(allowed=True, reason_code="disabled")
        normalized = text.strip()
        if not normalized:
            return SafetyCheckResult(allowed=True, reason_code="empty")
        for pattern in self._patterns:
            if pattern.search(normalized):
                empathy = "我理解你的想法。"
                message = self._template.format(empathy=empathy, subject=subject)
                return SafetyCheckResult(
                    allowed=False,
                    reason_code="off_topic",
                    redirect_message=message,
                )
        return SafetyCheckResult(allowed=True, reason_code="ok")
