"""Export kp_catalog (+ optional questions) to editable `.kp.md` drafts (P1-3)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from agent_platform.learning.contracts import Question
from agent_platform.learning.kp_catalog import KpCatalogService, UnitCatalogEntry, get_kp_catalog_service
from agent_platform.learning.kp_document_parser import KpDocumentDraft, parse_kp_document_text
from agent_platform.learning.question_bank import QuestionBankService


_GRADE_CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}


@dataclass
class KpExportResult:
    filename: str
    content: str
    unit_ids: list[str] = field(default_factory=list)
    knowledge_point_count: int = 0
    question_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "unit_ids": self.unit_ids,
            "knowledge_point_count": self.knowledge_point_count,
            "question_count": self.question_count,
            "warnings": self.warnings,
        }


def _grade_label(grade: int) -> str:
    return f"{_GRADE_CN.get(grade, str(grade))}年级"


def _suggest_filename(subject: str, grade: int, unit_id: Optional[str] = None) -> str:
    if unit_id:
        return f"{unit_id}.kp.md"
    safe_subject = re.sub(r"[^\w.\-一-龥]", "_", subject.strip() or "export")
    return f"{safe_subject}-{_grade_label(grade)}.kp.md"


def _escape_single_line(text: str) -> str:
    return " ".join(text.split())


def _render_question(q: Question) -> list[str]:
    stem = _escape_single_line(q.stem)
    lines = [
        f"- {stem} → {q.question_id}",
        f"  知识点: {q.knowledge_point_id}",
        f"  答案: {q.expected_answer}",
        f"  题型: {q.answer_type.value}",
        f"  解析: {q.explanation}",
        f"  错因: {q.default_error_code}",
    ]
    if q.numeric_tolerance is not None:
        lines.append(f"  容差: {q.numeric_tolerance}")
    return lines


def _render_unit(
    unit: UnitCatalogEntry,
    questions: list[Question],
    *,
    include_questions: bool,
) -> list[str]:
    lines = [
        f"# 单元：{unit.unit_title}",
        "",
        f"unit_id: {unit.unit_id}",
    ]
    if unit.textbook_ref:
        lines.append(f"教材章节: {unit.textbook_ref}")
    lines.append("")
    lines.append("## 知识点")
    lines.append("")
    for kp in unit.knowledge_points:
        lines.append(f"- {kp.title} → {kp.knowledge_point_id}")
    if include_questions and questions:
        lines.append("")
        lines.append("## 练习题")
        lines.append("")
        for q in sorted(questions, key=lambda item: item.question_id):
            lines.extend(_render_question(q))
            lines.append("")
    lines.append("")
    return lines


def export_units_to_kp_md(
    units: list[UnitCatalogEntry],
    *,
    subject: str,
    grade: int,
    textbook_ref: Optional[str] = None,
    document_note: Optional[str] = None,
    questions_by_unit: Optional[dict[str, list[Question]]] = None,
    include_questions: bool = True,
) -> KpExportResult:
    if not units:
        raise ValueError("no units to export")

    ref = textbook_ref or units[0].textbook_ref or "（请填写教材版本）"
    note = document_note or "由知识库导出的可编辑草稿，修改后可在「知识点入库」重新上传"
    qmap = questions_by_unit or {}

    lines = [
        "---",
        f"学科: {subject}",
        f"年级: {grade}",
        f"教材版本: {ref}",
        f"文档说明: {note}",
        "---",
        "",
    ]

    kp_count = 0
    q_count = 0
    unit_ids: list[str] = []
    warnings: list[str] = []

    for unit in units:
        if unit.subject != subject or unit.grade != grade:
            warnings.append(f"skipped unit {unit.unit_id} (subject/grade mismatch)")
            continue
        unit_ids.append(unit.unit_id)
        kp_count += len(unit.knowledge_points)
        u_questions = qmap.get(unit.unit_id, [])
        q_count += len(u_questions)
        if include_questions and not u_questions:
            warnings.append(f"unit {unit.unit_id} has no questions in bank")
        lines.extend(_render_unit(unit, u_questions, include_questions=include_questions))

    content = "\n".join(lines).rstrip() + "\n"
    return KpExportResult(
        filename=_suggest_filename(subject, grade),
        content=content,
        unit_ids=unit_ids,
        knowledge_point_count=kp_count,
        question_count=q_count,
        warnings=warnings,
    )


class KpCatalogExportService:
    def __init__(
        self,
        catalog: Optional[KpCatalogService] = None,
        bank: Optional[QuestionBankService] = None,
    ) -> None:
        self._catalog = catalog or get_kp_catalog_service()
        self._bank = bank or QuestionBankService()

    def _questions_by_unit(self, unit_ids: set[str]) -> dict[str, list[Question]]:
        out: dict[str, list[Question]] = {uid: [] for uid in unit_ids}
        for q in self._bank.list_questions():
            if q.unit_id in unit_ids:
                out[q.unit_id].append(q)
        return out

    def export(
        self,
        *,
        subject: str,
        grade: int,
        unit_id: Optional[str] = None,
        include_questions: bool = True,
    ) -> KpExportResult:
        if unit_id:
            unit = self._catalog.get_unit(unit_id)
            if unit.subject != subject or unit.grade != grade:
                raise ValueError(
                    f"unit {unit_id} is {unit.subject} G{unit.grade}, "
                    f"not {subject} G{grade}"
                )
            units = [unit]
        else:
            units = [
                u
                for u in self._catalog.list_units(grade_level=grade, subject=subject, exact_grade=True)
            ]
            if not units:
                units = [
                    u
                    for u in self._catalog.catalog.units
                    if u.subject == subject and u.grade == grade
                ]

        if not units:
            raise ValueError(f"no catalog units for {subject!r} grade {grade}")

        unit_ids = {u.unit_id for u in units}
        qmap = self._questions_by_unit(unit_ids) if include_questions else {}
        textbook_ref = units[0].textbook_ref
        result = export_units_to_kp_md(
            units,
            subject=subject,
            grade=grade,
            textbook_ref=textbook_ref,
            questions_by_unit=qmap,
            include_questions=include_questions,
        )

        if unit_id:
            result.filename = _suggest_filename(subject, grade, unit_id)
        return result

    def export_and_validate(
        self,
        **kwargs,
    ) -> tuple[KpExportResult, KpDocumentDraft]:
        result = self.export(**kwargs)
        draft = parse_kp_document_text(result.content, source_path=result.filename)
        return result, draft
