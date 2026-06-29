"""When to offer wiki ingest — default silent, explicit /沉淀, depth threshold (M3 D6)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from agent_platform.wiki.store import WikiStoreLayout

Role = Literal["user", "assistant", "system"]

_DEFAULT_OFFER_MSG = (
    "这次讨论比较有价值，要不要沉淀到知识库？"
    "回复「好」或发送 /沉淀 开始写入。"
)

_EXPLICIT_DEFAULT = ("/沉淀", "/precipitate", "/wiki-ingest")


@dataclass
class PrecipitateConfig:
    enabled: bool = True
    offer_after_turns: int = 0
    min_assistant_turns: int = 3
    min_user_chars_total: int = 150
    min_user_chars_per_turn: int = 20
    cooldown_turns: int = 10
    explicit_commands: list[str] = field(default_factory=lambda: list(_EXPLICIT_DEFAULT))
    offer_message: str = _DEFAULT_OFFER_MSG
    state_path: Optional[Path] = None


@dataclass
class PrecipitateDecision:
    offer: bool
    reason_code: str
    message: str = ""
    session_id: str = ""
    assistant_turns: int = 0
    user_chars: int = 0
    topic: str = ""
    explicit: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class _SessionState:
    session_id: str
    topic: str = ""
    user_turns: int = 0
    assistant_turns: int = 0
    user_chars: int = 0
    turns_since_offer: int = 0
    last_offer_turn: int = 0
    declined: bool = False
    messages: list[dict[str, str]] = field(default_factory=list)


def load_precipitate_config(cfg: dict) -> PrecipitateConfig:
    p = cfg.get("precipitate") or {}
    ingest = cfg.get("ingest") or {}
    # Legacy: ingest.offer_after_turns → precipitate.offer_after_turns
    offer_after = p.get("offer_after_turns", ingest.get("offer_after_turns", 0))
    commands = p.get("explicit_commands") or list(_EXPLICIT_DEFAULT)
    state_raw = p.get("state_path")
    state_path = Path(state_raw).expanduser() if state_raw else None
    return PrecipitateConfig(
        enabled=bool(p.get("enabled", True)),
        offer_after_turns=int(offer_after),
        min_assistant_turns=int(p.get("min_assistant_turns", 3)),
        min_user_chars_total=int(p.get("min_user_chars_total", 150)),
        min_user_chars_per_turn=int(p.get("min_user_chars_per_turn", 20)),
        cooldown_turns=int(p.get("cooldown_turns", 10)),
        explicit_commands=[str(c).strip().lower() for c in commands if str(c).strip()],
        offer_message=str(p.get("offer_message", _DEFAULT_OFFER_MSG)),
        state_path=state_path,
    )


def is_explicit_command(text: str, commands: list[str]) -> bool:
    low = text.strip().lower()
    for cmd in commands:
        if low == cmd or low.startswith(cmd + " ") or low.startswith(cmd + "\n"):
            return True
    return False


def infer_topic(text: str, fallback: str = "") -> str:
    if fallback.strip():
        return fallback.strip()[:80]
    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
    stop = {"the", "and", "for", "什么", "怎么", "如何", "为什么", "可以", "一个"}
    kept = [t for t in tokens if t not in stop][:5]
    return " ".join(kept) if kept else "general"


class PrecipitateSessionStore:
    """Per-session turn counters for offer evaluation."""

    def __init__(self, state_path: Optional[Path] = None) -> None:
        self._path = state_path
        self._sessions: dict[str, _SessionState] = {}
        if state_path and state_path.is_file():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for sid, raw in (data.get("sessions") or {}).items():
            self._sessions[sid] = _SessionState(
                session_id=sid,
                topic=str(raw.get("topic", "")),
                user_turns=int(raw.get("user_turns", 0)),
                assistant_turns=int(raw.get("assistant_turns", 0)),
                user_chars=int(raw.get("user_chars", 0)),
                turns_since_offer=int(raw.get("turns_since_offer", 0)),
                last_offer_turn=int(raw.get("last_offer_turn", 0)),
                declined=bool(raw.get("declined", False)),
                messages=list(raw.get("messages", [])),
            )

    def save(self) -> None:
        if not self._path:
            return
        payload = {
            "sessions": {
                sid: {
                    "topic": s.topic,
                    "user_turns": s.user_turns,
                    "assistant_turns": s.assistant_turns,
                    "user_chars": s.user_chars,
                    "turns_since_offer": s.turns_since_offer,
                    "last_offer_turn": s.last_offer_turn,
                    "declined": s.declined,
                    "messages": s.messages[-50:],
                }
                for sid, s in self._sessions.items()
            }
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def get(self, session_id: str) -> _SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = _SessionState(session_id=session_id)
        return self._sessions[session_id]

    def record_turn(
        self,
        session_id: str,
        role: Role,
        text: str,
        *,
        topic: Optional[str] = None,
    ) -> _SessionState:
        st = self.get(session_id)
        st.turns_since_offer += 1
        st.messages.append({"role": role, "text": text[:4000]})
        if role == "user":
            st.user_turns += 1
            st.user_chars += len(text.strip())
            if topic:
                st.topic = topic.strip()[:80]
            elif not st.topic:
                st.topic = infer_topic(text)
        elif role == "assistant":
            st.assistant_turns += 1
        self.save()
        return st

    def mark_offered(self, session_id: str) -> None:
        st = self.get(session_id)
        st.last_offer_turn = st.assistant_turns + st.user_turns
        st.turns_since_offer = 0
        self.save()

    def mark_declined(self, session_id: str) -> None:
        st = self.get(session_id)
        st.declined = True
        st.turns_since_offer = 0
        self.save()

    def reset_declined(self, session_id: str) -> None:
        st = self.get(session_id)
        st.declined = False
        self.save()


def evaluate_precipitate(
    session_id: str,
    *,
    message: str = "",
    role: Role = "user",
    topic: Optional[str] = None,
    config: PrecipitateConfig,
    store: PrecipitateSessionStore,
    record: bool = True,
) -> PrecipitateDecision:
    """Decide whether Agent should offer wiki ingest for this session turn."""
    if record and message:
        store.record_turn(session_id, role, message, topic=topic)

    st = store.get(session_id)
    topic_s = st.topic or infer_topic(message, topic or "")
    base = PrecipitateDecision(
        offer=False,
        reason_code="silent",
        session_id=session_id,
        assistant_turns=st.assistant_turns,
        user_chars=st.user_chars,
        topic=topic_s,
    )

    if not config.enabled:
        base.reason_code = "disabled"
        return base

    explicit = is_explicit_command(message, config.explicit_commands)
    if explicit:
        return PrecipitateDecision(
            offer=True,
            reason_code="explicit_command",
            message=config.offer_message,
            session_id=session_id,
            assistant_turns=st.assistant_turns,
            user_chars=st.user_chars,
            topic=topic_s,
            explicit=True,
            details={"command": message.strip()[:40]},
        )

    # User accepted after prior offer
    if role == "user" and _is_acceptance(message):
        return PrecipitateDecision(
            offer=True,
            reason_code="user_accepted",
            message="好的，请把本次讨论整理后写入 raw/ 并执行 ingest。",
            session_id=session_id,
            assistant_turns=st.assistant_turns,
            user_chars=st.user_chars,
            topic=topic_s,
            details={"ready_for_ingest": True},
        )

    if st.declined and st.turns_since_offer < config.cooldown_turns:
        base.reason_code = "user_declined_cooldown"
        return base

    if config.offer_after_turns == 0 and config.min_assistant_turns <= 0:
        base.reason_code = "silent_mode"
        return base

    if (
        st.last_offer_turn > 0
        and 0 < st.turns_since_offer < config.cooldown_turns
    ):
        base.reason_code = "cooldown"
        base.details = {"turns_since_offer": st.turns_since_offer}
        return base

    depth_ok = (
        st.assistant_turns >= config.min_assistant_turns
        and st.user_chars >= config.min_user_chars_total
    )
    turn_ok = (st.user_turns + st.assistant_turns) >= config.offer_after_turns

    if depth_ok and (turn_ok or config.offer_after_turns == 0):
        store.mark_offered(session_id)
        return PrecipitateDecision(
            offer=True,
            reason_code="depth_threshold",
            message=config.offer_message,
            session_id=session_id,
            assistant_turns=st.assistant_turns,
            user_chars=st.user_chars,
            topic=topic_s,
            details={
                "min_assistant_turns": config.min_assistant_turns,
                "min_user_chars_total": config.min_user_chars_total,
            },
        )

    base.reason_code = "insufficient_depth"
    base.details = {
        "need_assistant_turns": config.min_assistant_turns,
        "need_user_chars": config.min_user_chars_total,
    }
    return base


def _is_acceptance(text: str) -> bool:
    low = text.strip().lower()
    accept = ("好", "好的", "可以", "行", "沉淀", "yes", "ok", "sure", "yep")
    return any(low == a or low.startswith(a + " ") for a in accept) and len(low) < 40


def write_session_transcript(
    layout: WikiStoreLayout,
    session_id: str,
    messages: list[dict[str, str]],
    *,
    topic: str = "session",
) -> str:
    """Write chat transcript to raw/transcripts/ for subsequent ingest (US-4 prep)."""
    out_dir = layout.raw_dir / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\-\u4e00-\u9fff]", "-", topic.lower())[:40].strip("-") or "session"
    name = f"{slug}-{session_id[:8]}.md"
    path = out_dir / name
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "---",
        f"title: {topic}",
        f"session_id: {session_id}",
        f"transcribed: {now}",
        "---",
        "",
        f"# {topic}",
        "",
    ]
    for m in messages:
        role = m.get("role", "user")
        text = m.get("text", "").strip()
        if text:
            lines.append(f"## {role}\n\n{text}\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"raw/transcripts/{name}"
