"""In-process ObserveEvent bus + JSONL audit (M4 D4)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from agent_platform.memory.contracts import ObserveEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[["EventEnvelope"], None]


@dataclass
class EventEnvelope:
    topic: str
    event: ObserveEvent
    meta: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        ev = self.event
        return {
            "topic": self.topic,
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_id": ev.event_id,
            "trace_id": ev.trace_id,
            "source": ev.source.value if hasattr(ev.source, "value") else str(ev.source),
            "modality": list(ev.modality),
            "text": ev.text,
            "scene": ev.scene,
            "device_id": ev.device_id,
            "payload": ev.payload,
            "meta": self.meta,
        }


class EventBus:
    """Sync pub/sub for ObserveEvent — single process (voice / CLI / Hermes tools)."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._global: list[EventHandler] = []

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._global.append(handler)

    def publish(self, topic: str, event: ObserveEvent, *, meta: Optional[dict[str, Any]] = None) -> None:
        env = EventEnvelope(topic=topic, event=event, meta=meta or {})
        for h in self._global:
            try:
                h(env)
            except Exception:
                logger.exception("event bus global handler failed topic=%s", topic)
        for h in self._handlers.get(topic, []):
            try:
                h(env)
            except Exception:
                logger.exception("event bus handler failed topic=%s", topic)


class JsonlAuditSubscriber:
    """Append bus records to perception_data/events.jsonl."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, env: EventEnvelope) -> None:
        line = json.dumps(env.to_record(), ensure_ascii=False) + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)


class SessionBusSubscriber:
    """Mirror events into per-session JSONL (voice / Hermes session_id)."""

    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, env: EventEnvelope) -> None:
        sid = env.meta.get("session_id")
        if not sid and env.event.payload:
            sid = env.event.payload.get("session_id")
        if not sid and env.event.trace_id.startswith("hermes-"):
            sid = env.event.trace_id.removeprefix("hermes-")
        if not sid:
            return
        path = self._dir / f"{_safe_session_id(sid)}.jsonl"
        rec = env.to_record()
        rec["session_id"] = sid
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _safe_session_id(session_id: str) -> str:
    return session_id.replace("/", "_").replace("..", "_")[:128]


_default_bus: EventBus | None = None
_bus_wired_roots: set[str] = set()


def get_event_bus() -> EventBus:
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus


def reset_event_bus() -> None:
    global _default_bus, _bus_wired_roots
    _default_bus = None
    _bus_wired_roots = set()


def wire_default_subscribers(
    bus: EventBus,
    *,
    store_root: Path,
    memory_observe: bool = False,
    memory_service: Any = None,
) -> EventBus:
    root_key = str(store_root.resolve())
    if root_key in _bus_wired_roots:
        return bus
    _bus_wired_roots.add(root_key)

    bus.subscribe_all(JsonlAuditSubscriber(store_root / "events.jsonl"))
    bus.subscribe_all(SessionBusSubscriber(store_root / "sessions"))
    if memory_observe:
        mem = memory_service
        if mem is None:
            from agent_platform.memory.service import MemoryService

            mem = MemoryService()

        def _mem_handler(env: EventEnvelope) -> None:
            if env.topic.startswith("perception."):
                mem.write_observe(env.event)

        bus.subscribe_all(_mem_handler)
    return bus
