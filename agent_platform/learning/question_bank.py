"""Seed question bank loader — JSON fallback + SQLite (Phase 4 / P0 multi-seed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.contracts import Question
from agent_platform.learning import sqlite_store


class QuestionBankService:
    def __init__(
        self,
        seed_path: Optional[Path] = None,
        sqlite_path: Optional[Path] = None,
    ) -> None:
        cfg = load_student_learning_config()
        bank_cfg = cfg.get("question_bank") or {}
        self._seed_paths = self._resolve_seed_paths(bank_cfg, seed_path)
        if sqlite_path is None:
            raw_sqlite = bank_cfg.get(
                "sqlite_path",
                "agent_platform/learning/question_bank/questions.db",
            )
            sqlite_path = repo_root() / raw_sqlite
        self._sqlite_path = sqlite_path.resolve()
        self._by_id: dict[str, Question] = {}
        self._use_sqlite = self._sqlite_path.is_file() and sqlite_store.count_questions(self._sqlite_path) > 0
        if not self._use_sqlite:
            self._by_id = self._load_all_json()

    def _resolve_seed_paths(self, bank_cfg: dict, seed_path: Optional[Path]) -> list[Path]:
        if seed_path is not None:
            return [seed_path.resolve()]
        paths_cfg = bank_cfg.get("seed_paths")
        if paths_cfg:
            return [repo_root() / p for p in paths_cfg]
        single = bank_cfg.get("seed_path")
        if single:
            return [repo_root() / single]
        return [repo_root() / "agent_platform/learning/question_bank/seed_questions_g2_math.json"]

    def _load_all_json(self) -> dict[str, Question]:
        merged: dict[str, Question] = {}
        for path in self._seed_paths:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for q in data.get("questions", []):
                question = Question.model_validate(q)
                merged[question.question_id] = question
        return merged

    @property
    def uses_sqlite(self) -> bool:
        return self._use_sqlite

    @property
    def sqlite_path(self) -> Path:
        return self._sqlite_path

    @property
    def seed_paths(self) -> list[Path]:
        return self._seed_paths

    def import_seed_to_sqlite(self) -> int:
        total = 0
        for i, path in enumerate(self._seed_paths):
            if not path.is_file():
                continue
            total += sqlite_store.import_from_json(
                path,
                self._sqlite_path,
                replace_all=(i == 0),
            )
        self._use_sqlite = True
        self._by_id = {}
        return total

    def list_questions(self, unit_id: Optional[str] = None) -> list[Question]:
        if self._use_sqlite:
            return sqlite_store.list_questions(self._sqlite_path, unit_id=unit_id)
        items = list(self._by_id.values())
        if unit_id:
            items = [q for q in items if q.unit_id == unit_id]
        return sorted(items, key=lambda q: q.question_id)

    def list_for_gap(
        self,
        unit_id: str,
        knowledge_point_id: str,
        error_code: str,
    ) -> list[Question]:
        if self._use_sqlite:
            exact = sqlite_store.list_questions(
                self._sqlite_path,
                unit_id=unit_id,
                knowledge_point_id=knowledge_point_id,
                error_code=error_code,
            )
        else:
            exact = [
                q
                for q in self.list_questions(unit_id)
                if q.knowledge_point_id == knowledge_point_id and q.default_error_code == error_code
            ]
        if exact:
            return sorted(exact, key=lambda q: q.question_id)
        if self._use_sqlite:
            relaxed = sqlite_store.list_questions(
                self._sqlite_path,
                unit_id=unit_id,
                knowledge_point_id=knowledge_point_id,
            )
        else:
            relaxed = [
                q
                for q in self.list_questions(unit_id)
                if q.knowledge_point_id == knowledge_point_id
            ]
        return sorted(relaxed, key=lambda q: q.question_id)

    def list_for_gap_kp(
        self,
        knowledge_point_id: str,
        error_code: Optional[str] = None,
        *,
        allowed_unit_ids: Optional[set[str]] = None,
        prefer_unit_id: Optional[str] = None,
    ) -> list[Question]:
        """Find questions for a gap by KP across units (optionally within allowed units)."""
        if self._use_sqlite:
            if error_code:
                exact = sqlite_store.list_questions(
                    self._sqlite_path,
                    knowledge_point_id=knowledge_point_id,
                    error_code=error_code,
                )
            else:
                exact = []
            pool = exact if exact else sqlite_store.list_questions(
                self._sqlite_path,
                knowledge_point_id=knowledge_point_id,
            )
        else:
            pool = list(self._by_id.values())
            if error_code:
                exact = [
                    q
                    for q in pool
                    if q.knowledge_point_id == knowledge_point_id
                    and q.default_error_code == error_code
                ]
                pool = exact if exact else [
                    q for q in pool if q.knowledge_point_id == knowledge_point_id
                ]
            else:
                pool = [q for q in pool if q.knowledge_point_id == knowledge_point_id]

        if allowed_unit_ids is not None:
            pool = [q for q in pool if q.unit_id in allowed_unit_ids]

        def _sort_key(q: Question) -> tuple:
            pref = 0 if prefer_unit_id and q.unit_id == prefer_unit_id else 1
            return (pref, q.question_id)

        return sorted(pool, key=_sort_key)

    def suggest_questions(
        self,
        *,
        unit_id: str,
        knowledge_point_id: Optional[str] = None,
        focus: str = "current_unit",
        limit: int = 5,
        allowed_unit_ids: Optional[set[str]] = None,
        prefer_unit_id: Optional[str] = None,
        exclude_question_ids: Optional[set[str]] = None,
    ) -> list[Question]:
        """Real-time question pick for Agent (not offline push_queue)."""
        limit = max(1, min(limit, 10))
        exclude = exclude_question_ids or set()
        pool: list[Question] = []

        if focus == "remediation" and knowledge_point_id:
            pool = self.list_for_gap_kp(
                knowledge_point_id,
                None,
                allowed_unit_ids=allowed_unit_ids,
                prefer_unit_id=prefer_unit_id or unit_id,
            )
        elif knowledge_point_id:
            if self._use_sqlite:
                pool = sqlite_store.list_questions(
                    self._sqlite_path,
                    unit_id=unit_id,
                    knowledge_point_id=knowledge_point_id,
                )
            else:
                pool = [
                    q
                    for q in self.list_questions(unit_id)
                    if q.knowledge_point_id == knowledge_point_id
                ]
        else:
            pool = self.list_questions(unit_id)

        out: list[Question] = []
        for q in pool:
            if q.question_id in exclude:
                continue
            out.append(q)
            if len(out) >= limit:
                break
        return out

    def get(self, question_id: str) -> Question:
        if self._use_sqlite:
            q = sqlite_store.get_question(self._sqlite_path, question_id)
            if q is None:
                raise KeyError(f"question not found: {question_id}")
            return q
        q = self._by_id.get(question_id)
        if q is None:
            raise KeyError(f"question not found: {question_id}")
        return q
