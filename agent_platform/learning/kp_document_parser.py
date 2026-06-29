"""Parse `.kp.md` knowledge-point documents (P1-A)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from agent_platform.learning.kp_catalog import KnowledgePointDef, UnitCatalogEntry


_KP_LINE = re.compile(
    r"^\s*-\s*(.+?)\s*(?:→|->)\s*(kp-[a-z0-9-]+)\s*$",
    re.IGNORECASE,
)
_UNIT_HEADING = re.compile(r"^#\s*单元[:：]\s*(.+)\s*$")
_META_LINE = re.compile(r"^(unit_id|教材章节|单元说明)[:：]\s*(.+)\s*$")
_KP_DESC = re.compile(r"^\s*说明[:：]\s*(.+)\s*$")


class KpDocumentParseError(ValueError):
    def __init__(self, message: str, line: Optional[int] = None) -> None:
        self.line = line
        if line is not None:
            super().__init__(f"line {line}: {message}")
        else:
            super().__init__(message)


class KpDocumentKp(BaseModel):
    knowledge_point_id: str
    title: str
    description: Optional[str] = None


class KpDocumentUnit(BaseModel):
    unit_id: str
    unit_title: str
    textbook_chapter: Optional[str] = None
    unit_description: Optional[str] = None
    knowledge_points: list[KpDocumentKp] = Field(default_factory=list)


class KpDocumentDraft(BaseModel):
    subject: str
    grade: int = Field(ge=1, le=6)
    textbook_ref: str
    document_note: Optional[str] = None
    units: list[KpDocumentUnit] = Field(default_factory=list)
    source_path: Optional[str] = None
    parse_warnings: list[str] = Field(default_factory=list)

    @field_validator("subject")
    @classmethod
    def _subject_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("subject must not be empty")
        return value

    def to_catalog_units(self) -> list[UnitCatalogEntry]:
        return [
            UnitCatalogEntry(
                unit_id=u.unit_id,
                grade=self.grade,
                subject=self.subject,
                unit_title=u.unit_title,
                textbook_ref=self.textbook_ref,
                knowledge_points=[
                    KnowledgePointDef(
                        knowledge_point_id=kp.knowledge_point_id,
                        title=kp.title,
                    )
                    for kp in u.knowledge_points
                ],
            )
            for u in self.units
        ]

    def summary_preview(self, limit: int = 500) -> str:
        parts = [
            f"学科={self.subject} 年级={self.grade} 单元数={len(self.units)}",
        ]
        for unit in self.units:
            parts.append(f"- {unit.unit_title} ({unit.unit_id}): {len(unit.knowledge_points)} 个知识点")
        text = "\n".join(parts)
        return text[:limit]


def _split_frontmatter(text: str) -> tuple[dict, str, int]:
    if not text.startswith("---"):
        raise KpDocumentParseError("missing YAML frontmatter (expected opening ---)")
    end = text.find("\n---", 3)
    if end == -1:
        raise KpDocumentParseError("unclosed YAML frontmatter (missing closing ---)")
    raw_yaml = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    try:
        meta = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as e:
        raise KpDocumentParseError(f"invalid frontmatter YAML: {e}") from e
    if not isinstance(meta, dict):
        raise KpDocumentParseError("frontmatter must be a YAML mapping")
    return meta, body, 1


def _parse_frontmatter(meta: dict) -> tuple[str, int, str, Optional[str]]:
    subject = meta.get("学科")
    grade = meta.get("年级")
    textbook_ref = meta.get("教材版本")
    document_note = meta.get("文档说明")

    if subject is None or str(subject).strip() == "":
        raise KpDocumentParseError("frontmatter missing required field: 学科")
    if grade is None:
        raise KpDocumentParseError("frontmatter missing required field: 年级")
    if textbook_ref is None or str(textbook_ref).strip() == "":
        raise KpDocumentParseError("frontmatter missing required field: 教材版本")

    try:
        grade_int = int(grade)
    except (TypeError, ValueError) as e:
        raise KpDocumentParseError(f"年级 must be integer 1-6, got {grade!r}") from e
    if not 1 <= grade_int <= 6:
        raise KpDocumentParseError(f"年级 must be 1-6, got {grade_int}")

    return str(subject).strip(), grade_int, str(textbook_ref).strip(), (
        str(document_note).strip() if document_note else None
    )


def parse_kp_document_text(text: str, *, source_path: Optional[str] = None) -> KpDocumentDraft:
    meta, body, _ = _split_frontmatter(text)
    subject, grade, textbook_ref, document_note = _parse_frontmatter(meta)
    warnings: list[str] = []
    units: list[KpDocumentUnit] = []
    unit_ids: set[str] = set()
    kp_ids: set[str] = set()

    current_unit: Optional[KpDocumentUnit] = None
    in_kp_section = False

    for line_no, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line.strip():
            continue

        unit_match = _UNIT_HEADING.match(line)
        if unit_match:
            if current_unit is not None:
                if not current_unit.unit_id:
                    raise KpDocumentParseError("unit missing unit_id", line_no)
                if not current_unit.knowledge_points:
                    raise KpDocumentParseError(
                        f"unit {current_unit.unit_id!r} has no knowledge points",
                        line_no,
                    )
            current_unit = KpDocumentUnit(
                unit_id="",
                unit_title=unit_match.group(1).strip(),
            )
            units.append(current_unit)
            in_kp_section = False
            continue

        if current_unit is None:
            if line.startswith("#"):
                warnings.append(f"line {line_no}: ignored heading {line!r}")
            continue

        if line.strip() == "## 知识点":
            in_kp_section = True
            continue

        meta_match = _META_LINE.match(line.strip())
        if meta_match and not in_kp_section:
            key, value = meta_match.group(1), meta_match.group(2).strip()
            if key == "unit_id":
                if current_unit.unit_id:
                    raise KpDocumentParseError("duplicate unit_id in same unit block", line_no)
                if value in unit_ids:
                    raise KpDocumentParseError(f"duplicate unit_id {value!r} in document", line_no)
                unit_ids.add(value)
                current_unit.unit_id = value
            elif key == "教材章节":
                current_unit.textbook_chapter = value
            elif key == "单元说明":
                current_unit.unit_description = value
            continue

        if in_kp_section:
            kp_match = _KP_LINE.match(line)
            if kp_match:
                title = kp_match.group(1).strip()
                kp_id = kp_match.group(2).strip()
                if kp_id in kp_ids:
                    raise KpDocumentParseError(f"duplicate knowledge_point_id {kp_id!r}", line_no)
                kp_ids.add(kp_id)
                current_unit.knowledge_points.append(
                    KpDocumentKp(knowledge_point_id=kp_id, title=title)
                )
                continue
            desc_match = _KP_DESC.match(line)
            if desc_match and current_unit.knowledge_points:
                current_unit.knowledge_points[-1].description = desc_match.group(1).strip()
                continue
            raise KpDocumentParseError(
                f"invalid knowledge point line (expected '- 标题 → kp-id'): {line!r}",
                line_no,
            )

        if line.startswith("#") and not line.startswith("##"):
            warnings.append(f"line {line_no}: ignored heading {line!r}")

    if current_unit is None:
        raise KpDocumentParseError("document has no unit blocks (# 单元：...)")

    if not current_unit.unit_id:
        raise KpDocumentParseError("last unit missing unit_id")
    if not current_unit.knowledge_points:
        raise KpDocumentParseError(
            f"unit {current_unit.unit_id!r} has no knowledge points",
        )

    return KpDocumentDraft(
        subject=subject,
        grade=grade,
        textbook_ref=textbook_ref,
        document_note=document_note,
        units=units,
        source_path=source_path,
        parse_warnings=warnings,
    )


def parse_kp_document(path: str | Path) -> KpDocumentDraft:
    file_path = Path(path).resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"kp document not found: {file_path}")
    text = file_path.read_text(encoding="utf-8")
    draft = parse_kp_document_text(text, source_path=str(file_path))
    if file_path.suffix.lower() not in {".md", ".markdown"} and not file_path.name.endswith(".kp.md"):
        draft.parse_warnings.append(
            f"unexpected extension {file_path.suffix!r}; recommended .kp.md",
        )
    return draft
