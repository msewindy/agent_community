"""Proactive data directory (M5)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent_platform.proactive._config import load_proactive_config, resolve_store_root
from agent_platform.proactive.contracts import ProactiveStoreLayout

_LOG_SEED = """# Proactive Event Log

Append-only log for proactive evaluate / feedback (M5 / US-5).

"""


def layout_for(root: Path) -> ProactiveStoreLayout:
    root = root.resolve()
    return ProactiveStoreLayout(
        root=root,
        sessions_dir=root / "sessions",
        events_log_path=root / "events.log.md",
    )


def ensure_store(root: Path | None = None) -> ProactiveStoreLayout:
    cfg = load_proactive_config()
    root = (root or resolve_store_root(cfg)).resolve()
    lay = layout_for(root)
    lay.sessions_dir.mkdir(parents=True, exist_ok=True)
    if not lay.events_log_path.is_file():
        lay.events_log_path.write_text(_LOG_SEED, encoding="utf-8")
    return lay


def append_event_log(lay: ProactiveStoreLayout, line: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with lay.events_log_path.open("a", encoding="utf-8") as f:
        f.write(f"- {ts} {line}\n")
