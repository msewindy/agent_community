"""课本课堂活动清单 — 不进入题库 / question_inbox（家庭 Alpha：Jarvis 不推题）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.g3_textbook_common import unit_id_for
from agent_platform.learning.hujiao_g3_english_parser import ExtractedExercise
from agent_platform.learning.store import _atomic_write_json

CLASSROOM_ONLY_NOTE = "请在课堂完成；Jarvis 仅支持文字题库推题，不代替听力/看图/角色扮演等活动。"


def _activities_path(data_root: Path, *, slug: str = "english-g3-hujiao") -> Path:
    return data_root / "_classroom_activities" / f"{slug}.json"


def save_from_pending_exercises(
    exercises: list[ExtractedExercise],
    *,
    data_root: Optional[Path] = None,
    textbook_ref: str,
    subject: str = "英语",
    grade: int = 3,
    slug: str = "english-g3-hujiao",
) -> Path:
    """Persist classroom-only activities extracted from PDF (no question bank)."""
    cfg = load_student_learning_config()
    if data_root is None:
        raw = (cfg.get("data") or {}).get("root", "student_data")
        data_root = repo_root() / raw
    data_root = Path(data_root).resolve()

    by_unit: dict[int, list[dict[str, Any]]] = {}
    seen: set[tuple[int, str]] = set()
    for ex in exercises:
        key = (ex.unit_num, ex.exercise_type)
        if key in seen:
            continue
        seen.add(key)
        by_unit.setdefault(ex.unit_num, []).append(
            {
                "page": ex.page,
                "activity_type": ex.exercise_type,
                "label": ex.exercise_type.replace("_", " "),
                "review_reason": ex.review_reason,
                "jarvis_policy": "classroom_only",
            }
        )

    units = []
    for num in sorted(by_unit):
        unit_id = unit_id_for(subject, grade, num)
        units.append(
            {
                "unit_id": unit_id,
                "unit_num": num,
                "activities": sorted(by_unit[num], key=lambda a: (a["page"], a["activity_type"])),
            }
        )

    payload = {
        "schema_version": "1.0.0",
        "subject": subject,
        "grade": grade,
        "textbook_ref": textbook_ref,
        "policy_note": CLASSROOM_ONLY_NOTE,
        "units": units,
        "activity_count": sum(len(u["activities"]) for u in units),
    }
    path = _activities_path(data_root, slug=slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def classroom_blurb_for_unit(unit_num: int, activities: list[dict[str, Any]]) -> str:
    """Wiki / KP 说明用：列出本单元课堂活动。"""
    lines = ["", "**课堂活动（请在课堂完成，Jarvis 不推题）**："]
    for act in sorted(activities, key=lambda a: (a.get("page", 0), a.get("activity_type", ""))):
        page = act.get("page")
        label = act.get("label") or act.get("activity_type", "")
        lines.append(f"- 课本 p{page} · {label}")
    return "\n".join(lines)
