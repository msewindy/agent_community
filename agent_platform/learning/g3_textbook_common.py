"""Shared types and helpers for G3 textbook PDF ingest (math / chinese / english)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from agent_platform.learning.contracts import AnswerType

# Re-export for classroom_activities compatibility
from agent_platform.learning.hujiao_g3_english_parser import ExtractedExercise  # noqa: F401

AUTO_IMPORT_CONFIDENCE = 0.85

_RE_CJK = re.compile(r"[\u4e00-\u9fff]")
_RE_MATH_EXPR = re.compile(
    r"^[\d\s+\-×÷*/()（）]+[=？?]?$",
)
_RE_CALC_ASSIGN = re.compile(
    r"^(.+?)\s*=\s*([+-]?\d+(?:\.\d+)?)\s*$",
)
_RE_CN_NUM = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def cn_unit_num(label: str) -> Optional[int]:
    label = label.strip()
    if label.isdigit():
        n = int(label)
        return n if 1 <= n <= 12 else None
    if len(label) == 1 and label in _RE_CN_NUM:
        return _RE_CN_NUM[label]
    if label == "十":
        return 10
    m = re.match(r"十([一二三四五六七八九])", label)
    if m:
        return 10 + _RE_CN_NUM[m.group(1)]
    return None


def unit_id_for(subject: str, grade: int, unit_num: int) -> str:
    subj = subject.strip().lower()
    if subject == "英语":
        return f"english-g{grade}-u{unit_num:02d}"
    if subject == "数学":
        return f"math-g{grade}-u{unit_num:02d}"
    if subject == "语文":
        return f"chinese-g{grade}-u{unit_num:02d}"
    raise ValueError(f"unsupported subject: {subject!r}")


def kp_id_for(subject: str, grade: int, unit_num: int, slug: str) -> str:
    prefix = {"英语": "en", "数学": "math", "语文": "zh"}.get(subject)
    if not prefix:
        raise ValueError(subject)
    return f"kp-{prefix}-g{grade}-u{unit_num:02d}-{slug}"


def normalize_math_expr(expr: str) -> str:
    s = expr.strip()
    s = s.replace("×", "×").replace("÷", "÷")
    s = re.sub(r"\s+", " ", s)
    return s


def eval_simple_math(expr: str) -> Optional[float]:
    """Safely evaluate elementary arithmetic (digits + + - * / × ÷ parentheses)."""
    s = expr.strip()
    s = s.replace("×", "*").replace("÷", "/").replace("（", "(").replace("）", ")")
    s = re.sub(r"[^\d+\-*/().\s]", "", s)
    if not s or not re.search(r"\d", s):
        return None
    if not re.fullmatch(r"[\d+\-*/().\s]+", s):
        return None
    try:
        # pylint: disable=eval-used
        val = eval(s, {"__builtins__": {}}, {})  # noqa: S307
    except Exception:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    return None


@dataclass
class UnitPageRange:
    unit_num: int
    start_page: int  # 0-based index in fitz
    end_page: int


@dataclass
class ParsedLesson:
    index: int
    title: str
    page: int


@dataclass
class ParsedChineseUnit:
    unit_num: int
    unit_id: str
    unit_title: str
    theme: str
    lessons: list[ParsedLesson] = field(default_factory=list)
    oral_topic: str = ""
    writing_topic: str = ""
    intro_text: str = ""


def pending_exercises(exercises: list) -> list:
    from agent_platform.learning.hujiao_g3_english_parser import pending_exercises as _pe

    return _pe(exercises)
