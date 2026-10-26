"""Upsert C2 window-period seed questions (math u02 + english seeds) into questions.db."""

from __future__ import annotations

import json
from pathlib import Path

from agent_platform.learning import sqlite_store
from agent_platform.learning.contracts import Question
from agent_platform.learning._config import repo_root

SEEDS = [
    repo_root() / "agent_platform/learning/question_bank/seed_questions_g3_math_hujiao.json",
    repo_root() / "agent_platform/learning/question_bank/seed_questions_g3_english_hujiao.json",
]
DB = repo_root() / "agent_platform/learning/question_bank/questions.db"


def main() -> None:
    all_q: list[Question] = []
    for path in SEEDS:
        data = json.loads(path.read_text(encoding="utf-8"))
        all_q.extend(Question.model_validate(q) for q in data.get("questions", []))
    n = sqlite_store.upsert_questions(DB, all_q)
    u02 = len(sqlite_store.list_questions(DB, unit_id="math-g3-u02"))
    en01 = len(sqlite_store.list_questions(DB, unit_id="english-g3-u01"))
    print(f"upserted={n} math-g3-u02={u02} english-g3-u01={en01}")


if __name__ == "__main__":
    main()
