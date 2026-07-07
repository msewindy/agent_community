"""Parse 沪教版三年级数学上册 PDF → KP draft + exercises."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz

from agent_platform.learning.contracts import AnswerType
from agent_platform.learning.g3_textbook_common import (
    AUTO_IMPORT_CONFIDENCE,
    ExtractedExercise,
    eval_simple_math,
    kp_id_for,
    normalize_math_expr,
    unit_id_for,
)
from agent_platform.learning.kp_document_parser import (
    KpDocumentDraft,
    KpDocumentKp,
    KpDocumentQuestion,
    KpDocumentUnit,
)

TEXTBOOK_REF = "沪教版（五·四学制）·三年级数学上册"
SUBJECT = "数学"
GRADE = 3

# Curated unit metadata (TOC + teaching focus)
MATH_UNITS: dict[int, dict] = {
    1: {
        "title": "两步四则运算与应用题",
        "chapter": "第一单元",
        "kps": [
            ("mult-add", "乘加混合运算（先乘后加）", "算式中同时有乘法和加法时，先算乘法，再算加法。例：6+3×4 先算 3×4=12，得 18。"),
            ("mult-sub", "乘减混合运算（先乘后减）", "先算乘法，再算减法。例：20-3×4 先算 3×4=12，得 8。"),
            ("div-add", "除加混合运算（先除后加）", "先算除法，再算加法。例：18÷3+4 先算 18÷3=6，得 10。"),
            ("div-sub", "除减混合运算（先除后减）", "先算除法，再算减法。例：25-10÷5 先算 10÷5=2，得 23。"),
            ("same-level", "同级混合运算（从左到右）", "只有加减或只有乘除时，按从左到右顺序计算。"),
            ("parentheses", "小括号运算（先算括号内）", "有小括号时，先算括号里面的，再算括号外。"),
            ("word-problem", "混合运算应用题列式", "把两步情境写成综合算式并求解。"),
            ("expr-meaning", "综合算式情境含义", "结合情境解释算式各部分表示什么。"),
        ],
        "default_kp": "mult-add",
        "error": "PROCEDURE_ERROR",
    },
    2: {
        "title": "用一位数乘",
        "chapter": "第二单元",
        "kps": [
            ("mult-tens", "整十、整百数乘一位数", "如 3×200、400×2，先算基本乘法再补零。"),
            ("mult-2digit", "两位数乘一位数", "竖式计算，含不进位与进位。"),
            ("mult-3digit", "三位数乘一位数", "三位数乘一位数的竖式与估算。"),
            ("mult-word", "乘法应用题", "把情境写成乘法或连乘算式。"),
        ],
        "default_kp": "mult-2digit",
        "error": "CALCULATION_ERROR",
    },
    3: {
        "title": "三角形与四边形",
        "chapter": "第三单元",
        "kps": [
            ("triangle", "认识三角形", "三角形的边、角与稳定性。"),
            ("quadrilateral", "认识四边形", "长方形、正方形、梯形等。"),
            ("classify", "图形分类", "按角或边对三角形、四边形分类。"),
            ("properties", "图形特征", "辨认图形并描述特征。"),
        ],
        "default_kp": "triangle",
        "error": "READING_ERROR",
    },
    4: {
        "title": "用一位数除",
        "chapter": "第四单元",
        "kps": [
            ("div-tens", "整十、整百数除以一位数", "如 400÷5、240÷6。"),
            ("div-2digit", "两位数除以一位数", "竖式除法，含有余数。"),
            ("div-3digit", "三位数除以一位数", "三位数除以一位数的竖式。"),
            ("div-word", "除法应用题", "平均分与包含除的情境列式。"),
        ],
        "default_kp": "div-2digit",
        "error": "CALCULATION_ERROR",
    },
    5: {
        "title": "年、月、日的秘密",
        "chapter": "第五单元",
        "kps": [
            ("calendar", "年、月、日认识", "公历年月日、大小月。"),
            ("leap", "平年与闰年", "判断平年、闰年。"),
            ("duration", "时间计算", "经过天数、周年计算。"),
            ("date-problem", "日期应用题", "日程与间隔问题。"),
        ],
        "default_kp": "calendar",
        "error": "READING_ERROR",
    },
    6: {
        "title": "周长",
        "chapter": "第六单元",
        "kps": [
            ("perimeter-concept", "周长的认识", "封闭图形一周的长度。"),
            ("perimeter-rect", "长方形、正方形周长", "公式与计算。"),
            ("perimeter-calc", "周长计算", "已知边长求周长。"),
            ("perimeter-word", "周长应用题", "围边框、跑圈等情境。"),
        ],
        "default_kp": "perimeter-rect",
        "error": "PROCEDURE_ERROR",
    },
    7: {
        "title": "马拉松的路线设计",
        "chapter": "第七单元",
        "kps": [
            ("route", "路线与方向", "认识路线图、描述路线。"),
            ("distance", "路程问题", "分段路程与总路程。"),
            ("plan", "方案设计", "综合应用测量与计算。"),
        ],
        "default_kp": "route",
        "error": "READING_ERROR",
    },
    8: {
        "title": "数学广场",
        "chapter": "第八单元",
        "kps": [
            ("pattern", "规律与推理", "数形规律、简单推理。"),
            ("game", "数学游戏", "综合练习与游戏活动。"),
            ("review", "单元复习", "本学期计算与图形综合复习。"),
        ],
        "default_kp": "pattern",
        "error": "CALCULATION_ERROR",
    },
}

_MANUAL_MATH = re.compile(
    r"(想一想|探究|画一画|量一量|拼一拼|围一围|数学广场|路线设计|操作|观察图形|指一指)",
)
_RE_CALC_HOMEWORK = re.compile(
    r"^(\d+\s*[+\-×÷*/]\s*[\d+\-×÷*/()\s]+)\s*=\s*$",
)
_RE_CALC_INLINE = re.compile(
    r"^([\d+\-×÷*/()（）\s]{3,}?)\s*=\s*([+-]?\d+(?:\.\d+)?)\s*[喋。]?$",
)


@dataclass
class MathUnitRange:
    unit_num: int
    start: int
    end: int


def _default_pdf_path() -> Path:
    from agent_platform.learning._config import repo_root

    base = repo_root() / "三年级课本"
    for p in base.glob("*.pdf"):
        if "数学" in p.name and "沪" in p.name:
            return p
    hits = list(base.glob("*数学*.pdf"))
    if hits:
        return hits[0]
    raise FileNotFoundError("math textbook PDF not found under 三年级课本/")


def _parse_toc_page_ranges(doc: fitz.Document) -> list[MathUnitRange]:
    """Use printed TOC on pages 2-3 (0-based 1-2)."""
    text = doc[1].get_text() + "\n" + doc[2].get_text()
    # lines like: 两步四则运算与应用题 \n 1 \n 1 \n 12
    titles = list(MATH_UNITS.values())
    order = sorted(MATH_UNITS.keys())
    starts: dict[int, int] = {}
    for i, num in enumerate(order):
        title = MATH_UNITS[num]["title"]
        # find title then next number as start page (printed page)
        idx = text.find(title)
        if idx < 0:
            continue
        tail = text[idx : idx + 80]
        nums = [int(m.group(0)) for m in re.finditer(r"\b(\d{1,3})\b", tail)]
        # first small number after title often duplicate unit index; last is start page
        if nums:
            page_printed = nums[-1]
            starts[num] = max(0, page_printed - 1)

    ranges: list[MathUnitRange] = []
    ordered = sorted(starts.items(), key=lambda x: x[1])
    for i, (num, start) in enumerate(ordered):
        end = ordered[i + 1][1] - 1 if i + 1 < len(ordered) else doc.page_count - 1
        ranges.append(MathUnitRange(unit_num=num, start=start, end=end))
    if len(ranges) < 8:
        # fallback equal split after page 3
        chunk = max(1, (doc.page_count - 4) // 8)
        ranges = [
            MathUnitRange(unit_num=n, start=3 + (n - 1) * chunk, end=min(doc.page_count - 1, 3 + n * chunk - 1))
            for n in range(1, 9)
        ]
    return ranges


def _kp_map(unit_num: int) -> dict[str, str]:
    meta = MATH_UNITS[unit_num]
    return {slug: kp_id_for(SUBJECT, GRADE, unit_num, slug) for slug, _, _ in meta["kps"]}


def _classify_kp(unit_num: int, expr: str) -> tuple[str, str]:
    meta = MATH_UNITS[unit_num]
    kps = _kp_map(unit_num)
    e = expr.replace(" ", "")
    if unit_num == 1:
        if "(" in e or "（" in e:
            return kps["parentheses"], "PROCEDURE_ERROR"
        if re.search(r"[×*]", e) and "+" in e:
            return kps["mult-add"], "PROCEDURE_ERROR"
        if re.search(r"[×*]", e) and "-" in e:
            return kps["mult-sub"], "PROCEDURE_ERROR"
        if re.search(r"[÷/]", e) and "+" in e:
            return kps["div-add"], "PROCEDURE_ERROR"
        if re.search(r"[÷/]", e) and "-" in e:
            return kps["div-sub"], "PROCEDURE_ERROR"
        if re.search(r"[+\-]", e) and not re.search(r"[×÷*/]", e):
            return kps["same-level"], "PROCEDURE_ERROR"
    if unit_num == 2:
        return kps["mult-2digit"], meta["error"]
    if unit_num == 4:
        return kps["div-2digit"], meta["error"]
    slug = meta["default_kp"]
    return kps[slug], meta["error"]


def _extract_calculations(unit_num: int, page: int, text: str) -> list[ExtractedExercise]:
    out: list[ExtractedExercise] = []
    seen: set[str] = set()
    kps = _kp_map(unit_num)
    default_slug = MATH_UNITS[unit_num]["default_kp"]

    for line in text.splitlines():
        ln = line.strip()
        if not ln or len(ln) > 80:
            continue
        if _MANUAL_MATH.search(ln):
            continue

        m = _RE_CALC_INLINE.match(ln)
        if m:
            expr, ans = m.group(1), m.group(2)
            expr_n = normalize_math_expr(expr)
            key = expr_n + "=" + ans
            if key in seen:
                continue
            seen.add(key)
            ev = eval_simple_math(expr)
            if ev is not None and abs(ev - float(ans)) > 0.01:
                continue
            kp_id, err = _classify_kp(unit_num, expr_n)
            out.append(
                ExtractedExercise(
                    unit_num=unit_num,
                    page=page + 1,
                    exercise_type="calculation",
                    stem=f"计算：{expr_n} = ?",
                    expected_answer=str(int(float(ans))) if float(ans).is_integer() else str(ans),
                    explanation=f"课本 p{page + 1}：{expr_n} = {ans}",
                    knowledge_point_id=kp_id,
                    default_error_code=err,
                    answer_type=AnswerType.exact,
                    confidence=0.92,
                    source_snippet=ln,
                )
            )
            continue

        m2 = _RE_CALC_HOMEWORK.match(ln)
        if m2:
            expr_n = normalize_math_expr(m2.group(1))
            if expr_n in seen:
                continue
            ev = eval_simple_math(expr_n)
            if ev is None:
                continue
            ans = str(int(ev)) if ev.is_integer() else str(ev)
            seen.add(expr_n)
            kp_id, err = _classify_kp(unit_num, expr_n)
            out.append(
                ExtractedExercise(
                    unit_num=unit_num,
                    page=page + 1,
                    exercise_type="calculation",
                    stem=f"计算：{expr_n} = ?",
                    expected_answer=ans,
                    explanation=f"按运算顺序：{expr_n} = {ans}",
                    knowledge_point_id=kp_id,
                    default_error_code=err,
                    answer_type=AnswerType.exact,
                    confidence=0.88,
                    source_snippet=ln,
                )
            )
    return out


def _extract_manual(unit_num: int, page: int, text: str) -> list[ExtractedExercise]:
    out: list[ExtractedExercise] = []
    seen: set[str] = set()
    kps = _kp_map(unit_num)
    default_kp = kps[MATH_UNITS[unit_num]["default_kp"]]
    for m in _MANUAL_MATH.finditer(text):
        et = m.group(1)
        key = et
        if key in seen:
            continue
        seen.add(key)
        out.append(
            ExtractedExercise(
                unit_num=unit_num,
                page=page + 1,
                exercise_type=et,
                stem=f"【课堂活动】课本第 {page + 1} 页 · {et}",
                expected_answer="",
                explanation="图形/操作/探究类活动，请在课堂完成。",
                knowledge_point_id=default_kp,
                default_error_code=MATH_UNITS[unit_num]["error"],
                confidence=0.3,
                review_reason="多模态/操作题，Jarvis 不推题",
            )
        )
    if unit_num in (3, 6, 7, 8) and page == MATH_UNITS[unit_num].get("_start", 0):
        pass
    # unit 3/6/7 heavy on diagrams — one marker per page max
    if unit_num in (3, 6, 7) and re.search(r"(三角形|四边形|周长|路线|马拉松)", text):
        key = "diagram"
        if key not in seen and not out:
            out.append(
                ExtractedExercise(
                    unit_num=unit_num,
                    page=page + 1,
                    exercise_type="look_and_draw",
                    stem=f"【课堂活动】课本第 {page + 1} 页 · 图形/测量",
                    expected_answer="",
                    explanation="依赖插图或测量，请在课堂完成。",
                    knowledge_point_id=default_kp,
                    default_error_code="READING_ERROR",
                    confidence=0.3,
                    review_reason="图形式活动",
                )
            )
    return out


def parse_textbook_exercises(path: Path) -> list[ExtractedExercise]:
    doc = fitz.open(path)
    ranges = _parse_toc_page_ranges(doc)
    exercises: list[ExtractedExercise] = []
    seen_pending: set[tuple[int, str]] = set()
    for rng in ranges:
        for page_idx in range(rng.start, min(rng.end + 1, doc.page_count)):
            text = doc[page_idx].get_text()
            exercises.extend(_extract_calculations(rng.unit_num, page_idx, text))
            for pending in _extract_manual(rng.unit_num, page_idx, text):
                key = (rng.unit_num, pending.exercise_type)
                if key in seen_pending:
                    continue
                seen_pending.add(key)
                exercises.append(pending)
    doc.close()
    return exercises


def build_kp_document(
    textbook_path: Path,
    *,
    include_questions: bool = True,
) -> tuple[KpDocumentDraft, list[ExtractedExercise]]:
    exercises = parse_textbook_exercises(textbook_path) if include_questions else []
    doc_units: list[KpDocumentUnit] = []

    for num in sorted(MATH_UNITS.keys()):
        meta = MATH_UNITS[num]
        uid = unit_id_for(SUBJECT, GRADE, num)
        kps = [
            KpDocumentKp(
                knowledge_point_id=kp_id_for(SUBJECT, GRADE, num, slug),
                title=title,
                description=desc,
            )
            for slug, title, desc in meta["kps"]
        ]
        doc_units.append(
            KpDocumentUnit(
                unit_id=uid,
                unit_title=meta["title"],
                textbook_chapter=meta["chapter"],
                unit_description=f"{meta['chapter']} · {meta['title']}",
                knowledge_points=kps,
                questions=[],
            )
        )

    q_counters: dict[int, int] = {n: 0 for n in MATH_UNITS}
    for ex in exercises:
        if ex.confidence >= AUTO_IMPORT_CONFIDENCE and ex.expected_answer:
            q_counters[ex.unit_num] += 1
            qid = f"q-math-g3-u{ex.unit_num:02d}-{q_counters[ex.unit_num]:03d}"
            unit = doc_units[ex.unit_num - 1]
            unit.questions.append(
                KpDocumentQuestion(
                    question_id=qid,
                    stem=ex.stem,
                    knowledge_point_id=ex.knowledge_point_id,
                    expected_answer=ex.expected_answer,
                    explanation=ex.explanation,
                    default_error_code=ex.default_error_code,
                    answer_type=ex.answer_type,
                )
            )

    draft = KpDocumentDraft(
        subject=SUBJECT,
        grade=GRADE,
        textbook_ref=TEXTBOOK_REF,
        document_note="由沪教三年级数学上册 PDF 自动解析生成",
        units=doc_units,
        source_path=str(textbook_path),
    )
    return draft, exercises
