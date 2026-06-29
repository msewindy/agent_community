"""Student learning data paths and atomic JSON persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config, resolve_data_root
from agent_platform.learning.contracts import (
    AttemptRecord,
    GapMap,
    GapSnapshot,
    LearningProactiveMessage,
    PushQueue,
    StudentContext,
    StudyPlan,
)


class StudentDataLayout:
    def __init__(self, root: Path, student_id: str) -> None:
        self.root = root.resolve()
        self.student_id = student_id
        self.student_dir = self.root / student_id
        self.context_path = self.student_dir / "context.json"
        self.attempts_dir = self.student_dir / "attempts"
        self.gap_map_path = self.student_dir / "gap_map.json"
        self.push_queue_path = self.student_dir / "push_queue.json"
        self.plans_dir = self.student_dir / "plans"
        self.proactive_log_path = self.student_dir / "learning_proactive.jsonl"
        self.evolution_dir = self.student_dir / "evolution"
        self.gap_snapshots_path = self.student_dir / "gap_snapshots.jsonl"
        self.profile_path = self.student_dir / "onboarding_profile.json"
        self.parent_reports_dir = self.student_dir / "parent_reports"

    def plan_path(self, plan_id: str) -> Path:
        return self.plans_dir / f"{plan_id}.json"

    def attempt_path(self, attempt_id: str) -> Path:
        return self.attempts_dir / f"{attempt_id}.json"

    def ensure_student_dir(self) -> None:
        self.student_dir.mkdir(parents=True, exist_ok=True)


def layout_for(student_id: str, data_root: Optional[Path] = None) -> StudentDataLayout:
    root = data_root or resolve_data_root()
    return StudentDataLayout(root, student_id)


def load_context(path: Path) -> StudentContext:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return StudentContext.model_validate(raw)


def save_context(path: Path, ctx: StudentContext) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(ctx.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=".context-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=f".{path.stem}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_attempt(path: Path, record: AttemptRecord) -> None:
    payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    _atomic_write_json(path, payload)


def load_attempt(path: Path) -> AttemptRecord:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return AttemptRecord.model_validate(raw)


def list_attempt_paths(attempts_dir: Path) -> list[Path]:
    if not attempts_dir.is_dir():
        return []
    return sorted(attempts_dir.glob("att-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def load_gap_map(path: Path) -> GapMap:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return GapMap.model_validate(raw)


def save_gap_map(path: Path, gap_map: GapMap) -> None:
    payload = json.dumps(gap_map.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    _atomic_write_json(path, payload)


def load_push_queue(path: Path) -> PushQueue:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PushQueue.model_validate(raw)


def save_push_queue(path: Path, queue: PushQueue) -> None:
    payload = json.dumps(queue.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    _atomic_write_json(path, payload)


def load_study_plan(path: Path) -> StudyPlan:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return StudyPlan.model_validate(raw)


def save_study_plan(path: Path, plan: StudyPlan) -> None:
    payload = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    _atomic_write_json(path, payload)


def append_proactive_message(path: Path, message: LearningProactiveMessage) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(message.model_dump(mode="json"), ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def list_proactive_messages(path: Path, limit: int = 50) -> list[LearningProactiveMessage]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    records = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        records.append(LearningProactiveMessage.model_validate(json.loads(line)))
    return list(reversed(records))


def append_gap_snapshot(path: Path, snapshot: GapSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def latest_gap_snapshots(path: Path) -> dict[str, GapSnapshot]:
    if not path.is_file():
        return {}
    latest: dict[str, GapSnapshot] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        snap = GapSnapshot.model_validate(json.loads(line))
        latest[snap.gap_id] = snap
    return latest
