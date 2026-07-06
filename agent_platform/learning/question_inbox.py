"""课本/批量上传的待审习题收件箱 — 在「习题处理 → 待归类」处理，不进知识点入库。"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.contracts import utc_now
from agent_platform.learning.kp_document_parser import KpDocumentDraft, KpDocumentQuestion, KpDocumentUnit
from agent_platform.learning.question_bank_ingest import import_draft_questions, validate_draft_questions
from agent_platform.learning.store import _atomic_write_json

PLACEHOLDER_ANSWERS = frozenset({"", "TBD", "tbd", "待补", "待人工补全"})


class QuestionInboxEntry(BaseModel):
    entry_id: str
    question_id: str
    unit_id: str
    unit_title: str = ""
    stem: str
    knowledge_point_id: str
    expected_answer: str = ""
    explanation: str = ""
    default_error_code: str = ""
    answer_type: str = "exact"
    source: str = "textbook_ingest"
    source_ref: Optional[str] = None
    status: Literal["pending", "imported", "dropped"] = "pending"
    created_at: str
    resolved_at: Optional[str] = None

    @property
    def needs_answer(self) -> bool:
        return self.expected_answer.strip() in PLACEHOLDER_ANSWERS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class QuestionInboxService:
    def __init__(self, data_root: Optional[Path] = None) -> None:
        cfg = load_student_learning_config()
        if data_root is None:
            raw = (cfg.get("data") or {}).get("root", "student_data")
            data_root = repo_root() / raw
        self._root = Path(data_root).resolve()
        self._path = self._root / "_question_inbox" / "pending.json"

    @property
    def inbox_path(self) -> Path:
        return self._path

    def _load(self) -> list[QuestionInboxEntry]:
        if not self._path.is_file():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return [QuestionInboxEntry.model_validate(e) for e in raw]

    def _save(self, entries: list[QuestionInboxEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps([e.model_dump(mode="json") for e in entries], ensure_ascii=False, indent=2)
            + "\n"
        )
        _atomic_write_json(self._path, payload)

    def list_pending(self) -> list[QuestionInboxEntry]:
        return [e for e in self._load() if e.status == "pending"]

    def upsert_from_draft(
        self,
        draft: KpDocumentDraft,
        *,
        source_ref: Optional[str] = None,
        replace_existing: bool = True,
    ) -> list[QuestionInboxEntry]:
        """Append or replace pending entries from a questions-only draft."""
        if not draft.has_questions():
            return []

        entries = self._load()
        if replace_existing:
            drop_ids = {q.question_id for u in draft.units for q in u.questions}
            entries = [e for e in entries if e.question_id not in drop_ids or e.status != "pending"]

        added: list[QuestionInboxEntry] = []
        existing_ids = {e.question_id for e in entries if e.status == "pending"}
        for unit in draft.units:
            for q in unit.questions:
                if q.question_id in existing_ids:
                    continue
                entry = QuestionInboxEntry(
                    entry_id=f"qin-{utc_now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}",
                    question_id=q.question_id,
                    unit_id=unit.unit_id,
                    unit_title=unit.unit_title,
                    stem=q.stem,
                    knowledge_point_id=q.knowledge_point_id,
                    expected_answer=q.expected_answer,
                    explanation=q.explanation,
                    default_error_code=q.default_error_code,
                    answer_type=q.answer_type.value,
                    source="textbook_ingest",
                    source_ref=source_ref,
                    created_at=_now_iso(),
                )
                entries.append(entry)
                added.append(entry)
        self._save(entries)
        return added

    def update_entry(
        self,
        entry_id: str,
        *,
        expected_answer: Optional[str] = None,
        knowledge_point_id: Optional[str] = None,
        explanation: Optional[str] = None,
    ) -> QuestionInboxEntry:
        entries = self._load()
        target = next((e for e in entries if e.entry_id == entry_id), None)
        if target is None:
            raise KeyError(f"question inbox entry not found: {entry_id}")
        if target.status != "pending":
            raise ValueError(f"entry already {target.status}: {entry_id}")

        updates: dict[str, Any] = {}
        if expected_answer is not None:
            updates["expected_answer"] = expected_answer.strip()
        if knowledge_point_id is not None:
            updates["knowledge_point_id"] = knowledge_point_id.strip()
        if explanation is not None:
            updates["explanation"] = explanation.strip()
        updated = target.model_copy(update=updates)
        entries = [updated if e.entry_id == entry_id else e for e in entries]
        self._save(entries)
        return updated

    def drop_entry(self, entry_id: str) -> QuestionInboxEntry:
        entries = self._load()
        target = next((e for e in entries if e.entry_id == entry_id), None)
        if target is None:
            raise KeyError(f"question inbox entry not found: {entry_id}")
        updated = target.model_copy(update={"status": "dropped", "resolved_at": _now_iso()})
        entries = [updated if e.entry_id == entry_id else e for e in entries]
        self._save(entries)
        return updated

    def import_entry(
        self,
        entry_id: str,
        *,
        expected_answer: Optional[str] = None,
        knowledge_point_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if expected_answer is not None or knowledge_point_id is not None:
            entry = self.update_entry(
                entry_id,
                expected_answer=expected_answer,
                knowledge_point_id=knowledge_point_id,
            )
        else:
            entry = next((e for e in self._load() if e.entry_id == entry_id), None)
            if entry is None:
                raise KeyError(f"question inbox entry not found: {entry_id}")
        if entry.status != "pending":
            raise ValueError(f"entry already {entry.status}: {entry_id}")
        if entry.needs_answer:
            raise ValueError("答案未补全，无法导入题库")

        q = KpDocumentQuestion(
            question_id=entry.question_id,
            stem=entry.stem,
            knowledge_point_id=entry.knowledge_point_id,
            expected_answer=entry.expected_answer,
            explanation=entry.explanation,
            default_error_code=entry.default_error_code,
        )
        from agent_platform.learning.contracts import AnswerType

        try:
            q = q.model_copy(update={"answer_type": AnswerType(entry.answer_type)})
        except ValueError:
            pass

        draft = KpDocumentDraft(
            subject="英语",
            grade=3,
            textbook_ref="question-inbox",
            units=[
                KpDocumentUnit(
                    unit_id=entry.unit_id,
                    unit_title=entry.unit_title,
                    questions=[q],
                )
            ],
        )
        v = validate_draft_questions(draft)
        if not v.ok:
            raise ValueError("; ".join(v.errors))

        result = import_draft_questions(draft, archive=False)
        entries = self._load()
        resolved = entry.model_copy(update={"status": "imported", "resolved_at": _now_iso()})
        entries = [resolved if e.entry_id == entry_id else e for e in entries]
        self._save(entries)
        return {"imported": result.imported, "question_id": entry.question_id, "warnings": result.warnings}

    def drop_classroom_placeholders(self) -> int:
        """Drop inbox rows that are PDF manual placeholders (family Alpha cleanup)."""
        entries = self._load()
        dropped = 0
        kept: list[QuestionInboxEntry] = []
        for entry in entries:
            is_placeholder = (
                entry.status == "pending"
                and (
                    "【待人工补全】" in entry.stem
                    or "-pending-" in entry.question_id
                )
            )
            if is_placeholder:
                kept.append(
                    entry.model_copy(
                        update={"status": "dropped", "resolved_at": _now_iso()}
                    )
                )
                dropped += 1
            else:
                kept.append(entry)
        if dropped:
            self._save(kept)
        return dropped

    def import_all_ready(self) -> dict[str, Any]:
        pending = self.list_pending()
        imported_ids: list[str] = []
        skipped: list[dict[str, str]] = []
        for entry in pending:
            if entry.needs_answer:
                skipped.append({"entry_id": entry.entry_id, "reason": "答案未补全"})
                continue
            try:
                self.import_entry(entry.entry_id)
                imported_ids.append(entry.question_id)
            except ValueError as exc:
                skipped.append({"entry_id": entry.entry_id, "reason": str(exc)})
        return {
            "imported": len(imported_ids),
            "imported_ids": imported_ids,
            "skipped": skipped,
            "remaining": len(self.list_pending()),
        }
