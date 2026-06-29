"""SQLite-backed question bank storage (Phase 4)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from agent_platform.learning.contracts import AnswerType, Question

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    question_id TEXT PRIMARY KEY,
    unit_id TEXT NOT NULL,
    knowledge_point_id TEXT NOT NULL,
    stem TEXT NOT NULL,
    answer_type TEXT NOT NULL,
    expected_answer TEXT NOT NULL,
    explanation TEXT NOT NULL,
    default_error_code TEXT NOT NULL,
    numeric_tolerance REAL
);
CREATE INDEX IF NOT EXISTS idx_questions_unit ON questions(unit_id);
CREATE INDEX IF NOT EXISTS idx_questions_kp ON questions(knowledge_point_id);
CREATE INDEX IF NOT EXISTS idx_questions_error ON questions(default_error_code);
"""


def _row_to_question(row: sqlite3.Row) -> Question:
    tol = row["numeric_tolerance"]
    return Question(
        question_id=row["question_id"],
        unit_id=row["unit_id"],
        knowledge_point_id=row["knowledge_point_id"],
        stem=row["stem"],
        answer_type=AnswerType(row["answer_type"]),
        expected_answer=row["expected_answer"],
        explanation=row["explanation"],
        default_error_code=row["default_error_code"],
        numeric_tolerance=tol,
    )


def ensure_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)


def import_from_json(seed_path: Path, db_path: Path, *, replace_all: bool = True) -> int:
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    questions = [Question.model_validate(q) for q in data.get("questions", [])]
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        if replace_all:
            conn.execute("DELETE FROM questions")
        for q in questions:
            conn.execute(
                """
                INSERT OR REPLACE INTO questions (
                    question_id, unit_id, knowledge_point_id, stem,
                    answer_type, expected_answer, explanation,
                    default_error_code, numeric_tolerance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    q.question_id,
                    q.unit_id,
                    q.knowledge_point_id,
                    q.stem,
                    q.answer_type.value,
                    q.expected_answer,
                    q.explanation,
                    q.default_error_code,
                    q.numeric_tolerance,
                ),
            )
        conn.commit()
    return len(questions)


def list_questions(
    db_path: Path,
    unit_id: Optional[str] = None,
    knowledge_point_id: Optional[str] = None,
    error_code: Optional[str] = None,
) -> list[Question]:
    if not db_path.is_file():
        return []
    ensure_schema(db_path)
    clauses: list[str] = []
    params: list[str] = []
    if unit_id:
        clauses.append("unit_id = ?")
        params.append(unit_id)
    if knowledge_point_id:
        clauses.append("knowledge_point_id = ?")
        params.append(knowledge_point_id)
    if error_code:
        clauses.append("default_error_code = ?")
        params.append(error_code)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM questions {where} ORDER BY question_id"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_question(r) for r in rows]


def get_question(db_path: Path, question_id: str) -> Optional[Question]:
    if not db_path.is_file():
        return None
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
    return _row_to_question(row) if row else None


def count_questions(db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM questions").fetchone()
    return int(row[0]) if row else 0
