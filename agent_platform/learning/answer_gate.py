"""Education AnswerGate — gap/attempt evidence required (Phase 5)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent_platform.learning.contracts import GapEntry
from agent_platform.learning.prompts import guiding_fallback

_GAP_ID_RE = re.compile(r"gap-[a-z0-9-]+")
_ATT_ID_RE = re.compile(r"att-\d{8}-\d{4}-[a-f0-9]{6}")

_CLAIM_PATTERNS: list[tuple[str, str]] = [
    (r"反复", "repeated_error_claim"),
    (r"经常.{0,8}错", "repeated_error_claim"),
    (r"总是.{0,8}错", "repeated_error_claim"),
    (r"薄弱", "gap_claim"),
    (r"漏洞", "gap_claim"),
    (r"错因", "gap_claim"),
    (r"已(?:经)?掌握", "mastery_claim"),
    (r"常犯", "repeated_error_claim"),
]


@dataclass
class AnswerGateResult:
    passed: bool
    text: str
    violations: list[str] = field(default_factory=list)
    rewritten: bool = False


class StudentAnswerGate:
    def check(self, text: str, gaps: list[GapEntry] | None = None) -> AnswerGateResult:
        text = (text or "").strip()
        if not text:
            return AnswerGateResult(passed=True, text=text)

        gaps = gaps or []
        gap_ids = {g.gap_id for g in gaps}
        violations: list[str] = []
        has_claim = False
        for pattern, label in _CLAIM_PATTERNS:
            if re.search(pattern, text):
                has_claim = True
                if label not in violations:
                    violations.append(label)

        if not has_claim:
            return AnswerGateResult(passed=True, text=text)

        mentioned_gaps = _GAP_ID_RE.findall(text)
        has_attempt = bool(_ATT_ID_RE.search(text))

        if mentioned_gaps:
            unknown = [g for g in mentioned_gaps if g not in gap_ids]
            if unknown and gaps:
                return AnswerGateResult(
                    passed=False,
                    text=guiding_fallback(),
                    violations=violations + ["unknown_gap_id"],
                    rewritten=True,
                )
            if gaps or has_attempt:
                return AnswerGateResult(passed=True, text=text, violations=[])

        if has_attempt and gaps:
            return AnswerGateResult(passed=True, text=text)

        if not gaps:
            return AnswerGateResult(
                passed=False,
                text=guiding_fallback(),
                violations=violations,
                rewritten=True,
            )

        if not mentioned_gaps and not has_attempt:
            return AnswerGateResult(
                passed=False,
                text=guiding_fallback(),
                violations=violations,
                rewritten=True,
            )

        return AnswerGateResult(passed=True, text=text)
