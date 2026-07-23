"""Upsert Chinese G3 U01 seed questions into local questions.db (no full wipe)."""
from __future__ import annotations

import json
from pathlib import Path

from agent_platform.learning import sqlite_store
from agent_platform.learning.contracts import Question
from agent_platform.learning._config import repo_root

SEED = repo_root() / "agent_platform/learning/question_bank/seed_questions_g3_chinese_pep.json"
DB = repo_root() / "agent_platform/learning/question_bank/questions.db"


def main() -> None:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    questions = [Question.model_validate(q) for q in data.get("questions", [])]
    n = sqlite_store.upsert_questions(DB, questions)
    after = len(sqlite_store.list_questions(DB, unit_id="chinese-g3-u01"))
    print(f"upserted={n} chinese-g3-u01_count={after}")


if __name__ == "__main__":
    main()
