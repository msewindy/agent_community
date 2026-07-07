"""Parse 部编版三年级语文上册 PDF → KP draft + classroom activities."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import fitz

from agent_platform.learning.contracts import AnswerType
from agent_platform.learning.g3_textbook_common import (
    AUTO_IMPORT_CONFIDENCE,
    ExtractedExercise,
    ParsedChineseUnit,
    ParsedLesson,
    cn_unit_num,
    kp_id_for,
    unit_id_for,
)
from agent_platform.learning.kp_document_parser import (
    KpDocumentDraft,
    KpDocumentKp,
    KpDocumentQuestion,
    KpDocumentUnit,
)

TEXTBOOK_REF = "部编版·三年级语文上册"
SUBJECT = "语文"
GRADE = 3

# Unit themes (2024 上册) — aligned with目录
CHINESE_UNIT_THEMES: dict[int, str] = {
    1: "美丽的校园",
    2: "金秋时节",
    3: "预测",
    4: "观察",
    5: "祖国的山河",
    6: "自然奇观",
    7: "童话世界",
    8: "智慧火花",
}

_KP_SLUGS = [
    ("char", "识字与写字", "本单元要求认读、书写的生字与词语。"),
    ("vocab", "词语积累", "新鲜感的词语、成语与近反义词。"),
    ("reading", "课文阅读理解", "理解课文内容、写法与朗读要求。"),
    ("oral", "口语交际", "围绕单元主题的口头表达。"),
    ("writing", "习作", "单元习作要求与写法。"),
    ("garden", "语文园地", "识字加油站、词句段运用与积累。"),
]

_MANUAL_ZH = re.compile(
    r"(朗读课文|背诵|口语交际|习作|写一写|读一读|想一想|说一说|抄写下来|观察|续写|猜一猜|默读)",
)
_RE_UNIT_HEAD = re.compile(r"第\s*([一二三四五六七八])\s*单\s*元")
_RE_LESSON = re.compile(r"^(\d+)\s+(.+?)\.{2,}")
_RE_ORAL = re.compile(r"口语交际\s*\n\s*(.+?)(?:\.{2,}|\n)")
_RE_WRITING = re.compile(r"习作\s*\n\s*(.+?)(?:\.{2,}|\n)")


def _default_pdf_path() -> Path:
    from agent_platform.learning._config import repo_root

    base = repo_root() / "三年级课本"
    for p in base.glob("*.pdf"):
        if "语文" in p.name:
            return p
    raise FileNotFoundError("chinese textbook PDF not found under 三年级课本/")


def _parse_toc(doc: fitz.Document) -> list[ParsedChineseUnit]:
    toc_text = ""
    for i in range(3, min(7, doc.page_count)):
        toc_text += doc[i].get_text() + "\n"

    units: dict[int, ParsedChineseUnit] = {}
    current: Optional[int] = None
    for line in toc_text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        um = _RE_UNIT_HEAD.search(ln)
        if um:
            num = cn_unit_num(um.group(1))
            if num and 1 <= num <= 8:
                current = num
                theme = CHINESE_UNIT_THEMES.get(num, f"第{num}单元")
                units[num] = ParsedChineseUnit(
                    unit_num=num,
                    unit_id=unit_id_for(SUBJECT, GRADE, num),
                    unit_title=theme,
                    theme=theme,
                )
            continue
        if current is None:
            continue
        lm = _RE_LESSON.match(ln)
        if lm:
            title = lm.group(2).strip().strip(".")
            if len(title) >= 2 and "语文园地" not in title:
                units[current].lessons.append(
                    ParsedLesson(index=int(lm.group(1)), title=title, page=0)
                )
        if "口语交际" in ln:
            m = re.search(r"口语交际\s*(.+?)\.{2,}", ln)
            if m:
                units[current].oral_topic = m.group(1).strip()
        if ln.startswith("习作") or "习作" in ln and "例文" not in ln:
            m = re.search(r"习作\s*(.+?)\.{2,}", ln)
            if m:
                units[current].writing_topic = m.group(1).strip()

    # fill missing units from themes
    for num in range(1, 9):
        if num not in units:
            theme = CHINESE_UNIT_THEMES[num]
            units[num] = ParsedChineseUnit(
                unit_num=num,
                unit_id=unit_id_for(SUBJECT, GRADE, num),
                unit_title=theme,
                theme=theme,
            )
    return [units[n] for n in sorted(units)]


def _unit_page_ranges(doc: fitz.Document, units: list[ParsedChineseUnit]) -> dict[int, tuple[int, int]]:
    starts: dict[int, int] = {}
    for i in range(doc.page_count):
        text = doc[i].get_text()
        m = _RE_UNIT_HEAD.search(text.replace("\n", ""))
        if m:
            num = cn_unit_num(m.group(1))
            if num and num not in starts:
                starts[num] = i
    ordered = sorted(starts.items())
    ranges: dict[int, tuple[int, int]] = {}
    for idx, (num, start) in enumerate(ordered):
        end = ordered[idx + 1][1] - 1 if idx + 1 < len(ordered) else doc.page_count - 1
        ranges[num] = (start, end)
    if len(ranges) < 8:
        chunk = max(1, (doc.page_count - 6) // 8)
        for num in range(1, 9):
            ranges[num] = (5 + (num - 1) * chunk, min(doc.page_count - 1, 5 + num * chunk - 1))
    return ranges


def _extract_intro(doc: fitz.Document, start: int) -> str:
    text = doc[start].get_text()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    parts = []
    for ln in lines[:12]:
        if _RE_UNIT_HEAD.search(ln.replace(" ", "")):
            continue
        if re.match(r"^[◎●○]", ln):
            parts.append(ln.lstrip("◎●○ \t"))
        elif len(ln) > 6 and not re.match(r"^\d+$", ln):
            parts.append(ln)
    return " ".join(parts[:4])


def _reading_description(unit: ParsedChineseUnit, intro: str) -> str:
    lines = [f"本单元主题：{unit.theme}。", ""]
    if intro:
        lines.append(intro)
        lines.append("")
    if unit.lessons:
        lines.append("课文篇目：")
        for les in unit.lessons:
            lines.append(f"- {les.title}")
    lines.append("")
    lines.append("阅读要求：朗读课文，把握主要内容，关注有新鲜感的词句。")
    return "\n".join(lines)


def _oral_description(unit: ParsedChineseUnit) -> str:
    topic = unit.oral_topic or "围绕单元主题进行口语表达"
    return f"口语交际：{topic}。请在课堂或与家长练习讲述，Jarvis 可对话陪练但不自动推题。"


def _writing_description(unit: ParsedChineseUnit) -> str:
    topic = unit.writing_topic or "完成本单元习作"
    return f"习作：{topic}。开放写作请在课堂完成，Jarvis 可给思路提示但不代替批改。"


def _char_description(unit: ParsedChineseUnit) -> str:
    lesson_titles = "、".join(l.title for l in unit.lessons[:3])
    return f"认读与书写本单元课文中出现的生字新词（涉及：{lesson_titles or unit.theme}）。"


def _vocab_description(unit: ParsedChineseUnit) -> str:
    return f"积累与运用本单元词语，关注有新鲜感的表达（主题：{unit.theme}）。"


def _garden_description(unit: ParsedChineseUnit) -> str:
    return "语文园地：识字加油站、词句段运用、书写提示与日积月累。"


def _extract_exercises(unit_num: int, page: int, text: str) -> list[ExtractedExercise]:
    out: list[ExtractedExercise] = []
    seen: set[str] = set()
    reading_kp = kp_id_for(SUBJECT, GRADE, unit_num, "reading")
    for m in _MANUAL_ZH.finditer(text):
        et = m.group(1)
        if et in seen:
            continue
        seen.add(et)
        out.append(
            ExtractedExercise(
                unit_num=unit_num,
                page=page + 1,
                exercise_type=et,
                stem=f"【课堂活动】课本第 {page + 1} 页 · {et}",
                expected_answer="",
                explanation="朗读/习作/观察类活动，请在课堂完成。",
                knowledge_point_id=reading_kp,
                default_error_code="READING_ERROR",
                confidence=0.3,
                review_reason="语文开放/朗读/习作活动，Jarvis 不推题",
            )
        )
    return out


def parse_textbook(path: Path) -> tuple[list[ParsedChineseUnit], list[ExtractedExercise]]:
    doc = fitz.open(path)
    units = _parse_toc(doc)
    ranges = _unit_page_ranges(doc, units)
    by_num = {u.unit_num: u for u in units}
    exercises: list[ExtractedExercise] = []
    seen_act: set[tuple[int, str]] = set()

    for num, (start, end) in ranges.items():
        unit = by_num[num]
        unit.intro_text = _extract_intro(doc, start)
        for page_idx in range(start, min(end + 1, doc.page_count)):
            text = doc[page_idx].get_text()
            for ex in _extract_exercises(num, page_idx, text):
                key = (num, ex.exercise_type)
                if key in seen_act:
                    continue
                seen_act.add(key)
                exercises.append(ex)

    doc.close()
    return units, exercises


def build_kp_document(
    textbook_path: Path,
    *,
    include_questions: bool = True,
) -> tuple[KpDocumentDraft, list[ExtractedExercise]]:
    units, exercises = parse_textbook(textbook_path) if include_questions else ([], [])
    if not units:
        doc = fitz.open(textbook_path)
        units = _parse_toc(doc)
        doc.close()

    doc_units: list[KpDocumentUnit] = []
    for unit in units:
        intro = unit.intro_text
        kps = [
            KpDocumentKp(
                knowledge_point_id=kp_id_for(SUBJECT, GRADE, unit.unit_num, slug),
                title=title,
                description={
                    "char": _char_description(unit),
                    "vocab": _vocab_description(unit),
                    "reading": _reading_description(unit, intro),
                    "oral": _oral_description(unit),
                    "writing": _writing_description(unit),
                    "garden": _garden_description(unit),
                }[slug],
            )
            for slug, title, _ in _KP_SLUGS
        ]
        doc_units.append(
            KpDocumentUnit(
                unit_id=unit.unit_id,
                unit_title=unit.unit_title,
                textbook_chapter=f"第{unit.unit_num}单元",
                unit_description=f"第{unit.unit_num}单元 · {unit.theme}",
                knowledge_points=kps,
                questions=[],
            )
        )

    draft = KpDocumentDraft(
        subject=SUBJECT,
        grade=GRADE,
        textbook_ref=TEXTBOOK_REF,
        document_note="由部编版三年级语文上册 PDF 自动解析生成",
        units=doc_units,
        source_path=str(textbook_path),
    )
    return draft, exercises
