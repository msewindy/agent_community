"""Per-session perception context for voice / Hermes (M4 D4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agent_platform.memory.trace import trace_from_session


def session_trace_id(session_id: str) -> str:
    return trace_from_session(session_id)


def session_file(sessions_dir: Path, session_id: str) -> Path:
    safe = session_id.replace("/", "_").replace("..", "_")[:128]
    return sessions_dir / f"{safe}.jsonl"


def append_session_record(sessions_dir: Path, session_id: str, record: dict[str, Any]) -> None:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    rec = {**record, "session_id": session_id}
    with session_file(sessions_dir, session_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_session_records(
    sessions_dir: Path, session_id: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    path = session_file(sessions_dir, session_id)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if line.strip():
            out.append(json.loads(line))
    return out


@dataclass
class SessionVisionContext:
    """Latest vision describe in this session."""

    description: str
    trace_id: str
    frame_path: Optional[str] = None
    question: Optional[str] = None


def latest_vision_context(
    sessions_dir: Path, session_id: str
) -> Optional[SessionVisionContext]:
    for rec in reversed(load_session_records(sessions_dir, session_id, limit=30)):
        if rec.get("topic") != "perception.describe":
            continue
        text = rec.get("text") or ""
        if not text:
            continue
        payload = rec.get("payload") or {}
        return SessionVisionContext(
            description=text,
            trace_id=str(rec.get("trace_id", "")),
            frame_path=payload.get("frame_path"),
            question=payload.get("question"),
        )
    return None


def format_session_prompt_prefix(ctx: SessionVisionContext, *, user_question: str) -> str:
    return (
        "[共域视觉上下文 — Reachy 按需观测，非持续监控]\n"
        f"用户问题：{user_question}\n"
        f"视觉描述：{ctx.description}\n"
        "请基于以上视觉描述回答用户；若描述不足以回答，请说明。"
    )
