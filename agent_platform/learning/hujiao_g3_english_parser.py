"""Parse 沪教版（五·四学制）三年级英语上册 PDF → KP draft + textbook exercises."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz

from agent_platform.learning.contracts import AnswerType
from agent_platform.learning.kp_document_parser import (
    KpDocumentDraft,
    KpDocumentKp,
    KpDocumentQuestion,
    KpDocumentUnit,
)

TEXTBOOK_REF = "沪教版（五·四学制）·三年级英语上册"
SUBJECT = "英语"
GRADE = 3

UNIT_TITLES: dict[int, tuple[str, str]] = {
    1: ("A new start", "Making a goal leaf"),
    2: ("Proud of you, proud of myself", "Talking about yourself and your classmates"),
    3: ("Our garden", "Making a school garden report"),
    4: ("Water in our life", "Making a lab report"),
    5: ("I can help", "Making a good helpers' star chart"),
    6: ("How do you feel?", "Writing a note to Mr Tree"),
    7: ("Jobs", "Doing a group interview"),
    8: ("Finding places", "Showing the way"),
    9: ("Special days", "Festival celebration"),
    10: ("Foods around the world", "World Food Festival"),
}

_RE_CJK = re.compile(r"[\u4e00-\u9fff]")
_RE_UNIT_SUMMARY = re.compile(r"U(\d+)\s*词句汇总")
_RE_UNIT_PAGE = re.compile(r"Unit\s+(\d+)\b", re.I)
_RE_DIALOGUE = re.compile(
    r"-\s*(?P<q>.+?\?)\s*\n-\s*(?P<a>.+?)(?=\n-\s*|\nI can\b|\Z)",
    re.S,
)
_RE_NUMBERED_STMT = re.compile(r"^\s*(\d+)\s{1,3}(.+?)\s*$", re.M)
_MANUAL_EXERCISE = re.compile(
    r"(Read and match|Look and write|Listen and|Look, listen|Tick the correct|"
    r"Draw the|Role-play|Do a survey|Write and draw|Watch and tick|Think and talk|"
    r"Show and tell|Make a plan)",
    re.I,
)

AUTO_IMPORT_CONFIDENCE = 0.85


@dataclass
class VocabPair:
    english: str
    chinese: str


@dataclass
class SentencePair:
    english: str
    chinese: str


@dataclass
class ParsedUnit:
    unit_num: int
    unit_id: str
    unit_title: str
    textbook_chapter: str
    core_vocab: list[VocabPair] = field(default_factory=list)
    extended_vocab: list[VocabPair] = field(default_factory=list)
    sentences: list[SentencePair] = field(default_factory=list)
    big_task: str = ""


@dataclass
class ExtractedExercise:
    unit_num: int
    page: int
    exercise_type: str
    stem: str
    expected_answer: str
    explanation: str
    knowledge_point_id: str
    default_error_code: str
    answer_type: AnswerType = AnswerType.exact
    confidence: float = 0.5
    review_reason: Optional[str] = None
    source_snippet: str = ""


def _is_english_line(line: str) -> bool:
    line = line.strip()
    if not line or line in {"A", "B", "C", "D", "E", "a", "b", "c", "d", "e"}:
        return False
    cjk = len(_RE_CJK.findall(line))
    latin = len(re.findall(r"[A-Za-z]", line))
    return latin > 0 and cjk <= max(2, latin // 4)


def _parse_vocab_block(text: str) -> list[VocabPair]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    lines = [
        ln
        for ln in lines
        if not re.match(r"^[一二三四]、", ln) and not re.match(r"^U\d+", ln)
    ]
    pairs: list[VocabPair] = []
    buf_en: list[str] = []
    buf_zh: list[str] = []

    def flush() -> None:
        nonlocal buf_en, buf_zh
        if not buf_en:
            buf_zh = []
            return
        for i, en in enumerate(buf_en):
            zh = buf_zh[i] if i < len(buf_zh) else ""
            pairs.append(VocabPair(english=en, chinese=zh))
        buf_en = []
        buf_zh = []

    for line in lines:
        if _is_english_line(line):
            if buf_zh:
                flush()
            buf_en.append(re.sub(r"\s+", " ", line))
        elif _RE_CJK.search(line):
            buf_zh.append(line)
    flush()
    return pairs


def _parse_sentence_block(text: str) -> list[SentencePair]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    pairs: list[SentencePair] = []
    buf_en: list[str] = []
    for line in lines:
        if _is_english_line(line):
            buf_en.append(line)
        elif _RE_CJK.search(line) and buf_en:
            en = re.sub(r"\s+", " ", " ".join(buf_en)).strip()
            zh = line
            if en and not en.endswith("?"):
                en = en.rstrip(" .")
            pairs.append(SentencePair(english=en, chinese=zh))
            buf_en = []
        elif _RE_CJK.search(line) and not buf_en:
            continue
    if buf_en:
        en = re.sub(r"\s+", " ", " ".join(buf_en)).strip()
        if en:
            pairs.append(SentencePair(english=en, chinese=""))
    return pairs


def _split_summary_units(text: str) -> dict[int, str]:
    matches = list(_RE_UNIT_SUMMARY.finditer(text))
    out: dict[int, str] = {}
    for i, m in enumerate(matches):
        num = int(m.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[num] = text[m.start() : end]
    return out


def parse_summary_pdf(path: Path) -> dict[int, ParsedUnit]:
    doc = fitz.open(path)
    text = "".join(page.get_text() for page in doc)
    doc.close()

    chunks = _split_summary_units(text)
    parsed: dict[int, ParsedUnit] = {}
    for num, chunk in chunks.items():
        if num not in UNIT_TITLES:
            continue
        title, big = UNIT_TITLES[num]
        unit_id = f"english-g3-u{num:02d}"
        core_m = re.search(r"一、核心词汇(.*?)二、核心句子", chunk, re.S)
        sent_m = re.search(r"二、核心句子(.*?)三、扩展词汇", chunk, re.S)
        ext_m = re.search(r"三、扩展词汇(.*)", chunk, re.S)

        core_vocab = _parse_vocab_block(core_m.group(1) if core_m else "")
        sentences = _parse_sentence_block(sent_m.group(1) if sent_m else "")
        extended = _parse_vocab_block(ext_m.group(1) if ext_m else "")

        parsed[num] = ParsedUnit(
            unit_num=num,
            unit_id=unit_id,
            unit_title=title,
            textbook_chapter=f"Unit {num}",
            core_vocab=core_vocab,
            extended_vocab=extended,
            sentences=sentences,
            big_task=big,
        )
    return parsed


def _unit_page_ranges(doc: fitz.Document) -> dict[int, tuple[int, int]]:
    starts: dict[int, int] = {}
    for i in range(doc.page_count):
        text = doc[i].get_text()
        for m in _RE_UNIT_PAGE.finditer(text):
            num = int(m.group(1))
            if 1 <= num <= 10 and num not in starts:
                starts[num] = i
    ordered = sorted(starts.items())
    ranges: dict[int, tuple[int, int]] = {}
    for idx, (num, start) in enumerate(ordered):
        end = ordered[idx + 1][1] - 1 if idx + 1 < len(ordered) else doc.page_count - 1
        ranges[num] = (start, end)
    return ranges


def _kp_ids(unit_num: int) -> dict[str, str]:
    base = f"kp-en-g3-u{unit_num:02d}"
    return {
        "vocab": f"{base}-vocab",
        "sentences": f"{base}-sentences",
        "grammar": f"{base}-grammar",
        "reading": f"{base}-reading",
    }


def _classify_kp(answer: str, question: str = "") -> tuple[str, str]:
    blob = f"{question} {answer}".lower()
    if any(k in blob for k in ("read", "story", "ant", "bird", "fox", "according to")):
        return "reading", "EN_READING_ERROR"
    if re.search(r"\b(am|is|are|i'm|we're|don't|can|want to|good at|how do you feel)\b", blob):
        return "grammar", "GRAMMAR_ERROR"
    if re.search(r"\b(where is|it's from|there is|there are|turn left|walk along)\b", blob):
        return "grammar", "GRAMMAR_ERROR"
    if len(answer.split()) <= 3 and answer.isalpha():
        return "vocab", "VOCAB_GAP"
    return "sentences", "GRAMMAR_ERROR"


def _normalize_answer(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip())
    s = s.rstrip(".")
    return s


def _story_supports_statement(story: str, statement: str) -> bool:
    story_l = story.lower()
    stmt_l = statement.lower()
    tokens = [w for w in re.findall(r"[a-z]{4,}", stmt_l) if w not in {"this", "that", "with", "from", "into"}]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in story_l)
    return hits >= max(2, len(tokens) // 2)


def _extract_find_rule_exercises(unit_num: int, page: int, text: str) -> list[ExtractedExercise]:
    out: list[ExtractedExercise] = []
    kps = _kp_ids(unit_num)
    seen: set[str] = set()
    for block in re.split(r"Find the rule", text, flags=re.I)[1:]:
        segment = block[:1200]
        for m in _RE_DIALOGUE.finditer(segment):
            q = _normalize_answer(m.group("q").replace("\n", " "))
            a = _normalize_answer(m.group("a").replace("\n", " "))
            if len(a) < 3:
                continue
            key = a.lower()
            if key in seen:
                continue
            seen.add(key)
            kp_key, err = _classify_kp(a, q)
            out.append(
                ExtractedExercise(
                    unit_num=unit_num,
                    page=page,
                    exercise_type="find_the_rule",
                    stem=f"句型练习：根据问句用英文完整作答（小写）。问：{q}",
                    expected_answer=a.lower(),
                    explanation=f"课本 Find the rule：{q} → {a}",
                    knowledge_point_id=kps[kp_key],
                    default_error_code=err,
                    confidence=0.95,
                    source_snippet=f"{q} / {a}",
                )
            )
        for line in segment.splitlines():
            ln = line.strip().lstrip("-").strip()
            if not ln or ln.startswith("I can ") or "?" in ln:
                continue
            if not _is_english_line(ln) or len(ln) < 8:
                continue
            if not re.match(
                r"^(I\'m|I am|You are|She is|He is|We\'re|We are|Let\'s|Walk|Turn|There is|There are)",
                ln,
                re.I,
            ):
                continue
            norm = _normalize_answer(ln)
            key = norm.lower()
            if key in seen:
                continue
            seen.add(key)
            kp_key, err = _classify_kp(norm)
            out.append(
                ExtractedExercise(
                    unit_num=unit_num,
                    page=page,
                    exercise_type="find_the_rule_pattern",
                    stem=f"课本句型默写（小写）：请写出与课本 Find the rule 一致的句子：{norm}",
                    expected_answer=key,
                    explanation=f"课本第 {page} 页 Find the rule 句型。",
                    knowledge_point_id=kps[kp_key],
                    default_error_code=err,
                    confidence=0.92,
                    source_snippet=norm,
                )
            )
    return out


def _extract_read_and_choose(unit_num: int, page: int, text: str) -> list[ExtractedExercise]:
    if not re.search(r"Read and choose", text, re.I):
        return []
    kps = _kp_ids(unit_num)
    story_parts: list[str] = []
    for line in text.splitlines():
        ln = line.strip()
        if re.match(r"^\d+\s", ln):
            break
        if _is_english_line(ln) and len(ln) > 20:
            story_parts.append(ln)
    story = " ".join(story_parts)
    if len(story) < 40:
        return []

    out: list[ExtractedExercise] = []
    for m in _RE_NUMBERED_STMT.finditer(text):
        stmt = _normalize_answer(m.group(2).replace("\n", " "))
        if len(stmt) < 10 or stmt.lower() in {"beginning", "middle", "ending"}:
            continue
        supported = _story_supports_statement(story, stmt)
        out.append(
            ExtractedExercise(
                unit_num=unit_num,
                page=page,
                exercise_type="read_and_choose",
                stem=(
                    f"阅读课文判断正误（填 true 或 false，小写）。"
                    f"课文节选：{story[:180]}… 陈述：{stmt}"
                ),
                expected_answer="true" if supported else "false",
                explanation=f"根据第 {page} 页 Story time 内容判断。",
                knowledge_point_id=kps["reading"],
                default_error_code="EN_READING_ERROR",
                confidence=0.88 if supported else 0.75,
                source_snippet=stmt,
            )
        )
    return out


def _extract_manual_pending(unit_num: int, page: int, text: str) -> list[ExtractedExercise]:
    out: list[ExtractedExercise] = []
    kps = _kp_ids(unit_num)
    for m in _MANUAL_EXERCISE.finditer(text):
        label = m.group(1)
        ctx_start = max(0, m.start() - 80)
        ctx = text[ctx_start : m.start() + 200].replace("\n", " ")
        out.append(
            ExtractedExercise(
                unit_num=unit_num,
                page=page,
                exercise_type=label.lower().replace(" ", "_"),
                stem=f"【待人工补全】课本第 {page} 页 · {label}（需看图/听音/教师答案）",
                expected_answer="",
                explanation="PDF 无法自动提取答案，请在家长端审核后补全 expected_answer。",
                knowledge_point_id=kps["reading"],
                default_error_code="EN_READING_ERROR",
                confidence=0.2,
                review_reason=f"课本习题「{label}」依赖图片/听力/开放作答，无法自动确定答案与知识点",
                source_snippet=ctx[:200],
            )
        )
    return out


def parse_textbook_exercises(path: Path) -> list[ExtractedExercise]:
    doc = fitz.open(path)
    ranges = _unit_page_ranges(doc)
    exercises: list[ExtractedExercise] = []
    seen_pending: set[tuple[int, str]] = set()

    for unit_num, (start, end) in ranges.items():
        for page_idx in range(start, end + 1):
            text = doc[page_idx].get_text()
            page_no = page_idx + 1
            exercises.extend(_extract_find_rule_exercises(unit_num, page_no, text))
            exercises.extend(_extract_read_and_choose(unit_num, page_no, text))
            for pending in _extract_manual_pending(unit_num, page_no, text):
                key = (unit_num, pending.exercise_type)
                if key in seen_pending:
                    continue
                seen_pending.add(key)
                exercises.append(pending)
    doc.close()
    return exercises


def _vocab_description(unit: ParsedUnit) -> str:
    lines = ["核心词汇（要求掌握）："]
    for p in unit.core_vocab:
        zh = f"（{p.chinese}）" if p.chinese else ""
        lines.append(f"- {p.english}{zh}")
    if unit.extended_vocab:
        lines.append("")
        lines.append("拓展词汇（讲解用，不单独推题）：")
        for p in unit.extended_vocab:
            zh = f"（{p.chinese}）" if p.chinese else ""
            lines.append(f"- {p.english}{zh}")
    return "\n".join(lines)


def _sentences_description(unit: ParsedUnit) -> str:
    lines = ["核心句子（熟读）："]
    for s in unit.sentences[:20]:
        zh = f" — {s.chinese}" if s.chinese else ""
        lines.append(f"- {s.english}{zh}")
    if len(unit.sentences) > 20:
        lines.append(f"- …共 {len(unit.sentences)} 句，详见汇总 PDF")
    return "\n".join(lines)


def _grammar_description(unit: ParsedUnit) -> str:
    patterns: list[str] = []
    for s in unit.sentences:
        if "?" in s.english or "want" in s.english.lower() or "good at" in s.english.lower():
            patterns.append(s.english)
    lines = [f"本单元 Big task：{unit.big_task}", "", "句型与表达："]
    for p in patterns[:12]:
        lines.append(f"- {p}")
    return "\n".join(lines)


def _reading_description(unit: ParsedUnit) -> str:
    return (
        f"本单元阅读重点：{unit.unit_title}（{unit.textbook_chapter}）。"
        f"结合课本 Story time / Reading time 段落理解关键词并作答。"
    )


def build_kp_document(
    summary_path: Path,
    textbook_path: Path,
    *,
    include_questions: bool = True,
) -> tuple[KpDocumentDraft, list[ExtractedExercise]]:
    units_data = parse_summary_pdf(summary_path)
    exercises = parse_textbook_exercises(textbook_path) if include_questions else []

    doc_units: list[KpDocumentUnit] = []
    for num in sorted(units_data):
        u = units_data[num]
        kps = _kp_ids(num)
        doc_units.append(
            KpDocumentUnit(
                unit_id=u.unit_id,
                unit_title=u.unit_title,
                textbook_chapter=u.textbook_chapter,
                unit_description=f"{u.textbook_chapter} · {u.big_task}",
                knowledge_points=[
                    KpDocumentKp(
                        knowledge_point_id=kps["vocab"],
                        title="单元核心词汇",
                        description=_vocab_description(u),
                    ),
                    KpDocumentKp(
                        knowledge_point_id=kps["sentences"],
                        title="单元核心句型",
                        description=_sentences_description(u),
                    ),
                    KpDocumentKp(
                        knowledge_point_id=kps["grammar"],
                        title="语法与表达",
                        description=_grammar_description(u),
                    ),
                    KpDocumentKp(
                        knowledge_point_id=kps["reading"],
                        title="课文阅读理解",
                        description=_reading_description(u),
                    ),
                ],
                questions=[],
            )
        )

    q_counters: dict[int, int] = {n: 0 for n in units_data}
    for ex in exercises:
        if ex.confidence >= AUTO_IMPORT_CONFIDENCE and ex.expected_answer:
            q_counters[ex.unit_num] += 1
            qid = f"q-en3-u{ex.unit_num:02d}-{q_counters[ex.unit_num]:03d}"
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
        document_note="由沪教三年级上册 PDF 自动解析生成",
        units=doc_units,
        source_path=str(summary_path),
    )
    return draft, exercises


def pending_exercises(exercises: list[ExtractedExercise]) -> list[ExtractedExercise]:
    return [
        ex
        for ex in exercises
        if ex.confidence < AUTO_IMPORT_CONFIDENCE or not ex.expected_answer
    ]


def build_pending_questions_draft(
    exercises: list[ExtractedExercise],
    *,
    textbook_ref: str = TEXTBOOK_REF,
) -> KpDocumentDraft:
    pending = pending_exercises(exercises)
    by_unit: dict[int, list[ExtractedExercise]] = {}
    for ex in pending:
        by_unit.setdefault(ex.unit_num, []).append(ex)

    units: list[KpDocumentUnit] = []
    for num in sorted(by_unit):
        umeta = UNIT_TITLES[num]
        kps = _kp_ids(num)
        questions: list[KpDocumentQuestion] = []
        for i, ex in enumerate(by_unit[num], 1):
            reason = ex.review_reason or "知识点关联或答案不确定，需人工确认"
            questions.append(
                KpDocumentQuestion(
                    question_id=f"q-en3-u{num:02d}-pending-{i:03d}",
                    stem=ex.stem,
                    knowledge_point_id=ex.knowledge_point_id or kps["reading"],
                    expected_answer=ex.expected_answer or "TBD",
                    explanation=f"{ex.explanation} 【待审】{reason}（课本 p{ex.page}）",
                    default_error_code=ex.default_error_code,
                    answer_type=ex.answer_type,
                )
            )
        units.append(
            KpDocumentUnit(
                unit_id=f"english-g3-u{num:02d}",
                unit_title=umeta[0],
                textbook_chapter=f"Unit {num}",
                unit_description="待审习题（课本图片/听力类）",
                knowledge_points=[],
                questions=questions,
            )
        )
    return KpDocumentDraft(
        subject=SUBJECT,
        grade=GRADE,
        textbook_ref=textbook_ref,
        document_note="沪教课本待人工审核习题（无知识点变更）",
        units=units,
        parse_warnings=["questions-only: 待补答案或确认 knowledge_point_id"],
    )
