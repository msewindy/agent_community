"""Per-session proactive state — snooze after dismiss (M5)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class SessionProactiveState:
    session_id: str
    snoozed: bool = False
    snooze_reason: str = ""
    work_minutes_reported: float = 0.0
    proposals_sent: int = 0
    last_proposal_trace: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _session_path(sessions_dir: Path, session_id: str) -> Path:
    safe = session_id.replace("/", "_").replace("..", "_")[:128]
    return sessions_dir / f"{safe}.json"


def load_session(sessions_dir: Path, session_id: str) -> SessionProactiveState:
    path = _session_path(sessions_dir, session_id)
    if not path.is_file():
        return SessionProactiveState(session_id=session_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    return SessionProactiveState(
        session_id=session_id,
        snoozed=bool(data.get("snoozed", False)),
        snooze_reason=str(data.get("snooze_reason", "")),
        work_minutes_reported=float(data.get("work_minutes_reported", 0)),
        proposals_sent=int(data.get("proposals_sent", 0)),
        last_proposal_trace=str(data.get("last_proposal_trace", "")),
        extra=data.get("extra") or {},
    )


def save_session(sessions_dir: Path, state: SessionProactiveState) -> None:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = _session_path(sessions_dir, state.session_id)
    payload = {
        "session_id": state.session_id,
        "snoozed": state.snoozed,
        "snooze_reason": state.snooze_reason,
        "work_minutes_reported": state.work_minutes_reported,
        "proposals_sent": state.proposals_sent,
        "last_proposal_trace": state.last_proposal_trace,
        "extra": state.extra,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_dismiss_message(text: str, phrases: list[str]) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    for p in phrases:
        if p.lower() in t:
            return True
    return bool(re.search(r"(别|不要).{0,4}打扰", t))
