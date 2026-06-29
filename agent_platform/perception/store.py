"""Perception data directory — policy + captures + event log (M4 D1)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agent_platform.perception._config import load_perception_config, resolve_store_root
from agent_platform.perception.contracts import PerceptionStoreLayout

_LOG_SEED = """# Perception Event Log

Append-only log for Reachy capture / observe events (M4).

"""


def layout_for(root: Path) -> PerceptionStoreLayout:
    root = root.resolve()
    return PerceptionStoreLayout(
        root=root,
        policy_path=root / "policy.json",
        captures_dir=root / "captures",
        events_log_path=root / "events.log.md",
    )


def ensure_store(root: Path | None = None) -> PerceptionStoreLayout:
    cfg = load_perception_config()
    root = (root or resolve_store_root(cfg)).resolve()
    lay = layout_for(root)
    lay.captures_dir.mkdir(parents=True, exist_ok=True)
    if not lay.events_log_path.is_file():
        lay.events_log_path.write_text(_LOG_SEED, encoding="utf-8")
    return lay


def append_event_log(lay: PerceptionStoreLayout, line: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with lay.events_log_path.open("a", encoding="utf-8") as f:
        f.write(f"- {ts} {line}\n")


def validate_store(root: Path | None = None) -> list[str]:
    lay = layout_for(root or resolve_store_root())
    missing: list[str] = []
    for p in (lay.root, lay.captures_dir, lay.events_log_path):
        if not p.exists():
            missing.append(str(p))
    return missing
